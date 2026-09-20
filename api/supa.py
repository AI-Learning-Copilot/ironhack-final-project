"""The one Supabase client the API uses, plus the usage sink.

Configuration, all from the environment:

    SUPABASE_URL                https://<ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   server-side key; bypasses row level security. Never in a browser.

Both unset means "no Supabase": sessions stay in memory and turns go only to the local
SQLite log. That keeps `uvicorn api.main:app` working on a laptop with nothing configured.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

log = logging.getLogger("api.supa")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_ROLE_KEY)


@lru_cache(maxsize=1)
def client():
    """Lazy: the import alone costs ~100 ms and a laptop run may never need it."""
    from supabase import create_client

    return create_client(SUPABASE_URL, SERVICE_ROLE_KEY)


def record_turn(
    *,
    user_id: str,
    user_email: str,
    course: str,
    session_id: str | None,
    question: str,
    usage: dict,
) -> None:
    """Insert one row into `turns`. Never raises: usage logging must not fail an answer."""
    if not configured():
        return
    try:
        client().table("turns").insert(
            {
                "user_id": user_id,
                "user_email": user_email,
                "course": course,
                "session_id": session_id,
                "request_id": usage.get("request_id"),
                "question_chars": len(question),
                "tools": ",".join(usage.get("tools", [])) or None,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "llm_calls": usage.get("llm_calls"),
                "cost_usd": usage.get("cost_usd"),
                "latency_s": usage.get("latency_s"),
                "error": usage.get("error"),
            }
        ).execute()
    except Exception:  # noqa: BLE001
        log.exception("could not record turn in Supabase")
