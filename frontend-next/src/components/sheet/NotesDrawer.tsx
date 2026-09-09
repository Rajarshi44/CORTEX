"use client";
/**
 * Numbered margin notes: the dossier of whatever is selected, with the sentence behind every line.
 *
 * Three rules govern this panel. Everything printed is a value the API actually recorded — no
 * placeholder rows, no invented citations. Every claim names the source it came from and links to
 * it where that source has a public page. And a property is shown as a person would write it, never
 * as the raw key and blob that arrived on the wire.
 */
import Link from "next/link";
import { useMemo, useState } from "react";
import { useSheet } from "@/lib/store";
import { useEntity, useAlertStatus, useAddNote, useUpdateNote, useDeleteNote } from "@/lib/queries";
import { Glyph, LineSample } from "./KeyRail";
import {
  SHAPE, TYPE_LABEL, INK, SEVERITY_INK, ALERT_KIND_LABEL, lineStyleFor, relLabel, fmtInr,
  attrRows, dateSpan,
} from "@/lib/notation";
import { sourceLabel, sourceHref } from "@/lib/provenance";
import type { Dossier, DossierDocument, Evidence, Note } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X, ExternalLink } from "lucide-react";
import { format } from "date-fns";

const TABS = ["Record", "Links", "Evidence", "Associates", "Money", "Calls", "Timeline", "Notes"] as const;

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="grid grid-cols-[7.5rem_1fr] gap-2 py-0.5 text-[length:var(--fs-body)]"><dt className="label text-ink-faint">{k}</dt><dd className="figure min-w-0 break-words text-ink">{v}</dd></div>;
}

/** A safe date, or nothing. Sources leave dates out far more often than they get them wrong. */
function when(iso: string | null | undefined, pattern = "dd MMM yyyy"): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : format(d, pattern);
}

/**
 * The document behind a claim. With a public page it is a link; without one it is the document and
 * the body that holds it, in plain text — a source with no address is still named, never faked into
 * a link that goes nowhere.
 */
function SourceLink({ title, href, plain, className }: { title: string; href: string | null; plain?: string; className?: string }) {
  if (!href) return <span className={cn("note", className)} title="This source has no public page to open">{title}{plain ? ` · ${plain}` : ""}</span>;
  // The marker rides the last word rather than a flex track, so a long title wraps without stranding it.
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cn("note text-blue underline decoration-blue-soft hover:text-pencil hover:decoration-pencil", className)}>
      {title}<span aria-hidden="true">{" ↗"}</span>
    </a>
  );
}

/** One extracted claim: what was said, how it was read out of the document, and where the document is. */
function EvidenceNote({ e, i }: { e: Evidence; i: number }) {
  const style = lineStyleFor(e.extractor, e.confidence);
  const href = sourceHref(e.source_type, e.source_url);
  const at = when(e.at);
  return (
    <li className="border-b border-rule py-2 last:border-b-0">
      <blockquote className="border-l border-rule-strong pl-2 text-[length:var(--fs-body)] leading-snug text-ink">“{(e.snippet ?? "").trim()}”</blockquote>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 pl-2">
        <span className="figure label text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
        <span className="flex-1 text-[var(--fs-note)] leading-tight text-ink-soft">
          Extracted by <span className="label text-ink">{e.extractor}</span>
          {e.at && <span> at <span className="figure text-ink">{format(new Date(e.at), "dd MMM HH:mm")}</span></span>}
        </span>
        <LineSample style={style} width={22} />
        <span className="label figure px-1 py-0.5 text-ink-faint">{(e.confidence * 100).toFixed(0)}% conf</span>
      </div>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-2 pl-2">
        <SourceLink title={e.document_title} href={href} plain={sourceLabel(e.source_type, e.source_name)} />
        <Link href={`/sources?doc=${e.document_id}`} className="note text-ink-faint hover:text-pencil">read on the sheet</Link>
      </p>
    </li>
  );
}

/** Documents this entity appears in, each named by the body that published it. */
function DocumentRow({ d }: { d: DossierDocument }) {
  const href = sourceHref(d.source_type, d.source_url);
  const at = when(d.occurred_at);
  return (
    <li className="border-b border-rule py-1.5 last:border-b-0">
      <div className="flex items-baseline gap-2">
        <span className="label shrink-0 text-ink-faint">{d.source_type}</span>
        <Link href={`/sources?doc=${d.id}`} className="min-w-0 flex-1 truncate text-[length:var(--fs-body)] text-ink hover:text-pencil">{d.title}</Link>
        {at && <span className="figure note shrink-0">{at}</span>}
      </div>
      <p className="pl-1 note">{sourceLabel(d.source_type, d.source_name)} · <SourceLink title={href ? "open the source" : "no public page"} href={href} /></p>
    </li>
  );
}

function NoteItem({ n, eId }: { n: Note; eId: string }) {
  const user = useSheet((s) => s.user);
  const deleteNote = useDeleteNote();
  const updateNote = useUpdateNote();
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(n.text);
  const canEdit = user?.username === n.username || user?.role === "admin";

  if (isEditing) {
    return (
      <li className="border-l-2 border-rule pl-3">
        <div className="flex items-baseline gap-2">
          <span className="label text-ink">{n.username}</span>
          <span className="figure note">{when(n.created_at, "dd MMM HH:mm")}</span>
        </div>
        <textarea value={editText} onChange={e => setEditText(e.target.value)} className="w-full mt-1 bg-film text-ink border border-rule-strong p-1 text-[length:var(--fs-body)] resize-none" />
        <div className="mt-1 flex gap-2">
          <button onClick={() => { updateNote.mutate({ entityId: eId, noteId: n.id, text: editText }, { onSuccess: () => setIsEditing(false) }) }} disabled={updateNote.isPending} className="label text-ink hover:text-pencil">Save</button>
          <button onClick={() => setIsEditing(false)} className="label text-ink-faint hover:text-ink">Cancel</button>
        </div>
      </li>
    );
  }

  return (
    <li className="border-l-2 border-rule pl-3 group">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <span className="label text-ink">{n.username}</span>
          <span className="figure note ml-2">{when(n.created_at, "dd MMM HH:mm")}</span>
        </div>
        {canEdit && (
          <div className="hidden gap-3 group-hover:flex">
            <button type="button" onClick={() => setIsEditing(true)} className="label note text-ink-faint hover:text-pencil">Edit</button>
            <button type="button" onClick={() => deleteNote.mutate({ entityId: eId, noteId: n.id })} disabled={deleteNote.isPending} className="label note text-ink-faint hover:text-pencil">Delete</button>
          </div>
        )}
      </div>
      <p className="mt-0.5 text-[length:var(--fs-body)] text-ink-faint whitespace-pre-wrap">{n.text}</p>
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
  const [tab, setTab] = useState<(typeof TABS)[number]>("Record");
  const [noteText, setNoteText] = useState("");
  const addNote = useAddNote();
  const patch = useAlertStatus();
  const d = data as Dossier | undefined;
  const e = d?.entity;

  const assoc = useMemo(() => d?.associates ?? [], [d]);
  /** Every recorded property, humanised. The keys vary by source, so nothing here is hard-coded. */
  const props = useMemo(() => attrRows(e?.attrs), [e]);
  /** Evidence grouped by the body that published it: "this came from OpenSanctions, that from the Court". */
  const evidenceBySource = useMemo(() => {
    const groups = new Map<string, { name: string; href: string | null; items: Evidence[] }>();
    for (const ev of d?.evidence ?? []) {
      const name = sourceLabel(ev.source_type, ev.source_name);
      const g = groups.get(name) ?? { name, href: sourceHref(ev.source_type, ev.source_url), items: [] };
      g.items.push(ev);
      groups.set(name, g);
    }
    return [...groups.values()].sort((a, b) => b.items.length - a.items.length);
  }, [d]);
  /** Relationships, largest family first, so the strongest structure reads at the top. */
  const relGroups = useMemo(
    () => Object.entries(d?.relationships ?? {}).sort((a, b) => b[1].length - a[1].length),
    [d],
  );

  if (!open || !selected) return null;

  const tabs = TABS.filter((t) => t !== "Money" || d?.money).filter((t) => t !== "Calls" || d?.calls);

  return (
    <aside aria-label="Margin notes" className="absolute inset-y-0 right-0 z-20 flex w-[var(--notes-w)] max-w-[92vw] flex-col border-l border-ink bg-film-lift shadow-[-8px_0_24px_-16px_rgba(31,31,31,0.5)]">
      <header className="flex items-start gap-2 border-b border-ink px-3 py-2">
        {e ? <Glyph shape={SHAPE[e.type]} size={18} stroke={e.type === "BANK_ACCOUNT" ? INK.blue : INK.ink} className="mt-1 shrink-0" /> : <span className="h-4 w-4" />}
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[length:var(--fs-title)] font-semibold leading-tight text-ink">{e?.label ?? (isLoading ? "Loading note…" : "—")}</h2>
          <p className="note truncate">{e ? [TYPE_LABEL[e.type], e.aliases?.length ? `@ ${e.aliases.join(", ")}` : null, e.role].filter(Boolean).join(" · ") : ""}</p>
        </div>
        <button type="button" onClick={() => { setOpen(false); select(null); }} aria-label="Close notes" className="rounded-[2px] p-1 text-ink-soft hover:bg-film-deep hover:text-ink"><X className="h-4 w-4" /></button>
      </header>
      {e && (e.type === "PERSON" || e.type === "ORGANIZATION") && (
        <div className="grid grid-cols-3 divide-x divide-rule border-b border-rule-strong">
          {([["Priority", e.priority, INK.pencil], ["Influence", e.influence, INK.ink], ["Suspicion", e.suspicion, INK.amber]] as const).map(([k, v, c]) => (
            <div key={k} className="px-3 py-1.5"><div className="label text-ink-faint">{k}</div><div className="figure text-[length:var(--fs-title)] font-semibold" style={{ color: c }}>{v.toFixed(2)}</div></div>
          ))}
        </div>
      )}
      <nav className="flex overflow-x-auto whitespace-nowrap border-b border-rule-strong px-1 scrollbar-hide" aria-label="Note sections">
        {tabs.map((t) => {
          const n = t === "Evidence" ? d?.evidence.length : t === "Links" ? relGroups.reduce((a, [, r]) => a + r.length, 0) : t === "Associates" ? assoc.length : undefined;
          return (
            <button key={t} type="button" onClick={() => setTab(t)} aria-pressed={tab === t} className={cn("label px-2.5 py-1.5 shrink-0", tab === t ? "label-ink pencil-line" : "text-ink-faint hover:text-ink")}>
              {t}{n ? <span className="figure ml-1 text-ink-faint">{n}</span> : null}
            </button>
          );
        })}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6">
        {isError && <p className="mt-4 text-pencil">This entity could not be loaded.</p>}
        {isLoading && <div className="mt-3 space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="h-4 animate-pulse bg-film-deep" style={{ width: `${80 - i * 12}%` }} />)}</div>}

        {d && e && tab === "Record" && (
          <div className="mt-2">
            {e.role_reasons?.length > 0 && <section className="mb-3"><h3 className="label">Why this role</h3><ul className="mt-1 list-disc pl-4 text-[length:var(--fs-body)] text-ink">{e.role_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}
            {e.suspicion_reasons?.length > 0 && <section className="mb-3"><h3 className="label">Suspicion signals</h3><ul className="mt-1 list-disc pl-4 text-[length:var(--fs-body)] text-ink">{e.suspicion_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}

            <section className="mb-4">
              <h3 className="label border-b border-rule pb-1">On the chart</h3>
              <dl className="mt-1">
                <Row k="Type" v={TYPE_LABEL[e.type]} />
                {e.community !== null && <Row k="Community" v={`#${e.community}`} />}
                <Row k="Links drawn" v={e.degree} />
                <Row k="Mentions" v={e.mentions} />
                {when(e.first_seen) && <Row k="First seen" v={when(e.first_seen)} />}
                {when(e.last_seen) && <Row k="Last seen" v={when(e.last_seen)} />}
              </dl>
            </section>

            <section className="mb-4">
              <h3 className="label border-b border-rule pb-1">Recorded properties{props.length ? <span className="figure ml-1 text-ink-faint">{props.length}</span> : null}</h3>
              {props.length > 0 ? (
                <dl className="mt-1">
                  {props.map((p) => (
                    <Row
                      key={p.key}
                      k={p.label}
                      v={p.href
                        ? <a href={p.href} target="_blank" rel="noopener noreferrer" className="text-blue underline decoration-blue-soft hover:text-pencil">{p.value}</a>
                        : p.value}
                    />
                  ))}
                </dl>
              ) : (
                <p className="mt-1 note">No properties were recorded for this entity beyond its name and its links.</p>
              )}
            </section>

            {d.alerts.length > 0 && (
              <section className="mb-4">
                <h3 className="label border-b border-rule pb-1">Alerts on this entity</h3>
                <ul className="mt-1 divide-y divide-rule">
                  {d.alerts.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 py-1.5">
                      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ background: SEVERITY_INK[a.severity] }} />
                      <span className="min-w-0 flex-1 text-[length:var(--fs-body)]">{ALERT_KIND_LABEL[a.kind] ?? a.kind}: {a.title}</span>
                      <select aria-label="Alert status" value={a.status} onChange={(ev) => patch.mutate({ id: a.id, status: ev.target.value as "open" })} className="label border border-rule-strong bg-film px-1 py-0.5">
                        {["open", "reviewing", "confirmed", "dismissed"].map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {d.removal_impact && (
              <section className="mb-4 border border-pencil-soft bg-[var(--pencil-wash)] p-2">
                <h3 className="label text-pencil">If removed</h3>
                <p className="mt-1 text-[length:var(--fs-body)] text-ink">Cuts <span className="figure font-semibold">{Math.round((d.removal_impact.flow_share ?? 0) * 100)}%</span> of this community’s interaction volume; fragments it by <span className="figure font-semibold">{Math.round((d.removal_impact.community_fragmentation ?? 0) * 100)}%</span>{d.removal_impact.isolated_after?.length ? <>; isolates {d.removal_impact.isolated_after.map((x) => x.label).join(", ")}</> : null}.</p>
              </section>
            )}

            <div className="flex flex-wrap gap-2">
              <Link href={`/chart?focus=${e.id}&depth=2`} className="label rounded-[2px] border border-ink px-2 py-1 hover:bg-ink hover:text-film">Redraw around this</Link>
              <button type="button" onClick={() => setHighlights([e.id, ...assoc.slice(0, 8).map((a) => a.other.id)], `${e.label} and their eight strongest associates are emphasised.`)} className="label rounded-[2px] border border-rule-strong px-2 py-1 hover:border-ink">Emphasise associates</button>
              <button type="button" onClick={() => setRoute(null)} className="label rounded-[2px] border border-rule-strong px-2 py-1 hover:border-ink">Clear route</button>
            </div>
          </div>
        )}

        {d && e && tab === "Links" && (
          <div className="mt-2">
            {relGroups.map(([rel, rows]) => (
              <section key={rel} className="mb-4">
                <h3 className="label flex items-baseline gap-2 border-b border-rule pb-1">
                  <span className="label-ink">{relLabel(rel)}</span><span className="figure text-ink-faint">{rows.length}</span>
                </h3>
                <ul>
                  {rows.map((r, i) => {
                    const span = dateSpan(r.first_seen, r.last_seen);
                    const subject = r.direction === "out" ? e.label : r.other.label;
                    const object = r.direction === "out" ? r.other.label : e.label;
                    return (
                      <li key={`${r.other.id}-${i}`} className="border-b border-rule py-1.5 last:border-b-0">
                        <button type="button" onClick={() => select(r.other.id)} className="flex w-full items-center gap-2 text-left hover:text-pencil">
                          <Glyph shape={SHAPE[r.other.type]} size={13} stroke={r.other.type === "BANK_ACCOUNT" ? INK.blue : INK.ink} />
                          <span className="min-w-0 flex-1 truncate text-[length:var(--fs-body)]">{r.other.label}</span>
                          {r.count > 1 && <span className="figure note shrink-0">{r.count}×</span>}
                        </button>
                        <p className="note pl-7">
                          {subject} {relLabel(rel)} {object}
                          {span ? ` · ${span}` : ""}
                          {r.confidence < 1 ? ` · ${Math.round(r.confidence * 100)}% confidence` : ""}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
            {!relGroups.length && <p className="note py-3">No relationships are drawn to this entity yet.</p>}
          </div>
        )}

        {d && tab === "Evidence" && (
          <div className="mt-2">
            {evidenceBySource.map((g) => (
              <section key={g.name} className="mb-4">
                <h3 className="label flex flex-wrap items-baseline gap-x-2 border-b border-rule pb-1">
                  <span className="label-ink">{g.name}</span>
                  <span className="figure text-ink-faint">{g.items.length}</span>
                  {g.href && <a href={g.href} target="_blank" rel="noopener noreferrer" className="label ml-auto text-blue hover:text-pencil">source ↗</a>}
                </h3>
                <ol className="mt-1">{g.items.map((ev, i) => <EvidenceNote key={`${ev.document_id}-${i}`} e={ev} i={i} />)}</ol>
              </section>
            ))}
            {!evidenceBySource.length && <p className="note py-3">No evidence snippets recorded for this entity.</p>}
            {d.documents.length > 0 && (
              <section className="mb-4">
                <h3 className="label flex items-baseline gap-2 border-b border-rule pb-1"><span className="label-ink">Documents it appears in</span><span className="figure text-ink-faint">{d.documents.length}</span></h3>
                <ul className="mt-1">{d.documents.map((doc) => <DocumentRow key={doc.id} d={doc} />)}</ul>
              </section>
            )}
          </div>
        )}

        {d && tab === "Associates" && (
          <ol className="mt-1">
            {assoc.map((a, i) => (
              <li key={a.other.id} className="border-b border-rule py-1.5">
                <button type="button" onClick={() => select(a.other.id)} className="flex w-full items-center gap-2 text-left hover:text-pencil">
                  <span className="figure label text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                  <Glyph shape={SHAPE[a.other.type]} size={13} />
                  <span className="min-w-0 flex-1 truncate text-[length:var(--fs-body)]">{a.other.label}</span>
                  <span className="figure note">{a.weight.toFixed(1)}</span>
                </button>
                <p className="note pl-7">{Object.entries(a.channels).map(([k, v]) => `${k} ${v}`).join(" · ")}{a.amount ? ` · ${fmtInr(a.amount)}` : ""}{a.night_calls ? ` · ${a.night_calls} night` : ""}</p>
              </li>
            ))}
            {!assoc.length && <li className="note py-3">No projected associates: this entity has no person-to-person channel yet.</li>}
          </ol>
        )}

        {d && tab === "Money" && d.money && (
          <div className="mt-2 text-[length:var(--fs-body)]">
            <dl><Row k="Accounts" v={d.money.accounts.join(", ") || "—"} /><Row k="Inbound" v={fmtInr(d.money.total_in)} /><Row k="Outbound" v={fmtInr(d.money.total_out)} /></dl>
            <h3 className="label mt-3">Top sources</h3><ul className="mt-1">{d.money.top_sources.map(([s, v]) => <li key={s} className="flex justify-between border-b border-rule py-1"><span className="truncate">{s}</span><span className="figure text-blue">{fmtInr(v)}</span></li>)}</ul>
            <h3 className="label mt-3">Top destinations</h3><ul className="mt-1">{d.money.top_destinations.map(([s, v]) => <li key={s} className="flex justify-between border-b border-rule py-1"><span className="truncate">{s}</span><span className="figure text-blue">{fmtInr(v)}</span></li>)}</ul>
          </div>
        )}

        {d && tab === "Calls" && d.calls && (
          <div className="mt-2 text-[length:var(--fs-body)]">
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
              <li key={t.id} className="grid grid-cols-[5.5rem_1fr] gap-2 border-b border-rule py-1.5 text-[length:var(--fs-note)]"><span className="figure text-ink-faint">{when(t.at, "dd MMM HH:mm")}</span><span className="text-ink"><span className="label mr-1 text-ink-faint">{t.kind}</span>{t.summary}</span></li>
            ))}
            {!d.timeline.length && <li className="note py-3">No dated events are recorded for this entity.</li>}
          </ol>
        )}

        {d && e && tab === "Notes" && (
          <div className="mt-4">
            {d.notes && d.notes.length > 0 && (
              <ul className="mb-4 space-y-3">
                {d.notes.map((n) => (
                  <NoteItem key={n.id} n={n} eId={e.id} />
                ))}
              </ul>
            )}
            <form onSubmit={(ev) => {
              ev.preventDefault();
              if (noteText.trim()) {
                addNote.mutate({ entityId: e.id, text: noteText }, { onSuccess: () => setNoteText("") });
              }
            }}>
              <textarea
                value={noteText}
                onChange={(ev) => setNoteText(ev.target.value)}
                placeholder="Write a note..."
                className="w-full bg-film text-ink border border-rule-strong p-2 text-[length:var(--fs-body)] focus:outline-none focus:border-ink resize-none min-h-[60px]"
              />
              <div className="mt-2 flex justify-end">
                <button type="submit" disabled={!noteText.trim() || addNote.isPending} className="bg-ink text-film label px-3 py-1 hover:opacity-80 disabled:opacity-50">
                  {addNote.isPending ? "Saving..." : "Save note"}
                </button>
              </div>
            </form>
            {d.documents.length > 0 && (
              <p className="mt-4 note border-t border-rule pt-4">Appears in {d.documents.length} document{d.documents.length > 1 ? "s" : ""}. <Link href={`/sources?entity=${e.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 hover:text-pencil">Open sources<ExternalLink className="h-3 w-3" aria-hidden="true" /></Link></p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
