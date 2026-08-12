# Spike: React frontend on a FastAPI session layer

Branch: `spike/react-frontend`. **`main` is untouched** — the Streamlit app there still
runs exactly as it did, and it is what we present if this goes nowhere.

## Why this exists

Not to make the UI prettier. The Streamlit app keeps one `Copilot` per `st.session_state`,
so a conversation lives inside one Python process. That is why a second replica is
impossible today: a student's follow-up can land on the machine that never saw their first
question. It is item one on the future-work slide and the blocker named in the scaling
note.

A React frontend cannot talk to a Python object, so building one forces the session out of
the process. That is the real experiment. The frontend is the reason to do it, not the
point of it.

## The question, and the answer

**Can a conversation be rebuilt from stored state well enough that a follow-up still
resolves?**

Yes. Measured on 12 August:

| Step | Result |
|---|---|
| Turn 1 — "What is an embedding?" | 6.51s, cites `w4d3 · Embeddings Intro` at five timestamps |
| Evict the live Copilot, keep the conversation | `live_copilots: 0` |
| Turn 2 — "**And where was it covered?**" | 3.01s, `rehydrated=true`, resolves "it" to embeddings and returns w4d3 with the exact timestamps |

The pronoun resolved against a conversation the new `Copilot` object never had. So
persistence is not a research problem — the pieces were already in the right shape.

## Why it worked

Two design decisions made months ago, for unrelated reasons, turned out to be what made
this cheap:

- **`Copilot` never imported Streamlit.** `agent.py` has no UI coupling at all, so the
  HTTP layer is a thin wrapper over `ask()`.
- **`SourceLog` was already plain serialisable data.** It was built that way so exact
  lesson ids and timestamps would survive the summariser compressing them into prose. The
  same property makes them survive a process boundary.

`build_citation` also means the React UI computes no labels and no URLs — it renders a
Loom embed without knowing anything about Loom's `?t=` parameter, exactly as the Streamlit
UI did.

## What is here

```text
api/
  main.py       FastAPI: /ask, /session, /session/{id}/reset, /evict, /health
  sessions.py   ConversationState, rehydrate(), SessionStore ABC, InMemorySessionStore
web/
  src/App.jsx   chat, citations, Loom embeds, the cold-replica button
```

`InMemorySessionStore` is not the destination. It gives the same lifetime Streamlit already
gave us, behind an interface a Redis or Postgres implementation satisfies without the API
layer changing. `rehydrate()` is the function that would run on every request in a
multi-replica deployment.

## Run it

One process, which is the way that actually works reliably. Build the frontend once, and
FastAPI serves it alongside the API:

```bash
npm install --prefix web && npm run build --prefix web
PYTHONPATH=src .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open **http://127.0.0.1:8000**. Ask "What is an embedding?", press **Simulate a cold
replica**, then ask "And where was it covered?" — the answer comes back tagged
*rebuilt from stored state*.

For frontend work, the Vite dev server gives hot reload and proxies `/api` to port 8000:

```bash
npm run dev --prefix web     # http://127.0.0.1:5173, needs uvicorn running too
```

`vite.config.js` sets `host: true` deliberately. Vite's default binds the IPv6 loopback
only, and a browser that resolves `localhost` to 127.0.0.1 then cannot connect at all.

## What this does NOT do

Deliberately out of scope. Do not read the gaps as unknowns; they are choices.

- No streaming. Streamlit gave us a spinner for free; without one, five seconds of nothing
  feels broken. This is the first thing to add.
- No study notes, syllabus panel, quiz UI, or lesson scope filter. All exist in
  `app/app.py` and would need porting.
- No auth. The session id is a bearer capability — anyone holding it can read the
  conversation. That is the identity decision the future-work slide describes, and it has
  to be made before anything is stored for real.
- No persistence across a restart. In-memory only. The point was to prove `rehydrate()`
  works, not to choose a database.
- No styling worth the name.

## What it would take to finish

Roughly, and only if a pilot makes it worth doing:

1. Streaming responses — half a day
2. Port the remaining panels from `app/app.py` — a day or two
3. Swap `InMemorySessionStore` for Redis — a few hours, the interface is already there
4. An identity and retention decision — not an engineering task
5. Two deployments instead of one

Steps 1 and 3 are the ones that change what we can claim. The rest is porting.
