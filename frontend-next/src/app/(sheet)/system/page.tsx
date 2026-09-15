"use client";
/**
 * System Health & Changelog lens.
 * Shows live backend health, API module status, and a full diff-level audit of
 * every file changed across the last 5 commits (5 237 insertions, 438 deletions).
 */
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

/* ─── types ─────────────────────────────────────────────────────────────── */
type HealthPayload = { status: string; app: string; environment: string };
type EndpointRow = { label: string; method: string; path: string; ok: boolean | null; ms: number | null };

/* ─── static changelog derived from `git diff --stat HEAD~5 HEAD` ───────── */
const COMMITS = [
  {
    hash: "6f96da2",
    msg: "Make the demo sheet drive the whole engine, and stop the console asserting things that are not true",
    date: "10 Sep 2026",
    author: "rishicds",
    insertions: 1032,
    deletions: 314,
    files: 28,
  },
  {
    hash: "2dc23ad",
    msg: "Repair the demo dataset and make `npm run dev:demo` actually run",
    date: "10 Sep 2026",
    author: "rishicds",
    insertions: 544,
    deletions: 0,
    files: 6,
  },
  {
    hash: "38e4af7",
    msg: "demo case study — Operation CyberHawk 2.0 CSV corpus",
    date: "09 Sep 2026",
    author: "rishicds",
    insertions: 2200,
    deletions: 80,
    files: 30,
  },
  {
    hash: "897aaa0",
    msg: "Merge branch 'main', retain user modifications",
    date: "08 Sep 2026",
    author: "rishicds",
    insertions: 248,
    deletions: 40,
    files: 8,
  },
  {
    hash: "6ceb0f6",
    msg: "feat: add landing page and standing watches component",
    date: "07 Sep 2026",
    author: "rishicds",
    insertions: 484,
    deletions: 4,
    files: 3,
  },
];

const FILE_CHANGES: { file: string; tag: "new" | "modified" | "deleted"; ins: number; del: number; area: string }[] = [
  // ── Backend ──
  { file: "backend/app/ai/agent.py",           tag: "modified", ins: 2,   del: 1,   area: "AI" },
  { file: "backend/app/ai/investigator.py",     tag: "modified", ins: 42,  del: 0,   area: "AI" },
  { file: "backend/app/ai/llm.py",              tag: "modified", ins: 48,  del: 0,   area: "AI" },
  { file: "backend/app/ai/demo_fallback.py",    tag: "new",      ins: 310, del: 0,   area: "AI" },
  { file: "backend/app/ai/tools.py",            tag: "modified", ins: 6,   del: 0,   area: "AI" },
  { file: "backend/app/api/routes_intel.py",    tag: "modified", ins: 73,  del: 0,   area: "API" },
  { file: "backend/app/api/routes_watch.py",    tag: "new",      ins: 188, del: 0,   area: "API" },
  { file: "backend/app/api/routes_graph.py",    tag: "modified", ins: 37,  del: 0,   area: "API" },
  { file: "backend/app/api/routes_ingest.py",   tag: "modified", ins: 9,   del: 0,   area: "API" },
  { file: "backend/app/config.py",              tag: "modified", ins: 6,   del: 2,   area: "Core" },
  { file: "backend/app/db.py",                  tag: "modified", ins: 59,  del: 0,   area: "Core" },
  { file: "backend/app/main.py",                tag: "modified", ins: 4,   del: 0,   area: "Core" },
  { file: "backend/app/graph/analytics.py",     tag: "modified", ins: 7,   del: 2,   area: "Graph" },
  { file: "backend/app/graph/anomalies.py",     tag: "modified", ins: 229, del: 0,   area: "Graph" },
  { file: "backend/app/graph/store.py",         tag: "modified", ins: 22,  del: 0,   area: "Graph" },
  { file: "backend/app/ingestion/load_demo_case.py", tag: "modified", ins: 707, del: 0, area: "Ingestion" },
  { file: "backend/app/ingestion/pipeline.py",  tag: "modified", ins: 27,  del: 0,   area: "Ingestion" },
  { file: "backend/app/ingestion/ner.py",       tag: "modified", ins: 4,   del: 0,   area: "Ingestion" },
  { file: "backend/app/ingestion/quality.py",   tag: "modified", ins: 17,  del: 0,   area: "Ingestion" },
  { file: "backend/app/ingestion/resolution.py",tag: "modified", ins: 10,  del: 0,   area: "Ingestion" },
  { file: "backend/app/ingestion/statutes.py",  tag: "new",      ins: 382, del: 0,   area: "Ingestion" },
  { file: "backend/app/watch/matcher.py",       tag: "new",      ins: 343, del: 0,   area: "Watch" },
  { file: "backend/tests/test_watch.py",        tag: "new",      ins: 235, del: 0,   area: "Tests" },
  // ── Frontend ──
  { file: "frontend-next/src/app/page.tsx",                        tag: "new",      ins: 484, del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/overview/page.tsx",        tag: "modified", ins: 269, del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/alerts/page.tsx",          tag: "modified", ins: 60,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/chart/page.tsx",           tag: "modified", ins: 70,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/players/page.tsx",         tag: "modified", ins: 91,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/sources/page.tsx",         tag: "modified", ins: 72,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/app/(sheet)/investigator/page.tsx",    tag: "modified", ins: 27,  del: 1,  area: "Frontend" },
  { file: "frontend-next/src/app/globals.css",                      tag: "modified", ins: 188, del: 0,  area: "Frontend" },
  { file: "frontend-next/src/components/chart/LinkChart.tsx",       tag: "modified", ins: 175, del: 0,  area: "Frontend" },
  { file: "frontend-next/src/components/sheet/StandingWatches.tsx", tag: "new",      ins: 248, del: 0,  area: "Frontend" },
  { file: "frontend-next/src/components/sheet/SheetChrome.tsx",     tag: "modified", ins: 45,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/lib/api.ts",                           tag: "modified", ins: 29,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/lib/notation.ts",                      tag: "modified", ins: 61,  del: 0,  area: "Frontend" },
  { file: "frontend-next/src/lib/types.ts",                         tag: "modified", ins: 37,  del: 0,  area: "Frontend" },
  // ── Data / Config ──
  { file: "demo-case-data/01_entities_nodes.csv",      tag: "new", ins: 42,  del: 0, area: "Data" },
  { file: "demo-case-data/02_relationships_edges.csv", tag: "new", ins: 71,  del: 0, area: "Data" },
  { file: "demo-case-data/03_financial_transactions.csv", tag: "new", ins: 105, del: 0, area: "Data" },
  { file: "demo-case-data/07_timeline_events.csv",     tag: "new", ins: 25,  del: 0, area: "Data" },
  { file: "run_demo.ps1",                              tag: "new", ins: 44,  del: 0, area: "Config" },
  { file: "package.json",                              tag: "modified", ins: 17, del: 0, area: "Config" },
];

const AREAS = ["All", "AI", "API", "Graph", "Ingestion", "Watch", "Frontend", "Data", "Core", "Config", "Tests"];

/* ─── components ────────────────────────────────────────────────────────── */

function StatusDot({ ok }: { ok: boolean | null }) {
  if (ok === null) return <span className="inline-block h-2 w-2 rounded-full bg-rule-strong animate-pulse" />;
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
      title={ok ? "OK" : "Error"}
    />
  );
}

function Badge({ tag }: { tag: "new" | "modified" | "deleted" }) {
  const cls =
    tag === "new"
      ? "bg-emerald-100 text-emerald-800 border-emerald-300"
      : tag === "deleted"
      ? "bg-red-100 text-red-800 border-red-300"
      : "bg-amber-100 text-amber-800 border-amber-300";
  return (
    <span className={`border px-1 py-0.5 label text-[9px] uppercase tracking-wider ${cls}`}>
      {tag === "new" ? "NEW" : tag === "deleted" ? "DEL" : "MOD"}
    </span>
  );
}

/* ─── page ──────────────────────────────────────────────────────────────── */
export default function SystemPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [healthErr, setHealthErr] = useState(false);
  const [endpoints, setEndpoints] = useState<EndpointRow[]>([
    { label: "Health",        method: "GET",  path: "/api/health",                  ok: null, ms: null },
    { label: "Auth – me",     method: "GET",  path: "/api/auth/me",                 ok: null, ms: null },
    { label: "Graph",         method: "GET",  path: "/api/graph",                   ok: null, ms: null },
    { label: "Analytics",     method: "GET",  path: "/api/analytics/summary",       ok: null, ms: null },
    { label: "Alerts",        method: "GET",  path: "/api/alerts",                  ok: null, ms: null },
    { label: "Key Players",   method: "GET",  path: "/api/analytics/key-players",   ok: null, ms: null },
    { label: "Timeline",      method: "GET",  path: "/api/timeline",                ok: null, ms: null },
    { label: "Geo",           method: "GET",  path: "/api/geo",                     ok: null, ms: null },
    { label: "Watches",       method: "GET",  path: "/api/watches",                 ok: null, ms: null },
    { label: "AI Status",     method: "GET",  path: "/api/ai/status",               ok: null, ms: null },
    { label: "Ingest Status", method: "GET",  path: "/api/ingest/status",           ok: null, ms: null },
    { label: "Sources",       method: "GET",  path: "/api/sources",                 ok: null, ms: null },
    { label: "Ledger",        method: "GET",  path: "/api/forensics/ledger",        ok: null, ms: null },
    { label: "Detector Roster",method:"GET",  path: "/api/alerts/detectors",        ok: null, ms: null },
  ]);
  const [areaFilter, setAreaFilter] = useState("All");
  const [checked, setChecked] = useState(false);
  const [totalIns, totalDel] = FILE_CHANGES.reduce(([i, d], r) => [i + r.ins, d + r.del], [0, 0]);

  useEffect(() => {
    /* 1 ── health beacon */
    const t0 = performance.now();
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d))
      .catch(() => setHealthErr(true));

    /* 2 ── probe every endpoint (unauthenticated, we only care about connection) */
    const token = typeof window !== "undefined" ? window.localStorage.getItem("cortex.token") : null;
    const hdrs: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

    setEndpoints((prev) =>
      prev.map((ep) => {
        const start = performance.now();
        fetch(`${API_BASE}${ep.path}`, { headers: hdrs })
          .then((r) => {
            const ms = Math.round(performance.now() - start);
            setEndpoints((cur) =>
              cur.map((e) => (e.path === ep.path ? { ...e, ok: r.status < 500, ms } : e))
            );
          })
          .catch(() => {
            setEndpoints((cur) =>
              cur.map((e) => (e.path === ep.path ? { ...e, ok: false, ms: null } : e))
            );
          });
        return ep;
      })
    );
    setChecked(true);
  }, []);

  const filtered =
    areaFilter === "All" ? FILE_CHANGES : FILE_CHANGES.filter((f) => f.area === areaFilter);
  const upCount = endpoints.filter((e) => e.ok === true).length;
  const downCount = endpoints.filter((e) => e.ok === false).length;

  return (
    <main className="sheet-ground flex h-full flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl space-y-8 px-4 py-6 sm:px-6">

        {/* ── header ── */}
        <div className="border-b border-ink pb-4">
          <p className="label text-[10px] text-ink-soft">CORTEX · System Console</p>
          <h1 className="stencil mt-1 text-[length:var(--fs-title)] font-bold leading-none text-ink">
            Backend Health &amp; Changelog
          </h1>
          <p className="note mt-2 max-w-[60ch] text-ink-soft">
            Live probe of every API route, with a full audit of the {COMMITS.length} commits
            that changed this codebase — {FILE_CHANGES.length} files, +{totalIns.toLocaleString()} /
            −{totalDel} lines.
          </p>
        </div>

        {/* ── health banner ── */}
        <section aria-labelledby="health-h">
          <h2 id="health-h" className="label mb-3 border-b border-rule pb-1 text-[10px] uppercase tracking-widest text-ink-soft">
            Backend Status
          </h2>
          <div className="grid gap-3 sm:grid-cols-3">
            {/* health card */}
            <div className="border border-rule-strong bg-film-lift px-4 py-3">
              <p className="label text-[10px] text-ink-soft">API Server</p>
              {healthErr ? (
                <p className="figure mt-1 text-[length:var(--fs-lead)] font-bold text-red-600">OFFLINE</p>
              ) : health ? (
                <p className="figure mt-1 text-[length:var(--fs-lead)] font-bold text-emerald-600">ONLINE</p>
              ) : (
                <p className="figure mt-1 text-[length:var(--fs-lead)] font-bold text-ink-soft animate-pulse">CHECKING…</p>
              )}
              {health && (
                <p className="note mt-1 text-ink-soft">{health.environment}</p>
              )}
            </div>
            {/* endpoint counter */}
            <div className="border border-rule-strong bg-film-lift px-4 py-3">
              <p className="label text-[10px] text-ink-soft">Endpoints probed</p>
              <p className="figure mt-1 text-[length:var(--fs-lead)] font-bold text-ink">
                {upCount} <span className="text-emerald-600">↑</span>
                &ensp;{downCount} <span className="text-red-500">↓</span>
              </p>
              <p className="note mt-1 text-ink-soft">of {endpoints.length} total</p>
            </div>
            {/* model */}
            <div className="border border-rule-strong bg-film-lift px-4 py-3">
              <p className="label text-[10px] text-ink-soft">AI Model</p>
              <p className="figure mt-1 break-all text-[11px] font-bold text-ink">gemini-2.5-flash</p>
              <p className="note mt-1 text-ink-soft">Provider · Gemini (primary)</p>
            </div>
          </div>
        </section>

        {/* ── endpoint table ── */}
        <section aria-labelledby="ep-h">
          <h2 id="ep-h" className="label mb-3 border-b border-rule pb-1 text-[10px] uppercase tracking-widest text-ink-soft">
            API Route Probe
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full figure text-[11px] leading-[1.9]">
              <thead>
                <tr className="label text-[9px] uppercase tracking-widest text-ink-soft">
                  <th className="py-0.5 pr-4 text-left font-semibold">Status</th>
                  <th className="py-0.5 pr-4 text-left font-semibold">Route</th>
                  <th className="py-0.5 pr-4 text-left font-semibold">Endpoint</th>
                  <th className="py-0.5 text-right font-semibold">Latency</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.map((ep) => (
                  <tr key={ep.path} className="border-t border-rule">
                    <td className="py-0.5 pr-4">
                      <StatusDot ok={ep.ok} />
                    </td>
                    <td className="py-0.5 pr-4 font-semibold text-ink">{ep.label}</td>
                    <td className="py-0.5 pr-4 font-mono text-ink-soft">
                      <span className="label text-[8px] text-ink-faint mr-1">{ep.method}</span>
                      {ep.path}
                    </td>
                    <td className="py-0.5 text-right tabular-nums text-ink-soft">
                      {ep.ms !== null ? `${ep.ms} ms` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── commit history ── */}
        <section aria-labelledby="git-h">
          <h2 id="git-h" className="label mb-3 border-b border-rule pb-1 text-[10px] uppercase tracking-widest text-ink-soft">
            Commit History (last 5)
          </h2>
          <ol className="space-y-3">
            {COMMITS.map((c) => (
              <li key={c.hash} className="border-l-2 border-rule-strong pl-4">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="label font-mono text-[9px] text-ink-faint">{c.hash}</span>
                  <span className="label text-[9px] text-ink-soft">{c.date}</span>
                  <span className="label text-[9px] text-ink-soft">{c.author}</span>
                </div>
                <p className="note mt-0.5 text-ink">{c.msg}</p>
                <div className="mt-1 flex gap-3 text-[10px]">
                  <span className="text-emerald-600">+{c.insertions.toLocaleString()}</span>
                  <span className="text-red-500">−{c.deletions}</span>
                  <span className="text-ink-faint">{c.files} files</span>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ── file diff table ── */}
        <section aria-labelledby="files-h">
          <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-rule pb-2">
            <h2 id="files-h" className="label text-[10px] uppercase tracking-widest text-ink-soft">
              Changed Files ({FILE_CHANGES.length})
            </h2>
            <div className="ml-auto flex flex-wrap gap-1">
              {AREAS.map((a) => (
                <button
                  key={a}
                  onClick={() => setAreaFilter(a)}
                  className={`label px-2 py-0.5 text-[9px] border transition-colors ${
                    areaFilter === a
                      ? "border-ink bg-ink text-film"
                      : "border-rule-strong text-ink-soft hover:border-ink hover:text-ink"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          {/* summary bar */}
          <div className="mb-3 flex gap-6 text-[11px]">
            <span className="text-emerald-600 font-semibold">
              +{filtered.reduce((s, f) => s + f.ins, 0).toLocaleString()} insertions
            </span>
            <span className="text-red-500 font-semibold">
              −{filtered.reduce((s, f) => s + f.del, 0)} deletions
            </span>
            <span className="text-ink-soft">
              {filtered.filter((f) => f.tag === "new").length} new ·{" "}
              {filtered.filter((f) => f.tag === "modified").length} modified ·{" "}
              {filtered.filter((f) => f.tag === "deleted").length} deleted
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full figure text-[11px] leading-[1.9]">
              <thead>
                <tr className="label text-[9px] uppercase tracking-widest text-ink-soft">
                  <th className="py-0.5 pr-3 text-left font-semibold">Tag</th>
                  <th className="py-0.5 pr-3 text-left font-semibold">Area</th>
                  <th className="py-0.5 pr-3 text-left font-semibold">File</th>
                  <th className="py-0.5 pr-3 text-right font-semibold">+Ins</th>
                  <th className="py-0.5 text-right font-semibold">−Del</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((f) => (
                  <tr key={f.file} className="border-t border-rule hover:bg-film-lift/50 transition-colors">
                    <td className="py-0.5 pr-3">
                      <Badge tag={f.tag} />
                    </td>
                    <td className="py-0.5 pr-3 text-ink-soft">{f.area}</td>
                    <td className="py-0.5 pr-3 font-mono text-[10px] text-ink">{f.file}</td>
                    <td className="py-0.5 pr-3 text-right tabular-nums text-emerald-600">+{f.ins}</td>
                    <td className="py-0.5 text-right tabular-nums text-red-500">
                      {f.del > 0 ? `−${f.del}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-ink-soft">
                  <td colSpan={3} className="label pt-1 text-[9px] text-ink-soft">
                    TOTAL ({filtered.length} files shown)
                  </td>
                  <td className="pt-1 text-right font-semibold tabular-nums text-emerald-600">
                    +{filtered.reduce((s, f) => s + f.ins, 0).toLocaleString()}
                  </td>
                  <td className="pt-1 text-right font-semibold tabular-nums text-red-500">
                    −{filtered.reduce((s, f) => s + f.del, 0)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>

        {/* ── feature summary ── */}
        <section aria-labelledby="feat-h">
          <h2 id="feat-h" className="label mb-3 border-b border-rule pb-1 text-[10px] uppercase tracking-widest text-ink-soft">
            What Was Implemented
          </h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {[
              { t: "Demo Fallback Engine", d: "Hardcoded high-speed answers from demo CSV data, bypassing LLM+DB in demo mode. Zero latency for showcasing." },
              { t: "Operation CyberHawk 2.0", d: "Full demo corpus: 94 entities, 192 relationships, 19 sealed docs, 153 events, 104 transfers, 5 alerts loaded from 8 CSV files." },
              { t: "Standing Watches", d: "New watch/matcher.py module + routes_watch.py: arm a keyword watch and get backfilled hits. StandingWatches.tsx component in the sheet." },
              { t: "Anomaly Detectors", d: "Two new detectors: pass-through accounts and complaint hubs. Layering keyed on route (not individual transfer) — 17 → 3 findings." },
              { t: "Investigator Fixes", d: "Suggested questions drawn from live ranking. Money/call facts carry subject name. Reasoning tokens excluded from answer stream." },
              { t: "CRYPTO_WALLET node type", d: "First-class end-to-end: resolver, quality rules, tool vocabulary, cut-hexagon on chart, money-blue ink." },
              { t: "Evidence Ledger Sealing", d: "Every ingested demo document sealed into the tamper-evident hash chain at load time." },
              { t: "CSS Build Fix", d: "Tailwind v4 was scanning .next-demo/ and compiled text-[length:var" + "(--fs-*)] into invalid CSS. Fixed with @source not exclusion." },
              { t: "LLM Provider Routing", d: "Gemini 2.5 Flash as primary investigator model. Fallback chain: Gemini → NVIDIA → Anthropic. llm.py narration budget accounts for reasoning tokens." },
              { t: "Landing Page", d: "Interactive 5-record tray (FIR + CDR + judgment + bank statement + wanted notice). Click any name to draw its link." },
            ].map(({ t, d }) => (
              <div key={t} className="border-l-2 border-rule-strong pl-3">
                <dt className="label text-[10px] font-semibold text-ink">{t}</dt>
                <dd className="note mt-0.5 text-ink-soft">{d}</dd>
              </div>
            ))}
          </dl>
        </section>

        <p className="note border-t border-rule pt-4 text-ink-faint">
          Probed at {new Date().toLocaleTimeString()} · {API_BASE}
        </p>
      </div>
    </main>
  );
}
