"""HTTP surface for the Copilot, so a React frontend can talk to it.

Deliberately thin. `Copilot.ask()` already returns the frozen `{answer, citations}` shape
and `build_citation` already computes the label and the URL, so there is nothing for this
layer to decide about presentation — the same reason the Streamlit UI never had to know
about Loom's `?t=` quirk applies to a React one.

What this layer DOES own is the session, which Streamlit used to own implicitly. See
`sessions.py`; that is where the real work of the spike is.

Run it:

    PYTHONPATH=src .venv/bin/uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
# `src` so the agent imports resolve the same way they do for Streamlit and the eval
# suite; this directory so `sessions` is importable whether uvicorn is pointed at
# `api.main` or the file itself.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import course  # noqa: E402
import pdf  # noqa: E402
from retrieval import search_with_scores  # noqa: E402
from schemas import SOURCE_NOTEBOOK, build_citation  # noqa: E402
from sessions import InMemorySessionStore, Turn  # noqa: E402

app = FastAPI(title="Ironhack AI Course Copilot API", version="0.1.0-spike")

# The dev frontend runs on Vite's default port. Kept explicit rather than "*" so that
# turning this into something deployable is a config change, not a security review.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = InMemorySessionStore()
router = APIRouter()


class AskRequest(BaseModel):
    """`language` is "auto", "en" or "es".

    Auto is the default and is handled by the system prompt, which answers in whatever
    language the student wrote in. An explicit choice appends an instruction to the
    question sent to the agent, leaving the question shown in the transcript unchanged —
    same approach the Streamlit app takes, so both frontends behave identically.
    """

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    language: str = "auto"


# How many notebook suggestions to attach to an answer that cited only lectures.
RELATED_NOTEBOOKS = 3


def related_notebooks(question: str, cited: list[dict], scope) -> list[dict]:
    """Notebooks worth offering next to an answer that only cited recordings.

    The agent calls one tool per turn by design, so a concept question routes to
    `search_course_material` and comes back with lectures only — correct for the answer,
    unhelpful for a student who then wants the code. This is a second retrieval filtered
    to notebooks, about 250ms and no model call, and it is kept clearly separate from the
    citations: these did not ground the answer, they are related material.

    Skipped when the answer already cites notebooks, and when nothing clears the scope's
    own relevance cutoff — 1.0 normally, 1.15 when a filter is active, the same numbers
    the tools use. An irrelevant notebook is worse than none.
    """
    if any(c.get("source_type") == SOURCE_NOTEBOOK for c in cited):
        return []

    try:
        hits = search_with_scores(
            question,
            k=RELATED_NOTEBOOKS,
            source_type=SOURCE_NOTEBOOK,
            lesson_id=scope.lesson_id or None,
            week=scope.week,
        )
    except Exception:  # noqa: BLE001 — a suggestion failing must not fail the answer
        return []

    out, seen = [], set()
    for doc, distance in hits:
        if distance > scope.cutoff():
            continue
        citation = build_citation(doc.metadata)
        if citation["url"] in seen:
            continue
        seen.add(citation["url"])
        out.append(citation)
    return out


class ScopeRequest(BaseModel):
    """Empty body clears the scope, which is how the UI turns the filter off."""

    lesson_id: str | None = None
    week: int | None = None


class QuizRequest(BaseModel):
    """`week` and `lesson_id` scope this quiz only — they do not touch the conversation.

    A student quizzing themselves on week 3 has not said anything about what their next
    question should search, so the two are kept apart.
    """

    topic: str = Field(min_length=1, max_length=200)
    num_questions: int = Field(default=3, ge=1, le=10)
    week: int | None = None
    lesson_id: str | None = None


class AskResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[dict]
    related_notebooks: list[dict] = []
    tools_used: list[str] = []
    elapsed_seconds: float
    rehydrated: bool = False


@router.get("/health")
def health() -> dict:
    return {"ok": True, **store.stats()}


@router.post("/session")
def new_session() -> dict:
    return {"session_id": store.create()}


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """One turn. Creates a session if the client did not supply one.

    `rehydrated` is in the response on purpose: it is how the frontend (and we, during
    the spike) can see when an answer came from a Copilot rebuilt from stored state
    rather than one that was already live. That flag is the experiment.
    """
    session_id = req.session_id or store.create()

    # A rebuild only counts as one if there was a conversation to rebuild. A brand new
    # session also has no live Copilot, and reporting that as a rehydration would make
    # the experiment look like it passed on every first turn.
    rebuilt = store.was_rebuilt_on_next_get(session_id)

    found = store.get(session_id)
    if found is None:
        # An expired or unknown id. Start a fresh session rather than 404ing, so a
        # student who left a tab open overnight gets a working page, not an error.
        session_id = store.create()
        found = store.get(session_id)
        rebuilt = False

    copilot, _state = found
    started = time.perf_counter()

    asked = req.question
    if req.language == "en":
        asked = f"{req.question}\n\nAnswer in English."
    elif req.language == "es":
        asked = f"{req.question}\n\nResponde en español."

    try:
        response = copilot.ask(asked)
    except Exception as exc:  # noqa: BLE001 — surface the failure, do not swallow it
        raise HTTPException(status_code=502, detail=f"copilot failed: {exc}") from exc

    elapsed = time.perf_counter() - started

    store.record(
        session_id,
        Turn(
            question=req.question,
            answer=response["answer"],
            citations=response["citations"],
        ),
    )

    # A refusal must never carry sources, related or otherwise.
    suggestions = (
        [] if not response["citations"]
        else related_notebooks(req.question, response["citations"], copilot.scope)
    )

    return AskResponse(
        session_id=session_id,
        answer=response["answer"],
        citations=response["citations"],
        related_notebooks=suggestions,
        elapsed_seconds=round(elapsed, 2),
        rehydrated=rebuilt,
    )


@router.get("/lessons")
def get_lessons() -> dict:
    """The course calendar. Static, cheap, safe to call on page load."""
    return {"lessons": course.lessons(), "weeks": course.weeks()}


@router.get("/lessons/{lesson_id}/notes")
def get_notes(lesson_id: str) -> dict:
    """Study notes for one lesson, as markdown.

    Markdown rather than HTML because the frontend should own presentation — the same
    reason `build_citation` hands over a label and a URL rather than a rendered link.
    """
    md = course.notes_markdown(lesson_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"no study notes for {lesson_id}")
    return {"lesson_id": lesson_id, "markdown": md}


@router.get("/lessons/{lesson_id}/notes.pdf")
def get_notes_pdf(lesson_id: str) -> Response:
    """The same PDF the Streamlit download button produces, from the same code.

    `src/pdf.py` is shared rather than reimplemented — two renderers would drift and
    students would get different documents depending on which frontend they used.
    """
    md = course.notes_markdown(lesson_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"no study notes for {lesson_id}")

    title = next((l["title"] for l in course.lessons() if l["lesson_id"] == lesson_id), "")
    body = pdf.study_notes_to_pdf(md, lesson_id, title)

    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="study-notes-{lesson_id}.pdf"'},
    )


@router.get("/syllabus.pdf")
def get_syllabus_pdf() -> Response:
    """The pre-built course syllabus. Static file, no rendering."""
    body = pdf.syllabus_pdf_bytes()
    if body is None:
        raise HTTPException(status_code=404, detail="syllabus PDF has not been generated")
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ironhack-ai-syllabus.pdf"'},
    )


@router.post("/session/{session_id}/scope")
def set_scope(session_id: str, req: ScopeRequest) -> dict:
    """Narrow the search to a lesson or a week for the rest of the conversation.

    Set on the retrieval side rather than worded into the question — see SearchScope.
    A scoped refusal says "not in THIS lesson", which is a different fact from "not in
    the course", and the frontend should show the filter that caused it.
    """
    found = store.get(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown session")
    copilot, _state = found

    if req.lesson_id is None and req.week is None:
        copilot.scope.clear()
    else:
        copilot.scope.set(lesson_id=req.lesson_id or "", week=req.week)

    return {
        "active": copilot.scope.active,
        "label": copilot.scope.label() if copilot.scope.active else "",
        "lesson_id": copilot.scope.lesson_id,
        "week": copilot.scope.week,
    }


@router.post("/session/{session_id}/quiz")
def quiz(session_id: str, req: QuizRequest) -> dict:
    """Generate a scored quiz on a topic, honouring the session's scope.

    Calls the tool directly rather than asking the agent to pick it. The agent route
    works but costs an extra model call to decide something the button already decided.
    """
    found = store.get(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown session")
    copilot, _state = found

    tool = next((t for t in copilot.executor.tools if t.name == "generate_quiz"), None)
    if tool is None:
        raise HTTPException(status_code=500, detail="generate_quiz tool is not registered")

    # The tools read the scope off the Copilot, so a per-quiz filter means swapping it for
    # the duration of the call and putting the conversation's own scope back afterwards —
    # including when the tool raises.
    previous = (copilot.scope.lesson_id, copilot.scope.week)
    scoped = req.week is not None or bool(req.lesson_id)
    if scoped:
        copilot.scope.set(lesson_id=req.lesson_id or "", week=req.week)

    # Read the label while the quiz scope is still applied — the finally below puts the
    # conversation's own scope back, and by then this would describe the wrong thing.
    label = copilot.scope.label() if scoped else ""

    try:
        markdown = tool.func(topic=req.topic, num_questions=req.num_questions)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"quiz failed: {exc}") from exc
    finally:
        copilot.scope.set(lesson_id=previous[0], week=previous[1])

    return {"topic": req.topic, "markdown": markdown, "scope": label}


@router.post("/session/{session_id}/reset")
def reset(session_id: str) -> dict:
    if not store.reset(session_id):
        raise HTTPException(status_code=404, detail="unknown session")
    return {"ok": True}


@router.post("/session/{session_id}/evict")
def evict(session_id: str) -> dict:
    """Drop the live Copilot, keep the conversation.

    The most important endpoint here. Call it between two turns and the next answer has
    to come from a Copilot rebuilt out of stored state — which is exactly what happens
    when a follow-up lands on a replica that never saw the first question. If the
    follow-up still resolves, horizontal scaling is unblocked.
    """
    evicted = store.evict_live(session_id)
    return {"evicted": evicted, **store.stats()}


@router.get("/session/{session_id}")
def get_session(session_id: str) -> dict:
    found = store.get(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown session")
    _copilot, state = found
    return state.to_dict()


# Both prefixes on purpose. The Vite dev server proxies /api to this process, and the
# built bundle below is served from this process directly — same fetch code either way.
app.include_router(router)
app.include_router(router, prefix="/api")

# Serve the built frontend if it exists, so the whole thing is one process on one port.
# Mounted last: a mount at "/" would otherwise shadow every route above it.
# Build it with `npm run build --prefix web`.
DIST = ROOT / "web" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="web")
