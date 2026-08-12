// Opening an external link is not as simple as target="_blank".
//
// A plain target="_blank" anchor silently does nothing in some browsers: popup blockers
// and extensions can suppress the new tab, and the click then has no effect at all —
// which reads as a broken link rather than a blocked one. Measured here: a synthetic
// anchor click opened no tab, so it is not a markup problem.
//
// So: try a new tab, and only if the browser truly refused, navigate in this one.
//
// The subtlety that cost a round trip. `window.open(url, "_blank", "noopener")` returns
// null BY SPECIFICATION, whether or not the tab opened. Treating that null as "blocked"
// meant the fallback fired on every click, so a link opened a new tab AND navigated the
// current one. Passing no feature string returns a real window handle, which is the only
// way to tell success from refusal. The opener reference is then severed by hand, which
// is what the "noopener" flag would have done.
export function openExternal(event, url) {
  // Let the browser handle modified clicks (cmd, ctrl, shift, middle) itself.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;

  event.preventDefault();

  let opened = null;
  try {
    opened = window.open(url, "_blank");
  } catch {
    opened = null;
  }

  if (opened) {
    // Same protection rel="noopener" gives, without the null return that hides whether
    // the tab actually opened.
    try {
      opened.opener = null;
    } catch {
      /* cross-origin already severed it */
    }
    return;
  }

  // Genuinely blocked: a link that takes over the page beats one that does nothing.
  window.location.href = url;
}
