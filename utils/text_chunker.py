import re

from config import CHUNK_SIZE_WORDS

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=\S)")


def _split_sentences(paragraph: str) -> list[str]:
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    parts = _SENTENCE_SPLIT.split(paragraph)
    return [p.strip() for p in parts if p.strip()]


def _word_count(s: str) -> int:
    return len(s.split())


def chunk_text(text: str, max_words: int = CHUNK_SIZE_WORDS) -> list[str]:
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    paragraphs = _PARAGRAPH_SPLIT.split(text)

    for paragraph in paragraphs:
        sentences = _split_sentences(paragraph)
        if not sentences:
            continue

        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            sw = _word_count(sentence)
            if sw > max_words:
                if current:
                    chunks.append(" ".join(current).strip())
                    current = []
                    current_words = 0
                chunks.append(sentence.strip())
                continue

            if current_words + sw > max_words and current:
                chunks.append(" ".join(current).strip())
                current = [sentence]
                current_words = sw
            else:
                current.append(sentence)
                current_words += sw

        if current:
            chunks.append(" ".join(current).strip())

    return [c for c in chunks if c]


if __name__ == "__main__":
    # Test 1: short text
    short = "Hello world. This is short."
    r1 = chunk_text(short, max_words=500)
    assert r1 == [short], f"test1 failed: {r1}"
    print(f"Test 1 (short text): {len(r1)} chunk(s) — OK")

    # Test 2: 1500 words
    long_text = ". ".join([f"This is sentence number {i} with some filler words here" for i in range(150)]) + "."
    wc = _word_count(long_text)
    r2 = chunk_text(long_text, max_words=500)
    assert len(r2) > 1, f"test2 expected multiple chunks, got {len(r2)}"
    for c in r2:
        assert _word_count(c) <= 500, f"chunk too long: {_word_count(c)} words"
        assert c[-1] in ".!?", f"chunk doesn't end on sentence boundary: {c[-30:]!r}"
    print(f"Test 2 (~{wc} words): {len(r2)} chunks, max={max(_word_count(c) for c in r2)} — OK")

    # Test 3: multi-paragraph — no chunk spans two paragraphs
    para_text = (
        "First paragraph sentence one. First paragraph sentence two.\n\n"
        "Second paragraph sentence one. Second paragraph sentence two.\n\n"
        "Third paragraph here. Another sentence."
    )
    r3 = chunk_text(para_text, max_words=500)
    # Each chunk should belong to exactly one paragraph
    paras = _PARAGRAPH_SPLIT.split(para_text)
    for c in r3:
        matches = sum(1 for p in paras if all(s.strip() in p for s in _split_sentences(c)))
        assert matches >= 1, f"chunk spans paragraphs: {c!r}"
    assert len(r3) == 3, f"expected 3 chunks (one per paragraph), got {len(r3)}"
    print(f"Test 3 (multi-paragraph): {len(r3)} chunks, no paragraph crossing — OK")

    # Test 4: empty string
    r4 = chunk_text("", max_words=500)
    assert r4 == [], f"test4 failed: {r4}"
    r4b = chunk_text("   \n\n  ", max_words=500)
    assert r4b == [], f"test4b failed: {r4b}"
    print("Test 4 (empty): [] — OK")

    # Test 5: single sentence longer than max_words
    huge = " ".join(["word"] * 600) + "."
    r5 = chunk_text(huge, max_words=500)
    assert len(r5) == 1, f"test5 expected 1 chunk, got {len(r5)}"
    assert _word_count(r5[0]) == 600, f"test5 word count: {_word_count(r5[0])}"
    print(f"Test 5 (over-long sentence): 1 chunk of {_word_count(r5[0])} words — OK")

    print("TextChunker: OK")
