# The API branch

Branch: `spike/react-frontend` (the name is historical; the React frontend it once held
is gone, and the frontend is now built in Lovable against the API in `api/`).

`main` still holds the Streamlit app, which stays deployed as the fallback until the
API-backed frontend passes the same evaluation.

## What is here

```text
api/
  main.py       FastAPI under /api: session, ask, ask/stream (SSE), lessons, notes
                (md + pdf), syllabus.pdf, scope, quiz, reset, evict, health
  sessions.py   ConversationState, rehydrate(), SessionStore ABC, InMemorySessionStore
  course.py     lessons.json + summaries/ as plain data for the API
  openapi.json  the contract the frontend is generated from — regenerate after any change
src/pdf.py      study-notes PDF, shared by the API and the Streamlit download button
render.yaml     Render blueprint (free plan) for the API
LOVABLE-BRIEF.md  what to tell Lovable
```

Run it:

```bash
PYTHONPATH=src .venv/bin/uvicorn api.main:app --reload --port 8000
# docs: http://127.0.0.1:8000/docs
```

## Why the session layer exists

The Streamlit app keeps one `Copilot` per `st.session_state`, so a conversation lives
inside one Python process and a second replica is impossible. `Copilot` cannot be
serialised (it owns an OpenAI client and a LangChain executor), so persistence means
storing the conversation as JSON (`ConversationState`) and rebuilding a `Copilot` from
it (`rehydrate()`).

Proven on 12 August and re-checked on 18 September after rebasing on `main`: ask "What
is an embedding?", `POST /api/session/{id}/evict`, ask "And where was it covered?" — the
follow-up resolves "it" correctly and comes back `rehydrated: true`.

## What the rebase on main (18 September) brought in

- `config.py`: timeouts, retries, token caps and `stream_usage` on every model client.
- `CopilotError`: a failed turn returns HTTP 503/504/502 with
  `{"message": <student-safe>, "kind": <rate_limit|timeout|connection|auth|unknown>}`,
  never the raw exception. The real cause is in the server log with a request id.
- `turnlog`: every `/api/ask` writes tokens, cost and latency to `logs/turns.sqlite`,
  under user `anonymous` until the login step lands.
- `/api/ask/stream` (21 September): the same turn as server-sent events — `session`,
  `tool`, `token`…, `done` (or `error`). First token about 2 s in; `done` carries the
  exact object `/api/ask` returns. `Copilot.ask_stream()` in `src/agent.py` drives it
  through LangChain's `astream_events`; `ask()` and `ask_stream()` share the usage
  bookkeeping and refusal handling in `_finish()`.

## What is deliberately not here yet

In the order they will be done:

1. **Auth.** Supabase (Google sign-in). The API will verify the Supabase JWT on every
   route and reject users not on the allowlist. Until then the session id is a bearer
   capability: anyone holding it can read that conversation.
2. **Persistence across restarts.** `InMemorySessionStore` is the same lifetime Streamlit
   gave us. A Supabase Postgres implementation of `SessionStore` replaces it; the
   interface is already there.
