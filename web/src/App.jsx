import { useEffect, useRef, useState } from "react";

// The API returns citations that are already labelled and already carry a working URL —
// `build_citation` in schemas.py does that, and it is the reason this component can
// render a Loom embed without knowing anything about Loom's `?t=` parameter. Same
// contract the Streamlit UI consumes; the frontend language is the only thing that
// changed.
function Citation({ c }) {
  const [open, setOpen] = useState(false);
  const isVideo = c.source_type === "video";

  return (
    <li className="citation">
      <button className="citation-label" onClick={() => setOpen(!open)}>
        <span className="citation-kind">{isVideo ? "video" : "notebook"}</span>
        {c.label}
      </button>

      {open && isVideo && (
        <div className="embed">
          <iframe src={c.url} title={c.label} allowFullScreen />
        </div>
      )}
      {open && !isVideo && (
        <a className="notebook-link" href={c.url} target="_blank" rel="noreferrer">
          Open the notebook →
        </a>
      )}
    </li>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const bottom = useRef(null);

  useEffect(() => {
    fetch("/api/session", { method: "POST" })
      .then((r) => r.json())
      .then((d) => setSessionId(d.session_id))
      .catch(() => setError("Could not reach the API. Is uvicorn running on port 8000?"));
  }, []);

  // Block body, not a concise arrow. Whatever an effect returns, React calls as the
  // cleanup function — so returning the result of scrollIntoView is only safe while that
  // result is undefined. Browser extensions and smooth-scroll polyfills patch
  // scrollIntoView and some of them return a promise, at which point React tries to call
  // it and the whole tree unmounts with "n is not a function". The braces make the
  // return value unconditionally undefined.
  //
  // `block: "nearest"` keeps the scroll inside <main>, which is the scroll container.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  async function ask(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;

    setQuestion("");
    setBusy(true);
    setError(null);
    setTurns((t) => [...t, { role: "user", text: q }]);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, session_id: sessionId }),
      });
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      setSessionId(d.session_id);
      setTurns((t) => [
        ...t,
        {
          role: "copilot",
          text: d.answer,
          citations: d.citations,
          elapsed: d.elapsed_seconds,
          rehydrated: d.rehydrated,
        },
      ]);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  // Drops the live Copilot server-side while keeping the conversation. The next answer
  // has to be produced by one rebuilt from stored state, which is what a follow-up hits
  // when it lands on a replica that never saw the first question. This button is the
  // experiment, not a feature.
  async function evict() {
    if (!sessionId) return;
    await fetch(`/api/session/${sessionId}/evict`, { method: "POST" });
    setTurns((t) => [...t, { role: "system", text: "Live copilot evicted. The next answer must be rebuilt from stored state." }]);
  }

  return (
    <div className="app">
      <header>
        <h1>Ironhack AI Course Copilot</h1>
        <p className="sub">React frontend · FastAPI · same agent, same index</p>
        <button className="ghost" onClick={evict} disabled={!turns.length}>
          Simulate a cold replica
        </button>
      </header>

      <main>
        {turns.length === 0 && (
          <div className="empty">
            <p>Ask about anything taught in the bootcamp.</p>
            <p className="hint">
              Try <em>“What is an embedding?”</em>, then follow up with{" "}
              <em>“And where was it covered?”</em>
            </p>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className={`turn ${t.role}`}>
            {t.role === "system" ? (
              <p className="system-note">{t.text}</p>
            ) : (
              <>
                <p className="text">{t.text}</p>
                {t.citations?.length > 0 && (
                  <ul className="citations">
                    {t.citations.map((c, j) => (
                      <Citation key={j} c={c} />
                    ))}
                  </ul>
                )}
                {t.role === "copilot" && (
                  <p className="meta">
                    {t.elapsed}s{t.rehydrated && <span className="badge">rebuilt from stored state</span>}
                  </p>
                )}
              </>
            )}
          </div>
        ))}

        {busy && <div className="turn copilot"><p className="text thinking">Searching 6,037 passages…</p></div>}
        {error && <p className="error">{error}</p>}
        <div ref={bottom} />
      </main>

      <form onSubmit={ask}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about the course…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !question.trim()}>Ask</button>
      </form>
    </div>
  );
}
