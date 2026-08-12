import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";
import "./styles.css";

// Errors thrown outside React's render path (an async handler, a rejected promise) never
// reach the error boundary. Surface those on the page too, for the same reason.
function showGlobal(kind, detail) {
  const el = document.createElement("pre");
  el.className = "global-error";
  el.textContent = `${kind}: ${detail}`;
  document.body.appendChild(el);
}
window.addEventListener("error", (e) => showGlobal("error", e.message + " @ " + e.filename + ":" + e.lineno));
window.addEventListener("unhandledrejection", (e) => showGlobal("unhandled promise", String(e.reason)));

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
