from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from notebooks import notebook_sections
from retrieval import search_with_scores

DEMOS_DIR = Path.home() / "IRONHACK/IA_Eng/demos_ai_eng"
OUTPUT = ROOT / "evaluation" / "notebook_mapping.csv"


def classify_notebook(path: Path, k: int = 10):
    """Classify one notebook against lecture transcripts."""

    sections = notebook_sections(path)

    if not sections:
        return None

    # Use the first few semantic sections as the notebook representation.
    query = "\n\n".join(
        section["text"]
        for section in sections[:3]
    )

    # IMPORTANT:
    # Only classify against transcript chunks.
    results = search_with_scores(
        query,
        k=k,
        source_type="video",
    )

    raw_votes = Counter()
    weighted_votes = {}
    lesson_scores = {}

    for doc, score in results:

        lesson = doc.metadata["lesson_id"]

        raw_votes[lesson] += 1

        # Smaller distance = stronger vote.
        weight = 1 / (score + 1e-6)

        weighted_votes[lesson] = (
            weighted_votes.get(lesson, 0)
            + weight
        )

        lesson_scores.setdefault(
            lesson,
            [],
        ).append(score)

    winner = max(
        weighted_votes,
        key=weighted_votes.get,
    )

    winner_votes = raw_votes[winner]

    # Percentage of neighbours agreeing.
    confidence = winner_votes / len(results)

    # Strength of semantic evidence.
    weighted_confidence = (
        weighted_votes[winner]
        / sum(weighted_votes.values())
    )

    avg_distance = (
        sum(lesson_scores[winner])
        / len(lesson_scores[winner])
    )

    return {
        "lesson": winner,
        "confidence": confidence,
        "weighted_confidence": weighted_confidence,
        "votes": winner_votes,
        "weighted_votes": weighted_votes[winner],
        "avg_distance": avg_distance,
    }


def main():

    notebooks = sorted(
        DEMOS_DIR.rglob("*.ipynb")
    )

    rows = []

    high = 0
    medium = 0
    low = 0

    print()
    print(f"Found {len(notebooks)} notebooks\n")

    for notebook in notebooks:

        result = classify_notebook(notebook)

        if result is None:
            continue

        # Keep the human-readable confidence for thresholds.
        if result["confidence"] >= 0.90:
            status = "MAIN"
            high += 1
        elif result["confidence"] >= 0.70:
            status = "REVIEW"
            medium += 1
        else:
            status = "EXTRA?"
            low += 1

        rows.append(
            {
                "notebook": notebook.relative_to(
                    DEMOS_DIR
                ).as_posix(),
                "lesson": result["lesson"],
                "confidence": round(
                    result["confidence"],
                    3,
                ),
                "weighted_confidence": round(
                    result["weighted_confidence"],
                    3,
                ),
                "votes": result["votes"],
                "weighted_votes": round(
                    result["weighted_votes"],
                    3,
                ),
                "avg_distance": round(
                    result["avg_distance"],
                    3,
                ),
                "status": status,
            }
        )

        print(
            f"{rows[-1]['notebook']:<65}"
            f"{result['lesson']:>6}   "
            f"{result['confidence']:.0%}"
        )

    rows.sort(
        key=lambda row: (
            -row["confidence"],
            -row["weighted_confidence"],
            row["avg_distance"],
        )
    )

    OUTPUT.parent.mkdir(
        exist_ok=True
    )

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "notebook",
                "lesson",
                "confidence",
                "weighted_confidence",
                "votes",
                "weighted_votes",
                "avg_distance",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"Total notebooks : {len(rows)}")
    print(f"MAIN            : {high}")
    print(f"REVIEW          : {medium}")
    print(f"EXTRA?          : {low}")

    print()
    print(f"CSV written to:\n{OUTPUT}")


if __name__ == "__main__":
    main()