"use client";
/** Minimal markdown for assistant answers and the brief: bold, italic, lists, headings, tables. No HTML passthrough. */
import { Fragment } from "react";

function inline(s: string, key: string) {
  const parts = s.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((p, i) => {
    if (p.startsWith("**")) return <strong key={key + i} className="font-semibold text-ink">{p.slice(2, -2)}</strong>;
    if (p.startsWith("*")) return <em key={key + i}>{p.slice(1, -1)}</em>;
    if (p.startsWith("`")) return <code key={key + i} className="figure rounded-[2px] bg-film-deep px-1">{p.slice(1, -1)}</code>;
    return <Fragment key={key + i}>{p}</Fragment>;
  });
}

export default function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.split(/\r?\n/);
  const out: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    if (l.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) { const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()); if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells); i++; }
      out.push(<div key={i} className="my-2 overflow-x-auto"><table className="w-full border-collapse text-[length:var(--fs-note)]"><thead><tr>{rows[0]?.map((c, j) => <th key={j} className="label border-b border-ink px-2 py-1 text-left">{inline(c, `h${j}`)}</th>)}</tr></thead><tbody>{rows.slice(1).map((r, ri) => <tr key={ri} className="border-b border-rule">{r.map((c, j) => <td key={j} className="figure px-2 py-1 align-top">{inline(c, `c${ri}${j}`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(l);
    if (h) { const lvl = h[1].length; out.push(lvl === 1 ? <h1 key={i} className="mt-4 text-[length:var(--fs-sheet)] font-semibold leading-tight">{inline(h[2], `H${i}`)}</h1> : lvl === 2 ? <h2 key={i} className="label label-ink mt-4 border-b border-rule-strong pb-1">{inline(h[2], `H${i}`)}</h2> : <h3 key={i} className="mt-3 font-semibold">{inline(h[2], `H${i}`)}</h3>); i++; continue; }
    if (/^\s*(?:[-*]|\d+\.)\s+/.test(l)) {
      const items: string[] = []; const ordered = /^\s*\d+\./.test(l);
      while (i < lines.length && /^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, "")); i++; }
      out.push(ordered ? <ol key={i} className="my-1.5 list-decimal space-y-1 pl-5">{items.map((it, j) => <li key={j}>{inline(it, `o${i}${j}`)}</li>)}</ol> : <ul key={i} className="my-1.5 list-disc space-y-1 pl-5">{items.map((it, j) => <li key={j}>{inline(it, `u${i}${j}`)}</li>)}</ul>);
      continue;
    }
    if (l.startsWith("---")) { out.push(<hr key={i} className="my-3 border-rule-strong" />); i++; continue; }
    out.push(<p key={i} className="my-1.5 leading-relaxed">{inline(l, `p${i}`)}</p>); i++;
  }
  return <div className={className}>{out}</div>;
}
