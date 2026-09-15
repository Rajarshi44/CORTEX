// Types mirror the FastAPI responses in backend/app/api/*. Keep names identical to the JSON.

export type EntityType =
  | "PERSON" | "PHONE" | "LOCATION" | "VEHICLE" | "ORGANIZATION" | "BANK_ACCOUNT" | "CRYPTO_WALLET"
  | "CASE" | "REPORT" | "SOCIAL_HANDLE" | "GOV_ID";

export type Extractor = "structured" | "checksum" | "rules" | "gliner" | "llm";

export type Severity = "critical" | "high" | "medium" | "low";
export type AlertStatus = "new" | "reviewing" | "dismissed" | "confirmed" | "open";
export type ReviewStatus = "pending" | "reviewed" | "escalated";

export interface User { username: string; role: "admin" | "analyst" | "viewer"; full_name: string }

/** One detector on the roster, and whether it has anything to say about this sheet. */
export interface Detector {
  name: string; kinds: string[]; needs: string; looks_for: string; alerts: number; fired: boolean;
  /** how many records of the kind it reads this sheet actually holds */
  records_held: number; records_unit: string;
  /** fired: found something. silent: read real records, found nothing. starved: nothing to read. */
  state: "fired" | "silent" | "starved";
}
export interface DetectorRoster { detectors: Detector[]; total: number; fired: number; silent: number; starved: number; alerts: number }

export interface NodeView {
  id: string; type: EntityType; label: string; aliases: string[];
  attrs: Record<string, unknown>; mentions: number;
  first_seen: string | null; last_seen: string | null;
  community: number | null; role: string | null; role_reasons: string[];
  influence: number; priority: number;  suspicion: number;
  suspicion_reasons: string[];
  pending_review?: boolean;
  degree: number; pagerank: number;
  metrics: Partial<Record<"degree" | "weighted_degree" | "betweenness" | "pagerank" | "eigenvector" | "closeness" | "clustering" | "influence", number>>;
}

export interface EdgeView {
  id: string; source: string; target: string; rel_type: string; weight: number; count: number;
  attrs: Record<string, unknown>; confidence: number; first_seen: string | null; last_seen: string | null; verb: string;
}

export interface GraphPayload { nodes: NodeView[]; edges: EdgeView[]; meta?: { total_nodes: number; total_edges: number; returned: number; computed_at?: string } }

export interface PathHop { from: { id: string; label: string; type: EntityType }; to: { id: string; label: string; type: EntityType }; rel_type: string; verb: string; count: number; attrs: Record<string, unknown> }

export interface SheetIdentity { title: string; code: string; kind: "real" | "mixed" | "demo" | "empty"; sources: string[]; subtitle: string }

export interface Summary {
  nodes: number; edges: number; actors: number; actor_edges: number; density: number; components: number;
  avg_clustering: number; communities: number; suspicious_communities: number;
  node_types: Record<string, number>; relationship_types: Record<string, number>; persons_of_interest: number;
  compute_backend?: { engine: string; betweenness_method: string };
}

export interface KeyPlayer extends Record<string, unknown> {
  id: string; label: string; type: EntityType; aliases: string[]; community: number | null; role: string | null;
  priority: number; suspicion: number; reasons: string[]; influence: number; degree: number; betweenness: number; pagerank: number; eigenvector: number;
}

export interface Broker { id: string; label: string; betweenness: number; community_span: number; bridges: { community: number; contacts: number }[]; score: number }

export interface RemovalImpact { node: string; label: string; global_fragmentation: number; components_before: number; components_after: number; community_fragmentation?: number; community_components_after?: number; isolated_after?: { id: string; label: string }[]; flow_share?: number }

export interface Community {
  id: number; size: number; label: string; leader: string; members: string[];
  top_members: { id: string; label: string; role: string | null; priority: number }[];
  locations: string[]; accused_count: number; internal_edges: number; density: number; risk: number; suspicious: boolean;
}

export interface LinkPrediction { source: string; target: string; source_label: string; target_label: string; score: number; raw_score: number; jaccard: number; common_neighbors: string[]; explanation: string }

export interface Alert {
  id: string;
  kind: string;
  severity: Severity;
  title: string;
  description: string;
  score: number;
  status: AlertStatus;
  review_status: ReviewStatus;
  reviewed_by: string | null;
  evidence: Record<string, unknown>;
  created_at: string;
  entities: { id: string; label: string; type: EntityType }[];
}

/**
 * A standing watch and the records that matched it.
 *
 * Held apart from `Alert` on purpose. An alert is an inference the detectors redraw on every
 * recompute; a hit is a fact about one document that arrived, and it outlives any recompute.
 */
export type WatchKind = "PERSON" | "ORGANIZATION" | "PHONE" | "VEHICLE" | "BANK_ACCOUNT" | "GOV_ID" | "TEXT";
export type HitStatus = "new" | "reviewing" | "dismissed" | "confirmed";

export interface Watch {
  id: string; kind: WatchKind; selector: string; reason: string; severity: Severity;
  active: boolean; created_by: string; created_at: string;
  last_hit_at: string | null; hit_count: number; new_hits: number;
}

export interface WatchHit {
  id: number; watch_id: string; status: HitStatus; matched_on: string; snippet: string;
  created_at: string; occurred_at: string | null;
  watch: { kind: WatchKind; selector: string; reason: string; severity: Severity } | null;
  document: { id: string; title: string; source_type: string } | null;
  entity: { id: string; label: string; type: EntityType; record_role: string | null; non_subject: boolean } | null;
}

/**
 * Where a row came from. The API resolves these (backend/app/ingestion/provenance.py);
 * they are optional here so a panel still renders against an older build, falling back to
 * `lib/provenance.ts`. A `source_url` of null means: real source, no public page to open.
 */
export interface Provenance { source_name?: string; source_url?: string | null; source_type?: string }

export interface Evidence extends Provenance { snippet: string; confidence: number; at: string | null; extractor: Extractor; document_id: string; document_title: string; source_type: string }

export interface DossierDocument extends Provenance { id: string; title: string; source_type: string; occurred_at?: string | null }

export interface TimelineEvent { id: number; kind: string; at: string; summary: string; details: Record<string, unknown>; lat: number | null; lon: number | null; entity_ids: string[]; document_id: string; actors?: { id: string; label: string }[] }

export interface Dossier {
  entity: NodeView;
  relationships: Record<string, { direction: "in" | "out"; other: NodeView; count: number; weight: number; attrs: Record<string, unknown>; first_seen: string | null; last_seen: string | null; confidence: number }[]>;
  associates: { other: NodeView; weight: number; channels: Record<string, number>; calls: number; night_calls: number; amount: number; meetings: number; cases: number }[];
  evidence: (Evidence & { document_title: string })[];
  alerts: { id: string; kind: string; severity: Severity; title: string; score: number; status: AlertStatus; review_status: ReviewStatus }[];
  timeline: TimelineEvent[];
  activity: [string, number][];
  removal_impact: RemovalImpact | null;
  documents: DossierDocument[];
  money?: { accounts: string[]; total_in: number; total_out: number; top_sources: [string, number][]; top_destinations: [string, number][]; transactions: { at: string; dir: "in" | "out"; counterparty: string; amount: number; mode: string; remarks: string }[] };
  calls?: { phones: string[]; total_calls: number; night_ratio: number; top_contacts: { phone: string; owner: string | null; owner_id: string | null; calls: number }[]; by_hour: number[] };
  notes?: Note[];
}

export interface Note { id: number; username: string; text: string; created_at: string; }

export interface AssistantAnswer { question: string; intent: string; answer: string; fallback_answer: string; llm: boolean; highlights: { nodes: string[]; edges: string[] }; data: unknown; highlight_nodes: { id: string; label: string; type: EntityType }[] }

export interface GeoPayload {
  locations: { id: string; label: string; lat: number; lon: number; degree: number; actors: number; poi: { id: string; label: string }[]; risk: number }[];
  /** `precision` says how precisely the place is known (court / city / state / country), so the map never implies a street address. */
  events: { id: number; kind: string; at: string; summary: string; lat: number; lon: number; document_id: string; entity_ids: string[]; precision: string | null; placed_at: string | null }[];
  /** Kinds present in the data, so filters are not a hard-coded list. */
  kinds: string[];
  meta: { events: number; locations: number; events_total: number };
}

export interface IngestStatus { job: { status: string; stage: string | null; done: number; total: number; stats?: Record<string, unknown>; report?: SourceReport; error?: string; history?: unknown[] }; documents: Record<string, number>; records: Record<string, number>; entities: number; relationships: number; events: number; graph_version: number }

export interface SourceInfo { name: string; title: string; description: string; homepage: string; licence: string; attribution: string }
export interface SourceReport { name: string; status: "ok" | "cached" | "blocked" | "unavailable" | "error"; records: number; documents: number; reason: string; started_at: string; elapsed: number; details: Record<string, unknown> }

export interface AiStatus { compute: { engine: string; rustworkx_available: boolean; rustworkx_version: string | null; betweenness_method: string }; extraction_tiers: { rules: { available: boolean }; neural: { available: boolean; installed: boolean; enabled: boolean; model: string; loaded: boolean; error: string | null }; llm: { available: boolean; model: string | null } }; semantic_search: { available: boolean; model: string; indexed_passages: number } }

export interface LedgerVerify { status: "intact" | "broken" | "empty"; valid: boolean; entries: number; head?: string; broken_at?: number; reason?: string; first_sealed?: string; last_sealed?: string }

export interface LinkageReport { cases_analysed: number; candidate_links: number; candidate_series: number; cross_jurisdiction_series: number; threshold: number; disclaimer: string; series: LinkageSeries[]; links: LinkagePair[] }
export interface LinkageSeries { size: number; cohesion: number; members: { document_id: string; title: string; station: string; occurred_at: string | null }[]; common_signature: string[]; recurring_signature: string[]; stations: string[]; cross_jurisdiction: boolean; first_offence: string | null; last_offence: string | null; span_days: number | null; crime_types: string[]; assessment: string }
export interface LinkagePair { a: string; b: string; a_title: string; b_title: string; score: number; strength: "strong" | "moderate"; components: Record<string, number>; reasons: string[]; context: { distance_km: number | null; days_apart: number | null; same_station: boolean; cross_jurisdiction: boolean } }

export interface DocumentSummary { id: string; source_type: string; title: string; occurred_at: string | null; records: number; preview: string }
export interface DocumentDetail extends Omit<DocumentSummary, "preview"> { content: string; meta: Record<string, unknown>; storage?: { database: string, table: string }; entities: { id: string; label: string; type: EntityType; snippet: string; confidence: number; extractor: Extractor }[] }

/** A page of the entity table. `total` is the unpaged count, so a view can say what it is not showing. */
export type EntityPage = {
  items: NodeView[];
  total: number;
  offset: number;
  limit: number;
  returned: number;
  complete: boolean;
};
