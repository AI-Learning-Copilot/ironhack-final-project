from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from notebook_utils import normalize_notebook_path

SLACK_FILE = ROOT / "para-leer" / "slack_export.md"
OUTPUT_FILE = ROOT / "evaluation" / "course_resources.csv"

LESSON_RE = re.compile(r"^w\d+d\d+$", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")

GITHUB_RE = re.compile(r"github\.com", re.IGNORECASE)
GOOGLE_RE = re.compile(r"docs\.google\.com", re.IGNORECASE)
LOOM_RE = re.compile(r"loom\.com", re.IGNORECASE)

rows = []

current_lesson = None
current_section = None


def add_resource(resource_type, title, resource, url):
    rows.append(
        {
            "lesson": current_lesson,
            "section": current_section,
            "type": resource_type,
            "title": title,
            "resource": resource,
            "url": url,
        }
    )


with SLACK_FILE.open(encoding="utf-8") as f:

    for raw_line in f:

        line = raw_line.strip()

        if not line:
            continue

        # -------------------------------------------------
        # Lesson
        # -------------------------------------------------

        lesson = line.replace(":", "").strip()

        if LESSON_RE.fullmatch(lesson):
            current_lesson = lesson.lower()
            current_section = None
            continue

        # -------------------------------------------------
        # Section header
        # -------------------------------------------------

        if line.endswith(":"):
            current_section = line[:-1].strip().lower()
            continue

        # -------------------------------------------------
        # Notebook
        # -------------------------------------------------

        if line.endswith(".ipynb"):

            notebook = normalize_notebook_path(line)

            add_resource(
                resource_type="notebook",
                title=Path(notebook).name,
                resource=notebook,
                url="",
            )

            continue

        # -------------------------------------------------
        # Markdown
        # -------------------------------------------------

        if line.endswith(".md"):

            md = line.strip()

            add_resource(
                resource_type="markdown",
                title=Path(md).name,
                resource=md,
                url="",
            )

            continue

        # -------------------------------------------------
        # URLs
        # -------------------------------------------------

        urls = URL_RE.findall(line)

        if not urls:
            continue

        for url in urls:

            if GITHUB_RE.search(url):
                resource_type = "github"

            elif GOOGLE_RE.search(url):
                resource_type = "slides"

            elif LOOM_RE.search(url):
                resource_type = "recording"

            else:
                resource_type = "link"

            title = line.replace(url, "").strip("- ").strip()

            add_resource(
                resource_type=resource_type,
                title=title,
                resource="",
                url=url,
            )

OUTPUT_FILE.parent.mkdir(exist_ok=True)

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "lesson",
            "section",
            "type",
            "title",
            "resource",
            "url",
        ],
    )

    writer.writeheader()
    writer.writerows(rows)

print()
print(f"Extracted {len(rows)} resources.\n")

types = {}

for row in rows:
    types[row["type"]] = types.get(row["type"], 0) + 1

print("Resource types\n")

for key, value in sorted(types.items()):
    print(f"{key:<12} {value}")

print()
print(f"CSV written to:\n{OUTPUT_FILE}")