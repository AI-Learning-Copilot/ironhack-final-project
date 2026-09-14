"""Runtime settings, read once from the environment.

Every model client in the project takes its model name, timeout and retry policy from
here, so the numbers live in one place and can be changed per deployment without a
code edit. Defaults are the values the app shipped with; only the safety limits are new.

    OPENAI_MODEL              chat model                       gpt-4o-mini
    OPENAI_TIMEOUT_SECONDS    per-request timeout              30
    OPENAI_MAX_RETRIES        retries on 429/5xx               3
    OPENAI_MAX_TOKENS         completion cap for answers       1200
    OPENAI_QUIZ_MAX_TOKENS    completion cap for quizzes       1500
    LOG_LEVEL                 python logging level             INFO

The OpenAI default timeout is 600 seconds. Without a cap, one hung request holds a
student's session for ten minutes, which is indistinguishable from the app being down.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

# One place, once. agent.py and embeddings.py used to each call load_dotenv at import.
load_dotenv(REPO_ROOT / ".env")

# chromadb 0.5.3 phones home unless told not to. Nothing in this project needs it.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "%s=%r is not an integer; using %d", name, raw, default
        )
        return default


CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TIMEOUT_SECONDS = _int("OPENAI_TIMEOUT_SECONDS", 30)
MAX_RETRIES = _int("OPENAI_MAX_RETRIES", 3)
MAX_TOKENS = _int("OPENAI_MAX_TOKENS", 1200)
QUIZ_MAX_TOKENS = _int("OPENAI_QUIZ_MAX_TOKENS", 1500)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def llm_kwargs(**overrides) -> dict:
    """Keyword arguments shared by every `ChatOpenAI` in the project.

    `stream_usage=True` matters for cost tracking: the agent streams its completions,
    and a streamed response carries no token counts unless the request asks for them.
    Without it, `get_openai_callback` and `usage_metadata` both report zero.
    """
    kwargs = {
        "model": CHAT_MODEL,
        "temperature": 0,
        "timeout": TIMEOUT_SECONDS,
        "max_retries": MAX_RETRIES,
        "max_tokens": MAX_TOKENS,
        "stream_usage": True,
    }
    kwargs.update(overrides)
    return kwargs


def configure_logging() -> None:
    """Idempotent. Streamlit reruns the script, so guard against adding handlers twice."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
