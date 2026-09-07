"""Turn edge-tts boundary events into readable SRT cues.

edge-tts reports timings per word (or per sentence, depending on the
`boundary` mode requested). One SRT cue per word is technically valid but
unusable in a player, so words are grouped into caption-sized cues here.
"""

import re
from dataclasses import dataclass

from config import (
    SRT_MAX_CHARS_PER_LINE,
    SRT_MAX_CUE_SECONDS,
    SRT_MAX_GAP_SECONDS,
    SRT_MAX_LINES_PER_CUE,
    SRT_MIN_CUE_SECONDS,
)

# Punctuation that belongs to the word it follows.
_TRAILING_PUNCT = set(".,!?;:…—\"')]}»”’")
# Punctuation that ends a spoken sentence — a natural cue break.
_SENTENCE_END = re.compile(r"[.!?…][\"')\]}»”’]*$")

_HNS_PER_SECOND = 10_000_000  # edge-tts reports 100-nanosecond ticks


@dataclass
class Cue:
    start: float
    end: float
    text: str


def format_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp (HH:MM:SS,mmm)."""
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def align_words_to_source(source: str, words: list[str]) -> list[str]:
    """Re-attach punctuation from `source` to boundary-event word texts.

    edge-tts strips punctuation from WordBoundary events, which loses both
    readability and the sentence breaks we want to split cues on. Walk the
    source text in step with the events and recover it. Falls back to the
    raw event text for any word that cannot be located.
    """
    lowered = source.lower()
    out: list[str] = []
    pos = 0
    for word in words:
        idx = source.find(word, pos)
        if idx == -1:
            idx = lowered.find(word.lower(), pos)
        if idx == -1:
            out.append(word)
            continue
        end = idx + len(word)
        while end < len(source) and source[end] in _TRAILING_PUNCT:
            end += 1
        out.append(source[idx:end])
        pos = end
    return out


def events_to_words(
    events: list[dict],
    source: str | None = None,
    offset_seconds: float = 0.0,
) -> list[tuple[float, float, str]]:
    """Convert raw boundary events to (start, end, text) tuples in seconds."""
    texts = [str(ev.get("text", "")) for ev in events]
    if source is not None:
        texts = align_words_to_source(source, texts)

    words: list[tuple[float, float, str]] = []
    for ev, text in zip(events, texts):
        text = text.strip()
        if not text:
            continue
        start = offset_seconds + ev["offset"] / _HNS_PER_SECOND
        end = start + ev["duration"] / _HNS_PER_SECOND
        words.append((start, end, text))
    return words


def _greedy_lines(words: list[str], width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _wrap(text: str, max_chars: int, max_lines: int) -> str:
    """Wrap cue text over at most `max_lines` balanced lines of `max_chars`.

    Finds the narrowest width that still fits the line budget, which splits
    evenly instead of leaving a full line followed by a stub. If nothing fits
    the budget, an extra line is preferred over an over-long one.
    """
    if len(text) <= max_chars or max_lines <= 1:
        return text

    words = text.split()
    best = _greedy_lines(words, max_chars)
    lo, hi = 1, max_chars
    while lo <= hi:
        mid = (lo + hi) // 2
        lines = _greedy_lines(words, mid)
        if len(lines) <= max_lines:
            best = lines
            hi = mid - 1
        else:
            lo = mid + 1
    return "\n".join(best)


def build_cues(
    words: list[tuple[float, float, str]],
    max_chars_per_line: int = SRT_MAX_CHARS_PER_LINE,
    max_lines: int = SRT_MAX_LINES_PER_CUE,
    max_seconds: float = SRT_MAX_CUE_SECONDS,
    min_seconds: float = SRT_MIN_CUE_SECONDS,
    max_gap: float = SRT_MAX_GAP_SECONDS,
) -> list[Cue]:
    """Group timed words into caption-sized, non-overlapping cues."""
    if not words:
        return []

    max_chars = max_chars_per_line * max_lines
    cues: list[Cue] = []
    buf: list[str] = []
    buf_start = 0.0
    buf_end = 0.0
    prev_end = 0.0

    def flush() -> None:
        nonlocal buf
        if buf:
            cues.append(Cue(buf_start, buf_end, _wrap(" ".join(buf), max_chars_per_line, max_lines)))
            buf = []

    for start, end, text in words:
        if buf:
            pending = len(" ".join(buf)) + 1 + len(text)
            too_long = pending > max_chars
            too_slow = (end - buf_start) > max_seconds
            big_gap = (start - prev_end) > max_gap
            if too_long or too_slow or big_gap:
                flush()

        if not buf:
            buf_start = start
        buf.append(text)
        buf_end = end
        prev_end = end

        # A sentence ending is the most natural place to cut.
        if _SENTENCE_END.search(text):
            flush()

    flush()

    # Enforce a readable minimum duration without letting cues overlap.
    for i, cue in enumerate(cues):
        if cue.end < cue.start:
            cue.end = cue.start
        if cue.end - cue.start < min_seconds:
            limit = cues[i + 1].start if i + 1 < len(cues) else cue.start + min_seconds
            cue.end = max(cue.end, min(cue.start + min_seconds, limit))
        if i + 1 < len(cues) and cue.end > cues[i + 1].start:
            cue.end = cues[i + 1].start
    return cues


def compose_srt(cues: list[Cue]) -> str:
    parts = []
    for i, cue in enumerate(cues, start=1):
        parts.append(
            f"{i}\n{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}\n{cue.text}\n"
        )
    return "\n".join(parts)


def write_srt(path: str, cues: list[Cue]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(compose_srt(cues))


if __name__ == "__main__":
    # Test 1: timestamp formatting, including the millisecond rounding edge
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(1.9996) == "00:00:02,000"
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(-5) == "00:00:00,000"
    assert format_timestamp(59.9999) == "00:01:00,000"
    print("Test 1 (timestamps) — OK")

    # Test 2: punctuation is recovered from the source text
    src = "Hello, world! How are you?"
    aligned = align_words_to_source(src, ["Hello", "world", "How", "are", "you"])
    assert aligned == ["Hello,", "world!", "How", "are", "you?"], aligned
    # Unmatched words fall back to the event text
    assert align_words_to_source("abc", ["zzz"]) == ["zzz"]
    print("Test 2 (punctuation alignment) — OK")

    # Test 3: events convert to seconds and honour the chunk offset
    events = [
        {"type": "WordBoundary", "offset": 10_000_000, "duration": 5_000_000, "text": "Hi"},
        {"type": "WordBoundary", "offset": 20_000_000, "duration": 5_000_000, "text": "there"},
    ]
    words = events_to_words(events, source="Hi there.", offset_seconds=100.0)
    assert words == [(101.0, 101.5, "Hi"), (102.0, 102.5, "there.")], words
    print("Test 3 (event conversion + offset) — OK")

    # Test 4: cues break on sentence ends, never overlap, respect limits
    src4 = "One two three four. Five six seven eight nine ten."
    ev4 = [
        {"type": "WordBoundary", "offset": i * 5_000_000, "duration": 4_000_000, "text": w}
        for i, w in enumerate(
            ["One", "two", "three", "four", "Five", "six", "seven", "eight", "nine", "ten"]
        )
    ]
    cues = build_cues(events_to_words(ev4, source=src4))
    assert len(cues) >= 2, cues
    assert cues[0].text.replace("\n", " ") == "One two three four."
    for a, b in zip(cues, cues[1:]):
        assert a.end <= b.start, f"overlap: {a} / {b}"
    for c in cues:
        assert c.end > c.start
        assert all(len(line) <= SRT_MAX_CHARS_PER_LINE for line in c.text.split("\n")), c.text
        assert len(c.text.split("\n")) <= SRT_MAX_LINES_PER_CUE, c.text
    print(f"Test 4 (cue grouping): {len(cues)} cues — OK")

    # Test 5: a long pause forces a cue break even mid-sentence
    ev5 = [
        {"type": "WordBoundary", "offset": 0, "duration": 1_000_000, "text": "alpha"},
        {"type": "WordBoundary", "offset": 100_000_000, "duration": 1_000_000, "text": "beta"},
    ]
    cues5 = build_cues(events_to_words(ev5))
    assert len(cues5) == 2, cues5
    print("Test 5 (gap split) — OK")

    # Test 6: sentence-level events (older edge-tts) still produce cues
    ev6 = [{
        "type": "SentenceBoundary", "offset": 0, "duration": 30_000_000,
        "text": "A whole sentence arrives as one event here.",
    }]
    cues6 = build_cues(events_to_words(ev6))
    assert len(cues6) == 1 and "sentence" in cues6[0].text
    print("Test 6 (sentence-boundary fallback) — OK")

    # Test 7: no events -> no cues, and composing yields an empty document
    assert build_cues([]) == []
    assert compose_srt([]) == ""
    srt = compose_srt(cues)
    assert srt.startswith("1\n") and " --> " in srt
    print("Test 7 (empty + compose) — OK")

    print("SrtBuilder: OK")
