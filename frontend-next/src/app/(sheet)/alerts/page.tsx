"use client";
/** The register: rows are live entities ranked by severity and time; columns never move. */
import { Suspense, useMemo, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import Link from "next/link";
import { useAlerts, useAlertStatus } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { ALERT_KIND_LABEL, SEVERITY_INK } from "@/lib/notation";
import type { Alert, AlertStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const ORDER = { critical: 0, high: 1, medium: 2, low: 3 } as const;
const STATUSES: AlertStatus[] = ["open", "reviewing", "confirmed", "dismissed"];

function Evidence({ a }: { a: Alert }) {
  const ev = a.evidence ?? {};
  const rows = Object.entries(ev).filter(([k, v]) => v !== null && v !== undefined && !["drivers", "hops", "txn_ids", "top_contacts", "numbers", "towers", "foreign_numbers", "sources"].includes(k));
  const drivers = ev.drivers as { feature: string; value: number; median: number; z?: number; contribution?: number }[] | undefined;
  const hops = ev.hops as { from: string; to: string; amount: number; at: string }[] | undefined;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <dl className="text-[var(--fs-note)]">{rows.map(([k, v]) => <div key={k} className="grid grid-cols-[9rem_1fr] gap-2 border-b border-rule py-1"><dt className="label text-ink-faint">{k.replace(/_/g, " ")}</dt><dd className="figure break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>)}</dl>
      <div>
        {drivers && <><h4 className="label">Drivers</h4><ul className="text-[var(--fs-note)]">{drivers.map((d) => <li key={d.feature} className="flex justify-between border-b border-rule py-1"><span>{d.feature}</span><span className="figure">{Number(d.value).toLocaleString("en-IN")} <span className="text-ink-faint">vs {Number(d.median).toFixed(1)}</span>{d.z !== undefined && <span className="ml-2 text-pencil">z {d.z}</span>}</span></li>)}</ul></>}
        {hops && <><h4 className="label">Chain</h4><ol className="text-[var(--fs-note)]">{hops.map((h, i) => <li key={i} className="border-b border-rule py-1"><span className="figure text-ink-faint">{format(new Date(h.at), "dd MMM HH:mm")}</span> {h.from} → {h.to} <span className="figure text-blue">₹{Math.round(h.amount).toLocaleString("en-IN")}</span></li>)}</ol></>}
        {a.entities.length > 0 && <><h4 className="label mt-3">Entities</h4><p className="flex flex-wrap gap-1">{a.entities.map((e) => <EntityChip key={e.id} id={e.id} label={e.label} />)}</p></>}
      </div>
    </div>
  );
}
function EntityChip({ id, label }: { id: string; label: string }) { const select = useSheet((s) => s.select); return <button type="button" onClick={() => select(id)} className="border border-rule-strong px-1.5 py-0.5 text-[var(--fs-note)] hover:border-ink">{label}</button>; }

function Register() {
  const [status, setStatus] = useState<string>("open");
  const [kind, setKind] = useState<string>("");
  const [openId, setOpenId] = useQueryState("id", parseAsString);
  const { data, isLoading } = useAlerts({ status: status || undefined, kind: kind || undefined, limit: 300 });
  const patch = useAlertStatus();
  const setHighlights = useSheet((s) => s.setHighlights);
  const presentation = useSheet((s) => s.presentation);
  const rows = useMemo(() => (data ?? []).slice().sort((a, b) => ORDER[a.severity] - ORDER[b.severity] || b.score - a.score), [data]);
  const kinds = useMemo(() => Array.from(new Set((data ?? []).map((a) => a.kind))), [data]);

  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1500px] px-6 py-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink pb-2">
          <div><h1 className="text-[var(--fs-sheet)] font-semibold leading-none tracking-tight">Register of alerts</h1><p className="mt-1 text-ink-soft">Seven detectors run after every ingestion. Each row explains its own drivers; marking a row records the analyst’s decision in the audit log.</p></div>
          <div className="flex items-center gap-3">
            <label className="label flex items-center gap-1.5">Status <select value={status} onChange={(e) => setStatus(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1 text-[var(--fs-body)] normal-case tracking-normal"><option value="">any</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
            <label className="label flex items-center gap-1.5">Kind <select value={kind} onChange={(e) => setKind(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1 text-[var(--fs-body)] normal-case tracking-normal"><option value="">any</option>{kinds.map((k) => <option key={k} value={k}>{ALERT_KIND_LABEL[k] ?? k}</option>)}</select></label>
          </div>
        </div>
        <div className={cn("register-row label mt-3 border-b border-rule-strong pb-1 text-ink-faint", presentation && "register-row-p")}><span>#</span><span>Severity</span><span>Alert</span><span>Kind</span><span className="text-right">Score</span></div>
        <ol>
          {isLoading && [0, 1, 2, 3, 4].map((i) => <li key={i} className="h-9 animate-pulse border-b border-rule bg-film-deep/40" />)}
          {rows.map((a, i) => {
            const open = openId === a.id;
            return (
              <li key={a.id} className="ripple-in border-b border-rule" style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }}>
                <div className={cn("register-row py-1.5", presentation && "register-row-p", open && "bg-film-lift")}>
                  <span className="figure text-ink-faint">{String(i + 1).padStart(3, "0")}</span>
                  <span className="flex items-center gap-1.5 label" style={{ color: SEVERITY_INK[a.severity] }}><span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: SEVERITY_INK[a.severity] }} />{a.severity}</span>
                  <button type="button" onClick={() => setOpenId(open ? null : a.id)} aria-expanded={open} className="min-w-0 truncate text-left font-medium hover:text-pencil">{a.title}</button>
                  <span className="label truncate text-ink-soft">{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span>
                  <span className="figure text-right">{a.score.toFixed(2)}</span>
                </div>
                {open && (
                  <div className="border-t border-rule bg-film-lift px-3 py-3">
                    <p className="max-w-[80ch] text-[var(--fs-body)] leading-relaxed"><MarkdownInline text={a.description} /></p>
                    <div className="mt-3"><Evidence a={a} /></div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="label text-ink-faint">Mark</span>
                      {STATUSES.map((s) => <button key={s} type="button" disabled={a.status === s} onClick={() => patch.mutate({ id: a.id, status: s })} className={cn("label border px-2 py-1", a.status === s ? "border-ink bg-ink text-film" : "border-rule-strong hover:border-ink")}>{s}</button>)}
                      <button type="button" onClick={() => setHighlights(a.entities.map((e) => e.id), `Alert emphasised: ${a.title}`)} className="label ml-auto text-ink-soft hover:text-pencil">emphasise on chart</button>
                      <Link href={`/chart${a.entities[0] ? `?focus=${a.entities[0].id}` : ""}`} className="label text-pencil hover:underline">redraw around it →</Link>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
          {!isLoading && !rows.length && <li className="py-8 text-center note">No alerts match. Detectors run after ingestion; load the demo corpus from Sources if the sheet is empty.</li>}
        </ol>
      </div>
      <SheetFooter lens="Alerts" />
    </div>
  );
}
function MarkdownInline({ text }: { text: string }) { return <>{text.split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>)}</>; }
export default function Page() { return <Suspense><Register /></Suspense>; }
