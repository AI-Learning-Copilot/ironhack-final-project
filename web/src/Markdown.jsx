import { openExternal } from "./external.js";

// A deliberately small markdown renderer. Answers, study notes and quizzes all arrive as
// markdown, and pulling in a full parser for headings, lists, bold and code is not worth
// the dependency here — Lovable can swap this for react-markdown in one line if it wants
// tables and footnotes.
function inline(text, key) {
  const parts = [];
  const re = /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("[")) {
      const [, label, href] = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/) || [];
      parts.push(
        <a
          key={parts.length}
          href={href}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => openExternal(e, href)}
        >
          {label}
        </a>
      );
    } else if (tok.startsWith("**")) parts.push(<strong key={parts.length}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={parts.length}>{tok.slice(1, -1)}</code>);
    else parts.push(<em key={parts.length}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <span key={key}>{parts}</span>;
}

export default function Markdown({ text }) {
  const blocks = [];
  let list = null;

  const flush = () => {
    if (list) {
      blocks.push(<ul key={blocks.length}>{list}</ul>);
      list = null;
    }
  };

  String(text || "").split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    if (!line.trim()) return flush();

    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      list = list || [];
      list.push(<li key={i}>{inline(bullet[1], i)}</li>);
      return;
    }
    flush();

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const Tag = `h${Math.min(heading[1].length + 1, 5)}`;
      blocks.push(<Tag key={i}>{inline(heading[2], i)}</Tag>);
      return;
    }
    if (/^>\s?/.test(line)) {
      blocks.push(<blockquote key={i}>{inline(line.replace(/^>\s?/, ""), i)}</blockquote>);
      return;
    }
    blocks.push(<p key={i}>{inline(line, i)}</p>);
  });

  flush();
  return <div className="md">{blocks}</div>;
}
