/**
 * Where a claim came from, as a link a reader can open.
 *
 * The API attaches `source_name` / `source_url` to every evidence and document row
 * (backend/app/ingestion/provenance.py). This module is the client-side fallback for
 * the same question, so a panel still names its source — and links it where the origin
 * is addressable — when a field has not arrived. Nothing here guesses: a source with no
 * public landing page returns null and the console prints a plain name, never a dead link.
 */

/** Human-facing name per document source type. Mirrors SOURCE_NAMES on the server. */
export const SOURCE_NAMES: Record<string, string> = {
  LEAK: "ICIJ Offshore Leaks",
  WATCHLIST: "OpenSanctions",
  JUDGMENT: "Supreme Court of India",
  GLEIF: "GLEIF registry",
  NEWS: "News report",
  INTEL: "Police notice",
  FIR: "First Information Report",
  CDR: "Call detail records",
  TRANSACTION: "Bank transactions",
  KYC: "KYC records",
  SURVEILLANCE: "Surveillance log",
  SOCIAL: "Social media",
  STATS: "NCRB statistics",
  BENCHMARK: "Research benchmark",
  REPORT: "Analyst report",
};

/** The landing page a reader can check a source type against. Absent = no public page. */
export const SOURCE_HOMES: Record<string, string> = {
  LEAK: "https://offshoreleaks.icij.org/",
  WATCHLIST: "https://www.opensanctions.org/datasets/",
  JUDGMENT: "https://main.sci.gov.in/judgments",
  GLEIF: "https://search.gleif.org/",
  INTEL: "https://www.nia.gov.in/most-wanted.htm",
  STATS: "https://data.gov.in/",
  BENCHMARK: "https://networks.skewed.de/",
};

/** One line on what a source type actually puts on the sheet. */
export const SOURCE_GIST: Record<string, string> = {
  LEAK: "Offshore companies, their officers and intermediaries",
  WATCHLIST: "Sanctioned, banned and debarred names, with the list that carries them",
  JUDGMENT: "Reported judgments — parties, counsel and the bench",
  GLEIF: "Registered legal entities and their parent / subsidiary tree",
  NEWS: "Headline and summary of a crime report, linked to the publisher",
  INTEL: "Wanted and proclaimed-offender notices",
  FIR: "First Information Reports and their narratives",
  CDR: "Call detail records",
  TRANSACTION: "Bank transfers between accounts",
  KYC: "Account-holder identity records",
  SURVEILLANCE: "Observation and tower-ping logs",
  SOCIAL: "Handles, posts and their locations",
  STATS: "Published crime statistics",
  BENCHMARK: "Labelled research networks used to measure the method",
  REPORT: "Analyst-written notes and reports",
};

/** Name of a source, preferring whatever the API already resolved. */
export function sourceLabel(sourceType?: string | null, given?: string | null): string {
  if (given) return given;
  const t = (sourceType ?? "").toUpperCase();
  return SOURCE_NAMES[t] ?? (t ? t.charAt(0) + t.slice(1).toLowerCase() : "Unattributed");
}

/** Address of a source, preferring the exact one the API recorded. Null means: no public page. */
export function sourceHref(sourceType?: string | null, given?: string | null): string | null {
  if (given && /^https?:\/\//i.test(given)) return given;
  return SOURCE_HOMES[(sourceType ?? "").toUpperCase()] ?? null;
}

/**
 * The exact address a connector recorded on a document, if it recorded one. Same key order as the
 * server, so the console and the API agree on which link is the most specific.
 */
export function metaHref(meta?: Record<string, unknown> | null): string | null {
  for (const key of ["url", "link", "pdf", "pdf_link", "source_url", "href"]) {
    const v = meta?.[key];
    if (typeof v === "string" && /^https?:\/\//i.test(v)) return v;
  }
  return null;
}

/** The one-line gist of a source type, for the "what is on the sheet" breakdown. */
export function sourceGist(sourceType?: string | null): string {
  return SOURCE_GIST[(sourceType ?? "").toUpperCase()] ?? "Documents collected under this type";
}

/**
 * Connectors, grouped the way an analyst thinks about them, with the landing page a
 * reader can open. Connector `homepage` from the API is an API/probe endpoint, not
 * something to show a person, so the human page is named here.
 */
export const CONNECTOR_GROUPS: { key: string; label: string; blurb: string; names: string[] }[] = [
  { key: "watchlists", label: "Watchlists and wanted notices", blurb: "Names a state has already designated, and the notices police have published.", names: ["opensanctions", "wanted"] },
  { key: "corporate", label: "Corporate and offshore records", blurb: "Who owns and directs what, onshore and off.", names: ["icij", "gleif"] },
  { key: "official", label: "Courts and police records", blurb: "Adjudicated facts and filed complaints.", names: ["courts", "cctns_mh"] },
  { key: "open", label: "Open statistics", blurb: "Official published counts, for base rates rather than individuals.", names: ["ncrb", "datagovin"] },
  { key: "press", label: "Press", blurb: "Headlines and summaries, always linked back to the publisher.", names: ["news"] },
  { key: "method", label: "Method validation", blurb: "Labelled networks with known answers, used to measure this console.", names: ["benchmarks"] },
];

/** Plain-English: what does harvesting this connector give you? */
export const CONNECTOR_GIST: Record<string, string> = {
  opensanctions: "Sanctioned and banned persons and companies — UAPA designations, SEBI/NSE debarments, INTERPOL red notices — with the list each name sits on.",
  wanted: "NIA and state-police most-wanted and proclaimed-offender notices, as published.",
  icij: "Offshore companies from the Panama and Pandora Papers, with their officers, addresses and intermediaries.",
  gleif: "Registered legal entities worldwide by LEI, and the parent / subsidiary tree around a group.",
  courts: "Reported Supreme Court and High Court judgments — parties, counsel, bench and the offences charged.",
  cctns_mh: "Published FIRs from the Maharashtra Police citizen portal, by district and date range.",
  ncrb: "NCRB Crime in India tables — offence counts by state and year.",
  datagovin: "Any open dataset published on data.gov.in matching a search term.",
  news: "Crime reporting from TOI, The Hindu and Indian Express, headline and summary only, linked to the article.",
  benchmarks: "Published criminal-network datasets with known ground truth, so community detection and key-player ranking can be scored.",
};

/** The page a person should be sent to for a connector, where the probe URL is not one. */
export const CONNECTOR_HOMES: Record<string, string> = {
  opensanctions: "https://www.opensanctions.org/datasets/",
  wanted: "https://www.nia.gov.in/most-wanted.htm",
  icij: "https://offshoreleaks.icij.org/",
  gleif: "https://search.gleif.org/",
  courts: "https://registry.opendata.aws/indian-supreme-court-judgments/",
  cctns_mh: "https://citizen.mahapolice.gov.in/Citizen/MH/PublishedFIRs.aspx",
  ncrb: "https://data.gov.in/",
  datagovin: "https://data.gov.in/",
  news: "https://timesofindia.indiatimes.com/india",
  benchmarks: "https://networks.skewed.de/",
};

export function connectorHref(name: string, homepage?: string): string | null {
  return CONNECTOR_HOMES[name] ?? (homepage && /^https?:\/\//i.test(homepage) ? homepage : null);
}
