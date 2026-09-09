"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useQueryState, parseAsString, parseAsInteger, parseAsBoolean } from "nuqs";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useGraph, useEgo, usePath } from "@/lib/queries";
import { projectionToChart } from "@/lib/projection";
import { useSheet } from "@/lib/store";
import KeyRail from "@/components/sheet/KeyRail";
import TitleBlock from "@/components/sheet/TitleBlock";
import RegisterStrip from "@/components/sheet/RegisterStrip";
import Narrative from "@/components/sheet/Narrative";
import HoverCaption from "@/components/chart/HoverCaption";
import type { EdgeView, NodeView } from "@/lib/types";
import { REL_GROUPS } from "@/lib/notation";
import { cn } from "@/lib/utils";

const LinkChart = dynamic(() => import("@/components/chart/LinkChart"), { ssr: false });

function ChartLens() {
  const [focus, setFocus] = useQueryState("focus", parseAsString);
  const [depth] = useQueryState("depth", parseAsInteger.withDefault(2));
  const [pathA, setPathA] = useQueryState("from", parseAsString);
  const [pathB, setPathB] = useQueryState("to", parseAsString);
  const [infra, setInfra] = useQueryState("infra", parseAsBoolean.withDefault(false));
  const [onlyPoi, setOnlyPoi] = useQueryState("poi", parseAsBoolean.withDefault(false));
  const hiddenTypes = useSheet((s) => s.hiddenTypes);
  const hiddenRels = useSheet((s) => s.hiddenRelations);
  const toggleRel = useSheet((s) => s.toggleRelation);
  const selected = useSheet((s) => s.selected);
  const select = useSheet((s) => s.select);
  const highlights = useSheet((s) => s.highlights);
  const setHighlights = useSheet((s) => s.setHighlights);
  const route = useSheet((s) => s.route);
  const setRoute = useSheet((s) => s.setRoute);
  const setNarrative = useSheet((s) => s.setNarrative);
  const [hover, setHover] = useState<{ node?: NodeView; edge?: EdgeView } | null>(null);

  // three sources of drawing: actor projection (default), full graph with infrastructure, or an ego redraw
  const proj = useQuery({ queryKey: ["projection", onlyPoi], queryFn: () => api.projection({ only_poi: onlyPoi }), enabled: !focus && !infra, staleTime: 120_000 });
  const full = useGraph({ limit: 380, min_priority: onlyPoi ? 0.2 : 0 });
  const ego = useEgo(focus, depth);
  const path = usePath(pathA, pathB);

  const src = useMemo(() => {
    if (focus) return ego.data ?? { nodes: [], edges: [] };
    if (infra) return full.data ?? { nodes: [], edges: [] };
    return projectionToChart(proj.data);
  }, [focus, infra, ego.data, full.data, proj.data]);

  const { nodes, edges, counts } = useMemo(() => {
    const ns = src.nodes.filter((n) => !hiddenTypes.includes(n.type));
    const ids = new Set(ns.map((n) => n.id));
    const es = src.edges.filter((e) => ids.has(e.source) && ids.has(e.target) && !hiddenRels.includes(e.rel_type));
    const c: Record<string, number> = {}; for (const n of src.nodes) c[n.type] = (c[n.type] ?? 0) + 1;
    return { nodes: ns, edges: es, counts: c };
  }, [src, hiddenTypes, hiddenRels]);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  useEffect(() => {
    if (path.data?.paths?.length) {
      const p = path.data.paths[0]; const ids = [p[0].from.id, ...p.map((h) => h.to.id)];
      setRoute(ids); setNarrative(`Route drawn: ${p[0].from.label} to ${p[p.length - 1].to.label} in ${p.length} hop${p.length > 1 ? "s" : ""} — ${p.map((h) => h.verb).join(", ")}.`);
    }
  }, [path.data, setRoute, setNarrative]);
  useEffect(() => {
    if (!src.nodes.length) return;
    setNarrative(focus ? `Sheet redrawn around ${src.nodes.find((n) => n.id === focus)?.label ?? "the selection"}: ${nodes.length} entities within ${depth} hops, ${edges.length} lines.`
      : `${infra ? "Full record" : "Actor chart"}: ${nodes.length} ${infra ? "entities" : "people and organisations"}${onlyPoi ? " of interest" : ""}, ${edges.length} lines.`);
  }, [src, nodes.length, edges.length, focus, depth, onlyPoi, infra, setNarrative]);
  useEffect(() => { if (focus && !selected) select(focus); }, [focus, selected, select]);

  const loading = focus ? ego.isLoading : infra ? full.isLoading : proj.isLoading;
  const error = focus ? ego.error : infra ? full.error : proj.error;
  const pickForPath = (id: string) => { if (!pathA || (pathA && pathB)) { setPathA(id); setPathB(null); setRoute(null); } else if (id !== pathA) setPathB(id); };

  return (
    <div className="flex min-h-0 flex-1">
      <KeyRail counts={counts} />
      <div className="sheet-ground relative min-w-0 flex-1">
        {loading && <div className="absolute inset-0 z-10 grid place-items-center bg-film/60"><p className="label text-ink-faint">Laying out the chart…</p></div>}
        {error && <div className="absolute inset-0 z-10 grid place-items-center"><p className="note-paper p-4 text-pencil">The chart could not be loaded: {String((error as Error).message)}</p></div>}
        <LinkChart nodes={nodes} edges={edges} emphasis={highlights} route={route} labelAll={!infra && nodes.length <= 90}
          onSelect={(id) => { select(id); if (id && (window.event as KeyboardEvent | undefined)?.shiftKey) pickForPath(id); }} onHover={setHover} />
        <div className="pointer-events-none absolute left-3 top-3 z-10 flex max-w-[46rem] flex-col gap-2">
          <div className="pointer-events-auto note-paper flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5">
            <span className="label label-ink">{focus ? "Redrawn around selection" : infra ? "Full record" : "Actor chart"}</span>
            {focus && <button type="button" onClick={() => { setFocus(null); setRoute(null); }} className="label text-pencil hover:underline">← whole sheet</button>}
            {!focus && <>
              <label className="flex items-center gap-1.5 text-[var(--fs-note)]"><input type="checkbox" checked={onlyPoi} onChange={(e) => setOnlyPoi(e.target.checked)} className="accent-pencil" />Persons of interest only</label>
              <label className="flex items-center gap-1.5 text-[var(--fs-note)]" title="Draw phones, accounts, vehicles, handles and locations as their own marks"><input type="checkbox" checked={infra} onChange={(e) => setInfra(e.target.checked)} className="accent-pencil" />Show infrastructure</label>
            </>}
            {highlights.length > 0 && <button type="button" onClick={() => setHighlights([], "Emphasis cleared.")} className="label text-ink-soft hover:text-pencil">clear emphasis</button>}
          </div>
          <div className="pointer-events-auto note-paper flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-1">
            <span className="label text-ink-faint">Lines</span>
            {REL_GROUPS.map((g) => { const off = g.rels.every((r) => hiddenRels.includes(r)); return <button key={g.key} type="button" aria-pressed={!off} onClick={() => g.rels.forEach((r) => { if (off === hiddenRels.includes(r)) toggleRel(r); })} className={cn("label rounded-[2px] px-1.5 py-0.5", off ? "text-ink-faint line-through" : "label-ink hover:bg-film-deep")}>{g.label}</button>; })}
          </div>
          <div className="pointer-events-auto note-paper flex items-center gap-2 px-3 py-1 text-[var(--fs-note)]">
            <span className="label text-ink-faint">Route</span>
            <span className="figure">{pathA ? nodeById.get(pathA)?.label ?? "…" : "shift-click a start"}</span><span className="text-ink-faint">→</span><span className="figure">{pathB ? nodeById.get(pathB)?.label ?? "…" : pathA ? "shift-click an end" : "—"}</span>
            {(pathA || pathB) && <button type="button" onClick={() => { setPathA(null); setPathB(null); setRoute(null); }} className="label text-pencil hover:underline">clear</button>}
            {path.isFetching && <span className="text-ink-faint">finding…</span>}
            {path.data && !path.data.paths.length && <span className="text-pencil">no path</span>}
          </div>
          <Narrative />
        </div>
        <div className="pointer-events-none absolute right-3 top-3 z-10"><RegisterStrip compact /></div>
        <div className="pointer-events-none absolute bottom-3 right-3 z-10"><TitleBlock sheet={focus ? `Ego · ${nodeById.get(focus)?.label ?? focus.slice(0, 8)}` : undefined} lens="Chart" /></div>
        <div className="pointer-events-none absolute bottom-3 left-3 z-10"><HoverCaption hit={hover} nodeById={nodeById} /></div>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><ChartLens /></Suspense>; }
