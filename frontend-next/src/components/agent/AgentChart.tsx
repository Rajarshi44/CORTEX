"use client";
/**
 * The agent's charts, drawn in the same technical pen as the link chart.
 *
 * Hand-rolled SVG rather than a charting library on purpose: the sheet's notation is hairline
 * rules, tick marks, tabular figures and one red pencil for emphasis. A generic library fights
 * that at every step - rounded bars, drop shadows, its own type scale - and the result stops
 * looking like one drawing. Seven forms, one ink set, no gradients.
 */
import { useEffect, useRef, useState } from "react";
import { INK } from "@/lib/notation";
import { formatValue, tickValue, type ChartVisual, type ChartPoint } from "@/lib/agent";
import { cn } from "@/lib/utils";

/** Series ink, in the order a reader should meet it: pen, then money blue, then the red pencil. */
const SERIES = [INK.ink, INK.blue, INK.pencil, INK.amber, INK.green, INK.inkSoft];

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(680);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, e.contentRect.width)));
    ro.observe(el);
    setW(Math.max(280, el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** "Nice" axis maximum, so ticks land on readable numbers instead of 0.4173. */
function niceMax(v: number): number {
  if (v <= 0) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  const n = v / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

const truncate = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

interface Props { visual: ChartVisual; onPick?: (entityId: string) => void }

export default function AgentChart({ visual, onPick }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const pts = visual.points;
  const pick = (p: ChartPoint) => { if (p.entity_id && onPick) onPick(p.entity_id); };

  return (
    <div ref={ref} className="w-full">
      {visual.kind === "stat" ? <Stat pts={pts} unit={visual.unit} onPick={pick} />
        : visual.kind === "donut" ? <Donut pts={pts} unit={visual.unit} width={width} onPick={pick} />
        : visual.kind === "bar" ? <Bars pts={pts} unit={visual.unit} width={width} onPick={pick} />
        : visual.kind === "hourly" ? <Hourly pts={pts} unit={visual.unit} width={width} />
        : visual.kind === "scatter" ? <Scatter pts={pts} unit={visual.unit} width={width} label={visual.series_label} onPick={pick} />
        : visual.kind === "line" || visual.kind === "area" ? <Series pts={pts} unit={visual.unit} width={width} fill={visual.kind === "area"} onPick={pick} />
        : <Columns pts={pts} unit={visual.unit} width={width} onPick={pick} />}
    </div>
  );
}

// ------------------------------------------------------------------------------ stat tiles
function Stat({ pts, unit, onPick }: { pts: ChartPoint[]; unit: string; onPick: (p: ChartPoint) => void }) {
  const rows = pts.slice(0, 4);
  return (
    <dl className={cn("grid gap-px bg-rule-strong", rows.length >= 4 ? "grid-cols-2 sm:grid-cols-4" : rows.length === 3 ? "grid-cols-3" : rows.length === 2 ? "grid-cols-2" : "grid-cols-1")}>
      {rows.map((p, i) => (
        <div key={i} className={cn("bg-film-lift px-3 py-2.5", p.entity_id && "cursor-pointer hover:bg-film-deep")}
             onClick={() => onPick(p)} role={p.entity_id ? "button" : undefined} tabIndex={p.entity_id ? 0 : undefined}
             onKeyDown={(e) => { if (p.entity_id && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onPick(p); } }}>
          <dd className="figure text-[1.6rem] font-semibold leading-none tracking-tight">{formatValue(p.value, unit)}</dd>
          <dt className="label mt-1.5 leading-tight">{p.label}</dt>
          {p.note && <p className="note mt-0.5 leading-snug text-ink-faint">{p.note}</p>}
        </div>
      ))}
    </dl>
  );
}

// ------------------------------------------------------------------------------ horizontal bars
function Bars({ pts, unit, width, onPick }: { pts: ChartPoint[]; unit: string; width: number; onPick: (p: ChartPoint) => void }) {
  const rows = pts.slice(0, 16);
  const labelW = Math.min(190, Math.max(90, width * 0.3));
  const valueW = 74;
  const trackW = Math.max(40, width - labelW - valueW - 8);
  const max = niceMax(Math.max(...rows.map((p) => Math.abs(p.value)), 1));
  const rowH = 24;

  return (
    <svg width={width} height={rows.length * rowH + 18} role="img" aria-label="bar chart" className="overflow-visible">
      {rows.map((p, i) => {
        const y = i * rowH;
        const w = (Math.abs(p.value) / max) * trackW;
        const hot = !!p.entity_id;
        return (
          <g key={i} className={cn(hot && "cursor-pointer")} onClick={() => onPick(p)}>
            {hot && <rect x={0} y={y} width={width} height={rowH} fill="transparent" className="hover:fill-[rgba(31,31,31,0.04)]" />}
            <text x={labelW - 8} y={y + rowH / 2} textAnchor="end" dominantBaseline="middle"
                  fontSize={11.5} fill={INK.ink}>
              {truncate(p.label, Math.floor(labelW / 6.2))}
              <title>{p.label}{p.note ? ` — ${p.note}` : ""}</title>
            </text>
            {/* the empty track, so a short bar still reads against a measured length */}
            <line x1={labelW} y1={y + rowH / 2} x2={labelW + trackW} y2={y + rowH / 2} stroke={INK.rule} strokeWidth={1} />
            <rect x={labelW} y={y + 5} width={Math.max(w, 1.5)} height={rowH - 10}
                  fill={i === 0 ? INK.pencil : INK.ink} opacity={i === 0 ? 1 : 0.82} />
            <text x={labelW + trackW + 8} y={y + rowH / 2} dominantBaseline="middle"
                  fontSize={11.5} fill={INK.inkSoft} className="figure">{formatValue(p.value, unit)}</text>
          </g>
        );
      })}
      <line x1={labelW} y1={0} x2={labelW} y2={rows.length * rowH} stroke={INK.inkFaint} strokeWidth={1} />
      <text x={labelW} y={rows.length * rowH + 12} fontSize={10} fill={INK.inkFaint} className="figure">0</text>
      <text x={labelW + trackW} y={rows.length * rowH + 12} textAnchor="end" fontSize={10} fill={INK.inkFaint} className="figure">
        {tickValue(max, unit)}
      </text>
    </svg>
  );
}

// ------------------------------------------------------------------------------ vertical columns
function Columns({ pts, unit, width, onPick }: { pts: ChartPoint[]; unit: string; width: number; onPick: (p: ChartPoint) => void }) {
  const rows = pts.slice(0, 24);
  const H = 190, padL = 46, padB = 40, padT = 10;
  const plotW = Math.max(40, width - padL - 10);
  const max = niceMax(Math.max(...rows.map((p) => Math.abs(p.value)), 1));
  const step = plotW / rows.length;
  const barW = Math.min(38, step * 0.62);
  const ticks = [0, max / 2, max];
  const rotate = rows.length > 8 || rows.some((p) => p.label.length > 7);

  return (
    <svg width={width} height={H + padB} role="img" aria-label="column chart" className="overflow-visible">
      {ticks.map((t, i) => {
        const y = padT + (1 - t / max) * (H - padT);
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={padL + plotW} y2={y} stroke={i === 0 ? INK.inkFaint : INK.rule} strokeWidth={1} />
            <text x={padL - 6} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={INK.inkFaint} className="figure">
              {tickValue(t, unit)}
            </text>
          </g>
        );
      })}
      {rows.map((p, i) => {
        const h = (Math.abs(p.value) / max) * (H - padT);
        const x = padL + i * step + (step - barW) / 2;
        const hot = !!p.entity_id;
        return (
          <g key={i} className={cn(hot && "cursor-pointer")} onClick={() => onPick(p)}>
            <rect x={x} y={padT + (H - padT) - h} width={barW} height={Math.max(h, 1)} fill={INK.ink} opacity={0.85} />
            <title>{p.label}: {formatValue(p.value, unit)}</title>
            <text x={x + barW / 2} y={H + 12} fontSize={10} fill={INK.inkSoft}
                  textAnchor={rotate ? "end" : "middle"}
                  transform={rotate ? `rotate(-38 ${x + barW / 2} ${H + 12})` : undefined}>
              {truncate(p.label, rotate ? 14 : 9)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ------------------------------------------------------------------------------ line / area
function Series({ pts, unit, width, fill, onPick }: { pts: ChartPoint[]; unit: string; width: number; fill: boolean; onPick: (p: ChartPoint) => void }) {
  const rows = pts.slice(0, 60);
  const H = 190, padL = 50, padB = 34, padT = 12;
  const plotW = Math.max(40, width - padL - 12);
  const plotH = H - padT;
  const max = niceMax(Math.max(...rows.map((p) => p.value), 1));
  const min = Math.min(0, ...rows.map((p) => p.value));
  const xs = (i: number) => padL + (rows.length === 1 ? plotW / 2 : (i / (rows.length - 1)) * plotW);
  const ys = (v: number) => padT + (1 - (v - min) / (max - min || 1)) * plotH;
  const line = rows.map((p, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)},${ys(p.value).toFixed(1)}`).join(" ");
  const area = `${line} L${xs(rows.length - 1).toFixed(1)},${ys(min).toFixed(1)} L${xs(0).toFixed(1)},${ys(min).toFixed(1)} Z`;
  const ticks = [min, (min + max) / 2, max];
  // Never print more than a handful of x labels: a dense axis is unreadable at this size.
  const everyN = Math.ceil(rows.length / 7);

  return (
    <svg width={width} height={H + padB} role="img" aria-label="line chart" className="overflow-visible">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} y1={ys(t)} x2={padL + plotW} y2={ys(t)} stroke={i === 0 ? INK.inkFaint : INK.rule} strokeWidth={1} />
          <text x={padL - 6} y={ys(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={INK.inkFaint} className="figure">
            {tickValue(t, unit)}
          </text>
        </g>
      ))}
      {fill && <path d={area} fill={INK.blue} opacity={0.1} />}
      <path d={line} fill="none" stroke={INK.blue} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      {rows.map((p, i) => (
        <g key={i} className={cn(p.entity_id && "cursor-pointer")} onClick={() => onPick(p)}>
          <circle cx={xs(i)} cy={ys(p.value)} r={rows.length > 30 ? 1.6 : 2.6} fill={INK.film} stroke={INK.blue} strokeWidth={1.3} />
          <circle cx={xs(i)} cy={ys(p.value)} r={9} fill="transparent" />
          <title>{p.label}: {formatValue(p.value, unit)}</title>
          {i % everyN === 0 && (
            <text x={xs(i)} y={H + 14} textAnchor="middle" fontSize={10} fill={INK.inkSoft}>{truncate(p.label, 10)}</text>
          )}
        </g>
      ))}
    </svg>
  );
}

// ------------------------------------------------------------------------------ donut
function Donut({ pts, unit, width, onPick }: { pts: ChartPoint[]; unit: string; width: number; onPick: (p: ChartPoint) => void }) {
  const rows = pts.slice(0, 7);
  const total = rows.reduce((s, p) => s + Math.abs(p.value), 0) || 1;
  const size = 168, R = 74, r = 44, cx = size / 2, cy = size / 2;
  let angle = -Math.PI / 2;
  const arcs = rows.map((p, i) => {
    const sweep = (Math.abs(p.value) / total) * Math.PI * 2;
    const a0 = angle, a1 = angle + sweep;
    angle = a1;
    const large = sweep > Math.PI ? 1 : 0;
    const d = [
      `M${cx + R * Math.cos(a0)},${cy + R * Math.sin(a0)}`,
      `A${R},${R} 0 ${large} 1 ${cx + R * Math.cos(a1)},${cy + R * Math.sin(a1)}`,
      `L${cx + r * Math.cos(a1)},${cy + r * Math.sin(a1)}`,
      `A${r},${r} 0 ${large} 0 ${cx + r * Math.cos(a0)},${cy + r * Math.sin(a0)}`, "Z",
    ].join(" ");
    return { d, p, ink: SERIES[i % SERIES.length], share: Math.abs(p.value) / total };
  });

  return (
    <div className={cn("flex gap-5", width < 420 ? "flex-col items-center" : "items-center")}>
      <svg width={size} height={size} role="img" aria-label="donut chart" className="shrink-0">
        {arcs.map((a, i) => (
          <path key={i} d={a.d} fill={a.ink} opacity={0.88} stroke={INK.film} strokeWidth={1.5}
                className={cn(a.p.entity_id && "cursor-pointer")} onClick={() => onPick(a.p)}>
            <title>{a.p.label}: {formatValue(a.p.value, unit)} ({(a.share * 100).toFixed(1)}%)</title>
          </path>
        ))}
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={17} fontWeight={600} fill={INK.ink} className="figure">
          {tickValue(total, unit)}
        </text>
        <text x={cx} y={cy + 11} textAnchor="middle" fontSize={9.5} fill={INK.inkFaint}
              style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>total</text>
      </svg>
      <ul className="min-w-0 flex-1 space-y-1">
        {arcs.map((a, i) => (
          <li key={i} className={cn("flex items-baseline gap-2 text-[length:var(--fs-body)]", a.p.entity_id && "cursor-pointer hover:text-pencil")}
              onClick={() => onPick(a.p)}>
            <span className="mt-1 h-2.5 w-2.5 shrink-0" style={{ background: a.ink }} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate" title={a.p.label}>{a.p.label}</span>
            <span className="figure shrink-0 tabular-nums text-ink-soft">{formatValue(a.p.value, unit)}</span>
            <span className="figure w-11 shrink-0 text-right text-ink-faint">{(a.share * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------------------ 24-hour clock
function Hourly({ pts, unit, width }: { pts: ChartPoint[]; unit: string; width: number }) {
  // Accept either 24 ordered points or {label:"03"} pairs; missing hours read as zero.
  const byHour = new Array(24).fill(0);
  pts.forEach((p, i) => {
    const h = /^\d{1,2}$/.test(p.label.trim()) ? Number(p.label) : i;
    if (h >= 0 && h < 24) byHour[h] = p.value;
  });
  const H = 150, padL = 34, padB = 30, padT = 8;
  const plotW = Math.max(40, width - padL - 10);
  const max = niceMax(Math.max(...byHour, 1));
  const step = plotW / 24;
  const night = (h: number) => h >= 22 || h < 6;
  const nightTotal = byHour.reduce((s, v, h) => s + (night(h) ? v : 0), 0);
  const total = byHour.reduce((s, v) => s + v, 0) || 1;

  return (
    <div>
      <svg width={width} height={H + padB} role="img" aria-label="calls by hour of day" className="overflow-visible">
        {/* night band: the shape an analyst is actually looking for */}
        <rect x={padL} y={padT} width={step * 6} height={H - padT} fill={INK.pencil} opacity={0.06} />
        <rect x={padL + step * 22} y={padT} width={step * 2} height={H - padT} fill={INK.pencil} opacity={0.06} />
        {[0, max / 2, max].map((t, i) => (
          <g key={i}>
            <line x1={padL} y1={padT + (1 - t / max) * (H - padT)} x2={padL + plotW} y2={padT + (1 - t / max) * (H - padT)}
                  stroke={i === 0 ? INK.inkFaint : INK.rule} strokeWidth={1} />
            <text x={padL - 5} y={padT + (1 - t / max) * (H - padT)} textAnchor="end" dominantBaseline="middle"
                  fontSize={10} fill={INK.inkFaint} className="figure">{tickValue(t, unit)}</text>
          </g>
        ))}
        {byHour.map((v, h) => {
          const bh = (v / max) * (H - padT);
          return (
            <g key={h}>
              <rect x={padL + h * step + step * 0.18} y={padT + (H - padT) - bh} width={step * 0.64}
                    height={Math.max(bh, v > 0 ? 1.5 : 0)} fill={night(h) ? INK.pencil : INK.ink} opacity={0.85} />
              <title>{String(h).padStart(2, "0")}:00 — {formatValue(v, unit)}</title>
              {h % 3 === 0 && (
                <text x={padL + h * step + step / 2} y={H + 13} textAnchor="middle" fontSize={9.5} fill={INK.inkSoft} className="figure">
                  {String(h).padStart(2, "0")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <p className="note mt-1">
        <span className="inline-block h-2 w-2 align-middle" style={{ background: INK.pencil }} aria-hidden="true" /> 22:00–06:00 ·{" "}
        <span className="figure">{((nightTotal / total) * 100).toFixed(0)}%</span> of activity falls in the night window
      </p>
    </div>
  );
}

// ------------------------------------------------------------------------------ scatter
function Scatter({ pts, unit, width, label, onPick }: { pts: ChartPoint[]; unit: string; width: number; label: string; onPick: (p: ChartPoint) => void }) {
  const rows = pts.filter((p) => typeof p.value2 === "number").slice(0, 80);
  if (!rows.length) return <Bars pts={pts} unit={unit} width={width} onPick={onPick} />;
  const H = 210, padL = 48, padB = 34, padT = 12;
  const plotW = Math.max(40, width - padL - 14);
  const maxX = niceMax(Math.max(...rows.map((p) => p.value), 1));
  const maxY = niceMax(Math.max(...rows.map((p) => p.value2!), 1));
  const xs = (v: number) => padL + (v / maxX) * plotW;
  const ys = (v: number) => padT + (1 - v / maxY) * (H - padT);

  return (
    <svg width={width} height={H + padB} role="img" aria-label="scatter plot" className="overflow-visible">
      {[0, maxY / 2, maxY].map((t, i) => (
        <g key={i}>
          <line x1={padL} y1={ys(t)} x2={padL + plotW} y2={ys(t)} stroke={i === 0 ? INK.inkFaint : INK.rule} strokeWidth={1} />
          <text x={padL - 6} y={ys(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={INK.inkFaint} className="figure">{tickValue(t, unit)}</text>
        </g>
      ))}
      <line x1={padL} y1={padT} x2={padL} y2={ys(0)} stroke={INK.inkFaint} strokeWidth={1} />
      {[0, maxX / 2, maxX].map((t, i) => (
        <text key={i} x={xs(t)} y={H + 14} textAnchor="middle" fontSize={10} fill={INK.inkFaint} className="figure">{tickValue(t, unit)}</text>
      ))}
      {rows.map((p, i) => (
        <g key={i} className={cn(p.entity_id && "cursor-pointer")} onClick={() => onPick(p)}>
          <circle cx={xs(p.value)} cy={ys(p.value2!)} r={4} fill={INK.blue} opacity={0.55} stroke={INK.blue} strokeWidth={1} />
          <title>{p.label} — {formatValue(p.value, unit)} / {formatValue(p.value2!, unit)}</title>
        </g>
      ))}
      {label && <text x={padL + plotW} y={H + 28} textAnchor="end" fontSize={10} fill={INK.inkFaint}>{label}</text>}
    </svg>
  );
}
