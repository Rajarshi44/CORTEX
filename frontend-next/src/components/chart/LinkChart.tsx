"use client";
/**
 * The drafted link chart. Canvas 2D on purpose: the notation needs true dashed and dotted
 * strokes and six node shapes, which Sigma's WebGL edge programs do not provide. graphology
 * holds the graph and ForceAtlas2 lays it out; this file draws it in technical-pen ink.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type { EdgeView, NodeView } from "@/lib/types";
import { DASH, INK, SHAPE, edgeInk, lineStyleFor, nodeRadius, relLabel, type Shape } from "@/lib/notation";
import { useSheet } from "@/lib/store";

export interface ChartProps {
  nodes: NodeView[];
  edges: EdgeView[];
  onSelect?: (id: string | null) => void;
  onHover?: (hit: { node?: NodeView; edge?: EdgeView } | null) => void;
  /** ids to keep bright; everything else recedes to faint ink */
  emphasis?: string[];
  route?: string[] | null;
  className?: string;
  /** label every person/organisation at rest (small charts), not only persons of interest */
  labelAll?: boolean;
}

type Pos = { x: number; y: number };
type Cam = { x: number; y: number; k: number };
const INFRA = new Set(["PHONE", "BANK_ACCOUNT", "SOCIAL_HANDLE", "VEHICLE", "GOV_ID", "LOCATION"]);

function drawShape(ctx: CanvasRenderingContext2D, s: Shape, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (s) {
    case "circle": ctx.arc(x, y, r, 0, Math.PI * 2); break;
    case "square": ctx.rect(x - r, y - r, r * 2, r * 2); break;
    case "diamond": ctx.moveTo(x, y - r * 1.15); ctx.lineTo(x + r * 1.15, y); ctx.lineTo(x, y + r * 1.15); ctx.lineTo(x - r * 1.15, y); ctx.closePath(); break;
    case "hexagon": for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i - Math.PI / 6; const px = x + r * 1.1 * Math.cos(a), py = y + r * 1.1 * Math.sin(a); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.closePath(); break;
    case "triangle": ctx.moveTo(x, y - r * 1.25); ctx.lineTo(x + r * 1.15, y + r * 0.85); ctx.lineTo(x - r * 1.15, y + r * 0.85); ctx.closePath(); break;
    case "rect": ctx.rect(x - r * 1.4, y - r * 0.85, r * 2.8, r * 1.7); break;
    case "pin": ctx.moveTo(x, y + r * 1.2); ctx.arc(x, y - r * 0.2, r * 0.9, Math.PI * 0.85, Math.PI * 2.15); ctx.closePath(); break;
    case "tag": ctx.moveTo(x - r * 1.2, y - r * 0.8); ctx.lineTo(x + r * 0.7, y - r * 0.8); ctx.lineTo(x + r * 1.3, y); ctx.lineTo(x + r * 0.7, y + r * 0.8); ctx.lineTo(x - r * 1.2, y + r * 0.8); ctx.closePath(); break;
    case "ring": ctx.arc(x, y, r, 0, Math.PI * 2); ctx.moveTo(x + r * 0.5, y); ctx.arc(x, y, r * 0.5, 0, Math.PI * 2, true); break;
  }
}

/**
 * Force layouts push disconnected components apart without limit, so a sheet of many small
 * networks ends up as dust on an enormous canvas. Shelf-pack the components instead: largest
 * first, top-left, in rows, with a fixed gutter, the way separate details are arranged on a drawing.
 */
function packComponents(g: Graph, pos: Map<string, Pos>, aspect = 1.6) {
  const comp = new Map<string, number>();
  const groups: string[][] = [];
  g.forEachNode((id) => {
    if (comp.has(id)) return;
    const stack = [id], members: string[] = [];
    comp.set(id, groups.length);
    while (stack.length) { const n = stack.pop()!; members.push(n); g.forEachNeighbor(n, (m) => { if (!comp.has(m)) { comp.set(m, groups.length); stack.push(m); } }); }
    groups.push(members);
  });
  if (groups.length < 2) return;
  const GAP = 28, PAD = 14;
  const boxes = groups.map((members) => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const m of members) { const p = pos.get(m)!; minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); }
    return { members, minX, minY, w: maxX - minX + PAD * 2, h: maxY - minY + PAD * 2 };
  }).sort((a, b) => b.h * b.w - a.h * a.w);
  const area = boxes.reduce((s, b) => s + (b.w + GAP) * (b.h + GAP), 0);
  const maxW = Math.max(boxes[0].w, Math.sqrt(area * aspect) * 1.15);
  let x = 0, y = 0, shelf = 0;
  for (const b of boxes) {
    if (x > 0 && x + b.w > maxW) { x = 0; y += shelf + GAP; shelf = 0; }
    for (const m of b.members) { const p = pos.get(m)!; pos.set(m, { x: p.x - b.minX + PAD + x, y: p.y - b.minY + PAD + y }); }
    x += b.w + GAP; shelf = Math.max(shelf, b.h);
  }
}

/** Deterministic pseudo-random so a re-render lays the same graph out the same way. */
function seeded(id: string) { let h = 2166136261; for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; }

export default function LinkChart({ nodes, edges, onSelect, onHover, emphasis, route, className, labelAll = false }: ChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const posRef = useRef<Map<string, Pos>>(new Map());
  const camRef = useRef<Cam>({ x: 0, y: 0, k: 1 });
  const dragRef = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const hoverRef = useRef<{ node?: string; edge?: string } | null>(null);
  const rafRef = useRef<number>(0);
  const selected = useSheet((s) => s.selected);
  const presentation = useSheet((s) => s.presentation);
  const [layoutKey, setLayoutKey] = useState(0);

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const edgeById = useMemo(() => new Map(edges.map((e) => [e.id, e])), [edges]);
  const emphasisSet = useMemo(() => new Set(emphasis ?? []), [emphasis]);
  const routeSet = useMemo(() => {
    const s = new Set<string>();
    if (route) for (let i = 0; i < route.length - 1; i++) { s.add(`${route[i]}|${route[i + 1]}`); s.add(`${route[i + 1]}|${route[i]}`); }
    return s;
  }, [route]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of edges) {
      (m.get(e.source) ?? m.set(e.source, new Set()).get(e.source)!).add(e.target);
      (m.get(e.target) ?? m.set(e.target, new Set()).get(e.target)!).add(e.source);
    }
    return m;
  }, [edges]);
  const maxW = useMemo(() => Math.max(1, ...edges.map((e) => e.weight)), [edges]);

  const fitToView = useCallback(() => {
    const c = canvasRef.current; if (!c || !posRef.current.size) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    posRef.current.forEach((p) => { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); });
    const w = c.clientWidth, h = c.clientHeight;
    const pad = 90;
    const k = Math.min((w - pad * 2) / Math.max(1, maxX - minX), (h - pad * 2) / Math.max(1, maxY - minY), 2.4);
    camRef.current = { k, x: w / 2 - ((minX + maxX) / 2) * k, y: h / 2 - ((minY + maxY) / 2) * k };
  }, []);

  // ------------------------------------------------------------ layout
  useEffect(() => {
    if (!nodes.length) { posRef.current = new Map(); return; }
    const g = new Graph({ multi: false, type: "undirected" });
    const prev = posRef.current;
    // random seed (deterministic per id) spread over a disc: a circular seed never converges
    // for a dense graph, it just leaves every node on the ring with the edges as chords.
    const R = 40 * Math.sqrt(nodes.length);
    for (const n of nodes) {
      const p = prev.get(n.id);
      const a = seeded(n.id) * Math.PI * 2, r = Math.sqrt(seeded(n.id + "r")) * R;
      g.addNode(n.id, { x: p?.x ?? r * Math.cos(a), y: p?.y ?? r * Math.sin(a), size: nodeRadius(n.type, n.priority, n.degree, false) });
    }
    for (const e of edges) if (g.hasNode(e.source) && g.hasNode(e.target) && e.source !== e.target && !g.hasEdge(e.source, e.target)) g.addEdge(e.source, e.target, { weight: 0.5 + Math.min(4, Math.log2(1 + e.weight)) });
    const n = nodes.length;
    // strong repulsion, weak gravity: clusters separate instead of collapsing into a disc
    const base = { gravity: 0.35, scalingRatio: n > 600 ? 6 : n > 250 ? 10 : 18, strongGravityMode: false, barnesHutOptimize: n > 300, barnesHutTheta: 0.7, slowDown: 2, linLogMode: false, outboundAttractionDistribution: true, edgeWeightInfluence: 1, adjustSizes: false };
    forceAtlas2.assign(g, { iterations: n > 600 ? 300 : 700, settings: base });
    // short second pass with size-aware repulsion to take the overlaps out
    forceAtlas2.assign(g, { iterations: 140, settings: { ...base, adjustSizes: true, slowDown: 4, scalingRatio: base.scalingRatio * 1.5 } });
    const next = new Map<string, Pos>();
    g.forEachNode((id, a) => next.set(id, { x: a.x as number, y: a.y as number }));
    const c = canvasRef.current;
    packComponents(g, next, c && c.clientHeight > 0 ? c.clientWidth / c.clientHeight : 1.6);
    posRef.current = next;
    setLayoutKey((k) => k + 1);
  }, [nodes, edges]);
  useEffect(() => { fitToView(); }, [layoutKey, fitToView]);

  // ------------------------------------------------------------ draw
  const draw = useCallback(() => {
    const c = canvasRef.current; if (!c) return;
    const ctx = c.getContext("2d"); if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cam = camRef.current, pos = posRef.current, hover = hoverRef.current;
    const focusId = selected ?? hover?.node ?? null;
    const focusNb = focusId ? neighbours.get(focusId) : null;
    const anyEmphasis = emphasisSet.size > 0;
    const receded = (id: string) => focusId ? (id !== focusId && !focusNb?.has(id)) : anyEmphasis ? !emphasisSet.has(id) : false;
    const sx = (x: number) => x * cam.k + cam.x, sy = (y: number) => y * cam.k + cam.y;
    const kk = Math.max(0.55, Math.min(1.5, cam.k));

    // edges: opacity carries weight; only the focus's lines go full ink
    for (const e of edges) {
      const a = pos.get(e.source), b = pos.get(e.target); if (!a || !b) continue;
      const rec = receded(e.source) || receded(e.target);
      const onRoute = routeSet.has(`${e.source}|${e.target}`);
      const touchesFocus = focusId !== null && (e.source === focusId || e.target === focusId);
      const style = lineStyleFor(e.attrs?.extractor as string | undefined, e.confidence);
      const rel = Math.min(1, e.weight / maxW);
      ctx.beginPath(); ctx.moveTo(sx(a.x), sy(a.y)); ctx.lineTo(sx(b.x), sy(b.y));
      ctx.setLineDash(DASH[style].map((d) => d * kk));
      if (onRoute) { ctx.strokeStyle = INK.pencil; ctx.lineWidth = 2.6; ctx.globalAlpha = 1; }
      else {
        ctx.strokeStyle = edgeInk(e.rel_type);
        const sq = Math.sqrt(rel);
        ctx.lineWidth = (0.7 + sq * 1.8) * kk;
        ctx.globalAlpha = rec ? 0.05 : touchesFocus || hover?.edge === e.id ? 0.95 : edges.length > 400 ? 0.18 + sq * 0.4 : 0.35 + sq * 0.45;
      }
      ctx.stroke();
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1;

    // nodes
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    const labelScale = (presentation ? 1.2 : 1) * Math.max(0.85, Math.min(1.25, cam.k));
    const drawn: { x: number; y: number; w: number; h: number }[] = [];
    const sorted = nodes.slice().sort((p, q) => q.priority - p.priority);
    // the names a reader needs at rest: the highest-priority and best-connected actors
    const named = new Set(sorted.filter((n) => !INFRA.has(n.type)).sort((p, q) => (q.priority + q.degree / 40) - (p.priority + p.degree / 40)).slice(0, labelAll ? 400 : 28).map((n) => n.id));
    for (const n of sorted) {
      const p = pos.get(n.id); if (!p) continue;
      const x = sx(p.x), y = sy(p.y);
      const infra = INFRA.has(n.type);
      const r = nodeRadius(n.type, n.priority, n.degree, presentation) * kk * (infra ? 0.8 : 1);
      const rec = receded(n.id);
      const isSel = n.id === selected, isHov = n.id === hover?.node, onRoute = !!route?.includes(n.id);
      const poi = n.suspicion >= 0.2;
      ctx.globalAlpha = rec ? 0.15 : 1;
      drawShape(ctx, SHAPE[n.type], x, y, r);
      ctx.fillStyle = INK.film; ctx.fill();
      ctx.lineWidth = (isSel || onRoute ? 2.4 : poi ? 1.7 : 1) * Math.min(1.3, kk);
      ctx.strokeStyle = isSel || onRoute ? INK.pencil : n.type === "BANK_ACCOUNT" ? INK.blue : infra ? INK.inkSoft : INK.ink;
      ctx.stroke();
      if (poi && (n.type === "PERSON" || n.type === "ORGANIZATION")) { ctx.beginPath(); ctx.arc(x, y, Math.max(1.4, r * 0.34), 0, Math.PI * 2); ctx.fillStyle = INK.pencil; ctx.fill(); }
      if (isSel || isHov) { ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.strokeStyle = INK.pencil; ctx.lineWidth = 1; ctx.setLineDash([2, 3]); ctx.stroke(); ctx.setLineDash([]); }

      // labels: persons of interest and organisations always; everything else on hover/selection or when asked
      // at rest: persons of interest, and organisations that anchor something (degree ≥ 3); the rest on hover or zoom
      const anchor = n.type === "ORGANIZATION" && (n.degree >= 3 || cam.k > 0.9);
      const wantLabel = isSel || isHov || (!rec && (named.has(n.id) || (labelAll ? !infra : ((poi && !infra) || anchor) && cam.k > 0.3)));
      if (wantLabel) {
        const fs = (isSel ? 12.5 : poi ? 11.5 : 10.5) * labelScale;
        ctx.font = `${isSel || poi ? 600 : 500} ${fs}px var(--font-barlow-condensed), sans-serif`;
        const label = n.label.length > 26 ? n.label.slice(0, 24) + "…" : n.label;
        const tw = ctx.measureText(label).width, th = fs * 1.2;
        const tx = x + r + 4, ty = y;
        const box = { x: tx - 2, y: ty - th / 2, w: tw + 4, h: th };
        const collides = !isSel && !isHov && drawn.some((d) => box.x < d.x + d.w && box.x + box.w > d.x && box.y < d.y + d.h && box.y + box.h > d.y);
        if (!collides) {
          drawn.push(box);
          ctx.fillStyle = "rgba(237,237,234,0.88)"; ctx.fillRect(box.x, box.y, box.w, box.h);
          ctx.fillStyle = rec ? INK.inkFaint : isSel ? INK.pencil : INK.ink; ctx.fillText(label, tx, ty);
        }
      }
    }
    ctx.globalAlpha = 1;
  }, [nodes, edges, selected, presentation, emphasisSet, routeSet, neighbours, route, maxW, labelAll]);

  useEffect(() => { const loop = () => { draw(); rafRef.current = requestAnimationFrame(loop); }; rafRef.current = requestAnimationFrame(loop); return () => cancelAnimationFrame(rafRef.current); }, [draw]);
  useEffect(() => { const ro = new ResizeObserver(() => fitToView()); if (wrapRef.current) ro.observe(wrapRef.current); return () => ro.disconnect(); }, [fitToView]);

  // ------------------------------------------------------------ hit testing
  const hitTest = useCallback((mx: number, my: number): { node?: string; edge?: string } | null => {
    const cam = camRef.current, pos = posRef.current;
    const wx = (mx - cam.x) / cam.k, wy = (my - cam.y) / cam.k;
    let best: string | undefined, bd = Infinity;
    for (const n of nodes) { const p = pos.get(n.id); if (!p) continue; const r = (nodeRadius(n.type, n.priority, n.degree, presentation) + 5) / cam.k; const d = Math.hypot(p.x - wx, p.y - wy); if (d < r && d < bd) { bd = d; best = n.id; } }
    if (best) return { node: best };
    const tol = 4 / cam.k;
    for (const e of edges) {
      const a = pos.get(e.source), b = pos.get(e.target); if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy; if (!l2) continue;
      const t = Math.max(0, Math.min(1, ((wx - a.x) * dx + (wy - a.y) * dy) / l2));
      if (Math.hypot(a.x + t * dx - wx, a.y + t * dy - wy) < tol) return { edge: e.id };
    }
    return null;
  }, [nodes, edges, presentation]);

  const onPointerDown = (ev: React.PointerEvent) => { const r = canvasRef.current!.getBoundingClientRect(); dragRef.current = { x: ev.clientX - r.left, y: ev.clientY - r.top, cx: camRef.current.x, cy: camRef.current.y, moved: false }; (ev.target as Element).setPointerCapture(ev.pointerId); };
  const onPointerMove = (ev: React.PointerEvent) => {
    const r = canvasRef.current!.getBoundingClientRect(); const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    if (dragRef.current) { const d = dragRef.current; const dx = mx - d.x, dy = my - d.y; if (Math.hypot(dx, dy) > 3) d.moved = true; camRef.current = { ...camRef.current, x: d.cx + dx, y: d.cy + dy }; return; }
    const hit = hitTest(mx, my), prev = hoverRef.current;
    if (hit?.node !== prev?.node || hit?.edge !== prev?.edge) { hoverRef.current = hit; canvasRef.current!.style.cursor = hit ? "pointer" : "grab"; onHover?.(hit ? { node: hit.node ? nodeById.get(hit.node) : undefined, edge: hit.edge ? edgeById.get(hit.edge) : undefined } : null); }
  };
  const onPointerUp = (ev: React.PointerEvent) => {
    const d = dragRef.current; dragRef.current = null;
    if (d && !d.moved) { const r = canvasRef.current!.getBoundingClientRect(); const hit = hitTest(ev.clientX - r.left, ev.clientY - r.top); onSelect?.(hit?.node ?? null); }
  };
  const onWheel = (ev: React.WheelEvent) => {
    const r = canvasRef.current!.getBoundingClientRect(); const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const cam = camRef.current; const k = Math.max(0.1, Math.min(6, cam.k * Math.exp(-ev.deltaY * 0.0012)));
    camRef.current = { k, x: mx - (mx - cam.x) * (k / cam.k), y: my - (my - cam.y) * (k / cam.k) };
  };
  const onKey = (ev: React.KeyboardEvent) => {
    const cam = camRef.current, step = 40;
    if (ev.key === "ArrowLeft") camRef.current = { ...cam, x: cam.x + step };
    else if (ev.key === "ArrowRight") camRef.current = { ...cam, x: cam.x - step };
    else if (ev.key === "ArrowUp") camRef.current = { ...cam, y: cam.y + step };
    else if (ev.key === "ArrowDown") camRef.current = { ...cam, y: cam.y - step };
    else if (ev.key === "+" || ev.key === "=") camRef.current = { ...cam, k: Math.min(6, cam.k * 1.2) };
    else if (ev.key === "-") camRef.current = { ...cam, k: Math.max(0.1, cam.k / 1.2) };
    else if (ev.key === "0") fitToView();
    else if (ev.key === "Escape") onSelect?.(null);
    else if (ev.key === "Enter" || ev.key === " ") { const poi = nodes.filter((n) => n.suspicion >= 0.2).sort((a, b) => b.priority - a.priority); const i = poi.findIndex((n) => n.id === selected); onSelect?.(poi[(i + 1) % Math.max(1, poi.length)]?.id ?? null); }
    else return;
    ev.preventDefault();
  };

  return (
    <div ref={wrapRef} className={`relative h-full w-full ${className ?? ""}`}>
      <canvas ref={canvasRef} role="application" tabIndex={0}
        aria-label={`Link chart with ${nodes.length} entities and ${edges.length} relationships. Arrow keys pan, plus and minus zoom, zero fits, Enter cycles persons of interest, Escape clears selection.`}
        className="block h-full w-full cursor-grab outline-none focus-visible:ring-2 focus-visible:ring-pencil"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={() => { hoverRef.current = null; onHover?.(null); }}
        onWheel={onWheel} onKeyDown={onKey} onDoubleClick={fitToView} />
      {!nodes.length && (
        <div className="absolute inset-0 grid place-items-center">
          <div className="note-paper max-w-sm p-5">
            <p className="label label-ink">Nothing drawn on this sheet</p>
            <p className="mt-2 text-ink-soft">No entities match the current key and filters. Clear a filter in the symbol key, or load data from the Sources lens.</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function edgeCaption(e: EdgeView, nodeById: Map<string, NodeView>): string {
  const a = nodeById.get(e.source)?.label ?? "?", b = nodeById.get(e.target)?.label ?? "?";
  const style = lineStyleFor(e.attrs?.extractor as string | undefined, e.confidence);
  const grade = style === "solid" ? "structured record" : style === "dashed" ? "rule-extracted from text" : "model-inferred";
  const ch = e.attrs?.channels as Record<string, number> | undefined;
  const detail = ch ? Object.entries(ch).map(([k, v]) => `${k} ${v}`).join(", ") : e.count > 1 ? `×${e.count}` : "";
  return `${a} ${relLabel(e.rel_type)} ${b}${detail ? ` · ${detail}` : ""} · ${grade}`;
}
