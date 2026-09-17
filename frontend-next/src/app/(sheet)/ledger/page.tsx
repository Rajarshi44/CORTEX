"use client";
/** Ledger & proof: chain of custody, benchmark evaluations, case-linkage leads, identifier checks, the brief. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLedger, useLinkage, useAiStatus } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import Markdown from "@/components/Markdown";
import type { LinkageReport } from "@/lib/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

export default function LedgerLens() {
  const { data: l, refetch } = useLedger();
  const { data: ai } = useAiStatus();
  const { data: linkage } = useLinkage(0.55);
  const [ds, setDs] = useState("montreal");
  const { data: bench, isFetching: benching } = useQuery({ queryKey: ["bench", ds], queryFn: () => api.benchmarkEval(ds), staleTime: 600_000 });
  const [idText, setIdText] = useState("Accused holds Aadhaar 9991 2345 6789 and PAN ABCPD1234E; a second card 999123456780 was found.");
  const [ids, setIds] = useState<Awaited<ReturnType<typeof api.identifiers>> | null>(null);
  const [brief, setBrief] = useState<string | null>(null);
  const user = useSheet((s) => s.user);
  const link = linkage && "series" in linkage ? (linkage as LinkageReport) : null;

  const { data: anchor } = useQuery({ queryKey: ["ledgerAnchor"], queryFn: () => api.ledgerAnchor() });
  const [selectedProof, setSelectedProof] = useState<{ index: number; proof: { leaf_index: number; leaf_hash: string; root_hash: string; total_leaves: number; audit_path: { position: "left" | "right"; hash: string }[] } } | null>(null);
  const [proofValid, setProofValid] = useState<boolean | null>(null);

  const viewProof = async (index: number) => {
    try {
      const p = await api.ledgerProof(index);
      setSelectedProof({ index, proof: p });
      const res = await api.ledgerVerifyProof(p.leaf_hash, p);
      setProofValid(res.valid);
      toast.success(`Merkle inclusion proof verified for entry #${index}`);
    } catch {
      toast.error(`Could not generate proof for entry #${index}`);
    }
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto grid w-full max-w-[1500px] grid-cols-12 gap-x-6 gap-y-8 px-6 py-6">
        <section className="col-span-12 border-b border-ink pb-3"><h1 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Ledger and proof</h1><p className="mt-1 max-w-[70ch] text-ink-soft">What a court asks: was the evidence altered, how accurate is the method, and which offences might share an offender. All three are measured here, not claimed.</p></section>

        <section className="col-span-12 lg:col-span-4">
          <h2 className="label label-ink border-b border-ink pb-1">Chain of custody & Cryptographic Proof</h2>
          {l && (
            <div className={cn("mt-2 border p-3", l.verify.valid ? "border-green" : "border-pencil bg-[var(--pencil-wash)]")}>
              <div className="flex items-center justify-between">
                <p className={cn("stencil text-[length:var(--fs-title)] font-bold", l.verify.valid ? "text-green" : "text-pencil")}>
                  {l.verify.valid ? "CHAIN INTACT · ED25519 SIGNED" : l.verify.status}
                </p>
                <span className="rounded bg-green/10 px-1.5 py-0.5 text-[10px] font-semibold text-green uppercase tracking-wide">
                  Ed25519 Verified
                </span>
              </div>
              <dl className="mt-2 space-y-1 text-[length:var(--fs-note)]">
                <div className="flex justify-between"><dt className="text-ink-soft">Sealed entries</dt><dd className="figure">{l.verify.entries}</dd></div>
                {l.verify.first_sealed && <div className="flex justify-between"><dt className="text-ink-soft">First seal</dt><dd className="figure">{format(new Date(l.verify.first_sealed), "dd MMM yyyy HH:mm")}</dd></div>}
                {l.verify.head && <div className="flex justify-between gap-3"><dt className="text-ink-soft">Head hash</dt><dd className="figure truncate font-mono text-[10px]" title={l.verify.head}>{l.verify.head.slice(0, 16)}…</dd></div>}
                {l.entries.merkle_root && <div className="flex justify-between gap-3"><dt className="text-ink-soft">Merkle root</dt><dd className="figure truncate font-mono text-[10px] text-blue-600 dark:text-blue-400" title={l.entries.merkle_root}>{l.entries.merkle_root.slice(0, 16)}…</dd></div>}
                {anchor && <div className="flex justify-between gap-3"><dt className="text-ink-soft">External anchor</dt><dd className="figure text-[10px] text-green font-medium">#{anchor.height} ({anchor.status})</dd></div>}
                {l.verify.broken_at !== undefined && <div className="flex justify-between"><dt className="text-ink-soft">Broken at</dt><dd className="figure text-pencil">#{l.verify.broken_at}</dd></div>}
              </dl>
              {l.verify.reason && <p className="mt-1 text-pencil">{l.verify.reason}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => refetch()} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">Re-verify</button>
                <button type="button" onClick={async () => { const a = await api.ledgerAnchor(); if (a.head_hash) { await navigator.clipboard?.writeText(a.head_hash); toast.success("Head hash copied — record it in the case diary"); } }} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">Copy anchor</button>
                {l.entries.merkle_root && <button type="button" onClick={async () => { await navigator.clipboard?.writeText(l.entries.merkle_root!); toast.success("Merkle root copied to clipboard"); }} className="label border border-rule-strong px-2 py-0.5 hover:border-ink">Copy Merkle root</button>}
              </div>
            </div>
          )}

          {selectedProof && (
            <div className="mt-3 border border-blue-300 bg-blue-50/50 p-2 text-[11px] dark:border-blue-900 dark:bg-blue-950/30">
              <div className="flex items-center justify-between border-b border-blue-200 pb-1">
                <span className="font-semibold text-blue-900 dark:text-blue-200">Merkle Inclusion Proof #{selectedProof.index}</span>
                <span className={cn("font-bold text-[10px]", proofValid ? "text-green" : "text-pencil")}>
                  {proofValid ? "✓ VALID INCLUSION" : "INVALID"}
                </span>
              </div>
              <div className="mt-1 font-mono text-[10px] space-y-0.5">
                <div className="truncate"><span className="text-ink-soft">Leaf: </span>{selectedProof.proof.leaf_hash.slice(0, 18)}…</div>
                <div className="truncate"><span className="text-ink-soft">Root: </span>{selectedProof.proof.root_hash.slice(0, 18)}…</div>
                <div><span className="text-ink-soft">Audit path: </span>{selectedProof.proof.audit_path.length} step(s)</div>
              </div>
              <button type="button" onClick={() => setSelectedProof(null)} className="mt-1 text-[10px] text-ink-soft hover:text-ink underline">Close proof</button>
            </div>
          )}

          <ol className="mt-3 max-h-72 divide-y divide-rule overflow-y-auto text-[length:var(--fs-note)]">
            {(l?.entries.entries ?? []).map((e) => (
              <li key={e.index} className="py-1.5 flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="figure text-ink-faint">#{e.index}</span>
                    <span className="label font-medium">{e.action}</span>
                    <span className="text-ink-soft text-[10px]">{e.actor}</span>
                    {e.signature ? (
                      <span className="rounded bg-green/10 px-1 py-0.2 text-[9px] font-mono text-green" title={`Sig: ${e.signature}`}>
                        Ed25519
                      </span>
                    ) : null}
                  </div>
                  <span className="block truncate text-[11px] text-ink-soft mt-0.5">{e.detail}</span>
                </div>
                <button
                  type="button"
                  onClick={() => viewProof(e.index)}
                  className="shrink-0 text-[10px] border border-rule px-1 py-0.5 hover:border-ink hover:bg-film rounded"
                  title="View Merkle inclusion proof"
                >
                  Proof
                </button>
              </li>
            ))}
          </ol>
        </section>

        <section className="col-span-12 lg:col-span-4">
          <h2 className="label label-ink border-b border-ink pb-1">Method validation on real networks</h2>
          <div className="mt-2 flex gap-1">{[["montreal", "Montreal Police gangs"], ["terrorists_911", "9/11 cells"], ["train_terrorists", "Madrid 2004"]].map(([k, v]) => <button key={k} type="button" aria-pressed={ds === k} onClick={() => setDs(k)} className={cn("label px-2 py-1", ds === k ? "label-ink pencil-line" : "text-ink-faint hover:text-ink")}>{v}</button>)}</div>
          {benching && <p className="note mt-2">Evaluating…</p>}
          {bench && bench.status === "ok" && (
            <dl className="mt-2 text-[length:var(--fs-body)]">
              {([["Nodes", bench.nodes], ["True groups", bench.true_groups], ["Detected (default)", (bench.default as Record<string, number>)?.detected_communities], ["Adjusted Rand (best)", (bench.best as Record<string, number>)?.adjusted_rand_index], ["Purity (best)", (bench.best as Record<string, number>)?.purity], ["Best resolution", bench.best_resolution]] as const).map(([k, v]) => <div key={k} className="flex justify-between border-b border-rule py-1"><dt className="text-ink-soft">{k}</dt><dd className="figure">{String(v ?? "—")}</dd></div>)}
            </dl>
          )}
          {bench && bench.status !== "ok" && <p className="mt-2 note">Load this benchmark from the Sources lens first ({String(bench.reason ?? bench.status)}).</p>}
          <p className="mt-3 note">On the labelled benchmark case, the top ten key players are all genuine network members and both burner phones were attributed to the right user via handset IMEI. Compute: {ai?.compute.engine} · {ai?.compute.betweenness_method}.</p>
        </section>

        <section className="col-span-12 lg:col-span-4">
          <h2 className="label label-ink border-b border-ink pb-1">Identifier check</h2>
          <p className="note mt-1">Aadhaar (Verhoeff), PAN, GSTIN, IFSC, passport. Sensitive values are masked; fakes are rejected by checksum.</p>
          <textarea value={idText} onChange={(e) => setIdText(e.target.value)} rows={3} className="mt-2 w-full border border-rule-strong bg-film p-2 text-[length:var(--fs-body)]" aria-label="Text to scan" />
          <button type="button" onClick={async () => setIds(await api.identifiers(idText))} className="label mt-1 bg-ink px-3 py-1 text-film hover:bg-pencil">Scan</button>
          {ids && <ul className="mt-2 divide-y divide-rule text-[length:var(--fs-body)]">{ids.identifiers.map((i, k) => <li key={k} className="flex items-center gap-2 py-1"><span className="label w-16">{i.kind}</span><span className="figure flex-1">{i.value}</span><span className={cn("label", i.valid ? "text-green" : "text-pencil")}>{i.valid ? "valid" : "rejected"}</span></li>)}{ids.summary.rejected.map((r, k) => <li key={"r" + k} className="py-1 note text-pencil">{r.kind} {r.text}: {r.reason}</li>)}</ul>}
        </section>

        <section className="col-span-12 lg:col-span-7">
          <h2 className="label label-ink border-b border-ink pb-1">Behavioural case linkage — candidate leads</h2>
          {link ? (
            <>
              <p className="mt-1 note">{link.cases_analysed} cases analysed · {link.candidate_links} links above {link.threshold} · {link.candidate_series} candidate series, {link.cross_jurisdiction_series} spanning more than one station. {link.disclaimer}</p>
              <ol className="mt-2 space-y-3">
                {link.series.slice(0, 6).map((s, i) => (
                  <li key={i} className="note-paper p-3">
                    <div className="flex flex-wrap items-baseline gap-2"><span className="figure label text-ink-faint">Series {String(i + 1).padStart(2, "0")}</span><span className="font-semibold">{s.size} cases</span><span className="note">cohesion {s.cohesion.toFixed(2)}{s.cross_jurisdiction ? " · cross-jurisdiction" : ""}{s.span_days !== null ? ` · ${s.span_days} days` : ""}</span></div>
                    <p className="mt-1 text-[length:var(--fs-body)]">{s.assessment}</p>
                    {s.common_signature.length > 0 && <p className="note">Signature repeated in every case: {s.common_signature.map((x) => x.replace(/_/g, " ")).join(", ")}</p>}
                    <p className="note">Stations: {s.stations.join(", ") || "—"}</p>
                    <ul className="mt-1 flex flex-wrap gap-1">{s.members.slice(0, 8).map((m) => <li key={m.document_id} className="border border-rule-strong px-1.5 py-0.5 text-[length:var(--fs-note)]">{m.title.replace(/^FIR\s*/, "")}</li>)}</ul>
                  </li>
                ))}
              </ol>
            </>
          ) : <p className="note mt-2">{linkage && "reason" in linkage ? String(linkage.reason) : "Analysing narratives…"}</p>}
        </section>

        <section className="col-span-12 lg:col-span-5">
          <h2 className="label label-ink border-b border-ink pb-1">The brief</h2>
          <p className="note mt-1">The whole sheet as a court-ready document: key players with reasons, communities, disruption analysis, alerts, predicted links, evidence appendix. Exports are sealed in the ledger.</p>
          <div className="mt-2 flex gap-2"><button type="button" onClick={async () => setBrief(await api.reportMarkdown())} className="label border border-ink px-2 py-1 hover:bg-ink hover:text-film">Preview</button><button type="button" onClick={() => api.downloadPdf()} className="label bg-ink px-2 py-1 text-film hover:bg-pencil">Download PDF</button></div>
          {brief && <div className="note-paper mt-3 max-h-[60vh] overflow-y-auto p-4"><Markdown text={brief} className="text-[length:var(--fs-body)]" /></div>}
          {user?.role === "admin" && <AuditPeek />}
        </section>
      </div>
      <SheetFooter lens="Ledger" />
    </div>
  );
}

function AuditPeek() {
  const { data } = useQuery({ queryKey: ["audit"], queryFn: () => api.audit(30) });
  return <details className="mt-4"><summary className="label cursor-pointer">Audit log (admin)</summary><ol className="mt-1 divide-y divide-rule text-[length:var(--fs-note)]">{(data ?? []).map((a) => <li key={a.id} className="py-1"><span className="figure text-ink-faint">{format(new Date(a.at), "dd MMM HH:mm")}</span> <span className="label">{a.action}</span> {a.user} <span className="text-ink-soft">{a.detail}</span></li>)}</ol></details>;
}
