import { useEffect, useRef, useState } from "react";
import Markdown from "./Markdown.jsx";
import { openExternal } from "./external.js";

// Citations arrive pre-labelled with a working URL. Nothing here composes either one —
// build_citation already handled Loom's `?t=` and the `Extra ·` prefix for supplementary
// notebooks, and a second implementation would get them subtly wrong.
function Citation({ c }) {
  const [open, setOpen] = useState(false);
  const isVideo = c.source_type === "video";

  // Only videos expand. A notebook has nothing to embed, so hiding its GitHub link
  // behind a click was pure friction — it is a link, so it is rendered as one.
  if (!isVideo) {
    return (
      <li className="citation">
        <a
          className="citation-label"
          href={c.url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => openExternal(e, c.url)}
        >
          <span className="citation-kind">notebook</span>
          <span className="citation-text">{c.label}</span>
          <span className="citation-chevron">↗</span>
        </a>
      </li>
    );
  }

  return (
    <li className="citation">
      <button className="citation-label" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="citation-kind">video</span>
        <span className="citation-text">{c.label}</span>
        <span className="citation-chevron">{open ? "−" : "▶"}</span>
      </button>

      {open && (
        <>
          <div className="embed">
            <iframe src={c.url} title={c.label} allowFullScreen />
          </div>
          {/* The same recording covers the topic at these points too. Kept out of the
              citation list because they are not separate sources — five entries for one
              lecture buried whatever else was found. */}
          {c.also_at?.length > 0 && (
            <p className="also-at">
              Also covered at{" "}
              {c.also_at.map((a, i) => (
                <span key={a.url}>
                  {i > 0 && ", "}
                  <a href={a.url} target="_blank" rel="noreferrer" onClick={(e) => openExternal(e, a.url)}>
                    {a.label.split(" · ").pop()}
                  </a>
                </span>
              ))}
            </p>
          )}
        </>
      )}
    </li>
  );
}

// An answer takes about five seconds and there is no streaming, so the wait has to be
// carried by the UI or the app reads as broken. A counter plus a changing line is enough:
// what makes dead time feel broken is the absence of change, not the duration.
const STAGES = [
  "Searching 6,037 passages…",
  "Reading the retrieved lessons…",
  "Writing an answer from what it found…",
];

function Thinking() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 0.1), 100);
    return () => clearInterval(t);
  }, []);
  const stage = STAGES[Math.min(Math.floor(elapsed / 2.5), STAGES.length - 1)];

  return (
    <div className="turn copilot thinking-turn">
      <p className="thinking">
        <span className="dots"><i /><i /><i /></span>
        {stage}
      </p>
      <p className="meta">{elapsed.toFixed(1)}s</p>
    </div>
  );
}

// A refusal is a first-class response, not an error: the course simply does not cover it.
// The backend guarantees zero citations in that case so a refusal can never look sourced,
// and this styles it calmly rather than as a failure.
function isRefusal(turn) {
  if (turn.citations?.length) return false;
  return /wasn't covered|was not covered|no fue cubierto|no está cubierto/i.test(turn.text || "");
}

export default function Chat({ turns, busy, error, onAsk, scopeLabel }) {
  const [question, setQuestion] = useState("");
  const bottom = useRef(null);

  // Block body, not a concise arrow. React calls whatever an effect returns as its
  // cleanup, and browser extensions that patch scrollIntoView can return a promise —
  // which unmounts the whole tree with "n is not a function".
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  function submit(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    onAsk(q);
  }

  return (
    <>
      <div className="stream">
        {turns.length === 0 && (
          <div className="empty">
            <h2>Ask the bootcamp a question</h2>
            <p>
              Every answer comes from the course's own recordings and notebooks, with the
              lesson and the video cued to the second.
            </p>
            <div className="suggestions">
              {["What is an embedding?", "How does CLIP work?", "Which lesson explained LangChain memory?"].map((s) => (
                <button key={s} onClick={() => onAsk(s)} disabled={busy}>{s}</button>
              ))}
            </div>
            <p className="hint">
              Follow-ups work — ask <em>“And where was it covered?”</em> after any answer.
            </p>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="turn user"><p>{t.text}</p></div>
          ) : (
            <div key={i} className={`turn copilot ${isRefusal(t) ? "refusal" : ""}`}>
              {isRefusal(t) && (
                <p className="refusal-tag">
                  {/* A scoped refusal means "not in THIS week", which is a different fact
                      from "not in the course" — the student chose the filter and the tag
                      should not contradict the answer underneath it. */}
                  Not covered in {scopeLabel || "the course"}
                </p>
              )}
              <Markdown text={t.text} />
              {t.citations?.length > 0 && (
                <ul className="citations">
                  {t.citations.map((c, j) => <Citation key={j} c={c} />)}
                </ul>
              )}

              {/* Kept visually separate from the citations above. These did not ground
                  the answer — they are the code for the same topic, found by a second
                  retrieval, and presenting them as sources would be a lie. */}
              {t.related_notebooks?.length > 0 && (
                <div className="related">
                  <h4>Notebooks on this topic</h4>
                  <ul className="citations">
                    {t.related_notebooks.map((c, j) => <Citation key={j} c={c} />)}
                  </ul>
                </div>
              )}
              <p className="meta">{t.elapsed}s</p>
            </div>
          )
        )}

        {busy && <Thinking />}
        {error && <p className="error">{error}</p>}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={scopeLabel ? `Ask about ${scopeLabel}…` : "Ask about the course…"}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || !question.trim()}>Ask</button>
      </form>
    </>
  );
}
