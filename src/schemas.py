"""The two contracts from para-leer/SCHEMA.md, as code.

Both parsers build chunks through the helpers here rather than hand-writing dicts, so
Casilda's VTT parser and Felipe's notebook parser cannot drift apart. The agent builds
citations through `build_citation`, so the UI never has to know that Loom wants `?t=872s`
and silently ignores `?t=872`.

If you need to change something in here, change para-leer/SCHEMA.md first and tell the
other person. A silent change breaks the other side and surfaces days later.
"""

from __future__ import annotations

# --- agreed on the call, 2026-08-05 -----------------------------------------

COLLECTION_NAME = "course_material"

# Chunk size IS timestamp precision: we cite the start of a chunk, so a 4-minute chunk
# points four minutes before the answer. 1000 chars is ~65s of lecture speech, which
# holds one complete idea while still landing the student close enough.
VIDEO_CHUNK_SIZE = 1000
VIDEO_CHUNK_OVERLAP = 200

# Notebooks split on markdown headings, which are already semantic units. Only force a
# split when a single section runs longer than this.
NOTEBOOK_MAX_CHARS = 1500

# 512 rather than the default 1536: ~6,000 chunks at 1536 dims makes a ~75 MB index,
# and GitHub warns at 50 MB per file. At 512 it is ~25 MB with no measurable retrieval
# loss at this corpus size.
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMENSIONS = 512

# Chat model. Not part of the frozen contracts — just shared config so agent.py and
# tools.py (which both make LLM calls) can't drift to two different models.
CHAT_MODEL = "gpt-4o-mini"

# Refusal detection. agent.py uses this to decide whether to drop citations (a
# confidently-wrong retrieval can still surface 5 irrelevant chunks even when the model
# correctly judges the topic uncovered — see the "quantum" vs "quantization" case).
# evaluation.py uses the SAME list to score refusals. One list, not two: a bare "no
# está" here once matched "no está disponible" inside a completely correct Spanish
# answer about training data and silently deleted 5 good citations. Every phrase below
# is specific to REFUSING, not just containing a negation.
#
# The system prompt gives the model this exact English template and a Spanish example,
# so wording stays predictable enough for keyword matching to work.
REFUSAL_MARKERS = (
    "wasn't covered", "was not covered", "not covered in the course",
    "does not cover", "do not cover", "doesn't cover",
    "no fue cubierto", "no está cubierto", "no se cubrió",
)

NOTEBOOK_REPO = "https://github.com/ironhack-ai-eng-june2026/demos_ai_eng/blob/main"
LOOM_EMBED = "https://www.loom.com/embed"

SOURCE_VIDEO = "video"
SOURCE_NOTEBOOK = "notebook"

# Chroma only accepts str/int/float/bool as metadata values. No lists, no dicts, no None.
_ALLOWED_META_TYPES = (str, int, float, bool)

# Every chunk carries every key. Filters behave predictably that way, and a missing key
# never silently excludes a document from a `where` query.
_DEFAULTS: dict[str, str | int] = {
    "source_type": "",
    "lesson_id": "",
    "lesson_title": "",
    "week": -1,
    "day": -1,
    # video
    "loom_id": "",
    "start_seconds": -1,
    "segment": "",
    "transcript_source": "",
    # notebook
    "folder": "",
    "notebook": "",
    "cell_index": -1,
    "heading": "",
}


# --- formatting -------------------------------------------------------------


def format_timestamp(seconds: int) -> str:
    """Human label: 872 -> '14:32', 4532 -> '1:15:32'."""
    seconds = max(int(seconds), 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def loom_time_param(seconds: int) -> str:
    """Loom's `t` parameter. It wants '872s' or '14m32s' and IGNORES a bare '872'.

    This is the single easiest thing to get wrong in the whole project: a bare integer
    fails silently, so the player just starts at zero and the citation looks broken
    without any error anywhere.
    """
    return f"{max(int(seconds), 0)}s"


# --- chunk construction -----------------------------------------------------


def _finish(meta: dict) -> dict:
    """Fill defaults, then reject anything Chroma would choke on."""
    full = {**_DEFAULTS, **meta}
    for key, value in full.items():
        if not isinstance(value, _ALLOWED_META_TYPES):
            raise TypeError(
                f"metadata[{key!r}] is {type(value).__name__}; Chroma accepts only "
                f"str, int, float, bool. Join lists into a delimited string."
            )
    return full


def video_chunk(
    text: str,
    *,
    lesson_id: str,
    lesson_title: str,
    loom_id: str,
    start_seconds: int,
    segment: str = "",
    transcript_source: str = "loom",
) -> dict:
    """One chunk of a lecture transcript.

    `start_seconds` is scoped to its own Loom, not to the lesson day — a day is 3-6
    separate recordings, so a time without `loom_id` is meaningless.
    """
    week, day = parse_lesson_id(lesson_id)
    return {
        "text": text,
        "metadata": _finish(
            {
                "source_type": SOURCE_VIDEO,
                "lesson_id": lesson_id,
                "lesson_title": lesson_title,
                "week": week,
                "day": day,
                "loom_id": loom_id,
                "start_seconds": int(start_seconds),
                "segment": segment,
                "transcript_source": transcript_source,
            }
        ),
    }


def notebook_chunk(
    text: str,
    *,
    lesson_id: str,
    lesson_title: str,
    folder: str,
    notebook: str,
    cell_index: int,
    heading: str = "",
) -> dict:
    """One chunk of a course notebook, normally one markdown section."""
    week, day = parse_lesson_id(lesson_id)
    return {
        "text": text,
        "metadata": _finish(
            {
                "source_type": SOURCE_NOTEBOOK,
                "lesson_id": lesson_id,
                "lesson_title": lesson_title,
                "week": week,
                "day": day,
                "folder": folder,
                "notebook": notebook,
                "cell_index": int(cell_index),
                "heading": heading,
            }
        ),
    }


def parse_lesson_id(lesson_id: str) -> tuple[int, int]:
    """'w7d2' -> (7, 2). Returns (-1, -1) for anything unparseable."""
    try:
        week, day = lesson_id.lower().lstrip("w").split("d")
        return int(week), int(day)
    except (ValueError, AttributeError):
        return -1, -1


# --- citations --------------------------------------------------------------


def build_citation(metadata: dict) -> dict:
    """Turn chunk metadata into what the UI renders.

    The agent calls this; the UI never computes a label or a URL. That way Felipe never
    needs to know Loom's `?t=` quirk and Casilda never needs to know how Streamlit
    renders an iframe.
    """
    source_type = metadata.get("source_type", "")

    if source_type == SOURCE_VIDEO:
        start = int(metadata.get("start_seconds", -1))
        loom_id = metadata.get("loom_id", "")
        stamp = format_timestamp(start)
        return {
            "source_type": SOURCE_VIDEO,
            "lesson_id": metadata.get("lesson_id", ""),
            "label": f"{metadata.get('lesson_id','')} · {metadata.get('lesson_title','')} · {stamp}",
            "url": f"{LOOM_EMBED}/{loom_id}?t={loom_time_param(start)}",
            "start_seconds": start,
        }

    if source_type == SOURCE_NOTEBOOK:
        folder = metadata.get("folder", "")
        notebook = metadata.get("notebook", "")
        cell = int(metadata.get("cell_index", -1))
        cell_label = f" · cell {cell}" if cell >= 0 else ""
        return {
            "source_type": SOURCE_NOTEBOOK,
            "lesson_id": metadata.get("lesson_id", ""),
            "label": f"{folder}/{notebook}{cell_label}",
            "url": f"{NOTEBOOK_REPO}/{folder}/{notebook}",
            "start_seconds": -1,
        }

    raise ValueError(f"unknown source_type {source_type!r}")


def build_response(answer: str, chunk_metadatas: list[dict]) -> dict:
    """The full agent response. Deduplicates citations, preserving order."""
    citations, seen = [], set()
    for meta in chunk_metadatas:
        citation = build_citation(meta)
        if citation["url"] not in seen:
            seen.add(citation["url"])
            citations.append(citation)
    return {"answer": answer, "citations": citations}
