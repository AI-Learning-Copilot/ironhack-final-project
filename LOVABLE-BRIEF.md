# Brief for building the frontend in Lovable

Everything below is a working, running API. `api/openapi.json` is the full contract —
paste that into Lovable first, because it is the thing that stops a generated frontend
inventing endpoints that do not exist.

Start the backend, then point Lovable at it:

```bash
PYTHONPATH=src .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Interactive docs, useful for checking a shape by hand: http://127.0.0.1:8000/docs

## What the product is

A study assistant for one Ironhack bootcamp cohort. It answers questions using only the
course's own recordings and notebooks, and every answer carries citations that link to the
exact lesson and the Loom video cued to the second.

The thing that makes it different from a chatbot is that **it refuses**. If the course did
not cover something, it says so and shows no sources at all. Design for that: a refusal is
a normal, first-class response, not an error state.

## The five surfaces to build

1. **Chat** — the main view. Question in, grounded answer out, citations underneath.
2. **Citations** — expandable. Video citations embed the Loom player; notebook citations
   link out to GitHub.
3. **Course browser** — 32 lesson days across 8 weeks, each with study notes in markdown.
4. **Scope filter** — narrow the whole conversation to one lesson or one week.
   Study notes and the syllabus both download as PDFs; link them, do not render them
   in-page.
5. **Quiz** — pick a topic, get multiple-choice questions with answers.

## Endpoints, in the order a frontend needs them

| Call | Purpose | Cost |
|---|---|---|
| `POST /api/session` | get a `session_id`, hold it for the whole visit | instant |
| `GET /api/lessons` | 32 lessons + 8 weeks, for the browser and the scope filter | instant, static |
| `GET /api/lessons/{id}/notes` | study notes as markdown | instant, static |
| `GET /api/lessons/{id}/notes.pdf` | the same notes as a formatted PDF | ~0.2s |
| `GET /api/syllabus.pdf` | the full 8-week course syllabus | instant, static |
| `POST /api/ask` | one turn | **~5s**, an OpenAI call |
| `POST /api/session/{id}/scope` | set or clear the lesson/week filter | instant |
| `POST /api/session/{id}/quiz` | generate a quiz | **~10s** |
| `POST /api/session/{id}/reset` | start the conversation over | instant |

`GET /api/health` returns session counts. `POST /api/session/{id}/evict` is a debugging
hook, not a feature — leave it out of the UI.

## The shapes that matter

`POST /api/ask` returns:

```json
{
  "session_id": "…",
  "answer": "An embedding is a representation of words…",
  "citations": [
    {
      "source_type": "video",
      "lesson_id": "w4d3",
      "label": "w4d3 · Embeddings Intro · 19:42",
      "url": "https://www.loom.com/embed/69e3…?t=1182s",
      "start_seconds": 1182
    }
  ],
  "elapsed_seconds": 4.31,
  "rehydrated": false
}
```

**Render `label` and `url` as given. Never build either one.** The backend already handles
Loom's `?t=` quirk and the `Extra ·` prefix that marks supplementary notebooks. A frontend
that formats its own labels will get them subtly wrong.

`source_type` is `"video"` or `"notebook"`. Video URLs are embeddable in an iframe;
notebook URLs are GitHub links and should open in a new tab.

`rehydrated` is engineering instrumentation. Do not show it to students.

## Design constraints that are not negotiable

**Answers take about five seconds.** Median ~5s, p95 ~10s, worst case ~12s. There is no
streaming yet, so the UI must carry that wait: a visible thinking state, and the question
staying on screen while it works. This is the single biggest thing the current frontend
gets wrong.

**A refusal shows no citations.** When the answer is "That wasn't covered in the course",
the citations array is empty by design — a refusal must never look sourced. Style it as a
calm, informative state, not a failure.

**A scoped refusal is different.** With a filter active the wording becomes "That wasn't
covered in week 7 — turn the lesson filter off to search all 8 weeks." If a scope is
active, show it prominently and make it one click to clear.

**Follow-ups work and should be encouraged.** "And where was it covered?" resolves against
the conversation. The empty state should teach this — it is the feature people do not
expect.

**Markdown everywhere.** Answers, study notes and quizzes all come back as markdown. Render
it properly: headings, lists, bold, and code blocks all appear.

## Look and feel

The existing app uses an indigo-and-pastel palette — `#818cf8` primary, `#FBFAFF`
background, `#1E1B4B` text, Sora for headings and Manrope for body. Keep it or replace it;
it is not sacred.

**Do not use Ironhack's logo or brand colours** unless we have said otherwise. It is their
material but not their product, and putting their branding on it uninvited is a
conversation we have not had yet.

Should be usable on a phone. Students will check something on the way to class.

## Do not build

- Login, accounts, or profiles. There is no auth and the session id is the only identity.
- Anything that stores conversations client-side. Persistence is a decision we have not
  made.
- Streaming. The endpoint does not support it.

## Known gaps, so nothing here is a surprise

- **No streaming**, so the wait is the design problem.
- **No auth.** Anyone holding a session id can read that conversation.
- **Nothing survives a restart.** Sessions are in memory.
