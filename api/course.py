"""Course structure and study notes, read straight off disk.

None of this touches the vector index. `data/lessons.json` is the course calendar — the
same file `lesson_index` reads — and `summaries/*.md` are the study notes already
generated for all 32 lesson days. Both are static, so these endpoints are cheap and can
be called on page load without costing an API request.

Kept out of `main.py` because it is a different concern: `main.py` owns the conversation,
this owns the catalogue.
"""

from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS_FILE = ROOT / "data" / "lessons.json"
NOTES_DIR = ROOT / "summaries"
NOTEBOOK_MAP = ROOT / "evaluation" / "notebook_mapping.csv"

# Same constants the agent cites with, repeated rather than imported so this module stays
# free of the agent's import chain (which loads chroma and the embedding client).
LOOM_WATCH = "https://www.loom.com/share"
NOTEBOOK_REPO = "https://github.com/ironhack-ai-eng-june2026/demos_ai_eng/blob/main"


def parse_lesson_id(lesson_id: str) -> tuple[int, int]:
    """`w7d2` -> (7, 2). Mirrors schemas.parse_lesson_id without importing the agent."""
    match = re.fullmatch(r"w(\d+)d(\d+)", lesson_id.strip().lower())
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


@lru_cache(maxsize=1)
def _raw_lessons() -> dict:
    if not LESSONS_FILE.is_file():
        return {}
    return json.loads(LESSONS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _notebooks_by_lesson() -> dict[str, list[str]]:
    """Notebook paths per lesson, MAIN mappings only.

    The CSV also carries EXTRA? and REVIEW rows. Those are the supplementary notebooks
    that live in the course repo without belonging to a taught day — the agent cites them
    with an `Extra ·` prefix, and listing them under a lesson here would assert a link the
    mapping explicitly declined to make.
    """
    if not NOTEBOOK_MAP.is_file():
        return {}
    out: dict[str, list[str]] = {}
    with NOTEBOOK_MAP.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("status") != "MAIN":
                continue
            out.setdefault(row["lesson"], []).append(row["notebook"])
    return {k: sorted(v) for k, v in out.items()}


def lessons() -> list[dict]:
    """The course calendar, flattened for a UI.

    `title` is the first recording's title, which is what the Streamlit lesson picker
    shows — a lesson day has several recordings and the first one names the day.
    `has_notes` lets a frontend grey out days with nothing to show rather than offering
    a link that 404s.
    """
    out = []
    for lesson_id, lesson in sorted(_raw_lessons().items(), key=lambda kv: parse_lesson_id(kv[0])):
        week, day = parse_lesson_id(lesson_id)
        recordings = lesson.get("recordings", [])
        out.append(
            {
                "lesson_id": lesson_id,
                "week": week,
                "day": day,
                "title": recordings[0].get("title", "") if recordings else "",
                "recordings": len(recordings),
                "duration_seconds": sum(int(r.get("duration_seconds", 0)) for r in recordings),
                "has_notes": (NOTES_DIR / f"{lesson_id}.md").is_file(),
                # The actual links. Built here for the same reason build_citation builds
                # them for the agent: one place knows Loom's URL shape and the repo path,
                # and the UI never composes a link of its own.
                "videos": [
                    {
                        "title": r.get("title", ""),
                        "segment": r.get("segment", ""),
                        "duration_seconds": int(r.get("duration_seconds", 0)),
                        "url": f"{LOOM_WATCH}/{r.get('loom_id', '')}",
                    }
                    for r in recordings
                ],
                "notebooks": [
                    {"path": nb, "url": f"{NOTEBOOK_REPO}/{nb}"}
                    for nb in _notebooks_by_lesson().get(lesson_id, [])
                ],
            }
        )
    return out


def weeks() -> list[dict]:
    """Lessons grouped by week, for a sidebar or a scope filter."""
    grouped: dict[int, list[dict]] = {}
    for lesson in lessons():
        grouped.setdefault(lesson["week"], []).append(lesson)
    return [{"week": w, "lessons": grouped[w]} for w in sorted(grouped)]


def notes_markdown(lesson_id: str) -> str | None:
    """The generated study notes for one lesson, or None if they were never built.

    Read-only on purpose. Generating notes is a map-reduce over every chunk in the
    lesson — 21 batches for w7d2 — which is far too slow for a request handler. All 32
    days are already committed under summaries/; regenerate with
    `python -m src.study_notes <lesson_id>`.
    """
    path = NOTES_DIR / f"{lesson_id}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
