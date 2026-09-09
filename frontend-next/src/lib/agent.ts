/**
 * Client for the investigator agent's newline-delimited JSON stream.
 *
 * The backend emits one JSON object per line as it plans, calls tools and writes. We hand each
 * one to a callback the moment it lands, so the analyst watches the retrieval happen instead of
 * waiting on a spinner. `fetch` rather than EventSource: the request needs a POST body and a
 * bearer token, and NDJSON needs no SSE framing.
 */
import { API_BASE, ApiError, getToken, setToken } from "./api";
import type { EntityType } from "./types";

// --------------------------------------------------------------------------- visuals
export type ChartKind = "bar" | "column" | "line" | "area" | "donut" | "scatter" | "stat" | "hourly";
export type Unit = "inr" | "count" | "percent" | "none" | string;

export interface ChartPoint { label: string; value: number; value2?: number; entity_id?: string; note?: string }
export interface ChartVisual {
  type: "chart"; kind: ChartKind; title: string; caption: string; unit: Unit;
  series_label: string; points: ChartPoint[];
}
export interface NetworkNode {
  id: string; label: string; type: EntityType; aliases?: string[]; role?: string | null;
  community?: number | null; priority: number; suspicion: number; degree: number;
}
export interface NetworkEdge {
  id: string; source: string; target: string; rel_type: string; verb: string;
  count: number; weight: number; confidence: number;
}
export interface NetworkVisual {
  type: "network"; title: string; caption: string;
  nodes: NetworkNode[]; edges: NetworkEdge[]; emphasis: string[];
}
export interface TableVisual {
  type: "table"; title: string; caption: string; columns: string[]; rows: string[][]; entity_ids: string[];
}
export interface TimelineEntry { at: string; label: string; kind: string; entity_id?: string | null; emphasis?: boolean }
export interface TimelineVisual { type: "timeline"; title: string; caption: string; events: TimelineEntry[] }

export type Visual = ChartVisual | NetworkVisual | TableVisual | TimelineVisual;

// --------------------------------------------------------------------------- events
export interface ProviderInfo { key: string; label: string; model: string; available: boolean }
export interface ToolCall {
  id: string; name: string; label: string; input: Record<string, unknown>;
  ms?: number; summary?: string; ok?: boolean; done: boolean;
}
export interface Citation { kind: "document" | "web"; id: string; title: string; source_type: string; snippet: string }
export interface HighlightNode { id: string; label: string; type: EntityType }

export type AgentEvent =
  | { type: "start"; providers: ProviderInfo[]; provider: string; model: string; tools: number }
  | { type: "step"; n: number }
  | { type: "tool_call"; id: string; name: string; input: Record<string, unknown>; label: string }
  | { type: "tool_done"; id: string; name: string; ms: number; summary: string; ok: boolean }
  | { type: "text"; delta: string }
  | { type: "visual"; visual: Visual }
  | { type: "fallback"; from: string; to: string; reason: string }
  | { type: "done"; answer: string; steps: number; seconds: number; highlight_nodes: HighlightNode[]; highlights: { nodes: string[]; edges: string[] }; visuals: Visual[]; citations: Citation[]; usage: Record<string, unknown> }
  | { type: "error"; message: string };

export interface AgentCapabilities {
  agent: boolean; llm: boolean; model: string | null;
  providers: ProviderInfo[]; provider: ProviderInfo | null;
  tools: { name: string; description: string }[];
  web_tier: string; max_steps: number; examples: string[];
}

export const agentApi = {
  capabilities: async (): Promise<AgentCapabilities> => {
    const headers = new Headers();
    const t = getToken();
    if (t) headers.set("Authorization", `Bearer ${t}`);
    const res = await fetch(`${API_BASE}/api/agent/capabilities`, { headers });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json();
  },
};

/**
 * POST a question and invoke `onEvent` for every event the agent emits.
 * Pass `signal` to let the user stop a run mid-flight.
 */
export async function streamAgent(
  question: string,
  history: { question: string; answer: string }[],
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}/api/agent/stream`, {
    method: "POST", headers, signal,
    body: JSON.stringify({ question, history: history.slice(-6) }),
  });

  if (res.status === 401) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* keep */ }
    throw new ApiError(res.status, detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // The last fragment may be half a line; keep it for the next chunk.
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const s = line.trim();
      if (!s) continue;
      try { onEvent(JSON.parse(s) as AgentEvent); }
      catch { /* a malformed line must not kill the stream */ }
    }
  }
  const tail = buffer.trim();
  if (tail) { try { onEvent(JSON.parse(tail) as AgentEvent); } catch { /* ignore */ } }
}

// --------------------------------------------------------------------------- formatting
export function formatValue(v: number, unit: Unit): string {
  if (unit === "inr") {
    const a = Math.abs(v);
    if (a >= 1e7) return `₹${(v / 1e7).toFixed(a >= 1e8 ? 0 : 2)} Cr`;
    if (a >= 1e5) return `₹${(v / 1e5).toFixed(a >= 1e6 ? 0 : 2)} L`;
    return `₹${Math.round(v).toLocaleString("en-IN")}`;
  }
  if (unit === "percent") return `${(v <= 1 ? v * 100 : v).toFixed(v <= 1 ? 1 : 0)}%`;
  if (Number.isInteger(v)) return v.toLocaleString("en-IN");
  return Math.abs(v) < 1 ? v.toFixed(3) : v.toFixed(2);
}

/** Compact axis tick: 12.4k, 3.1M, keeps the drafted axis narrow. */
export function tickValue(v: number, unit: Unit): string {
  if (unit === "inr") return formatValue(v, unit);
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`;
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
