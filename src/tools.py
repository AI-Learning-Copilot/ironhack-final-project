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
import random
import re
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
RELEVANCE_CUTOFF = 1.0

# A scoped search needs a stricter bar. Unscoped, a chunk has to beat 5,000 others to
# rank first, so a top hit under 1.3 really is about the topic. Scoped to one week or
# one day that competition disappears and the "best" chunk can be merely the least bad
# one. Measured for the query "RAG":
#
#   week 7 (genuinely covers RAG)   0.866
#   week 2 (does not)               1.232   <- passed 1.3, produced a quiz about R-squared
#   week 1 / week 3 (do not)        1.351 / 1.339
#   w1d1   (does not)               1.465
#
# 1.15 sits in the gap: week 7 still passes, week 2 now refuses.
SCOPED_RELEVANCE_CUTOFF = 1.15


class CitationCollector:
    """Collects chunk metadata across one question, in the order the tools saw it."""

    def __init__(self) -> None:
        self.metadatas: list[dict] = []

    def add(self, metadata: dict) -> None:
        self.metadatas.append(dict(metadata))

    def reset(self) -> None:
        self.metadatas.clear()


class SearchInput(BaseModel):
    query: str = Field(
        description=(
            "The student's FULL question, close to verbatim. Do NOT reduce it to a "
            "keyword or acronym. This is embedded and compared against lecture "
            "transcripts, so a bare term retrieves badly: 'CLIP' scores 1.193 and "
            "returns the LangChain recap, while 'How does CLIP work?' scores 0.725 "
            "and returns the CLIP lesson. Send the sentence, not the noun."
        )
    )
    lesson_id: str = Field(
        default="",
        description="Optional lesson filter such as 'w7d2'. Leave empty to search everything.",
    )


class TimestampInput(BaseModel):
    topic: str = Field(
        description=(
            "The concept to locate, as a phrase rather than a bare acronym — "
            "'how CLIP works' retrieves far better than 'CLIP'."
        )
    )


class NotebookInput(BaseModel):
    topic: str = Field(
        description=(
            "What the notebook should be about, as a phrase rather than a bare "
            "acronym — 'a RAG pipeline in LangChain' retrieves better than 'RAG'."
        )
    )


class ExplainInput(BaseModel):
    concept: str = Field(
        description=(
            "The concept to explain, in the student's words and as a phrase rather "
            "than a bare acronym. Single terms embed poorly against transcripts."
        )
    )
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


# A whole-course listing is 32 days; citing every one of them buries the answer. Six is
# the longest week in this course (weeks 1 and 5 have five taught days), so any
# single-week or single-day query cites, and only the unfiltered "list everything" does
# not.
LESSON_INDEX_CITATION_LIMIT = 6


@functools.lru_cache(maxsize=1)
def _load_lessons() -> dict:
    if not LESSONS_PATH.exists():
        return {}
    return json.loads(LESSONS_PATH.read_text())


class SourceLog:
    """Every source cited so far this conversation, kept outside the LLM's memory.

    The problem this solves: `ConversationSummaryBufferMemory` compresses older turns
    into prose, and prose loses digits. Measured on a real conversation, the summary kept
    "week 4 day 3" but contained no lesson id and no timestamp — the summariser wrote
    "at specific timestamps" instead of the numbers. So "go back to that minute you gave
    me earlier" became unanswerable after the buffer overflowed, even though the exact
    values had been in hand when the answer was generated.

    They were structured data before they were ever prose. `CitationCollector` already
    holds `lesson_id` and `start_seconds` per turn; this keeps them, indexed by turn, for
    as long as the conversation lasts. A prompt asking the summariser to preserve
    timestamps helps, but it is a model doing as it is told — this is the guarantee.

    Deduplicated on the citation label, so ten chunks from one lesson minute do not
    become ten entries.
    """

    # Enough to cover a long revision session without the tool output itself becoming a
    # wall of text the agent has to read on every call.
    MAX_TURNS = 12

    def __init__(self) -> None:
        self.turns: list[dict] = []

    def record(self, question: str, citations: list[dict]) -> None:
        """Called once per answered turn, after the citations are built."""
        if not citations:
            return

        seen: set[str] = set()
        labels: list[str] = []
        for citation in citations:
            label = citation.get("label", "")
            if label and label not in seen:
                seen.add(label)
                labels.append(label)

        self.turns.append({"question": question, "labels": labels})
        del self.turns[: -self.MAX_TURNS]

    def clear(self) -> None:
        self.turns.clear()

    def render(self) -> str:
        if not self.turns:
            return "NO_RESULTS: nothing has been cited in this conversation yet."

        lines = []
        for number, turn in enumerate(self.turns, 1):
            lines.append(f"{number}. You asked: {turn['question']}")
            lines.extend(f"   - {label}" for label in turn["labels"])
        return "Sources cited earlier in this conversation:\n" + "\n".join(lines)


class SearchScope:
    """How much of the course the tools are allowed to see this turn.

    Set on the retrieval side rather than asked for in the prompt. Wording a scope into
    the question only reaches whichever tool the model happens to pick, and it has to
    remember to pass the argument. A student who scopes to week 7 and then asks to be
    quizzed expects the *quiz* to come from week 7 — so the constraint belongs where
    every tool shares it, not in an argument one tool might forget.

    Empty means the whole course, which is the default.
    """

    def __init__(self) -> None:
        self.lesson_id: str = ""
        self.week: int | None = None

    def set(self, lesson_id: str = "", week: int | None = None) -> None:
        self.lesson_id = lesson_id or ""
        self.week = week

    def clear(self) -> None:
        self.set()

    @property
    def active(self) -> bool:
        return bool(self.lesson_id or self.week)

    def label(self) -> str:
        """How the scope is named back to the student."""
        if self.lesson_id:
            return self.lesson_id
        if self.week:
            return f"week {self.week}"
        return ""

    def kwargs(self) -> dict:
        return {"lesson_id": self.lesson_id or None, "week": self.week}

    def cutoff(self) -> float:
        return SCOPED_RELEVANCE_CUTOFF if self.active else RELEVANCE_CUTOFF


_OPTION_LINE = re.compile(r"^\s*\**\s*([A-D])\s*[\)\.\:]\s*(.+?)\s*\**\s*$")
_ANSWER_LINE = re.compile(r"^\s*\**\s*answer\s*:\s*([A-D])\s*\**\s*$", re.IGNORECASE)


def shuffle_quiz_answers(quiz: str) -> str:
    """Redistribute which letter is correct, preserving the frozen quiz format.

    Prompting alone does not fix this. Told explicitly to vary the position, the model
    still produced A×7 B×7 C×2 D×0 over sixteen questions — a student who always
    guesses B beats one who has not studied, and D is safe to ignore entirely.

    So the options are shuffled after generation and the Answer line rewritten to match.
    The output format is the contract in para-leer/SCHEMA.md that app.py parses, so this
    re-emits exactly that shape. Any question that does not parse cleanly is passed
    through untouched rather than risking a mangled quiz.
    """
    lines = quiz.splitlines()
    out: list[str] = []
    block: list[tuple[str, str]] = []
    block_start = 0

    def flush(answer_line_index: int | None, answer_letter: str | None) -> None:
        """Emit the pending option block, shuffled, with its answer line."""
        nonlocal block
        if len(block) != 4 or answer_letter is None:
            block = []
            return

        letters = [letter for letter, _ in block]
        texts = [text for _, text in block]
        correct_text = dict(block).get(answer_letter)

        order = list(range(4))
        random.shuffle(order)
        shuffled = [texts[i] for i in order]

        indent = " " * (len(out[block_start]) - len(out[block_start].lstrip()))
        for position, text in enumerate(shuffled):
            out[block_start + position] = f"{indent}{letters[position]}) {text}"

        new_letter = "ABCD"[shuffled.index(correct_text)]
        if answer_line_index is not None:
            out[answer_line_index] = f"{indent}Answer: {new_letter}"

        block = []

    for line in lines:
        option = _OPTION_LINE.match(line)
        answer = _ANSWER_LINE.match(line)

        out.append(line)

        if option:
            if not block:
                block_start = len(out) - 1
            block.append((option.group(1).upper(), option.group(2)))
        elif answer:
            flush(len(out) - 1, answer.group(1).upper())
        elif line.strip():
            block = []

    return "\n".join(out)


def make_tools(
    collector: CitationCollector,
    llm: ChatOpenAI | None = None,
    scope: SearchScope | None = None,
    sources: SourceLog | None = None,
) -> list[StructuredTool]:
    """Build the tool set, wired to one collector.

    `explain_concept` and `generate_quiz` make a second LLM call of their own — they are
    not pure retrieval like the first two tools. Reuse the caller's `llm` when one is
    passed (agent.py does this) so a Copilot only opens one model client rather than two.
    """
    synth_llm = llm or ChatOpenAI(
        model=CHAT_MODEL,
        temperature=0,
    )
    scope = scope if scope is not None else SearchScope()
    sources = sources if sources is not None else SourceLog()

    # The quiz gets its own client at a non-zero temperature. Everything else in this
    # project wants determinism, but a study tool that returns the identical three
    # questions every time you press the button is useless for revision — the second
    # attempt tests memory of the quiz, not of the course.
    # 0.5, not 0.8. Variety now comes from sampling a wider pool of excerpts rather
    # than from the sampler, and a hotter model was more willing to state a number it
    # half-remembered from the transcript as though it were a taught fact.
    quiz_llm = ChatOpenAI(
        model=CHAT_MODEL,
        temperature=1,
        )

    def search_course_material(query: str, lesson_id: str = "") -> str:
        """Search the course recordings for what was actually said about something."""
        # lesson_id is applied inside the search, not after it. Retrieving the global
        # top-5 and then dropping everything from other lessons almost always left
        # nothing, because the five nearest chunks across 5,000+ rarely share one day.
        # An explicit lesson_id argument from the model narrows further; the UI scope
        # is always applied on top of it.
        narrowed = dict(scope.kwargs())
        if lesson_id:
            narrowed["lesson_id"] = lesson_id
        scored = search_with_scores(query, k=5, **narrowed)
        # Filter by distance, not just by rank. Similarity search always returns k
        # results, so an off-topic question ("train a model on Roman aqueducts") still
        # comes back with five confident-looking chunks. Without this the agent refuses
        # correctly but the UI renders five irrelevant videos underneath the refusal.
        hits = [doc for doc, score in scored if score <= scope.cutoff()]
        if not hits:
            return "NO_RESULTS: nothing in the course material matches that."
        for doc in hits:
            collector.add(doc.metadata)
        return "\n\n".join(_format_hit(i, d) for i, d in enumerate(hits, 1))

    def find_notebooks(topic: str) -> str:
        """Which course notebooks cover a topic — file paths, no timestamps.

        Exists because "where are the notebooks on RAG?" used to return three videos and
        one notebook. The corpus is 5,090 video chunks against 947 notebook ones, so an
        unfiltered search is won by video on almost any topic that was also taught out
        loud — which is all of them. The filter goes into the query rather than being
        applied to the results, for the same reason `lesson_id` does: post-filtering a
        global top-8 usually leaves one notebook or none.

        Deduplicated by file. A student asking for the notebook wants one link per
        notebook, not the same file listed once per matching cell.
        """
        scored = search_with_scores(
            topic, k=12, source_type="notebook", **scope.kwargs()
        )
        relevant = [(d, s) for d, s in scored if s <= scope.cutoff()]
        if not relevant:
            return "NO_RESULTS: no course notebook covers that topic."

        lines, seen = [], set()
        for doc, _ in relevant:
            meta = doc.metadata
            key = (meta.get("folder", ""), meta.get("notebook", ""))
            if key in seen:
                continue
            seen.add(key)
            collector.add(meta)
            lines.append(f"- {build_citation(meta)['label']}")

        return "Course notebooks:\n" + "\n".join(lines[:5])

    def find_timestamp(topic: str) -> str:
        """Find which lessons cover a topic and at what point in the recording."""
        # Video only. A notebook has no minute, so an unfiltered search here produced
        # answers like "in the supplementary course notebook at 0:00 of the extra
        # lesson" — a timestamp invented for a file that does not have one. Notebook
        # questions belong to find_notebooks.
        scored = search_with_scores(topic, k=8, source_type="video", **scope.kwargs())
        relevant = [(d, s) for d, s in scored if s <= scope.cutoff()]
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
        scored = search_with_scores(concept, k=5, **scope.kwargs())
        hits = [doc for doc, score in scored if score <= scope.cutoff()]
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
        # Retrieve wider than needed, then sample. With k=8 and a fixed cap of 6 the
        # same six excerpts fed the model every time, so temperature alone would only
        # reword one fixed quiz. A wider pool means genuinely different questions.
        # Expand common course abbreviations so short quiz topics still retrieve
        # the relevant lesson. Keep this local to quiz generation so we do not
        # change the behaviour of normal course Q&A.
        quiz_query = topic

        topic_expansions = {
            "pca": "PCA Principal Component Analysis dimensionality reduction",
            "clip": "CLIP Contrastive Language-Image Pre-training multimodal image text",
            "rag": "RAG Retrieval-Augmented Generation retrieval context",
            "nlp": "NLP Natural Language Processing",
        }

        normalized_topic = topic.strip().lower()

        if normalized_topic in topic_expansions:
            quiz_query = topic_expansions[normalized_topic]

        scored = search_with_scores(quiz_query, k=20, **scope.kwargs())

        hits = [doc for doc, score in scored if score <= scope.cutoff()]
        if not hits:
            return (
                "NO_RESULTS: that topic does not appear in the course recordings, "
                "so a quiz cannot be generated."
            )
        # Six excerpts is the useful ceiling — more context does not make a better
        # 3-question quiz, it just adds tokens and lets the model wander off-topic.
        # Keep the closest two so the quiz stays on topic, then sample the rest from
        # the remaining pool so a second attempt is not the same quiz again.
        pool = hits[:2] + random.sample(hits[2:], min(4, max(0, len(hits) - 2)))
        for doc in pool:
            collector.add(doc.metadata)
        context = "\n\n".join(d.page_content.strip() for d in pool)
        # QUIZ FORMAT CONTRACT:
        # Keep this output format aligned with the frozen contract in
        # para-leer/SCHEMA.md. app/app.py parses this text to build the
        # interactive quiz and calculate the student's score.
        # The rules below exist because the first version produced technically-correct
        # but weak questions. Two failures in particular:
        #
        #   "What differentiates a router chain from a sequential chain?"
        #     A) Router chains can only handle one input at a time
        #     B) Router chains are used for making decisions based on conditions
        #     ...
        #   Every option describes router chains only, so the comparison the stem
        #   promises is never actually tested.
        #
        #   "What is the primary focus of the course excerpt regarding R-squared?"
        #   A question about the excerpt rather than about the subject.
        #
        #   "How many chains can theoretically be concatenated in LangChain?"  -> "100"
        #   A number said in passing, turned into a fact. "Unlimited" is arguably the
        #   better answer, and the student learns nothing either way.
        #
        #   "What happens when you run a sequential chain with the topic 'tennis'?"
        #   Tests whether you watched the demo that happened to use the word tennis.
        #   The mechanism is the point; the example topic is noise.
        prompt = (
            f"Using ONLY the course excerpts below, write {num_questions} multiple-choice "
            f"quiz questions about '{topic}'.\n\n"
            "Rules for the questions:\n"
            "- Ask about the SUBJECT, never about the material. Never write 'according "
            "to the excerpt', 'in this lesson', or 'what does the course say about'. The "
            "student is being tested on the concept, not on the transcript.\n"
            "- If a question compares two things, the options MUST distinguish between "
            "them — each option should say something about both, or contrast them "
            "directly. An option that only describes one of the two cannot test the "
            "comparison, which makes the question answerable without understanding it.\n"
            "- Vary what you ask: what something is, what it is for, when to choose it "
            "over an alternative, what happens if it is missing or misused.\n"
            "- Ask about the CONCEPT, never about the incidental details of a demo. "
            "The excerpts are lecture transcripts, so they are full of specifics that "
            "carry no understanding: the example topic the instructor typed, a variable "
            "name, a file name, which dataset was loaded. If a question can only be "
            "answered by having watched that exact demo, it is the wrong question — ask "
            "about the mechanism the demo was illustrating instead.\n"
            "- Never ask for a number, a count, a limit or a version unless the number "
            "is itself something the course teaches. A figure said once in passing is "
            "not a fact worth testing, and guessing one is worse.\n"
            "- If the excerpts do not state something explicitly and unambiguously, do "
            "not ask about it. Prefer a question you can point at a sentence for.\n\n"
            "Rules for the options:\n"
            "- Exactly four, labelled A-D, exactly one correct.\n"
            "- All four must be the same KIND of statement and roughly the same length. "
            "A single longer, more detailed option gives the answer away.\n"
            "- Wrong options must be plausible to someone who half-remembers the "
            "material — a real concept applied to the wrong thing, or a common "
            "misunderstanding. Never absurd, never obviously off-topic, never a "
            "filler like 'none of the above'.\n"
            "- Vary which letter is correct across the quiz. Left to itself the model "
            "puts the right answer at B nearly every time, which a student can game "
            "without knowing anything.\n"
            "- Base every question and every option strictly on the excerpts. Never "
            "invent a fact that is not in them. If the excerpts do not support four "
            "distinct plausible options, ask a simpler question that they do support.\n\n"
            "Format each question exactly as:\n\n"
            "<question>\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: <letter>\n\n"
            f"Course excerpts:\n{context}"
        )
        return shuffle_quiz_answers(quiz_llm.invoke(prompt).content)

    def recall_sources() -> str:
        """What was cited earlier in this conversation — exact ids and timestamps.

        No retrieval and no LLM call: this reads the log of what the tools already
        returned. That is the point. Re-searching for "the video you mentioned earlier"
        finds whatever ranks best today, which is not necessarily what was actually
        shown then.
        """
        return sources.render()

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

        # A full listing of all 32 days is a table of contents — nothing there is worth
        # citing, and 32 citations would bury the answer.
        #
        # A *filtered* listing is different. "Where are the labs for week 7?" routes
        # here, and the answer named w7d1, w7d3 and w7d4 with no sources at all, so the
        # student was told where to look and given nothing to click. Below the cutoff,
        # each listed day contributes its opening recording, which is a real link to the
        # start of that lesson.
        if len(ids) <= LESSON_INDEX_CITATION_LIMIT:
            for lesson_id in ids:
                recordings = lessons[lesson_id].get("recordings", [])
                if not recordings:
                    continue
                first = recordings[0]
                collector.add({
                    "source_type": "video",
                    "lesson_id": lesson_id,
                    "loom_id": first.get("loom_id", ""),
                    # build_citation reads `lesson_title`, not `title` — lessons.json
                    # calls the same field `title`, and passing it through under that
                    # name produced labels like "w7d1 ·  · 0:00".
                    "lesson_title": first.get("title", ""),
                    # 0, not the middle of the lesson: this tool knows which DAY matches,
                    # never which minute. find_timestamp is the one that knows minutes.
                    "start_seconds": 0,
                })

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
            func=recall_sources,
            name="recall_sources",
            description=(
                "Look up what you cited EARLIER IN THIS CONVERSATION, with the exact "
                "lesson ids and timestamps. Use this whenever the student refers back "
                "to a previous answer rather than asking something new — 'that "
                "timestamp you gave me', 'the video from before', 'which lesson was "
                "that again', 'open the second one'. Do NOT search the course again "
                "for these: search returns what ranks best now, which may not be what "
                "was actually shown earlier."
            ),
        ),
        StructuredTool.from_function(
            func=find_notebooks,
            name="find_notebooks",
            description=(
                "Find WHICH COURSE NOTEBOOKS cover a topic, and link to them. Use this "
                "whenever the student asks for a notebook, a demo file, the code, or "
                "where to practise something — 'which notebook covers RAG', 'where is "
                "the code for embeddings', 'send me the notebooks on pandas'. Returns "
                "notebook paths, not recordings and not timestamps."
            ),
            args_schema=NotebookInput,
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
