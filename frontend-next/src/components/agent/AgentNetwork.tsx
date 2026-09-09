"use client";
/**
 * A small link chart the agent can put inside an answer.
 *
 * The big sheet chart is Canvas + ForceAtlas2 and is built for thousands of nodes. This one is
 * SVG for a few dozen: it needs crisp text, hoverable edges and click-through, and at this size
 * a short deterministic force relaxation lays it out in a few milliseconds. Same notation as the
 * sheet - shape carries entity type, line style carries evidence grade, money runs blue - so a
 * reader who has learned the key already reads this.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { DASH, INK, SHAPE, edgeInk, lineStyleFor, relLabel, type Shape } from "@/lib/notation";
import type { NetworkVisual, NetworkNode, NetworkEdge } from "@/lib/agent";
import { cn } from "@/lib/utils";


function glyphPath(s: Shape, x: number, y: number, r: number): string {
  switch (s) {
    case "square": return `M${x - r},${y - r}h${2 * r}v${2 * r}h${-2 * r}z`;
    case "diamond": return `M${x},${y - r * 1.15}L${x + r * 1.15},${y}L${x},${y + r * 1.15}L${x - r * 1.15},${y}z`;
    case "hexagon": return Array.from({ length: 6 }, (_, i) => {
      const a = (Math.PI / 3) * i - Math.PI / 6;
      return `${i ? "L" : "M"}${(x + r * 1.1 * Math.cos(a)).toFixed(2)},${(y + r * 1.1 * Math.sin(a)).toFixed(2)}`;
    }).join("") + "z";
    case "triangle": return `M${x},${y - r * 1.25}L${x + r * 1.15},${y + r * 0.85}L${x - r * 1.15},${y + r * 0.85}z`;
    case "rect": return `M${x - r * 1.4},${y - r * 0.85}h${2.8 * r}v${1.7 * r}h${-2.8 * r}z`;
    case "pin": return `M${x},${y + r * 1.15} C${x - r * 1.25},${y - r * 0.25} ${x - r * 0.95},${y - r * 1.15} ${x},${y - r * 1.15} C${x + r * 0.95},${y - r * 1.15} ${x + r * 1.25},${y - r * 0.25} ${x},${y + r * 1.15}z`;
    case "tag": return `M${x - r * 1.2},${y - r * 0.8}H${x + r * 0.7}L${x + r * 1.3},${y}L${x + r * 0.7},${y + r * 0.8}H${x - r * 1.2}z`;
    case "ring": return `M${x + r},${y} a${r},${r} 0 1,0 ${-2 * r},0 a${r},${r} 0 1,0 ${2 * r},0 M${x + r * 0.45},${y} a${r * 0.45},${r * 0.45} 0 1,0 ${-0.9 * r},0 a${r * 0.45},${r * 0.45} 0 1,0 ${0.9 * r},0`;
    default: return `M${x + r},${y} a${r},${r} 0 1,0 ${-2 * r},0 a${r},${r} 0 1,0 ${2 * r},0`;
  }
}

type Pos = { x: number; y: number };

/** Split the drawing into connected components; each is laid out on its own. */
function components(nodes: NetworkNode[], edges: NetworkEdge[]): NetworkNode[][] {
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    adj.get(e.source)?.push(e.target);
    adj.get(e.target)?.push(e.source);
  }
  const seen = new Set<string>();
  const out: NetworkNode[][] = [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const n of nodes) {
    if (seen.has(n.id)) continue;
    const stack = [n.id], group: NetworkNode[] = [];
    seen.add(n.id);
    while (stack.length) {
      const id = stack.pop()!;
      const node = byId.get(id);
      if (node) group.push(node);
      for (const m of adj.get(id) ?? []) if (!seen.has(m)) { seen.add(m); stack.push(m); }
    }
    out.push(group);
  }
  return out.sort((a, b) => b.length - a.length);
}

/**
 * Deterministic spring relaxation for one component, in its own local coordinate space.
 *
 * Seeded on a circle rather than at random, so the same answer always redraws the same way.
 * Neighbours attract, everything repels; a hub is damped so the sum of its many springs does not
 * fling it across the drawing.
 */
function relax(nodes: NetworkNode[], edges: NetworkEdge[], iterations = 240): Map<string, Pos> {
  const pos = new Map<string, Pos>();
  const n = nodes.length;
  const R = 40 * Math.sqrt(Math.max(n, 1));
  nodes.forEach((nd, i) => {
    const a = (i / Math.max(n, 1)) * Math.PI * 2;
    // radius alternates so a ring of same-degree nodes does not sit on one perfect circle
    pos.set(nd.id, { x: Math.cos(a) * R * (i % 2 ? 0.72 : 1), y: Math.sin(a) * R * (i % 2 ? 0.72 : 1) });
  });
  if (n < 2) return pos;

  const ids = new Set(nodes.map((x) => x.id));
  const local = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const deg = new Map<string, number>();
  for (const e of local) {
    deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
    deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
  }
  const ideal = 74;
  const k2 = ideal * ideal;

  for (let it = 0; it < iterations; it++) {
    const cool = 1 - it / iterations;
    const disp = new Map<string, Pos>(nodes.map((nd) => [nd.id, { x: 0, y: 0 }]));
    for (let i = 0; i < n; i++) {
      const a = pos.get(nodes[i].id)!;
      for (let j = i + 1; j < n; j++) {
        const b = pos.get(nodes[j].id)!;
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = (i - j) * 0.5 + 0.6; dy = 0.4; d2 = dx * dx + dy * dy; }
        const d = Math.sqrt(d2);
        const f = k2 / d2;
        const da = disp.get(nodes[i].id)!, db = disp.get(nodes[j].id)!;
        da.x += (dx / d) * f; da.y += (dy / d) * f;
        db.x -= (dx / d) * f; db.y -= (dy / d) * f;
      }
    }
    for (const e of local) {
      const a = pos.get(e.source)!, b = pos.get(e.target)!;
      const dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = (d * d) / ideal;
      const da = disp.get(e.source)!, db = disp.get(e.target)!;
      da.x -= (dx / d) * f; da.y -= (dy / d) * f;
      db.x += (dx / d) * f; db.y += (dy / d) * f;
    }
    const maxStep = 16 * cool + 1;
    for (const nd of nodes) {
      const p = pos.get(nd.id)!, d = disp.get(nd.id)!;
      const damp = 1 / (1 + (deg.get(nd.id) ?? 0) * 0.3);
      const len = Math.max(Math.hypot(d.x, d.y), 0.01);
      p.x += (d.x / len) * Math.min(len, maxStep) * damp;
      p.y += (d.y / len) * Math.min(len, maxStep) * damp;
    }
  }
  return pos;
}

/**
 * Lay out every component separately, then shelf-pack them.
 *
 * A single force pass over a disconnected graph pushes the pieces apart without limit, so once
 * the result is scaled to fit, each piece has collapsed into an unreadable knot. Packing them
 * like separate details on a drawing gives each one room at a legible scale - the same reason
 * the main sheet chart packs its components.
 */
function layout(nodes: NetworkNode[], edges: NetworkEdge[], W: number): { pos: Map<string, Pos>; height: number } {
  const groups = components(nodes, edges);
  const boxes = groups.map((g) => {
    const p = relax(g, edges);
    const xs = [...p.values()].map((v) => v.x), ys = [...p.values()].map((v) => v.y);
    const minX = Math.min(...xs), minY = Math.min(...ys);
    // a lone node still needs a cell wide enough for its label
    const w = Math.max(Math.max(...xs) - minX, 90), h = Math.max(Math.max(...ys) - minY, 46);
    p.forEach((v) => { v.x -= minX; v.y -= minY; });
    return { pos: p, w, h };
  });

  const gutter = 34;
  const target = Math.max(W - gutter, 240);
  const rows: { items: typeof boxes; w: number; h: number }[] = [];
  let row: typeof boxes = [], rowW = 0, rowH = 0;
  for (const b of boxes) {
    if (row.length && rowW + b.w + gutter > target) {
      rows.push({ items: row, w: rowW, h: rowH });
      row = []; rowW = 0; rowH = 0;
    }
    row.push(b);
    rowW += b.w + gutter;
    rowH = Math.max(rowH, b.h);
  }
  if (row.length) rows.push({ items: row, w: rowW, h: rowH });

  const out = new Map<string, Pos>();
  let y = 0;
  for (const r of rows) {
    let x = 0;
    for (const b of r.items) {
      // centre each component vertically inside its row band
      const dy = y + (r.h - b.h) / 2;
      b.pos.forEach((v, id) => out.set(id, { x: v.x + x, y: v.y + dy }));
      x += b.w + gutter;
    }
    y += r.h + gutter;
  }
  return fit(out, W);
}

/**
 * Scale the packed layout to the available width and report the height it actually needs.
 *
 * The plate is sized to the drawing rather than the drawing squeezed into a fixed plate, so a
 * two-node answer does not sit in a field of empty grid and a big one is not crushed.
 */
function fit(pos: Map<string, Pos>, W: number, pad = 30): { pos: Map<string, Pos>; height: number } {
  const xs = [...pos.values()].map((p) => p.x), ys = [...pos.values()].map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1), spanY = Math.max(maxY - minY, 1);
  const s = Math.min((W - pad * 2) / spanX, (560 - pad * 2) / spanY, 1.6);
  const height = Math.round(Math.min(560, Math.max(220, spanY * s + pad * 2)));
  const ox = (W - spanX * s) / 2 - minX * s;
  const oy = (height - spanY * s) / 2 - minY * s;
  const out = new Map<string, Pos>();
  pos.forEach((p, id) => out.set(id, { x: p.x * s + ox, y: p.y * s + oy }));
  return { pos: out, height };
}

export default function AgentNetwork({ visual, onPick }: { visual: NetworkVisual; onPick?: (id: string) => void }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(680);
  const [hover, setHover] = useState<{ node?: NetworkNode; edge?: NetworkEdge } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, e.contentRect.width)));
    ro.observe(el);
    setW(Math.max(300, el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);

  const { nodes, edges, emphasis } = visual;
  const { pos, height: H } = useMemo(() => layout(nodes, edges, W), [nodes, edges, W]);
  const hot = useMemo(() => new Set(emphasis), [emphasis]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  /* Labels are the first thing to collide. Emphasised marks always keep theirs; everything else
     earns one only while the drawing is still open enough to read, and a label is dropped if it
     would land on one already placed. Hovering a mark always shows its name in the caption bar. */
  const labelled = useMemo(() => {
    const keep = new Set<string>();
    const ranked = [...nodes].sort((a, b) =>
      (hot.has(b.id) ? 1 : 0) - (hot.has(a.id) ? 1 : 0) || b.priority - a.priority || b.degree - a.degree);
    const placed: { x: number; y: number; w: number }[] = [];
    const budget = nodes.length <= 14 ? nodes.length : Math.max(10, Math.round(28 - nodes.length * 0.18));
    for (const n of ranked) {
      if (keep.size >= budget) break;
      const p = pos.get(n.id);
      if (!p) continue;
      const w = Math.min(n.label.length, 22) * 5.2;
      const clash = placed.some((q) => Math.abs(q.y - p.y) < 13 && Math.abs(q.x - p.x) < (q.w + w) / 2 + 6);
      if (clash && !hot.has(n.id)) continue;
      keep.add(n.id);
      placed.push({ x: p.x, y: p.y, w });
    }
    return keep;
  }, [nodes, hot, pos]);

  if (!nodes.length) return <p className="note">Nothing to draw.</p>;

  return (
    <div ref={wrapRef} className="w-full">
      <div className="sheet-ground sheet-ground-fine relative border border-rule-strong">
        <svg width={W} height={H} role="img" aria-label={visual.title} className="block">
          {edges.map((e) => {
            const a = pos.get(e.source), b = pos.get(e.target);
            if (!a || !b) return null;
            const style = lineStyleFor(undefined, e.confidence);
            const isHot = hot.has(e.source) && hot.has(e.target);
            const dim = hover?.node && e.source !== hover.node.id && e.target !== hover.node.id;
            return (
              <g key={e.id} onMouseEnter={() => setHover({ edge: e })} onMouseLeave={() => setHover(null)}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={10} />
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={hover?.edge?.id === e.id ? INK.pencil : edgeInk(e.rel_type)}
                      strokeWidth={Math.min(3.2, 0.9 + Math.log1p(e.count) * 0.55)}
                      strokeDasharray={DASH[style].join(" ") || undefined}
                      opacity={dim ? 0.16 : isHot ? 0.95 : 0.55} />
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = pos.get(n.id)!;
            const isHot = hot.has(n.id);
            const r = (n.type === "PERSON" || n.type === "ORGANIZATION" ? 6 + Math.min(n.priority, 1) * 7 : 4.6);
            const dim = hover?.node && hover.node.id !== n.id &&
              !edges.some((e) => (e.source === n.id && e.target === hover.node!.id) || (e.target === n.id && e.source === hover.node!.id));
            const ink = isHot ? INK.pencil : n.type === "BANK_ACCOUNT" ? INK.blue : INK.ink;
            return (
              <g key={n.id} className="cursor-pointer" opacity={dim ? 0.3 : 1}
                 onMouseEnter={() => setHover({ node: n })} onMouseLeave={() => setHover(null)}
                 onClick={() => onPick?.(n.id)}
                 role="button" tabIndex={0} aria-label={`${n.label}, ${n.type.toLowerCase()}`}
                 onKeyDown={(ev) => { if (ev.key === "Enter") onPick?.(n.id); }}>
                <path d={glyphPath(SHAPE[n.type], p.x, p.y, r)} fill={isHot ? INK.pencilSoft : INK.film}
                      stroke={ink} strokeWidth={isHot ? 2 : 1.4} strokeLinejoin="round" fillRule="evenodd" />
                {labelled.has(n.id) && (
                  <text x={p.x} y={p.y + r + 11} textAnchor="middle" fontSize={10.5}
                        fill={isHot ? INK.pencil : INK.inkSoft} fontWeight={isHot ? 600 : 400}
                        stroke={INK.film} strokeWidth={2.6} paintOrder="stroke" style={{ pointerEvents: "none" }}>
                    {n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-2">
          <p className="note-paper max-w-[70%] px-2 py-1 text-[var(--fs-note)] leading-snug">
            {hover?.node ? (
              <>
                <strong className="font-semibold">{hover.node.label}</strong>{" "}
                <span className="text-ink-faint">{hover.node.type.toLowerCase().replace("_", " ")}</span>
                {hover.node.role && <> · {hover.node.role}</>}
                {hover.node.suspicion > 0 && <> · suspicion <span className="figure">{hover.node.suspicion.toFixed(2)}</span></>}
              </>
            ) : hover?.edge ? (
              <>
                <strong className="font-semibold">{byId.get(hover.edge.source)?.label}</strong> {relLabel(hover.edge.rel_type)}{" "}
                <strong className="font-semibold">{byId.get(hover.edge.target)?.label}</strong>
                {hover.edge.count > 1 && <span className="figure"> · {hover.edge.count}×</span>}
              </>
            ) : (
              <span className="text-ink-faint">
                {nodes.length} entities · {edges.length} links · hover a mark, click to open it
              </span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
