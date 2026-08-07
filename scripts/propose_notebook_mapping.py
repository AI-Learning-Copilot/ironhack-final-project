from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "src"))

from notebooks import notebook_sections

LESSONS_FILE = ROOT / "data" / "lessons.json"

DEMOS_DIR = Path.home() / "IRONHACK/IA_Eng/demos_ai_eng"

with LESSONS_FILE.open(
    "r",
    encoding="utf-8",
) as f:
    lessons = json.load(f)

print(f"{len(lessons)} lessons loaded")

notebooks = sorted(
    DEMOS_DIR.rglob("*.ipynb")
)

print(f"{len(notebooks)} notebooks found")

print("\nFirst notebook:\n")

sections = notebook_sections(notebooks[0])

print(notebooks[0].relative_to(DEMOS_DIR))
print(f"{len(sections)} sections\n")

for section in sections[:3]:
    print("=" * 80)
    print("Heading:", section["heading"])
    print()
    print(section["text"][:400])
    print()