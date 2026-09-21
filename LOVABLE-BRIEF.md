# Brief for building the frontend in Lovable

Everything below is a working, running API. `api/openapi.json` is the full contract —
paste that into Lovable first, because it is the thing that stops a generated frontend
inventing endpoints that do not exist.

The backend is deployed:

    API base URL      https://course-copilot-api-vvnm.onrender.com/api
    Interactive docs  https://course-copilot-api-vvnm.onrender.com/docs
    Supabase URL      https://ktbnppcvuxcghilaxdrh.supabase.co
    Supabase key      sb_publishable_knTrfjryIDQzk6BnDWAYTQ_t5niYAfq   (public, for the browser)

Free hosting: the API sleeps after 15 minutes idle and takes 30-60 s to wake, so the
first request of a session can be slow. Show a "waking up" state if a request takes more
than 10 s; do not treat it as an error before 90 s.

For local work: `PYTHONPATH=src .venv/bin/uvicorn api.main:app --port 8000`.

## What the product is

A study assistant for one Ironhack bootcamp cohort. It answers questions using only the
course's own recordings and notebooks, and every answer carries citations that link to the
exact lesson and the Loom video cued to the second.

The thing that makes it different from a chatbot is that **it refuses**. If the course did
not cover something, it says so and shows no sources at all. Design for that: a refusal is
a normal, first-class response, not an error state.

## The six surfaces to build

1. **Chat** — the main view. Question in, grounded answer out, citations underneath.
2. **Citations** — expandable. Video citations embed the Loom player; notebook citations
   link out to GitHub.
3. **Course browser** — 32 lesson days across 8 weeks, each with study notes in markdown.
4. **Scope filter** — narrow the whole conversation to one lesson or one week.
   Study notes and the syllabus both download as PDFs; link them, do not render them
   in-page.
5. **Quiz** — pick a topic and a range (whole course, one week, or one lesson day), get
   multiple-choice questions, answer them, see a score.
6. **Answer language** — a small control for Auto / English / Español.

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
| `POST /api/session/{id}/quiz` | generate a quiz; optional `week` or `lesson_id` scopes that quiz only | **~10s** |
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

**Each citation is one recording or notebook, not one passage.** A lecture that covers the
topic at five points arrives as a single citation whose `url` is the best-ranked moment,
with the rest in `also_at`. Show the citation as one item. Offer `also_at` quietly beneath
it — "also covered at 20:44, 9:36" — never as extra citations, and never in the count. At
most four citations come back; there is no need for pagination.

`related_notebooks` has the same shape as a citation but a different meaning: it is the
code for the topic, found by a second retrieval, and it did **not** ground the answer.
Render it in its own labelled group, visually separated from the citations. Presenting it
as a source would be a lie, and refusals never carry any.

**External links need an onClick, not just `target="_blank"`.** Measured: a blocked popup
makes a `target="_blank"` anchor do nothing at all, which reads as broken rather than
blocked. Try `window.open`; if it returns `null`, navigate in the same tab; leave the
`href` on the anchor so right-click and middle-click still work.

**Errors come back as JSON, not text.** A failed turn is HTTP 502/503/504 with
`{"detail": {"message": "…", "kind": "rate_limit|timeout|connection|auth|quiz|unknown"}}`.
Show `message` to the student as-is (it is written for them) and offer a Retry button;
keep the question in the input.

## Design constraints that are not negotiable

**Answers stream.** `POST /api/ask/stream` sends server-sent events: `session`, then
`tool` while the course is searched (~2 s), then `token` events as the model writes,
then `done` with the same object `/api/ask` returns. Render tokens as they arrive and
replace the text with `done.answer` at the end (a scoped refusal is rewritten there).
`reset` means "clear what you have, the model changed its mind and is searching". An
`error` event replaces `done` on failure, with the same `{message, kind}` as `/api/ask`.
Read it with `fetch` and a stream reader; `EventSource` cannot send a POST body. Keep the
question on screen and a visible thinking state until the first token.

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
it properly: headings, lists, bold, links and code blocks all appear.

**The language control sends `language` on `/ask`** — `"auto"`, `"en"` or `"es"`. Auto is
the default and means the answer follows the language of the question, which the backend
handles on its own. Do not translate anything client-side.

**A quiz range is not the conversation scope.** The quiz's own `week` / `lesson_id` apply
to that quiz only. Choosing to be tested on week 3 says nothing about what the next
question should search, and the two must not be wired together.

## Look and feel

The existing app uses an indigo-and-pastel palette — `#818cf8` primary, `#FBFAFF`
background, `#1E1B4B` text, Sora for headings and Manrope for body. Keep it or replace it;
it is not sacred.

**Do not use Ironhack's logo or brand colours** unless we have said otherwise. It is their
material but not their product, and putting their branding on it uninvited is a
conversation we have not had yet.

**Keep the attribution line in the footer, wording unchanged:** the recordings and
notebooks are from the Ironhack AI Engineering bootcamp and belong to Ironhack; the
copilot is our final project for that bootcamp; the code is on GitHub. The whole app rests
on their material and the line between their content and our code belongs on the page, not
in a README. It can be small and quiet. It cannot be removed.

Should be usable on a phone. Students will check something on the way to class.

## Auth: build the screen now, the API enforces it later

Sign-in is **Supabase Auth** on the project above: email + password now, Google once the
OAuth client is configured. Connect the Lovable project to that Supabase project, build
the sign-in screen with Supabase Auth, and send the session's access token as
`Authorization: Bearer <access_token>` on every `/api` call. The API verifies it and
answers 401 `{"detail": {"message": "…", "kind": "auth"}}` when it is missing or expired
(send the student back to sign-in) and 403 `kind: "forbidden"` when the account is not on
the access list (show the message; there is nothing the student can do). Sessions belong
to the signed-in user: a session id from another account gets 403. Do not build your own
accounts, passwords or profiles, and never put the Supabase secret key in the frontend.

## Do not build

- Anything that stores conversations client-side. Persistence will live in Supabase on
  the API side.
- A second answer path: `/api/ask/stream` is the primary, `/api/ask` the fallback when
  streaming fails. Same body, same final object.

## Known gaps, so nothing here is a surprise

- **No auth yet.** Anyone holding a session id can read that conversation. See the
  auth section above.
- **Nothing survives a restart.** Sessions are in memory.
