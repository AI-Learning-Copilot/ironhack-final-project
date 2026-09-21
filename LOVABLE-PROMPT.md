# Course Copilot — first prompt for Lovable

Paste everything below the line into a new Lovable project as the first message. Then
connect the project to Supabase (Lovable's Supabase integration → project
`course-copilot`, ref `ktbnppcvuxcghilaxdrh`) when Lovable asks for it.

---

Build **Course Copilot**, a study assistant web app for a coding bootcamp. It answers
questions using only the course's own recorded lessons and notebooks, and every answer
carries citations that link to the exact lesson and the Loom video cued to the second.
The backend already exists; you build only the frontend.

## Backend

- API base URL: `https://course-copilot-api-vvnm.onrender.com/api`
- OpenAPI spec: `https://course-copilot-api-vvnm.onrender.com/openapi.json` — follow it
  exactly, do not invent endpoints or fields.
- Free hosting: the API sleeps after 15 minutes idle and takes 30–60 s to wake. If a
  request takes more than 10 s, show a "waking up the copilot…" state; only treat it as
  an error after 90 s.
- All errors are JSON: `{"detail": {"message": "...", "kind": "..."}}`. Show `message`
  to the student as-is and offer a Retry that keeps their question in the input.

## Auth (Supabase)

- Use Supabase Auth on the connected project. Sign-in with email + password (Google
  will be added later). Project URL `https://ktbnppcvuxcghilaxdrh.supabase.co`,
  publishable key `sb_publishable_knTrfjryIDQzk6BnDWAYTQ_t5niYAfq`.
- Send the session's access token on every API call: `Authorization: Bearer <token>`.
- 401 with `kind: "auth"` → send the student to sign-in. 403 with `kind: "forbidden"` →
  show the message ("not on the access list"); nothing else to do.
- Do not build your own accounts or profiles. Never put a secret key in the frontend.
- Nothing is stored client-side except the current `session_id` (sessionStorage).

## Flow, in the order the app calls things

1. Sign in.
2. `POST /session` → `{session_id}`. Keep it for the visit.
3. `GET /lessons` → `{lessons: [...], weeks: [...]}` for the course browser and the
   scope filter. Static; load once.
4. `POST /ask/stream` with `{question, session_id, language}` (`language` is `"auto"`,
   `"en"` or `"es"`, default `"auto"`). Server-sent events (`text/event-stream`), read
   with `fetch` + a stream reader (not `EventSource`, which cannot POST). Events in
   order: `session {session_id}` → `tool {name}` (show "searching the course…") →
   `token {text}` (append to the answer as it arrives, first token in ~2 s) →
   optionally `reset {}` (clear the text, keep waiting) → `done` (the full response
   below; replace the streamed text with `done.answer` and render `done.citations`)
   or `error {message, kind}` (HTTP is 200; treat like an error response).
   `POST /ask` with the same body returns the same `done` object in one piece after
   ~5 s; use it as the fallback if streaming fails. Response:
   ```json
   {"session_id": "...", "answer": "markdown", "citations": [...],
    "related_notebooks": [...], "elapsed_seconds": 4.3, "rehydrated": false}
   ```
   Each citation: `{source_type: "video"|"notebook", lesson_id, label, url,
   start_seconds, also_at: [{label, url, start_seconds}]}`.
5. `POST /session/{id}/scope` with `{lesson_id}` or `{week}` or `{}` to clear.
6. `POST /session/{id}/quiz` with `{topic, num_questions, week?, lesson_id?}` →
   `{topic, markdown, scope}`. Takes ~10 s.
7. `GET /lessons/{id}/notes` → `{lesson_id, markdown}`; `GET /lessons/{id}/notes.pdf`
   and `GET /syllabus.pdf` are downloads (open in a new tab, never render in-page).
8. `POST /session/{id}/reset` starts the conversation over.

`GET /health` and `POST /session/{id}/evict` exist but are not UI features.

## Screens

1. **Sign in** — one screen, email + password, "access is by invitation" note.
2. **Chat** — the main view. Question in, answer out as rendered markdown, citations
   underneath. Follow-ups work ("and where was it covered?") and the empty state should
   suggest one. Keep the question on screen while waiting; show a visible thinking
   state for the ~5 s wait.
3. **Citations** — one card per citation. Video: the `label` as the title, an embedded
   Loom player from `url` (it is an `/embed/` URL with `?t=` already set), and a small
   "also at 20:44, 9:36" line from `also_at`. Notebook: the label linking to `url` in a
   new tab. Render `label` and `url` exactly as given; never build them. At most four
   citations come back.
   `related_notebooks` has the same shape but did **not** ground the answer: show them in
   a separate group titled "Related notebooks", visually distinct from the citations.
4. **Refusals** — when `answer` says the topic was not covered, `citations` is empty
   by design. Style it as a calm informative state, not an error. If a scope filter is
   active, show the filter prominently with one-click clear.
5. **Course browser** — 8 weeks, 32 lesson days from `/lessons`. Each lesson: title,
   recordings, notebooks, a "Study notes" view (markdown from `/notes`) with a
   "Download PDF" button, and a "Search only this lesson" button that sets the scope.
6. **Scope filter** — a chip near the input showing the active lesson/week with an ×.
7. **Quiz** — topic input, range (whole course / a week / a lesson day), 3–5 questions.
   Render the returned markdown as an interactive quiz: each question has options
   A–D and an `Answer: X` line; hide the answer lines, let the student pick, then
   score. The quiz range does not change the conversation scope.
8. **Language** — small control Auto / English / Español, sent as `language`.
9. **New conversation** button → `/reset`.

## Look

- Name: **Course Copilot**. No school branding, no school logo.
- Palette: cobalt `#4C6FBF` (primary; `#8FAAEA` on dark), marigold `#F0B35B` (accent,
  sparingly), ink `#1E2A44` (text), paper `#F6F7FA` (background), night `#141A2B`
  (dark background). Light and dark mode.
- Type: **Bricolage Grotesque** 600 for headings, **Manrope** for body. Google Fonts.
- Layout on desktop: lesson browser as a collapsible left rail, chat in the centre,
  sources under each answer. On mobile: single column, browser behind a drawer.
  Students will use this on a phone on the way to class.
- Calm and readable over flashy. No gradients, no emoji as icons.
- Footer, small and quiet, wording unchanged: "The recordings and notebooks are from
  the Ironhack AI Engineering bootcamp and belong to Ironhack. The copilot is our final
  project for that bootcamp; the code is on GitHub."

## Do not build

- Client-side storage of conversations.
- Your own auth, accounts, or profiles.
