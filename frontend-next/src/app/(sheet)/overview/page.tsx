"use client";
/**
 * Overview — the concourse.
 *
 * The first screen is the map at the size of the room, with the service index down the left and
 * the detail of whatever you are pointing at down the right. Everything an officer does here
 * starts with looking at the network, so the network gets the viewport; the sheet's own title,
 * counts and specification are read second and live below the fold.
 */
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSummary, useKeyPlayers, useAlerts, useAiStatus, useLedger, useCommunities } from "@/lib/queries";
import { largestComponents, projectionToChart } from "@/lib/projection";
import { useSheet } from "@/lib/store";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import { SHAPE, SEVERITY_INK, ALERT_KIND_LABEL, TYPE_LABEL, TYPE_ORDER, routeInk, maskLabel } from "@/lib/notation";
import type { EntityType, KeyPlayer, NodeView } from "@/lib/types";
import { cn } from "@/lib/utils";

const LinkChart = dynamic(() => import("@/components/chart/LinkChart"), { ssr: false });

/**
 * The index's status column. It reports what the record says and nothing more: an actor with an
 * adverse entry is ON RECORD, one without is NO RECORD. Neither word is a finding about the person.
 */
/** The role, minus any parenthetical that restates the status column beside it. Not every actor is given one. */
function roleOnly(role: string | null) {
  if (!role) return "";
  return role.replace(/\s*\([^)]*\)\s*$/, "").trim() || role;
}

function recordStatus(suspicion: number) {
  return suspicion >= 0.2
    ? { word: "On record", tone: "text-amber-deep", title: "An adverse entry exists in the sources for this actor." }
    : { word: "No record", tone: "text-ink-faint", title: "No adverse entry in the sources. Listed for position in the network only." };
}

/**
 * An actor as the right rail receives it. The pointer picks one off the map, where it arrives as a
 * graph node, or off the index, where it arrives as a ranked row. The two agree on everything the
 * rail draws except the rank reasons, which only the ranking computes.
 */
type Pointed = NodeView | KeyPlayer;

export default function Overview() {
  const { data: sum } = useSummary();
  const { data: kp } = useKeyPlayers();
  const { data: alerts } = useAlerts({ status: "open", limit: 200 });
  const { data: comms } = useCommunities();
  const { data: proj } = useQuery({ queryKey: ["projection", false], queryFn: () => api.projection({ only_poi: false }), staleTime: 120_000 });
  const { data: ai } = useAiStatus();
  const { data: ledger } = useLedger();
  const select = useSheet((s) => s.select);
  const selected = useSheet((s) => s.selected);
  const [pointing, setPointing] = useState<Pointed | null>(null);
  const s = sum?.summary;
  const sheet = sum?.sheet;
  const chart = useMemo(() => { const c = projectionToChart(proj); return largestComponents(c.nodes, c.edges, 140); }, [proj]);
  const bySev = useMemo(() => (alerts ?? []).reduce<Record<string, number>>((m, a) => ((m[a.severity] = (m[a.severity] ?? 0) + 1), m), {}), [alerts]);
  const suspicious = (comms ?? []).filter((c) => c.suspicious);
  // a "community" of one is an isolated record, not a group; only real groups are counted here
  const groups = (comms ?? []).filter((c) => c.size > 1).length;
  const kinds = s ? Object.keys(s.node_types).length : 0;
  const players = kp?.key_players ?? [];
  // the right rail follows the pointer over the map, and holds the last thing opened when it leaves
  const shown = pointing ?? players.find((p) => p.id === selected) ?? null;
  const shownComm = shown ? (comms ?? []).find((c) => c.id === shown.community) : undefined;
  // only the ranking decomposes a score into reasons, so a node taken off the map carries none
  const shownReasons = shown && "reasons" in shown ? shown.reasons : [];

  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto">
      {/* ------------------------------------------------------------- the concourse */}
      <section aria-label="Network map" className="flex h-full min-h-[26rem] items-stretch sm:min-h-[34rem]">
        {/* the service index: the timetable you scan before you look up at the map */}
        <div className="hidden w-[19rem] shrink-0 flex-col border-r border-rule-strong bg-film-lift md:flex xl:w-[21rem]">
          <div className="flex items-baseline justify-between border-b border-ink px-3 py-2">
            <h2 className="label label-ink">Service index</h2>
            <Link href="/players" className="label text-ink-soft hover:text-ink">All players</Link>
          </div>
          <p className="border-b border-rule px-3 py-1.5 note">By priority: 55% position in the network, 45% record against the person.</p>
          <ol className="min-h-0 flex-1 overflow-y-auto">
            {players.slice(0, 40).map((p, i) => {
              const st = recordStatus(p.suspicion);
              const isOn = p.id === selected || p.id === pointing?.id;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => select(p.id)}
                    onMouseEnter={() => setPointing(p)}
                    onMouseLeave={() => setPointing(null)}
                    className={cn("track grid w-full grid-cols-[2.75rem_minmax(0,1fr)_2.75rem] items-center gap-2 px-3 py-1.5 text-left", isOn && "bg-amber-wash")}
                  >
                    {/* the route badge: which community's line this actor rides */}
                    <span className="figure flex items-center gap-1.5 text-[length:var(--fs-note)] text-ink-soft">
                      <span aria-hidden="true" className="block h-4 w-1" style={{ background: routeInk(p.community) }} />
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate font-semibold leading-tight">{maskLabel(p.label, p.role)}</span>
                      <span className="flex min-w-0 items-baseline gap-1.5">
                        <span className={cn("label shrink-0 text-[0.625rem]", st.tone)} title={st.title}>{st.word}</span>
                        <span className="min-w-0 truncate note">{roleOnly(p.role)}</span>
                      </span>
                    </span>
                    <span className="figure text-right text-[length:var(--fs-lead)] font-semibold leading-none text-ink">{p.priority.toFixed(2)}</span>
                  </button>
                </li>
              );
            })}
            {!kp && [0, 1, 2, 3, 4, 5, 6, 7].map((i) => <li key={i} className="mx-3 my-1.5 h-8 animate-pulse bg-film-deep" />)}
          </ol>
        </div>

        {/* the map: full bleed, nothing over it but its own plate and key */}
        <div className="sheet-ground relative min-w-0 flex-1">
          {chart.nodes.length > 0 && (
            <LinkChart
              nodes={chart.nodes}
              edges={chart.edges}
              onSelect={(id) => select(id)}
              onHover={(hit) => setPointing(hit?.node ?? null)}
            />
          )}
          {/* the plate, the way a printed map carries its title in a corner */}
          <div className="pointer-events-none absolute left-3 right-3 top-3 max-w-[26rem] border border-ink bg-film-lift/95 px-3 py-2 sm:left-4 sm:top-4">
            <h1 className="sign text-[length:clamp(1.15rem,1.6vw,1.6rem)]">{sheet?.title ?? " "}</h1>
            <p className="figure mt-1 flex flex-wrap gap-x-3 note">
              <span>{s?.nodes?.toLocaleString("en-IN") ?? "—"} entities</span>
              <span>{s?.edges?.toLocaleString("en-IN") ?? "—"} relations</span>
              <span>{groups || "—"} groups</span>
              <span>{alerts?.length ?? 0} open alerts</span>
            </p>
          </div>
          {/* the key, along the bottom edge where a map's key belongs */}
          <div className="pointer-events-none absolute bottom-0 left-0 right-0 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule-strong bg-film/90 px-4 py-1.5 note">
            <span className="flex items-center gap-1.5"><Glyph shape="circle" size={11} /> person</span>
            <span className="flex items-center gap-1.5"><Glyph shape="square" size={11} /> organisation</span>
            <span className="hidden items-center gap-1.5 sm:flex"><span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border border-ink-soft ring-1 ring-ink-soft ring-offset-1 ring-offset-film" /> interchange: rides two routes</span>
            <span className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-pencil" /> adverse record</span>
            <span className="hidden items-center gap-1.5 sm:flex"><span aria-hidden="true" className="inline-block h-0.5 w-5 bg-blue" /> money</span>
            <span className="ml-auto hidden lg:inline">Line colour is the community. Click a station to open its record.</span>
          </div>
        </div>

        {/* the detail: whatever the pointer is on, otherwise the state of the sheet */}
        <aside aria-label="Detail" className="hidden w-[18rem] shrink-0 flex-col overflow-y-auto border-l border-rule-strong bg-film-lift xl:flex">
          {shown ? (
            <div className="px-3 py-2">
              <span aria-hidden="true" className="mb-2 block h-1 w-10" style={{ background: routeInk(shown.community) }} />
              <h2 className="sign text-[length:var(--fs-title)] leading-tight">{maskLabel(shown.label, "role" in shown ? shown.role : undefined, "party_role" in shown ? (shown as any).party_role : undefined)}</h2>
              <p className="mt-0.5 note">{TYPE_LABEL[shown.type]}{shownComm ? ` · ${shownComm.label}` : ""}</p>
              <dl className="mt-3 space-y-1">
                {([["Priority", shown.priority], ["Position", shown.influence], ["Record", shown.suspicion]] as const).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex items-baseline justify-between"><dt className="label text-ink-faint">{k}</dt><dd className="figure font-semibold">{typeof v === "number" ? v.toFixed(2) : "—"}</dd></div>
                    <span aria-hidden="true" className="mt-0.5 block h-1 w-full bg-film-deep"><span className="block h-full bg-ink" style={{ width: `${Math.round(Math.min(1, Number(v) || 0) * 100)}%` }} /></span>
                  </div>
                ))}
              </dl>
              {shownReasons.length ? (
                <>
                  <h3 className="label label-ink mt-3 border-b border-rule pb-1">Why it ranks here</h3>
                  <ul className="mt-1 space-y-1">{shownReasons.slice(0, 4).map((r, i) => <li key={i} className="note">{r}</li>)}</ul>
                </>
              ) : null}
              <button type="button" onClick={() => select(shown.id)} className="label mt-3 w-full border border-ink px-2 py-1.5 hover:bg-ink hover:text-film">Open full record</button>
              <p className="mt-2 note">Rank explains position and record. It is not a finding against this person.</p>
            </div>
          ) : (
            <div className="px-3 py-2">
              <h2 className="label label-ink border-b border-ink pb-1">On this sheet now</h2>
              <div className="figure mt-2 grid grid-cols-2 gap-1.5">
                {(["critical", "high", "medium", "low"] as const).map((sv) => (
                  <span key={sv} className="flex items-baseline gap-1.5 border border-rule px-2 py-1">
                    <span aria-hidden="true" className="h-2 w-2 shrink-0 self-center" style={{ background: SEVERITY_INK[sv] }} />
                    <span className="text-[length:var(--fs-lead)] font-semibold leading-none">{bySev[sv] ?? 0}</span>
                    <span className="label text-[0.625rem] text-ink-faint">{sv}</span>
                  </span>
                ))}
              </div>
              <h3 className="label label-ink mt-4 border-b border-rule pb-1">Communities flagged</h3>
              <ul className="divide-y divide-rule">
                {suspicious.slice(0, 6).map((c) => (
                  <li key={c.id}>
                    <Link href={`/players?community=${c.id}`} className="flex items-start gap-2 py-1.5 hover:bg-film-deep">
                      <span aria-hidden="true" className="mt-1 block h-3 w-1 shrink-0" style={{ background: routeInk(c.id) }} />
                      <span className="min-w-0"><span className="block truncate font-semibold">{c.label}</span><span className="block note">{c.size} actors · risk {c.risk.toFixed(2)}</span></span>
                    </Link>
                  </li>
                ))}
                {comms && !suspicious.length && <li className="note py-2">No community carries adverse signals.</li>}
              </ul>
              <h3 className="label label-ink mt-4 border-b border-rule pb-1">Open register</h3>
              <ul className="divide-y divide-rule">
                {(alerts ?? []).slice(0, 7).map((a) => (
                  <li key={a.id}>
                    <Link href={`/alerts?id=${a.id}`} className="flex items-start gap-2 py-1.5 hover:bg-film-deep">
                      <span aria-hidden="true" className="mt-1.5 block h-2 w-2 shrink-0" style={{ background: SEVERITY_INK[a.severity] }} />
                      <span className="min-w-0"><span className="block leading-tight">{a.title}</span><span className="block note">{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span></span>
                    </Link>
                  </li>
                ))}
                {alerts && !alerts.length && <li className="note py-2">Nothing open on this sheet.</li>}
              </ul>
              <p className="mt-4 note">Point at the map or the index to read an actor here.</p>
            </div>
          )}
        </aside>
      </section>

      {/* ------------------------------------------------------- the sheet's front matter */}
      <div className="mx-auto max-w-[1500px] px-6">
        <section className="border-t-2 border-ink pt-6">
          <p className="max-w-[68ch] text-[length:var(--fs-lead)] text-ink-soft">
            {sheet?.subtitle ?? "Loading the sheet…"} Every line is backed by a document and a sentence; every score decomposes into reasons. Nothing on this sheet asserts guilt.
          </p>
          <dl className="mt-4 flex flex-wrap items-stretch border border-rule-strong bg-film-lift">
            {([
              ["Sheet", sheet?.code ?? "—"],
              ["Corpus", sheet?.kind === "real" ? "Verified Case Corpus / Official records" : sheet?.kind === "demo" ? "Synthetic demonstration" : sheet?.kind === "mixed" ? "Case corpus + public records" : "—"],
              ["Record kinds", String(kinds || "—")],
              ["Ledger", ledger ? `${ledger.verify.status} · ${ledger.verify.entries} sealed` : "—"],
              ["Engine", ai?.compute.engine ?? "—"],
            ] as const).map(([k, v]) => (
              <div key={k} className="flex min-w-[9rem] flex-1 flex-col justify-center border-r border-rule px-3 py-1.5 last:border-r-0">
                <dt className="label text-ink-faint">{k}</dt>
                <dd className="figure truncate text-[length:var(--fs-body)]">{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        <div className="grid grid-cols-12 gap-x-6 gap-y-8 pt-8">
          {/* on a narrow screen the index and detail rails are gone, so they are restated here */}
          <section className="col-span-12 md:hidden">
            <div className="flex items-baseline justify-between border-b border-ink pb-1"><h2 className="label label-ink">Key players by priority</h2><Link href="/players" className="label text-ink-soft hover:text-ink">All</Link></div>
            <ol className="divide-y divide-rule">
              {players.slice(0, 8).map((p, i) => {
                const st = recordStatus(p.suspicion);
                return (
                  <li key={p.id}>
                    <button type="button" onClick={() => select(p.id)} className="grid w-full grid-cols-[1.5rem_1fr_auto] items-center gap-2 py-2 text-left">
                      <span className="figure label text-ink-soft">{String(i + 1).padStart(2, "0")}</span>
                      <span className="min-w-0"><span className="block truncate font-semibold">{maskLabel(p.label, p.role)}</span><span className="block truncate note"><span className={st.tone}>{st.word}</span> · {roleOnly(p.role)}</span></span>
                      <span className="figure text-[length:var(--fs-lead)] font-semibold text-ink">{p.priority.toFixed(2)}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="col-span-12 md:col-span-6 lg:col-span-4">
            <div className="flex items-baseline justify-between border-b border-ink pb-1"><h2 className="label label-ink">Suspicious patterns</h2><Link href="/alerts" className="label text-ink-soft hover:text-ink">Register</Link></div>
            <div className="figure flex flex-wrap gap-4 py-2">{(["critical", "high", "medium", "low"] as const).map((sv) => <span key={sv} className="flex items-center gap-1.5 text-[length:var(--fs-body)]"><span aria-hidden="true" className="h-2.5 w-2.5" style={{ background: SEVERITY_INK[sv] }} />{bySev[sv] ?? 0} <span className="label text-ink-soft">{sv}</span></span>)}</div>
            <ul className="divide-y divide-rule">
              {(alerts ?? []).slice(0, 6).map((a) => <li key={a.id} className="py-1.5"><Link href={`/alerts?id=${a.id}`} className="block hover:bg-film-lift"><span className="label" style={{ color: SEVERITY_INK[a.severity] }}>{ALERT_KIND_LABEL[a.kind] ?? a.kind}</span><span className="block truncate text-[length:var(--fs-body)]">{a.title}</span></Link></li>)}
            </ul>
          </section>

          <section className="col-span-12 md:col-span-6 lg:col-span-4">
            <div className="border-b border-ink pb-1"><h2 className="label label-ink">Communities flagged</h2></div>
            <ul className="divide-y divide-rule">
              {suspicious.slice(0, 5).map((c) => <li key={c.id} className="py-2"><Link href={`/players?community=${c.id}`} className="flex items-start gap-2 hover:bg-film-lift"><span aria-hidden="true" className="mt-1 block h-3.5 w-1 shrink-0" style={{ background: routeInk(c.id) }} /><span className="min-w-0"><span className="block font-semibold">{c.label}</span><span className="block note">{c.size} actors · {c.accused_count} named accused · risk {c.risk.toFixed(2)} · {c.locations.slice(0, 3).join(", ")}</span></span></Link></li>)}
              {comms && !suspicious.length && <li className="note py-3">No community carries adverse signals.</li>}
            </ul>
          </section>

          <section className="col-span-12 lg:col-span-4">
            <div className="border-b border-ink pb-1"><h2 className="label label-ink">Provenance and integrity</h2></div>
            <dl className="mt-2 space-y-1.5 text-[length:var(--fs-body)]">
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Evidence ledger</dt><dd className={cn("figure font-semibold", ledger?.verify.valid ? "text-green" : "text-pencil")}>{ledger ? `${ledger.verify.status} · ${ledger.verify.entries} sealed` : "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Compute engine</dt><dd className="figure">{ai?.compute.engine ?? "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Extraction tiers</dt><dd className="figure">rules{ai?.extraction_tiers.neural.available ? " · neural" : ""}{ai?.extraction_tiers.llm.available ? " · llm" : ""}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Semantic search</dt><dd className="figure">{ai?.semantic_search.available ? "on" : "off"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-soft">Communities</dt><dd className="figure">{s?.communities ?? "—"} ({s?.suspicious_communities ?? 0} flagged)</dd></div>
            </dl>
            <p className="mt-3 note">{sheet?.kind === "real" ? `Sources on this sheet: ${sheet.sources.join(", ")}.` : "Benchmark: top-10 key players 10/10 genuine on the labelled case; both burner phones attributed by handset IMEI."} Full numbers in the Ledger lens.</p>
            <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Entities by type">
              {s && TYPE_ORDER.filter((t) => s.node_types[t]).map((t: EntityType) => <span key={t} className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[length:var(--fs-note)]"><Glyph shape={SHAPE[t]} size={11} />{TYPE_LABEL[t]} <span className="figure text-ink-soft">{s.node_types[t]}</span></span>)}
            </div>
          </section>
        </div>
      </div>
      <SheetFooter lens="Overview" />
    </div>
  );
}
