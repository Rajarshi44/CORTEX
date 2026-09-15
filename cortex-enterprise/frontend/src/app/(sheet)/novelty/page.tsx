"use client";
/**
 * Novel Intel Lens — Three enterprise-grade intelligence surfaces:
 *
 * 1. Iceberg Panel   — "How much of this network can we actually see?"
 *                      Capture-recapture statistical estimation of the true network size.
 *
 * 2. Ghost Nodes     — "Who is the handler no one is talking to directly?"
 *                      Pairs with shared criminal environment but zero direct contact.
 *
 * 3. First-Time Risk — "Who is clean on paper but deep in the network?"
 *                      Proximity-based risk scoring for individuals with no prior record.
 */
import { Suspense, useState } from "react";
import { useNovelty } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { SEVERITY_INK } from "@/lib/notation";
import { cn } from "@/lib/utils";

// ─── shared helpers ──────────────────────────────────────────────────────────
function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="relative h-1.5 w-full bg-film-deep rounded-full overflow-hidden">
      <div
        className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.round(value * 100)}%`, background: color }}
      />
    </div>
  );
}

function SectionHeader({ title, count, description }: { title: string; count?: number; description: string }) {
  return (
    <div className="mb-4 border-b border-ink pb-2">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">{title}</h2>
        {count !== undefined && (
          <span className="figure text-ink-faint">{count} finding{count !== 1 ? "s" : ""}</span>
        )}
      </div>
      <p className="mt-1 max-w-[76ch] text-ink-soft">{description}</p>
    </div>
  );
}

// ─── 1. Iceberg Panel ────────────────────────────────────────────────────────
function IcebergPanel({ data }: { data: ReturnType<typeof useNovelty>["data"] }) {
  const iceberg = data?.iceberg;
  if (!iceberg) return null;

  const visibilityPct = iceberg.visibility_pct;
  const darkPct = 100 - visibilityPct;

  return (
    <section id="iceberg-panel">
      <SectionHeader
        title="Network Iceberg"
        description="Statistical estimate of the true criminal network size using capture-recapture analysis across intelligence sources. The dark number represents individuals not yet present in any dataset."
      />
      <div className="grid gap-4 md:grid-cols-3 mb-6">
        {/* Observed */}
        <div className="border border-rule p-4">
          <p className="label text-ink-faint">Observed</p>
          <p className="figure text-[length:var(--fs-lead)] font-bold mt-1">{iceberg.observed.toLocaleString("en-IN")}</p>
          <p className="note mt-1">entities across all sources</p>
        </div>
        {/* Estimated */}
        <div className="border border-pencil p-4 bg-pencil/5">
          <p className="label" style={{ color: SEVERITY_INK.high }}>Estimated Total</p>
          <p className="figure text-[length:var(--fs-lead)] font-bold mt-1" style={{ color: SEVERITY_INK.high }}>
            ~{iceberg.estimated_total.toLocaleString("en-IN")}
          </p>
          <p className="note mt-1">true network size (statistical)</p>
        </div>
        {/* Dark Number */}
        <div className="border border-rule-strong p-4 bg-film-deep">
          <p className="label" style={{ color: SEVERITY_INK.critical }}>Dark Number</p>
          <p className="figure text-[length:var(--fs-lead)] font-bold mt-1" style={{ color: SEVERITY_INK.critical }}>
            {iceberg.dark_number.toLocaleString("en-IN")}
          </p>
          <p className="note mt-1">undetected individuals (~{darkPct.toFixed(1)}%)</p>
        </div>
      </div>

      {/* Visibility gauge */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="label text-ink-soft">Intelligence visibility</span>
          <span className="figure font-medium">{visibilityPct.toFixed(1)}%</span>
        </div>
        <div className="relative h-3 bg-film-deep border border-rule rounded-sm overflow-hidden">
          <div
            className="absolute left-0 top-0 h-full bg-green-700 transition-all duration-700"
            style={{ width: `${visibilityPct}%` }}
          />
          <div
            className="absolute top-0 h-full opacity-40"
            style={{ left: `${visibilityPct}%`, right: 0, background: SEVERITY_INK.critical }}
          />
        </div>
        <div className="flex justify-between mt-0.5">
          <span className="note text-green-700">Visible ({iceberg.observed})</span>
          <span className="note" style={{ color: SEVERITY_INK.critical }}>Dark ({iceberg.dark_number})</span>
        </div>
      </div>

      {/* Interpretation */}
      <p className="text-[length:var(--fs-body)] leading-relaxed max-w-[90ch] text-ink-soft border-l-2 border-pencil pl-3 py-1 bg-film-lift mb-4">
        {iceberg.interpretation}
      </p>

      {/* Source breakdown */}
      {Object.keys(iceberg.source_sets).length > 0 && (
        <div>
          <h3 className="label mb-2">Source coverage</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(iceberg.source_sets).map(([src, cnt]) => (
              <span key={src} className="border border-rule-strong px-2 py-0.5 text-[length:var(--fs-note)] figure">
                {src} <span className="text-ink-faint">— {cnt}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Pairwise estimates */}
      {iceberg.pairwise_estimates.length > 0 && (
        <details className="mt-4 border border-rule">
          <summary className="label cursor-pointer px-3 py-2 hover:bg-film-lift">
            Pairwise source estimates ({iceberg.pairwise_estimates.length} pair{iceberg.pairwise_estimates.length !== 1 ? "s" : ""})
          </summary>
          <div className="divide-y divide-rule">
            {iceberg.pairwise_estimates.map((p, i) => (
              <div key={i} className="grid grid-cols-[auto_1fr_1fr_1fr] gap-4 px-3 py-2 text-[length:var(--fs-note)]">
                <span className="label text-ink-faint">{p.sources.join(" ∩ ")}</span>
                <span>overlap: <span className="figure">{p.overlap}</span></span>
                <span>estimate: <span className="figure">{p.estimate.toLocaleString("en-IN")}</span></span>
                <span className="text-ink-faint">CI: {p.ci_low}–{p.ci_high}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

// ─── 2. Ghost Nodes Panel ────────────────────────────────────────────────────
function GhostNodesPanel({ data }: { data: ReturnType<typeof useNovelty>["data"] }) {
  const ghosts = data?.ghost_nodes ?? [];
  const select = useSheet((s) => s.select);
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section id="ghost-nodes-panel">
      <SectionHeader
        title="Ghost Nodes"
        count={ghosts.length}
        description="Pairs of individuals who share a significant criminal environment (multiple mutual associates) but have zero direct recorded contact. This is the structural signature of professional compartmentalisation — a handler, cutout, or dead-drop contact almost certainly bridges them."
      />
      {ghosts.length === 0 && (
        <p className="note py-6 text-center">No ghost node patterns detected on this sheet.</p>
      )}
      <ol className="divide-y divide-rule">
        {ghosts.map((g, i) => {
          const isOpen = open === i;
          const score = g.confidence_score;
          const color = score >= 0.8 ? SEVERITY_INK.critical : score >= 0.6 ? SEVERITY_INK.high : SEVERITY_INK.medium;
          return (
            <li key={i} className="ripple-in" style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="w-full text-left py-2 px-1 hover:bg-film-lift transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className="figure text-ink-faint shrink-0 mt-0.5">{String(i + 1).padStart(3, "0")}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{g.node_a.label}</span>
                      <span className="text-ink-faint">↔</span>
                      <span className="font-medium">{g.node_b.label}</span>
                      <span className="label ml-auto shrink-0" style={{ color }}>
                        {(score * 100).toFixed(0)}% confidence
                      </span>
                    </div>
                    <div className="mt-1">
                      <ScoreBar value={score} color={color} />
                    </div>
                    <p className="note mt-1 text-ink-faint">
                      {g.shared_neighbors_count} shared associate{g.shared_neighbors_count !== 1 ? "s" : ""}: {g.shared_neighbors.slice(0, 3).join(", ")}
                      {g.shared_neighbors.length > 3 ? ` +${g.shared_neighbors.length - 3} more` : ""}
                    </p>
                  </div>
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-rule bg-film-lift px-4 py-3">
                  <p className="text-[length:var(--fs-body)] leading-relaxed max-w-[80ch] mb-3">{g.interpretation}</p>
                  <div className="grid gap-2 md:grid-cols-2 text-[length:var(--fs-note)]">
                    <div>
                      <dt className="label text-ink-faint">Jaccard similarity</dt>
                      <dd className="figure">{g.jaccard_similarity.toFixed(3)}</dd>
                    </div>
                    <div>
                      <dt className="label text-ink-faint">Community</dt>
                      <dd className="figure">{g.community}</dd>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => select(g.node_a.id)}
                      className="label border border-rule-strong px-2 py-1 hover:border-ink"
                    >
                      Focus {g.node_a.label}
                    </button>
                    <button
                      type="button"
                      onClick={() => select(g.node_b.id)}
                      className="label border border-rule-strong px-2 py-1 hover:border-ink"
                    >
                      Focus {g.node_b.label}
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

// ─── 3. First-Time Offender Risk Panel ───────────────────────────────────────
function FirstTimeRiskPanel({ data }: { data: ReturnType<typeof useNovelty>["data"] }) {
  const ftos = data?.first_time_offenders ?? [];
  const select = useSheet((s) => s.select);
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section id="first-time-risk-panel">
      <SectionHeader
        title="First-Time Offender Risk"
        count={ftos.length}
        description="Individuals with no prior criminal record (no FIRs, no watchlist entries) who are structurally embedded within known criminal networks. Risk is computed from network proximity to established offenders — the strongest predictor of future criminal involvement (Papachristos et al., 2013)."
      />
      {ftos.length === 0 && (
        <p className="note py-6 text-center">No high-proximity clean-record individuals detected.</p>
      )}
      <div className="register-row label mb-1 text-ink-faint border-b border-rule-strong pb-1">
        <span>#</span><span>Name</span><span>Risk</span><span>Proximity</span><span>Community risk</span><span>Contacts</span>
      </div>
      <ol className="divide-y divide-rule">
        {ftos.map((f, i) => {
          const isOpen = open === i;
          const color = f.risk_score >= 0.7 ? SEVERITY_INK.critical : f.risk_score >= 0.45 ? SEVERITY_INK.high : SEVERITY_INK.medium;
          return (
            <li key={f.id} className="ripple-in" style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="w-full text-left hover:bg-film-lift transition-colors"
              >
                <div className="register-row py-2">
                  <span className="figure text-ink-faint">{String(i + 1).padStart(3, "0")}</span>
                  <span className="font-medium truncate">{f.label}</span>
                  <span>
                    <span className="figure font-medium" style={{ color }}>{(f.risk_score * 100).toFixed(0)}%</span>
                    <div className="mt-0.5"><ScoreBar value={f.risk_score} color={color} /></div>
                  </span>
                  <span className="figure text-ink-soft">{(f.proximity_score * 100).toFixed(0)}%</span>
                  <span className="figure text-ink-soft">{(f.community_risk * 100).toFixed(0)}%</span>
                  <span className="figure text-ink-faint">{f.high_risk_contacts}/{f.degree}</span>
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-rule bg-film-lift px-4 py-3">
                  <p className="text-[length:var(--fs-body)] leading-relaxed max-w-[80ch] mb-3">{f.interpretation}</p>
                  {f.reasons.length > 0 && (
                    <ul className="list-disc pl-4 text-[length:var(--fs-note)] mb-3 space-y-0.5">
                      {f.reasons.map((r, j) => <li key={j}>{r}</li>)}
                    </ul>
                  )}
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[length:var(--fs-note)] mb-3">
                    <div><dt className="label text-ink-faint inline">Accused contacts</dt> <dd className="figure inline">{f.accused_contacts}</dd></div>
                    <div><dt className="label text-ink-faint inline">Watchlisted contacts</dt> <dd className="figure inline">{f.watchlisted_contacts}</dd></div>
                    <div><dt className="label text-ink-faint inline">Channel types</dt> <dd className="figure inline">{f.channel_types.join(", ") || "—"}</dd></div>
                    <div><dt className="label text-ink-faint inline">Community</dt> <dd className="figure inline">{f.community}</dd></div>
                  </div>
                  <button
                    type="button"
                    onClick={() => select(f.id)}
                    className="label border border-rule-strong px-2 py-1 hover:border-ink"
                  >
                    Focus on {f.label}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

// ─── 4. Source Discrepancies Panel ──────────────────────────────────────────
function SourceDiscrepanciesPanel({ data }: { data: ReturnType<typeof useNovelty>["data"] }) {
  const discrepancies = data?.discrepancies?.alerts ?? [];
  const select = useSheet((s) => s.select);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section id="source-discrepancies-panel">
      <SectionHeader
        title="Source Discrepancies"
        count={discrepancies.length}
        description="Flags cases where two or more intelligence sources provide conflicting information about the same entity. These discrepancies indicate either identity fraud, record tampering, SIM-swap operations, or ghost identity use."
      />
      {discrepancies.length === 0 && (
        <p className="note py-6 text-center">No source discrepancies detected across the current dataset.</p>
      )}
      <ol className="divide-y divide-rule">
        {discrepancies.map((d, i) => {
          const isOpen = open === d.id;
          const color = d.severity === "critical" ? SEVERITY_INK.critical : d.severity === "high" ? SEVERITY_INK.high : SEVERITY_INK.medium;
          return (
            <li key={d.id} className="ripple-in" style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : d.id)}
                aria-expanded={isOpen}
                className="w-full text-left py-2 px-1 hover:bg-film-lift transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className="figure text-ink-faint shrink-0 mt-0.5">{String(i + 1).padStart(3, "0")}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-[length:var(--fs-body)]">{d.title}</span>
                      <span className="label ml-auto shrink-0 border border-rule-strong px-1.5 py-0.5" style={{ color }}>
                        {d.severity.toUpperCase()}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-rule bg-film-lift px-4 py-3">
                  <p className="text-[length:var(--fs-body)] leading-relaxed max-w-[80ch] mb-3">{d.description}</p>
                  
                  <div className="bg-film-deep border border-rule p-3 mb-3">
                    <h4 className="label text-ink-soft mb-2">Evidence</h4>
                    <dl className="text-[length:var(--fs-note)] grid gap-y-1">
                      {Object.entries(d.evidence).map(([k, v]) => (
                        <div key={k} className="grid grid-cols-[10rem_1fr] gap-2">
                          <dt className="text-ink-faint">{k.replace(/_/g, " ")}</dt>
                          <dd className="font-mono text-ink-soft break-words">
                            {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {d.entity_ids.map((eid) => (
                      <button
                        key={eid}
                        type="button"
                        onClick={() => select(eid)}
                        className="label border border-rule-strong px-2 py-1 hover:border-ink"
                      >
                        Focus {eid.substring(0, 8)}...
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

// ─── Summary Banner ───────────────────────────────────────────────────────────
function NoveltyBanner({ data }: { data: ReturnType<typeof useNovelty>["data"] }) {
  const s = data?.summary;
  if (!s) return null;
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {[
        { label: "Observed", val: data?.iceberg.observed ?? 0, ink: "text-ink" },
        { label: "Estimated Total", val: data?.iceberg.estimated_total ?? 0, ink: SEVERITY_INK.high },
        { label: "Dark Number", val: s.estimated_dark_network_size, ink: SEVERITY_INK.critical },
        { label: "Ghost Nodes", val: s.ghost_nodes_detected, ink: SEVERITY_INK.high },
        { label: "Clean-Record Risk", val: s.first_time_offenders_flagged, ink: SEVERITY_INK.medium },
        { label: "Discrepancies", val: s.discrepancies_detected, ink: SEVERITY_INK.critical },
      ].map(({ label, val, ink }) => (
        <div key={label} className="border border-rule p-3">
          <p className="label text-ink-faint text-[length:var(--fs-note)]">{label}</p>
          <p
            className="figure font-bold text-[length:var(--fs-lead)] leading-tight mt-0.5"
            style={ink.startsWith("#") ? { color: ink } : undefined}
          >
            {val.toLocaleString("en-IN")}
          </p>
        </div>
      ))}
    </div>
  );
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────
type Tab = "iceberg" | "ghost" | "fto" | "discrep";
const TABS: { id: Tab; label: string }[] = [
  { id: "iceberg", label: "Network Iceberg" },
  { id: "ghost", label: "Ghost Nodes" },
  { id: "fto", label: "First-Time Risk" },
  { id: "discrep", label: "Source Discrepancies" },
];

// ─── Main Page ───────────────────────────────────────────────────────────────
function NoveltyPage() {
  const { data, isLoading, isError } = useNovelty();
  const [tab, setTab] = useState<Tab>("iceberg");

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-[1500px] px-6 py-6">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink pb-2 mb-4">
          <div>
            <h1 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Novel Intelligence</h1>
            <p className="mt-1 max-w-[76ch] text-ink-soft">
              Three enterprise-grade analytical engines not found in any other criminal network tool: statistical estimation of the hidden network,
              detection of professional anti-forensic compartmentalisation, and proximity-based risk scoring for first-time offenders.
            </p>
          </div>
        </div>

        {isLoading && (
          <div className="space-y-3 mt-4">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 animate-pulse bg-film-deep/60 border border-rule" style={{ animationDelay: `${i * 80}ms` }} />
            ))}
          </div>
        )}

        {isError && (
          <div className="mt-6 border border-pencil bg-pencil/5 p-4">
            <p className="font-medium" style={{ color: SEVERITY_INK.critical }}>Unable to load novel intelligence.</p>
            <p className="note mt-1">Ensure the backend is running and the corpus has been loaded. The novel endpoints require at least one ingested document.</p>
          </div>
        )}

        {data && (
          <>
            {/* Summary KPI banner */}
            <NoveltyBanner data={data} />

            {/* Tab bar */}
            <nav className="flex gap-0 border-b border-rule-strong mb-6" aria-label="Novel Intel tabs">
              {TABS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  aria-current={tab === id ? "page" : undefined}
                  className={cn(
                    "label shrink-0 px-4 py-2 transition-colors hover:text-ink",
                    tab === id
                      ? "label-ink shadow-[inset_0_-2px_0_var(--amber-deep)] text-ink"
                      : "text-ink-soft",
                  )}
                >
                  {label}
                  {id === "iceberg" && data.iceberg.dark_number > 0 && (
                    <span className="ml-2 figure" style={{ color: SEVERITY_INK.critical }}>
                      +{data.iceberg.dark_number}
                    </span>
                  )}
                  {id === "ghost" && data.ghost_nodes.length > 0 && (
                    <span className="ml-2 figure text-ink-faint">{data.ghost_nodes.length}</span>
                  )}
                  {id === "fto" && data.first_time_offenders.length > 0 && (
                    <span className="ml-2 figure text-ink-faint">{data.first_time_offenders.length}</span>
                  )}
                  {id === "discrep" && data.summary.discrepancies_detected > 0 && (
                    <span className="ml-2 figure text-ink-faint">{data.summary.discrepancies_detected}</span>
                  )}
                </button>
              ))}
            </nav>

            {/* Panel content */}
            {tab === "iceberg" && <IcebergPanel data={data} />}
            {tab === "ghost" && <GhostNodesPanel data={data} />}
            {tab === "fto" && <FirstTimeRiskPanel data={data} />}
            {tab === "discrep" && <SourceDiscrepanciesPanel data={data} />}
          </>
        )}
      </div>
      <SheetFooter lens="Novel Intel" />
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <NoveltyPage />
    </Suspense>
  );
}
