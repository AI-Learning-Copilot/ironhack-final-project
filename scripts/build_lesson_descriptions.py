from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

lessons = json.loads(
    (ROOT / "data" / "lessons.json").read_text()
)

print()

for lesson_id, lesson in lessons.items():
    print(lesson_id)
    print(lesson["title"])
    print("-" * 80)