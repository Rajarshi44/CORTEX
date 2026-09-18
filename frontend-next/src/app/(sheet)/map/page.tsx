"use client";
/** Map & timeline: one scrubber drives both (specimen raise), with a numeric readout. */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useGeo, useTimeline, useHistogram } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import TitleBlock from "@/components/sheet/TitleBlock";
import Narrative from "@/components/sheet/Narrative";
import { INK, maskLabel } from "@/lib/notation";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const DEFAULT_CENTER: [number, number] = [77.209, 28.6139]; // Delhi National Capital Region [lng, lat]
const DEFAULT_ZOOM = 10.5;

/* ---------------------------------------------------------------------------
   EDITORIAL GeoJSON MAP STYLE
   
   No raster tiles, no external CDN. The basemap is rendered entirely from
   local GeoJSON files: India state boundaries + neighbouring country outlines.
   Every colour comes from the design system. The result is a purpose-built
   analytical surface: no roads, no POIs, no decorative noise.
--------------------------------------------------------------------------- */

// Design-system derived map palette
const MAP_PALETTE = {
  ocean: "#E8EDF2",          // Cool wash — distinguishes water from land
  land: "#F7F6F3",           // --film: warm bone canvas
  stateFill: "#F0EFEC",      // Slightly deeper than film for state polygons
  stateBorder: "#D4D4D0",    // Subtle state borders
  stateBorderHover: "#606760", // --ink-faint for emphasis
  stateHover: "#EAEAE6",     // --film-deep for hover state
  neighbourFill: "#EDEEEC",  // Faint context for neighbouring countries
  neighbourBorder: "#DDDDD9", // Very subtle neighbour borders
  stateLabel: "#787774",     // --ink-faint
  neighbourLabel: "#A0A09C", // Even fainter for context labels
} as const;

/**
 * Build the MapLibre style specification from local GeoJSON.
 * This replaces the raster-tile based MAP_STYLE entirely.
 */
function buildMapStyle(): maplibregl.StyleSpecification {
  return {
    version: 8,
    name: "CORTEX Editorial",
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      "india-states": {
        type: "geojson",
        data: "/geo/india-states.json",
        generateId: true,
      },
      "neighbours": {
        type: "geojson",
        data: "/geo/neighbours.json",
      },
    },
    layers: [
      // 1. Ocean / background
      {
        id: "background",
        type: "background",
        paint: {
          "background-color": MAP_PALETTE.ocean,
        },
      },

      // 2. Neighbouring countries fill — faint context
      {
        id: "neighbours-fill",
        type: "fill",
        source: "neighbours",
        paint: {
          "fill-color": MAP_PALETTE.neighbourFill,
          "fill-opacity": 0.85,
        },
      },

      // 3. Neighbouring countries border
      {
        id: "neighbours-border",
        type: "line",
        source: "neighbours",
        paint: {
          "line-color": MAP_PALETTE.neighbourBorder,
          "line-width": 0.8,
        },
      },

      // 4. India states fill — the main analytical canvas
      {
        id: "states-fill",
        type: "fill",
        source: "india-states",
        paint: {
          "fill-color": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            MAP_PALETTE.stateHover,
            MAP_PALETTE.stateFill,
          ],
          "fill-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, 0.95,
            12, 1.0,
          ],
        },
      },

      // 5. India state borders — editorial hairlines
      {
        id: "states-border",
        type: "line",
        source: "india-states",
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            MAP_PALETTE.stateBorderHover,
            MAP_PALETTE.stateBorder,
          ],
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, 0.5,
            7, 1.0,
            12, 1.5,
          ],
        },
      },

      // 6. Neighbouring country labels — very faint context
      {
        id: "neighbours-label",
        type: "symbol",
        source: "neighbours",
        layout: {
          "text-field": ["get", "name"],
          "text-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, 9,
            6, 11,
          ],
          "text-font": ["Noto Sans Regular"],
          "text-transform": "uppercase",
          "text-letter-spacing": 0.15,
          "text-max-width": 8,
        },
        paint: {
          "text-color": MAP_PALETTE.neighbourLabel,
          "text-halo-color": MAP_PALETTE.neighbourFill,
          "text-halo-width": 1,
          "text-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, 0.4,
            5, 0.7,
            8, 0.3,
          ],
        },
      },

      // 7. India state labels — marginalia on the analytical surface
      {
        id: "states-label",
        type: "symbol",
        source: "india-states",
        layout: {
          "text-field": ["get", "name"],
          "text-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            4, 8,
            6, 10,
            9, 12,
          ],
          "text-font": ["Noto Sans Regular"],
          "text-transform": "uppercase",
          "text-letter-spacing": 0.08,
          "text-max-width": 6,
          "text-anchor": "center",
          "symbol-placement": "point",
        },
        paint: {
          "text-color": MAP_PALETTE.stateLabel,
          "text-halo-color": MAP_PALETTE.stateFill,
          "text-halo-width": 1.5,
          "text-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3.5, 0,
            4.5, 0.5,
            6, 0.9,
            10, 0.7,
            14, 0.3,
          ],
        },
      },
    ],
  };
}

export default function MapLens() {
  const { data: geo } = useGeo();
  const { data: hist } = useHistogram();
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
  const hoveredStateId = useRef<number | string | null>(null);

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

  // Hover interactivity on state polygons
  const setupHoverInteraction = useCallback((map: maplibregl.Map) => {
    map.on("mousemove", "states-fill", (e: maplibregl.MapLayerMouseEvent) => {
      if (e.features && e.features.length > 0) {
        if (hoveredStateId.current !== null) {
          map.setFeatureState({ source: "india-states", id: hoveredStateId.current }, { hover: false });
        }
        hoveredStateId.current = e.features[0].id ?? null;
        if (hoveredStateId.current !== null) {
          map.setFeatureState({ source: "india-states", id: hoveredStateId.current }, { hover: true });
        }
        map.getCanvas().style.cursor = "default";
      }
    });

    map.on("mouseleave", "states-fill", () => {
      if (hoveredStateId.current !== null) {
        map.setFeatureState({ source: "india-states", id: hoveredStateId.current }, { hover: false });
      }
      hoveredStateId.current = null;
    });
  }, []);

  // Initialize map with GeoJSON style
  useEffect(() => {
    if (!boxRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: boxRef.current,
      style: buildMapStyle(),
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
      maxBounds: [
        [55, 2],    // Southwest corner (covers India + neighbours)
        [100, 42],  // Northeast corner
      ],
    });

    // Log any rendering errors for diagnostics
    map.on("error", (e) => console.error("[maplibre]", (e as unknown as { error?: { message?: string } }).error?.message ?? e));

    // Navigation control — minimal, just zoom
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    // Attribution for GeoJSON sources
    map.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution: "Natural Earth · DataMeet",
    }));

    // Setup hover interactivity once the map loads
    map.on("load", () => {
      setupHoverInteraction(map);
    });

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, [setupHoverInteraction]);

  // location circles: risk carries ink
  useEffect(() => {
    const map = mapRef.current; if (!map || !geo) return;
    const paint = () => {
      const src = { type: "FeatureCollection", features: geo.locations.map((l) => ({ type: "Feature", geometry: { type: "Point", coordinates: [l.lon, l.lat] }, properties: { id: l.id, label: maskLabel(l.label), risk: l.risk, actors: l.actors, poi: l.poi.length } })) } as GeoJSON.FeatureCollection;
      if (map.getSource("locs")) (map.getSource("locs") as maplibregl.GeoJSONSource).setData(src);
      else {
        map.addSource("locs", { type: "geojson", data: src });
        map.addLayer({
          id: "locs-glow",
          type: "circle",
          source: "locs",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["get", "actors"], 0, 12, 20, 28, 60, 40],
            "circle-color": [
              "case",
              [">=", ["get", "risk"], 0.3], "rgba(176, 40, 33, 0.08)",
              [">", ["get", "poi"], 0], "rgba(20, 22, 19, 0.05)",
              "rgba(20, 22, 19, 0.03)"
            ],
            "circle-blur": 1,
          },
        });
        map.addLayer({
          id: "locs-ring",
          type: "circle",
          source: "locs",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["get", "actors"], 0, 4, 20, 16, 60, 26],
            "circle-color": "rgba(237,237,234,0.55)",
            "circle-stroke-width": ["case", [">", ["get", "poi"], 0], 2, 1],
            "circle-stroke-color": [
              "case",
              [">=", ["get", "risk"], 0.3], INK.pencil,
              [">", ["get", "poi"], 0], INK.ink,
              INK.inkFaint,
            ],
          },
        });
        map.addLayer({ id: "locs-label", type: "symbol", source: "locs", layout: { "text-field": ["get", "label"], "text-size": presentation ? 13 : 11, "text-offset": [0, 1.6], "text-font": ["Noto Sans Regular"], "text-anchor": "top" }, paint: { "text-color": INK.ink, "text-halo-color": MAP_PALETTE.stateFill, "text-halo-width": 1.5 } });
        map.on("click", "locs-ring", (e: maplibregl.MapLayerMouseEvent) => { const p = e.features?.[0]?.properties; if (p?.id) select(String(p.id)); });
        map.on("mouseenter", "locs-ring", () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", "locs-ring", () => (map.getCanvas().style.cursor = ""));
      }
    };
    if (map.isStyleLoaded()) paint(); else map.once("load", paint);
    // Frame what the sheet actually covers. Fit bounds only when points exist and span an area.
    if (geo.locations.length) {
      const b = new maplibregl.LngLatBounds();
      for (const l of geo.locations) b.extend([l.lon, l.lat]);
      for (const e of geo.events) if (e.lat && e.lon) b.extend([e.lon, e.lat]);
      const sw = b.getSouthWest();
      const ne = b.getNorthEast();
      if (Math.abs(sw.lat - ne.lat) > 0.02 || Math.abs(sw.lng - ne.lng) > 0.02) {
        map.fitBounds(b, { padding: 64, maxZoom: 12, animate: false });
      } else {
        map.setCenter([sw.lng, sw.lat]);
        map.setZoom(DEFAULT_ZOOM);
      }
    } else {
      map.setCenter(DEFAULT_CENTER);
      map.setZoom(DEFAULT_ZOOM);
    }
  }, [geo, select, presentation]);

  // event pins for the current window
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    markers.current.forEach((m) => m.remove()); markers.current = [];
    for (const ev of (events ?? []).filter((e) => e.lat && e.lon).slice(0, 400)) {
      const el = document.createElement("button");
      el.type = "button"; el.className = "cortex-pin"; el.title = `${format(new Date(ev.at), "dd MMM HH:mm")} · ${ev.summary}`;
      el.setAttribute("aria-label", el.title);
      const isTransfer = ev.kind === "TRANSFER";
      const isFir = ev.kind === "FIR";
      el.style.cssText = `width:10px;height:10px;border-radius:${isTransfer ? "0" : "50%"};border:1.5px solid ${isTransfer ? INK.blue : isFir ? INK.pencil : INK.ink};background:${MAP_PALETTE.land};cursor:pointer;transform:rotate(${isTransfer ? "45deg" : "0"});box-shadow:0 1px 4px rgba(0,0,0,0.12);transition:transform 120ms ease`;
      el.onmouseenter = () => { el.style.transform = `rotate(${isTransfer ? "45deg" : "0"}) scale(1.4)`; };
      el.onmouseleave = () => { el.style.transform = `rotate(${isTransfer ? "45deg" : "0"}) scale(1)`; };
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
          <ol className="min-h-0 flex-1 overflow-y-auto">{listed.map((e) => <li key={e.id} className="border-b border-rule px-3 py-1 text-[length:var(--fs-note)]"><button type="button" onClick={() => { const a = e.actors?.[0]; if (a) select(a.id); }} className="block w-full text-left hover:text-pencil"><span className="figure text-ink-faint">{format(new Date(e.at), "dd MMM HH:mm")}</span> <span className="label text-ink-faint">{e.kind}</span><span className="block truncate text-ink">{maskLabel(e.summary)}</span></button></li>)}</ol>
        </aside>
        <div className="pointer-events-none absolute bottom-3 right-3 z-10"><TitleBlock lens="Map" /></div>
      </div>
      {/* the scrubber: a scale bar along the bottom margin */}
      <div className="border-t border-ink bg-film-deep px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="label label-ink">Scale of time</span>
          <span className="figure text-[length:var(--fs-note)]">{timeWindow ? `${timeWindow[0]} → ${timeWindow[1].slice(0, 10)} · ${span} d` : "whole sheet"}</span>
          <label className="label ml-auto flex items-center gap-1.5">Window <select value={span} onChange={(e) => setSpan(Number(e.target.value))} className="border border-rule-strong bg-film px-1 py-0.5 text-[length:var(--fs-note)] normal-case tracking-normal">{[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</select></label>
          {cursor !== null && <button type="button" onClick={() => setCursor(null)} className="label text-pencil hover:underline">whole sheet</button>}
        </div>
        <div className="relative mt-1 h-12" aria-hidden="true">
          <div className="absolute inset-0 flex items-end gap-px">{days.map((d, i) => <div key={d.day} className={cn("flex-1", cursor !== null && i <= cursor && i > cursor - span ? "bg-pencil" : "bg-ink-faint")} style={{ height: `${Math.max(4, (d.total / maxDay) * 100)}%` }} />)}</div>
        </div>
        <input type="range" min={0} max={Math.max(0, days.length - 1)} value={cursor ?? days.length - 1} onChange={(e) => setCursor(Number(e.target.value))} className="w-full accent-pencil" aria-label="Time cursor" aria-valuetext={cursor !== null && days[cursor] ? days[cursor].day : "whole sheet"} />
        <div className="flex justify-between figure text-[length:var(--fs-note)] text-ink-faint"><span>{days[0]?.day ?? ""}</span><span>{days[days.length - 1]?.day ?? ""}</span></div>
      </div>
    </div>
  );
}
