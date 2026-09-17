import type {
  AiStatus, Alert, AlertStatus, ReviewStatus, AssistantAnswer, Community, DocumentDetail, DocumentSummary, Dossier, GeoPayload,
  DetectorRoster, EntityPage, GraphPayload, IngestStatus, KeyPlayer, Broker, LedgerVerify, LinkPrediction, LinkageReport, NodeView, PathHop,
  RemovalImpact, SourceInfo, SourceReport, Summary, TimelineEvent, User, SheetIdentity, Note,
  Severity, Watch, WatchHit, WatchKind, HitStatus,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "cortex.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try {
    if (t) window.localStorage.setItem(TOKEN_KEY, t);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}, raw = false): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !(init.body instanceof URLSearchParams) && init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      // A hard navigation on purpose, not a router push: the session is gone, so every query cache
      // and store still holding the previous user's records has to go with it. Only a full document
      // load clears them, and that guarantee is worth the repaint.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    }
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* keep */ }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res as unknown as T;
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, unknown>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // ---- auth
  login: async (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    const r = await request<{ access_token: string; user: User }>("/api/auth/login", { method: "POST", body });
    setToken(r.access_token);
    return r.user;
  },
  me: () => request<User>("/api/auth/me"),
  logout: () => setToken(null),
  audit: (limit = 200) => request<{ id: number; user: string; action: string; detail: string; at: string }[]>(`/api/auth/audit${qs({ limit })}`),

  // ---- graph
  graph: (p: { types?: string[]; community?: number; min_priority?: number; focus?: string; depth?: number; limit?: number; include_infra?: boolean } = {}) =>
    request<GraphPayload>(`/api/graph${qs(p)}`),
  projection: (p: { min_weight?: number; only_poi?: boolean } = {}) =>
    request<{ nodes: NodeView[]; edges: { source: string; target: string; weight: number; channels: Record<string, number>; calls: number; night_calls: number; amount: number; meetings: number; cases: number }[] }>(`/api/graph/projection${qs(p)}`),
  path: (src: string, dst: string, k = 3) => request<{ paths: PathHop[][]; subgraph: GraphPayload }>(`/api/graph/path${qs({ src, dst, k })}`),
  // `limit: 0` asks for every row; `total` is the unpaged count so a view can say what it is not showing.
  entities: (p: { q?: string; types?: string[]; sort?: string; limit?: number; offset?: number; roles?: string[]; exclude_roles?: boolean } = {}) =>
    request<EntityPage>(`/api/entities${qs(p)}`),
  entity: (id: string) => request<Dossier>(`/api/entities/${id}`),
  addNote: (id: string, text: string) => request<Note>(`/api/entities/${id}/notes`, { method: "POST", body: JSON.stringify({ text }) }),
  updateNote: (id: string, noteId: number, text: string) => request<Note>(`/api/entities/${id}/notes/${noteId}`, { method: "PUT", body: JSON.stringify({ text }) }),
  deleteNote: (id: string, noteId: number) => request<{ ok: boolean }>(`/api/entities/${id}/notes/${noteId}`, { method: "DELETE" }),
  ego: (id: string, depth = 1, limit = 120) => request<GraphPayload>(`/api/entities/${id}/ego${qs({ depth, limit })}`),

  // ---- analytics
  summary: () => request<{ summary: Summary; computed_at: string; alert_count: number; last_run: Record<string, unknown>; sheet?: SheetIdentity }>("/api/analytics/summary"),
  buildRealCorpus: (reset = false) => request<{ started: boolean }>("/api/sources/corpus/real", { method: "POST", body: JSON.stringify({ reset }) }),
  keyPlayers: () => request<{ key_players: KeyPlayer[]; brokers: Broker[]; removal_impact: Record<string, RemovalImpact> }>("/api/analytics/key-players"),
  communities: () => request<Community[]>("/api/analytics/communities"),
  linkPredictions: () => request<LinkPrediction[]>("/api/analytics/link-predictions"),
  impact: (id: string) => request<RemovalImpact>(`/api/analytics/impact/${id}`),
  recompute: () => request<Record<string, unknown>>("/api/analytics/recompute", { method: "POST" }),
  // `limit: 0` returns every matching event; `total` counts the matches a cap would hide.
  timeline: (p: { kinds?: string[]; entity?: string; start?: string; end?: string; limit?: number; only_poi?: boolean } = {}) =>
    request<{ items: TimelineEvent[]; total: number; returned: number; limit: number; complete: boolean }>(`/api/timeline${qs(p)}`),
  histogram: (bucket: "day" | "month" = "day", only_poi = true) => request<Record<string, number | string>[]>(`/api/timeline/histogram${qs({ bucket, only_poi })}`),
  geo: () => request<GeoPayload>("/api/geo"),

  // ---- alerts
  alerts: (p: { status?: string; kind?: string; severity?: string; entity?: string; limit?: number } = {}) => request<Alert[]>(`/api/alerts${qs(p)}`),
  patchAlert: (id: string, status?: AlertStatus, review_status?: ReviewStatus) => request<Alert>(`/api/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ status, review_status }) }),
  detectors: () => request<DetectorRoster>("/api/alerts/detectors"),

  // ---- assistant & AI
  ask: (question: string) => request<AssistantAnswer>("/api/assistant/ask", { method: "POST", body: JSON.stringify({ question }) }),
  assistantCaps: () => request<{ llm: boolean; model: string | null; examples: string[] }>("/api/assistant/capabilities"),
  aiStatus: () => request<AiStatus>("/api/ai/status"),
  semanticSearch: (query: string, limit = 10, source_type?: string) =>
    request<{ status: string; reason?: string; results: { document_id: string; source_type: string; title: string; score: number | null; snippet: string }[] }>("/api/ai/search", { method: "POST", body: JSON.stringify({ query, limit, source_type }) }),
  extractPreview: (text: string, labels?: string[], threshold?: number) =>
    request<{ rules: { entities: { type: string; text: string; confidence: number; attrs: Record<string, unknown> }[]; relations: { source: string; type: string; target: string; confidence: number }[]; sections: string[]; dates: string[] }; neural: { available: boolean; entities: { type: string; text: string; confidence: number; label: string; context?: string[] }[]; context?: { label: string; text: string; score: number }[]; rejected?: { label: string; text: string; score: number; reason: string }[]; only_found_by_transformer?: { label: string; text: string; confidence: number }[]; reason?: string } }>("/api/ai/extract/preview", { method: "POST", body: JSON.stringify({ text, labels, threshold }) }),
  computeBenchmark: () => request<Record<string, unknown>>("/api/ai/compute/benchmark"),

  // ---- forensics
  ledgerVerify: () => request<LedgerVerify>("/api/forensics/ledger/verify"),
  ledger: (limit = 60) => request<{ entries: { index: number; timestamp: string; actor: string; action: string; subject_type: string; subject_id: string; payload_hash: string; previous_hash: string; entry_hash: string; signature?: string; detail: string }[]; height: number; head_hash: string | null; merkle_root?: string; public_key?: string; by_action: Record<string, number> }>(`/api/forensics/ledger${qs({ limit })}`),
  ledgerAnchor: () => request<{ status: string; head_hash?: string; height?: number; merkle_root?: string; signature?: string; public_key?: string; timestamp?: string; sealed_at?: string; note?: string }>("/api/forensics/ledger/anchor"),
  ledgerProof: (index: number) => request<{ leaf_index: number; leaf_hash: string; root_hash: string; total_leaves: number; audit_path: { position: "left" | "right"; hash: string }[] }>(`/api/forensics/ledger/proof/${index}`),
  ledgerVerifyProof: (leaf_hash: string, proof: unknown) => request<{ valid: boolean; leaf_hash: string; root_hash: string }>("/api/forensics/ledger/verify-proof", { method: "POST", body: JSON.stringify({ leaf_hash, proof }) }),
  ledgerVerifyBrief: (hash?: string, index?: number) => request<{ status: string; valid: boolean; index?: number; payload_hash?: string; entry_hash?: string; signature?: string; signature_valid?: boolean; chain_intact?: boolean }>(`/api/forensics/ledger/verify-brief${qs({ hash, index })}`),
  verifyDocument: (id: string) => request<{ status: string; conclusion?: string; sealed_at?: string; reason?: string }>(`/api/forensics/ledger/verify-document/${id}`),
  identifiers: (text: string) => request<{ identifiers: { kind: string; value: string; valid: boolean; sensitive: boolean; attrs: Record<string, unknown> }[]; summary: { counts: Record<string, number>; valid: number; invalid: number; rejected: { kind: string; text: string; reason: string }[] } }>("/api/forensics/identifiers", { method: "POST", body: JSON.stringify({ text, include_invalid: true }) }),
  linkage: (threshold = 0.55, limit = 300) => request<LinkageReport | { status: string; cases_analysed: number; reason: string }>(`/api/forensics/linkage${qs({ threshold, limit })}`),

  // ---- ingestion & documents
  ingestStatus: () => request<IngestStatus>("/api/ingest/status"),
  ingestDemo: () => request<{ started: boolean }>("/api/ingest/demo", { method: "POST" }),
  ingestText: (source_type: string, title: string, text: string) =>
    request<{ document_id: string; stats: Record<string, unknown>; entities: { id: string; label: string; type: string }[]; alerts: number }>("/api/ingest/text", { method: "POST", body: JSON.stringify({ source_type, title, text }) }),
  upload: (source_type: string, file: File) => {
    const fd = new FormData(); fd.set("source_type", source_type); fd.set("file", file);
    return request<{ started: boolean; file: string; source_type: string }>("/api/ingest/upload", { method: "POST", body: fd });
  },
  reset: () => request<{ ok: boolean }>("/api/ingest/reset", { method: "DELETE" }),
  documents: (p: { source_type?: string; q?: string; entity_id?: string; limit?: number } = {}) => request<DocumentSummary[]>(`/api/ingest/documents${qs(p)}`),
  document: (id: string) => request<DocumentDetail>(`/api/ingest/documents/${id}`),
  tagDocument: (document_id: string, provenance: string, notes?: string) =>
    request<{ ok: boolean; id: string; provenance: string; notes?: string; tagged_by?: string; meta: Record<string, unknown> }>(
      "/api/sources/tag",
      { method: "POST", body: JSON.stringify({ document_id, provenance, notes }) }
    ),
  updateDocumentProvenance: (doc_id: string, provenance: string, notes?: string) =>
    request<{ ok: boolean; id: string; provenance: string; notes?: string; meta: Record<string, unknown> }>(
      `/api/ingest/documents/${doc_id}/provenance`,
      { method: "PUT", body: JSON.stringify({ provenance, notes }) }
    ),
  geoConfig: () =>
    request<{ city: string; center: [number, number]; default_center: [number, number]; zoom: number; coordinates: { lng: number; lat: number } }>("/api/geo/config"),

  // ---- live sources
  sources: () => request<{ sources: SourceInfo[]; cache: { entries: number; bytes: number } }>("/api/sources"),
  sourcesHealth: (name?: string) => request<SourceReport[]>(`/api/sources/health${qs({ name })}`),
  harvest: (source: string, params: Record<string, unknown> = {}, offline = false) =>
    request<{ started: boolean; source: string }>("/api/sources/harvest", { method: "POST", body: JSON.stringify({ source, params, offline }) }),
  gleifSearch: (q: string, country = "IN", limit = 12) => request<{ lei: string; name: string; status: string; country: string; city: string; registered_as: string | null }[]>(`/api/sources/gleif/search${qs({ q, country, limit })}`),
  gleifTree: (lei: string) => request<Record<string, { lei: string; name: string; country: string }[]>>(`/api/sources/gleif/${lei}/tree`),
  icijStats: () => request<Record<string, number | boolean>>("/api/sources/icij/stats"),
  newsPreview: (feed = "toi_crime") => request<{ feed: string; title: string; summary: string; link: string; published: string }[]>(`/api/sources/news/preview${qs({ feed })}`),
  benchmarkEval: (dataset: string) => request<Record<string, unknown>>(`/api/sources/benchmarks/evaluate/${dataset}`),
  screen: (threshold = 88) => request<{ status: string; screened?: number; hits: { entity: string; matched: string; score: number; topics: string[]; lists: string[] }[] }>(`/api/sources/opensanctions/screen${qs({ threshold })}`, { method: "POST" }),

  // ---- standing watches
  watches: (active?: boolean) => request<Watch[]>(`/api/watches${qs({ active })}`),
  watchKinds: () => request<{ kinds: { kind: WatchKind; help: string }[]; severities: Severity[]; statuses: HitStatus[] }>("/api/watches/kinds"),
  createWatch: (kind: WatchKind, value: string, reason = "", severity: Severity = "high") =>
    request<Watch & { created: boolean; backfill_hits: number; note: string | null }>("/api/watches", { method: "POST", body: JSON.stringify({ kind, value, reason, severity }) }),
  patchWatch: (id: string, body: { active?: boolean; severity?: Severity; reason?: string }) =>
    request<Watch>(`/api/watches/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteWatch: (id: string) => request<{ deleted: boolean }>(`/api/watches/${id}`, { method: "DELETE" }),
  rescanWatch: (id: string) => request<Watch & { new_hits: number }>(`/api/watches/${id}/rescan`, { method: "POST" }),
  watchHits: (p: { status?: string; watch_id?: string; limit?: number } = {}) => request<WatchHit[]>(`/api/watches/hits${qs(p)}`),
  patchWatchHit: (id: number, status: HitStatus) => request<WatchHit>(`/api/watches/hits/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),

  // ---- novel intelligence
  noveltySummary: (top_ghost = 15, top_fto = 20) =>
    request<{
      iceberg: { observed: number; estimated_total: number; dark_number: number; visibility_pct: number; source_sets: Record<string, number>; pairwise_estimates: { sources: string[]; n1: number; n2: number; overlap: number; estimate: number; ci_low: number; ci_high: number }[]; interpretation: string };
      ghost_nodes: { type: string; node_a: { id: string; label: string; suspicion: number }; node_b: { id: string; label: string; suspicion: number }; community: number; confidence_score: number; jaccard_similarity: number; shared_neighbors_count: number; shared_neighbors: string[]; interpretation: string }[];
      first_time_offenders: { id: string; label: string; risk_score: number; suspicion_score: number; proximity_score: number; community_risk: number; degree: number; high_risk_contacts: number; accused_contacts: number; watchlisted_contacts: number; channel_types: string[]; reasons: string[]; community: number; interpretation: string }[];
      discrepancies: { alerts: { id: string; kind: string; severity: string; title: string; description: string; score: number; entity_ids: string[]; evidence: Record<string, unknown> }[]; total: number; by_kind: Record<string, number>; critical: number; high: number };
      alerts: { id: string; kind: string; severity: string; title: string; description: string; score: number; entity_ids: string[]; evidence: Record<string, unknown> }[];
      summary: { ghost_nodes_detected: number; first_time_offenders_flagged: number; discrepancies_detected: number; estimated_dark_network_size: number; visibility_pct: number; critical_alerts: number; high_alerts: number };
    }>(`/api/novelty/summary${qs({ top_ghost, top_fto })}`),

  // ---- global search
  globalSearch: (q: string) => request<{
    entities: { id: string; type: string; label: string; risk_score: number }[];
    alerts: { id: string; kind: string; title: string; severity: string; review_status: string }[];
    documents: { id: string; source_type: string; title: string; occurred_at: string | null }[];
  }>(`/api/search${qs({ q })}`),

  // ---- reports
  reportMarkdown: async () => (await request<Response>("/api/reports/brief.md", {}, true)).text(),
  reportPdfUrl: () => `${API_BASE}/api/reports/brief.pdf`,
  downloadPdf: async () => {
    const res = await request<Response>("/api/reports/brief.pdf", {}, true);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "cortex-brief.pdf"; a.click();
    URL.revokeObjectURL(url);
  },

  wsUrl: () => `${API_BASE.replace(/^http/, "ws")}/api/ingest/ws`,
};
