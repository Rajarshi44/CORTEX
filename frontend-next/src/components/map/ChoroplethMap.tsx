"use client";

import { useMemo, useRef, useState, useCallback, useEffect } from "react";
import regionData from "@/data/india-regions.json";

/* ── Types ─────────────────────────────────────────────────────────── */

type DistrictShape = (typeof regionData.districts)[number];

export type RegionStat = {
  name: string;
  entities: number;
  poi: number;
  events: number;
  alerts: number;
  threat: number;       // 0–1 scale
  communities: number;
  documents: number;
  /** Breakdown by entity type */
  breakdown: { persons: number; phones: number; orgs: number; accounts: number };
  /** Recent events for the detail panel */
  recentEvents: { kind: string; summary: string; at: string }[];
};

export type ChoroplethStats = { byRegion: RegionStat[] };
type Props = { stats: ChoroplethStats; title?: string };

/* ── Threat tiers & colors ─────────────────────────────────────────── */

const TIERS = [
  { label: "Critical", min: 0.8, fill: "rgba(248,113,113,.42)", stroke: "rgba(248,113,113,.75)", dot: "#f87171", badge: "#f87171", badgeBg: "rgba(248,113,113,.18)" },
  { label: "High",     min: 0.6, fill: "rgba(251,146,60,.38)",  stroke: "rgba(251,146,60,.7)",   dot: "#fb923c", badge: "#fb923c", badgeBg: "rgba(251,146,60,.16)" },
  { label: "Medium",   min: 0.3, fill: "rgba(250,204,21,.32)",  stroke: "rgba(250,204,21,.65)",  dot: "#facc15", badge: "#facc15", badgeBg: "rgba(250,204,21,.14)" },
  { label: "Low",      min: 0,   fill: "rgba(74,222,128,.30)",  stroke: "rgba(74,222,128,.6)",   dot: "#4ade80", badge: "#4ade80", badgeBg: "rgba(74,222,128,.14)" },
] as const;
const NO_DATA_TIER = { label: "No data", fill: "rgba(148,163,184,.15)", stroke: "rgba(148,163,184,.3)", dot: "#64748b", badge: "#64748b", badgeBg: "rgba(148,163,184,.12)" };

function tierFor(threat: number, hasData: boolean) {
  if (!hasData) return NO_DATA_TIER;
  for (const t of TIERS) if (threat >= t.min) return t;
  return TIERS[TIERS.length - 1];
}

function threatLabel(threat: number) {
  if (threat >= 0.8) return "Critical";
  if (threat >= 0.6) return "High";
  if (threat >= 0.3) return "Medium";
  return "Low";
}

/* ── Component ─────────────────────────────────────────────────────── */

export default function ChoroplethMap({ stats, title = "Threat Intelligence Heatmap" }: Props) {
  const regions = stats.byRegion;
  const hasRealData = regions.some((r) => r.entities > 0 || r.events > 0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null);
  const [sortBy, setSortBy] = useState<"entities" | "threat" | "alerts" | "events">("entities");
  const [camera, setCamera] = useState({ x: 0, y: 48, width: 1000, height: 650 });
  const drag = useRef<{ x: number; y: number; camera: typeof camera } | null>(null);

  const statByName = useMemo(() => new Map(regions.map((r) => [r.name.toLowerCase(), r])), [regions]);
  const detail = selectedId ? ((() => { const d = regionData.districts.find((r) => r.id === selectedId); return d ? statByName.get(d.name.toLowerCase()) : undefined; })()) : undefined;
  const selectedDistrict = selectedId ? regionData.districts.find((r) => r.id === selectedId) : undefined;

  // KPI aggregates
  const coveredCount = regions.filter((r) => r.entities > 0 || r.events > 0).length;
  const totalEntities = regions.reduce((s, r) => s + r.entities, 0);
  const totalPoi = regions.reduce((s, r) => s + r.poi, 0);
  const totalAlerts = regions.reduce((s, r) => s + r.alerts, 0);
  const totalEvents = regions.reduce((s, r) => s + r.events, 0);
  const regionsWithData = regions.filter((r) => r.entities > 0);
  const avgThreat = regionsWithData.length > 0 ? regionsWithData.reduce((s, r) => s + r.threat, 0) / regionsWithData.length : 0;
  const avgThreatTier = tierFor(avgThreat, regionsWithData.length > 0);

  // Sorted for table
  const sorted = useMemo(() => {
    return [...regions].sort((a, b) => {
      if (sortBy === "threat") return b.threat - a.threat;
      if (sortBy === "alerts") return b.alerts - a.alerts;
      if (sortBy === "events") return b.events - a.events;
      return b.entities - a.entities;
    });
  }, [regions, sortBy]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    setTooltip({ x: e.clientX, y: e.clientY });
  }, []);

  const hoveredDist = hoveredId ? (() => { const d = regionData.districts.find((r) => r.id === hoveredId); return d ? { shape: d, stat: statByName.get(d.name.toLowerCase()) } : undefined; })() : undefined;

  // Camera controls
  const zoomAt = (factor: number, clientX?: number, clientY?: number) => setCamera((c) => {
    const nw = Math.max(260, Math.min(1000, c.width * factor));
    const nh = nw * 0.65;
    const rect = (document.querySelector(".choropleth-stage") as HTMLElement | null)?.getBoundingClientRect();
    const px = rect && clientX !== undefined ? (clientX - rect.left) / rect.width : 0.5;
    const py = rect && clientY !== undefined ? (clientY - rect.top) / rect.height : 0.5;
    return { x: Math.max(0, Math.min(1000 - nw, c.x + (c.width - nw) * px)), y: Math.max(0, Math.min(760 - nh, c.y + (c.height - nh) * py)), width: nw, height: nh };
  });
  const resetCamera = () => setCamera({ x: 0, y: 48, width: 1000, height: 650 });

  // Ref for native wheel handler (React onWheel is passive, can't preventDefault)
  const stageRef = useRef<HTMLDivElement>(null);
  const zoomAtRef = useRef(zoomAt);
  zoomAtRef.current = zoomAt;

  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      zoomAtRef.current(e.deltaY > 0 ? 1.12 : 0.88, e.clientX, e.clientY);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  return (
    <section className="choropleth-shell">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="choropleth-head">
        <div>
          <p className="choropleth-kicker">CORTEX / GEO ANALYSIS</p>
          <h1>{title}</h1>
          <p className="choropleth-subtitle">
            Criminal network threat assessment across mapped regions
          </p>
        </div>
        <div className="cortex-live-badge" data-live={hasRealData}>
          <span className="cortex-live-dot" />
          <span>
            {hasRealData ? `LIVE DATA · ${coveredCount} REGIONS` : "NO GEO DATA YET"}
          </span>
        </div>
      </div>

      {/* ── KPI Summary Row ───────────────────────────────────────── */}
      <div className="cortex-kpi-row">
        {[
          { label: "Regions Covered", value: `${coveredCount}/36`, color: "#38bdf8" },
          { label: "Total Entities", value: totalEntities.toLocaleString("en-IN"), color: "#f8fafc" },
          { label: "Persons of Interest", value: totalPoi.toLocaleString("en-IN"), color: totalPoi > 0 ? "#fb923c" : "#64748b" },
          { label: "Avg Threat Level", value: regionsWithData.length > 0 ? threatLabel(avgThreat) : "—", color: avgThreatTier.badge },
        ].map((kpi, i) => (
          <div key={kpi.label} className="cortex-kpi-card" style={{ animationDelay: `${0.05 + i * 0.06}s` }}>
            <span className="cortex-kpi-label">{kpi.label}</span>
            <strong className="cortex-kpi-value" style={{ color: kpi.color }}>{kpi.value}</strong>
          </div>
        ))}
      </div>

      {/* ── Section: Geographic Heatmap ────────────────────────────── */}
      <div className="cortex-section-label">
        <span>§ Geographic Heatmap</span>
        <div className="cortex-section-line" />
      </div>

      {/* ── Map + Detail Panel Grid ───────────────────────────────── */}
      <div className={`choropleth-layout ${detail ? "has-selection" : ""}`}>
        {/* SVG Map */}
        <div className="choropleth-stage" ref={stageRef}>
          <svg
            className="choropleth-svg"
            viewBox={`${camera.x} ${camera.y} ${camera.width} ${camera.height}`}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="Interactive regional threat choropleth"
            onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, camera }; }}
            onPointerMove={(e) => {
              if (drag.current) {
                const currentDrag = drag.current;
                const rect = e.currentTarget.getBoundingClientRect();
                const sx = camera.width / rect.width;
                const sy = camera.height / rect.height;
                setCamera((c) => ({
                  ...c,
                  x: Math.max(0, Math.min(1000 - c.width, currentDrag.camera.x - (e.clientX - currentDrag.x) * sx)),
                  y: Math.max(0, Math.min(760 - c.height, currentDrag.camera.y - (e.clientY - currentDrag.y) * sy)),
                }));
              }
              handleMouseMove(e);
            }}
            onPointerUp={() => { drag.current = null; }}
            onPointerCancel={() => { drag.current = null; }}
            onMouseLeave={() => { setHoveredId(null); setTooltip(null); }}
          >
            <defs>
              <filter id="district-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="0" stdDeviation="7" floodColor="#38bdf8" floodOpacity=".8" />
              </filter>
            </defs>
            {regionData.districts.map((district) => {
              const stat = statByName.get(district.name.toLowerCase());
              const hasData = stat ? (stat.entities > 0 || stat.events > 0) : false;
              const tier = tierFor(stat?.threat ?? 0, hasData);
              const isSelected = selectedId === district.id;
              const isHovered = hoveredId === district.id;

              return (
                <g
                  key={district.id}
                  className="district-group"
                  onMouseEnter={() => setHoveredId(district.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => setSelectedId(isSelected ? null : district.id)}
                >
                  <path
                    className={`district-path ${isSelected ? "is-selected" : ""}`}
                    d={district.path}
                    fill={isSelected ? "rgba(56,189,248,0.4)" : isHovered ? "rgba(56,189,248,0.25)" : tier.fill}
                    stroke={isSelected ? "#38bdf8" : isHovered ? "rgba(56,189,248,0.8)" : tier.stroke}
                    strokeWidth={isSelected ? 3 : isHovered ? 2.5 : 1.25}
                    filter={isSelected ? "url(#district-shadow)" : undefined}
                  />
                  <text className="district-label" x={district.labelX} y={district.labelY - 8}>
                    {district.name}
                  </text>
                  <circle
                    className="district-dot"
                    cx={district.labelX}
                    cy={district.labelY + 4}
                    r={isSelected ? 5 : isHovered ? 4 : 3}
                    fill={isSelected ? "#38bdf8" : tier.dot}
                    opacity={hasData ? 1 : 0.4}
                  />
                </g>
              );
            })}
          </svg>

          {/* Map controls */}
          <div className="map-controls" aria-label="Map controls">
            <button type="button" onClick={() => zoomAt(0.8)} aria-label="Zoom in">+</button>
            <button type="button" onClick={() => zoomAt(1.25)} aria-label="Zoom out">−</button>
            <button type="button" onClick={resetCamera} aria-label="Reset map view">↺</button>
          </div>
          <div className="choropleth-gridline" />

          {/* Hover Tooltip */}
          {hoveredDist && tooltip && !selectedId && (
            <div className="choropleth-tooltip" style={{ left: tooltip.x + 16, top: tooltip.y + 16 }}>
              <strong>{hoveredDist.shape.name}</strong>
              {hoveredDist.stat && (hoveredDist.stat.entities > 0 || hoveredDist.stat.events > 0) ? (
                <>
                  <span className="cortex-tt-row">
                    <span>Entities</span>
                    <span className="cortex-tt-val">{hoveredDist.stat.entities}</span>
                  </span>
                  <span className="cortex-tt-row">
                    <span>POI</span>
                    <span className="cortex-tt-val" style={{ color: hoveredDist.stat.poi > 0 ? "#fb923c" : undefined }}>
                      {hoveredDist.stat.poi}
                    </span>
                  </span>
                  <span className="cortex-tt-row">
                    <span>Threat</span>
                    <span className="cortex-tt-val" style={{ color: tierFor(hoveredDist.stat.threat, true).badge }}>
                      {threatLabel(hoveredDist.stat.threat)}
                    </span>
                  </span>
                  <span className="cortex-tt-row">
                    <span>Events</span>
                    <span className="cortex-tt-val">{hoveredDist.stat.events}</span>
                  </span>
                  <span className="cortex-tt-row">
                    <span>Alerts</span>
                    <span className="cortex-tt-val" style={{ color: hoveredDist.stat.alerts > 0 ? "#f87171" : undefined }}>
                      {hoveredDist.stat.alerts}
                    </span>
                  </span>
                </>
              ) : (
                <span style={{ color: "#64748b", fontStyle: "italic" }}>No intelligence collected</span>
              )}
            </div>
          )}
        </div>

        {/* ── Detail Panel ──────────────────────────────────────────── */}
        {detail && selectedDistrict && (
          <aside className="district-panel">
            <button className="district-close" type="button" onClick={() => setSelectedId(null)} aria-label="Close region details">×</button>
            <p className="choropleth-kicker">SELECTED REGION</p>
            <h2>{selectedDistrict.name}</h2>

            {(detail.entities === 0 && detail.events === 0) ? (
              <p className="district-empty">No intelligence records reference this region yet.</p>
            ) : (
              <>
                {/* KPI Cards */}
                <div className="kpi-grid">
                  {[
                    { label: "Entities", value: detail.entities, color: "#f8fafc" },
                    { label: "POI", value: detail.poi, color: detail.poi > 0 ? "#fb923c" : "#64748b" },
                    { label: "Threat", value: threatLabel(detail.threat), color: tierFor(detail.threat, true).badge },
                    { label: "Events", value: detail.events, color: "#38bdf8" },
                    { label: "Alerts", value: detail.alerts, color: detail.alerts > 0 ? "#f87171" : "#64748b" },
                    { label: "Communities", value: detail.communities, color: "#a78bfa" },
                    { label: "Documents", value: detail.documents, color: "#94a3b8" },
                  ].map((m) => (
                    <div className="kpi-card" key={m.label}>
                      <span>{m.label}</span>
                      <strong style={{ color: m.color }}>{m.value}</strong>
                    </div>
                  ))}
                </div>

                {/* Entity Type Breakdown Bar */}
                {detail.entities > 0 && (
                  <div className="sentiment-block">
                    <div className="sentiment-title">
                      <span>Entity Composition</span>
                      <span>{detail.entities} total</span>
                    </div>
                    <div className="cortex-comp-bar">
                      {detail.breakdown.persons > 0 && (
                        <i style={{ width: `${(detail.breakdown.persons / detail.entities) * 100}%`, background: "#38bdf8" }} />
                      )}
                      {detail.breakdown.phones > 0 && (
                        <i style={{ width: `${(detail.breakdown.phones / detail.entities) * 100}%`, background: "#a78bfa" }} />
                      )}
                      {detail.breakdown.orgs > 0 && (
                        <i style={{ width: `${(detail.breakdown.orgs / detail.entities) * 100}%`, background: "#facc15" }} />
                      )}
                      {detail.breakdown.accounts > 0 && (
                        <i style={{ width: `${(detail.breakdown.accounts / detail.entities) * 100}%`, background: "#4ade80" }} />
                      )}
                    </div>
                    <div className="cortex-comp-key">
                      <span style={{ color: "#38bdf8" }}>Persons {detail.breakdown.persons}</span>
                      <span style={{ color: "#a78bfa" }}>Phones {detail.breakdown.phones}</span>
                      <span style={{ color: "#facc15" }}>Orgs {detail.breakdown.orgs}</span>
                      <span style={{ color: "#4ade80" }}>Accounts {detail.breakdown.accounts}</span>
                    </div>
                  </div>
                )}

                {/* Recent Events */}
                {detail.recentEvents.length > 0 && (
                  <div className="cortex-events-section">
                    <p className="cortex-events-title">Recent Events</p>
                    <div className="cortex-events-list">
                      {detail.recentEvents.slice(0, 5).map((ev, i) => (
                        <div key={i} className="cortex-event-item">
                          <span className="cortex-event-kind">{ev.kind.replace(/_/g, " ")}</span>
                          <p className="cortex-event-summary">{ev.summary.length > 100 ? ev.summary.slice(0, 100) + "…" : ev.summary}</p>
                          <span className="cortex-event-time">{ev.at ? new Date(ev.at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "—"}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </aside>
        )}
      </div>

      {/* ── Legend ─────────────────────────────────────────────────── */}
      <div className="choropleth-footer">
        <div className="choropleth-legend">
          <span style={{ marginRight: 4, color: "#64748b", fontSize: ".62rem", letterSpacing: ".12em" }}>THREAT:</span>
          {[...TIERS, NO_DATA_TIER].map((t) => (
            <span key={t.label}><i style={{ background: t.dot }} />{t.label}</span>
          ))}
        </div>
        <div className="choropleth-summary">
          <span>{totalEntities.toLocaleString("en-IN")} entities</span>
          <span>{totalPoi.toLocaleString("en-IN")} POI</span>
          <span>{totalEvents.toLocaleString("en-IN")} events</span>
          <span>{totalAlerts.toLocaleString("en-IN")} alerts</span>
        </div>
      </div>

      {/* ── Section: Region Table ──────────────────────────────────── */}
      <div className="cortex-section-label" style={{ marginTop: "1.5rem" }}>
        <span>§ Region-wise Breakdown</span>
        <div className="cortex-section-line" />
      </div>

      <div className="cortex-table-wrap">
        {/* Sort controls */}
        <div className="cortex-sort-bar">
          <span className="cortex-sort-label">SORT:</span>
          {(["entities", "threat", "alerts", "events"] as const).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setSortBy(opt)}
              className={`cortex-sort-btn ${sortBy === opt ? "is-active" : ""}`}
            >
              {opt}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="cortex-table-scroll">
          <table className="cortex-region-table">
            <thead>
              <tr>
                {["#", "Region", "Entities", "POI", "Events", "Alerts", "Threat", "Communities"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, idx) => {
                const hasData = r.entities > 0 || r.events > 0;
                const tier = tierFor(r.threat, hasData);
                const districtShape = regionData.districts.find((d) => d.name.toLowerCase() === r.name.toLowerCase());
                const isSelected = districtShape ? selectedId === districtShape.id : false;

                return (
                  <tr
                    key={r.name}
                    onClick={() => { if (districtShape) setSelectedId(isSelected ? null : districtShape.id); }}
                    className={isSelected ? "is-active" : ""}
                    style={{ opacity: hasData ? 1 : 0.35, animationDelay: `${idx * 0.02}s` }}
                  >
                    <td><span className="cortex-row-num">{idx + 1}</span></td>
                    <td>
                      <span className="cortex-row-region">
                        <span className="cortex-row-dot" style={{ background: tier.dot }} />
                        {r.name}
                      </span>
                    </td>
                    <td><span className="figure">{r.entities || "—"}</span></td>
                    <td><span className="figure" style={{ color: r.poi > 0 ? "#fb923c" : undefined }}>{r.poi || "—"}</span></td>
                    <td><span className="figure" style={{ color: "#38bdf8" }}>{r.events || "—"}</span></td>
                    <td><span className="figure" style={{ color: r.alerts > 0 ? "#f87171" : undefined }}>{r.alerts || "—"}</span></td>
                    <td>
                      {hasData ? (
                        <span className="cortex-threat-badge" style={{ color: tier.badge, background: tier.badgeBg }}>
                          {threatLabel(r.threat)}
                        </span>
                      ) : (
                        <span style={{ color: "#475569" }}>—</span>
                      )}
                    </td>
                    <td><span className="figure" style={{ color: "#a78bfa" }}>{r.communities || "—"}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
