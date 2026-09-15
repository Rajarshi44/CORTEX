"use client";
/**
 * The frame every agent visual sits in, plus the two simplest forms.
 *
 * A figure on this sheet is a numbered plate: a stencil label, a title, the drawing, and a
 * caption saying what to notice and where the numbers came from. The frame is what makes five
 * different visuals read as one document.
 */
import { useMemo } from "react";
import { INK } from "@/lib/notation";
import type { TableVisual, TimelineVisual, Visual } from "@/lib/agent";
import AgentChart from "./AgentChart";
import AgentNetwork from "./AgentNetwork";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  chart: "Figure", network: "Link chart", table: "Table", timeline: "Chronology",
};

export default function VisualBlock({ visual, index, onPick }: { visual: Visual; index: number; onPick?: (id: string) => void }) {
  return (
    <figure className="note-paper my-3 border border-rule-strong">
      <figcaption className="flex items-baseline justify-between gap-3 border-b border-rule-strong px-3 py-1.5">
        <span className="label label-ink truncate">{visual.title}</span>
        <span className="label shrink-0 text-ink-faint">
          {KIND_LABEL[visual.type] ?? "Figure"} {String(index + 1).padStart(2, "0")}
        </span>
      </figcaption>
      <div className="px-3 py-3">
        {visual.type === "chart" ? <AgentChart visual={visual} onPick={onPick} />
          : visual.type === "network" ? <AgentNetwork visual={visual} onPick={onPick} />
          : visual.type === "table" ? <AgentTable visual={visual} onPick={onPick} />
          : <AgentTimeline visual={visual} onPick={onPick} />}
        {visual.caption && <p className="note mt-2 border-t border-rule pt-1.5 leading-snug">{visual.caption}</p>}
      </div>
    </figure>
  );
}

// ------------------------------------------------------------------------------ table
function AgentTable({ visual, onPick }: { visual: TableVisual; onPick?: (id: string) => void }) {
  const { columns, rows, entity_ids } = visual;
  // Right-align a column only when every cell in it reads as a number.
  const numeric = useMemo(
    () => columns.map((_, c) => rows.length > 0 && rows.every((r) => /^[₹%+\-\s]*[\d.,]+\s*(cr|l|k|%|×|x)?$/i.test((r[c] ?? "").trim()))),
    [columns, rows],
  );
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full border-collapse text-[length:var(--fs-body)]">
        <thead>
          <tr>{columns.map((c, i) => (
            <th key={i} className={cn("label border-b border-ink px-2 py-1 whitespace-nowrap", numeric[i] ? "text-right" : "text-left")}>{c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => {
            const eid = entity_ids?.[ri];
            return (
              <tr key={ri} className={cn("border-b border-rule", eid && "cursor-pointer hover:bg-film-deep")}
                  onClick={() => eid && onPick?.(eid)}>
                {columns.map((_, ci) => (
                  <td key={ci} className={cn("px-2 py-1 align-top", numeric[ci] ? "figure text-right tabular-nums" : "",
                                             ci === 0 && "font-medium")}>{r[ci] ?? ""}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------------------ timeline
const KIND_INK: Record<string, string> = {
  CALL: INK.ink, TRANSFER: INK.blue, FIR: INK.pencil, SIGHTING: INK.amber,
  JUDGMENT: INK.green, NEWS: INK.inkSoft, INTEL: INK.amber, POST: INK.inkSoft,
};

function AgentTimeline({ visual, onPick }: { visual: TimelineVisual; onPick?: (id: string) => void }) {
  const evs = visual.events;
  const dates = evs.map((e) => new Date(e.at).getTime()).filter((t) => !Number.isNaN(t));
  const t0 = Math.min(...dates), t1 = Math.max(...dates);
  const span = Math.max(t1 - t0, 1);
  const fmt = (s: string) => {
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return s;
    // Only show a clock when the source actually carried one.
    return /\d{2}:\d{2}/.test(s)
      ? d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })
      : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  };

  return (
    <div>
      {/* the compressed rule: where the events actually cluster in time */}
      {dates.length > 2 && (
        <svg width="100%" height={22} className="mb-2 block overflow-visible" role="img" aria-label="event density over the period">
          <line x1="0" y1={11} x2="100%" y2={11} stroke={INK.rule} strokeWidth={1} />
          {evs.map((e, i) => {
            const t = new Date(e.at).getTime();
            if (Number.isNaN(t)) return null;
            const pct = ((t - t0) / span) * 100;
            return <line key={i} x1={`${pct}%`} y1={4} x2={`${pct}%`} y2={18} strokeWidth={e.emphasis ? 2 : 1}
                         stroke={e.emphasis ? INK.pencil : KIND_INK[e.kind] ?? INK.inkSoft} opacity={e.emphasis ? 1 : 0.7} />;
          })}
        </svg>
      )}
      <ol className="relative space-y-0 border-l border-rule-strong pl-4">
        {evs.map((e, i) => (
          <li key={i} className={cn("relative py-1.5", e.entity_id && "cursor-pointer")}
              onClick={() => e.entity_id && onPick?.(e.entity_id)}>
            <span className="absolute -left-[21px] top-[13px] h-1.5 w-1.5 rotate-45"
                  style={{ background: e.emphasis ? INK.pencil : KIND_INK[e.kind] ?? INK.inkSoft }} aria-hidden="true" />
            <div className="flex flex-wrap items-baseline gap-x-2">
              <time className="figure shrink-0 text-[length:var(--fs-note)] text-ink-faint tabular-nums">{fmt(e.at)}</time>
              {e.kind && <span className="label text-[10px] leading-none text-ink-faint">{e.kind}</span>}
            </div>
            <p className={cn("leading-snug", e.emphasis && "font-semibold text-pencil")}>{e.label}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
