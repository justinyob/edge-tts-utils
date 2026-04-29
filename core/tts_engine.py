import logging
import os
import platform
import sys
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import edge_tts
from pydub import AudioSegment

from config import TEMP_DIR_PREFIX
from core.exceptions import (
    MSG_DISK_WRITE_FAILED,
    MSG_SYNTHESIS_FAILED,
    CancellationError,
    DiskWriteError,
    SynthesisError,
)
from utils.paths import resource_path
from utils.text_chunker import chunk_text

log = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    output_path: str
    srt_path: Optional[str]
    duration_seconds: float
    chunk_count: int


def _format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_srt(path: str, entries: list[tuple[float, float, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, start=1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n")
            f.write(f"{text}\n\n")


def _safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


class TTSEngine:
    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            if platform.system() == "Windows":
                ffmpeg_path = resource_path("ffmpeg.exe")
            else:
                ffmpeg_path = resource_path("ffmpeg")
            if os.path.exists(ffmpeg_path):
                AudioSegment.converter = ffmpeg_path

    async def _synthesize_chunk(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        output_path: str,
        collect_boundaries: bool,
    ) -> list[dict]:
        boundaries: list[dict] = []
        try:
            communicate = edge_tts.Communicate(
                text, voice, rate=rate, pitch=pitch, volume=volume
            )
        except Exception as e:
            log.exception("edge_tts.Communicate construction failed")
            raise SynthesisError(MSG_SYNTHESIS_FAILED) from e

        try:
            f = open(output_path, "wb")
        except OSError as e:
            log.exception("Failed to open chunk file for writing: %s", output_path)
            raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e

        try:
            try:
                stream = communicate.stream()
                while True:
                    try:
                        event = await stream.__anext__()
                    except StopAsyncIteration:
                        break
                    etype = event.get("type")
                    if etype == "audio":
                        f.write(event["data"])
                    elif etype == "WordBoundary" and collect_boundaries:
                        boundaries.append(event)
            except Exception as e:
                log.exception("edge_tts streaming failed for chunk")
                raise SynthesisError(MSG_SYNTHESIS_FAILED) from e
        finally:
            try:
                f.close()
            except OSError:
                log.exception("Failed to close chunk file: %s", output_path)
        return boundaries

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        output_path: str,
        srt_path: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> SynthesisResult:
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("Text is empty after chunking.")

        total = len(chunks)
        temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
        chunk_files: list[str] = []
        srt_entries: list[tuple[float, float, str]] = []
        cumulative_offset_seconds = 0.0

        try:
            for i, chunk in enumerate(chunks):
                if cancel_event is not None and cancel_event.is_set():
                    raise CancellationError("Synthesis cancelled.")

                chunk_path = os.path.join(temp_dir, f"chunk_{i:05d}.mp3")
                boundaries = await self._synthesize_chunk(
                    chunk, voice, rate, pitch, volume,
                    chunk_path, collect_boundaries=srt_path is not None,
                )
                chunk_files.append(chunk_path)

                if srt_path is not None:
                    for ev in boundaries:
                        # offset/duration are in 100-nanosecond units
                        start = cumulative_offset_seconds + ev["offset"] / 10_000_000
                        end = start + ev["duration"] / 10_000_000
                        srt_entries.append((start, end, ev.get("text", "")))

                segment = AudioSegment.from_file(chunk_path, format="mp3")
                cumulative_offset_seconds += len(segment) / 1000.0

                if progress_callback is not None:
                    progress_callback(i + 1, total)

            try:
                combined = AudioSegment.empty()
                for cf in chunk_files:
                    combined += AudioSegment.from_file(cf, format="mp3")
            except Exception as e:
                log.exception("Failed to concatenate audio chunks")
                raise SynthesisError(MSG_SYNTHESIS_FAILED) from e

            try:
                combined.export(output_path, format="mp3")
            except (OSError, PermissionError) as e:
                log.exception("Failed writing final MP3 to %s", output_path)
                raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e
            except Exception as e:
                log.exception("Failed exporting final MP3 to %s", output_path)
                raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e

            if srt_path is not None:
                try:
                    _write_srt(srt_path, srt_entries)
                except OSError as e:
                    log.exception("Failed writing SRT to %s", srt_path)
                    raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e

            return SynthesisResult(
                output_path=output_path,
                srt_path=srt_path,
                duration_seconds=len(combined) / 1000.0,
                chunk_count=total,
            )
        finally:
            for cf in chunk_files:
                _safe_remove(cf)
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass

    async def synthesize_preview(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
    ) -> str:
        words = text.split()
        snippet = " ".join(words[:100])
        if not snippet.strip():
            raise ValueError("Preview text is empty.")

        fd, path = tempfile.mkstemp(prefix=TEMP_DIR_PREFIX, suffix=".mp3")
        os.close(fd)
        try:
            await self._synthesize_chunk(
                snippet, voice, rate, pitch, volume, path,
                collect_boundaries=False,
            )
            return path
        except Exception:
            _safe_remove(path)
            raise


if __name__ == "__main__":
    import asyncio

    async def _test():
        engine = TTSEngine()
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "She sells seashells by the seashore. "
            "How much wood would a woodchuck chuck?"
        )

        out_fd, out_path = tempfile.mkstemp(prefix="tts_test_", suffix=".mp3")
        os.close(out_fd)
        srt_path = out_path.replace(".mp3", ".srt")

        progress_log = []

        def progress(i, total):
            progress_log.append((i, total))

        try:
            result = await engine.synthesize(
                text=text,
                voice="en-US-JennyNeural",
                rate="+0%",
                pitch="+0Hz",
                volume="+0%",
                output_path=out_path,
                srt_path=srt_path,
                progress_callback=progress,
            )
            assert os.path.exists(out_path), "output mp3 missing"
            assert os.path.getsize(out_path) > 0, "output mp3 empty"
            assert os.path.exists(srt_path), "srt missing"
            assert result.duration_seconds > 0
            assert result.chunk_count == 1
            assert progress_log == [(1, 1)], f"progress log: {progress_log}"
            print(f"  synthesize: {os.path.getsize(out_path)} bytes, "
                  f"{result.duration_seconds:.2f}s, srt entries OK")

            preview = await engine.synthesize_preview(
                text=text,
                voice="en-US-JennyNeural",
                rate="+0%",
                pitch="+0Hz",
                volume="+0%",
            )
            assert os.path.exists(preview)
            assert os.path.getsize(preview) > 0
            print(f"  preview: {os.path.getsize(preview)} bytes")
            _safe_remove(preview)
        finally:
            _safe_remove(out_path)
            _safe_remove(srt_path)

        print("TTSEngine: OK")

    asyncio.run(_test())
