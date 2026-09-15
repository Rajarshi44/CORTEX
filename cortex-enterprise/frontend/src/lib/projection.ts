import type { EdgeView, NodeView } from "./types";
import type { api } from "./api";

type Projection = Awaited<ReturnType<typeof api.projection>>;

const CHANNEL_REL: Record<string, string> = {
  calls: "CALLED", transfers: "TRANSFERRED_TO", meetings: "MET", met: "MET", shared_case: "CO_ACCUSED", co_accused: "CO_ACCUSED",
  reports_to: "REPORTS_TO", communicated_with: "COMMUNICATED_WITH", mentioned_with: "MENTIONED_WITH", social: "MENTIONED",
  owns: "OWNS", director_of: "DIRECTOR_OF", affiliated_with: "AFFILIATED_WITH", associate_of: "ASSOCIATE_OF", shared_handset: "SHARED_HANDSET",
};
const STRUCTURED = new Set(["calls", "transfers", "meetings", "met", "shared_handset", "co_accused", "shared_case"]);

/** Keep the largest connected components until roughly `maxNodes` entities are on the sheet. */
export function largestComponents(nodes: NodeView[], edges: EdgeView[], maxNodes = 120): { nodes: NodeView[]; edges: EdgeView[] } {
  const parent = new Map<string, string>();
  const find = (a: string): string => { let r = a; while (parent.get(r) !== r) r = parent.get(r)!; parent.set(a, r); return r; };
  for (const n of nodes) parent.set(n.id, n.id);
  for (const e of edges) if (parent.has(e.source) && parent.has(e.target)) parent.set(find(e.source), find(e.target));
  const size = new Map<string, number>();
  for (const n of nodes) { const r = find(n.id); size.set(r, (size.get(r) ?? 0) + 1); }
  const order = [...size.entries()].sort((a, b) => b[1] - a[1]);
  const keep = new Set<string>(); let total = 0;
  for (const [root, s] of order) { if (total && total + s > maxNodes) continue; keep.add(root); total += s; if (total >= maxNodes) break; }
  const ns = nodes.filter((n) => keep.has(find(n.id)));
  const ids = new Set(ns.map((n) => n.id));
  return { nodes: ns, edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
}

/** Turn the actor projection (people and organisations, channel-weighted links) into chart nodes and edges. */
export function projectionToChart(p: Projection | undefined): { nodes: NodeView[]; edges: EdgeView[] } {
  if (!p) return { nodes: [], edges: [] };
  const edges: EdgeView[] = p.edges.map((e) => {
    const channels = e.channels ?? {};
    const dominant = Object.entries(channels).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "associate_of";
    const count = Object.values(channels).reduce((s, v) => s + v, 0) || 1;
    return {
      id: `${e.source}|${e.target}`, source: e.source, target: e.target,
      rel_type: CHANNEL_REL[dominant] ?? "ASSOCIATE_OF", weight: e.weight, count,
      attrs: { channels, calls: e.calls, night_calls: e.night_calls, amount: e.amount, meetings: e.meetings, cases: e.cases, extractor: STRUCTURED.has(dominant) ? "structured" : "rules" },
      confidence: STRUCTURED.has(dominant) ? 1 : 0.8, first_seen: null, last_seen: null, verb: dominant,
    };
  });
  return { nodes: p.nodes, edges };
}
