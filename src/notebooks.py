"""Parse Ironhack course notebooks into chunks ready for Chroma.

Notebook chunks use the same frozen metadata schema as transcript chunks, but the
chunking strategy is different. Markdown headings already define semantic sections,
so a section begins at a heading and includes the following markdown/code cells until
the next heading.

Large sections are split to NOTEBOOK_MAX_CHARS.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from notebook_utils import normalize_notebook_path

from schemas import EXTRA_LESSON_ID, NOTEBOOK_MAX_CHARS, notebook_chunk


def _find_demos_dir() -> Path:
    """Locate the demos_ai_eng clone.

    We keep it in different places: Felipe has it beside the repo, Casilda has it inside
    her course folder. Hard-coding either one means the parser only runs on one machine,
    which we would not notice until the other person tried to build the index.

    Set DEMOS_AI_ENG_DIR in .env to override.
    """
    import os

    override = os.getenv("DEMOS_AI_ENG_DIR")
    candidates = [Path(override)] if override else []
    candidates += [
        Path(__file__).resolve().parents[2] / "demos_ai_eng",
        Path.home() / "Desktop/AI_Engineering/Lectures/demos_ai_eng",
        Path.home() / "demos_ai_eng",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Return the first candidate so the error names a concrete path rather than failing
    # somewhere deeper with a confusing message.
    return candidates[0]


DEMOS_DIR = _find_demos_dir()


# Explicit mapping is intentional. Notebook filenames and lesson days do not have a
# guaranteed one-to-one relationship, so silently guessing lesson IDs is unsafe.


COURSE_RESOURCES = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "course_resources.csv"
)


def load_notebook_lessons() -> dict[str, str]:
    """
    Load the official notebook → lesson mapping generated from the Slack export.

    Only notebooks classified as official resources are included.
    """

    mapping: dict[str, str] = {}

    if not COURSE_RESOURCES.exists():
        raise FileNotFoundError(
            f"{COURSE_RESOURCES} not found. "
            "Run scripts/parse_slack_resources.py first."
        )

    with COURSE_RESOURCES.open(
        newline="",
        encoding="utf-8",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            # Only official notebooks
            if row["type"] != "notebook":
                continue

            # Ignore malformed rows
            if not row["lesson"]:
                continue

            mapping[
                normalize_notebook_path(row["resource"])
            ] = row["lesson"]


        print(f"Loaded {len(mapping)} notebook mappings.")

        return mapping


NOTEBOOK_LESSONS = load_notebook_lessons()


_HEADING = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_HTML = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t]+")


def _cell_source(cell: dict) -> str:
    """Return a notebook cell's source as one string."""
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def extract_heading(text: str) -> str:
    """Return the first markdown heading in a cell, or an empty string.

    Ironhack notebooks sometimes put HTML such as <br> before the markdown heading,
    so HTML tags are removed before looking for '#', '##', etc.
    """
    cleaned = _HTML.sub("", text)
    match = _HEADING.search(cleaned)
    return match.group(2).strip() if match else ""


def clean_cell_text(text: str) -> str:
    """Normalize notebook text while preserving useful code/newline structure."""
    text = text.strip()
    lines = [_WHITESPACE.sub(" ", line.rstrip()) for line in text.splitlines()]
    return "\n".join(lines).strip()


def load_notebook(path: Path) -> dict:
    """Read one .ipynb file as JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def notebook_sections(path: Path) -> list[dict]:
    """Group notebook cells into semantic sections.

    A markdown cell containing a heading starts a new section. All following cells,
    including code, belong to that section until the next heading.

    Returns dictionaries containing:
        text
        cell_index
        heading
    """
    notebook = load_notebook(path)
    cells = notebook.get("cells", [])

    sections: list[dict] = []
    current: dict | None = None

    for index, cell in enumerate(cells):
        source = clean_cell_text(_cell_source(cell))
        if not source:
            continue

        heading = extract_heading(source) if cell.get("cell_type") == "markdown" else ""

        if heading:
            if current is not None and current["parts"]:
                current["text"] = "\n\n".join(current.pop("parts"))
                sections.append(current)

            current = {
                "cell_index": index,
                "heading": heading,
                "parts": [source],
            }
            continue

        # Content before the notebook's first heading is still retained.
        if current is None:
            current = {
                "cell_index": index,
                "heading": "",
                "parts": [],
            }

        current["parts"].append(source)

    if current is not None and current["parts"]:
        current["text"] = "\n\n".join(current.pop("parts"))
        sections.append(current)

    return sections


def split_section(text: str, max_chars: int = NOTEBOOK_MAX_CHARS) -> list[str]:
    """Split an oversized semantic section without dropping content.

    Paragraph boundaries are preferred. A single paragraph longer than max_chars is
    hard-split as a last resort.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""

            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start:start + max_chars])
            continue

        candidate = paragraph if not current else current + "\n\n" + paragraph

        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def chunk_notebook(
    path: Path,
    *,
    lesson_id: str,
    lesson_title: str,
    demos_dir: Path = DEMOS_DIR,
) -> list[dict]:
    """Convert one notebook into frozen-schema chunks."""
    relative = path.relative_to(demos_dir)

    folder = relative.parent.as_posix()
    notebook_name = relative.name

    chunks: list[dict] = []

    for section in notebook_sections(path):
        for text in split_section(section["text"]):

            # Context header improves retrieval quality.
            header = f"[{folder}/{notebook_name} · {section['heading']}]"
            chunk_text = f"{header}\n{text}"

            chunks.append(
                notebook_chunk(
                    chunk_text,
                    lesson_id=lesson_id,
                    lesson_title=lesson_title,
                    folder=folder,
                    notebook=notebook_name,
                    cell_index=section["cell_index"],
                    heading=section["heading"],
                )
            )

    return chunks

def chunk_all_notebooks(demos_dir: Path = DEMOS_DIR) -> list[dict]:
    """Every notebook in NOTEBOOK_LESSONS, as chunks.

    Lesson titles come from data/lessons.json so a notebook citation reads the same as
    a video one. Notebooks that are mapped but missing from the clone are skipped with a
    warning rather than raising — a partial index beats no index during the week.

    Coverage is currently weeks 7-8 only, because NOTEBOOK_LESSONS is a hand-checked
    mapping and guessing the rest from folder names would produce confidently wrong
    citations. Extending it means reading the "Files:" list in each #3--resources post.
    """
    import json

    lessons_path = Path(__file__).resolve().parents[1] / "data" / "lessons.json"
    lessons = json.loads(lessons_path.read_text()) if lessons_path.exists() else {}

    chunks: list[dict] = []
    for relative, lesson_id in NOTEBOOK_LESSONS.items():
        path = demos_dir / relative
        if not path.exists():
            print(f"  skipping missing notebook: {relative}")
            continue
        title = lessons.get(lesson_id, {}).get("title", lesson_id)
        chunks.extend(
            chunk_notebook(
                path, lesson_id=lesson_id, lesson_title=title, demos_dir=demos_dir
            )
        )

    chunks.extend(chunk_extra_notebooks(demos_dir, mapped=set(NOTEBOOK_LESSONS)))
    return chunks


def chunk_extra_notebooks(demos_dir: Path, mapped: set[str]) -> list[dict]:
    """Notebooks in the course repo that no lesson claims.

    The Slack resource posts attach 40 notebooks to lessons; the repo holds 64. The
    other 24 are supplementary — Python basics, NumPy, pandas, data viz, transfer
    learning, LangSmith deep dives, extra RAG evaluation. They are real course material
    and a student should be able to find them, so they are indexed.

    They are tagged EXTRA_LESSON_ID rather than given a lesson inherited from their
    folder. Folder inheritance looked tempting and is wrong: 01_python is mapped to
    w4d1 (regex), so eight Python-basics notebooks would have been cited as
    "week 4 day 1". A citation that is confidently wrong is worse than one that says
    plainly it is supplementary.
    """
    extras = sorted(
        str(path.relative_to(demos_dir))
        for path in demos_dir.rglob("*.ipynb")
        if ".ipynb_checkpoints" not in str(path)
        and str(path.relative_to(demos_dir)) not in mapped
    )

    chunks: list[dict] = []
    for relative in extras:
        chunks.extend(
            chunk_notebook(
                demos_dir / relative,
                lesson_id=EXTRA_LESSON_ID,
                lesson_title="Supplementary course notebook",
                demos_dir=demos_dir,
            )
        )

    print(f"{len(extras)} supplementary notebooks -> {len(chunks):,} chunks")
    return chunks
