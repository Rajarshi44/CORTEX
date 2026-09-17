"use client";
/**
 * The front door. A case file emptied onto the desk, with the threads NOT yet drawn.
 * Every underlined name is a real control: pull one and the sheet strikes a line to every
 * other record that name appears in, and shows the sentence that justifies it. The visitor
 * performs the product's mechanic instead of reading about it.
 *
 * Threads attach to the measured position of each word, so they stay true at any scale.
 */
import Link from "next/link";
import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { LineSample } from "@/components/sheet/KeyRail";
import { INK } from "@/lib/notation";
import { cn } from "@/lib/utils";

const CANVAS_W = 940;
const CANVAS_H = 470;
const MIN_SCALE = 0.86;

type Grade = "solid" | "dashed" | "dotted";

const GRADE_NOTE: Record<Grade, string> = {
  solid: "Structured record. The field itself carries the link.",
  dashed: "Rule-extracted. A pattern in the narrative drew it.",
  dotted: "Model-inferred. Proposed, and still to be confirmed.",
};

const DASH: Record<Grade, string | undefined> = { solid: undefined, dashed: "7 5", dotted: "1.5 4" };

/* ---------------------------------------------------------------- the links to be found */

type LinkDef = {
  id: string;
  a: string; b: string;
  grade: Grade;
  conf: string;
  joins: string;
  sentence: string;
};

const LINKS: LinkDef[] = [
  {
    id: "l1", a: "salim", b: "phone", grade: "solid", conf: "1.00",
    joins: "Salim Qureshi to 98••••2211",
    sentence: "The subscriber on 98••••2211 is the person the FIR names as Salim Qureshi @ Sallu, r/o Nagpada.",
  },
  {
    id: "l2", a: "phone", b: "account", grade: "solid", conf: "1.00",
    joins: "98••••2211 to A/C ••••4471",
    sentence: "Three credits of ₹49,500, ₹49,500 and ₹48,000 land on one day, each below the ₹50,000 reporting line.",
  },
  {
    id: "l3", a: "rafiq", b: "party", grade: "dashed", conf: "0.86",
    joins: "Rafiq Sheikh to CRL.A. 442/2023",
    sentence: "…the consignment was arranged by one Rafiq Sheikh @ Bhai, and that payment moved through a Kurla account…",
  },
  {
    id: "l4", a: "party", b: "notice", grade: "solid", conf: "1.00",
    joins: "CRL.A. 442/2023 to the wanted notice",
    sentence: "State of Maharashtra versus Rafiq Sheikh & Ors. is the same name the notice circulates.",
  },
  {
    id: "l5", a: "gate", b: "tower", grade: "solid", conf: "1.00",
    joins: "JNPT Gate 3 to the 04:12 tower",
    sentence: "The interception point and the cell tower carrying the 04:12 call are the same location.",
  },
];

/** Which record each name lives in, so the rest of the tray can recede while a link is live. */
const ANCHOR_DOC: Record<string, string> = {
  gate: "fir", salim: "fir", rafiq: "fir",
  phone: "cdr", tower: "cdr",
  party: "judgment", account: "bank", notice: "wanted",
};

/* ------------------------------------------------------------------------ the tray state */

type TrayCtx = {
  selected: string | null;
  pick: (id: string) => void;
  liveAnchors: Set<string>;
};
const Tray = createContext<TrayCtx>({ selected: null, pick: () => {}, liveAnchors: new Set() });

/** A name inside a record. Underlined in pencil, and a real button. */
function Ent({ id, children }: { id: string; children: React.ReactNode }) {
  const { selected, pick, liveAnchors } = useContext(Tray);
  const on = selected === id || liveAnchors.has(id);
  return (
    <button
      type="button"
      data-anchor={id}
      onClick={() => pick(id)}
      aria-pressed={selected === id}
      className={cn(
        "cursor-pointer rounded-[1px] font-semibold underline decoration-pencil decoration-dotted underline-offset-[3px] transition-colors",
        on ? "bg-pencil-wash text-pencil" : "text-ink hover:bg-pencil-wash hover:text-pencil",
      )}
    >
      {children}
    </button>
  );
}

/* ----------------------------------------------------------------------------- the records */

type Doc = { id: string; kind: string; ref: string; x: number; y: number; w: number; rot: number; body: React.ReactNode };

const DOCS: Doc[] = [
  {
    id: "fir", kind: "First Information Report", ref: "FIR 0114/2024",
    x: 0, y: 30, w: 360, rot: -2.4,
    body: (
      <p className="text-[13px] leading-[1.55] text-ink">
        …on interception at <Ent id="gate">JNPT Gate 3</Ent>, accused{" "}
        <Ent id="salim">Salim Qureshi @ Sallu</Ent>, r/o Nagpada, was found in possession of 12.4 kg of a white
        crystalline substance since identified as Mephedrone. He stated the consignment was arranged by one{" "}
        <Ent id="rafiq">Rafiq Sheikh @ Bhai</Ent>, and that payment moved through a Kurla account…
      </p>
    ),
  },
  {
    id: "cdr", kind: "Call Detail Records", ref: "BATCH 0091",
    x: 340, y: 0, w: 424, rot: 1.6,
    body: (
      <table className="w-full figure text-[11px] leading-[1.8] text-ink">
        <thead>
          <tr className="label text-[10px] text-ink-soft">
            <th className="py-0.5 pr-3 text-left font-semibold">A-party</th>
            <th className="py-0.5 pr-3 text-left font-semibold">B-party</th>
            <th className="py-0.5 pr-3 text-right font-semibold">Time</th>
            <th className="py-0.5 text-left font-semibold">Tower</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-rule">
            <td className="pr-3"><Ent id="phone">98••••2211</Ent></td>
            <td className="pr-3">99••••8814</td>
            <td className="pr-3 text-right">04:12</td>
            <td><Ent id="tower">JNPT Gate 3</Ent></td>
          </tr>
          <tr className="border-t border-rule">
            <td className="pr-3">98••••2211</td><td className="pr-3">90••••3390</td>
            <td className="pr-3 text-right">04:31</td><td>Nagpada</td>
          </tr>
          <tr className="border-t border-rule">
            <td className="pr-3">90••••3390</td><td className="pr-3">99••••8814</td>
            <td className="pr-3 text-right">04:58</td><td>Kurla W</td>
          </tr>
        </tbody>
      </table>
    ),
  },
  {
    id: "judgment", kind: "Judgment", ref: "CRL.A. 442/2023",
    x: 512, y: 152, w: 404, rot: -1.4,
    body: (
      <p className="text-[13px] leading-[1.5] text-ink">
        <span className="label text-[11px] text-ink-soft">State of Maharashtra</span>{" "}
        <span className="text-ink-soft">versus</span> <Ent id="party">Rafiq Sheikh &amp; Ors.</Ent>
        <span className="mt-1 block text-ink-soft">
          …bail rejected. The appellant&apos;s association with the co-accused stands established on the call
          records placed on record…
        </span>
      </p>
    ),
  },
  {
    id: "bank", kind: "Account Statement", ref: "11 MAR 2024",
    x: 40, y: 250, w: 336, rot: 3.2,
    body: (
      <>
        <p className="mb-1 text-[12px] text-ink-soft">
          <Ent id="account">A/C ••••4471</Ent>
        </p>
        <table className="w-full figure text-[11px] leading-[1.75] text-ink">
          <tbody>
            <tr className="border-t border-rule"><td>11 Mar</td><td className="text-ink-soft">UPI-CR</td><td className="text-right text-blue">₹49,500</td></tr>
            <tr className="border-t border-rule"><td>11 Mar</td><td className="text-ink-soft">UPI-CR</td><td className="text-right text-blue">₹49,500</td></tr>
            <tr className="border-t border-rule"><td>11 Mar</td><td className="text-ink-soft">UPI-CR</td><td className="text-right text-blue">₹48,000</td></tr>
          </tbody>
        </table>
      </>
    ),
  },
  {
    id: "wanted", kind: "Wanted Notice", ref: "NCB MUMBAI ZONE",
    x: 350, y: 336, w: 300, rot: -3.6,
    body: (
      <p className="text-[13px] leading-[1.45] text-ink">
        <span className="stencil block text-[17px] font-bold tracking-[0.04em]">
          <Ent id="notice">Rafiq Sheikh</Ent>
        </span>
        <span className="label mt-0.5 block text-[11px] text-ink-soft">alias Bhai</span>
        <span className="mt-1 block text-[12px] text-ink-soft">Wanted in connection with NDPS 21(c) / 29.</span>
      </p>
    ),
  },
];

const PROOF = [
  { figure: "10 / 10", note: "of the top ten key players are genuine network members, with no false positives.", source: "Benchmark with a hidden answer key" },
  { figure: "8 / 8", note: "anomaly flags genuine, including both burner identities and the foreign handler.", source: "Benchmark with a hidden answer key" },
  { figure: "10", note: "verified public sources: eCourts, NIA, ICIJ, OpenSanctions, GLEIF, data.gov.in.", source: "Live connectors" },
  { figure: "< 20 s", note: "to resolve 3,954 entities and 4,191 relationships across all ten sources.", source: "Single run on real data" },
];

/* --------------------------------------------------------------------------------- page */

export default function Landing() {
  const reduce = useReducedMotion();
  const [selected, setSelected] = useState<string | null>(null);
  const [found, setFound] = useState<Set<string>>(() => new Set());
  const [pts, setPts] = useState<Record<string, { x: number; y: number }>>({});
  const [scale, setScale] = useState(1);
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const pick = useCallback((id: string) => {
    setSelected(id);
    setFound((prev) => {
      const next = new Set(prev);
      for (const l of LINKS) if (l.a === id || l.b === id) next.add(l.id);
      return next;
    });
  }, []);

  // Fit the fixed canvas to its column; below MIN_SCALE it pans in its own scroller.
  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setScale(Math.max(MIN_SCALE, Math.min(1, el.clientWidth / CANVAS_W)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Measure where every name actually sits, so threads attach to the words themselves.
  useLayoutEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const measure = () => {
      const cb = c.getBoundingClientRect();
      const s = cb.width / CANVAS_W || 1;
      const next: Record<string, { x: number; y: number }> = {};
      c.querySelectorAll<HTMLElement>("[data-anchor]").forEach((el) => {
        const r = el.getBoundingClientRect();
        next[el.dataset.anchor!] = {
          x: (r.left + r.width / 2 - cb.left) / s,
          y: (r.top + r.height / 2 - cb.top) / s,
        };
      });
      setPts(next);
    };
    const ro = new ResizeObserver(measure);
    ro.observe(c);
    return () => ro.disconnect();
  }, []);

  const shown = useMemo(
    () => LINKS.filter((l) => selected && (l.a === selected || l.b === selected)),
    [selected],
  );
  const liveAnchors = useMemo(() => {
    const s = new Set<string>();
    for (const l of shown) { s.add(l.a); s.add(l.b); }
    return s;
  }, [shown]);
  const note = shown[0] ?? null;
  const complete = found.size === LINKS.length;

  const litDocs = useMemo(() => {
    const s = new Set<string>();
    for (const id of liveAnchors) { const d = ANCHOR_DOC[id]; if (d) s.add(d); }
    return s;
  }, [liveAnchors]);

  const curve = (a: { x: number; y: number }, b: { x: number; y: number }) => {
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    // bow the line off the straight run so it reads as drawn, not plotted
    const bow = Math.min(46, len * 0.16);
    return `M ${a.x} ${a.y} Q ${mx - (dy / len) * bow} ${my + (dx / len) * bow} ${b.x} ${b.y}`;
  };

  return (
    <main className="sheet-ground min-h-dvh text-ink">
      <header className="flex h-14 flex-wrap items-center gap-x-4 border-b border-ink bg-film-deep/80 px-4 sm:px-6">
        <span className="stencil text-[var(--fs-lead)] font-bold text-ink">CORTEX</span>
        <p className="label hidden text-[10px] text-ink-soft sm:block">SIH 26189 for MHA / NCRB</p>
        <Link
          href="/login"
          className="label ml-auto border border-ink px-3 py-1.5 text-ink transition-transform hover:bg-ink hover:text-film active:translate-y-[1px]"
        >
          Open the sheet
        </Link>
      </header>

      <div className="mx-auto grid max-w-[1500px] grid-cols-1 gap-8 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_23rem] lg:gap-10 lg:py-8">
        {/* ------------------------------------------------------------------ the tray */}
        <section aria-labelledby="tray-h" className="min-w-0">
          <h2 id="tray-h" className="sr-only">Five records. Pull a name to draw its links.</h2>
          <div
            ref={frameRef}
            tabIndex={0}
            aria-label="The tray of records. Scrolls sideways."
            className="w-full min-w-0 overflow-x-auto"
          >
            <div className="relative" style={{ width: CANVAS_W * scale, height: CANVAS_H * scale }}>
              <div
                ref={canvasRef}
                className="absolute left-0 top-0"
                style={{ width: CANVAS_W, height: CANVAS_H, transform: `scale(${scale})`, transformOrigin: "top left" }}
              >
                <Tray.Provider value={{ selected, pick, liveAnchors }}>
                  {DOCS.map((d) => (
                    <article
                      key={d.id}
                      data-doc={d.id}
                      className={cn(
                        "note-paper absolute border border-rule-strong px-3 py-2.5 transition-opacity duration-300",
                        selected && !litDocs.has(d.id) && "opacity-[0.55]",
                      )}
                      style={{ left: d.x, top: d.y, width: d.w, transform: `rotate(${d.rot}deg)` }}
                    >
                      <header className="mb-1.5 flex items-baseline justify-between gap-3 border-b border-rule pb-1">
                        <h3 className="label text-[10px] label-ink">{d.kind}</h3>
                        <p className="figure text-[9px] uppercase tracking-[0.08em] text-ink-soft">{d.ref}</p>
                      </header>
                      {d.body}
                    </article>
                  ))}
                </Tray.Provider>

                <svg
                  width={CANVAS_W} height={CANVAS_H} viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
                  className="pointer-events-none absolute inset-0" aria-hidden="true"
                >
                  {shown.map((l) => {
                    const a = pts[l.a], b = pts[l.b];
                    if (!a || !b) return null;
                    return (
                      <g key={l.id}>
                        <motion.path
                          d={curve(a, b)}
                          fill="none"
                          stroke={INK.pencil}
                          strokeWidth={2}
                          strokeDasharray={DASH[l.grade]}
                          strokeLinecap="round"
                          initial={reduce ? false : { pathLength: 0 }}
                          animate={{ pathLength: 1 }}
                          transition={{ duration: 0.75, ease: [0.16, 1, 0.3, 1] }}
                        />
                        <motion.circle
                          cx={b.x} cy={b.y} r={4.5}
                          fill={INK.pencil}
                          initial={reduce ? false : { scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: 0.55, type: "spring", stiffness: 320, damping: 22 }}
                        />
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          </div>

          <p className="note mt-3 max-w-[70ch] text-ink-soft">
            Records shown are from the Official CORTEX Case Corpus (<span className="text-ink">Operation Saltwater</span>).
            Identifiers are masked exactly as the console masks them.
          </p>
        </section>

        {/* -------------------------------------------------------------- the argument */}
        <section className="min-w-0">
          <h1 className="text-balance font-condensed text-[clamp(2.5rem,5.5vw,4rem)] font-bold leading-[0.94] tracking-[-0.02em] text-ink">
            Five papers that never met.
          </h1>
          <p className="mt-4 max-w-[46ch] text-[var(--fs-lead)] leading-[1.55] text-ink-soft">
            An FIR, a call record, a statement, a judgment, a notice. Pull any underlined name to draw its link.
          </p>

          {/* the live readout: empty, partial, complete */}
          <div className="mt-5 min-h-[7rem] border-t border-ink pt-3">
            <div className="flex items-baseline gap-3">
              <p className="figure text-[var(--fs-body)] font-semibold text-ink">
                {found.size} of {LINKS.length}
              </p>
              <p className="note text-ink-soft">links drawn</p>
              <span className="ml-auto flex gap-1" aria-hidden="true">
                {LINKS.map((l) => (
                  <span key={l.id} className={cn("h-1 w-5", found.has(l.id) ? "bg-pencil" : "bg-rule-strong")} />
                ))}
              </span>
            </div>

            <div aria-live="polite" className="mt-3">
              {!note ? (
                <p className="text-[var(--fs-body)] leading-snug text-ink-soft">
                  Nothing is drawn yet. Every line this sheet makes has to be pulled from a record, and it carries
                  the sentence that justifies it.
                </p>
              ) : (
                <>
                  <p className="figure text-[var(--fs-note)] text-ink-soft">{note.joins}</p>
                  <blockquote className="mt-1.5 border-l border-rule-strong pl-3 text-[var(--fs-body)] leading-snug text-ink">
                    &ldquo;{note.sentence}&rdquo;
                  </blockquote>
                  <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[var(--fs-note)] text-ink-soft">
                    <LineSample style={note.grade} width={26} ink={INK.pencil} />
                    <span className="min-w-0 flex-1">{GRADE_NOTE[note.grade]}</span>
                    <span className="figure">conf {note.conf}</span>
                  </p>
                </>
              )}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <Link
              href="/login"
              className={cn(
                "border px-5 py-2.5 text-[var(--fs-body)] font-semibold transition-transform active:translate-y-[1px]",
                complete
                  ? "border-pencil bg-pencil text-film hover:border-ink hover:bg-ink"
                  : "border-ink bg-film-lift text-ink hover:bg-ink hover:text-film",
              )}
            >
              Open the sheet
            </Link>
            <span className="note text-ink-soft">
              {complete ? "That is the whole network. The console does it across 777 documents." : "analyst / analyst@123"}
            </span>
          </div>

          <dl className="mt-6 space-y-1.5 border-t border-rule-strong pt-3">
            {(["solid", "dashed", "dotted"] as const).map((g) => (
              <div key={g} className="flex items-start gap-2">
                <LineSample style={g} width={26} ink={INK.pencil} />
                <dt className="min-w-0 flex-1 text-[var(--fs-note)] text-ink-soft">{GRADE_NOTE[g]}</dt>
              </div>
            ))}
          </dl>
        </section>
      </div>

      {/* ------------------------------------------------------------------ measured proof */}
      <section aria-labelledby="proof-h" className="border-t border-ink bg-film-deep/70">
        <h2 id="proof-h" className="sr-only">Measured results</h2>
        <dl className="mx-auto grid max-w-[1500px] gap-x-8 gap-y-5 px-4 py-6 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          {PROOF.map((p) => (
            <div key={p.figure} className="border-t border-rule-strong pt-2">
              <dt className="figure font-condensed text-[1.9rem] font-bold leading-none tracking-[-0.02em] text-ink">
                {p.figure}
              </dt>
              <dd className="mt-1.5 max-w-[34ch] text-[var(--fs-note)] leading-snug text-ink-soft">
                {p.note}
                <span className="label mt-1 block text-[9px] text-ink-soft">{p.source}</span>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="border-t border-rule-strong">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-end justify-between gap-4 px-4 py-4 sm:px-6">
          <Link href="/login" className="label text-pencil hover:underline">Open the sheet</Link>
          <dl className="ml-auto grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 border border-rule-strong bg-film-lift px-3 py-2 text-right">
            <dt className="label text-[9px] text-ink-soft">Sheet</dt>
            <dd className="figure text-[var(--fs-note)] text-ink">001</dd>
            <dt className="label text-[9px] text-ink-soft">Case</dt>
            <dd className="figure text-[var(--fs-note)] text-ink">SIH 26189</dd>
          </dl>
        </div>
      </footer>
    </main>
  );
}
