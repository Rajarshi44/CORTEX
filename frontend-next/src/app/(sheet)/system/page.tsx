"use client";
/**
 * System Health & Changelog lens.
 * Shows live backend health, API module status, and a full diff-level audit of
 * every file changed across the last 5 commits (5 237 insertions, 438 deletions).
 */
import React, { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

/* ─── types ─────────────────────────────────────────────────────────────── */
type HealthPayload = { status: string; app: string; environment: string };
type EndpointRow = { label: string; method: string; path: string; ok: boolean | null; ms: number | null; data: any | null };

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



/* ─── page ──────────────────────────────────────────────────────────────── */
export default function SystemPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [healthErr, setHealthErr] = useState(false);
  const [endpoints, setEndpoints] = useState<EndpointRow[]>([
    { label: "Health",        method: "GET",  path: "/api/health",                  ok: null, ms: null, data: null },
    { label: "Auth – me",     method: "GET",  path: "/api/auth/me",                 ok: null, ms: null, data: null },
    { label: "Graph",         method: "GET",  path: "/api/graph",                   ok: null, ms: null, data: null },
    { label: "Analytics",     method: "GET",  path: "/api/analytics/summary",       ok: null, ms: null, data: null },
    { label: "Alerts",        method: "GET",  path: "/api/alerts",                  ok: null, ms: null, data: null },
    { label: "Key Players",   method: "GET",  path: "/api/analytics/key-players",   ok: null, ms: null, data: null },
    { label: "Timeline",      method: "GET",  path: "/api/timeline",                ok: null, ms: null, data: null },
    { label: "Geo",           method: "GET",  path: "/api/geo",                     ok: null, ms: null, data: null },
    { label: "Watches",       method: "GET",  path: "/api/watches",                 ok: null, ms: null, data: null },
    { label: "AI Status",     method: "GET",  path: "/api/ai/status",               ok: null, ms: null, data: null },
    { label: "Ingest Status", method: "GET",  path: "/api/ingest/status",           ok: null, ms: null, data: null },
    { label: "Sources",       method: "GET",  path: "/api/sources",                 ok: null, ms: null, data: null },
    { label: "Ledger",        method: "GET",  path: "/api/forensics/ledger",        ok: null, ms: null, data: null },
    { label: "Detector Roster",method:"GET",  path: "/api/alerts/detectors",        ok: null, ms: null, data: null },
  ]);
  const [checked, setChecked] = useState(false);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);

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

    const probe = () => {
      setEndpoints((prev) =>
        prev.map((ep) => {
          const start = performance.now();
          fetch(`${API_BASE}${ep.path}`, { headers: hdrs })
            .then(async (r) => {
              const ms = Math.round(performance.now() - start);
              let data = null;
              try {
                if (r.headers.get("content-type")?.includes("application/json")) {
                  data = await r.json();
                } else {
                  data = await r.text();
                }
              } catch (e) {
                 data = "Failed to parse response";
              }
              setEndpoints((cur) =>
                cur.map((e) => (e.path === ep.path ? { ...e, ok: r.status < 500, ms, data } : e))
              );
            })
            .catch(() => {
              setEndpoints((cur) =>
                cur.map((e) => (e.path === ep.path ? { ...e, ok: false, ms: null, data: "Network Error" } : e))
              );
            });
          return ep;
        })
      );
    };

    probe();
    const interval = setInterval(probe, 5000);
    setChecked(true);

    return () => clearInterval(interval);
  }, []);


  const upCount = endpoints.filter((e) => e.ok === true).length;
  const downCount = endpoints.filter((e) => e.ok === false).length;

  return (
    <main className="sheet-ground flex h-full w-full flex-col overflow-y-auto">
      <div className="w-full space-y-8 px-4 py-6 sm:px-6">

        {/* ── header ── */}
        <div className="border-b border-ink pb-4">
          <p className="label text-[10px] text-ink-soft">CORTEX · System Console</p>
          <h1 className="stencil mt-1 text-[length:var(--fs-title)] font-bold leading-none text-ink">
            Backend Health &amp; Changelog
          </h1>
          <p className="note mt-2 max-w-[60ch] text-ink-soft">
            Live probe of every API route ensuring backend connection integrity.
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
                  <React.Fragment key={ep.path}>
                    <tr onClick={() => setSelectedRoute(selectedRoute === ep.path ? null : ep.path)} className="border-t border-rule cursor-pointer hover:bg-film-lift transition-colors group">
                      <td className="py-0.5 pr-4">
                        <StatusDot ok={ep.ok} />
                      </td>
                      <td className="py-0.5 pr-4 font-semibold text-ink group-hover:text-pencil transition-colors">{ep.label}</td>
                      <td className="py-0.5 pr-4 font-mono text-ink-soft">
                        <span className="label text-[8px] text-ink-faint mr-1">{ep.method}</span>
                        {ep.path}
                      </td>
                      <td className="py-0.5 text-right tabular-nums text-ink-soft">
                        {ep.ms !== null ? `${ep.ms} ms` : "—"}
                      </td>
                    </tr>
                    {selectedRoute === ep.path && (
                      <tr className="border-0 bg-film-lift">
                        <td colSpan={4} className="p-3 border-t border-rule-strong">
                          <pre className="text-[10px] text-ink overflow-x-auto bg-film border border-rule-strong p-3 max-h-96 overflow-y-auto">
                            {typeof ep.data === "string" ? ep.data : JSON.stringify(ep.data, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>



        {/* ── documentation ── */}
        <section aria-labelledby="docs-h" className="border-t border-rule pt-6 pb-4">
          <h2 id="docs-h" className="label mb-4 text-[12px] uppercase tracking-widest text-ink font-bold flex items-center gap-2">
            <span className="bg-pencil text-film px-1.5 py-0.5 rounded-sm text-[9px]">DOCS</span> API Integration & Extensibility
          </h2>
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="bg-film-lift border border-rule-strong p-5">
              <h3 className="label text-[11px] text-pencil font-semibold mb-3">Adding New API Endpoints</h3>
              <p className="note text-ink-soft mb-3 leading-relaxed">Expand CORTEX by writing standard FastAPI routes. Test them directly in the table above by clicking the rows to inspect JSON responses.</p>
              <ol className="list-decimal pl-4 space-y-2 mt-2 text-[length:var(--fs-note)] text-ink">
                <li>
                  <strong className="text-ink font-semibold">Define the Route:</strong> In <code>backend/app/api</code>, create or edit a router (e.g. <code>routes_custom.py</code>).
                  <div className="bg-film border border-rule mt-1 p-2 font-mono text-[9px] text-ink-faint rounded-sm">
                    @router.get("/my-endpoint")<br/>
                    def my_endpoint(db: Session = Depends(get_session)):
                  </div>
                </li>
                <li>
                  <strong className="text-ink font-semibold">Register the Router:</strong> Include it in <code>backend/app/main.py</code>.
                  <div className="bg-film border border-rule mt-1 p-2 font-mono text-[9px] text-ink-faint rounded-sm">
                    app.include_router(routes_custom.router, prefix="/api/custom")
                  </div>
                </li>
                <li>
                  <strong className="text-ink font-semibold">Live Testing:</strong> Add your endpoint to the <code>endpoints</code> state in this page (<code>SystemPage.tsx</code>) to see it polled dynamically.
                </li>
              </ol>
            </div>
            
            <div className="bg-film-lift border border-rule-strong p-5">
              <h3 className="label text-[11px] text-pencil font-semibold mb-3">Connecting New Databases & Ingestion</h3>
              <p className="note text-ink-soft mb-3 leading-relaxed">Integrate external data lakes or relational databases seamlessly.</p>
              <ul className="list-disc pl-4 space-y-3 mt-2 text-[length:var(--fs-note)] text-ink">
                <li>
                  <strong className="text-ink font-semibold">Configure Connection:</strong> Set your database URI in <code>backend/app/config.py</code>. The engine uses SQLAlchemy under the hood.
                </li>
                <li>
                  <strong className="text-ink font-semibold">Define Schemas:</strong> Add your new tables in <code>backend/app/db.py</code> using mapped classes.
                </li>
                <li>
                  <strong className="text-ink font-semibold">Ingestion Pipeline:</strong> Feed raw records into the system using <code>backend/app/ingestion/pipeline.py</code>. Map them to standardized <code>Entity</code> and <code>Relationship</code> models. See <code>load_demo_case.py</code> for an example of a bulk CSV ingester.
                </li>
              </ul>
            </div>
          </div>
        </section>

        <p className="note border-t border-rule pt-4 text-ink-faint">
          Probed at {new Date().toLocaleTimeString()} · {API_BASE}
        </p>
      </div>
    </main>
  );
}
