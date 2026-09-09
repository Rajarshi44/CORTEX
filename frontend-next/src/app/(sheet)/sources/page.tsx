"use client";
/**
 * Sources and ingestion, read in three passes.
 *
 *   1. What is on the sheet — the counts, and which body each document came from, linked.
 *   2. Add more — the connectors, grouped, each said plainly, with its harvest presets.
 *   3. Documents — the browsable corpus with its filters.
 *
 * Unavailable sources drop off, they do not grey out. Every capability the dense version had is
 * still here; only the order and the air between things have changed.
 */
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSources, useSourcesHealth, useIngestStatus, useDocuments, useDocument, useInvalidateSheet } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import { SHAPE } from "@/lib/notation";
import { CONNECTOR_GROUPS, CONNECTOR_GIST, connectorHref, sourceLabel, sourceHref, sourceGist, metaHref } from "@/lib/provenance";
import type { EntityType, SourceInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { ArrowUpRight } from "lucide-react";

const HARVEST_PRESETS: Record<string, { label: string; params: Record<string, unknown> }[]> = {
  courts: [{ label: "Supreme Court 2024, criminal", params: { court: "sc", year: 2024, limit: 120 } }, { label: "Bombay HC 2024", params: { court: "hc", year: 2024, bench: "bombay", limit: 80 } }],
  icij: [{ label: "India subset", params: { country: "India", max_officers: 300 } }],
  gleif: [{ label: "Tata group tree", params: { query: "Tata", limit: 8, depth: 1 } }],
  opensanctions: [{ label: "Criminal-interest list", params: { dataset: "crime", limit: 600 } }, { label: "INTERPOL red notices", params: { dataset: "interpol_red_notices", limit: 600 } }],
  benchmarks: [{ label: "Montreal gangs", params: { dataset: "montreal" } }, { label: "9/11 cells", params: { dataset: "terrorists_911" } }, { label: "St. Louis police records", params: { dataset: "crime" } }],
  wanted: [{ label: "All pages", params: {} }],
  news: [{ label: "Crime feeds", params: { limit: 30 } }],
  ncrb: [{ label: "Crime in India datasets", params: { year: 2024 } }],
  datagovin: [{ label: "Search 'crime'", params: { title: "crime", limit: 200 } }],
  cctns_mh: [{ label: "Mumbai City, 30 days", params: { district: "Mumbai City", days: 30 } }],
};
const SRC_TYPES = ["FIR", "CDR", "TRANSACTION", "KYC", "SURVEILLANCE", "SOCIAL", "INTEL", "JUDGMENT", "NEWS", "LEAK", "WATCHLIST", "GLEIF", "BENCHMARK", "STATS"];

/** One of the three passes down the page: a numbered rule, a title, and one line saying why it is here. */
function Zone({ n, title, lead, aside, id, children }: { n: string; title: string; lead: string; aside?: React.ReactNode; id?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="col-span-12 scroll-mt-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-ink pb-2">
        <span className="stencil text-[length:var(--fs-title)] font-bold leading-none text-ink-faint" aria-hidden="true">{n}</span>
        <h2 className="text-[length:var(--fs-title)] font-semibold leading-none tracking-tight text-ink">{title}</h2>
        {aside && <div className="ml-auto flex items-baseline gap-3">{aside}</div>}
      </div>
      <p className="mt-2 max-w-[80ch] text-ink-soft">{lead}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Sources() {
  const { data: src } = useSources();
  const { data: health, refetch: recheck, isFetching: checking } = useSourcesHealth();
  const [docId, setDocId] = useQueryState("doc", parseAsString);
  const [entityId] = useQueryState("entity", parseAsString);
  const [docType, setDocType] = useState("");
  const [docQ, setDocQ] = useState("");
  const { data: docs } = useDocuments({ source_type: docType || undefined, q: docQ || undefined, limit: 80, entity_id: entityId || undefined });
  const { data: doc } = useDocument(docId);
  const invalidate = useInvalidateSheet();
  const user = useSheet((s) => s.user);
  const select = useSheet((s) => s.select);
  const [job, setJob] = useState<{ status: string; stage: string | null; done: number; total: number; report?: unknown; error?: string; stats?: unknown } | null>(null);
  const { data: status } = useIngestStatus(job?.status === "running");
  const wsRef = useRef<WebSocket | null>(null);
  const [text, setText] = useState({ source_type: "FIR", title: "", text: "" });
  const [uploadType, setUploadType] = useState("CDR");
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  // live progress over the backend's WebSocket
  useEffect(() => {
    let alive = true; let ws: WebSocket | null = null; let ping: ReturnType<typeof setInterval> | undefined;
    const connect = () => {
      try { ws = new WebSocket(api.wsUrl()); } catch { return; }
      wsRef.current = ws;
      ws.onmessage = (m) => { try { const j = JSON.parse(m.data); if (alive) { setJob(j); if (j.status === "done") { invalidate(); toast.success(`Ingested: ${j.stage}`); } if (j.status === "error") toast.error(j.error ?? "Ingestion failed"); } } catch { /* ignore */ } };
      ws.onopen = () => { ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 15000); };
      ws.onclose = () => { clearInterval(ping); if (alive) setTimeout(connect, 3000); };
    };
    connect();
    return () => { alive = false; clearInterval(ping); ws?.close(); };
  }, [invalidate]);

  const run = async (fn: () => Promise<unknown>, what: string) => { try { await fn(); toast(`${what} started`); } catch (e) { toast.error((e as Error).message); } };
  const byName = new Map((health ?? []).map((h) => [h.name, h]));
  const live = (src?.sources ?? []).filter((s) => (byName.get(s.name)?.status ?? "ok") !== "blocked" && byName.get(s.name)?.status !== "error");
  const dropped = (src?.sources ?? []).filter((s) => !live.includes(s));

  /** What each body actually put on the sheet, largest contribution first. */
  const breakdown = useMemo(() => {
    const documents = status?.documents ?? {};
    const records = status?.records ?? {};
    return Object.keys({ ...documents, ...records })
      .map((t) => ({ type: t, documents: documents[t] ?? 0, records: records[t] ?? 0, name: sourceLabel(t), href: sourceHref(t), gist: sourceGist(t) }))
      .sort((a, b) => b.records - a.records || b.documents - a.documents);
  }, [status]);

  /** The connectors, in the groups an analyst thinks in; anything new to the API still shows, under "Other". */
  const placed = new Set(CONNECTOR_GROUPS.flatMap((g) => g.names));
  const grouped = CONNECTOR_GROUPS
    .map((g) => ({ ...g, sources: g.names.map((n) => live.find((s) => s.name === n)).filter((s): s is SourceInfo => !!s) }))
    .filter((g) => g.sources.length > 0);
  const ungrouped = live.filter((s) => !placed.has(s.name));
  const groups = ungrouped.length
    ? [...grouped, { key: "other", label: "Other connectors", blurb: "Newly registered on the backend.", names: [] as string[], sources: ungrouped }]
    : grouped;

  const totalDocs = Object.values(status?.documents ?? {}).reduce((a, b) => a + b, 0);
  const totalRecords = Object.values(status?.records ?? {}).reduce((a, b) => a + b, 0);
  const showDocuments = (t: string) => { setDocType(t); window.document.getElementById("documents")?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto grid w-full max-w-[1500px] grid-cols-12 gap-x-6 gap-y-12 px-6 py-6">
        <section className="col-span-12 flex flex-wrap items-end justify-between gap-6 border-b border-ink pb-3">
          <div><h1 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Sources and ingestion</h1><p className="mt-2 max-w-[70ch] text-ink-soft">Every document on the sheet is sealed in the evidence ledger at collection. Live connectors respect robots.txt and rate limits; a source that is blocked or down is dropped from this list rather than shown greyed.</p></div>
          <dl className="grid grid-cols-4 gap-x-8 text-right">
            {([["Documents", totalDocs], ["Records", totalRecords], ["Entities", status?.entities], ["Events", status?.events]] as const).map(([k, v]) => <div key={k}><dt className="label text-ink-faint">{k}</dt><dd className="figure text-[length:var(--fs-title)] font-semibold leading-none">{v?.toLocaleString("en-IN") ?? "—"}</dd></div>)}
          </dl>
        </section>

        {job && job.status !== "idle" && (
          <section className="col-span-12 note-paper border border-ink px-3 py-2" aria-live="polite">
            <div className="flex items-center gap-3"><span className={cn("label", job.status === "error" ? "text-pencil" : job.status === "done" ? "text-green" : "label-ink")}>{job.status}</span><span className="text-[length:var(--fs-body)]">{job.stage}</span>{job.total > 0 && <span className="figure ml-auto note">{job.done} / {job.total}</span>}</div>
            {job.status === "running" && <div className="mt-1 h-1 w-full bg-film-deep"><div className="h-full bg-pencil transition-[width]" style={{ width: job.total ? `${(job.done / job.total) * 100}%` : "30%" }} /></div>}
            {job.error && <p className="mt-1 text-pencil">{job.error}</p>}
          </section>
        )}

        {/* ---------------------------------------------------------------- 1 */}
        <Zone
          n="01"
          title="What is on the sheet"
          lead="Each body below contributed the documents counted against it. Open the source to check any of it against the original: these are public records, and nothing here asks to be taken on trust."
        >
          {breakdown.length === 0 && <p className="note">The sheet is empty. Build it from public records in the next section, or load the demo corpus.</p>}
          <ul className="grid gap-x-6 gap-y-0 sm:grid-cols-2 xl:grid-cols-3">
            {breakdown.map((b) => (
              <li key={b.type} className="border-t border-rule py-3 first:border-t-0 sm:first:border-t sm:[&:nth-child(-n+2)]:border-t-0 xl:[&:nth-child(3)]:border-t-0">
                <div className="flex items-baseline gap-2">
                  <span className="label label-ink">{b.type}</span>
                  <span className="figure ml-auto text-[length:var(--fs-lead)] font-semibold leading-none">{b.documents.toLocaleString("en-IN")}</span>
                  <span className="label text-ink-faint">doc{b.documents === 1 ? "" : "s"}</span>
                </div>
                <p className="mt-1 text-[length:var(--fs-body)] text-ink">{b.name}</p>
                <p className="note">{b.gist}</p>
                <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3">
                  <button type="button" onClick={() => showDocuments(b.type)} className="label text-ink-soft hover:text-pencil">browse {b.records.toLocaleString("en-IN")} record{b.records === 1 ? "" : "s"}</button>
                  {b.href
                    ? <a href={b.href} target="_blank" rel="noopener noreferrer" className="label inline-flex items-baseline gap-1 text-blue hover:text-pencil">open the source<ArrowUpRight className="h-3 w-3 translate-y-0.5" aria-hidden="true" /></a>
                    : <span className="note text-ink-faint">no public page</span>}
                </div>
              </li>
            ))}
          </ul>
        </Zone>

        {/* ---------------------------------------------------------------- 2 */}
        <Zone
          n="02"
          title="Add more"
          lead="Ten live connectors, grouped by what they tell you. Pick a preset and the harvest runs in the background; progress streams at the top of this page and the sheet redraws when it lands."
          aside={<>
            <span className="label text-ink-faint">{live.length} reachable</span>
            <button type="button" onClick={() => recheck()} className="label text-ink-soft hover:text-pencil">{checking ? "checking…" : "re-check"}</button>
          </>}
        >
          <div className="grid gap-x-8 gap-y-8 lg:grid-cols-2">
            {groups.map((g) => (
              <section key={g.key}>
                <h3 className="label label-ink border-b border-rule-strong pb-1">{g.label}</h3>
                <p className="note mt-1">{g.blurb}</p>
                <ul className="mt-2 divide-y divide-rule">
                  {g.sources.map((s) => {
                    const h = byName.get(s.name);
                    const href = connectorHref(s.name, s.homepage);
                    return (
                      <li key={s.name} className="py-3">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <span className="font-semibold text-ink">{s.title}</span>
                          <span className={cn("label", h?.status === "ok" || h?.status === "cached" ? "text-green" : "text-ink-faint")}>{h?.status ?? "…"}</span>
                          {href && <a href={href} target="_blank" rel="noopener noreferrer" className="label ml-auto inline-flex items-baseline gap-1 text-blue hover:text-pencil">source<ArrowUpRight className="h-3 w-3 translate-y-0.5" aria-hidden="true" /></a>}
                        </div>
                        <p className="mt-1 max-w-[70ch] text-[length:var(--fs-body)] text-ink-soft">{CONNECTOR_GIST[s.name] ?? s.description}</p>
                        <p className="note mt-1">Licence: {s.licence}</p>
                        {canWrite && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {(HARVEST_PRESETS[s.name] ?? [{ label: "Harvest", params: {} }]).map((p) => (
                              <button key={p.label} type="button" onClick={() => run(() => api.harvest(s.name, p.params), `${s.title}: ${p.label}`)} className="label border border-rule-strong px-2 py-0.5 hover:border-ink hover:bg-film-deep">{p.label}</button>
                            ))}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
            {!src && [0, 1].map((i) => <div key={i} className="h-40 animate-pulse bg-film-deep/40" />)}
          </div>

          {dropped.length > 0 && <p className="mt-6 max-w-[90ch] note border-t border-rule pt-2">Dropped this session (blocked or unreachable from this network): {dropped.map((s) => `${s.title} — ${byName.get(s.name)?.reason || byName.get(s.name)?.status}`).join("; ")}.</p>}

          {canWrite && (
            <div className="mt-8">
              <h3 className="label label-ink border-b border-rule-strong pb-1">Or bring your own</h3>
              <div className="mt-3 grid gap-6 lg:grid-cols-2">
                <form onSubmit={async (e) => { e.preventDefault(); if (!text.text.trim()) return; try { const r = await api.ingestText(text.source_type, text.title || `${text.source_type} pasted ${format(new Date(), "dd MMM HH:mm")}`, text.text); invalidate(); toast.success(`${r.entities.length} entities extracted`); if (r.entities[0]) select(r.entities[0].id); setText({ ...text, text: "", title: "" }); } catch (err) { toast.error((err as Error).message); } }} className="note-paper p-4">
                  <h4 className="label label-ink">Paste a narrative</h4>
                  <p className="note mt-0.5">An FIR, intel note or judgment paragraph. Extracted in seconds, sealed, drawn on the sheet.</p>
                  <div className="mt-3 flex gap-2"><select value={text.source_type} onChange={(e) => setText({ ...text, source_type: e.target.value })} className="border border-rule-strong bg-film px-1.5 py-1">{["FIR", "INTEL", "REPORT"].map((t) => <option key={t}>{t}</option>)}</select><input value={text.title} onChange={(e) => setText({ ...text, title: e.target.value })} placeholder="Title (optional)" className="flex-1 border border-rule-strong bg-film px-2 py-1" /></div>
                  <textarea value={text.text} onChange={(e) => setText({ ...text, text: e.target.value })} rows={6} placeholder="On 20/02/2026 accused Sunil Pawar r/o Dharavi was apprehended…" className="mt-2 w-full border border-rule-strong bg-film p-2 text-[length:var(--fs-body)]" />
                  <button type="submit" className="label mt-2 bg-ink px-3 py-1.5 text-film hover:bg-pencil">Extract and draw</button>
                </form>
                <div className="note-paper flex flex-col p-4">
                  <h4 className="label label-ink">Upload a file</h4>
                  <p className="note mt-0.5">CSV for CDR, transactions, KYC; JSON for FIRs, surveillance, social, intel. Progress streams live at the top of the page.</p>
                  <div className="mt-3 flex gap-2"><select value={uploadType} onChange={(e) => setUploadType(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1">{["CDR", "TRANSACTION", "KYC", "FIR", "SURVEILLANCE", "SOCIAL", "INTEL"].map((t) => <option key={t}>{t}</option>)}</select><input type="file" accept=".csv,.json,.txt" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.upload(uploadType, f), `Upload ${f.name}`); }} className="flex-1 text-[length:var(--fs-note)] file:mr-2 file:border file:border-rule-strong file:bg-film file:px-2 file:py-1 file:text-[length:var(--fs-note)]" /></div>
                  <h4 className="label label-ink mt-6 border-t border-rule pt-3">Whole-sheet actions</h4>
                  <p className="note mt-0.5">Building from public records runs ICIJ, OpenSanctions, INTERPOL, the MHA banned list, NSE/SEBI debarments, GLEIF, NIA wanted notices, Supreme Court 2024 and the news feeds in one pass.</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" onClick={() => run(api.ingestDemo, "Demo corpus")} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film">Load demo corpus</button>
                    <button type="button" onClick={() => run(() => api.buildRealCorpus(false), "Public-record sheet")} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film" title="ICIJ, OpenSanctions, INTERPOL, MHA banned list, NSE/SEBI debarred, GLEIF, NIA wanted, Supreme Court 2024, news">Add public records</button>
                    {user?.role === "admin" && <button type="button" onClick={() => { if (confirm("Replace everything on the sheet with a fresh build from public records?")) run(() => api.buildRealCorpus(true), "Rebuild from public records"); }} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film">Rebuild from public records</button>}
                    {user?.role === "admin" && <button type="button" onClick={() => { if (confirm("Clear every document, entity and alert from the sheet?")) run(async () => { await api.reset(); invalidate(); }, "Reset"); }} className="label border border-pencil px-2 py-1 text-pencil hover:bg-pencil hover:text-film">Clear sheet</button>}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Zone>

        {/* ---------------------------------------------------------------- 3 */}
        <Zone
          n="03"
          id="documents"
          title="Documents"
          lead="The corpus itself. Open one to read what was collected, which entities were drawn out of it, and whether it still matches its seal in the ledger."
          aside={<>
            <select value={docType} onChange={(e) => setDocType(e.target.value)} aria-label="Filter by source type" className="label border border-rule-strong bg-film px-1.5 py-0.5"><option value="">all types</option>{SRC_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
            <input value={docQ} onChange={(e) => setDocQ(e.target.value)} placeholder="search titles" aria-label="Search documents" className="w-40 border border-rule-strong bg-film px-2 py-0.5 text-[length:var(--fs-note)]" />
          </>}
        >
          <div className="grid gap-x-8 gap-y-4 lg:grid-cols-12">
            <div className="lg:col-span-5">
              <p className="note mb-1">{(docs ?? []).length} shown{docType ? ` · ${docType}` : ""}{entityId ? " · filtered to the selected entity" : ""}</p>
              <ol className="max-h-[60vh] divide-y divide-rule overflow-y-auto border-t border-rule">
                {(docs ?? []).map((dd) => (
                  <li key={dd.id}>
                    <button type="button" onClick={() => setDocId(dd.id)} className={cn("block w-full py-2 pr-2 text-left hover:text-pencil", docId === dd.id && "text-pencil")}>
                      <span className="flex items-baseline gap-2"><span className="label shrink-0 text-ink-faint">{dd.source_type}</span><span className="min-w-0 flex-1 text-[length:var(--fs-body)]">{dd.title}</span>{dd.occurred_at && <span className="figure note shrink-0">{format(new Date(dd.occurred_at), "dd MMM yy")}</span>}</span>
                      <span className="note block">{sourceLabel(dd.source_type)} · {dd.records} record{dd.records === 1 ? "" : "s"}</span>
                    </button>
                  </li>
                ))}
                {docs && docs.length === 0 && <li className="note py-3">No document matches this filter.</li>}
              </ol>
            </div>
            <div className="lg:col-span-7">
              {doc ? (
                <article className="note-paper p-4">
                  <h3 className="text-[length:var(--fs-lead)] font-semibold leading-tight">{doc.title}</h3>
                  <p className="note mt-1">{typeof doc.meta?.feed === "string" ? doc.meta.feed : sourceLabel(doc.source_type)} · {doc.source_type} · {doc.records} record{doc.records === 1 ? "" : "s"}{doc.occurred_at ? ` · ${format(new Date(doc.occurred_at), "dd MMM yyyy")}` : ""}</p>
                  {(() => {
                    // The exact page this document was taken from, if one was recorded; otherwise the source's own landing page.
                    const exact = metaHref(doc.meta);
                    const href = exact ?? sourceHref(doc.source_type);
                    return href
                      ? <a href={href} target="_blank" rel="noopener noreferrer" className="label mt-1 inline-flex items-baseline gap-1 text-blue hover:text-pencil">{exact ? "open the original" : "open the source"}<ArrowUpRight className="h-3 w-3 translate-y-0.5" aria-hidden="true" /></a>
                      : <p className="note mt-1 text-ink-faint">This document records no public address to open.</p>;
                  })()}
                  {doc.entities.length > 0 && (
                    <>
                      <h4 className="label mt-4 border-b border-rule pb-1">Entities drawn from this document</h4>
                      <p className="mt-2 flex flex-wrap gap-1.5">{doc.entities.map((en) => <button key={en.id + en.snippet.slice(0, 8)} type="button" onClick={() => select(en.id)} className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[length:var(--fs-note)] hover:border-ink" title={`${en.extractor} · ${Math.round(en.confidence * 100)}% confidence`}><Glyph shape={SHAPE[en.type as EntityType]} size={11} />{en.label}</button>)}</p>
                    </>
                  )}
                  {doc.content && <pre className="mt-4 max-h-72 overflow-y-auto whitespace-pre-wrap border-l border-rule-strong pl-3 font-sans text-[length:var(--fs-body)] leading-relaxed">{doc.content.slice(0, 4000)}</pre>}
                  <VerifyDoc id={doc.id} />
                </article>
              ) : (
                <p className="note">Pick a document to read it.</p>
              )}
            </div>
          </div>
        </Zone>
      </div>
      <SheetFooter lens="Sources" />
    </div>
  );
}

function VerifyDoc({ id }: { id: string }) {
  const [r, setR] = useState<{ status: string; conclusion?: string; reason?: string } | null>(null);
  return <div className="mt-4 flex items-center gap-2 border-t border-rule pt-3 text-[length:var(--fs-note)]"><button type="button" onClick={async () => setR(await api.verifyDocument(id))} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">Verify against ledger</button>{r && <span className={cn("figure", r.status === "match" ? "text-green" : r.status === "mismatch" ? "text-pencil" : "text-ink-soft")}>{r.conclusion ?? r.reason ?? r.status}</span>}</div>;
}
export default function Page() { return <Suspense><Sources /></Suspense>; }
