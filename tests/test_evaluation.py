"""Guards on the deterministic scoring in evaluation/evaluation.py. No API calls.

    python tests/test_evaluation.py    # or: pytest tests/test_evaluation.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evaluation"))

from evaluation import is_refusal, looks_spanish, score_case  # noqa: E402


def _response(answer: str, *lessons: str, source_type: str = "video") -> dict:
    return {
        "answer": answer,
        "citations": [
            {"lesson_id": lesson, "source_type": source_type, "url": f"https://x/{lesson}", "label": lesson}
            for lesson in lessons
        ],
    }


# --- is_refusal ---------------------------------------------------------------

def test_refusal_detected_in_english_and_spanish():
    assert is_refusal("That wasn't covered in the course.")
    assert is_refusal("Eso no fue cubierto en el curso.")
    assert not is_refusal("RAG combines retrieval and generation.")


def test_refusal_detected_in_other_languages():
    # The prompt asks for the English sentence verbatim; these are the second net.
    assert is_refusal("Isso não foi coberto no curso.")
    assert is_refusal("Cela n'a pas été couvert dans le cours.")
    assert is_refusal("Das wurde nicht behandelt.")


# --- looks_spanish --------------------------------------------------------------

def test_looks_spanish():
    assert looks_spanish("La base de datos vectorial guarda los embeddings para que el modelo los use.")
    assert not looks_spanish("The vector database stores the embeddings for the model.")


# --- score_case -----------------------------------------------------------------

def test_unanswerable_passes_only_when_refused_without_citations():
    case = {"kind": "unanswerable"}
    good = score_case(case, _response("That wasn't covered in the course."), None)
    assert all(good["checks"].values())

    cited = score_case(case, _response("That wasn't covered in the course.", "w4d3"), None)
    assert not cited["checks"]["no_citations"]

    answered = score_case(case, _response("Quantum computing uses qubits.", "w4d3"), None)
    assert not answered["checks"]["refused"]


def test_answerable_needs_an_expected_lesson():
    case = {"kind": "content", "expected_lessons": ["w4d3", "w4d4"]}
    ok = score_case(case, _response("Embeddings map text to vectors.", "w4d3"), None)
    assert ok["checks"]["source_correct"]
    assert ok["checks"]["has_citations"]
    assert ok["checks"]["not_refused"]

    wrong = score_case(case, _response("Embeddings map text to vectors.", "w1d1"), None)
    assert not wrong["checks"]["source_correct"]
    assert any("expected one of" in note for note in wrong["notes"])


def test_must_mention_accepts_any_alternative():
    case = {"kind": "content", "expected_lessons": ["w4d3"], "must_mention": ["gradient|slope"]}
    result = score_case(case, _response("Follow the slope downhill.", "w4d3"), None)
    assert result["checks"]["mentions:gradient|slope"]


def test_expected_source_type():
    case = {"kind": "content", "expected_lessons": ["w4d3"], "expect_source_types": ["notebook"]}
    video_only = score_case(case, _response("See the demo.", "w4d3"), None)
    assert not video_only["checks"]["cites:notebook"]
    with_nb = score_case(case, _response("See the demo.", "w4d3", source_type="notebook"), None)
    assert with_nb["checks"]["cites:notebook"]


def test_followup_that_must_use_memory():
    case = {"kind": "followup", "expected_lessons": ["w4d3"], "followup_must_not_search": True}
    first = _response("Embeddings map text to vectors.", "w4d3")
    used_memory = score_case(case, first, _response("In simpler words: numbers that mean things."), )
    assert used_memory["checks"]["followup_used_memory"]
    re_searched = score_case(case, first, _response("In simpler words...", "w4d3"))
    assert not re_searched["checks"]["followup_used_memory"]


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
    print("evaluation scoring holds" if not failures else "%d failed" % failures)
    sys.exit(1 if failures else 0)
