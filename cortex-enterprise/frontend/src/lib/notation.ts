/**
 * The link-chart notation. This is the design system's core: an analyst reads
 * entity type off the shape and evidence grade off the line, exactly as on a
 * hand-drafted chart. Nothing decorative lives here; every mark means one thing.
 */
import { format } from "date-fns";
import type { EntityType, Extractor } from "./types";

export const INK = {
  film: "#E4E7E4",       // platform terrazzo
  rule: "#C3C8C3",
  ink: "#141613",        // board black
  inkSoft: "#4C534C",
  inkFaint: "#606760",
  pencil: "#B02821",     // signal red: stop, critical, selection
  pencilSoft: "#E39D99",
  blue: "#1F6FB2",       // money runs on the blue route
  blueSoft: "#9DC0DD",
  amber: "#6B4600",      // the only amber that carries text or a mark on the light ground
  green: "#2E7D4F",
} as const;

/**
 * Route colours, one per community, the way a metro map gives each line its own ink.
 * They ride the edge only; the text field stays achromatic, so colour never becomes the sole
 * carrier of meaning and a colour-blind reader loses nothing but the grouping shorthand.
 */
/**
 * The route palette. Signal red is deliberately absent: on this map red means stop — a critical
 * alert or the mark you have selected — and a community that happened to be numbered first is
 * neither. Six hues, each distinguishable from the others in greyscale weight as well as in hue.
 */
export const ROUTE_INKS = ["#1F6FB2", "#2E7D4F", "#8A5A04", "#7A4FA3", "#0F7B8A", "#B5532A"] as const;

export function routeInk(community: number | null | undefined): string {
  if (community === null || community === undefined) return INK.inkSoft;
  return ROUTE_INKS[Math.abs(community) % ROUTE_INKS.length];
}

export type Shape = "circle" | "square" | "diamond" | "hexagon" | "triangle" | "rect" | "pin" | "tag" | "ring" | "cut-hexagon";

export const SHAPE: Record<EntityType, Shape> = {
  PERSON: "circle",
  ORGANIZATION: "square",
  PHONE: "diamond",
  BANK_ACCOUNT: "hexagon",
  CRYPTO_WALLET: "cut-hexagon",
  VEHICLE: "triangle",
  CASE: "rect",
  REPORT: "rect",
  LOCATION: "pin",
  SOCIAL_HANDLE: "tag",
  GOV_ID: "ring",
};

export const TYPE_LABEL: Record<EntityType, string> = {
  PERSON: "Person", ORGANIZATION: "Organisation", PHONE: "Phone", BANK_ACCOUNT: "Account", VEHICLE: "Vehicle",
  CRYPTO_WALLET: "Crypto wallet", CASE: "Case / FIR", REPORT: "Report", LOCATION: "Location",
  SOCIAL_HANDLE: "Handle", GOV_ID: "Identifier",
};

export const TYPE_ORDER: EntityType[] = ["PERSON", "ORGANIZATION", "PHONE", "BANK_ACCOUNT", "CRYPTO_WALLET", "VEHICLE", "GOV_ID", "CASE", "REPORT", "LOCATION", "SOCIAL_HANDLE"];

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
export const DASH: Record<LineStyle, number[]> = { solid: [], dashed: [11, 3.5], dotted: [1.5, 4] };

/** Ink per relationship family. Money is blue; everything else is pen black, weight carries volume. */
export const MONEY_RELS = new Set(["TRANSFERRED_TO", "OWNS_ACCOUNT", "OWNS_WALLET", "CONVERTED_VIA"]);
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
  burner_phone: "Burner phone", structuring: "Structured deposits", layering: "Layering route", call_burst: "Call burst",
  transfer_burst: "Pass-through account", complaint_hub: "Complaint hub",
  night_activity: "Night activity", international_contact: "International contact", behavioural_outlier: "Behavioural outlier",
  detector_error: "Detector error", wanted_corporate_ties: "Wanted person controls companies", offshore_officer_accused: "Offshore officer accused",
  debarred_shared_directors: "Debarred company, shared directors", mass_directorship: "Mass directorship",
  GHOST_NODE: "Ghost node / hidden intermediary",
  FIRST_TIME_OFFENDER_RISK: "First-time offender proximity risk",
  SOURCE_OWNERSHIP_CONFLICT: "Source discrepancy: Ownership",
  SOURCE_ATTRIBUTE_CONFLICT: "Source discrepancy: Attribute",
  SOURCE_STATUS_CONFLICT: "Source discrepancy: Status (Ghost activity)",
};

/** Node radius on the chart: priority carries size; types without scores sit small. */
export function nodeRadius(type: EntityType, priority: number, degree: number, presentation: boolean): number {
  const base = type === "PERSON" || type === "ORGANIZATION" ? 6.5 + priority * 15 : 4 + Math.min(degree, 30) * 0.1;
  return presentation ? base * 1.35 : base;
}

/** Short reference code for margin notes and the title block, e.g. "P-014". */
export function refCode(type: EntityType, index: number): string {
  const p: Record<EntityType, string> = { PERSON: "P", ORGANIZATION: "O", PHONE: "T", BANK_ACCOUNT: "A", CRYPTO_WALLET: "W", VEHICLE: "V", CASE: "C", REPORT: "R", LOCATION: "L", SOCIAL_HANDLE: "H", GOV_ID: "I" };
  return `${p[type] ?? "X"}-${String(index).padStart(3, "0")}`;
}

export const fmtInr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
export const fmtNum = (n: number, d = 2) => Number.isInteger(n) ? n.toLocaleString("en-IN") : n.toFixed(d);

/* ------------------------------------------------------------------ properties
   An entity's recorded properties come off the wire as whatever the source called
   them. They are read by a person, so a key becomes a phrase and a value becomes a
   sentence fragment: never a raw JSON blob, never a snake_case key on the sheet.
--------------------------------------------------------------------------- */

/** Words that are read as letters, not capitalised as words. */
const ACRONYM: Record<string, string> = {
  id: "ID", ids: "IDs", url: "URL", uri: "URI", lei: "LEI", isin: "ISIN", icij: "ICIJ", nia: "NIA", mha: "MHA",
  sebi: "SEBI", nse: "NSE", bse: "BSE", uapa: "UAPA", pan: "PAN", gstin: "GSTIN", ifsc: "IFSC", imei: "IMEI",
  imsi: "IMSI", cnr: "CNR", fir: "FIR", cdr: "CDR", kyc: "KYC", ip: "IP", pep: "PEP", ncrb: "NCRB", cctns: "CCTNS",
  usd: "USD", inr: "INR", ocr: "OCR", pdf: "PDF", api: "API", sc: "SC", hc: "HC",
};

/** Keys whose natural phrasing is not a simple de-underscoring. */
const ATTR_LABEL: Record<string, string> = {
  lat: "Latitude", lon: "Longitude", opensanctions_id: "OpenSanctions ID", icij_type: "ICIJ record type",
  icij_node_id: "ICIJ node ID", sourceID: "ICIJ source file", screened_match: "Screened against watchlist",
  screen_score: "Screen match score", screen_strength: "Screen match strength", watchlist_datasets: "Watchlist datasets",
  watchlist_topics: "Watchlist topics", referent_count: "Linked list entries", record_role: "Role in record",
  court_role: "Role in court record", wanted_notice: "Wanted notice", valid_until: "Record valid until",
  jurisdiction_description: "Jurisdiction", incorporation_date: "Incorporated on", birth_date: "Date of birth",
};

/** snake_case, camelCase or SCREAMING_CASE to a sentence a person reads. */
export function humaniseKey(key: string): string {
  if (ATTR_LABEL[key]) return ATTR_LABEL[key];
  const words = key.replace(/([a-z0-9])([A-Z])/g, "$1 $2").split(/[_\s.-]+/).filter(Boolean);
  if (!words.length) return key;
  return words
    .map((w, i) => {
      const a = ACRONYM[w.toLowerCase()];
      if (a) return a;
      const lower = w.toLowerCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}|$)/;
/** Keys whose numbers are labels, not quantities: an ID is never written 1,01,27,533. */
const IDENTIFIER_KEY = /(^|_)(id|ids|no|num|number|code|pin|lei|imei|imsi|isin|cnr|year|account|phone)$/i;

/** One scalar, formatted the way the sheet writes it: Yes/No, 12 Mar 2024, grouped figures. */
export function formatAttrScalar(v: unknown, key?: string): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "";
    if (key && IDENTIFIER_KEY.test(key)) return String(v);
    return Number.isInteger(v) ? v.toLocaleString("en-IN") : String(Number(v.toFixed(4)));
  }
  const s = String(v).trim();
  if (ISO_DATE.test(s)) {
    const d = new Date(s);
    if (!Number.isNaN(d.getTime())) return format(d, "dd MMM yyyy");
  }
  return s;
}

/** Any recorded value as prose: lists become comma lists, nested records become "key: value" pairs. */
export function formatAttrValue(v: unknown, key?: string): string {
  if (Array.isArray(v)) return v.map((x) => formatAttrValue(x, key)).filter(Boolean).join(", ");
  if (v && typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .filter(([, x]) => !isEmptyAttr(x))
      .map(([k, x]) => `${humaniseKey(k)}: ${formatAttrValue(x, k)}`)
      .join(" · ");
  }
  return formatAttrScalar(v, key);
}

/** A property with nothing in it is not printed: a blank row says nothing and costs a line. */
export function isEmptyAttr(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return true;
  if (Array.isArray(v)) return v.length === 0 || v.every(isEmptyAttr);
  if (typeof v === "object") return Object.keys(v as object).length === 0;
  if (typeof v === "number") return !Number.isFinite(v);
  return String(v).trim() === "";
}

/** Every non-empty recorded property, humanised, in the order the source recorded it. */
export function attrRows(attrs: Record<string, unknown> | null | undefined): { key: string; label: string; value: string; href: string | null }[] {
  return Object.entries(attrs ?? {})
    .filter(([, v]) => !isEmptyAttr(v))
    .map(([k, v]) => {
      const value = formatAttrValue(v, k);
      return { key: k, label: humaniseKey(k), value, href: /^https?:\/\/\S+$/i.test(value) ? value : null };
    })
    .filter((r) => r.value !== "");
}

/** "12 Mar 2024 – 4 Apr 2024", or a single date, or nothing at all. */
export function dateSpan(first?: string | null, last?: string | null): string {
  const fmt = (s?: string | null) => {
    if (!s) return null;
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : format(d, "dd MMM yyyy");
  };
  const a = fmt(first), b = fmt(last);
  if (a && b) return a === b ? a : `${a} – ${b}`;
  return a ?? b ?? "";
}
