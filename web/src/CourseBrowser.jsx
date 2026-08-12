import { useState } from "react";
import { api } from "./api.js";
import Markdown from "./Markdown.jsx";

function duration(seconds) {
  // Round to whole minutes first, then split. Flooring the hours before rounding the
  // remainder produced "4h 60m" for anything within 30 seconds of the next hour.
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

// Hand-written because nothing in the data can produce it: lessons.json carries per-day
// titles, and a week's five titles concatenated run to several hundred characters.
// "Week 4" alone tells a student nothing; "Week 4 · NLP & embeddings" does.
const WEEK_THEMES = {
  1: "Python & data",
  2: "Machine learning",
  3: "Deep learning & vision",
  4: "NLP & embeddings",
  5: "Databases & LLM APIs",
  6: "Deployment",
  7: "LangChain & RAG",
  8: "Multimodal & evaluation",
};

export default function CourseBrowser({ weeks, scope, onScope }) {
  const [openLesson, setOpenLesson] = useState(null);
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(null);

  async function toggle(lesson) {
    if (openLesson === lesson.lesson_id) return setOpenLesson(null);
    setOpenLesson(lesson.lesson_id);

    if (!notes[lesson.lesson_id] && lesson.has_notes) {
      setLoading(lesson.lesson_id);
      try {
        const d = await api.notes(lesson.lesson_id);
        setNotes((n) => ({ ...n, [lesson.lesson_id]: d.markdown }));
      } catch {
        setNotes((n) => ({ ...n, [lesson.lesson_id]: "_Study notes could not be loaded._" }));
      } finally {
        setLoading(null);
      }
    }
  }

  return (
    <div className="browser">
      <div className="browser-head">
        <h2>The course</h2>
        <a className="pdf-link" href={api.syllabusPdfUrl()} target="_blank" rel="noreferrer">
          Full syllabus (PDF)
        </a>
      </div>

      {weeks.map(({ week, lessons }) => {
        const scoped = scope.active && scope.week === week && !scope.lesson_id;
        return (
          <section key={week} className="week">
            <div className="week-head">
              <h3>
                Week {week} <span className="week-theme">{WEEK_THEMES[week] || ""}</span>
              </h3>
              <button
                className={`scope-btn ${scoped ? "on" : ""}`}
                onClick={() => onScope(scoped ? {} : { week })}
                title="Restrict every answer to this week"
              >
                {scoped ? "Searching this week only" : "Search only this week"}
              </button>
            </div>

            <ul className="lessons">
              {lessons.map((l) => {
                const open = openLesson === l.lesson_id;
                const lessonScoped = scope.active && scope.lesson_id === l.lesson_id;
                return (
                  <li key={l.lesson_id} className={open ? "open" : ""}>
                    <div className="lesson-row">
                      <button className="lesson-main" onClick={() => toggle(l)} aria-expanded={open}>
                        <span className="lesson-id">{l.lesson_id}</span>
                        <span className="lesson-title">{l.title}</span>
                        <span className="lesson-meta">
                          {l.recordings} rec · {duration(l.duration_seconds)}
                        </span>
                      </button>
                      <button
                        className={`scope-btn small ${lessonScoped ? "on" : ""}`}
                        onClick={() => onScope(lessonScoped ? {} : { lesson_id: l.lesson_id })}
                        title="Restrict every answer to this lesson"
                      >
                        {lessonScoped ? "scoped" : "scope"}
                      </button>
                    </div>

                    {open && (
                      <div className="lesson-body">
                        {l.videos?.length > 0 && (
                          <div className="resource-group">
                            <h4>Recordings</h4>
                            <ul className="resources">
                              {l.videos.map((v) => (
                                <li key={v.url}>
                                  <a href={v.url} target="_blank" rel="noreferrer">
                                    <span className="res-kind">video</span>
                                    <span className="res-text">{v.title || v.segment}</span>
                                    <span className="res-meta">{duration(v.duration_seconds)}</span>
                                  </a>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {l.notebooks?.length > 0 && (
                          <div className="resource-group">
                            <h4>Notebooks</h4>
                            <ul className="resources">
                              {l.notebooks.map((n) => (
                                <li key={n.url}>
                                  <a href={n.url} target="_blank" rel="noreferrer">
                                    <span className="res-kind">code</span>
                                    <span className="res-text">{n.path}</span>
                                    <span className="res-meta">↗</span>
                                  </a>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        <div className="resource-group">
                          <h4>Study notes</h4>
                          {!l.has_notes && <p className="hint">None for this day.</p>}
                          {l.has_notes && loading === l.lesson_id && <p className="hint">Loading…</p>}
                          {l.has_notes && notes[l.lesson_id] && (
                            <>
                              <a className="pdf-link" href={api.notesPdfUrl(l.lesson_id)} target="_blank" rel="noreferrer">
                                Download as PDF ↗
                              </a>
                              <Markdown text={notes[l.lesson_id]} />
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
