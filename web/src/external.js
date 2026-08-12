// Opening an external link is not as simple as target="_blank".
//
// A plain target="_blank" anchor silently does nothing in some browsers: popup blockers
// and extensions can suppress the new tab, and the click then has no effect at all —
// which reads as a broken link rather than a blocked one. Measured here: a synthetic
// anchor click opened no tab, so it is not a markup problem.
//
// So: try a new tab, and if the browser refuses, navigate in this one. A link that
// takes over the page is worse than a new tab, but far better than a link that does
// nothing. The href stays on the anchor so right-click, copy and middle-click all
// still behave normally.
export function openExternal(event, url) {
  // Let the browser handle modified clicks (cmd, ctrl, shift, middle) itself.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;

  event.preventDefault();
  let opened = null;
  try {
    opened = window.open(url, "_blank", "noopener,noreferrer");
  } catch {
    opened = null;
  }
  if (!opened) window.location.href = url;
}
