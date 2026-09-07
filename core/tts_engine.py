import inspect
import logging
import os
import platform
import sys
import tempfile
import threading
from dataclasses import dataclass
from functools import lru_cache
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
from utils.srt_builder import build_cues, events_to_words, write_srt
from utils.text_chunker import chunk_text

log = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    output_path: str
    srt_path: Optional[str]
    duration_seconds: float
    chunk_count: int
    srt_cue_count: int = 0


_BOUNDARY_TYPES = ("WordBoundary", "SentenceBoundary")


@lru_cache(maxsize=1)
def _supports_boundary_arg() -> bool:
    """edge-tts gained the `boundary` keyword in 7.x; degrade gracefully without it."""
    try:
        return "boundary" in inspect.signature(edge_tts.Communicate.__init__).parameters
    except (TypeError, ValueError):
        return False


def _safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


class TTSEngine:
    def __init__(self) -> None:
        self._configure_ffmpeg()

    @staticmethod
    def _configure_ffmpeg() -> None:
        """Point pydub at the bundled ffmpeg/ffprobe binaries when frozen."""
        if not getattr(sys, "frozen", False):
            return

        is_windows = platform.system() == "Windows"
        ffmpeg_name = "ffmpeg.exe" if is_windows else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if is_windows else "ffprobe"

        ffmpeg_path = resource_path(ffmpeg_name)
        ffprobe_path = resource_path(ffprobe_name)

        if os.path.exists(ffmpeg_path):
            AudioSegment.converter = ffmpeg_path
            # pydub also reads `ffmpeg` on some code paths
            AudioSegment.ffmpeg = ffmpeg_path
            log.info("Bundled ffmpeg located at %s", ffmpeg_path)
        else:
            log.warning("Bundled ffmpeg not found at %s; falling back to PATH", ffmpeg_path)

        if os.path.exists(ffprobe_path):
            AudioSegment.ffprobe = ffprobe_path
            log.info("Bundled ffprobe located at %s", ffprobe_path)
        elif os.path.exists(ffmpeg_path):
            # Better than failing: ffmpeg can answer most ffprobe queries pydub cares about,
            # and even a wrong-arg invocation surfaces as a SubprocessError instead of WinError 2.
            AudioSegment.ffprobe = ffmpeg_path
            log.warning("Bundled ffprobe missing; using ffmpeg at %s as fallback", ffmpeg_path)

        # pydub.utils.mediainfo_json calls shutil.which("ffprobe") and ignores
        # AudioSegment.ffprobe entirely. Prepend the bundle dir to PATH so the
        # bare-name lookup resolves to our shipped binaries.
        bin_dir = os.path.dirname(ffmpeg_path)
        if os.path.isdir(bin_dir):
            existing = os.environ.get("PATH", "")
            if bin_dir not in existing.split(os.pathsep):
                os.environ["PATH"] = bin_dir + os.pathsep + existing
                log.info("Prepended bundle dir to PATH: %s", bin_dir)

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
        kwargs = {"rate": rate, "pitch": pitch, "volume": volume}
        if collect_boundaries and _supports_boundary_arg():
            # edge-tts defaults to SentenceBoundary; word-level timings let us
            # build properly sized caption cues.
            kwargs["boundary"] = "WordBoundary"
        try:
            communicate = edge_tts.Communicate(text, voice, **kwargs)
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
                    elif collect_boundaries and etype in _BOUNDARY_TYPES:
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
        srt_words: list[tuple[float, float, str]] = []
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
                    # Chunk timings are chunk-relative; shift them onto the
                    # timeline of the concatenated output.
                    srt_words.extend(
                        events_to_words(boundaries, source=chunk,
                                        offset_seconds=cumulative_offset_seconds)
                    )

                try:
                    segment = AudioSegment.from_file(chunk_path, format="mp3")
                except FileNotFoundError as e:
                    log.exception("ffmpeg/ffprobe not found while measuring chunk %s", chunk_path)
                    raise SynthesisError(MSG_SYNTHESIS_FAILED) from e
                except Exception as e:
                    log.exception("Failed to read chunk %s for duration", chunk_path)
                    raise SynthesisError(MSG_SYNTHESIS_FAILED) from e
                cumulative_offset_seconds += len(segment) / 1000.0

                if progress_callback is not None:
                    progress_callback(i + 1, total)

            try:
                combined = AudioSegment.empty()
                for cf in chunk_files:
                    combined += AudioSegment.from_file(cf, format="mp3")
            except FileNotFoundError as e:
                log.exception("ffmpeg/ffprobe not found while concatenating chunks")
                raise SynthesisError(MSG_SYNTHESIS_FAILED) from e
            except Exception as e:
                log.exception("Failed to concatenate audio chunks")
                raise SynthesisError(MSG_SYNTHESIS_FAILED) from e

            try:
                combined.export(output_path, format="mp3")
            except FileNotFoundError as e:
                log.exception("ffmpeg not found while exporting MP3 to %s", output_path)
                raise SynthesisError(MSG_SYNTHESIS_FAILED) from e
            except (OSError, PermissionError) as e:
                log.exception("Failed writing final MP3 to %s", output_path)
                raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e
            except Exception as e:
                log.exception("Failed exporting final MP3 to %s", output_path)
                raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e

            cue_count = 0
            if srt_path is not None:
                cues = build_cues(srt_words)
                cue_count = len(cues)
                if not cues:
                    log.warning(
                        "No boundary events received; SRT at %s will be empty", srt_path
                    )
                try:
                    write_srt(srt_path, cues)
                except OSError as e:
                    log.exception("Failed writing SRT to %s", srt_path)
                    raise DiskWriteError(MSG_DISK_WRITE_FAILED) from e

            return SynthesisResult(
                output_path=output_path,
                srt_path=srt_path,
                duration_seconds=len(combined) / 1000.0,
                chunk_count=total,
                srt_cue_count=cue_count,
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
    import re

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

            srt_body = open(srt_path, encoding="utf-8").read()
            assert srt_body.strip(), "srt is empty — no boundary events collected"
            assert result.srt_cue_count > 0, "no cues built"
            assert srt_body.count(" --> ") == result.srt_cue_count
            assert srt_body.startswith("1\n"), srt_body[:40]
            # Cues must stay inside the audio timeline and never run backwards
            times = re.findall(
                r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)", srt_body
            )
            assert len(times) == result.srt_cue_count
            prev_end = 0.0
            for h1, m1, s1, ms1, h2, m2, s2, ms2 in times:
                start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
                end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
                assert start >= prev_end, f"cue overlaps previous: {start} < {prev_end}"
                assert end > start, f"non-positive cue duration at {start}"
                assert end <= result.duration_seconds + 1.0, (
                    f"cue end {end} past audio duration {result.duration_seconds}"
                )
                prev_end = end
            print(f"  synthesize: {os.path.getsize(out_path)} bytes, "
                  f"{result.duration_seconds:.2f}s, {result.srt_cue_count} srt cues OK")

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
