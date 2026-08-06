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

import functools
import json
from pathlib import Path

from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from retrieval import search, search_with_scores
from schemas import CHAT_MODEL, build_citation, format_timestamp

LESSONS_PATH = Path(__file__).resolve().parents[1] / "data" / "lessons.json"

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


class ExplainInput(BaseModel):
    concept: str = Field(description="The concept to explain, in the student's words.")
    style: str = Field(
        default="simple",
        description="'simple' for a beginner explanation with an analogy, "
        "'technical' for the precise definition. Default 'simple'.",
    )


class QuizInput(BaseModel):
    topic: str = Field(description="The topic to quiz the student on.")
    num_questions: int = Field(default=3, description="How many questions. 3-5.")


class LessonIndexInput(BaseModel):
    week: str = Field(
        default="",
        description="Optional filter such as 'w7' for week 7. Leave empty to list every lesson.",
    )


def _format_hit(index: int, doc) -> str:
    citation = build_citation(doc.metadata)
    return f"[{index}] {citation['label']}\n{doc.page_content.strip()}"


@functools.lru_cache(maxsize=1)
def _load_lessons() -> dict:
    if not LESSONS_PATH.exists():
        return {}
    return json.loads(LESSONS_PATH.read_text())


def make_tools(
    collector: CitationCollector, llm: ChatOpenAI | None = None
) -> list[StructuredTool]:
    """Build the tool set, wired to one collector.

    `explain_concept` and `generate_quiz` make a second LLM call of their own — they are
    not pure retrieval like the first two tools. Reuse the caller's `llm` when one is
    passed (agent.py does this) so a Copilot only opens one model client rather than two.
    """
    synth_llm = llm or ChatOpenAI(model=CHAT_MODEL, temperature=0)

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

    def explain_concept(concept: str, style: str = "simple") -> str:
        """A pedagogical explanation, grounded in the recordings — not a raw excerpt dump."""
        scored = search_with_scores(concept, k=5)
        hits = [doc for doc, score in scored if score <= RELEVANCE_CUTOFF]
        if not hits:
            return "NO_RESULTS: that concept does not appear in the course recordings."
        for doc in hits:
            collector.add(doc.metadata)

        context = "\n\n".join(d.page_content.strip() for d in hits)
        instruction = (
            "Explain it to a complete beginner using a concrete analogy. Avoid jargon "
            "where you can."
            if style != "technical"
            else "Give the precise technical explanation an experienced engineer would expect."
        )
        prompt = (
            f"Using ONLY the course excerpts below, explain '{concept}'. {instruction}\n\n"
            f"Course excerpts:\n{context}"
        )
        return synth_llm.invoke(prompt).content

    def generate_quiz(topic: str, num_questions: int = 3) -> str:
        """Multiple-choice questions grounded in the recordings, with answers."""
        num_questions = max(3, min(num_questions, 5))
        scored = search_with_scores(topic, k=8)
        hits = [doc for doc, score in scored if score <= RELEVANCE_CUTOFF]
        if not hits:
            return (
                "NO_RESULTS: that topic does not appear in the course recordings, "
                "so a quiz cannot be generated."
            )
        for doc in hits:
            collector.add(doc.metadata)

        # Cap at 6 excerpts even when 8 were retrieved: more context does not make a
        # better 3-question quiz, it just adds tokens and lets the model wander off-topic.
        context = "\n\n".join(d.page_content.strip() for d in hits[:6])
        prompt = (
            f"Using ONLY the course excerpts below, write {num_questions} multiple-choice "
            f"quiz questions about '{topic}'. Each question needs 4 options labelled A-D "
            "and exactly one correct answer. Base every question and answer strictly on "
            "the excerpts — never invent a fact that is not in them. Format each question "
            "as:\n\n<question>\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: <letter>\n\n"
            f"Course excerpts:\n{context}"
        )
        return synth_llm.invoke(prompt).content

    def lesson_index(week: str = "") -> str:
        """The course calendar — no retrieval, no LLM call, just data/lessons.json."""
        lessons = _load_lessons()
        if not lessons:
            return "NO_RESULTS: the lesson index is not available."

        ids = sorted(lessons)
        if week:
            prefix = week.strip().lower()
            ids = [lesson_id for lesson_id in ids if lesson_id.startswith(prefix)]
            if not ids:
                return f"NO_RESULTS: no lessons found matching '{week}'."

        # Deliberately not added to the collector: this is a table of contents, not
        # sourced content — it has no single moment worth citing.
        lines = [f"- {lesson_id}: {lessons[lesson_id]['title']}" for lesson_id in ids]
        return "Course lessons:\n" + "\n".join(lines)

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
        StructuredTool.from_function(
            func=explain_concept,
            name="explain_concept",
            description=(
                "Explain a NEW concept, named for the first time this conversation, "
                "pedagogically and with an analogy, grounded in the recordings. "
                "Do NOT use this for 'explain that more simply', 'simplify', 'in other "
                "words', or any request to re-explain something already discussed — "
                "those are answered from conversation memory with no tool call at all."
            ),
            args_schema=ExplainInput,
        ),
        StructuredTool.from_function(
            func=generate_quiz,
            name="generate_quiz",
            description=(
                "Generate 3-5 multiple-choice quiz questions on a topic, grounded in the "
                "recordings. Use this when the student asks to be quizzed or tested."
            ),
            args_schema=QuizInput,
        ),
        StructuredTool.from_function(
            func=lesson_index,
            name="lesson_index",
            description=(
                "List the lessons in the course, optionally filtered to one week (e.g. "
                "'w7'). Use this for 'what did we cover' or 'what lessons are there' "
                "questions — NOT for explaining a specific concept."
            ),
            args_schema=LessonIndexInput,
        ),
    ]
