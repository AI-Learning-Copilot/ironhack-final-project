from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from notebook_utils import normalize_notebook_path

DEMOS = Path.home() / "IRONHACK/IA_Eng/demos_ai_eng"

CSV = ROOT / "evaluation" / "course_resources.csv"


# ----------------------------------------------------
# Official notebooks from Slack
# ----------------------------------------------------

official = set()

with CSV.open(
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        if row["type"] != "notebook":
            continue

        official.add(
            normalize_notebook_path(
                row["resource"]
            )
        )


# ----------------------------------------------------
# Repository notebooks
# ----------------------------------------------------

repository = set()

for notebook in DEMOS.rglob("*.ipynb"):

    repository.add(
        normalize_notebook_path(
            notebook.relative_to(
                DEMOS
            ).as_posix()
        )
    )


matched = sorted(
    official & repository
)

extras = sorted(
    repository - official
)

missing = sorted(
    official - repository
)


print()
print("=" * 70)
print("NOTEBOOK RECONCILIATION")
print("=" * 70)
print()

print(f"Repository notebooks : {len(repository)}")
print(f"Official notebooks   : {len(official)}")
print(f"Matched notebooks    : {len(matched)}")
print(f"Extras               : {len(extras)}")
print(f"Missing              : {len(missing)}")

print()

if missing:

    print("=" * 70)
    print("Missing from repository")
    print("=" * 70)

    for notebook in missing:
        print(notebook)

if extras:

    print()
    print("=" * 70)
    print("Extra notebooks")
    print("=" * 70)

    for notebook in extras:
        print(notebook)