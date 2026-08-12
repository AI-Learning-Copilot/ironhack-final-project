import { useState } from "react";
import { api } from "./api.js";

// The API returns a quiz as markdown: question, four A–D options, then "Answer: B".
// Parsing it here rather than asking the model for JSON keeps the tool's output identical
// to the one the Streamlit app renders, and the format is fixed enough to split on.
function parseQuiz(markdown) {
  const questions = [];
  let current = null;

  for (const raw of String(markdown || "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;

    const option = line.match(/^([A-D])\)\s*(.*)$/);
    const answer = line.match(/^Answer:\s*([A-D])/i);

    if (answer) {
      if (current) current.answer = answer[1].toUpperCase();
      continue;
    }
    if (option) {
      if (current) current.options.push({ key: option[1], text: option[2] });
      continue;
    }
    current = { prompt: line.replace(/^\d+[.)]\s*/, ""), options: [], answer: null };
    questions.push(current);
  }
  return questions.filter((q) => q.options.length > 0);
}

export default function QuizPanel({ sessionId, scopeLabel }) {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(3);
  const [questions, setQuestions] = useState(null);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function generate(e) {
    e.preventDefault();
    if (!topic.trim() || busy) return;
    setBusy(true);
    setError(null);
    setQuestions(null);
    setPicked({});
    try {
      const d = await api.quiz(sessionId, topic.trim(), count);
      const parsed = parseQuiz(d.markdown);
      if (!parsed.length) throw new Error("The quiz came back in an unexpected shape.");
      setQuestions(parsed);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  const scored = questions?.filter((q, i) => picked[i]).length || 0;
  const correct = questions?.filter((q, i) => picked[i] === q.answer).length || 0;

  return (
    <div className="quiz">
      <h2>Quiz yourself</h2>
      <p className="hint">
        Questions are written from the course material only
        {scopeLabel ? `, and right now only from ${scopeLabel}` : ""}.
      </p>

      <form onSubmit={generate} className="quiz-form">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="A topic — RAG, embeddings, overfitting…"
          disabled={busy}
        />
        <select value={count} onChange={(e) => setCount(Number(e.target.value))} disabled={busy}>
          {[2, 3, 5].map((n) => <option key={n} value={n}>{n} questions</option>)}
        </select>
        <button type="submit" disabled={busy || !topic.trim()}>
          {busy ? "Writing…" : "Generate"}
        </button>
      </form>

      {busy && <p className="hint">This one takes about ten seconds — it writes and then shuffles the options.</p>}
      {error && <p className="error">{error}</p>}

      {questions && (
        <>
          {scored > 0 && (
            <p className="score">
              {correct} of {scored} correct
            </p>
          )}
          <ol className="questions">
            {questions.map((q, i) => (
              <li key={i}>
                <p className="q-prompt">{q.prompt}</p>
                <ul className="options">
                  {q.options.map((o) => {
                    const chosen = picked[i] === o.key;
                    const revealed = Boolean(picked[i]);
                    const right = o.key === q.answer;
                    return (
                      <li key={o.key}>
                        <button
                          className={`option ${chosen ? "chosen" : ""} ${revealed && right ? "right" : ""} ${
                            revealed && chosen && !right ? "wrong" : ""
                          }`}
                          disabled={revealed}
                          onClick={() => setPicked((p) => ({ ...p, [i]: o.key }))}
                        >
                          <span className="option-key">{o.key}</span>
                          {o.text}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
