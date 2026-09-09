"""
Where a claim came from, as a link an investigator can open.

A sheet that says "this man is on a watchlist" and cannot show you the watchlist entry is asking
to be believed. Every document therefore resolves to a human-readable source name and, wherever
the origin is addressable, a URL.

Two routes to a link, in order of trust:

1. The document's own metadata. Connectors that harvested a specific page or file already stored
   its address (`url`, `link`, `pdf`), and that exact address is always preferred.
2. A derived link. Bulk sources - the whole OpenSanctions crime dataset, an ICIJ subset - have no
   per-record page, but they do have a stable dataset or search page that a reader can verify
   against. Those are constructed here rather than invented per connector, so one fix reaches
   every lens at once.

Nothing here guesses: a source with no addressable origin returns None and the console shows a
plain name instead of a dead link.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

# Human-facing name for each source type, and the landing page a reader can check it against.
SOURCE_NAMES: dict[str, str] = {
    "LEAK": "ICIJ Offshore Leaks",
    "WATCHLIST": "OpenSanctions",
    "JUDGMENT": "Supreme Court of India",
    "GLEIF": "GLEIF registry",
    "NEWS": "News report",
    "INTEL": "Police notice",
    "FIR": "First Information Report",
    "CDR": "Call detail records",
    "TRANSACTION": "Bank transactions",
    "KYC": "KYC records",
    "SURVEILLANCE": "Surveillance log",
    "SOCIAL": "Social media",
    "STATS": "NCRB statistics",
    "BENCHMARK": "Research benchmark",
}

SOURCE_HOMES: dict[str, str] = {
    "LEAK": "https://offshoreleaks.icij.org/",
    "WATCHLIST": "https://www.opensanctions.org/datasets/",
    "JUDGMENT": "https://main.sci.gov.in/judgments",
    "GLEIF": "https://search.gleif.org/",
    "INTEL": "https://www.nia.gov.in/most-wanted.htm",
    "STATS": "https://data.gov.in/",
}

# OpenSanctions publishes one page per dataset; the connector records which one it pulled.
_OS_DATASET = "https://www.opensanctions.org/datasets/{dataset}/"


def source_name(source_type: str, meta: dict[str, Any] | None = None) -> str:
    """A name a person recognises, specific where the metadata allows."""
    meta = meta or {}
    if source_type == "WATCHLIST":
        ds = str(meta.get("dataset") or "")
        return {
            "crime": "OpenSanctions crime list",
            "interpol_red_notices": "INTERPOL red notices",
            "in_mha_banned": "MHA banned organisations (UAPA)",
            "in_nse_debarred": "NSE / SEBI debarred entities",
        }.get(ds, f"OpenSanctions {ds}" if ds else "OpenSanctions")
    if source_type == "NEWS" and meta.get("feed"):
        return {
            "toi_crime": "Times of India, crime desk",
            "toi_mumbai": "Times of India, Mumbai",
            "hindu_national": "The Hindu, national",
            "ie_mumbai": "Indian Express, Mumbai",
        }.get(str(meta["feed"]), "News report")
    return SOURCE_NAMES.get(source_type, source_type.title())


def source_url(source_type: str, meta: dict[str, Any] | None = None, title: str = "") -> str | None:
    """The most specific verifiable address for this document, or None if there is not one."""
    meta = meta or {}
    # 1. an exact address the connector already recorded
    for key in ("url", "link", "pdf", "pdf_link", "source_url", "href"):
        v = meta.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    # 2. a stable page for the dataset the record came from
    if source_type == "WATCHLIST":
        ds = meta.get("dataset")
        if ds:
            return _OS_DATASET.format(dataset=ds)
        return SOURCE_HOMES["WATCHLIST"]
    if source_type == "LEAK":
        # the leaks database is searchable by name, which is what a reader actually wants
        subject = str(meta.get("country") or "").strip()
        return (f"https://offshoreleaks.icij.org/search?q={quote_plus(subject)}"
                if subject else SOURCE_HOMES["LEAK"])
    if source_type == "GLEIF":
        q = str(meta.get("query") or "").strip()
        return f"https://search.gleif.org/#/search/simpleSearch={quote_plus(q)}" if q else SOURCE_HOMES["GLEIF"]
    if source_type == "JUDGMENT":
        cnr = meta.get("cnr") or meta.get("case_no")
        if cnr:
            return f"https://judgments.ecourts.gov.in/pdfsearch/?p=pdf_search/search&search={quote_plus(str(cnr))}"
        return SOURCE_HOMES["JUDGMENT"]
    return SOURCE_HOMES.get(source_type)


def describe(document: Any) -> dict[str, Any]:
    """The provenance block attached to evidence and document rows in the API."""
    meta = getattr(document, "meta", None) or {}
    st = getattr(document, "source_type", "") or ""
    return {
        "source_name": source_name(st, meta),
        "source_url": source_url(st, meta, getattr(document, "title", "") or ""),
        "source_type": st,
    }
