// One place that knows the endpoint shapes. Everything else takes plain objects, so a
// restyle never has to touch fetch code.

async function call(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export const api = {
  newSession: () => call("/api/session", { method: "POST" }),
  lessons: () => call("/api/lessons"),
  notes: (id) => call(`/api/lessons/${id}/notes`),
  notesPdfUrl: (id) => `/api/lessons/${id}/notes.pdf`,
  syllabusPdfUrl: () => "/api/syllabus.pdf",
  ask: (question, sessionId) => call("/api/ask", { method: "POST", body: { question, session_id: sessionId } }),
  scope: (sessionId, body) => call(`/api/session/${sessionId}/scope`, { method: "POST", body }),
  quiz: (sessionId, topic, numQuestions, scope = {}) =>
    call(`/api/session/${sessionId}/quiz`, {
      method: "POST",
      body: { topic, num_questions: numQuestions, ...scope },
    }),
  reset: (sessionId) => call(`/api/session/${sessionId}/reset`, { method: "POST" }),
};
