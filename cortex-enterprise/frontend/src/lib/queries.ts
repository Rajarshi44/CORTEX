"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AlertStatus, HitStatus, Severity, WatchKind, ReviewStatus } from "./types";

export const qk = {
  me: ["me"] as const,
  summary: ["summary"] as const,
  graph: (p: unknown) => ["graph", p] as const,
  entity: (id: string) => ["entity", id] as const,
  ego: (id: string, d: number) => ["ego", id, d] as const,
  keyPlayers: ["keyPlayers"] as const,
  communities: ["communities"] as const,
  linkPred: ["linkPred"] as const,
  alerts: (p: unknown) => ["alerts", p] as const,
  timeline: (p: unknown) => ["timeline", p] as const,
  histogram: ["histogram"] as const,
  geo: ["geo"] as const,
  ingest: ["ingest"] as const,
  sources: ["sources"] as const,
  sourcesHealth: ["sourcesHealth"] as const,
  ai: ["ai"] as const,
  ledger: ["ledger"] as const,
  linkage: (t: number) => ["linkage", t] as const,
  documents: (p: unknown) => ["documents", p] as const,
  document: (id: string) => ["document", id] as const,
  path: (a: string, b: string) => ["path", a, b] as const,
  watches: ["watches"] as const,
  watchKinds: ["watchKinds"] as const,
  watchHits: (p: unknown) => ["watchHits", p] as const,
  novelty: ["novelty"] as const,
};

export const useMe = () => useQuery({ queryKey: qk.me, queryFn: api.me, retry: false });
export const useSummary = () => useQuery({ queryKey: qk.summary, queryFn: api.summary });
export const useGraph = (p: Parameters<typeof api.graph>[0]) => useQuery({ queryKey: qk.graph(p), queryFn: () => api.graph(p), staleTime: 120_000 });
export const useEntity = (id: string | null) => useQuery({ queryKey: qk.entity(id ?? ""), queryFn: () => api.entity(id!), enabled: !!id });
export const useEgo = (id: string | null, depth = 1) => useQuery({ queryKey: qk.ego(id ?? "", depth), queryFn: () => api.ego(id!, depth), enabled: !!id });
export const useKeyPlayers = () => useQuery({ queryKey: qk.keyPlayers, queryFn: api.keyPlayers });
export const useCommunities = () => useQuery({ queryKey: qk.communities, queryFn: api.communities });
export const useLinkPredictions = () => useQuery({ queryKey: qk.linkPred, queryFn: api.linkPredictions });
export const useAlerts = (p: Parameters<typeof api.alerts>[0] = {}) => useQuery({ queryKey: qk.alerts(p), queryFn: () => api.alerts(p) });
export const useDetectors = () => useQuery({ queryKey: ["detectors"], queryFn: () => api.detectors(), staleTime: 60_000 });
export const useTimeline = (p: Parameters<typeof api.timeline>[0] = {}) => useQuery({ queryKey: qk.timeline(p), queryFn: () => api.timeline(p) });
export const useHistogram = () => useQuery({ queryKey: qk.histogram, queryFn: () => api.histogram("day", true) });
export const useGeo = () => useQuery({ queryKey: qk.geo, queryFn: api.geo });
export const useIngestStatus = (poll = false) => useQuery({ queryKey: qk.ingest, queryFn: api.ingestStatus, refetchInterval: poll ? 2000 : false });
export const useSources = () => useQuery({ queryKey: qk.sources, queryFn: api.sources });
export const useSourcesHealth = () => useQuery({ queryKey: qk.sourcesHealth, queryFn: () => api.sourcesHealth(), staleTime: 300_000 });
export const useAiStatus = () => useQuery({ queryKey: qk.ai, queryFn: api.aiStatus, staleTime: 300_000 });
export const useLedger = () => useQuery({ queryKey: qk.ledger, queryFn: async () => ({ verify: await api.ledgerVerify(), entries: await api.ledger(40) }) });
export const useLinkage = (threshold = 0.55) => useQuery({ queryKey: qk.linkage(threshold), queryFn: () => api.linkage(threshold) });
export const useDocuments = (p: Parameters<typeof api.documents>[0] = {}) => useQuery({ queryKey: qk.documents(p), queryFn: () => api.documents(p) });
export const useDocument = (id: string | null) => useQuery({ queryKey: qk.document(id ?? ""), queryFn: () => api.document(id!), enabled: !!id });
export const usePath = (a: string | null, b: string | null) => useQuery({ queryKey: qk.path(a ?? "", b ?? ""), queryFn: () => api.path(a!, b!), enabled: !!a && !!b });

export function useAlertStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, review_status }: { id: string; status?: AlertStatus; review_status?: ReviewStatus }) => api.patchAlert(id, status, review_status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["alerts"] }); qc.invalidateQueries({ queryKey: ["entity"] }); },
  });
}

// ----------------------------------------------------------------- standing watches
export const useWatches = () => useQuery({ queryKey: qk.watches, queryFn: () => api.watches() });
export const useWatchKinds = () => useQuery({ queryKey: qk.watchKinds, queryFn: api.watchKinds, staleTime: 600_000 });
export const useWatchHits = (p: Parameters<typeof api.watchHits>[0] = {}) =>
  useQuery({ queryKey: qk.watchHits(p), queryFn: () => api.watchHits(p) });

/** Every watch mutation moves both lists: the register of hits and the counter on the watch. */
function useWatchMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation<R, Error, V>({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watches"] });
      qc.invalidateQueries({ queryKey: ["watchHits"] });
    },
  });
}

export const useCreateWatch = () =>
  useWatchMutation(({ kind, value, reason, severity }: { kind: WatchKind; value: string; reason?: string; severity?: Severity }) =>
    api.createWatch(kind, value, reason, severity));
export const useDeleteWatch = () => useWatchMutation((id: string) => api.deleteWatch(id));
export const useRescanWatch = () => useWatchMutation((id: string) => api.rescanWatch(id));
export const useToggleWatch = () =>
  useWatchMutation(({ id, active }: { id: string; active: boolean }) => api.patchWatch(id, { active }));
export const useWatchHitStatus = () =>
  useWatchMutation(({ id, status }: { id: number; status: HitStatus }) => api.patchWatchHit(id, status));

/** After any ingestion the whole sheet is stale. */
export function useInvalidateSheet() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export function useAddNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, text }: { entityId: string; text: string }) => api.addNote(entityId, text),
    onSuccess: (_, { entityId }) => {
      qc.invalidateQueries({ queryKey: qk.entity(entityId) });
    },
  });
}

export function useUpdateNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, noteId, text }: { entityId: string; noteId: number; text: string }) => api.updateNote(entityId, noteId, text),
    onSuccess: (_, { entityId }) => qc.invalidateQueries({ queryKey: qk.entity(entityId) }),
  });
}

export function useDeleteNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, noteId }: { entityId: string; noteId: number }) => api.deleteNote(entityId, noteId),
    onSuccess: (_, { entityId }) => qc.invalidateQueries({ queryKey: qk.entity(entityId) }),
  });
}

// ----------------------------------------------------------------- novel intelligence
export const useNovelty = () => useQuery({ queryKey: qk.novelty, queryFn: () => api.noveltySummary(), staleTime: 120_000 });
