"use client";
/**
 * Standing watches: the half of the register that fires on arrival rather than on recompute.
 *
 * Kept visually distinct from the detector register above it. A detector alert is an inference the
 * sheet redraws every time it recomputes; a hit is a fact about one document that arrived, and it
 * survives every recompute. Conflating the two would tell a reader that both carry the same weight,
 * and they do not: a hit is a record to open, an alert is a lead to rule out.
 */
import { useState } from "react";
import Link from "next/link";
import { useSheet } from "@/lib/store";
import {
  useWatches, useWatchHits, useWatchKinds, useCreateWatch, useDeleteWatch, useRescanWatch,
  useToggleWatch, useWatchHitStatus,
} from "@/lib/queries";
import { SEVERITY_INK } from "@/lib/notation";
import type { HitStatus, Severity, Watch, WatchHit, WatchKind } from "@/lib/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const HIT_STATUSES: HitStatus[] = ["new", "reviewing", "confirmed", "dismissed"];
const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

const KIND_LABEL: Record<WatchKind, string> = {
  PERSON: "Person", ORGANIZATION: "Organisation", PHONE: "Phone", VEHICLE: "Vehicle",
  BANK_ACCOUNT: "Account", GOV_ID: "Identifier", TEXT: "Phrase",
};

// What a useful selector looks like for each kind, so the field is never a blank guess.
const PLACEHOLDER: Record<WatchKind, string> = {
  PERSON: "Rajiv Singh", ORGANIZATION: "Meridian Traders Pvt Ltd", PHONE: "9876543210",
  VEHICLE: "MH 12 AB 1234", BANK_ACCOUNT: "50100234567890", GOV_ID: "ABCDE1234F", TEXT: "hawala",
};

function when(iso: string | null): string {
  if (!iso) return "—";
  try { return format(new Date(iso), "dd MMM yyyy"); } catch { return "—"; }
}

export default function StandingWatches() {
  const { data: watches } = useWatches();
  const { data: kinds } = useWatchKinds();
  const [status, setStatus] = useState<string>("new");
  const { data: hits, isLoading } = useWatchHits({ status: status || undefined, limit: 200 });
  const rows = watches ?? [];
  const armed = rows.filter((w) => w.active).length;

  return (
    <section className="mt-10 border-t-2 border-ink pt-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[length:var(--fs-sheet)] font-semibold leading-none tracking-tight">Standing watches</h2>
          <p className="mt-1 max-w-[76ch] text-ink-soft">
            A detector reads the whole sheet and is redrawn on every recompute. A watch does the opposite: it names
            one selector and checks it against every record as that record arrives, then keeps the hit with the
            document that caused it. Arming one also searches everything already held, so the answer to
            <em> has this ever appeared</em> comes back immediately.
          </p>
        </div>
        <p className="label shrink-0 text-ink-faint">{armed} armed · {rows.length - armed} paused</p>
      </div>

      <ArmForm kinds={kinds?.kinds} />
      {rows.length > 0 && <WatchList rows={rows} />}

      <div className="mt-7 flex flex-wrap items-end justify-between gap-3 border-b border-rule-strong pb-1">
        <h3 className="label label-ink">Records that matched</h3>
        <label className="label flex items-center gap-1.5">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="border border-rule-strong bg-film px-1.5 py-1 text-[length:var(--fs-body)] normal-case tracking-normal">
            <option value="">any</option>
            {HIT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      <HitList hits={hits} isLoading={isLoading} hasWatches={rows.length > 0} />
    </section>
  );
}

// ------------------------------------------------------------------------------------- arming
function ArmForm({ kinds }: { kinds?: { kind: WatchKind; help: string }[] }) {
  const [kind, setKind] = useState<WatchKind>("PHONE");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState<Severity>("high");
  const [said, setSaid] = useState<string | null>(null);
  const create = useCreateWatch();
  const help = kinds?.find((k) => k.kind === kind)?.help;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setSaid(null);
    create.mutate({ kind, value, reason, severity }, {
      onSuccess: (w) => {
        // The interesting number is the backfill: what was already on the sheet before the watch existed.
        setSaid(w.created
          ? `Armed on ${w.selector}. ${w.backfill_hits === 0 ? "Nothing already held matches it." : `${w.backfill_hits} record(s) already held matched.`}`
          : (w.note ?? "Already watched."));
        setValue(""); setReason("");
      },
      onError: (err) => setSaid(err instanceof Error ? err.message : "Could not arm that watch."),
    });
  }

  return (
    <form onSubmit={submit} className="mt-4 border border-rule-strong bg-film-lift p-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="label flex flex-col gap-1">Watch
          <select value={kind} onChange={(e) => { setKind(e.target.value as WatchKind); setSaid(null); }}
                  className="border border-rule-strong bg-film px-2 py-1 text-[length:var(--fs-body)] normal-case tracking-normal">
            {(Object.keys(KIND_LABEL) as WatchKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </label>
        <label className="label flex min-w-[14rem] flex-1 flex-col gap-1">Selector
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder={PLACEHOLDER[kind]}
                 className="border border-rule-strong bg-film px-2 py-1 text-[length:var(--fs-body)] normal-case tracking-normal" />
        </label>
        <label className="label flex min-w-[14rem] flex-1 flex-col gap-1">Why <span className="text-ink-faint">(carried onto every hit)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="absconding accused, FIR 214/2024"
                 className="border border-rule-strong bg-film px-2 py-1 text-[length:var(--fs-body)] normal-case tracking-normal" />
        </label>
        <label className="label flex flex-col gap-1">Severity
          <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}
                  className="border border-rule-strong bg-film px-2 py-1 text-[length:var(--fs-body)] normal-case tracking-normal">
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <button type="submit" disabled={create.isPending || !value.trim()}
                className="label border border-ink bg-ink px-3 py-1.5 text-film disabled:opacity-40">
          {create.isPending ? "Arming…" : "Arm watch"}
        </button>
      </div>
      {help && <p className="mt-2 note max-w-[92ch]">{help}</p>}
      {said && <p className={cn("mt-2 text-[length:var(--fs-note)]", create.isError ? "text-pencil" : "text-ink-soft")} role="status">{said}</p>}
    </form>
  );
}

// ------------------------------------------------------------------------------------- watches
function WatchList({ rows }: { rows: Watch[] }) {
  const del = useDeleteWatch();
  const rescan = useRescanWatch();
  const toggle = useToggleWatch();
  const [said, setSaid] = useState<string | null>(null);

  return (
    <div className="mt-4">
      <div className="label grid grid-cols-[6rem_1fr_1fr_4rem_7rem_11rem] items-center gap-3 border-b border-rule-strong pb-1 text-ink-faint">
        <span>Kind</span><span>Selector</span><span>Why</span><span className="text-right">Hits</span><span>Last hit</span><span />
      </div>
      <ul>
        {rows.map((w) => (
          <li key={w.id} className={cn("grid grid-cols-[6rem_1fr_1fr_4rem_7rem_11rem] items-center gap-3 border-b border-rule py-1.5", !w.active && "opacity-45")}>
            <span className="label flex items-center gap-1.5" style={{ color: SEVERITY_INK[w.severity] }}>
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: SEVERITY_INK[w.severity] }} />
              {KIND_LABEL[w.kind]}
            </span>
            <span className="truncate font-medium">{w.selector}</span>
            <span className="truncate text-ink-soft">{w.reason || <span className="text-ink-faint">—</span>}</span>
            <span className="figure text-right">
              {w.hit_count}
              {w.new_hits > 0 && <span className="ml-1 text-pencil" title={`${w.new_hits} not yet actioned`}>·{w.new_hits}</span>}
            </span>
            <span className="figure text-ink-faint">{when(w.last_hit_at)}</span>
            <span className="flex justify-end gap-2">
              <button type="button" disabled={rescan.isPending}
                      onClick={() => rescan.mutate(w.id, { onSuccess: (r) => setSaid(`${w.selector}: ${r.new_hits} new match(es) across the sheet.`) })}
                      className="label text-ink-soft hover:text-pencil disabled:opacity-40">rescan</button>
              <button type="button" onClick={() => toggle.mutate({ id: w.id, active: !w.active })}
                      className="label text-ink-soft hover:text-pencil">{w.active ? "pause" : "arm"}</button>
              <button type="button"
                      onClick={() => { if (confirm(`Delete the watch on ${w.selector}? Its ${w.hit_count} recorded hit(s) go with it.`)) del.mutate(w.id); }}
                      className="label text-ink-faint hover:text-pencil">delete</button>
            </span>
          </li>
        ))}
      </ul>
      {said && <p className="mt-2 note" role="status">{said}</p>}
    </div>
  );
}

// ------------------------------------------------------------------------------------- hits
function HitList({ hits, isLoading, hasWatches }: { hits?: WatchHit[]; isLoading: boolean; hasWatches: boolean }) {
  const patch = useWatchHitStatus();
  const select = useSheet((s) => s.select);

  if (isLoading) return <ul className="mt-2">{[0, 1, 2].map((i) => <li key={i} className="h-12 animate-pulse border-b border-rule bg-film-deep/40" />)}</ul>;
  if (!hits?.length) {
    return (
      <p className="py-6 note">
        {hasWatches
          ? "Nothing has matched yet. A watch stays armed and checks every record that arrives from here on."
          : "No watches armed. Arm one above and it will be checked against the records already held, then against every record that arrives."}
      </p>
    );
  }
  return (
    <ul className="mt-1">
      {hits.map((h, i) => (
        <li key={h.id} className="ripple-in border-b border-rule py-2" style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }}>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="label flex items-center gap-1.5 shrink-0" style={{ color: SEVERITY_INK[h.watch?.severity ?? "medium"] }}>
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: SEVERITY_INK[h.watch?.severity ?? "medium"] }} />
              {h.watch ? KIND_LABEL[h.watch.kind] : "watch"}
            </span>
            <span className="font-medium">{h.watch?.selector}</span>
            <span className="text-ink-faint">matched {h.matched_on}</span>
            <span className="figure ml-auto shrink-0 text-ink-faint">{when(h.occurred_at ?? h.created_at)}</span>
          </div>
          {h.watch?.reason && <p className="mt-0.5 note">Watched because: {h.watch.reason}</p>}
          {h.snippet && <p className="mt-1 max-w-[90ch] text-[length:var(--fs-note)] leading-relaxed text-ink-soft">“{h.snippet}”</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {h.document && (
              <Link href={`/sources?doc=${h.document.id}`} className="label text-pencil hover:underline">
                {h.document.source_type} · {h.document.title}
              </Link>
            )}
            {h.entity && (
              <button type="button" onClick={() => select(h.entity!.id)} className="label border border-rule-strong px-1.5 py-0.5 hover:border-ink">
                {h.entity.label}
              </button>
            )}
            {/* On a corpus of judgments the busiest name is often the judge. Saying so turns a
                distraction into a row the reader can dismiss without opening it. */}
            {h.entity?.record_role && (
              <span className={cn("label", h.entity.non_subject ? "text-ink-faint" : "text-ink-soft")}
                    title={h.entity.non_subject ? "Machinery of the case, not a subject of it" : "Standing in the record"}>
                {h.entity.record_role}
              </span>
            )}
            <span className="label ml-auto text-ink-faint">Mark</span>
            {HIT_STATUSES.map((s) => (
              <button key={s} type="button" disabled={h.status === s} onClick={() => patch.mutate({ id: h.id, status: s })}
                      className={cn("label border px-2 py-0.5", h.status === s ? "border-ink bg-ink text-film" : "border-rule-strong hover:border-ink")}>
                {s}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
