"use client";
import { Suspense, useMemo, useState } from "react";
import { useQueryState, parseAsInteger } from "nuqs";
import { useKeyPlayers, useCommunities, useLinkPredictions } from "@/lib/queries";
import { useSheet } from "@/lib/store";
import { Glyph } from "@/components/sheet/KeyRail";
import SheetFooter from "@/components/sheet/SheetFooter";
import { SHAPE } from "@/lib/notation";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { Link2 } from "lucide-react";

function Bar({ v, ink = "var(--ink)", max = 1 }: { v: number; ink?: string; max?: number }) {
  return <span className="inline-block h-1.5 w-20 bg-film-deep align-middle"><span className="block h-full" style={{ width: `${Math.min(100, (v / max) * 100)}%`, background: ink }} /></span>;
}

function Players() {
  const { data: kp } = useKeyPlayers();
  const { data: comms } = useCommunities();
  const { data: lp } = useLinkPredictions();
  const [community, setCommunity] = useQueryState("community", parseAsInteger);
  const select = useSheet((s) => s.select);
  const setHighlights = useSheet((s) => s.setHighlights);
  const [sort, setSort] = useState<"priority" | "influence" | "suspicion" | "betweenness">("priority");
  const players = useMemo(() => (kp?.key_players ?? []).filter((p) => community === null || p.community === community).slice().sort((a, b) => (b[sort] as number) - (a[sort] as number)), [kp, community, sort]);
  const comm = comms?.find((c) => c.id === community);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto grid w-full max-w-[1500px] grid-cols-12 gap-x-6 gap-y-8 px-6 py-6">
        <section className="col-span-12 lg:col-span-7">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink pb-2">
            <div><h1 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Key players</h1><p className="mt-1 text-ink-soft">Priority fuses structural influence with evidentiary suspicion. A well-connected citizen has influence without suspicion and does not surface here.</p></div>
            <div className="flex items-center gap-1" role="group" aria-label="Sort">{(["priority", "influence", "suspicion", "betweenness"] as const).map((k) => <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)} className={cn("label px-2 py-1", sort === k ? "label-ink pencil-line" : "text-ink-faint hover:text-ink")}>{k}</button>)}</div>
          </div>
          {community !== null && <p className="mt-2 flex items-center gap-2 text-[length:var(--fs-body)]">Showing community #{community}{comm ? ` · ${comm.label}` : ""}. <button type="button" onClick={() => setCommunity(null)} className="label text-pencil hover:underline">show all</button></p>}
          <p className="mt-3 note border-l-2 border-rule-strong pl-3">
            <b className="text-ink">Priority</b> is 55% <b className="text-ink">position</b> in the network and
            45% <b className="text-ink">record</b> against the person. Both are needed: heavy influence with a clean
            record means well connected, not suspect.
          </p>
          <ol className="mt-2">
            {players.map((p, i) => (
              <li key={p.id} className="track grid grid-cols-[2rem_minmax(0,1fr)_9.5rem] items-start gap-3 py-3">
                <span className="figure label pt-1 text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                <button type="button" onClick={() => select(p.id)} className="min-w-0 text-left hover:text-pencil">
                  <span className="flex items-start gap-2">
                    <Glyph shape={SHAPE[p.type]} size={14} className="mt-1 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-semibold leading-snug">{p.label}
                        {p.aliases?.length ? <span className="font-normal text-ink-faint"> @ {p.aliases.join(", ")}</span> : null}
                      </span>
                      {/* the service's status: a word and a border, so the read never depends on hue */}
                      <span
                        className="status mt-1"
                        style={{ "--status-tone": p.suspicion >= 0.5 ? "var(--pencil)" : p.suspicion >= 0.2 ? "var(--amber-deep)" : "var(--rule-strong)" } as React.CSSProperties}
                        title={p.suspicion >= 0.2 ? "An adverse record exists for this actor" : "No adverse record"}
                      >
                        {p.role}
                      </span>
                      <span className="mt-0.5 block note">{p.reasons?.slice(0, 2).join("; ")}</span>
                    </span>
                  </span>
                </button>
                <div className="pt-0.5 text-right">
                  {/* the figure is ink: a number is not an accusation. Red is spent only where a record exists. */}
                  <span className="figure block text-[length:var(--fs-title)] font-semibold leading-none text-ink">{p.priority.toFixed(2)}</span>
                  {/* one bar, split into the two things that produced the number above it */}
                  <span aria-hidden="true" className="mt-1.5 flex h-1.5 w-full overflow-hidden bg-film-deep">
                    <span className="block bg-ink" style={{ width: `${Math.round(0.55 * p.influence * 100)}%` }} />
                    <span className="block bg-amber-deep" style={{ width: `${Math.round(0.45 * p.suspicion * 100)}%` }} />
                  </span>
                  <span className="figure mt-1 block note">
                    <span className="text-ink">pos {p.influence.toFixed(2)}</span>
                    {" · "}
                    <span className={p.suspicion >= 0.2 ? "text-amber-deep" : "text-ink-soft"}>rec {p.suspicion.toFixed(2)}</span>
                  </span>
                </div>
              </li>
            ))}
            {!kp && <li className="py-6 text-center note">Computing…</li>}
            {kp && !players.length && <li className="py-6 text-center note">No key player matches this filter.</li>}
          </ol>

          <h2 className="label label-ink mt-8 border-b border-ink pb-1">Brokers — who bridges the groups</h2>
          <ul className="divide-y divide-rule">
            {(kp?.brokers ?? []).map((b) => <li key={b.id} className="flex items-center gap-3 py-2"><button type="button" onClick={() => select(b.id)} className="font-semibold hover:text-pencil">{b.label}</button><span className="note">bridges {b.community_span} communities · betweenness {b.betweenness.toFixed(3)}</span><span className="figure ml-auto text-ink-soft">{b.bridges.map((x) => `#${x.community}:${x.contacts}`).join("  ")}</span></li>)}
          </ul>

          <h2 className="label label-ink mt-8 border-b border-ink pb-1">Disruption — if removed</h2>
          <table className="mt-1 w-full">
            <thead><tr className="label text-left text-ink-faint"><th className="py-1 font-semibold">Target</th><th className="py-1 text-right font-semibold">Flow cut</th><th className="py-1 text-right font-semibold">Fragmentation</th><th className="py-1 font-semibold">Isolated</th></tr></thead>
            <tbody>{Object.values(kp?.removal_impact ?? {}).map((r) => <tr key={r.node} className="border-t border-rule"><td className="py-1.5"><button type="button" onClick={() => select(r.node)} className="hover:text-pencil">{r.label}</button></td><td className="figure py-1.5 text-right text-pencil">{Math.round((r.flow_share ?? 0) * 100)}%</td><td className="figure py-1.5 text-right">{Math.round((r.community_fragmentation ?? 0) * 100)}%</td><td className="py-1.5 note">{r.isolated_after?.map((x) => x.label).join(", ") || "—"}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="col-span-12 lg:col-span-5">
          <h2 className="label label-ink border-b border-ink pb-1">Communities</h2>
          <ul className="divide-y divide-rule">
            {(comms ?? []).filter((c) => c.size > 1).map((c) => (
              <li key={c.id} className={cn("py-2", community === c.id && "bg-film-lift -mx-2 px-2")}>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => setCommunity(community === c.id ? null : c.id)} className="font-semibold hover:text-pencil">#{c.id} {c.label}</button>
                  {c.suspicious && <span className="label text-pencil">flagged</span>}
                  <span className="figure ml-auto note">{c.size} actors · risk {c.risk.toFixed(2)}</span>
                </div>
                {/* Only say what this group actually has. Printing "0 named accused · no locations"
                    on every row taught the reader to stop reading the line. */}
                <p className="note">{[
                  c.accused_count ? `${c.accused_count} named accused` : null,
                  `density ${c.density}`,
                  c.locations.length ? c.locations.slice(0, 3).join(", ") : null,
                ].filter(Boolean).join(" · ")}</p>
                <p className="mt-1 flex flex-wrap gap-1">{c.top_members.slice(0, 5).map((m) => <button key={m.id} type="button" onClick={() => select(m.id)} className="border border-rule-strong px-1.5 py-0.5 text-[length:var(--fs-note)] hover:border-ink">{m.label}</button>)}</p>
                <button type="button" onClick={() => setHighlights(c.members, `Community #${c.id}, ${c.size} actors, emphasised on the chart.`)} className="label mt-1 border border-rule-strong px-2 py-0.5 text-ink-soft hover:border-ink hover:text-ink">Emphasise on chart</button>
              </li>
            ))}
          </ul>

          <h2 className="label label-ink mt-8 border-b border-ink pb-1">Predicted links — not yet observed</h2>
          <p className="mt-1 note">Adamic–Adar over shared associates, weighted by suspicion. Leads to check, not facts.</p>
          <ul className="divide-y divide-rule">
            {(lp ?? []).slice(0, 8).map((p, i) => <li key={i} className="py-2"><div className="flex items-center gap-2"><button type="button" onClick={() => select(p.source)} className="font-semibold hover:text-pencil">{p.source_label}</button><Link2 className="h-3 w-3 shrink-0 text-ink-soft" aria-label="and" /><button type="button" onClick={() => select(p.target)} className="font-semibold hover:text-pencil">{p.target_label}</button><span className="figure ml-auto note">{p.score.toFixed(2)}</span></div><p className="note">{p.explanation}</p><Link href={`/chart?from=${p.source}&to=${p.target}`} className="label mt-1 inline-block border border-rule-strong px-2 py-0.5 text-ink-soft hover:border-ink hover:text-ink">Draw route</Link></li>)}
          </ul>
        </section>
      </div>
      <SheetFooter lens="Players" />
    </div>
  );
}
export default function Page() { return <Suspense><Players /></Suspense>; }
