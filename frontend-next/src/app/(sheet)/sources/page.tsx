"use client";
/** Sources & ingestion: what is on the sheet, where it came from, and how to add more. Unavailable sources drop off, they do not grey out. */
import { Suspense, useEffect, useRef, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSources, useSourcesHealth, useIngestStatus, useDocuments, useDocument, useInvalidateSheet } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import { SHAPE } from "@/lib/notation";
import type { EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

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

  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[1500px] grid-cols-12 gap-x-6 gap-y-8 px-6 py-6">
        <section className="col-span-12 flex flex-wrap items-end justify-between gap-4 border-b border-ink pb-3">
          <div><h1 className="text-[var(--fs-sheet)] font-semibold leading-none tracking-tight">Sources and ingestion</h1><p className="mt-1 max-w-[70ch] text-ink-soft">Every document on the sheet is sealed in the evidence ledger at collection. Live connectors respect robots.txt and rate limits; a source that is blocked or down is dropped from this list rather than shown greyed.</p></div>
          <dl className="grid grid-cols-4 gap-x-6 text-right">
            {([["Documents", Object.values(status?.documents ?? {}).reduce((a, b) => a + b, 0)], ["Records", Object.values(status?.records ?? {}).reduce((a, b) => a + b, 0)], ["Entities", status?.entities], ["Events", status?.events]] as const).map(([k, v]) => <div key={k}><dt className="label text-ink-faint">{k}</dt><dd className="figure text-[var(--fs-title)] font-semibold leading-none">{v?.toLocaleString("en-IN") ?? "—"}</dd></div>)}
          </dl>
        </section>

        {job && job.status !== "idle" && (
          <section className="col-span-12 note-paper border border-ink px-3 py-2" aria-live="polite">
            <div className="flex items-center gap-3"><span className={cn("label", job.status === "error" ? "text-pencil" : job.status === "done" ? "text-green" : "label-ink")}>{job.status}</span><span className="text-[var(--fs-body)]">{job.stage}</span>{job.total > 0 && <span className="figure ml-auto note">{job.done} / {job.total}</span>}</div>
            {job.status === "running" && <div className="mt-1 h-1 w-full bg-film-deep"><div className="h-full bg-pencil transition-[width]" style={{ width: job.total ? `${(job.done / job.total) * 100}%` : "30%" }} /></div>}
            {job.error && <p className="mt-1 text-pencil">{job.error}</p>}
          </section>
        )}

        <section className="col-span-12 lg:col-span-7">
          <div className="flex items-center justify-between border-b border-ink pb-1"><h2 className="label label-ink">Live connectors · {live.length} reachable</h2><button type="button" onClick={() => recheck()} className="label text-ink-soft hover:text-pencil">{checking ? "checking…" : "re-check"}</button></div>
          <ul className="divide-y divide-rule">
            {live.map((s) => { const h = byName.get(s.name); return (
              <li key={s.name} className="py-2">
                <div className="flex items-baseline gap-2"><span className="font-semibold">{s.title}</span><span className="label text-ink-faint">{h?.status ?? "…"}</span><span className="figure ml-auto note">{s.licence}</span></div>
                <p className="max-w-[80ch] note">{s.description}</p>
                {canWrite && <div className="mt-1 flex flex-wrap gap-1.5">{(HARVEST_PRESETS[s.name] ?? [{ label: "Harvest", params: {} }]).map((p) => <button key={p.label} type="button" onClick={() => run(() => api.harvest(s.name, p.params), `${s.title}: ${p.label}`)} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">{p.label} →</button>)}</div>}
              </li>); })}
            {!src && [0, 1, 2].map((i) => <li key={i} className="h-12 animate-pulse bg-film-deep/40" />)}
          </ul>
          {dropped.length > 0 && <p className="mt-2 note">Dropped this session (blocked or unreachable from this network): {dropped.map((s) => `${s.title} — ${byName.get(s.name)?.reason || byName.get(s.name)?.status}`).join("; ")}.</p>}

          {canWrite && (
            <div className="mt-8 grid gap-6 md:grid-cols-2">
              <form onSubmit={async (e) => { e.preventDefault(); if (!text.text.trim()) return; try { const r = await api.ingestText(text.source_type, text.title || `${text.source_type} pasted ${format(new Date(), "dd MMM HH:mm")}`, text.text); invalidate(); toast.success(`${r.entities.length} entities extracted`); if (r.entities[0]) select(r.entities[0].id); setText({ ...text, text: "", title: "" }); } catch (err) { toast.error((err as Error).message); } }} className="note-paper p-3">
                <h3 className="label label-ink">Paste a narrative</h3>
                <p className="note">An FIR, intel note or judgment paragraph. Extracted in seconds, sealed, drawn on the sheet.</p>
                <div className="mt-2 flex gap-2"><select value={text.source_type} onChange={(e) => setText({ ...text, source_type: e.target.value })} className="border border-rule-strong bg-film px-1.5 py-1">{["FIR", "INTEL", "REPORT"].map((t) => <option key={t}>{t}</option>)}</select><input value={text.title} onChange={(e) => setText({ ...text, title: e.target.value })} placeholder="Title (optional)" className="flex-1 border border-rule-strong bg-film px-2 py-1" /></div>
                <textarea value={text.text} onChange={(e) => setText({ ...text, text: e.target.value })} rows={6} placeholder="On 20/02/2026 accused Sunil Pawar r/o Dharavi was apprehended…" className="mt-2 w-full border border-rule-strong bg-film p-2 text-[var(--fs-body)]" />
                <button type="submit" className="label mt-2 bg-ink px-3 py-1.5 text-film hover:bg-pencil">Extract and draw</button>
              </form>
              <div className="note-paper p-3">
                <h3 className="label label-ink">Upload a file</h3>
                <p className="note">CSV for CDR, transactions, KYC; JSON for FIRs, surveillance, social, intel. Progress streams live above.</p>
                <div className="mt-2 flex gap-2"><select value={uploadType} onChange={(e) => setUploadType(e.target.value)} className="border border-rule-strong bg-film px-1.5 py-1">{["CDR", "TRANSACTION", "KYC", "FIR", "SURVEILLANCE", "SOCIAL", "INTEL"].map((t) => <option key={t}>{t}</option>)}</select><input type="file" accept=".csv,.json,.txt" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.upload(uploadType, f), `Upload ${f.name}`); }} className="flex-1 text-[var(--fs-note)] file:mr-2 file:border file:border-rule-strong file:bg-film file:px-2 file:py-1 file:text-[var(--fs-note)]" /></div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={() => run(api.ingestDemo, "Demo corpus")} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film">Load demo corpus</button>
                  {canWrite && <button type="button" onClick={() => run(() => api.buildRealCorpus(false), "Public-record sheet")} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film" title="ICIJ, OpenSanctions, INTERPOL, MHA banned list, NSE/SEBI debarred, GLEIF, NIA wanted, Supreme Court 2024, news">Add public records</button>}
                  {user?.role === "admin" && <button type="button" onClick={() => { if (confirm("Replace everything on the sheet with a fresh build from public records?")) run(() => api.buildRealCorpus(true), "Rebuild from public records"); }} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film">Rebuild from public records</button>}
                  {user?.role === "admin" && <button type="button" onClick={() => { if (confirm("Clear every document, entity and alert from the sheet?")) run(async () => { await api.reset(); invalidate(); }, "Reset"); }} className="label border border-pencil px-2 py-1 text-pencil hover:bg-pencil hover:text-film">Clear sheet</button>}
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="col-span-12 lg:col-span-5">
          <div className="flex items-center gap-2 border-b border-ink pb-1"><h2 className="label label-ink">Documents</h2><select value={docType} onChange={(e) => setDocType(e.target.value)} className="label ml-auto border border-rule-strong bg-film px-1 py-0.5"><option value="">all types</option>{SRC_TYPES.map((t) => <option key={t}>{t}</option>)}</select><input value={docQ} onChange={(e) => setDocQ(e.target.value)} placeholder="search" className="w-28 border border-rule-strong bg-film px-1.5 py-0.5 text-[var(--fs-note)]" /></div>
          <ol className="max-h-[40vh] divide-y divide-rule overflow-y-auto">
            {(docs ?? []).map((d) => <li key={d.id}><button type="button" onClick={() => setDocId(d.id)} className={cn("block w-full py-1.5 text-left hover:text-pencil", docId === d.id && "text-pencil")}><span className="label text-ink-faint">{d.source_type}</span> <span className="text-[var(--fs-body)]">{d.title}</span>{d.occurred_at && <span className="figure ml-2 note">{format(new Date(d.occurred_at), "dd MMM yy")}</span>}</button></li>)}
          </ol>
          {doc && (
            <article className="note-paper mt-3 p-3">
              <h3 className="font-semibold">{doc.title}</h3>
              <p className="note">{doc.source_type} · {doc.records} record{doc.records === 1 ? "" : "s"}{doc.occurred_at ? ` · ${format(new Date(doc.occurred_at), "dd MMM yyyy")}` : ""}</p>
              {doc.entities.length > 0 && <p className="mt-2 flex flex-wrap gap-1">{doc.entities.map((e) => <button key={e.id + e.snippet.slice(0, 8)} type="button" onClick={() => select(e.id)} className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[var(--fs-note)] hover:border-ink" title={`${e.extractor} · ${e.confidence}`}><Glyph shape={SHAPE[e.type as EntityType]} size={11} />{e.label}</button>)}</p>}
              {doc.content && <pre className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap border-l border-rule-strong pl-2 font-sans text-[var(--fs-body)] leading-relaxed">{doc.content.slice(0, 4000)}</pre>}
              <VerifyDoc id={doc.id} />
            </article>
          )}
        </section>
      </div>
      <SheetFooter lens="Sources" />
    </div>
  );
}

function VerifyDoc({ id }: { id: string }) {
  const [r, setR] = useState<{ status: string; conclusion?: string; reason?: string } | null>(null);
  return <div className="mt-2 flex items-center gap-2 text-[var(--fs-note)]"><button type="button" onClick={async () => setR(await api.verifyDocument(id))} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">Verify against ledger</button>{r && <span className={cn("figure", r.status === "match" ? "text-green" : r.status === "mismatch" ? "text-pencil" : "text-ink-soft")}>{r.conclusion ?? r.reason ?? r.status}</span>}</div>;
}
export default function Page() { return <Suspense><Sources /></Suspense>; }
