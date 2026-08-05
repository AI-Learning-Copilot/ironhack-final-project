"""Parse Ironhack course notebooks into chunks ready for Chroma.

Notebook chunks use the same frozen metadata schema as transcript chunks, but the
chunking strategy is different. Markdown headings already define semantic sections,
so a section begins at a heading and includes the following markdown/code cells until
the next heading.

Large sections are split to NOTEBOOK_MAX_CHARS.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from schemas import NOTEBOOK_MAX_CHARS, notebook_chunk


DEMOS_DIR = Path(__file__).resolve().parents[2] / "demos_ai_eng"


# Explicit mapping is intentional. Notebook filenames and lesson days do not have a
# guaranteed one-to-one relationship, so silently guessing lesson IDs is unsafe.
NOTEBOOK_LESSONS: dict[str, str] = {
    "14_LangChain/1_langchain-intro.ipynb": "w7d1",
    "14_LangChain/2_langchain-expression-language.ipynb": "w7d1",
    "14_LangChain/3_langchain-RAG.ipynb": "w7d2",
    "14_LangChain/4_langchain-memory.ipynb": "w7d3",
    "14_LangChain/5_langchain-retrieval-agents.ipynb": "w7d3",
    "14_LangChain/9_langchain-streaming.ipynb": "w7d4",
    "14_LangChain/12_clip-text-image-search.ipynb": "w8d1",
    "14_LangChain/13_multi-modal-rag.ipynb": "w8d1",
}


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