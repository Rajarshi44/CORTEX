"use client";
/** Numbered margin notes: the dossier of whatever is selected, with the sentence behind every line. */
import Link from "next/link";
import { useMemo, useState } from "react";
import { useSheet } from "@/lib/store";
import { useEntity, useAlertStatus } from "@/lib/queries";
import { Glyph, LineSample } from "./KeyRail";
import { SHAPE, TYPE_LABEL, INK, SEVERITY_INK, ALERT_KIND_LABEL, lineStyleFor, relLabel, fmtInr } from "@/lib/notation";
import type { Dossier, Evidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X, ArrowUpRight, ExternalLink } from "lucide-react";
import { format } from "date-fns";

const TABS = ["Notes", "Associates", "Evidence", "Money", "Calls", "Timeline"] as const;

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="grid grid-cols-[7.5rem_1fr] gap-2 py-0.5 text-[var(--fs-body)]"><dt className="label text-ink-faint">{k}</dt><dd className="figure min-w-0 break-words text-ink">{v}</dd></div>;
}

function EvidenceNote({ e, i }: { e: Evidence; i: number }) {
  const style = lineStyleFor(e.extractor, e.confidence);
  return (
    <li className="border-b border-rule py-2">
      <div className="flex items-center gap-2">
        <span className="figure label text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
        <LineSample style={style} width={22} />
        <span className="label truncate">{e.source_type} · {e.extractor}</span>
        {e.at && <span className="figure ml-auto note">{format(new Date(e.at), "dd MMM yy")}</span>}
      </div>
      <blockquote className="mt-1 border-l border-rule-strong pl-2 text-[var(--fs-body)] leading-snug text-ink">“{e.snippet.trim()}”</blockquote>
      <Link href={`/sources?doc=${e.document_id}`} className="mt-1 inline-flex items-center gap-1 note hover:text-pencil">{e.document_title}<ArrowUpRight className="h-3 w-3" aria-hidden="true" /></Link>
    </li>
  );
}

export default function NotesDrawer() {
  const selected = useSheet((s) => s.selected);
  const open = useSheet((s) => s.notesOpen);
  const setOpen = useSheet((s) => s.setNotesOpen);
  const select = useSheet((s) => s.select);
  const setRoute = useSheet((s) => s.setRoute);
  const setHighlights = useSheet((s) => s.setHighlights);
  const { data, isLoading, isError } = useEntity(selected);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Notes");
  const patch = useAlertStatus();
  const d = data as Dossier | undefined;
  const e = d?.entity;

  const assoc = useMemo(() => d?.associates ?? [], [d]);
  if (!open || !selected) return null;

  return (
    <aside aria-label="Margin notes" className="absolute inset-y-0 right-0 z-20 flex w-[var(--notes-w)] max-w-[92vw] flex-col border-l border-ink bg-film-lift shadow-[-8px_0_24px_-16px_rgba(31,31,31,0.5)]">
      <header className="flex items-start gap-2 border-b border-ink px-3 py-2">
        {e ? <Glyph shape={SHAPE[e.type]} size={18} stroke={e.type === "BANK_ACCOUNT" ? INK.blue : INK.ink} className="mt-1 shrink-0" /> : <span className="h-4 w-4" />}
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[var(--fs-title)] font-semibold leading-tight text-ink">{e?.label ?? (isLoading ? "Loading note…" : "—")}</h2>
          <p className="note truncate">{e ? [TYPE_LABEL[e.type], e.aliases?.length ? `@ ${e.aliases.join(", ")}` : null, e.role].filter(Boolean).join(" · ") : ""}</p>
        </div>
        <button type="button" onClick={() => { setOpen(false); select(null); }} aria-label="Close notes" className="rounded-[2px] p-1 text-ink-soft hover:bg-film-deep hover:text-ink"><X className="h-4 w-4" /></button>
      </header>
      {e && (e.type === "PERSON" || e.type === "ORGANIZATION") && (
        <div className="grid grid-cols-3 divide-x divide-rule border-b border-rule-strong">
          {([["Priority", e.priority, INK.pencil], ["Influence", e.influence, INK.ink], ["Suspicion", e.suspicion, INK.amber]] as const).map(([k, v, c]) => (
            <div key={k} className="px-3 py-1.5"><div className="label text-ink-faint">{k}</div><div className="figure text-[var(--fs-title)] font-semibold" style={{ color: c }}>{v.toFixed(2)}</div></div>
          ))}
        </div>
      )}
      <nav className="flex border-b border-rule-strong px-1" aria-label="Note sections">
        {TABS.filter((t) => t !== "Money" || d?.money).filter((t) => t !== "Calls" || d?.calls).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} aria-pressed={tab === t} className={cn("label px-2.5 py-1.5", tab === t ? "label-ink pencil-line" : "text-ink-faint hover:text-ink")}>{t}</button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6">
        {isError && <p className="mt-4 text-pencil">This entity could not be loaded.</p>}
        {isLoading && <div className="mt-3 space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="h-4 animate-pulse bg-film-deep" style={{ width: `${80 - i * 12}%` }} />)}</div>}
        {d && e && tab === "Notes" && (
          <div className="mt-2">
            {e.role_reasons?.length > 0 && <section className="mb-3"><h3 className="label">Why this role</h3><ul className="mt-1 list-disc pl-4 text-[var(--fs-body)] text-ink">{e.role_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}
            {e.suspicion_reasons?.length > 0 && <section className="mb-3"><h3 className="label">Suspicion signals</h3><ul className="mt-1 list-disc pl-4 text-[var(--fs-body)] text-ink">{e.suspicion_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}
            <dl className="mb-3">
              {e.community !== null && <Row k="Community" v={`#${e.community}`} />}
              <Row k="Degree" v={e.degree} />
              {e.first_seen && <Row k="First seen" v={format(new Date(e.first_seen), "dd MMM yyyy")} />}
              {e.last_seen && <Row k="Last seen" v={format(new Date(e.last_seen), "dd MMM yyyy")} />}
              {Object.entries(e.attrs).filter(([k, v]) => v !== null && v !== "" && !["lat", "lon", "document_id", "source", "fingerprint", "context"].includes(k) && typeof v !== "object").slice(0, 10).map(([k, v]) => <Row key={k} k={k.replace(/_/g, " ")} v={String(v)} />)}
              {Array.isArray(e.attrs.context) && <Row k="Context" v={(e.attrs.context as string[]).join("; ")} />}
            </dl>
            {d.alerts.length > 0 && (
              <section className="mb-3">
                <h3 className="label">Alerts on this entity</h3>
                <ul className="mt-1 divide-y divide-rule">
                  {d.alerts.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 py-1.5">
                      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ background: SEVERITY_INK[a.severity] }} />
                      <span className="min-w-0 flex-1 truncate text-[var(--fs-body)]">{ALERT_KIND_LABEL[a.kind] ?? a.kind}: {a.title}</span>
                      <select aria-label="Alert status" value={a.status} onChange={(ev) => patch.mutate({ id: a.id, status: ev.target.value as "open" })} className="label border border-rule-strong bg-film px-1 py-0.5">
                        {["open", "reviewing", "confirmed", "dismissed"].map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {d.removal_impact && (
              <section className="mb-3 border border-pencil-soft bg-[var(--pencil-wash)] p-2">
                <h3 className="label text-pencil">If removed</h3>
                <p className="mt-1 text-[var(--fs-body)] text-ink">Cuts <span className="figure font-semibold">{Math.round((d.removal_impact.flow_share ?? 0) * 100)}%</span> of this community’s interaction volume; fragments it by <span className="figure font-semibold">{Math.round((d.removal_impact.community_fragmentation ?? 0) * 100)}%</span>{d.removal_impact.isolated_after?.length ? <>; isolates {d.removal_impact.isolated_after.map((x) => x.label).join(", ")}</> : null}.</p>
              </section>
            )}
            <div className="flex flex-wrap gap-2">
              <Link href={`/chart?focus=${e.id}&depth=2`} className="label rounded-[2px] border border-ink px-2 py-1 hover:bg-ink hover:text-film">Redraw around this</Link>
              <button type="button" onClick={() => setHighlights([e.id, ...assoc.slice(0, 8).map((a) => a.other.id)], `${e.label} and their eight strongest associates are emphasised.`)} className="label rounded-[2px] border border-rule-strong px-2 py-1 hover:border-ink">Emphasise associates</button>
              <button type="button" onClick={() => setRoute(null)} className="label rounded-[2px] border border-rule-strong px-2 py-1 hover:border-ink">Clear route</button>
            </div>
          </div>
        )}
        {d && tab === "Associates" && (
          <ol className="mt-1">
            {assoc.map((a, i) => (
              <li key={a.other.id} className="border-b border-rule py-1.5">
                <button type="button" onClick={() => select(a.other.id)} className="flex w-full items-center gap-2 text-left hover:text-pencil">
                  <span className="figure label text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                  <Glyph shape={SHAPE[a.other.type]} size={13} />
                  <span className="min-w-0 flex-1 truncate text-[var(--fs-body)]">{a.other.label}</span>
                  <span className="figure note">{a.weight.toFixed(1)}</span>
                </button>
                <p className="note pl-7">{Object.entries(a.channels).map(([k, v]) => `${k} ${v}`).join(" · ")}{a.amount ? ` · ${fmtInr(a.amount)}` : ""}{a.night_calls ? ` · ${a.night_calls} night` : ""}</p>
              </li>
            ))}
            {!assoc.length && <li className="note py-3">No projected associates: this entity has no person-to-person channel yet.</li>}
          </ol>
        )}
        {d && tab === "Evidence" && <ol className="mt-1">{d.evidence.map((ev, i) => <EvidenceNote key={i} e={ev} i={i} />)}{!d.evidence.length && <li className="note py-3">No evidence snippets recorded.</li>}</ol>}
        {d && tab === "Money" && d.money && (
          <div className="mt-2 text-[var(--fs-body)]">
            <dl><Row k="Accounts" v={d.money.accounts.join(", ") || "—"} /><Row k="Inbound" v={fmtInr(d.money.total_in)} /><Row k="Outbound" v={fmtInr(d.money.total_out)} /></dl>
            <h3 className="label mt-3">Top sources</h3><ul className="mt-1">{d.money.top_sources.map(([s, v]) => <li key={s} className="flex justify-between border-b border-rule py-1"><span className="truncate">{s}</span><span className="figure text-blue">{fmtInr(v)}</span></li>)}</ul>
            <h3 className="label mt-3">Top destinations</h3><ul className="mt-1">{d.money.top_destinations.map(([s, v]) => <li key={s} className="flex justify-between border-b border-rule py-1"><span className="truncate">{s}</span><span className="figure text-blue">{fmtInr(v)}</span></li>)}</ul>
          </div>
        )}
        {d && tab === "Calls" && d.calls && (
          <div className="mt-2 text-[var(--fs-body)]">
            <dl><Row k="Numbers" v={d.calls.phones.join(", ")} /><Row k="Calls" v={d.calls.total_calls} /><Row k="At night" v={`${Math.round(d.calls.night_ratio * 100)}%`} /></dl>
            <h3 className="label mt-3">By hour</h3>
            <div className="mt-1 flex h-12 items-end gap-px" aria-label="Calls by hour of day">{d.calls.by_hour.map((v, h) => { const m = Math.max(1, ...d.calls!.by_hour); return <div key={h} title={`${h}:00 — ${v}`} className={cn("flex-1", h >= 23 || h < 5 ? "bg-pencil" : "bg-ink")} style={{ height: `${(v / m) * 100}%`, opacity: v ? 1 : 0.15 }} />; })}</div>
            <h3 className="label mt-3">Most frequent contacts</h3>
            <ol className="mt-1">{d.calls.top_contacts.map((c) => <li key={c.phone} className="flex items-center justify-between border-b border-rule py-1">{c.owner_id ? <button type="button" onClick={() => select(c.owner_id!)} className="truncate text-left hover:text-pencil">{c.owner}</button> : <span className="figure">{c.phone}</span>}<span className="figure note">{c.calls}×</span></li>)}</ol>
          </div>
        )}
        {d && tab === "Timeline" && (
          <ol className="mt-1">
            {d.timeline.slice().reverse().slice(0, 80).map((t) => (
              <li key={t.id} className="grid grid-cols-[5.5rem_1fr] gap-2 border-b border-rule py-1.5 text-[var(--fs-note)]"><span className="figure text-ink-faint">{format(new Date(t.at), "dd MMM HH:mm")}</span><span className="text-ink"><span className="label mr-1 text-ink-faint">{t.kind}</span>{t.summary}</span></li>
            ))}
          </ol>
        )}
        {d && d.documents.length > 0 && tab === "Notes" && (
          <p className="mt-4 note">Appears in {d.documents.length} document{d.documents.length > 1 ? "s" : ""}. <Link href={`/sources?entity=${e!.id}`} className="inline-flex items-center gap-0.5 hover:text-pencil">Open sources<ExternalLink className="h-3 w-3" aria-hidden="true" /></Link></p>
        )}
      </div>
    </aside>
  );
}
