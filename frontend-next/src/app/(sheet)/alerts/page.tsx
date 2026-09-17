"use client";
/** The register: rows are live entities ranked by severity and time; columns never move. */
import { Suspense, useMemo, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import Link from "next/link";
import { useAlerts, useAlertStatus, useDetectors } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import StandingWatches from "@/components/sheet/StandingWatches";
import { ALERT_KIND_LABEL, SEVERITY_INK, maskLabel } from "@/lib/notation";
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
      <dl className="text-[length:var(--fs-note)]">{rows.map(([k, v]) => <div key={k} className="grid grid-cols-[9rem_1fr] gap-2 border-b border-rule py-1"><dt className="label text-ink-faint">{k.replace(/_/g, " ")}</dt><dd className="figure break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>)}</dl>
      <div>
        {drivers && <><h4 className="label">Drivers</h4><ul className="text-[length:var(--fs-note)]">{drivers.map((d) => <li key={d.feature} className="flex justify-between border-b border-rule py-1"><span>{d.feature}</span><span className="figure">{Number(d.value).toLocaleString("en-IN")} <span className="text-ink-faint">vs {Number(d.median).toFixed(1)}</span>{d.z !== undefined && <span className="ml-2 text-pencil">z {d.z}</span>}</span></li>)}</ul></>}
        {hops && <><h4 className="label">Chain</h4><ol className="text-[length:var(--fs-note)]">{hops.map((h, i) => <li key={i} className="border-b border-rule py-1"><span className="figure text-ink-faint">{format(new Date(h.at), "dd MMM HH:mm")}</span> {h.from} → {h.to} <span className="figure text-blue">₹{Math.round(h.amount).toLocaleString("en-IN")}</span></li>)}</ol></>}
        {a.entities.length > 0 && <><h4 className="label mt-3">Entities</h4><p className="flex flex-wrap gap-1">{a.entities.map((e) => <EntityChip key={e.id} id={e.id} label={e.label} />)}</p></>}
      </div>
    </div>
  );
}
function EntityChip({ id, label }: { id: string; label: string }) { const select = useSheet((s) => s.select); return <button type="button" onClick={() => select(id)} className="border border-rule-strong px-1.5 py-0.5 text-[length:var(--fs-note)] hover:border-ink">{maskLabel(label)}</button>; }

function Register() {
  const [status, setStatus] = useState<string>("open");
  const [kind, setKind] = useState<string>("");
  const [openId, setOpenId] = useQueryState("id", parseAsString);
  const { data, isLoading } = useAlerts({ status: status || undefined, kind: kind || undefined, limit: 300 });
  const { data: roster } = useDetectors();
  const patch = useAlertStatus();
  const setHighlights = useSheet((s) => s.setHighlights);
  const presentation = useSheet((s) => s.presentation);
  const rows = useMemo(() => (data ?? []).slice().sort((a, b) => ORDER[a.severity] - ORDER[b.severity] || b.score - a.score), [data]);
  const kinds = useMemo(() => Array.from(new Set((data ?? []).map((a) => a.kind))), [data]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-[1500px] px-6 py-6">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink pb-2">
          <div><h1 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Register of alerts</h1><p className="mt-1 max-w-[76ch] text-ink-soft">{roster ? `${roster.total} detectors run` : "Every detector runs"} after each ingestion{roster ? `; ${roster.fired} of them found something on this sheet` : ""}. Open a row to see the numbers that triggered it; marking a row records your decision in the audit log. An alert is a lead to rule out, never a finding.</p></div>
          <div className="flex items-center gap-3">
            <label className="label flex items-center gap-1.5">Status <select value={status} onChange={(e) => setStatus(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1 text-[length:var(--fs-body)] normal-case tracking-normal"><option value="">any</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
            <label className="label flex items-center gap-1.5">Kind <select value={kind} onChange={(e) => setKind(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1 text-[length:var(--fs-body)] normal-case tracking-normal"><option value="">any</option>{kinds.map((k) => <option key={k} value={k}>{ALERT_KIND_LABEL[k] ?? k}</option>)}</select></label>
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
                  <button type="button" onClick={() => setOpenId(open ? null : a.id)} aria-expanded={open} className="min-w-0 truncate text-left font-medium hover:text-pencil">{maskLabel(a.title)}</button>
                  <span className="label truncate text-ink-soft">{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span>
                  <span className="figure text-right">{a.score.toFixed(2)}</span>
                </div>
                {open && (
                  <div className="border-t border-rule bg-film-lift px-3 py-3">
                    <p className="max-w-[80ch] text-[length:var(--fs-body)] leading-relaxed"><MarkdownInline text={a.description} /></p>
                    <div className="mt-3"><Evidence a={a} /></div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="label text-ink-faint">Mark</span>
                      {STATUSES.map((s) => <button key={s} type="button" disabled={a.status === s} onClick={() => patch.mutate({ id: a.id, status: s })} className={cn("label border px-2 py-1", a.status === s ? "border-ink bg-ink text-film" : "border-rule-strong hover:border-ink")}>{s}</button>)}
                      <span className="label text-ink-faint ml-2 border-l border-rule pl-3">Review</span>
                      {(["pending", "reviewed", "escalated"] as const).map((s) => <button key={s} type="button" disabled={a.review_status === s} onClick={() => patch.mutate({ id: a.id, review_status: s })} className={cn("label border px-2 py-1", a.review_status === s ? "border-ink bg-ink text-film" : "border-rule-strong hover:border-ink")}>{s}</button>)}
                      <button type="button" onClick={() => setHighlights(a.entities.map((e) => e.id), `Alert emphasised: ${a.title}`)} className="label ml-auto text-ink-soft hover:text-pencil">emphasise on chart</button>
                      <Link href={`/chart${a.entities[0] ? `?focus=${a.entities[0].id}` : ""}`} className="label text-pencil hover:underline">redraw around it</Link>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
          {!isLoading && !rows.length && <li className="py-8 text-center note">No alerts match this filter. Detectors run after every ingestion.</li>}
        </ol>

        {/* A short register is the honest result on a narrow corpus, but a blank half-screen reads
            as a broken page, and copy that hard-codes "two of the eight fired" is wrong the moment
            the corpus changes. Read it off the roster, and keep the two silences apart: a detector
            that read the record and found nothing has produced a result; one with no record to read
            has not run at all. */}
        {!isLoading && roster && roster.fired < roster.total && (
          <section className="mt-8 border-t border-rule pt-4">
            <h2 className="label label-ink">The rest of the bench</h2>
            <p className="mt-1 max-w-[80ch] note">
              {roster.fired} of {roster.total} detectors found something on this sheet
              {roster.silent > 0 && <>, {roster.silent} read the record and found nothing</>}
              {roster.starved > 0 && <>, and {roster.starved} have no record of their kind to read yet</>}.
              A detector that ran and stayed quiet has given you an answer. One with nothing to read has not:
              add the missing record from the Sources lens and it comes alive on the next recompute.
            </p>
            <ul className="mt-3 divide-y divide-rule">
              {roster.detectors.filter((d) => !d.fired).map((d) => (
                <li key={d.name} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 py-1.5">
                  <span className="text-[length:var(--fs-body)]">{d.name}</span>
                  <span className={cn("label shrink-0 text-right", d.state === "silent" ? "text-ink-soft" : "text-ink-faint")}>
                    {d.state === "silent"
                      ? `nothing found in ${d.records_held.toLocaleString("en-IN")} ${d.records_unit}`
                      : `no ${d.needs} on this sheet`}
                  </span>
                  <span className="col-span-2 note">Looks for {d.looks_for}.</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        <StandingWatches />
      </div>
      <SheetFooter lens="Alerts" />
    </div>
  );
}
function MarkdownInline({ text }: { text: string }) { const masked = maskLabel(text); return <>{masked.split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>)}</>; }
export default function Page() { return <Suspense><Register /></Suspense>; }
