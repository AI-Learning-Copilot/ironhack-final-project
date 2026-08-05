"""Guards on chunking.

The invariant that matters most: a chunk's timestamp is the start of its FIRST cue, and
we never split inside a cue. A cue is the smallest unit with a real timestamp, so
splitting one would mean guessing where in those seconds the text fell — and the whole
product is "take me to the exact moment".

    python tests/test_chunking.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chunking import chunk_all, chunk_cues, chunk_recording  # noqa: E402
from ingestion import Cue, load_all  # noqa: E402
from schemas import VIDEO_CHUNK_SIZE, build_citation  # noqa: E402


def _cues(count, text="word " * 20, step=10):
    return [Cue(i * step, text.strip()) for i in range(count)]


def test_timestamp_is_the_first_cue_of_the_chunk():
    chunks = chunk_cues(_cues(40))
    assert chunks[0][0] == 0
    # every chunk's start must be one of the real cue timestamps, never interpolated
    valid = {c.start_seconds for c in _cues(40)}
    assert all(start in valid for start, _ in chunks)


def test_chunks_respect_the_size_target():
    chunks = chunk_cues(_cues(60))
    assert all(len(text) <= VIDEO_CHUNK_SIZE for _, text in chunks[:-1])


def test_a_single_oversized_cue_is_not_split():
    # Better one long chunk with an honest timestamp than two with a guessed one.
    monster = "x" * (VIDEO_CHUNK_SIZE * 2)
    chunks = chunk_cues([Cue(5, monster)])
    assert len(chunks) == 1
    assert chunks[0] == (5, monster)


def test_chunks_overlap():
    chunks = chunk_cues(_cues(40))
    assert len(chunks) > 1
    # the tail of one chunk should reappear at the head of the next
    first_words = chunks[1][1].split()[:5]
    assert " ".join(first_words) in chunks[0][1]


def test_timestamps_increase():
    chunks = chunk_cues(_cues(60))
    starts = [start for start, _ in chunks]
    assert starts == sorted(starts)


def test_empty_input():
    assert chunk_cues([]) == []


def test_real_recording_produces_valid_schema_chunks():
    recording = load_all(limit_lessons=1)[0]
    chunks = chunk_recording(recording)
    assert chunks
    for chunk in chunks:
        meta = chunk["metadata"]
        assert meta["source_type"] == "video"
        assert meta["loom_id"] == recording.loom_id
        assert meta["start_seconds"] >= 0
        assert meta["lesson_id"] == recording.lesson_id
        # Chroma safety
        for value in meta.values():
            assert isinstance(value, (str, int, float, bool))


def test_citations_from_real_chunks_carry_the_loom_suffix():
    chunks = chunk_recording(load_all(limit_lessons=1)[0])
    for chunk in chunks[:20]:
        url = build_citation(chunk["metadata"])["url"]
        assert "?t=" in url and url.endswith("s"), url


def test_whole_corpus_chunks_cleanly():
    chunks = chunk_all(load_all())
    assert 4000 < len(chunks) < 8000, "unexpected chunk count: %d" % len(chunks)
    assert all(chunk["text"].strip() for chunk in chunks), "an empty chunk was emitted"
    assert not any("<v" in chunk["text"] for chunk in chunks)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("  ok   " + name)
            except AssertionError as exc:
                failures += 1
                print("  FAIL " + name + ": " + str(exc))
    print("chunking holds" if not failures else "%d failed" % failures)
    sys.exit(1 if failures else 0)
