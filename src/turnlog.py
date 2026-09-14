"""Per-turn usage log: who asked, what it cost, how long it took.

One SQLite table, one row per turn, written by the app after every answer. This is the
raw material for two things the project did not have: a usage report per client, and a
budget based on measured questions-per-student instead of a guess.

    from turnlog import record, summary
    record(user="ana@client.com", course="ironhack-ai-eng", question=q, usage=copilot.last_usage)
    summary()  # -> [{"user": ..., "turns": 12, "cost_usd": 0.01, ...}, ...]

The database lives in logs/turns.sqlite (gitignored — add `logs/` to .gitignore if it is
not there yet). Deleting the file is safe; it is recreated on the next turn.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "logs" / "turns.sqlite"

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turn (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL    NOT NULL,
    user              TEXT    NOT NULL,
    course            TEXT    NOT NULL,
    request_id        TEXT,
    question_chars    INTEGER,
    tools             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    llm_calls         INTEGER,
    cost_usd          REAL,
    latency_s         REAL,
    error             TEXT
);
CREATE INDEX IF NOT EXISTS turn_user_ts ON turn(user, ts);
"""


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.executescript(_SCHEMA)
    return conn


def record(
    *,
    user: str,
    course: str,
    question: str,
    usage: dict,
    path: Path = DB_PATH,
) -> None:
    """Append one turn. Never raises: a logging failure must not break an answer."""
    try:
        with _connect(path) as conn:
            conn.execute(
                """INSERT INTO turn (ts, user, course, request_id, question_chars, tools,
                                     prompt_tokens, completion_tokens, llm_calls,
                                     cost_usd, latency_s, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.time(),
                    user,
                    course,
                    usage.get("request_id"),
                    len(question),
                    ",".join(usage.get("tools", [])) or None,
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("llm_calls"),
                    usage.get("cost_usd"),
                    usage.get("latency_s"),
                    usage.get("error"),
                ),
            )
    except Exception:  # noqa: BLE001
        log.exception("could not record turn")


def summary(path: Path = DB_PATH, course: str | None = None) -> list[dict]:
    """Per-user totals, most active first. Empty list when nothing has been logged."""
    if not path.exists():
        return []
    where = "WHERE course = ?" if course else ""
    params = (course,) if course else ()
    with _connect(path) as conn:
        rows = conn.execute(
            f"""SELECT user,
                       COUNT(*)                         AS turns,
                       SUM(error IS NOT NULL)           AS errors,
                       ROUND(COALESCE(SUM(cost_usd),0), 4) AS cost_usd,
                       ROUND(AVG(latency_s), 2)         AS avg_latency_s,
                       MIN(ts)                          AS first_ts,
                       MAX(ts)                          AS last_ts
                FROM turn {where}
                GROUP BY user
                ORDER BY turns DESC""",
            params,
        ).fetchall()
    keys = ["user", "turns", "errors", "cost_usd", "avg_latency_s", "first_ts", "last_ts"]
    return [dict(zip(keys, row)) for row in rows]


if __name__ == "__main__":
    for row in summary():
        print(row)
