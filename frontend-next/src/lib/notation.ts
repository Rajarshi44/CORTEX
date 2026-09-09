/**
 * The link-chart notation. This is the design system's core: an analyst reads
 * entity type off the shape and evidence grade off the line, exactly as on a
 * hand-drafted chart. Nothing decorative lives here; every mark means one thing.
 */
import type { EntityType, Extractor } from "./types";

export const INK = {
  film: "#EDEDEA",       // drafting-film ground
  rule: "#DAD9D3",       // faint sheet rules
  ink: "#1F1F1F",        // technical-pen black
  inkSoft: "#5B5B57",    // secondary ink
  inkFaint: "#9A9A94",   // tertiary / receded
  pencil: "#B03A2E",     // red confirmation pencil: priority, selection, critical
  pencilSoft: "#D9A39C",
  blue: "#3A5F8F",       // money lines
  blueSoft: "#9FB4CC",
  amber: "#B7791F",      // high severity / warning
  green: "#4E7A47",      // confirmed / intact
} as const;

export type Shape = "circle" | "square" | "diamond" | "hexagon" | "triangle" | "rect" | "pin" | "tag" | "ring";

export const SHAPE: Record<EntityType, Shape> = {
  PERSON: "circle",
  ORGANIZATION: "square",
  PHONE: "diamond",
  BANK_ACCOUNT: "hexagon",
  VEHICLE: "triangle",
  CASE: "rect",
  REPORT: "rect",
  LOCATION: "pin",
  SOCIAL_HANDLE: "tag",
  GOV_ID: "ring",
};

export const TYPE_LABEL: Record<EntityType, string> = {
  PERSON: "Person", ORGANIZATION: "Organisation", PHONE: "Phone", BANK_ACCOUNT: "Account", VEHICLE: "Vehicle",
  CASE: "Case / FIR", REPORT: "Report", LOCATION: "Location", SOCIAL_HANDLE: "Handle", GOV_ID: "Identifier",
};

export const TYPE_ORDER: EntityType[] = ["PERSON", "ORGANIZATION", "PHONE", "BANK_ACCOUNT", "VEHICLE", "GOV_ID", "CASE", "REPORT", "LOCATION", "SOCIAL_HANDLE"];

/** Line style = evidence grade. Solid: structured / checksum. Dashed: rule-extracted. Dotted: model-inferred. */
export type LineStyle = "solid" | "dashed" | "dotted";
export function lineStyleFor(extractor?: Extractor | string | null, confidence?: number): LineStyle {
  if (extractor === "structured" || extractor === "checksum") return "solid";
  if (extractor === "gliner" || extractor === "llm") return "dotted";
  if (extractor === "rules") return "dashed";
  // no extractor on the edge itself: infer from confidence
  if (confidence !== undefined && confidence >= 0.95) return "solid";
  if (confidence !== undefined && confidence < 0.7) return "dotted";
  return "dashed";
}
export const DASH: Record<LineStyle, number[]> = { solid: [], dashed: [6, 4], dotted: [1.5, 3.5] };

/** Ink per relationship family. Money is blue; everything else is pen black, weight carries volume. */
export const MONEY_RELS = new Set(["TRANSFERRED_TO", "OWNS_ACCOUNT"]);
export const COMMS_RELS = new Set(["CALLED", "USES_PHONE", "SHARED_HANDSET", "PINGED_AT", "COMMUNICATED_WITH"]);
export function edgeInk(rel: string): string {
  return MONEY_RELS.has(rel) ? INK.blue : INK.ink;
}

export const REL_LABEL: Record<string, string> = {
  CALLED: "called", TRANSFERRED_TO: "paid", USES_PHONE: "uses phone", OWNS_ACCOUNT: "holds account", MET: "met",
  SEEN_AT: "seen at", RESIDES_AT: "resides at", ACCUSED_IN: "accused in", COMPLAINANT_IN: "complainant in",
  MENTIONED_IN: "mentioned in", ASSOCIATED_VEHICLE: "vehicle", OWNS: "owns", DIRECTOR_OF: "director of",
  AFFILIATED_WITH: "affiliated", REPORTS_TO: "on instructions of", CO_ACCUSED: "co-accused", MENTIONED_WITH: "mentioned with",
  COMMUNICATED_WITH: "communicates", OWNS_HANDLE: "handle", MENTIONED: "mentioned", POSTED_FROM: "posted from",
  PINGED_AT: "pinged tower", SUBJECT_OF: "subject of", REGISTERED_AT: "registered at", LOCATED_AT: "located at",
  OWNED_BY: "owned by", SHARED_HANDSET: "same handset", HOLDS_ID: "holds ID", SUBSIDIARY_OF: "subsidiary of",
  WANTED_IN: "wanted", PETITIONER_IN: "petitioner", RESPONDENT_IN: "respondent", ADJUDICATED: "adjudicated",
  INVOLVED_IN: "involved in", ASSOCIATE_OF: "associate", POSSIBLE_SAME_AS: "possibly same as",
};
export const relLabel = (r: string) => REL_LABEL[r] ?? r.toLowerCase().replace(/_/g, " ");

export const REL_GROUPS: { key: string; label: string; rels: string[] }[] = [
  { key: "comms", label: "Communication", rels: ["CALLED", "USES_PHONE", "SHARED_HANDSET", "COMMUNICATED_WITH", "PINGED_AT"] },
  { key: "money", label: "Money", rels: ["TRANSFERRED_TO", "OWNS_ACCOUNT"] },
  { key: "contact", label: "Contact", rels: ["MET", "SEEN_AT", "RESIDES_AT", "POSTED_FROM", "ASSOCIATE_OF", "MENTIONED_WITH"] },
  { key: "legal", label: "Legal", rels: ["ACCUSED_IN", "COMPLAINANT_IN", "CO_ACCUSED", "MENTIONED_IN", "SUBJECT_OF", "WANTED_IN", "PETITIONER_IN", "RESPONDENT_IN", "REPORTS_TO"] },
  { key: "assets", label: "Assets & IDs", rels: ["ASSOCIATED_VEHICLE", "OWNS", "DIRECTOR_OF", "AFFILIATED_WITH", "SUBSIDIARY_OF", "HOLDS_ID", "OWNS_HANDLE", "LOCATED_AT", "REGISTERED_AT", "OWNED_BY"] },
];

export const SEVERITY_INK: Record<string, string> = { critical: INK.pencil, high: INK.amber, medium: INK.inkSoft, low: INK.inkFaint };
export const ALERT_KIND_LABEL: Record<string, string> = {
  burner_phone: "Burner phone", structuring: "Structured deposits", layering: "Layering chain", call_burst: "Call burst",
  night_activity: "Night activity", international_contact: "International contact", behavioural_outlier: "Behavioural outlier",
  detector_error: "Detector error", wanted_corporate_ties: "Wanted person controls companies", offshore_officer_accused: "Offshore officer accused",
  debarred_shared_directors: "Debarred company, shared directors", mass_directorship: "Mass directorship",
};

/** Node radius on the chart: priority carries size; types without scores sit small. */
export function nodeRadius(type: EntityType, priority: number, degree: number, presentation: boolean): number {
  const base = type === "PERSON" || type === "ORGANIZATION" ? 5 + priority * 12 : 3.2 + Math.min(degree, 30) * 0.08;
  return presentation ? base * 1.35 : base;
}

/** Short reference code for margin notes and the title block, e.g. "P-014". */
export function refCode(type: EntityType, index: number): string {
  const p: Record<EntityType, string> = { PERSON: "P", ORGANIZATION: "O", PHONE: "T", BANK_ACCOUNT: "A", VEHICLE: "V", CASE: "C", REPORT: "R", LOCATION: "L", SOCIAL_HANDLE: "H", GOV_ID: "I" };
  return `${p[type]}-${String(index).padStart(3, "0")}`;
}

export const fmtInr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
export const fmtNum = (n: number, d = 2) => Number.isInteger(n) ? n.toLocaleString("en-IN") : n.toFixed(d);
