import { useEffect, useState } from "react";
import { api } from "./api.js";
import Chat from "./Chat.jsx";
import CourseBrowser from "./CourseBrowser.jsx";
import QuizPanel from "./QuizPanel.jsx";

const EMPTY_SCOPE = { active: false, label: "", lesson_id: "", week: null };

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("chat");
  const [weeks, setWeeks] = useState([]);
  const [scope, setScope] = useState(EMPTY_SCOPE);

  useEffect(() => {
    api.newSession()
      .then((d) => setSessionId(d.session_id))
      .catch(() => setError("Could not reach the API. Is uvicorn running on port 8000?"));
    api.lessons().then((d) => setWeeks(d.weeks)).catch(() => {});
  }, []);

  async function ask(question) {
    setBusy(true);
    setError(null);
    setTurns((t) => [...t, { role: "user", text: question }]);
    try {
      const d = await api.ask(question, sessionId);
      setSessionId(d.session_id);
      setTurns((t) => [
        ...t,
        {
          role: "copilot",
          text: d.answer,
          citations: d.citations,
          related_notebooks: d.related_notebooks,
          elapsed: d.elapsed_seconds,
        },
      ]);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  // The scope is set on the retrieval side rather than worded into the question, so it
  // holds for the whole conversation until cleared. Switching back to chat on change is
  // deliberate: a filter only shows its effect in an answer.
  async function changeScope(body) {
    if (!sessionId) return;
    try {
      setScope(await api.scope(sessionId, body));
      setTab("chat");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function reset() {
    if (!sessionId) return;
    await api.reset(sessionId).catch(() => {});
    setTurns([]);
    setScope(EMPTY_SCOPE);
    setError(null);
  }

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>AI Course Copilot</h1>
          <p className="sub">Answers from the bootcamp's own recordings and notebooks</p>
        </div>
        <nav>
          {[["chat", "Ask"], ["course", "Course"], ["quiz", "Quiz"]].map(([key, label]) => (
            <button key={key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      {scope.active && (
        <div className="scope-bar">
          <span>
            Searching <strong>{scope.label}</strong> only — anything outside it will say so.
          </span>
          <button onClick={() => changeScope({})}>Search all 8 weeks</button>
        </div>
      )}

      <main className={tab === "chat" ? "chat-main" : ""}>
        {tab === "chat" && (
          <Chat
            turns={turns}
            busy={busy}
            error={error}
            onAsk={ask}
            scopeLabel={scope.active ? scope.label : ""}
          />
        )}
        {tab === "course" && <CourseBrowser weeks={weeks} scope={scope} onScope={changeScope} />}
        {tab === "quiz" && <QuizPanel sessionId={sessionId} scopeLabel={scope.active ? scope.label : ""} />}
      </main>

      {tab === "chat" && turns.length > 0 && (
        <footer>
          <button className="ghost" onClick={reset}>Start a new conversation</button>
        </footer>
      )}
    </div>
  );
}
