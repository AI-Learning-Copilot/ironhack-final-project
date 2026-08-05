"""C6 — evaluate the copilot against a hand-built ground-truth set.

    python evaluation/evaluation.py              # run and print a report
    python evaluation/evaluation.py --upload     # also push the dataset to LangSmith
    python evaluation/evaluation.py --case f03   # one case, for debugging

Every metric here is deterministic. An LLM judging its own answers would grade this
system on fluency, which it is already good at, and tell us nothing about whether the
citation points at the right lesson — which is the only thing the product actually
promises. Traces still go to LangSmith automatically, so the reasoning behind any failure
is one click away.

The headline metric is SOURCE ACCURACY: did the answer cite a lesson that genuinely
covers the topic? The ground truth for that comes from real lesson titles in
data/lessons.json, not from what the system happens to return.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent import Copilot  # noqa: E402

CASES_PATH = Path(__file__).parent / "test_questions.json"
DATASET_NAME = "ai-learning-copilot-eval"

REFUSAL_MARKERS = (
    "wasn't covered", "was not covered", "not covered", "does not cover",
    "no está", "no fue cubierto", "not appear", "don't have information",
    "no information",
)

# Enough to tell Spanish from English without a language-detection dependency.
SPANISH_MARKERS = (" el ", " la ", " los ", " las ", " que ", " para ", " es ", " un ",
                   " una ", " se ", " del ", " con ", "ó", "é", "í", "á", "ñ")


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text())["cases"]


def looks_spanish(text: str) -> bool:
    lowered = f" {text.lower()} "
    return sum(marker in lowered for marker in SPANISH_MARKERS) >= 4


def is_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def score_case(case: dict, response: dict, followup: dict | None) -> dict:
    """Deterministic scoring. Returns {check_name: bool} plus a note on failure."""
    answer = response["answer"]
    cited = [c["lesson_id"] for c in response["citations"]]
    checks: dict[str, bool] = {}
    notes: list[str] = []

    if case["kind"] == "unanswerable":
        checks["refused"] = is_refusal(answer)
        checks["no_citations"] = len(response["citations"]) == 0
        if not checks["refused"]:
            notes.append(f"did not refuse: {answer[:70]!r}")
        if not checks["no_citations"]:
            notes.append(f"cited {cited} on an unanswerable question")
        return {"checks": checks, "notes": notes}

    expected = case["expected_lessons"]
    checks["source_correct"] = any(lesson in expected for lesson in cited)
    if not checks["source_correct"]:
        notes.append(f"cited {cited or '[]'}, expected one of {expected}")

    checks["has_citations"] = len(response["citations"]) > 0
    checks["not_refused"] = not is_refusal(answer)
    if not checks["not_refused"]:
        notes.append("refused a question that is answerable")

    for term in case.get("must_mention", []):
        # "a|b|c" means any of them counts. A single required word is a brittle check:
        # an answer can explain backpropagation perfectly while saying "slope" rather
        # than "gradient", and failing that is measuring vocabulary, not correctness.
        alternatives = [t.strip().lower() for t in term.split("|")]
        key = f"mentions:{term}"
        checks[key] = any(alt in answer.lower() for alt in alternatives)
        if not checks[key]:
            notes.append(f"answer mentions none of {alternatives}")

    if case.get("must_be_language") == "spanish":
        checks["answered_in_spanish"] = looks_spanish(answer)
        if not checks["answered_in_spanish"]:
            notes.append("answered in English to a Spanish question")

    if followup is not None:
        if case.get("followup_must_not_search"):
            # "Explain that more simply" should re-word what is already in memory,
            # not trigger a fresh retrieval. Citations are the tell.
            checks["followup_used_memory"] = len(followup["citations"]) == 0
            if not checks["followup_used_memory"]:
                notes.append("re-searched instead of using memory")
        else:
            checks["followup_answered"] = len(followup["answer"].strip()) > 20

    return {"checks": checks, "notes": notes}


def run(cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        copilot = Copilot()  # fresh memory per case, except within a followup pair
        started = time.time()
        response = copilot.ask(case["question"])
        latency = time.time() - started

        followup = None
        if case.get("followup"):
            f_started = time.time()
            followup = copilot.ask(case["followup"])
            latency += time.time() - f_started

        scored = score_case(case, response, followup)
        passed = all(scored["checks"].values())
        results.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "question": case["question"],
                "answer": response["answer"],
                "cited": [c["lesson_id"] for c in response["citations"]],
                "latency": latency,
                "passed": passed,
                **scored,
            }
        )
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark}  {case['id']}  {latency:5.1f}s  {case['question'][:52]}")
        for note in scored["notes"]:
            print(f"          - {note}")
    return results


def report(results: list[dict]) -> None:
    total = len(results)
    passed = sum(r["passed"] for r in results)
    latencies = sorted(r["latency"] for r in results)

    def pct(p: float) -> float:
        return latencies[min(int(len(latencies) * p), len(latencies) - 1)]

    print("\n" + "=" * 62)
    print(f"  OVERALL              {passed}/{total} cases pass ({passed / total:.0%})")

    answerable = [r for r in results if r["kind"] != "unanswerable"]
    source_ok = sum(r["checks"].get("source_correct", False) for r in answerable)
    print(f"  SOURCE ACCURACY      {source_ok}/{len(answerable)} "
          f"({source_ok / len(answerable):.0%})  <- the headline number")

    refusals = [r for r in results if r["kind"] == "unanswerable"]
    refused_ok = sum(r["passed"] for r in refusals)
    print(f"  REFUSAL ACCURACY     {refused_ok}/{len(refusals)}")

    for kind in ("content", "location", "spanish", "followup"):
        group = [r for r in results if r["kind"] == kind]
        if group:
            print(f"    {kind:<18} {sum(r['passed'] for r in group)}/{len(group)}")

    print(f"  LATENCY              median {statistics.median(latencies):.1f}s · "
          f"p95 {pct(0.95):.1f}s · max {max(latencies):.1f}s")
    print("=" * 62)

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("\nFailures to look at:")
        for r in failures:
            print(f"  {r['id']}  {r['question'][:56]}")
            for note in r["notes"]:
                print(f"        {note}")


def upload_dataset(cases: list[dict]) -> None:
    """Push the ground truth to LangSmith so runs are comparable over time."""
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        print(f"dataset {DATASET_NAME!r} already exists — leaving it alone")
        return
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Hand-built ground truth for the Ironhack AI Learning Copilot (C6).",
    )
    client.create_examples(
        inputs=[{"question": c["question"]} for c in cases],
        outputs=[
            {"expected_lessons": c["expected_lessons"], "kind": c["kind"]} for c in cases
        ],
        dataset_id=dataset.id,
    )
    print(f"uploaded {len(cases)} examples to LangSmith dataset {DATASET_NAME!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="push dataset to LangSmith")
    parser.add_argument("--case", help="run a single case id")
    parser.add_argument("--save", action="store_true", help="write evaluation/results.json")
    args = parser.parse_args()

    cases = load_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            sys.exit(f"no case with id {args.case!r}")

    if args.upload:
        upload_dataset(load_cases())

    print(f"running {len(cases)} cases\n")
    results = run(cases)
    report(results)

    if args.save:
        out = Path(__file__).parent / "results.json"
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nwrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
