# Project 3 — AI Learning Copilot for the Ironhack bootcamp

**Team:** Casilda Gonzalez (CGS) · Felipe Martignon (FM)
**Team repo:** https://github.com/Casildagsf/ironhack-final-project (public)
**Live app:** https://ai-learning-copilot-ironhack-final-project.streamlit.app/
**Submission:** Thursday 13 August 2026

**Status as of 6 August: the MVP is COMPLETE and deployed**, one day ahead of the Friday
target. All six MVP criteria verified on the live app. Evaluation passes 30/30 locally and
all six behaviour classes were re-verified against the deployment (`V4`).

> **Every decision in §9 is now settled** — that section is kept as a record of what we
> chose and why, not as open questions. The stack is **Streamlit**, the repo is **public**,
> and **voice input is cut**. §5 reflects what each of us actually built.

---

## 1. What we are building

A copilot over **our own bootcamp material**. A student asks *"where was cross-validation
explained?"* and gets: the lesson, the exact minute in the Loom recording (as an embedded
player cued to that second), and the notebook cell that covers it. Plus per-lesson
summaries, and answers in the student's own language.

This beats a generic YouTube QA bot on every grading criterion in the brief: we can
actually verify accuracy (we sat through the lessons), and the education/accessibility
business case in the README is literally this product.

## 2. Corpus — already collected

| | |
|---|---|
| Loom recordings | **122** across 33 lesson days (`w1d1` → `w8d2`) |
| Total runtime | **91.4 hours** (avg 45 min) |
| Transcripts (`.vtt`) | **120** — see below for the 2 without captions |
| Metadata (`.info.json`) | 122, each with the Loom title `AI 2026.06 - w1d1 - c - Intro to AI Engineering` |
| Notebooks | 60+ in `demos_ai_eng/` (**pull latest — local copy is missing `15_Evaluation/`**) |
| Size on disk | 8.8 MB |

Lives in `data/raw/captions/` (gitignored), indexed by `data/raw/looms.txt`. Re-runnable
with `bash data/raw/fetch_captions.sh` (idempotent — skips what it already has).

### The 2 recordings without captions — resolved

Metadata came down for **all 122**. Captions came down for **120**. The two gaps are not a
download failure — Loom has no transcript for them at all (`"subtitles": []` in both
`.info.json` files, so there is nothing to retry):

| Recording | Length | Decision |
|---|---|---|
| `w3d4 - d - intro to Standup meetings` | 37 min | **Skip.** Pure process admin, no teaching content. Nobody will ask about it. |
| `w6d2 - a - Project-3 Kick-off` | 45 min | **Skip.** Homework briefing, not a teaching lesson. Decided 6 Aug (CGS + FM); task `C0` closed as WONT DO. |

**Both exclusions are deliberate scope, not a gap.** The corpus is the course's *teaching*
material: one is standup admin, the other is assignment logistics. Report the corpus as
**120 of 120 teaching recordings — complete**, never as "120 of 122, two missing".

## 3. Architecture — two decisions that drive everything

**A. Split build time from run time.** Parsing, chunking, embedding and summarising happen
**once, on a laptop**. The Chroma index is **committed to the repo**. Streamlit Community
Cloud has an ephemeral filesystem and sleeps when idle — re-embedding on boot would cost
money on every wake, lose the index on every restart, and wreck latency, which is graded.
At run time the app only *reads*.

**B. One Chroma collection, two source types.** Video and notebook chunks share one
collection with a `source_type` field. Retrieval is unified; only the *citation format*
branches. This is what makes it feel smart: one question returns both "w7d2, 14:32" and
"`14_LangChain/3_langchain-RAG.ipynb`, cell 12".

### Run-time flow — what actually shipped

**Single Streamlit app, one deploy.** No FastAPI, no React, no CORS, no API key plumbing.
An earlier draft of this plan specified FastAPI/Render + React/Vercel; that was dropped on
5 August (§9.1). What runs:

1. **Streamlit Community Cloud** hosts `app/app.py` — chat input, answer, citation list.
   Auto-redeploys on every push to `main`. `OPENAI_API_KEY` lives in app Secrets.
2. **The agent** (`src/agent.py`) — `create_openai_tools_agent` + `AgentExecutor` on
   `gpt-4o-mini`, with `ConversationSummaryBufferMemory`, capped at 4 iterations.
3. **Five tools** (`src/tools.py`): `search_course_material`, `find_timestamp`,
   `explain_concept`, `generate_quiz`, `lesson_index`.
4. **The committed Chroma index** (`index/`) — 5,248 chunks, read-only at run time.
5. **`Copilot.ask()` returns `{answer, citations}`** and nothing else. Each citation
   arrives with its `label` and `url` already built.

**The UI never computes a URL.** The agent emits the finished Loom `/embed/` link with the
`?t=<N>s` timestamp already in it, and `app.py` drops it straight into
`components.iframe()`. That is why Felipe never had to learn Loom's timestamp quirk, and
why the citation contract could be frozen before the agent existed.

*The architecture diagram for the README and slides is `F7` — Felipe's.*

### Non-obvious details that will bite us

- **Loom deep links need `?t=80s` or `?t=10m8s`, not `?t=80`.** Raw seconds are silently
  ignored. Loom's `/embed/<id>` iframe accepts the same param — so citations render as an
  inline player already cued to the moment, and the student never leaves the app.
- **Embeddings at `dimensions=512`, not the default 1536.** Actual: 5,248 chunks (5,090
  video + 158 notebook), index 66 MB. At 1536 dims it would be roughly 3× that, and GitHub
  warns at 50 MB per file. At 512 it fits and
  retrieval quality is unchanged at this corpus size.
- **VTT cues carry speaker tags** (`<v 0>text</v>`) and classroom admin chatter. Strip the
  tags in the parser.
- **`start_seconds` is scoped to its own Loom**, not to the lesson day — a day is 3–6
  separate recordings.

## 4. The contract that lets us work in parallel

**Freeze these two on day 1, before anyone writes code.** Everything else can then be
built independently and merged without conflicts.

**(a) Chunk schema** — both ingestion halves emit exactly this:

```python
{
  "text": str,
  "metadata": {
    "source_type": "video" | "notebook",
    "lesson_id":   "w7d2",
    "title":       "RAG II - Indexing",
    # video only:
    "loom_id":      "9adc63fbe9f84e93a7334a8c80c20569",
    "start_seconds": 872,
    # notebook only:
    "folder":     "14_LangChain",
    "notebook":   "3_langchain-RAG.ipynb",
    "cell_index": 12,
  }
}
```

**(b) `/ask` response** — the front end is built against this shape with a mock backend:

```json
{
  "answer": "markdown string",
  "citations": [
    {"source_type":"video","lesson_id":"w7d2","title":"RAG II - Indexing",
     "loom_id":"9adc...","start_seconds":872,"label":"14:32"},
    {"source_type":"notebook","folder":"14_LangChain",
     "notebook":"3_langchain-RAG.ipynb","cell_index":12}
  ]
}
```

## 4b. The MVP — freeze this and defend it

**The MVP is the smallest thing that satisfies the brief and is demoable end to end.**
Everything else is a bonus, and bonuses only get built once this is stable and deployed.

A student opens a URL and:

1. Asks a question in natural language
2. Gets an answer **grounded in our course material**, not the model's general knowledge
3. Sees **which lesson** it came from and an embedded Loom **cued to the exact second**
4. Asks a follow-up that only makes sense with memory ("explain that more simply")
5. …and the agent **chose between at least two tools** to do it

That's it. Five things. If those work on a public URL, the project passes.

**Explicitly NOT in the MVP** — do not start any of these until the five above are live:
notebook indexing, Study Notes, quiz, translation, lesson picker UI.

Ranked order once the MVP is up:
1. **Notebook indexing** (F1 → C3) — the dual-source citation is our differentiator
2. **Quiz tool** — cheap, and it makes agent routing obviously necessary
3. **Study Notes** — the strongest bonus in Felipe's plan
4. **Translation** — one line in the system prompt

**Voice input is CUT** (decided 6 Aug, CGS + FM). The README's objective 2 asks for speech
recognition; we are shipping a text-only copilot and saying so plainly in our own README
rather than bolting on a mic we cannot test properly before the deadline.

### The calendar — what happened, and what is left

**The MVP landed on 6 August, a day early**, and the bonuses landed with it. Everything
below Thursday is what remains.

| | |
|---|---|
| **Wed 5 Aug** | `S1`–`S5` contracts + repo + pinned env · `C1` VTT parser · `C1c` dev index · `C2` `lessons.json` · `C1b` name scrubbing |
| **Thu 6 Aug** | `C3` full index · `C4` agent · `C5a` + `C5b` all 5 tools · `C6` evaluation · `TR` translation · `F1` notebook parser · `C3b` re-index with notebooks · `F3` `F4` `F6` app + citations + deploy · `C7` wire · **MVP LIVE + verified (`V1`–`V4`)** |
| Sat–Sun | not working. Felipe is 7 hours away from Saturday. |
| **Mon 10 Aug** | `F7` README + architecture diagram (FM) · `S7` version check |
| **Tue 11 Aug** | `F2` Study Notes · `F5` lesson picker / quiz view (FM) |
| **Wed 12 Aug** | `PRES` slides (CGS) · final re-run of the eval |
| **Thu 13 Aug** | buffer + **submit** |

**Everything still open is a bonus or a document. Nothing left is load-bearing.** If Monday
or Tuesday slips, we submit exactly what is already deployed and it still meets the brief.

**Do not let the buffer become the plan.** Wednesday 12th is for fixing what the final eval
run exposes, not for starting anything new. If something is not started by Tuesday
lunchtime, it does not go in.

**From Monday the 7-hour time difference is real.** The **Next pickup / notes** column in
`TRACKER.csv` becomes the actual handover — this week we could just pair on anything stuck.

## 5. Who does what

Split so neither of us is ever blocked waiting on the other.

`TRACKER.csv` in the shared Drive folder is the live status. This section is the ownership
map — who owns which code, so we never edit the same file at the same time.

### Casilda — the retrieval core
Owns the corpus, the index, and the agent. Everything under `src/` except `notebooks.py`.

| # | Task | Status |
|---|---|---|
| C1 · C1b | VTT parser + jargon fixes + classmate-name scrubbing | ✅ |
| C2 | `lessons.json` generated from the 122 `.info.json` titles | ✅ |
| C3 · C3b | Full Chroma index at 512 dims, video + notebooks, committed | ✅ |
| C4 | Agent: `create_openai_tools_agent` + `AgentExecutor` + summary-buffer memory | ✅ |
| C5a · C5b | All 5 tools, incl. `build_citation()` emitting Loom's `?t=80s` format | ✅ |
| C6 · V4 | Evaluation: 30 cases, 30/30 local, 6/6 classes on the deployed app | ✅ |
| C7 | Swapped Felipe's mock fixture for the real agent | ✅ |
| TR | Translation — answer in the language of the question | ✅ |
| PRES | Final presentation slides — **scheduled last** | open |

### Felipe — the app and everything that serves it
Owns `app/` and `src/notebooks.py`. Built the whole UI against
`tests/fixtures/mock_response.json` before the agent existed.

| # | Task | Status |
|---|---|---|
| F1 | Notebook parser: `.ipynb` → chunks split at markdown headings, same schema as C1 | ✅ |
| F3 | Streamlit app shell reading the mock fixture | ✅ |
| F4 | Citation rendering: inline Loom `/embed/` iframe cued to `?t=`, notebook paths | ✅ |
| F6 | Deploy to Streamlit Community Cloud | ✅ |
| F2 | Study Notes generator per lesson | open |
| F5 | Lesson picker + language selector + quiz view | open |
| F7 | README + architecture diagram | open |

**Why this split worked.** Freezing the two contracts in §4 *before* either of us wrote
code meant Felipe could build and style the entire UI against a mock while the agent did
not exist yet. `C7` — wiring the real agent in — was close to a one-line change, because
the shape it returned was the shape the UI already consumed.

### Rules we hold
- **Nothing is pushed to `main` without telling the other person first.**
- Only Casilda regenerates and commits `index/`. Felipe never commits it.
- Neither of us edits the other's files. `src/notebooks.py` is Felipe's; `src/` otherwise
  is Casilda's; `app/` is Felipe's.

## 6. How we share work — do NOT move the videos

**Nobody needs the video files.** We never downloaded any. The 91 hours stay on Loom; we
only ever handled 8.8 MB of text. Three rules:

1. **Never upload recordings to Drive.** It would be 50–100 GB, blow the quota, take days,
   and duplicate something Loom already hosts and serves with timestamp links.
2. **Never share a link to Casilda's computer.** Her laptop being asleep would block
   Felipe. Not a collaboration model.
3. **Code and data go in git. Documents go in Drive.**

The repo already has a remote: `github.com/Casildagsf/project-3-business-case-multimodal-ai-chatbot-for-yt-video-qa`

**Setup (10 minutes, once):**
1. Casilda adds Felipe as a collaborator on the GitHub repo
2. Casilda commits `data/` (8.8 MB — well within limits) and pushes
3. Felipe runs `bash data/raw/fetch_captions.sh` — raw transcripts are gitignored
   (classmates are named in them), so each of us regenerates them locally. Idempotent.
4. Later, `index/` gets committed by Casilda only — 66 MB, 5,248 chunks

**What stays in Google Drive:** this plan, the tracking sheet, the slides, meeting notes.
Not code, not data, not the index.

**Branching:** `main` stays deployable. Work on `feat/<name>-<thing>`, open a PR, the other
reviews. Two people, small repo — no need for anything heavier.

## 7. Environment — identical on both machines

**The two machines are not alike. This drives the choices below.**

| | Casilda | Felipe |
|---|---|---|
| Machine | Mac, Apple Silicon (arm64) | MacBook Air 2020, **Intel Core i7 (x86_64)** |
| RAM | — | 16 GB |
| macOS | — | Sequoia 15.7.8 |
| Python today | 3.13.9 | **3.11** |

**Python 3.11 for both.** Felipe *can* run 3.13 — Sequoia supports it fine — but he
shouldn't have to. Reasons, in order:

1. He's already on 3.11. Casilda installing it is one `brew install python@3.11`;
   Felipe migrating would mean rebuilding his whole environment for no gain.
2. **Intel + 3.13 is the thinnest wheel combination** of the four we could pick. The exact
   failure that already bit Casilda in the course — `langchain-pinecone` → `simsimd` with
   no 3.13 wheel — is a wheel-availability problem, and 3.11 makes that class of problem
   largely disappear.
3. Verified the pinned stack works on it: `chromadb 1.5.9` ships
   `cp39-abi3-macosx_10_12_x86_64` (Intel, Python 3.9+); `langchain`, `langchain-core` and
   `openai` are all `py3-none-any`. Nothing needs compiling on either machine.

**Consequence of Felipe's hardware: no local models, anywhere.** Iris Plus graphics and an
Intel CPU mean local embedding models and local LLMs are all off the table
for him. Everything goes through an API — OpenAI embeddings, `gpt-4o-mini`.
Do not assign Felipe any task that runs a model locally. (This costs us nothing: the plan
was already API-only.)

**A fresh venv inside the repo — NOT the course venv.** `AI_Engineering/.venv/langchain-v0.2.x`
is shared with the labs and carries elasticsearch/ollama baggage. One unpinned
`pip install langchain-*` in a lecture notebook would pull `langchain-core` 1.x and destroy
the project env too. Isolate it.

```bash
# Casilda only, once:  brew install python@3.11
cd <repo>
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import sys, chromadb, langchain; print(sys.version, chromadb.__version__, langchain.__version__)"
```

Both should paste that last line's output into the tracker on day 1. If the two machines
print different versions, stop and fix it before writing any code — a version mismatch
found on day 5 costs a day.

**`requirements.txt` — pinned, matching the API the course actually taught** (the
`demos_ai_eng` notebooks use `AgentExecutor`, `create_react_agent`, `langchain.chains` —
i.e. the 0.2 API, which we both already know):

**`requirements.txt` in the repo root is the source of truth — do not copy versions out of
this document.** It is fully pinned and commented, with `requirements.lock.txt` holding the
200-package freeze for byte-identical reproduction. The load-bearing pins:

```
langchain==0.2.17          # + core 0.2.43, community 0.2.19, openai 0.1.25
chromadb==0.5.3            # capped below 0.6 by langchain-chroma; pure-python wheel
langchain-chroma==0.1.4    # so nothing compiles on Apple Silicon OR Felipe's Intel Mac
streamlit==1.61.1
starlette==1.3.1           # transitive dep of streamlit, pinned deliberately
```

Note `chromadb` is **0.5.3**, not the 1.5.9 an earlier draft of this plan named — that
version is incompatible with `langchain-chroma`. No `fastapi`, `uvicorn` or
`python-multipart`: those belonged to the dropped FastAPI/React stack.

**Hard rule:** never `pip install` a `langchain-*` package unpinned. It pulls
`langchain-core` 1.x and breaks everything. If you need a new package, add it to
`requirements.txt` with a version and tell the other person.

**Secrets:** `.env` at the repo root, **gitignored**. Each of us uses our own keys in dev.

```
OPENAI_API_KEY=...
LANGCHAIN_API_KEY=...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=ai-learning-copilot
```

No `APP_API_KEY` — that was the `X-API-Key` for the dropped FastAPI front end. A single
Streamlit app has no service-to-service hop to authenticate.

**Settled (`D4`):** the deployed app uses **Casilda's OpenAI key**, set in Streamlit
Secrets, with a hard spend cap on the account. Ingestion cost ~$0.02, so the real cost is
demo traffic. LangSmith runs on Casilda's own account; Felipe revoked the key he had
shared and needs no keys at all for the MVP.

**Two course notebooks are near-direct references — read them before writing code:**
`14_LangChain/14_multi-modal-rag-chroma.ipynb` and
`14_LangChain/15_langsmith-medical-assistant-agent.ipynb`.

## 8. Risks

**Still live — manage these on demo day:**

- **The app sleeps when idle** (Streamlit Community Cloud free tier) and takes a few
  seconds to wake. **Open it and ask one question a few minutes before presenting** so the
  audience never watches it boot.
- **The chat input does not submit on Enter** — the send arrow must be clicked. Know this
  before demoing live.

**Retired — recorded because the mitigation is part of the build:**

- **Caption quality.** Auto-captions mangled the jargon badly: "RAG" came through as "RAC"
  in 61 of 78 mentions. Fixed with a find-and-replace dictionary in the parser — RAG
  mentions went 17 → 96. Without this the corpus barely mentioned its own central concept.
- **Classmates' voices and names are in the recordings.** Direct address is scrubbed to
  `[student]` (46 replacements). Scoped to direct address only — a blanket name scrub would
  have destroyed teaching content, since Alice/Bob/Charlie are Python loop examples, not
  classmates. Raw transcripts stay gitignored; instructor permission was granted (`D3`).
- **Agent over-calling tools.** Capped at `max_iterations=4`, plus an explicit instruction
  never to repeat an identical tool call, plus a fallback that catches LangChain's raw
  "stopped due to max iterations" string if it ever leaks to a student.
- **Merge conflicts on `index/`.** Only Casilda regenerates it; Felipe never commits it.
  Held all week.

## 9. Decisions taken — all settled, kept as the record of why

**1. Streamlit, not FastAPI + React.** ✅ *Decided 5 Aug, both.*
Two people, six days — one deploy beats two. No CORS, no `X-API-Key` plumbing, no keeping
two services in sync. `components.iframe()` handles the Loom embed natively. This collapsed
Felipe's four front-end tasks into three and saved roughly two days. Everywhere this
document previously described React/Vercel + FastAPI/Render, that was the superseded plan.

**2. Public repo.** ✅ *Decided 5 Aug, both.*
Reversed the earlier "private" recommendation. Raw transcripts stay **gitignored** because
classmates are named in them, and they are regenerable with `data/raw/fetch_captions.sh`.
The Chroma index *is* committed — it has to be, or the deployed app re-embeds on every wake
and loses it to the ephemeral filesystem.

**3. Instructor permission to process and deploy the recordings.** ✅ *Granted, 5 Aug.*
Students' voices are in them, so this was asked before any deployment, not after.

**4. Casilda's OpenAI key, with a hard spend cap.** ✅ *Decided 5 Aug.*
It is only an environment variable, so it is swappable later. LangSmith runs on Casilda's
own account — Felipe's shared key was revoked and he needs no keys for the MVP.

**5. Both uncaptioned recordings are out of scope.** ✅ *Decided 6 Aug, both.*
`w3d4-d` is standup admin, `w6d2-a` is the Project-3 homework briefing. The corpus is the
course's *teaching* material, so the honest figure is **120 of 120 teaching recordings**,
never "120 of 122".

**6. Voice / audio input is CUT.** ✅ *Decided 6 Aug, both.*
The brief's objective 2 asks for speech recognition. We are shipping a text-only copilot
and **saying so plainly in the README** — a stated scoping decision reads as a choice,
whereas silence reads as an oversight.
