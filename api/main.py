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
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
# `src` so the agent imports resolve the same way they do for Streamlit and the eval
# suite; this directory so `sessions` is importable whether uvicorn is pointed at
# `api.main` or the file itself.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class AskResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[dict]
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

    try:
        response = copilot.ask(req.question)
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

    return AskResponse(
        session_id=session_id,
        answer=response["answer"],
        citations=response["citations"],
        elapsed_seconds=round(elapsed, 2),
        rehydrated=rebuilt,
    )


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
