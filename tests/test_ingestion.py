"""Guards on transcript loading.

    python tests/test_ingestion.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion import (  # noqa: E402
    clean_text,
    load_all,
    parse_title,
    timestamp_to_seconds,
)


def test_speaker_tags_are_stripped():
    assert clean_text("<v 0>Templates, so that's not this one.</v>") == (
        "Templates, so that's not this one."
    )


def test_jargon_is_corrected():
    # The one that matters: "RAC" outnumbered "RAG" 61 to 17 in the raw captions, so
    # without this a student asking about RAG misses most of the material.
    assert clean_text("the core idea of a RAC is") == "the core idea of a RAG is"
    assert clean_text("we use lang chain for this") == "we use LangChain for this"
    assert clean_text("store it in karma") == "store it in Chroma"


def test_jargon_fix_respects_word_boundaries():
    # "rack", "racing" and friends must survive untouched
    for word in ("rack", "racing", "characteristic"):
        assert word in clean_text("the " + word + " here").lower()


def test_whitespace_is_collapsed():
    assert clean_text("two\n  lines   here") == "two lines here"


def test_timestamps():
    assert timestamp_to_seconds("00:00:03.570") == 3
    assert timestamp_to_seconds("00:14:32.570") == 872
    assert timestamp_to_seconds("01:15:32.000") == 4532


def test_title_parsing_keeps_dashes_in_the_topic():
    # The topic itself contains " - ", which is why a fixed-field split would be wrong.
    title, segment = parse_title("AI 2026.06 - w7d2 - b - RAG II - Indexing")
    assert title == "RAG II - Indexing"
    assert segment == "b"


def test_title_parsing_survives_an_unexpected_format():
    title, segment = parse_title("something odd")
    assert title == "something odd"
    assert segment == ""


def test_corpus_loads():
    recordings = load_all()
    assert len(recordings) == 120, "expected 120 recordings, got %d" % len(recordings)
    assert all(r.cues for r in recordings), "a recording has no cues"
    assert all(r.lesson_id.startswith("w") for r in recordings)
    assert all(len(r.loom_id) == 32 for r in recordings)


def test_dev_index_subset():
    # Task C1c: the subset is what lets agent work start before the full index exists.
    subset = load_all(limit_lessons=5)
    assert {r.lesson_id for r in subset} == {"w1d1", "w1d2", "w1d3", "w1d4", "w1d5"}
    assert len(subset) < len(load_all())


def test_no_speaker_tags_survive():
    for recording in load_all(limit_lessons=3):
        for cue in recording.cues:
            assert "<v" not in cue.text


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
    print("ingestion holds" if not failures else "%d failed" % failures)
    sys.exit(1 if failures else 0)
