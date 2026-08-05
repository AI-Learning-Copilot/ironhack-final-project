"""Agent tools.

The problem these solve: a LangChain tool can only return a *string* to the model, but
the UI needs structured citations — lesson id, Loom id, timestamp — to render an embedded
player. If we asked the model to repeat that data back to us in its answer it would
paraphrase, drop digits, and occasionally invent a timestamp.

So the tools do two things at once. They return readable text to the model, and they
record the exact metadata of every chunk they touched into a `CitationCollector`. After
the run, `agent.py` reads the collector. The model never handles a URL or a timestamp.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from retrieval import search, search_with_scores
from schemas import build_citation, format_timestamp

# Chroma returns distances, so lower is closer. Re-measured after contextual headers
# were added to chunk text (which tightened every on-topic score):
#
#   on-topic  (RAG, embeddings, chunking, cosine sim, vector DBs, CLIP)   0.721 - 0.923
#   off-topic (capital of France, paella, changing a tyre, 1998 World Cup) 1.381 - 1.682
#   borderline ("train a model on a Roman aqueduct dataset")              1.119
#
# 1.3 sits in the empty band, with a 0.196 margin above the worst on-topic score. The
# borderline case stays IN on purpose: "how do I train a model" genuinely is course
# material, only the dataset is not, and the agent words that refusal correctly itself.
#
# Fitted to eleven queries, so treat it as a starting point. C6 should re-tune it against
# the 25-question eval set, which includes three deliberately unanswerable ones.
RELEVANCE_CUTOFF = 1.3


class CitationCollector:
    """Collects chunk metadata across one question, in the order the tools saw it."""

    def __init__(self) -> None:
        self.metadatas: list[dict] = []

    def add(self, metadata: dict) -> None:
        self.metadatas.append(dict(metadata))

    def reset(self) -> None:
        self.metadatas.clear()


class SearchInput(BaseModel):
    query: str = Field(description="What to look for, in the student's own words.")
    lesson_id: str = Field(
        default="",
        description="Optional lesson filter such as 'w7d2'. Leave empty to search everything.",
    )


class TimestampInput(BaseModel):
    topic: str = Field(description="The concept to locate, e.g. 'cosine similarity'.")


def _format_hit(index: int, doc) -> str:
    citation = build_citation(doc.metadata)
    return f"[{index}] {citation['label']}\n{doc.page_content.strip()}"


def make_tools(collector: CitationCollector) -> list[StructuredTool]:
    """Build the tool set, wired to one collector."""

    def search_course_material(query: str, lesson_id: str = "") -> str:
        """Search the course recordings for what was actually said about something."""
        scored = search_with_scores(query, k=5)
        # Filter by distance, not just by rank. Similarity search always returns k
        # results, so an off-topic question ("train a model on Roman aqueducts") still
        # comes back with five confident-looking chunks. Without this the agent refuses
        # correctly but the UI renders five irrelevant videos underneath the refusal.
        hits = [doc for doc, score in scored if score <= RELEVANCE_CUTOFF]
        if lesson_id:
            hits = [d for d in hits if d.metadata.get("lesson_id") == lesson_id]
        if not hits:
            return "NO_RESULTS: nothing in the course material matches that."
        for doc in hits:
            collector.add(doc.metadata)
        return "\n\n".join(_format_hit(i, d) for i, d in enumerate(hits, 1))

    def find_timestamp(topic: str) -> str:
        """Find which lessons cover a topic and at what point in the recording."""
        scored = search_with_scores(topic, k=8)
        relevant = [(d, s) for d, s in scored if s <= RELEVANCE_CUTOFF]
        if not relevant:
            return "NO_RESULTS: that topic does not appear in the course recordings."

        lines, seen = [], set()
        for doc, _ in relevant:
            meta = doc.metadata
            key = (meta["lesson_id"], meta["loom_id"], meta["start_seconds"] // 300)
            if key in seen:
                continue
            seen.add(key)
            collector.add(meta)
            lines.append(
                f"- {meta['lesson_id']} · {meta['lesson_title']} · "
                f"{format_timestamp(meta['start_seconds'])}"
            )
        return "Covered at:\n" + "\n".join(lines[:5])

    return [
        StructuredTool.from_function(
            func=search_course_material,
            name="search_course_material",
            description=(
                "Search the bootcamp recordings for what the instructor actually said "
                "about a concept. Use this for any question about course content. "
                "Returns transcript excerpts with the lesson and timestamp they came from."
            ),
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            func=find_timestamp,
            name="find_timestamp",
            description=(
                "Find WHERE a topic was covered — which lesson and at what minute. Use "
                "this when the student asks where or when something was explained, "
                "rather than asking for the explanation itself."
            ),
            args_schema=TimestampInput,
        ),
    ]
