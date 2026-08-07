from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retrieval import search_with_scores


QUESTIONS = ROOT / "evaluation" / "golden_questions.csv"
OUTPUT = ROOT / "evaluation" / "results.json"
REPORT = ROOT / "evaluation" / "retrieval_report.md"


@dataclass
class EvaluationResult:
    question: str
    expected_lesson: str

    retrieved_lessons: list[str]
    retrieved_sources: list[str]
    retrieved_headings: list[str]
    retrieved_distances: list[float]

    top1_correct: bool
    top3_correct: bool
    top5_correct: bool


def load_questions() -> list[dict]:
    """Load evaluation questions."""

    with QUESTIONS.open(
        newline="",
        encoding="utf-8",
    ) as f:
        return list(csv.DictReader(f))


def evaluate_question(
    row: dict,
) -> EvaluationResult:
    """Evaluate retrieval for one question."""

    question = row["question"]
    expected = row["expected_lesson"]

    results = search_with_scores(
        question,
        k=5,
    )

    lessons = [
        doc.metadata["lesson_id"]
        for doc, _ in results
    ]


    sources = []

    for doc, _ in results:

        metadata = doc.metadata

        if metadata.get("source_type") == "notebook":

            source = metadata.get(
                "notebook",
                "Unknown Notebook",
            )

        else:

            source = (
                metadata.get("lesson_title")
                or metadata.get("segment")
                or metadata.get("loom_id")
                or "Unknown Video"
            )

        sources.append(source)



    headings = [
        doc.metadata.get("heading", "")
        for doc, _ in results
    ]

    distances = [
        score
        for _, score in results
    ]

    return EvaluationResult(
        question=question,
        expected_lesson=expected,

        retrieved_lessons=lessons,
        retrieved_sources=sources,
        retrieved_headings=headings,
        retrieved_distances=distances,

        top1_correct=(
            lessons[0] == expected
        ),

        top3_correct=(
            expected in lessons[:3]
        ),

        top5_correct=(
            expected in lessons
        ),
    )


def summarize(
    results: list[EvaluationResult],
) -> None:
    """Print evaluation summary."""

    total = len(results)

    top1 = sum(
        r.top1_correct
        for r in results
    )

    top3 = sum(
        r.top3_correct
        for r in results
    )

    top5 = sum(
        r.top5_correct
        for r in results
    )

    avg_distance = (
        sum(
            r.retrieved_distances[0]
            for r in results
        )
        / total
    )

    print()
    print("=" * 60)
    print("Retrieval Evaluation")
    print("=" * 60)
    print()

    print(f"Questions tested : {total}")
    print()

    print(f"Top-1 Accuracy : {top1 / total:.1%}")
    print(f"Top-3 Accuracy : {top3 / total:.1%}")
    print(f"Top-5 Accuracy : {top5 / total:.1%}")
    print()

    print(f"Average distance : {avg_distance:.3f}")
    print()

    print(f"Failures : {total - top1}")
def print_failures(
    results: list[EvaluationResult],
) -> None:
    """Print every failed Top-1 retrieval with detailed information."""

    failures = [
        r
        for r in results
        if not r.top1_correct
    ]

    if not failures:
        return

    print()
    print("=" * 60)
    print("FAILED QUESTIONS")
    print("=" * 60)

    for result in failures:

        print()
        print(f"Question : {result.question}")
        print(f"Expected : {result.expected_lesson}")
        print()

        for i in range(len(result.retrieved_lessons)):

            print(f"Rank #{i + 1}")

            print(
                f"Lesson   : {result.retrieved_lessons[i]}"
            )

            print(
                f"Source   : {result.retrieved_sources[i]}"
            )

            heading = result.retrieved_headings[i]

            if heading:
                print(
                    f"Heading  : {heading}"
                )

            print(
                f"Distance : {result.retrieved_distances[i]:.3f}"
            )

            print("-" * 40)


def analyze_failures(
    results: list[EvaluationResult],
) -> None:
    """Count failures by lesson."""

    counter = Counter()

    for result in results:

        if not result.top1_correct:
            counter[result.expected_lesson] += 1

    if not counter:
        return

    print()
    print("=" * 60)
    print("FAILURES BY LESSON")
    print("=" * 60)

    for lesson, count in counter.most_common():
        print(f"{lesson:<8} {count}")


def save_results(
    results: list[EvaluationResult],
) -> None:
    """Save detailed evaluation results as JSON."""

    OUTPUT.write_text(
        json.dumps(
            [
                asdict(result)
                for result in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Results written to:\n{OUTPUT}")


def write_report(
    results: list[EvaluationResult],
) -> None:
    """Generate a Markdown evaluation report."""

    total = len(results)

    top1 = sum(
        r.top1_correct
        for r in results
    )

    top3 = sum(
        r.top3_correct
        for r in results
    )

    top5 = sum(
        r.top5_correct
        for r in results
    )

    lines = [
        "# Retrieval Evaluation",
        "",
        f"- Questions tested: **{total}**",
        f"- Top-1 Accuracy: **{top1/total:.1%}**",
        f"- Top-3 Accuracy: **{top3/total:.1%}**",
        f"- Top-5 Accuracy: **{top5/total:.1%}**",
        "",
        "## Failed Questions",
        "",
    ]

    for result in results:

        if result.top1_correct:
            continue

        lines.extend([
            f"### {result.question}",
            "",
            f"**Expected lesson:** `{result.expected_lesson}`",
            "",
            "| Rank | Lesson | Source | Distance |",
            "|------|--------|--------|---------:|",
        ])

        for i in range(len(result.retrieved_lessons)):

            lines.append(
                f"| {i+1} | "
                f"{result.retrieved_lessons[i]} | "
                f"{result.retrieved_sources[i]} | "
                f"{result.retrieved_distances[i]:.3f} |"
            )

        lines.append("")

    lines.extend([
        "---",
        "",
        "_Automatically generated by `scripts/evaluate_retrieval.py`._",
    ])

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print(f"Markdown report written to:\n{REPORT}")


def main() -> None:

    rows = load_questions()

    results = [
        evaluate_question(row)
        for row in rows
    ]

    summarize(results)

    print_failures(results)

    analyze_failures(results)

    save_results(results)

    write_report(results)


if __name__ == "__main__":
    main()