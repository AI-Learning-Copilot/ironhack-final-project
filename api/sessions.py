"""Conversation state, kept outside the Streamlit process.

This module is the whole point of the spike. The Streamlit app keeps one `Copilot` per
`st.session_state`, which means a conversation lives in the memory of one Python process.
That is why we cannot run a second replica: a student's follow-up can land on the machine
that never saw their first question. It is item one on the future-work slide.

A `Copilot` cannot be serialised — it holds an OpenAI client, a LangChain executor and a
summariser. So "persist the session" cannot mean "pickle the Copilot". It has to mean:

    persist the CONVERSATION, and rebuild a Copilot from it on demand.

`ConversationState` below is that conversation, and it is deliberately nothing but JSON:
a list of turns and the `SourceLog` entries. Both are already plain data — `SourceLog`
was built that way on purpose, to survive summarisation, and it turns out that is also
exactly what makes it survive a process boundary.

`rehydrate()` is the part worth testing. If a Copilot rebuilt from stored state answers a
follow-up correctly, then horizontal scaling is unblocked and the future-work item is an
afternoon rather than a research project.

The in-memory store here is not the destination. It is the same lifetime Streamlit already
gives us, behind an interface a Redis or Postgres implementation can satisfy without the
API layer noticing.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agent import Copilot


# A session with no traffic for this long is dropped. Streamlit's own sessions die with
# the browser connection, so this is not a regression — it is the first time the lifetime
# has been an explicit number rather than an accident of the framework.
SESSION_TTL_SECONDS = 60 * 60

# Each live Copilot measured at ~2.9 MB. The cap is what stops a burst of visitors
# exhausting the container before the TTL has a chance to sweep anything.
MAX_LIVE_SESSIONS = 200


@dataclass
class Turn:
    """One exchange. `citations` is what the student was actually shown."""

    question: str
    answer: str
    citations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"question": self.question, "answer": self.answer, "citations": self.citations}

    @classmethod
    def from_dict(cls, raw: dict) -> "Turn":
        return cls(
            question=raw.get("question", ""),
            answer=raw.get("answer", ""),
            citations=raw.get("citations", []),
        )


@dataclass
class ConversationState:
    """Everything needed to rebuild a conversation. JSON all the way down."""

    session_id: str
    turns: list[Turn] = field(default_factory=list)
    source_log: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turns": [t.to_dict() for t in self.turns],
            "source_log": self.source_log,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ConversationState":
        return cls(
            session_id=raw["session_id"],
            turns=[Turn.from_dict(t) for t in raw.get("turns", [])],
            source_log=raw.get("source_log", []),
            created_at=raw.get("created_at", time.time()),
            last_seen=raw.get("last_seen", time.time()),
        )


def rehydrate(state: ConversationState) -> Copilot:
    """Build a Copilot that believes it has already had this conversation.

    Two things have to be restored, and they are restored differently on purpose.

    The LangChain memory is replayed turn by turn through `save_context`, which is the
    same path a live conversation takes. That matters: it means the summariser compresses
    the replayed history exactly as it would have compressed it live, so a rebuilt session
    behaves like the original rather than like a session with a suspiciously perfect
    transcript.

    The `SourceLog` is assigned directly, because it is the guarantee rather than the
    best effort. Replaying it through the model would be the one way to lose the digits
    it exists to protect.
    """
    copilot = Copilot()

    for turn in state.turns:
        copilot.memory.save_context({"input": turn.question}, {"output": turn.answer})

    copilot.sources.turns = list(state.source_log)
    return copilot


class SessionStore(ABC):
    """The seam. Swap the implementation, not the API layer.

    A Redis or Postgres implementation stores `ConversationState.to_dict()` and calls
    `rehydrate()` on load. Nothing above this interface changes.
    """

    @abstractmethod
    def create(self) -> str: ...

    @abstractmethod
    def get(self, session_id: str) -> tuple[Copilot, ConversationState] | None: ...

    @abstractmethod
    def record(self, session_id: str, turn: Turn) -> None: ...

    @abstractmethod
    def reset(self, session_id: str) -> bool: ...

    @abstractmethod
    def delete(self, session_id: str) -> bool: ...

    @abstractmethod
    def stats(self) -> dict: ...


class InMemorySessionStore(SessionStore):
    """One process, live Copilots, swept on a TTL.

    Functionally equivalent to what Streamlit gives us today, with two differences that
    are the reason the spike exists: the session id is explicit rather than implied by a
    websocket, and the state behind it is serialisable. Neither is worth anything on a
    single replica. Both are prerequisites for a second one.
    """

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._live: dict[str, Copilot] = {}

    def create(self) -> str:
        self._sweep()
        session_id = uuid.uuid4().hex
        self._states[session_id] = ConversationState(session_id=session_id)
        return session_id

    def get(self, session_id: str) -> tuple[Copilot, ConversationState] | None:
        self._sweep()
        state = self._states.get(session_id)
        if state is None:
            return None

        state.last_seen = time.time()

        # The interesting branch. A cache miss here is what a second replica would hit on
        # every request, so exercising it locally — by evicting a live Copilot and asking
        # a follow-up — is how we find out whether rehydration actually works.
        copilot = self._live.get(session_id)
        if copilot is None:
            copilot = rehydrate(state)
            self._live[session_id] = copilot

        return copilot, state

    def record(self, session_id: str, turn: Turn) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        state.turns.append(turn)
        state.last_seen = time.time()

        copilot = self._live.get(session_id)
        if copilot is not None:
            # Keep the stored log in step with the live one rather than rebuilding it
            # from the turns: the live SourceLog has already deduplicated and capped.
            state.source_log = list(copilot.sources.turns)

    def reset(self, session_id: str) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        state.turns.clear()
        state.source_log.clear()
        self._live.pop(session_id, None)
        return True

    def delete(self, session_id: str) -> bool:
        self._live.pop(session_id, None)
        return self._states.pop(session_id, None) is not None

    def was_rebuilt_on_next_get(self, session_id: str) -> bool:
        """Would the next `get` have to rebuild a Copilot from stored turns?

        True only when there is a conversation to rebuild AND nothing live holding it —
        which is precisely the condition a follow-up hits on a cold replica.
        """
        state = self._states.get(session_id)
        return bool(state and state.turns and session_id not in self._live)

    def evict_live(self, session_id: str) -> bool:
        """Drop the live Copilot but keep the state — simulates landing on a cold replica.

        Test hook, and the single most useful endpoint in the spike.
        """
        return self._live.pop(session_id, None) is not None

    def stats(self) -> dict:
        return {
            "sessions": len(self._states),
            "live_copilots": len(self._live),
            "ttl_seconds": SESSION_TTL_SECONDS,
            "max_live": MAX_LIVE_SESSIONS,
        }

    def _sweep(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        for session_id, state in list(self._states.items()):
            if state.last_seen < cutoff:
                self.delete(session_id)

        # Over the cap, drop the live objects for the least recently seen sessions but
        # keep their state. The conversation survives; only the memory footprint goes.
        if len(self._live) > MAX_LIVE_SESSIONS:
            by_age = sorted(self._live, key=lambda sid: self._states[sid].last_seen
                            if sid in self._states else 0)
            for session_id in by_age[: len(self._live) - MAX_LIVE_SESSIONS]:
                self._live.pop(session_id, None)
