"use client";
/** Alerts as a ruled register in the top margin: rows ranked by severity, columns never move (split-flap raise). */
import Link from "next/link";
import { useAlerts } from "@/lib/queries";
import { ALERT_KIND_LABEL, SEVERITY_INK } from "@/lib/notation";
import { useSheet } from "@/lib/store";
import { cn } from "@/lib/utils";

const ORDER = { critical: 0, high: 1, medium: 2, low: 3 } as const;

export default function RegisterStrip({ compact = false }: { compact?: boolean }) {
  const { data, isLoading } = useAlerts({ status: "open", limit: 60 });
  const setHighlights = useSheet((s) => s.setHighlights);
  const select = useSheet((s) => s.select);
  const rows = (data ?? []).slice().sort((a, b) => ORDER[a.severity] - ORDER[b.severity] || b.score - a.score).slice(0, compact ? 4 : 6);
  const counts = (data ?? []).reduce<Record<string, number>>((m, a) => ((m[a.severity] = (m[a.severity] ?? 0) + 1), m), {});
  return (
    <section aria-label="Open alerts register" className="note-paper w-[min(30rem,42vw)]">
      <header className="flex items-center justify-between border-b border-rule-strong px-3 py-1.5">
        <h2 className="label label-ink">Register of open alerts</h2>
        <div className="flex items-center gap-2 figure text-[var(--fs-note)]">
          {(["critical", "high", "medium", "low"] as const).map((s) => counts[s] ? (
            <span key={s} className="inline-flex items-center gap-1" style={{ color: SEVERITY_INK[s] }}>
              <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full" style={{ background: SEVERITY_INK[s] }} />{counts[s]} {s}
            </span>) : null)}
          <Link href="/alerts" className="text-ink-soft underline decoration-rule-strong hover:text-pencil">all</Link>
        </div>
      </header>
      <ol className="divide-y divide-rule">
        {isLoading && Array.from({ length: 3 }).map((_, i) => <li key={i} className="h-7 animate-pulse bg-film-deep/60" />)}
        {rows.map((a, i) => (
          <li key={a.id} className="ripple-in" style={{ animationDelay: `${i * 35}ms` }}>
            <button
              type="button"
              onClick={() => { setHighlights(a.entities.map((e) => e.id), `Alert: ${a.title}`); if (a.entities[0]) select(a.entities[0].id); }}
              className="grid w-full grid-cols-[0.75rem_6.5rem_1fr] items-center gap-2 px-3 py-1 text-left hover:bg-film-deep focus-visible:bg-film-deep"
              title={a.description}
            >
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: SEVERITY_INK[a.severity] }} />
              <span className={cn("label truncate", a.severity === "critical" && "text-pencil")}>{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span>
              <span className="truncate text-[var(--fs-note)] text-ink">{a.title}</span>
              <span className="sr-only">, severity {a.severity}</span>
            </button>
          </li>
        ))}
        {!isLoading && !rows.length && <li className="px-3 py-2 note">No open alerts. The detectors run after every ingestion.</li>}
      </ol>
    </section>
  );
}
