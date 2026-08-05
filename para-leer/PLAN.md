# Project 3 — AI Learning Copilot for the Ironhack bootcamp

**Team:** Casilda Gonzalez (CGS) · Felipe Martignon (FM)
**Team repo:** https://github.com/Casildagsf/ironhack-final-project (currently empty — README only)
**Status:** M0 complete. 122 transcripts downloaded, sitting in the *old* brief repo and
still to be migrated into the team repo.

> **Two decisions are still open** and this document assumes an answer to one of them.
> See §9 at the end. Do not treat §5 (work split) as agreed until they're settled.

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
| `w6d2 - a - Project-3 Kick-off` | 45 min | **Whisper it** (task `C0`, ~$0.27). Probably the most-asked-about recording — "what exactly do they want in the project?" |

Chunks from the Whisper pass carry `transcript_source: "whisper"` so the writeup can point
at it and, if quality is worse than Loom's captions, we can measure or filter it separately.
This also satisfies README objective 2 (speech recognition) in the *ingestion* path, not
only the microphone input.

**Neither is on the MVP path.** 118 teaching recordings is more than enough to demo.

## 3. Architecture — two decisions that drive everything

**A. Split build time from run time.** Parsing, chunking, embedding and summarising happen
**once, on a laptop**, in a notebook. The Chroma index and the summaries are **committed to
the repo**. Render's free tier has an ephemeral filesystem and a cold start — re-embedding
on boot would lose the index on every restart and wreck latency, which is graded.
At run time the API only *reads*.

**B. One Chroma collection, two source types.** Video and notebook chunks share one
collection with a `source_type` field. Retrieval is unified; only the *citation format*
branches. This is what makes it feel smart: one question returns both "w7d2, 14:32" and
"`14_LangChain/3_langchain-RAG.ipynb`, cell 12".

### Run-time flow

```
React (Vercel)  ──►  FastAPI (Render)  ──►  LangChain agent (gpt-4o-mini + memory)
   text or voice        /ask /transcribe          │
   embedded Loom                                  ├─ search_material   ─► Chroma index
   player at ?t=                                  ├─ get_lesson_summary ─► summaries/*.md
                                                  ├─ lesson_index
                                                  ├─ transcribe_audio  ─► Whisper API
                                                  └─ citation_link
```

### Non-obvious details that will bite us

- **Loom deep links need `?t=80s` or `?t=10m8s`, not `?t=80`.** Raw seconds are silently
  ignored. Loom's `/embed/<id>` iframe accepts the same param — so citations render as an
  inline player already cued to the moment, and the student never leaves the app.
- **Embeddings at `dimensions=512`, not the default 1536.** 91 hours ≈ 6,000 chunks. At
  1536 the persisted index is ~75 MB (GitHub warns at 50 MB/file). At 512 it is ~25 MB and
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
notebook indexing, Study Notes, quiz, translation, voice input, lesson picker UI.

Ranked order once the MVP is up:
1. **Notebook indexing** (F1 → C3) — the dual-source citation is our differentiator
2. **Quiz tool** — cheap, and it makes agent routing obviously necessary
3. **Study Notes** — the strongest bonus in Felipe's plan
4. **Translation** — one line in the system prompt
5. **Voice input** — last, and only if everything else is finished

### Critical path to MVP

```
S1a ✅ → C1 (VTT parser) → C3 (index) → C4 (agent) → C5 (tools) → C7 (wire) → F6 (deploy)
          3h               3h           4h           4h           1h          2h
```

**≈ 17 hours, and almost all of it currently sits on Casilda.** Felipe's tasks (F1, F2, F5)
are parallel or downstream, so he is not on the critical path at all — which means the MVP
date is set entirely by one person's throughput. That is the main scheduling risk.

**Fix: Felipe takes C3 (indexing).** He is already writing F1, and indexing is the step that
consumes both parsers, so it is a natural fit. Casilda hands him chunks; he owns building
and committing the index. That moves 3 hours off the critical path and gives him something
real before the app work starts.

With that change: **Casilda ~11h, Felipe ~10h.** At roughly 6 focused hours a day each,
**the MVP lands on day 3**, leaving days 4–6 for evaluation, bonuses, docs and slides —
which is the right shape, because F7 (slides) needs C6's numbers and cannot be rushed.

### The actual calendar — submission is Thursday 13 August

**Six working days, and the MVP takes two of them.** That is a comfortable margin, and the
whole point of it is iteration: getting a working thing early so the remaining four days
improve it rather than build it.

| | |
|---|---|
| **Wed 5 Aug** (part day) | `C1` ✅ `C2` ✅ `C1c` ✅ · `S6` `F3` |
| **Thu 6 Aug** | `C4` `C5a` · `C3` `F4` |
| **Fri 7 Aug** | `C7` · `F6` · verify → **MVP LIVE** |
| Sat–Sun | not working. Felipe moves 7 hours away on Saturday. |
| **Mon 10 Aug** | `C6` evaluation · `F1` notebook parser |
| **Tue 11 Aug** | `C3b` re-index with notebooks · `C5b` quiz + explain tools |
| **Wed 12 Aug** | `F2` Study Notes · translation · `F7` slides · re-run eval |
| **Thu 13 Aug** | buffer + **submit** |

**Do not let the buffer become the plan.** Wednesday 12th is for fixing what the Monday
evaluation exposes, not for starting anything new. If something is not started by Tuesday
lunchtime, it does not go in.

Two consequences of the dates:

- **We work the same hours until Saturday.** Handovers barely matter this week — pair on
  anything stuck instead of writing it up. From Monday the 7-hour gap is real and the
  **Next pickup / notes** column becomes the actual handover.
- **`C6` (LangSmith evaluation) moves to Monday, first thing.** It is a graded deliverable
  and it is also what tells us what to fix — running it on day 1 of the second week means
  four days to act on what it finds. Running it late makes it a formality.

If the MVP is not up by end of Friday, cut notebook indexing and ship video-only.

## 5. Who does what

Split so neither of us is ever blocked waiting on the other.

### Casilda — the retrieval core
Owns the data (already has it), the index, and the agent.

| # | Task | Est |
|---|---|---|
| C1 | VTT parser: cues → ~800-char chunks, strip `<v N>`, keep first cue's start time | 3 h |
| C2 | Generate `lessons.json` from the 122 `.info.json` titles (no hand-typing) | 1 h |
| C3 | Ingest all captions → Chroma at 512 dims, commit `index/` | 3 h |
| C4 | Agent: `create_openai_tools_agent` + `AgentExecutor` + summary-buffer memory | 4 h |
| C5 | The 5 tools, incl. `citation_link` emitting Loom's `?t=80s` format | 3 h |
| C6 | LangSmith eval set: 25 Q/A pairs (15 factual, 5 summary, 3 Spanish, 3 unanswerable) | 3 h |
| C7 | Swap Felipe's mock `/ask` for the real agent | 1 h |

### Felipe — everything that serves it
Starts immediately against the mock; never waits for the agent.

| # | Task | Est |
|---|---|---|
| F1 | Notebook parser: `.ipynb` → chunks split at markdown headings, same schema as C1 | 3 h |
| F2 | Summaries: map-reduce each lesson → `summaries/<lesson_id>.md`, commit them | 3 h |
| F3 | FastAPI skeleton: `/ask` (**mock**), `/transcribe`, `/health`, `X-API-Key`, CORS | 3 h |
| F4 | Deploy to Render, verify with Postman | 2 h |
| F5 | React on Vercel: question box, mic via `MediaRecorder`, access-code unlock | 5 h |
| F6 | Citation rendering: inline Loom `/embed/` iframe cued to `?t=`, notebook paths | 3 h |
| F7 | README, architecture diagram, slides | 3 h |

### Shared, do together on day 1 (90 min, one call)
- Agree the two contracts in §4 — this is the whole basis of working in parallel
- Set up the repo, envs, and keys (§6, §7)
- Pick who owns which branch naming, agree we never push to `main` directly

**Calendar estimate: 4 working days** if we hold the split. Sequentially it would be 6.

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
3. Felipe clones — he now has all 122 transcripts, byte-identical
4. Later, `index/` (~25 MB) and `summaries/` get committed the same way

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
Intel CPU mean local Whisper, local embedding models, and local LLMs are all off the table
for him. Everything goes through an API — Whisper API, OpenAI embeddings, `gpt-4o-mini`.
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

```
langchain==0.2.17
langchain-core==0.2.43
langchain-community==0.2.19
langchain-openai==0.1.25
langsmith==0.1.147
chromadb==1.5.9
openai==1.109.1
fastapi
uvicorn[standard]
python-multipart
webvtt-py
yt-dlp
python-dotenv
```

**Hard rule:** never `pip install` a `langchain-*` package unpinned. It pulls
`langchain-core` 1.x and breaks everything. If you need a new package, add it to
`requirements.txt` with a version and tell the other person.

**Secrets:** `.env` at the repo root, **gitignored**. Each of us uses our own keys in dev.

```
OPENAI_API_KEY=...
LANGCHAIN_API_KEY=...
LANGCHAIN_TRACING_V2=true
APP_API_KEY=...        # the X-API-Key the front end sends
```

**Still to agree:** whose OpenAI key the *deployed* app uses, and a spend cap on it.
Ingestion is ~$0.02 and summaries ~$0.20, so the real cost is demo traffic — small, but
it should sit on one account with a limit set, not "whoever's key is in Render".

**Two course notebooks are near-direct references — read them before writing code:**
`14_LangChain/14_multi-modal-rag-chroma.ipynb` and
`14_LangChain/15_langsmith-medical-assistant-agent.ipynb`.

## 8. Risks

- **Render free tier cold start (~50 s)** hurts the latency criterion. Warm it before
  demoing and say so in the slides.
- **The material is Ironhack's IP.** Keep the deployed app behind the access-code screen.
  Do not ship a public URL with the whole course inside it.
- **Caption quality.** Auto-captions mangle jargon. Spot-check at C1; if bad, a ~20-term
  find-and-replace dictionary in the parser fixes most of it.
- **Agent over-calling tools** inflates latency. Cap `max_iterations`, prompt it to search
  once unless the first result is empty.
- **Merge conflicts on `index/`.** Binary-ish and large. Only Casilda regenerates it;
  Felipe never commits it.

## 9. Open decisions — settle these on the first call

**1. Streamlit, or FastAPI + React?**
Felipe's plan says Streamlit. Casilda's earlier plan said FastAPI/Render + React/Vercel.
**Recommendation: Streamlit.** Six days, two people — one deploy
beats two. No CORS, no `X-API-Key` plumbing, no keeping two services in sync. Streamlit
has `st.audio_input` for the voice bonus and `components.iframe()` handles the Loom embed.

**§5's Felipe tasks (F3–F6) are written for FastAPI/React and are wrong if we pick
Streamlit.** They collapse to roughly: Streamlit app shell → citation rendering with the
Loom iframe → Community Cloud deploy. Fewer tasks, ~2 days saved.

**2. Public or private repo?**
Felipe's plan says keep `data/` out of GitHub for IP reasons. But the Chroma index *must*
be committed or the deployed app re-embeds on every cold start and loses it on ephemeral
disk. **Recommendation: private repo**, then commit index + summaries. That satisfies both
concerns better than gitignoring does.

**3. Also do on day 0 (Felipe's point, and he's right):** ask the instructor whether we may
process and deploy Ironhack's recordings. Students' voices are in them. Five-minute Slack
message; if the answer is restrictive we need to know now, not on day 5.
