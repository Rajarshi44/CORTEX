"use client";
/** Overview: the sheet's front matter. What is on it, who matters, what is flagged, how it was proven. */
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSummary, useKeyPlayers, useAlerts, useAiStatus, useLedger, useCommunities } from "@/lib/queries";
import { largestComponents, projectionToChart } from "@/lib/projection";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import { SHAPE, SEVERITY_INK, ALERT_KIND_LABEL, TYPE_LABEL, TYPE_ORDER } from "@/lib/notation";
import type { EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";

const LinkChart = dynamic(() => import("@/components/chart/LinkChart"), { ssr: false });

export default function Overview() {
  const { data: sum } = useSummary();
  const { data: kp } = useKeyPlayers();
  const { data: alerts } = useAlerts({ status: "open", limit: 200 });
  const { data: comms } = useCommunities();
  const { data: proj } = useQuery({ queryKey: ["projection", false], queryFn: () => api.projection({ only_poi: false }), staleTime: 120_000 });
  const { data: ai } = useAiStatus();
  const { data: ledger } = useLedger();
  const select = useSheet((s) => s.select);
  const s = sum?.summary;
  const sheet = sum?.sheet;
  const chart = useMemo(() => { const c = projectionToChart(proj); return largestComponents(c.nodes, c.edges, 140); }, [proj]);
  const bySev = useMemo(() => (alerts ?? []).reduce<Record<string, number>>((m, a) => ((m[a.severity] = (m[a.severity] ?? 0) + 1), m), {}), [alerts]);
  const suspicious = (comms ?? []).filter((c) => c.suspicious);
  const kinds = s ? Object.keys(s.node_types).length : 0;

  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1500px] px-6 pt-8">
        {/* sheet heading: one ruled line, the way a drawing carries its title and its counts */}
        <section className="border-b-2 border-ink pb-5">
          <p className="label">Sheet {sheet?.code ?? "—"} · {sheet?.kind === "real" ? "Public records" : sheet?.kind === "demo" ? "Synthetic demonstration" : sheet?.kind === "mixed" ? "Case corpus + public records" : "—"} · {kinds || "—"} kinds of record</p>
          <h1 className="mt-1 text-[clamp(2rem,3.4vw,3.25rem)] font-semibold leading-[1.02] tracking-tight">{sheet?.title ?? "\u00a0"}</h1>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
            <p className="max-w-[62ch] text-[var(--fs-lead)] text-ink-soft">{sheet?.subtitle ?? "Loading the sheet…"} Every line is backed by a document and a sentence; every score decomposes into reasons. Nothing on this sheet asserts guilt.</p>
            <dl className="figure flex flex-wrap items-baseline gap-x-6 text-[var(--fs-body)]">
              {([["entities", s?.nodes], ["relations", s?.edges], ["persons of interest", s?.persons_of_interest], ["open alerts", alerts?.length]] as const).map(([k, v]) => (
                <div key={k} className="flex items-baseline gap-1.5"><dd className="text-[var(--fs-title)] font-semibold leading-none">{v?.toLocaleString("en-IN") ?? "—"}</dd><dt className="label text-ink-faint">{k}</dt></div>
              ))}
            </dl>
          </div>
        </section>

        <div className="grid grid-cols-12 gap-x-6 gap-y-10 pt-8">
          {/* the actor chart, as the sheet's own drawing */}
          <section className="col-span-12 lg:col-span-7">
            <div className="flex items-baseline justify-between border-b border-ink pb-1"><h2 className="label label-ink">The largest networks on the sheet</h2><Link href="/chart" className="label text-pencil hover:underline">Open the full chart →</Link></div>
            <div className="sheet-ground mt-2 h-[440px] border border-rule-strong">{chart.nodes.length > 0 && <LinkChart nodes={chart.nodes} edges={chart.edges} labelAll onSelect={(id) => select(id)} />}</div>
            <p className="mt-1.5 note">Circles are people, squares organisations; a red centre marks a person of interest. Line weight and darkness carry volume; blue is money. Click any mark to open its notes.</p>
          </section>

          {/* key players as a numbered list */}
          <section className="col-span-12 lg:col-span-5">
            <div className="flex items-baseline justify-between border-b border-ink pb-1"><h2 className="label label-ink">Key players by priority</h2><Link href="/players" className="label text-ink-soft hover:text-pencil">all →</Link></div>
            <ol className="divide-y divide-rule">
              {(kp?.key_players ?? []).slice(0, 8).map((p, i) => (
                <li key={p.id}>
                  <button type="button" onClick={() => select(p.id)} className="grid w-full grid-cols-[2rem_1.25rem_1fr_auto] items-center gap-2 py-2 text-left hover:bg-film-lift">
                    <span className="figure label text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                    <Glyph shape={SHAPE[p.type]} size={14} />
                    <span className="min-w-0"><span className="block truncate font-semibold">{p.label}{p.aliases?.length ? <span className="font-normal text-ink-faint"> @ {p.aliases[0]}</span> : null}</span><span className="block truncate note">{p.role} · {p.reasons?.[0]}</span></span>
                    <span className="figure text-right"><span className="block text-[var(--fs-lead)] font-semibold text-pencil">{p.priority.toFixed(2)}</span><span className="block note">infl {p.influence.toFixed(2)} · susp {p.suspicion.toFixed(2)}</span></span>
                  </button>
                </li>
              ))}
              {!kp && [0, 1, 2, 3, 4].map((i) => <li key={i} className="h-10 animate-pulse bg-film-deep/50" />)}
            </ol>
          </section>

          <section className="col-span-12 md:col-span-6 lg:col-span-4">
            <div className="flex items-baseline justify-between border-b border-ink pb-1"><h2 className="label label-ink">Suspicious patterns</h2><Link href="/alerts" className="label text-ink-soft hover:text-pencil">register →</Link></div>
            <div className="figure flex gap-4 py-2">{(["critical", "high", "medium", "low"] as const).map((sv) => <span key={sv} className="flex items-center gap-1.5 text-[var(--fs-body)]"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: SEVERITY_INK[sv] }} />{bySev[sv] ?? 0} <span className="label text-ink-faint">{sv}</span></span>)}</div>
            <ul className="divide-y divide-rule">
              {(alerts ?? []).slice(0, 6).map((a) => <li key={a.id} className="py-1.5"><Link href={`/alerts?id=${a.id}`} className="block hover:text-pencil"><span className="label" style={{ color: SEVERITY_INK[a.severity] }}>{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span><span className="block truncate text-[var(--fs-body)]">{a.title}</span></Link></li>)}
            </ul>
          </section>

          <section className="col-span-12 md:col-span-6 lg:col-span-4">
            <div className="border-b border-ink pb-1"><h2 className="label label-ink">Communities flagged</h2></div>
            <ul className="divide-y divide-rule">
              {suspicious.slice(0, 5).map((c) => <li key={c.id} className="py-2"><Link href={`/players?community=${c.id}`} className="block hover:text-pencil"><span className="font-semibold">#{c.id} {c.label}</span><span className="block note">{c.size} actors · {c.accused_count} named accused · risk {c.risk.toFixed(2)} · {c.locations.slice(0, 3).join(", ")}</span></Link></li>)}
              {comms && !suspicious.length && <li className="note py-3">No community carries adverse signals.</li>}
            </ul>
          </section>

          <section className="col-span-12 lg:col-span-4">
            <div className="border-b border-ink pb-1"><h2 className="label label-ink">Provenance and integrity</h2></div>
            <dl className="mt-2 space-y-1.5 text-[var(--fs-body)]">
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Evidence ledger</dt><dd className={cn("figure font-semibold", ledger?.verify.valid ? "text-green" : "text-pencil")}>{ledger ? `${ledger.verify.status} · ${ledger.verify.entries} sealed` : "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Compute engine</dt><dd className="figure">{ai?.compute.engine ?? "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Extraction tiers</dt><dd className="figure">rules{ai?.extraction_tiers.neural.available ? " · neural" : ""}{ai?.extraction_tiers.llm.available ? " · llm" : ""}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Semantic search</dt><dd className="figure">{ai?.semantic_search.available ? "on" : "off"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Communities</dt><dd className="figure">{s?.communities ?? "—"} ({s?.suspicious_communities ?? 0} flagged)</dd></div>
            </dl>
            <p className="mt-3 note">{sheet?.kind === "real" ? `Sources on this sheet: ${sheet.sources.join(", ")}.` : "Benchmark: top-10 key players 10/10 genuine on the labelled case; both burner phones attributed by handset IMEI."} Full numbers in the Ledger lens.</p>
            <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Entities by type">
              {s && TYPE_ORDER.filter((t) => s.node_types[t]).map((t: EntityType) => <span key={t} className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[var(--fs-note)]"><Glyph shape={SHAPE[t]} size={11} />{TYPE_LABEL[t]} <span className="figure text-ink-faint">{s.node_types[t]}</span></span>)}
            </div>
          </section>
        </div>
      </div>
      <SheetFooter lens="Overview" />
    </div>
  );
}
