# S1 — The two contracts

**Status: DRAFT. Review together, change what you disagree with, then freeze.**
Once frozen, neither of us changes it alone — a change here breaks the other person's code
silently, and we won't find out until integration day.

---

## Why this exists

Two things happen in parallel, and both would break without an agreement:

1. **Casilda writes the VTT parser. Felipe writes the notebook parser.** They write into the
   *same* Chroma collection. If Casilda emits `start_seconds` and Felipe emits `timestamp`,
   or one uses `lesson_id: "w7d2"` and the other `lesson: "week 7 day 2"`, retrieval returns
   a mix that no downstream code can render. Nobody notices until C3.

2. **Felipe builds the whole Streamlit UI before the agent exists**, against a mock. If the
   mock's shape differs from what the real agent returns, C7 (integration) turns from a
   1-hour swap into a UI rewrite.

Everything else in the project can be built independently. These two cannot.

---

## Contract 1 — the chunk

Both parsers emit this. **Every chunk carries every key** — use the defaults rather than
omitting, so `where` filters behave predictably.

```python
{
  "text": "Cosine similarity measures the angle between two vectors...",
  "metadata": {
    # --- always present ---
    "source_type":   "video",              # "video" | "notebook"
    "lesson_id":     "w7d2",               # the day code from Slack
    "lesson_title":  "RAG II - Indexing",  # from the Loom .info.json title
    "week":          7,
    "day":           2,

    # --- video chunks (defaults for notebook chunks) ---
    "loom_id":       "9adc63fbe9f84e93a7334a8c80c20569",   # "" if notebook
    "start_seconds": 872,                                   # -1 if notebook
    "segment":       "b",                                   # "" if notebook

    # --- notebook chunks (defaults for video chunks) ---
    "folder":        "",     # e.g. "14_LangChain"
    "notebook":      "",     # e.g. "3_langchain-RAG.ipynb"
    "cell_index":    -1,
    "heading":       "",     # the markdown heading the chunk sits under
  }
}
```

**Hard constraint, not a style choice:** Chroma metadata values may only be `str`, `int`,
`float` or `bool`. **No lists, no nested dicts, no `None`.** If you need a list, join it
into a delimited string. This will bite whoever forgets it.

### Chunking rules

| | Video | Notebook |
|---|---|---|
| Split on | ~800 chars, 120 overlap, never mid-cue | markdown headings |
| Timestamp | start time of the **first cue** in the chunk | n/a (`-1`) |
| Too-long unit | — | split a long section at ~800 chars, repeat the heading |
| Skip | — | `_images/`, `datasets/`, empty cells |

`start_seconds` is scoped to **its own Loom**, not to the lesson day. A day is 3–6 separate
recordings, so "w7d2 at 872s" is meaningless without `loom_id`.

---

## Contract 2 — what the agent returns

```python
{
  "answer": "Cosine similarity measures... [markdown]",
  "citations": [
    {
      "source_type":   "video",
      "lesson_id":     "w7d2",
      "label":         "w7d2 · RAG II — Indexing · 14:32",
      "url":           "https://www.loom.com/embed/9adc63fb...?t=872s",
      "start_seconds": 872,
    },
    {
      "source_type": "notebook",
      "lesson_id":   "w7d2",
      "label":       "14_LangChain/3_langchain-RAG.ipynb · cell 12",
      "url":         "https://github.com/Casildagsf/ironhack-final-project/blob/main/...",
      "start_seconds": -1,
    },
  ],
}
```

### The one design decision that matters here

**The agent builds `label` and `url`. The UI never computes them.**

That means Felipe never needs to know that Loom wants `?t=872s` and silently ignores
`?t=872`. And Casilda never needs to know how Streamlit renders an iframe. It also makes
the mock trivially correct — Felipe hardcodes two citation dicts in this exact shape and
his UI is finished before the agent exists.

---

## The four things that actually need a decision

Everything above is a proposal. These are the parts where we might genuinely disagree —
bring an opinion to the call:

1. **Chunk size.** 800 chars / 120 overlap is a starting guess. Lecture speech is rambly;
   1200 may retrieve better. We can tune this later, but both parsers must use the same
   value, so pick one now.
2. **One collection or two?** Proposal is one, with `source_type` as a filter. Two
   collections would mean the agent queries twice and merges — more control, more code.
3. **Do we index the 2 uncaptioned videos?** `w3d4-d` (standup intro) and `w6d2-a`
   (Project-3 kickoff). Proposal: no. They're admin, and Whisper would cost ~$0.50 and an
   hour for content nobody will ask about.
4. **Notebook URL target.** Linking to GitHub blob means the repo must stay public and the
   path must stay stable. Alternative: show the path as text with no link. Proposal: link.

---

## Who does what

| Step | Who | Time |
|---|---|---|
| Read this draft before the call | Both | 10 min |
| Call: settle the 4 decisions above, edit this file live | **Both together** | 20–30 min |
| Write `src/schemas.py` — the dicts, the defaults, a `build_citation()` helper | Casilda | 45 min |
| Write `tests/fixtures/mock_response.json` from Contract 2 | Casilda | 15 min |
| Review `schemas.py`, then build the mock UI against the fixture | Felipe | — |

Casilda writes `schemas.py` because she has the data and hits the real edge cases first.
Felipe reviews it — if he can't build his mock from it without asking a question, it isn't
finished.

**After this is merged, C1 and F1 start in parallel and don't need to talk again until C3.**
