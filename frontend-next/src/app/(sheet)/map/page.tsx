"use client";
/** Map & timeline: one scrubber drives both (specimen raise), with a numeric readout. */
import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useGeo, useTimeline, useHistogram } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import TitleBlock from "@/components/sheet/TitleBlock";
import Narrative from "@/components/sheet/Narrative";
import { INK } from "@/lib/notation";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const STYLE = "https://tiles.openfreemap.org/styles/positron";

export default function MapLens() {
  const { data: geo } = useGeo();
  const { data: hist } = useHistogram();
  // Empty means every kind the sheet actually holds. The chips used to be a fixed list written
  // for the synthetic case (FIR / SIGHTING / CALL / TRANSFER), which selected nothing at all on a
  // corpus of judgments and news and left the map blank.
  const [kinds, setKinds] = useState<string[]>([]);
  const timeWindow = useSheet((s) => s.timeWindow);
  const setTimeWindow = useSheet((s) => s.setTimeWindow);
  const select = useSheet((s) => s.select);
  const setNarrative = useSheet((s) => s.setNarrative);
  const presentation = useSheet((s) => s.presentation);
  const availableKinds = geo?.kinds ?? [];
  const { data: timelinePage } = useTimeline({ kinds: kinds.length ? kinds : undefined, start: timeWindow?.[0], end: timeWindow?.[1], limit: 800, only_poi: true });
  const events = timelinePage?.items;
  const eventsTotal = timelinePage?.total ?? 0;
  const mapRef = useRef<maplibregl.Map | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const markers = useRef<maplibregl.Marker[]>([]);

  // day buckets for the scrubber
  const days = useMemo(() => (hist ?? []).map((h) => ({ day: String(h.bucket), total: Object.entries(h).filter(([k]) => k !== "bucket").reduce((s, [, v]) => s + Number(v), 0) })), [hist]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [span, setSpan] = useState(7);
  useEffect(() => {
    if (cursor === null || !days.length) { setTimeWindow(null); return; }
    const i = Math.max(0, Math.min(days.length - 1, cursor));
    const end = new Date(days[i].day); const start = new Date(end); start.setDate(start.getDate() - span);
    setTimeWindow([start.toISOString().slice(0, 10), end.toISOString().slice(0, 10) + "T23:59:59"]);
  }, [cursor, span, days, setTimeWindow]);

  useEffect(() => {
    if (!boxRef.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: boxRef.current, style: STYLE, center: [72.9, 19.08], zoom: 9.6, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // location circles: risk carries ink
  useEffect(() => {
    const map = mapRef.current; if (!map || !geo) return;
    const paint = () => {
      const src = { type: "FeatureCollection", features: geo.locations.map((l) => ({ type: "Feature", geometry: { type: "Point", coordinates: [l.lon, l.lat] }, properties: { id: l.id, label: l.label, risk: l.risk, actors: l.actors, poi: l.poi.length } })) } as GeoJSON.FeatureCollection;
      if (map.getSource("locs")) (map.getSource("locs") as maplibregl.GeoJSONSource).setData(src);
      else {
        map.addSource("locs", { type: "geojson", data: src });
        map.addLayer({ id: "locs-ring", type: "circle", source: "locs", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "actors"], 0, 4, 20, 16, 60, 26], "circle-color": "rgba(237,237,234,0.55)", "circle-stroke-width": ["case", [">", ["get", "poi"], 0], 2, 1], "circle-stroke-color": ["case", [">=", ["get", "risk"], 0.3], INK.pencil, [">", ["get", "poi"], 0], INK.ink, INK.inkFaint] } });
        map.addLayer({ id: "locs-label", type: "symbol", source: "locs", layout: { "text-field": ["get", "label"], "text-size": presentation ? 13 : 11, "text-offset": [0, 1.6], "text-font": ["Noto Sans Regular"], "text-anchor": "top" }, paint: { "text-color": INK.ink, "text-halo-color": INK.film, "text-halo-width": 1.2 } });
        map.on("click", "locs-ring", (e: maplibregl.MapLayerMouseEvent) => { const p = e.features?.[0]?.properties; if (p?.id) select(String(p.id)); });
        map.on("mouseenter", "locs-ring", () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", "locs-ring", () => (map.getCanvas().style.cursor = ""));
      }
    };
    if (map.isStyleLoaded()) paint(); else map.once("load", paint);
    // Frame what the sheet actually covers. A fixed Mumbai viewport was right for the synthetic
    // case and wrong for a corpus that spans the country.
    if (geo.locations.length) {
      const b = new maplibregl.LngLatBounds();
      for (const l of geo.locations) b.extend([l.lon, l.lat]);
      for (const e of geo.events) if (e.lat && e.lon) b.extend([e.lon, e.lat]);
      map.fitBounds(b, { padding: 64, maxZoom: 9, animate: false });
    }
  }, [geo, select, presentation]);

  // event pins for the current window
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    markers.current.forEach((m) => m.remove()); markers.current = [];
    for (const ev of (events ?? []).filter((e) => e.lat && e.lon).slice(0, 400)) {
      const el = document.createElement("button");
      el.type = "button"; el.className = "sutra-pin"; el.title = `${format(new Date(ev.at), "dd MMM HH:mm")} · ${ev.summary}`;
      el.setAttribute("aria-label", el.title);
      el.style.cssText = `width:10px;height:10px;border-radius:${ev.kind === "TRANSFER" ? "0" : "50%"};border:1.5px solid ${ev.kind === "TRANSFER" ? INK.blue : ev.kind === "FIR" ? INK.pencil : INK.ink};background:${INK.film};cursor:pointer;transform:rotate(${ev.kind === "TRANSFER" ? "45deg" : "0"})`;
      el.onclick = () => { const a = ev.actors?.[0]; if (a) select(a.id); setNarrative(`${format(new Date(ev.at), "dd MMM yyyy HH:mm")}: ${ev.summary}`); };
      markers.current.push(new maplibregl.Marker({ element: el }).setLngLat([ev.lon!, ev.lat!]).addTo(map));
    }
    if (events) setNarrative(`${events.length} event${events.length === 1 ? "" : "s"} ${timeWindow ? `between ${timeWindow[0]} and ${timeWindow[1].slice(0, 10)}` : "across the whole sheet"} for persons of interest; ${markers.current.length} placed on the map.`);
  }, [events, select, setNarrative, timeWindow]);

  const maxDay = Math.max(1, ...days.map((d) => d.total));
  const listed = (events ?? []).slice().reverse().slice(0, 120);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1">
        <div ref={boxRef} className="h-full w-full" role="region" aria-label="Map of locations and events" />
        <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-col gap-2">
          <div className="pointer-events-auto note-paper flex flex-wrap items-center gap-2 px-3 py-1.5">
            <span className="label label-ink">Events</span>
            {availableKinds.map((k) => { const on = kinds.length === 0 || kinds.includes(k); return <button key={k} type="button" aria-pressed={on} onClick={() => setKinds((s) => s.includes(k) ? s.filter((x) => x !== k) : [...(s.length ? s : availableKinds.filter((x) => x !== k)), k].filter((x, i, a) => a.indexOf(x) === i))} className={cn("label px-1.5 py-0.5", on ? "label-ink pencil-line" : "text-ink-faint hover:text-ink")}>{k}</button>; })}
          </div>
          <Narrative />
        </div>
        <aside className="pointer-events-auto absolute right-3 top-3 z-10 hidden max-h-[60%] w-[22rem] flex-col note-paper lg:flex">
          <h2 className="label label-ink border-b border-rule-strong px-3 py-1.5">Events in window · {events?.length ?? 0}{eventsTotal > (events?.length ?? 0) ? ` of ${eventsTotal}` : ""}</h2>
          <ol className="min-h-0 flex-1 overflow-y-auto">{listed.map((e) => <li key={e.id} className="border-b border-rule px-3 py-1 text-[var(--fs-note)]"><button type="button" onClick={() => { const a = e.actors?.[0]; if (a) select(a.id); }} className="block w-full text-left hover:text-pencil"><span className="figure text-ink-faint">{format(new Date(e.at), "dd MMM HH:mm")}</span> <span className="label text-ink-faint">{e.kind}</span><span className="block truncate text-ink">{e.summary}</span></button></li>)}</ol>
        </aside>
        <div className="pointer-events-none absolute bottom-3 right-3 z-10"><TitleBlock lens="Map" /></div>
      </div>
      {/* the scrubber: a scale bar along the bottom margin */}
      <div className="border-t border-ink bg-film-deep px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="label label-ink">Scale of time</span>
          <span className="figure text-[var(--fs-note)]">{timeWindow ? `${timeWindow[0]} → ${timeWindow[1].slice(0, 10)} · ${span} d` : "whole sheet"}</span>
          <label className="label ml-auto flex items-center gap-1.5">Window <select value={span} onChange={(e) => setSpan(Number(e.target.value))} className="border border-rule-strong bg-film px-1 py-0.5 text-[var(--fs-note)] normal-case tracking-normal">{[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</select></label>
          {cursor !== null && <button type="button" onClick={() => setCursor(null)} className="label text-pencil hover:underline">whole sheet</button>}
        </div>
        <div className="relative mt-1 h-12" aria-hidden="true">
          <div className="absolute inset-0 flex items-end gap-px">{days.map((d, i) => <div key={d.day} className={cn("flex-1", cursor !== null && i <= cursor && i > cursor - span ? "bg-pencil" : "bg-ink-faint")} style={{ height: `${Math.max(4, (d.total / maxDay) * 100)}%` }} />)}</div>
        </div>
        <input type="range" min={0} max={Math.max(0, days.length - 1)} value={cursor ?? days.length - 1} onChange={(e) => setCursor(Number(e.target.value))} className="w-full accent-pencil" aria-label="Time cursor" aria-valuetext={cursor !== null && days[cursor] ? days[cursor].day : "whole sheet"} />
        <div className="flex justify-between figure text-[var(--fs-note)] text-ink-faint"><span>{days[0]?.day ?? ""}</span><span>{days[days.length - 1]?.day ?? ""}</span></div>
      </div>
    </div>
  );
}
