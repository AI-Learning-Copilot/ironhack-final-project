"""Generate study notes from the indexed Ironhack course material.

F2 — Study Notes

The notes are generated lesson by lesson from the same Chroma index used by
the Copilot. Each lesson can contain both video transcript chunks and course
notebook chunks.

Pipeline:

    lesson_id
        ↓
    retrieve ALL chunks belonging to that lesson
        ↓
    MAP — summarize chunks in batches
        ↓
    REDUCE — combine the summaries
        ↓
    Markdown study notes + source list

The LLM generates the explanatory text, but citations are built from the
original chunk metadata. The model never invents Loom timestamps or notebook
URLs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

# The rest of the project imports modules directly from src/.
# Add src/ to sys.path so this module behaves the same way when run with:
#
#     python -m src.study_notes w7d2
#
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from langchain_openai import ChatOpenAI

from retrieval import get_store
from schemas import CHAT_MODEL, build_citation

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

LESSONS_PATH = ROOT_DIR / "data" / "lessons.json"
NOTES_DIR = ROOT_DIR / "summaries"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAP_CHUNK_SIZE = 8

# Keep individual chunks reasonably small when sending them to the LLM.
MAX_CHUNK_CHARS = 5000

# Maximum size of the combined map summaries passed to the reduce step.
MAX_SUMMARY_CHARS = 30000


# ---------------------------------------------------------------------------
# Course metadata
# ---------------------------------------------------------------------------


def load_lessons() -> dict:
    """Load the course lesson metadata."""

    if not LESSONS_PATH.exists():
        raise FileNotFoundError(
            f"Could not find lessons file: {LESSONS_PATH}"
        )

    return json.loads(
        LESSONS_PATH.read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def get_lesson_chunks(lesson_id: str) -> list[tuple]:
    """Retrieve every indexed chunk belonging to one lesson.

    Study Notes are different from normal question answering.

    Normal Q&A wants the most relevant chunks.

    Study Notes need the complete lesson material, otherwise important
    concepts could disappear simply because they were not among the top-k
    similarity results.

    The Chroma index already stores lesson_id in every chunk's metadata, so
    we retrieve directly by metadata instead of using semantic top-k search.
    """

    store = get_store()

    result = store.get(
        where={"lesson_id": lesson_id},
        include=["documents", "metadatas"],
    )

    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    chunks: list[tuple] = []

    for text, metadata in zip(documents, metadatas):
        if not text:
            continue

        chunks.append(
            (
                text,
                metadata,
            )
        )

    # Keep the lesson in a predictable order.
    #
    # Videos are ordered by timestamp.
    # Notebooks are ordered by cell index.
    #
    # We use source_type as the first key so video and notebook chunks
    # remain grouped rather than being randomly interleaved.
    def sort_key(item: tuple) -> tuple:
        text, metadata = item

        source_type = metadata.get("source_type", "")

        if source_type == "video":
            position = int(
                metadata.get("start_seconds", -1)
            )
        else:
            position = int(
                metadata.get("cell_index", -1)
            )

        return (
            source_type,
            position,
        )

    chunks.sort(key=sort_key)

    return chunks


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_chunk(
    index: int,
    text: str,
    metadata: dict,
) -> str:
    """Format one source chunk for the map prompt."""

    citation = build_citation(metadata)

    return (
        f"### Source {index}\n"
        f"Label: {citation['label']}\n"
        f"Source type: {metadata.get('source_type', '')}\n\n"
        f"{text[:MAX_CHUNK_CHARS].strip()}"
    )


# ---------------------------------------------------------------------------
# MAP step
# ---------------------------------------------------------------------------


def map_batch(
    llm: ChatOpenAI,
    lesson_id: str,
    batch: list[tuple],
    batch_number: int,
) -> str:
    """Summarize one batch of lesson chunks."""

    sources = []

    for index, (text, metadata) in enumerate(batch, start=1):
        sources.append(
            format_chunk(
                index=index,
                text=text,
                metadata=metadata,
            )
        )

    source_text = "\n\n".join(sources)

    prompt = f"""
You are creating study notes for the Ironhack AI Engineering course.

Lesson: {lesson_id}
Batch: {batch_number}

Summarize the course material below.

IMPORTANT RULES:

- Use ONLY the information contained in the supplied course material.
- Do not add outside knowledge.
- Preserve the terminology used by the course.
- Focus on concepts, definitions, explanations, examples, workflows,
  tools, and important implementation details.
- Remove repetition and conversational filler.
- Do not write a transcript.
- Do not invent examples that are not present in the material.
- If the material contains code or technical procedures, explain what they
  are doing rather than reproducing large blocks of code.
- Make the result useful as revision material for a student.
- Mention important concepts even if they are introduced briefly.
- Do not create a Sources section.
- Do not invent URLs or timestamps.

Write a concise but substantive study-note section.

COURSE MATERIAL:

{source_text}
""".strip()

    response = llm.invoke(prompt)

    return response.content.strip()


# ---------------------------------------------------------------------------
# REDUCE step
# ---------------------------------------------------------------------------


def reduce_summaries(
    llm: ChatOpenAI,
    lesson_id: str,
    lesson_title: str,
    summaries: list[str],
) -> str:
    """Combine map summaries into the final study notes."""

    combined = "\n\n".join(
        f"### Material section {index}\n{summary}"
        for index, summary in enumerate(
            summaries,
            start=1,
        )
    )

    combined = combined[:MAX_SUMMARY_CHARS]

    prompt = f"""
You are creating the final study notes for an Ironhack AI Engineering
course lesson.

Lesson ID: {lesson_id}
Lesson title: {lesson_title}

Below are summaries produced from the actual course recordings and
notebooks.

Create a clear, well-organized revision document.

IMPORTANT RULES:

- Use ONLY the supplied summaries.
- Do not introduce information from your general knowledge.
- Do not claim that something was taught if it does not appear in the
  supplied material.
- Preserve the course's terminology.
- Merge duplicated explanations.
- Keep technically important details.
- Prefer concise explanations over long prose.
- Use Markdown headings and bullet points.
- Make the notes useful for someone revising before an exam or project.
- Do not include URLs.
- Do not include timestamps.
- Do not include a Sources section.

Use exactly this high-level structure:

## Overview

A short explanation of what the lesson covers.

## Key Concepts

The most important concepts from the lesson.

## Detailed Notes

Organize the material into logical subsections. Create subsection
headings based on the actual concepts covered.

## Examples & Applications

Important examples, demonstrations, or applications explicitly present
in the material.

## Key Takeaways

A concise bullet list of the most important things the student should
remember.

COURSE MATERIAL SUMMARIES:

{combined}
""".strip()

    response = llm.invoke(prompt)

    return response.content.strip()


# ---------------------------------------------------------------------------
# Source collection
# ---------------------------------------------------------------------------


def build_sources(
    chunks: list[tuple],
) -> list[dict]:
    """Build a compact, deduplicated list of course sources.

    Multiple chunks from the same recording or notebook may have different
    URLs because video chunks contain different timestamps. For Study Notes,
    we only need one representative link per underlying course source.
    """

    sources: list[dict] = []
    seen: set[tuple] = set()

    for _, metadata in chunks:
        try:
            citation = build_citation(metadata)
        except ValueError:
            continue

        source_type = metadata.get("source_type", "")
        url = citation.get("url", "")

        if not url:
            continue

        if source_type == "video":
            source_key = (
                "video",
                metadata.get("loom_id")
                or metadata.get("recording_id")
                or url.split("?")[0],
            )
        elif source_type == "notebook":
            source_key = (
                "notebook",
                url.split("#")[0],
            )
        else:
            source_key = (
                source_type,
                url,
            )

        if source_key in seen:
            continue

        seen.add(source_key)

        label = citation.get(
            "label",
            "Course source",
        )

        if source_type == "notebook":
            label = re.sub(
                r"\s*·\s*cell\s+\d+\s*$",
                "",
                label,
            )

        sources.append(
            {
                **citation,
                "label": label,
                "source_type": source_type,
            }
        )

    return sources


# Final Markdown
# ---------------------------------------------------------------------------


def build_markdown(
    lesson_id: str,
    lesson_title: str,
    notes: str,
    sources: list[dict],
) -> str:
    """Build the final Markdown document with compact source sections."""

    lines = [
        f"# {lesson_id.upper()} — {lesson_title}",
        "",
        "> Study notes generated from the indexed Ironhack AI Engineering "
        "course recordings and notebooks.",
        "",
        notes.strip(),
        "",
        "## Sources",
        "",
    ]

    if not sources:
        lines.append(
            "_No course sources were available._"
        )
    else:
        videos = [
            source
            for source in sources
            if source.get("source_type") == "video"
        ]

        notebooks = [
            source
            for source in sources
            if source.get("source_type") == "notebook"
        ]

        other = [
            source
            for source in sources
            if source.get("source_type")
            not in {"video", "notebook"}
        ]

        # ---------------------------------------------------------------
        # Recordings
        # ---------------------------------------------------------------

        if videos:
            lines.extend(
                [
                    "### 🎥 Lecture recordings",
                    "",
                ]
            )

            for source in videos:
                label = source.get(
                    "label",
                    "Lecture recording",
                )
                url = source.get(
                    "url",
                    "",
                )

                if url:
                    lines.append(
                        f"- [{label}]({url})"
                    )
                else:
                    lines.append(
                        f"- {label}"
                    )

            lines.append("")

        # ---------------------------------------------------------------
        # Notebooks
        # ---------------------------------------------------------------

        if notebooks:
            lines.extend(
                [
                    "### 📓 Course notebooks",
                    "",
                ]
            )

            for source in notebooks:
                label = source.get(
                    "label",
                    "Course notebook",
                )
                url = source.get(
                    "url",
                    "",
                )

                if url:
                    lines.append(
                        f"- [{label}]({url})"
                    )
                else:
                    lines.append(
                        f"- {label}"
                    )

            lines.append("")

        # ---------------------------------------------------------------
        # Anything unexpected
        # ---------------------------------------------------------------

        if other:
            lines.extend(
                [
                    "### Other course sources",
                    "",
                ]
            )

            for source in other:
                label = source.get(
                    "label",
                    "Course source",
                )
                url = source.get(
                    "url",
                    "",
                )

                if url:
                    lines.append(
                        f"- [{label}]({url})"
                    )
                else:
                    lines.append(
                        f"- {label}"
                    )

            lines.append("")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_study_notes(
    lesson_id: str,
    *,
    output_path: Path | None = None,
) -> Path:
    """Generate Study Notes for one lesson."""

    lessons = load_lessons()

    if lesson_id not in lessons:
        available = ", ".join(
            sorted(lessons.keys())
        )

        raise ValueError(
            f"Unknown lesson_id {lesson_id!r}. "
            f"Available lessons: {available}"
        )

    lesson = lessons[lesson_id]

    lesson_title = lesson.get(
        "title",
        lesson_id,
    )

    print(
        f"Loading material for {lesson_id}: "
        f"{lesson_title}"
    )

    chunks = get_lesson_chunks(lesson_id)

    if not chunks:
        raise RuntimeError(
            f"No indexed chunks found for lesson {lesson_id}."
        )

    print(
        f"Found {len(chunks)} indexed chunks."
    )

    llm = ChatOpenAI(
        model=CHAT_MODEL,
        temperature=0,
    )

    # -----------------------------------------------------------------------
    # MAP
    # -----------------------------------------------------------------------

    batches = [
        chunks[start:start + MAP_CHUNK_SIZE]
        for start in range(
            0,
            len(chunks),
            MAP_CHUNK_SIZE,
        )
    ]

    print(
        f"MAP step: {len(batches)} batches."
    )

    summaries: list[str] = []

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        print(
            f"  Summarizing batch "
            f"{batch_number}/{len(batches)}..."
        )

        summary = map_batch(
            llm=llm,
            lesson_id=lesson_id,
            batch=batch,
            batch_number=batch_number,
        )

        if summary:
            summaries.append(summary)

    if not summaries:
        raise RuntimeError(
            f"The MAP step produced no summaries for {lesson_id}."
        )

    # -----------------------------------------------------------------------
    # REDUCE
    # -----------------------------------------------------------------------

    print(
        f"REDUCE step: combining {len(summaries)} summaries..."
    )

    notes = reduce_summaries(
        llm=llm,
        lesson_id=lesson_id,
        lesson_title=lesson_title,
        summaries=summaries,
    )

    # -----------------------------------------------------------------------
    # SOURCES
    # -----------------------------------------------------------------------

    sources = build_sources(chunks)

    # -----------------------------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------------------------

    if output_path is None:
        output_path = (
            NOTES_DIR
            / f"{lesson_id}.md"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    markdown = build_markdown(
        lesson_id=lesson_id,
        lesson_title=lesson_title,
        notes=notes,
        sources=sources,
    )

    output_path.write_text(
        markdown,
        encoding="utf-8",
    )

    print()
    print(
        f"Study Notes written to:"
    )
    print(
        f"  {output_path}"
    )
    print(
        f"Sources: {len(sources)}"
    )

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point."""

    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python -m src.study_notes <lesson_id>\n\n"
            "Example:\n"
            "  python -m src.study_notes w7d2"
        )

        raise SystemExit(1)

    lesson_id = sys.argv[1].strip().lower()

    generate_study_notes(
        lesson_id
    )


if __name__ == "__main__":
    main()