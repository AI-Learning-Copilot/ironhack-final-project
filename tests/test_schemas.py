"""Guards on the two frozen contracts (para-leer/SCHEMA.md).

If one of these fails, someone changed a contract without agreeing it first.

    python -m pytest tests/test_schemas.py        # or just: python tests/test_schemas.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from schemas import (  # noqa: E402
    build_citation,
    build_response,
    format_timestamp,
    loom_time_param,
    notebook_chunk,
    parse_lesson_id,
    video_chunk,
)

SAMPLE_LOOM = "9adc63fbe9f84e93a7334a8c80c20569"


def _video():
    return video_chunk(
        "Indexing splits documents, embeds the chunks and stores the vectors.",
        lesson_id="w7d2",
        lesson_title="RAG II - Indexing",
        loom_id=SAMPLE_LOOM,
        start_seconds=872,
        segment="b",
    )


def _notebook():
    return notebook_chunk(
        "We split with RecursiveCharacterTextSplitter, then embed.",
        lesson_id="w7d2",
        lesson_title="RAG II - Indexing",
        folder="14_LangChain",
        notebook="3_langchain-RAG.ipynb",
        cell_index=12,
        heading="Indexing documents",
    )


def test_timestamps():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(872) == "14:32"
    assert format_timestamp(4532) == "1:15:32"


def test_loom_wants_a_unit_suffix():
    # A bare integer is silently ignored by Loom: the player starts at zero and the
    # citation looks broken with no error anywhere. This is the whole reason the agent
    # builds URLs instead of the UI.
    assert loom_time_param(872) == "872s"
    assert not loom_time_param(872).isdigit()


def test_lesson_id_parsing():
    assert parse_lesson_id("w7d2") == (7, 2)
    assert parse_lesson_id("W10D5") == (10, 5)
    assert parse_lesson_id("nonsense") == (-1, -1)


def test_both_parsers_emit_identical_key_sets():
    # The actual point of the contract: Casilda's and Felipe's chunks must be
    # interchangeable inside one Chroma collection.
    assert _video()["metadata"].keys() == _notebook()["metadata"].keys()


def test_metadata_is_chroma_safe():
    for chunk in (_video(), _notebook()):
        for key, value in chunk["metadata"].items():
            assert isinstance(value, (str, int, float, bool)), f"{key} is {type(value)}"
            assert value is not None


def test_rejects_types_chroma_cannot_store():
    try:
        video_chunk(
            "x",
            lesson_id="w1d1",
            lesson_title="t",
            loom_id="a",
            start_seconds=1,
            segment=["not", "allowed"],
        )
    except TypeError as exc:
        assert "Chroma accepts only" in str(exc)
    else:
        raise AssertionError("a list was accepted into metadata")


def test_citations():
    video = build_citation(_video()["metadata"])
    assert video["url"] == f"https://www.loom.com/embed/{SAMPLE_LOOM}?t=872s"
    assert video["label"] == "w7d2 · RAG II - Indexing · 14:32"

    notebook = build_citation(_notebook()["metadata"])
    assert notebook["url"].startswith("https://github.com/ironhack-ai-eng-june2026/")
    assert notebook["url"].endswith("14_LangChain/3_langchain-RAG.ipynb")
    assert notebook["start_seconds"] == -1


def test_response_deduplicates():
    metas = [_video()["metadata"], _notebook()["metadata"], _video()["metadata"]]
    assert len(build_response("answer", metas)["citations"]) == 2


def test_fixture_matches_the_contract():
    # Felipe's UI is built against this file, so it must stay in sync with the code.
    path = Path(__file__).resolve().parents[1] / "tests/fixtures/mock_response.json"
    payload = json.loads(path.read_text())
    assert set(payload) == {"answer", "citations"}
    assert {c["source_type"] for c in payload["citations"]} == {"video", "notebook"}
    for citation in payload["citations"]:
        assert set(citation) == {
            "source_type",
            "lesson_id",
            "label",
            "url",
            "start_seconds",
        }


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {name}: {exc}")
    print("all schema contracts hold" if not failures else f"{failures} failed")
    sys.exit(1 if failures else 0)
