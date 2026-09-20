"""HTTP surface for the Copilot. The frontend (built in Lovable) talks to this.

Deliberately thin. `Copilot.ask()` already returns the frozen `{answer, citations}` shape
and `build_citation` already computes the label and the URL, so there is nothing for this
layer to decide about presentation — the same reason the Streamlit UI never had to know
about Loom's `?t=` quirk applies to any other one.

What this layer DOES own is the session, which Streamlit used to own implicitly. See
`sessions.py`.

Run it:

    PYTHONPATH=src .venv/bin/uvicorn api.main:app --reload --port 8000

`api/openapi.json` is the contract the frontend is generated from. Regenerate it after
any change to a route or a model:

    PYTHONPATH=src .venv/bin/python -c "import json, api.main as m; \\
        print(json.dumps(m.app.openapi(), indent=2))" > api/openapi.json
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import Response
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
import supa  # noqa: E402
import turnlog  # noqa: E402
from agent import CopilotError  # noqa: E402
from auth import User, current_user  # noqa: E402
from config import configure_logging  # noqa: E402
from retrieval import search_with_scores  # noqa: E402
from schemas import SOURCE_NOTEBOOK, build_citation  # noqa: E402
from sessions import InMemorySessionStore, SupabaseSessionStore, Turn  # noqa: E402

configure_logging()
log = logging.getLogger("api")

app = FastAPI(title="Ironhack AI Course Copilot API", version="0.3.0")

# Which course this deployment serves; the turn log keys on it. One deployment per
# course until a client table exists.
COURSE_ID = os.getenv("COURSE_ID", "ironhack-ai-engineering")

# The HTTP status a failed turn maps to, by CopilotError.kind. 503 for the transient
# ones (the client may retry), 502 for a misconfigured upstream, 500 for the rest.
_STATUS_BY_KIND = {
    "rate_limit": 503,
    "timeout": 504,
    "connection": 503,
    "auth": 502,
}

# Any origin, and credentials off.
#
# A hosted preview (Lovable, StackBlitz, a deployed frontend) calls this from an origin
# we cannot know in advance, and a browser blocks the request before it arrives if the
# origin is not allowed. An allowlist would mean editing this file every time a frontend
# moves.
#
# Safe because nothing is sent automatically: no cookies, and the Supabase token travels
# in an Authorization header the frontend sets by hand, which a third-party page cannot
# make a browser attach. So "*" plus bearer tokens is fine. Once the Lovable origin is
# known, set ALLOWED_ORIGINS to it anyway; it costs nothing and narrows the surface.
#
# allow_credentials must stay False: the CORS spec forbids "*" together with credentials,
# and browsers reject the combination outright rather than falling back.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Postgres-backed sessions when Supabase is configured, in-memory otherwise. Same
# interface either way; `stats()` says which one is running.
if supa.configured():
    store = SupabaseSessionStore(course=COURSE_ID)
    log.info("sessions: supabase")
else:
    store = InMemorySessionStore()
    log.info("sessions: in-memory (SUPABASE_URL not set)")

router = APIRouter()


def _record(user: User, session_id: str | None, question: str, usage: dict) -> None:
    """Both usage sinks: the local SQLite log (ephemeral on Render) and Supabase."""
    turnlog.record(user=user.email or user.id, course=COURSE_ID, question=question, usage=usage)
    supa.record_turn(
        user_id=user.id, user_email=user.email, course=COURSE_ID,
        session_id=session_id, question=question, usage=usage,
    )


def _owned(session_id: str, user: User):
    """The session, or 404 if unknown, or 403 if it belongs to someone else.

    Anonymous sessions (created before the frontend sent tokens) stay reachable by
    anyone holding the id, which is what they were before. A session created by a
    signed-in user is theirs alone.
    """
    found = store.get(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"message": "unknown session", "kind": "session"})
    _copilot, state = found
    if state.user_id != "anonymous" and state.user_id != user.id:
        raise HTTPException(status_code=403, detail={"message": "not your session", "kind": "forbidden"})
    return found


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

# How many distinct sources an answer shows before the rest are dropped. Five citations
# is not five leads: it is usually one recording quoted five times, and the student reads
# the first one.
MAX_CITATIONS = 4


def condense_citations(citations: list[dict]) -> list[dict]:
    """One entry per recording or notebook, keeping the best-ranked position first.

    `build_response` deduplicates on URL, and a URL carries the timestamp — so five
    chunks from one lecture become five citations pointing at the same video, minutes
    apart. Ranked by chunk score they are all near the top, which pushes the genuinely
    different source off the end of the list. That is the "many videos and the first one
    is not the best" problem: the list was never five sources, it was one source five
    times.

    Grouping by recording keeps the order the reranker produced — the first timestamp
    seen for a recording is its best-scoring one, so it stays as the link. The remaining
    timestamps are not thrown away; they move to `also_at` for a UI to offer underneath,
    because "it comes up again at 24:10" is useful once it is not competing for the slot.
    """
    grouped: dict[str, dict] = {}

    for citation in citations:
        # loom_id for a video, path for a notebook — the URL minus the timestamp.
        key = citation["url"].split("?")[0]
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {**citation, "also_at": []}
            continue
        existing["also_at"].append(
            {
                "label": citation["label"],
                "url": citation["url"],
                "start_seconds": citation.get("start_seconds", -1),
            }
        )

    return list(grouped.values())[:MAX_CITATIONS]


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
def new_session(user: User = Depends(current_user)) -> dict:
    return {"session_id": store.create(user_id=user.id)}


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user: User = Depends(current_user)) -> AskResponse:
    """One turn. Creates a session if the client did not supply one.

    `rehydrated` is in the response on purpose: it is how the frontend (and we, during
    the spike) can see when an answer came from a Copilot rebuilt from stored state
    rather than one that was already live. That flag is the experiment.
    """
    session_id = req.session_id or store.create(user_id=user.id)

    # A rebuild only counts as one if there was a conversation to rebuild. A brand new
    # session also has no live Copilot, and reporting that as a rehydration would make
    # the experiment look like it passed on every first turn.
    rebuilt = store.was_rebuilt_on_next_get(session_id)

    found = store.get(session_id)
    if found is None:
        # An expired or unknown id. Start a fresh session rather than 404ing, so a
        # student who left a tab open overnight gets a working page, not an error.
        session_id = store.create(user_id=user.id)
        found = store.get(session_id)
        rebuilt = False
    elif found[1].user_id != "anonymous" and found[1].user_id != user.id:
        raise HTTPException(status_code=403, detail={"message": "not your session", "kind": "forbidden"})

    copilot, _state = found
    started = time.perf_counter()

    asked = req.question
    if req.language == "en":
        asked = f"{req.question}\n\nAnswer in English."
    elif req.language == "es":
        asked = f"{req.question}\n\nResponde en español."

    try:
        response = copilot.ask(asked)
    except CopilotError as exc:
        # ask() has already logged the real cause with a request id. The client gets
        # the student-safe message and a status it can branch on; never the raw error.
        _record(user, session_id, req.question, copilot.last_usage)
        raise HTTPException(
            status_code=_STATUS_BY_KIND.get(exc.kind, 500),
            detail={"message": exc.user_message, "kind": exc.kind},
        ) from exc

    elapsed = time.perf_counter() - started

    _record(user, session_id, req.question, copilot.last_usage)

    store.record(
        session_id,
        Turn(
            question=req.question,
            answer=response["answer"],
            citations=response["citations"],
        ),
    )

    citations = condense_citations(response["citations"])

    # A refusal must never carry sources, related or otherwise.
    suggestions = (
        [] if not citations
        else related_notebooks(req.question, citations, copilot.scope)
    )

    return AskResponse(
        session_id=session_id,
        answer=response["answer"],
        citations=citations,
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
def set_scope(session_id: str, req: ScopeRequest, user: User = Depends(current_user)) -> dict:
    """Narrow the search to a lesson or a week for the rest of the conversation.

    Set on the retrieval side rather than worded into the question — see SearchScope.
    A scoped refusal says "not in THIS lesson", which is a different fact from "not in
    the course", and the frontend should show the filter that caused it.
    """
    copilot, _state = _owned(session_id, user)

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
def quiz(session_id: str, req: QuizRequest, user: User = Depends(current_user)) -> dict:
    """Generate a scored quiz on a topic, honouring the session's scope.

    Calls the tool directly rather than asking the agent to pick it. The agent route
    works but costs an extra model call to decide something the button already decided.
    """
    copilot, _state = _owned(session_id, user)

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
    except Exception as exc:  # noqa: BLE001 — the tool calls OpenAI directly, not via ask()
        log.exception("quiz failed for session %s", session_id)
        raise HTTPException(
            status_code=503,
            detail={"message": "The quiz could not be generated. Try again in a moment.",
                    "kind": "quiz"},
        ) from exc
    finally:
        copilot.scope.set(lesson_id=previous[0], week=previous[1])

    return {"topic": req.topic, "markdown": markdown, "scope": label}


@router.post("/session/{session_id}/reset")
def reset(session_id: str, user: User = Depends(current_user)) -> dict:
    _owned(session_id, user)
    store.reset(session_id)
    return {"ok": True}


@router.post("/session/{session_id}/evict")
def evict(session_id: str, user: User = Depends(current_user)) -> dict:
    """Drop the live Copilot, keep the conversation.

    The most important endpoint here. Call it between two turns and the next answer has
    to come from a Copilot rebuilt out of stored state — which is exactly what happens
    when a follow-up lands on a replica that never saw the first question. If the
    follow-up still resolves, horizontal scaling is unblocked.
    """
    _owned(session_id, user)
    evicted = store.evict_live(session_id)
    return {"evicted": evicted, **store.stats()}


@router.get("/session/{session_id}")
def get_session(session_id: str, user: User = Depends(current_user)) -> dict:
    _copilot, state = _owned(session_id, user)
    return state.to_dict()


# Everything lives under /api. The frontend is a separate deployment (Lovable), so this
# process serves no HTML; `/` just says what it is.
app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": app.title, "version": app.version, "docs": "/docs", "api": "/api"}
