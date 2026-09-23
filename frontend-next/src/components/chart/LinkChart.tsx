"use client";
/**
 * The junction map.
 *
 * Canvas 2D on purpose: the notation needs true dashed and dotted strokes and nine node shapes,
 * which Sigma's WebGL edge programs do not provide. graphology holds the graph and ForceAtlas2
 * places the stations; this file draws them the way a transit diagram is drawn.
 *
 * The one rule that makes it a map and not a scatter plot: no line is drawn at an arbitrary angle.
 * Every link leaves its station on an axis, turns once through a rounded 45° bend, and arrives.
 * The straight run is spent at the busier end, so trunk lines fan cleanly out of the interchanges
 * and the eye can follow a single route across a crowded field.
 */
import { useEffect, useMemo, useRef, useCallback } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type { EdgeView, NodeView } from "@/lib/types";
import { DASH, INK, MONEY_RELS, SHAPE, lineStyleFor, nodeRadius, relLabel, routeInk, maskLabel, type Shape } from "@/lib/notation";
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
const INFRA = new Set(["PHONE", "BANK_ACCOUNT", "CRYPTO_WALLET", "SOCIAL_HANDLE", "VEHICLE", "GOV_ID", "LOCATION"]);
/* Canvas cannot read a CSS custom property, so the station-name face is named outright here.
   It has to stay in step with --font-condensed in globals.css. */
const LABEL_FACE = '"Archivo Narrow", "Archivo", system-ui, sans-serif';

function drawShape(ctx: CanvasRenderingContext2D, s: Shape, x: number, y: number, r: number) {
  ctx.beginPath();
  switch (s) {
    case "circle": ctx.arc(x, y, r, 0, Math.PI * 2); break;
    case "square": ctx.rect(x - r, y - r, r * 2, r * 2); break;
    case "diamond": ctx.moveTo(x, y - r * 1.15); ctx.lineTo(x + r * 1.15, y); ctx.lineTo(x, y + r * 1.15); ctx.lineTo(x - r * 1.15, y); ctx.closePath(); break;
    case "hexagon": for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i - Math.PI / 6; const px = x + r * 1.1 * Math.cos(a), py = y + r * 1.1 * Math.sin(a); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); } ctx.closePath(); break;
    case "triangle": ctx.moveTo(x, y - r * 1.25); ctx.lineTo(x + r * 1.15, y + r * 0.85); ctx.lineTo(x - r * 1.15, y + r * 0.85); ctx.closePath(); break;
    case "rect": ctx.rect(x - r * 1.4, y - r * 0.85, r * 2.8, r * 1.7); break;
    case "pin": ctx.moveTo(x, y + r * 1.2); ctx.arc(x, y - r * 0.2, r * 0.9, Math.PI * 0.85, Math.PI * 2.15); ctx.closePath(); break;
    case "tag": ctx.moveTo(x - r * 1.2, y - r * 0.8); ctx.lineTo(x + r * 0.7, y - r * 0.8); ctx.lineTo(x + r * 1.3, y); ctx.lineTo(x + r * 0.7, y + r * 0.8); ctx.lineTo(x - r * 1.2, y + r * 0.8); ctx.closePath(); break;
    case "ring": ctx.arc(x, y, r, 0, Math.PI * 2); ctx.moveTo(x + r * 0.5, y); ctx.arc(x, y, r * 0.5, 0, Math.PI * 2, true); break;
    // A wallet is an account the banking system cannot see: the account hexagon with its top-left
    // corner cut off, so the two read as the same family at a glance and still never as each other.
    case "cut-hexagon": {
      const pts: [number, number][] = [];
      for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i - Math.PI / 6; pts.push([x + r * 1.1 * Math.cos(a), y + r * 1.1 * Math.sin(a)]); }
      pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
      ctx.closePath();
      ctx.moveTo(x - r * 1.15, y - r * 0.35); ctx.lineTo(x - r * 0.35, y - r * 1.15);
      break;
    }
    // A type the notation has no mark for must still be visible and still read as unrecognised;
    // falling through an unmatched switch drew nothing at all and lost the node silently.
    default: ctx.rect(x - r * 0.8, y - r * 0.8, r * 1.6, r * 1.6); break;
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
  const GAP = 12, PAD = 8;
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

/**
 * The corner of an octilinear run from a to b: one axis segment and one 45° diagonal.
 * `straightFromA` spends the axis run at a's end, which is how a trunk leaves an interchange.
 * Returns null for a run too short to bend, which is drawn as a plain segment.
 */
function corner(ax: number, ay: number, bx: number, by: number, straightFromA: boolean): Pos | null {
  const dx = bx - ax, dy = by - ay;
  const adx = Math.abs(dx), ady = Math.abs(dy);
  if (adx < 2 && ady < 2) return null;
  const sgx = Math.sign(dx), sgy = Math.sign(dy);
  if (straightFromA) {
    const run = Math.abs(adx - ady);
    return adx > ady ? { x: ax + sgx * run, y: ay } : { x: ax, y: ay + sgy * run };
  }
  const d = Math.min(adx, ady);
  return { x: ax + sgx * d, y: ay + sgy * d };
}

/** Lay the octilinear path for one link into the current context path. */
function routePath(ctx: CanvasRenderingContext2D, ax: number, ay: number, bx: number, by: number, straightFromA: boolean, bend: number) {
  const c = corner(ax, ay, bx, by, straightFromA);
  ctx.moveTo(ax, ay);
  if (!c) { ctx.lineTo(bx, by); return; }
  // the bend can never eat more than half of the shorter of the two segments it joins
  const r = Math.max(1, Math.min(bend, Math.hypot(c.x - ax, c.y - ay) / 2, Math.hypot(bx - c.x, by - c.y) / 2));
  ctx.arcTo(c.x, c.y, bx, by, r);
  ctx.lineTo(bx, by);
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
  /**
   * Interchanges: stations where more than one route calls. On a transit map these are the only
   * marks that get the double ring, and they are exactly the actors an investigator wants first —
   * the person standing on two communities at once.
   */
  const interchange = useMemo(() => {
    const routes = new Map<string, Set<number>>();
    for (const e of edges) {
      const ca = nodeById.get(e.source)?.community, cb = nodeById.get(e.target)?.community;
      if (typeof cb === "number") (routes.get(e.source) ?? routes.set(e.source, new Set()).get(e.source)!).add(cb);
      if (typeof ca === "number") (routes.get(e.target) ?? routes.set(e.target, new Set()).get(e.target)!).add(ca);
    }
    return new Set([...routes].filter(([, s]) => s.size > 1).map(([id]) => id));
  }, [edges, nodeById]);

  const fitToView = useCallback(() => {
    const c = canvasRef.current; if (!c || !posRef.current.size) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    posRef.current.forEach((p) => { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); });
    const w = c.clientWidth, h = c.clientHeight;
    // The plate is the whole panel. A generous inner margin only leaves the network looking like
    // dust in the middle of an empty field, so the fit takes the room it is given.
    const pad = 34;
    const k = Math.min((w - pad * 2) / Math.max(1, maxX - minX), (h - pad * 2) / Math.max(1, maxY - minY), 3.4);
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
    const base = {
      gravity: 0.35,
      scalingRatio: n > 5000 ? 2 : n > 600 ? 6 : n > 250 ? 10 : 18,
      strongGravityMode: false,
      barnesHutOptimize: n > 300,
      barnesHutTheta: n > 5000 ? 1.2 : 0.7,
      slowDown: n > 5000 ? 10 : 2,
      linLogMode: false,
      outboundAttractionDistribution: true,
      edgeWeightInfluence: 1,
      adjustSizes: false
    };
    forceAtlas2.assign(g, { iterations: n > 5000 ? 50 : n > 600 ? 300 : 700, settings: base });
    // short second pass with size-aware repulsion to take the overlaps out, skip for massive nets
    if (n < 5000) {
      forceAtlas2.assign(g, { iterations: 140, settings: { ...base, adjustSizes: true, slowDown: 4, scalingRatio: base.scalingRatio * 1.5 } });
    }
    const next = new Map<string, Pos>();
    g.forEachNode((id, a) => next.set(id, { x: a.x as number, y: a.y as number }));
    const c = canvasRef.current;
    packComponents(g, next, c && c.clientHeight > 0 ? c.clientWidth / c.clientHeight : 1.6);
    posRef.current = next;
    // Frame the new layout here rather than through a state bump. Drawing runs off `posRef` in the
    // animation loop below, so nothing needs to re-render for the chart to change - and a setState
    // in this effect only bought a second render pass to do what this line does.
    fitToView();
  }, [nodes, edges, fitToView]);

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

    // Lines. Octilinear, round-jointed, inked by the route they belong to; a transit line reads as
    // a line, so the base weight stays generous and volume rides on top of it rather than under it.
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const bend = Math.max(4, 9 * kk);
    for (const e of edges) {
      const a = pos.get(e.source), b = pos.get(e.target); if (!a || !b) continue;
      const rec = receded(e.source) || receded(e.target);
      const onRoute = routeSet.has(`${e.source}|${e.target}`);
      const touchesFocus = focusId !== null && (e.source === focusId || e.target === focusId);
      const style = lineStyleFor(e.attrs?.extractor as string | undefined, e.confidence);
      const rel = Math.min(1, e.weight / maxW);
      // the axis run is spent at the busier end, so trunks leave the interchanges square
      const da = neighbours.get(e.source)?.size ?? 0, db = neighbours.get(e.target)?.size ?? 0;
      const [p, q] = da >= db ? [a, b] : [b, a];
      ctx.beginPath();
      routePath(ctx, sx(p.x), sy(p.y), sx(q.x), sy(q.y), true, bend);
      ctx.setLineDash(DASH[style].map((d) => d * kk));
      if (onRoute) { ctx.strokeStyle = INK.pencil; ctx.lineWidth = 3.4 * kk; ctx.globalAlpha = 1; }
      else {
        // A route map inks each line by the service it belongs to. Two actors in one community
        // ride that community's colour; a line crossing between them stays neutral, which is
        // exactly what makes an interchange visible without labelling it.
        const ca = nodeById.get(e.source)?.community, cb = nodeById.get(e.target)?.community;
        const money = MONEY_RELS.has(e.rel_type);
        ctx.strokeStyle = money ? INK.blue : (ca !== null && ca !== undefined && ca === cb) ? routeInk(ca) : INK.inkSoft;
        const sq = Math.sqrt(rel);
        ctx.lineWidth = (1.5 + sq * 2.2) * kk;
        ctx.globalAlpha = rec ? 0.08 : touchesFocus || hover?.edge === e.id ? 1 : edges.length > 400 ? 0.55 + sq * 0.35 : 0.78 + sq * 0.22;
      }
      ctx.stroke();
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.lineCap = "butt"; ctx.lineJoin = "miter";

    // nodes
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    const labelScale = (presentation ? 1.2 : 1) * Math.max(0.85, Math.min(1.25, cam.k));
    const drawn: { x: number; y: number; w: number; h: number }[] = [];
    const sorted = nodes.slice().sort((p, q) => q.priority - p.priority);
    // the names a reader needs at rest: the highest-priority and best-connected actors
    const named = new Set(sorted.filter((n) => !INFRA.has(n.type)).sort((p, q) => (q.priority + q.degree / 40) - (p.priority + p.degree / 40)).slice(0, labelAll ? 44 : 24).map((n) => n.id));
    for (const n of sorted) {
      const p = pos.get(n.id); if (!p) continue;
      const x = sx(p.x), y = sy(p.y);
      const infra = INFRA.has(n.type);
      const r = nodeRadius(n.type, n.priority, n.degree, presentation) * kk * (infra ? 0.8 : 1);
      const rec = receded(n.id);
      const isSel = n.id === selected, isHov = n.id === hover?.node, onRoute = !!route?.includes(n.id);
      const poi = n.suspicion >= 0.2;
      ctx.globalAlpha = rec ? 0.15 : 1;
      const stationInk = isSel || onRoute ? INK.pencil : n.type === "BANK_ACCOUNT" || n.type === "CRYPTO_WALLET" ? INK.blue : infra ? INK.inkSoft : routeInk(n.community);
      // The interchange marker: a second ring, and only ever here. It says this actor stands on
      // more than one route — which is the whole reason a broker is worth opening.
      if (interchange.has(n.id) && !infra) {
        ctx.beginPath(); ctx.arc(x, y, r + 3.2 * Math.min(1.3, kk), 0, Math.PI * 2);
        ctx.strokeStyle = stationInk; ctx.lineWidth = 1 * Math.min(1.3, kk); ctx.stroke();
      }
      drawShape(ctx, SHAPE[n.type], x, y, r);
      ctx.fillStyle = "#EEF0ED"; ctx.fill();
      ctx.lineWidth = (isSel || onRoute ? 3 : poi || interchange.has(n.id) ? 2.3 : 1.6) * Math.min(1.3, kk);
      ctx.strokeStyle = stationInk;
      ctx.stroke();
      if (poi && (n.type === "PERSON" || n.type === "ORGANIZATION")) { ctx.beginPath(); ctx.arc(x, y, Math.max(1.4, r * 0.34), 0, Math.PI * 2); ctx.fillStyle = INK.pencil; ctx.fill(); }
      if (isSel || isHov) { ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.strokeStyle = INK.pencil; ctx.lineWidth = 1; ctx.setLineDash([2, 3]); ctx.stroke(); ctx.setLineDash([]); }

      // labels: persons of interest and organisations always; everything else on hover/selection or when asked
      // at rest: persons of interest, and organisations that anchor something (degree ≥ 3); the rest on hover or zoom
      const anchor = n.type === "ORGANIZATION" && (n.degree >= 3 || cam.k > 0.9);
      const wantLabel = isSel || isHov || (!rec && (named.has(n.id) || (((poi && !infra) || anchor) && cam.k > 0.75)));
      if (wantLabel) {
        const fs = (isSel ? 12.5 : poi ? 11.5 : 10.5) * labelScale;
        ctx.font = `${isSel || poi ? 600 : 500} ${fs}px ${LABEL_FACE}`;
        const masked = maskLabel(n.label, n.role, n.attrs?.party_role as string | undefined);
        const label = masked.length > 26 ? masked.slice(0, 24) + "…" : masked;
        const tw = ctx.measureText(label).width, th = fs * 1.2;
        const gap = r + 4;
        /**
         * Station names are set around the mark, the way they are on a printed map: right first,
         * then left, then below, then above. A name that would collide with one already set, or
         * would run off the plate, gives up its slot rather than being printed on top of another
         * name or sliced by the frame.
         */
        const slots: [number, number][] = [
          [x + gap, y], [x - gap - tw, y],
          [x - tw / 2, y + gap + th * 0.4], [x - tw / 2, y - gap - th * 0.4],
        ];
        let placed: { x: number; y: number; w: number; h: number } | null = null;
        let tx = 0, ty = 0;
        for (const [cx2, cy2] of slots) {
          const box = { x: cx2 - 2, y: cy2 - th / 2, w: tw + 4, h: th };
          if (box.x < 2 || box.y < 2 || box.x + box.w > w - 2 || box.y + box.h > h - 2) continue;
          if (drawn.some((d) => box.x < d.x + d.w && box.x + box.w > d.x && box.y < d.y + d.h && box.y + box.h > d.y)) continue;
          placed = box; tx = cx2; ty = cy2; break;
        }
        // the selection always gets its name, even where it has to sit on top of another
        if (!placed && (isSel || isHov)) {
          const cx2 = Math.max(2, Math.min(w - tw - 4, x + gap));
          placed = { x: cx2 - 2, y: y - th / 2, w: tw + 4, h: th }; tx = cx2; ty = y;
        }
        if (placed) {
          drawn.push(placed);
          ctx.fillStyle = "rgba(228,231,228,0.9)"; ctx.fillRect(placed.x, placed.y, placed.w, placed.h);
          ctx.fillStyle = rec ? INK.inkFaint : isSel ? INK.pencil : INK.ink; ctx.fillText(label, tx, ty);
        }
      }
    }
    ctx.globalAlpha = 1;
  }, [nodes, edges, selected, presentation, emphasisSet, routeSet, neighbours, interchange, nodeById, route, maxW, labelAll]);

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
  const aNode = nodeById.get(e.source), bNode = nodeById.get(e.target);
  const a = aNode ? maskLabel(aNode.label, aNode.role, aNode.attrs?.party_role as string | undefined) : "?";
  const b = bNode ? maskLabel(bNode.label, bNode.role, bNode.attrs?.party_role as string | undefined) : "?";
  const style = lineStyleFor(e.attrs?.extractor as string | undefined, e.confidence);
  const grade = style === "solid" ? "structured record" : style === "dashed" ? "rule-extracted from text" : "model-inferred";
  const ch = e.attrs?.channels as Record<string, number> | undefined;
  const detail = ch ? Object.entries(ch).map(([k, v]) => `${k} ${v}`).join(", ") : e.count > 1 ? `×${e.count}` : "";
  return `${a} ${relLabel(e.rel_type)} ${b}${detail ? ` · ${detail}` : ""} · ${grade}`;
}
