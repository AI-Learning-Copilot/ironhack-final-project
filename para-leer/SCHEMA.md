# S1 — The two contracts

**Status: AGREED 2026-08-05 by Casilda and Felipe. FROZEN.**

Neither of us changes this alone. A change here breaks the other person's code silently and
we won't find out until integration. If something needs to change: say so, agree, edit here
first, then edit code.

---

## Why this exists

Two things happen in parallel, and both would break without an agreement:

1. **Casilda writes the VTT parser. Felipe writes the notebook parser.** They write into the
   *same* Chroma collection. Mismatched keys produce a mix nothing downstream can render,
   and it surfaces days later at C3.
2. **Felipe builds the whole Streamlit UI before the agent exists**, against a mock. If the
   mock's shape differs from what the real agent returns, C7 turns from a 1-hour swap into
   a UI rewrite.

Everything else can be built independently. These two cannot.

---

## Contract 1 — the chunk

Both parsers emit this. **Every chunk carries every key** — use the defaults rather than
omitting, so `where` filters behave predictably.

```python
{
  "text": "Cosine similarity measures the angle between two vectors...",
  "metadata": {
    # --- always present ---
    "source_type":       "video",              # "video" | "notebook"
    "lesson_id":         "w7d2",               # day code from the Slack post
    "lesson_title":      "RAG II - Indexing",  # from the Loom .info.json title
    "week":              7,
    "day":               2,

    # --- video chunks (defaults shown for notebook chunks) ---
    "loom_id":           "9adc63fbe9f84e93a7334a8c80c20569",   # "" if notebook
    "start_seconds":     872,                                   # -1 if notebook
    "segment":           "b",                                   # "" if notebook
    "transcript_source": "loom",               # "loom" | "whisper" | "" if notebook

    # --- notebook chunks (defaults shown for video chunks) ---
    "folder":            "",     # e.g. "14_LangChain"
    "notebook":          "",     # e.g. "3_langchain-RAG.ipynb"
    "cell_index":        -1,
    "heading":           "",     # the markdown heading the chunk sits under
  }
}
```

**Hard constraint, not a style choice:** Chroma metadata values may only be `str`, `int`,
`float` or `bool`. **No lists, no nested dicts, no `None`.** Join lists into a delimited
string. This will bite whoever forgets it.

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
      "source_type":   "notebook",
      "lesson_id":     "w7d2",
      "label":         "14_LangChain/3_langchain-RAG.ipynb · cell 12",
      "url":           "https://github.com/ironhack-ai-eng-june2026/demos_ai_eng/blob/main/14_LangChain/3_langchain-RAG.ipynb",
      "start_seconds": -1,
    },
  ],
}
```

### The design decision that matters most here

**The agent builds `label` and `url`. The UI never computes them.**

Felipe therefore never needs to know that Loom wants `?t=872s` and *silently ignores*
`?t=872`. Casilda never needs to know how Streamlit renders an iframe. It also makes the
mock automatically correct: hardcode two citation dicts in this shape and the UI is
finished before the agent exists.

---

## Decisions taken on the call, 2026-08-05

**1. Chunk size — video: 1000 chars / 200 overlap. Notebooks: split by markdown heading,
force-split only above ~1500 chars.**

Chunk size *is* timestamp precision: we cite the start of the chunk, so a 4-minute chunk
points four minutes before the answer. 800 chars ≈ 52 s of speech and often cuts an
explanation before its payoff; 1000 ≈ 65 s holds one complete idea while still landing the
student close enough. Notebooks are different media — headings are already semantic units,
so different sizes per source is correct, not inconsistent.

**2. One Chroma collection, with `source_type` as a filter.**

A student asks one question and wants the best answer regardless of source. Two collections
means querying twice and merging — a re-ranking problem we don't want on this deadline.
`where={"source_type": "video"}` gives us the two-collection behaviour for free.

**3. Both uncaptioned recordings are out of scope.**

Loom has no captions for two recordings, and neither is teaching material:
- `w3d4 - d - intro to Standup meetings` (37 min) — process admin.
- `w6d2 - a - Project-3 Kick-off` (45 min) — homework briefing, not a lesson.

Decided 6 Aug (CGS + FM). The corpus is the course's *teaching* content, so the honest
figure is **120 of 120 teaching recordings**, not "120 of 122". No Whisper pass is run.

**4. Notebook citations link to the public Ironhack repo.**

`github.com/ironhack-ai-eng-june2026/demos_ai_eng` is public (verified HTTP 200), so we
link straight there — no vendoring, and the link stays current.

**Corollary: do not copy the notebooks into this repo.** Felipe parses them from a local
clone at build time; only the index is committed. GitHub cannot reliably deep-link a
notebook cell, so the URL opens the notebook and `label` carries `cell 12`.

**5. Instructor permission — granted.** We may process and deploy the recordings. Raw
transcripts still stay out of the public repo (classmates are named throughout); the
committed index carries scrubbed text. See task C1b.

---

## Who does what next

| Step | Who | Status |
|---|---|---|
| Write `src/schemas.py` — the dicts, defaults, and `build_citation()` | Casilda | next |
| Write `tests/fixtures/mock_response.json` from Contract 2 | Casilda | next |
| Clone `demos_ai_eng` locally, confirm cell extraction from an `.ipynb` | Felipe | can start now |
| Review `schemas.py`, then build the mock UI against the fixture | Felipe | blocked on Casilda |
| `C1` (VTT parser) and `F1` (notebook parser) in parallel | Both | after `schemas.py` |

**Acceptance test for `schemas.py`:** if Felipe cannot build his mock from it without asking
a question, it isn't finished.


---

## Quiz text format contract

The `generate_quiz` tool and the interactive Streamlit quiz UI share the
following text-format contract.

Each multiple-choice question must be returned in this form:

```text
<question>
A) <option>
B) <option>
C) <option>
D) <option>
Answer: <letter>
```

### Rules

- Each question has exactly four options: A, B, C, and D.
- Each question has exactly one correct answer.
- The correct answer is written on a separate `Answer:` line.
- The answer value is one letter only: A, B, C, or D.
- Questions may optionally be numbered.
- Introductory text before the questions is allowed.
- Markdown emphasis around lines is tolerated by the UI.
- The Streamlit parser also tolerates `)`, `.`, or `:` after option letters.

This format is consumed by `app/app.py` to build the interactive quiz and
calculate the student's score.

If this format changes, both `src/tools.py` and `app/app.py` must be reviewed
together.

**Contract producer:** `src/tools.py` → `generate_quiz`

**Contract consumer:** `app/app.py` → `parse_quiz`