"""
Open-web search and page reading for the investigator agent.

Two tiers behind one interface:
  * Firecrawl (`FIRECRAWL_API_KEY`) - JS-rendered pages, clean markdown, real search ranking.
  * DuckDuckGo HTML + the shared `Connector` fetcher - no key, robots-aware, rate limited,
    disk cached, so the demo still works on a conference wifi or fully offline from cache.

The tier is chosen per call and reported in the result, so an analyst always sees whether a
claim came from a live fetch, a cached copy, or nothing at all.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from ..config import settings
from .base import DEFAULT_HEADERS, Connector, SourceReport, register

log = logging.getLogger("cna.sources.web")

FIRECRAWL_BASE = "https://api.firecrawl.dev/v2"
# An honest, contact-bearing agent string. Several large sites (Wikimedia most notably) return
# 403 to a spoofed Chrome UA on a scripted request but serve a declared bot happily, so this is
# both the polite choice and the one that actually works. The browser headers stay as a fallback
# for the older portals that sniff for a real browser.
HONEST_UA = "SUTRA-CNA/1.0 (criminal network analysis console; research use; contact: local operator)"
HONEST_HEADERS = {"User-Agent": HONEST_UA,
                  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                  "Accept-Language": "en-IN,en;q=0.8"}
# Hosts that reliably answer a scripted GET; a search result outside these still gets fetched,
# this list only decides what we surface first when a query returns many equivalent pages.
PREFERRED = ("thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com", "hindustantimes.com",
             "reuters.com", "bbc.com", "livemint.com", "ndtv.com", "wikipedia.org", "sebi.gov.in",
             "rbi.org.in", "enforcementdirectorate.gov.in", "mha.gov.in", "indiankanoon.org")


def firecrawl_key() -> str | None:
    """Firecrawl key from the environment, or from `Settings` when it came out of a .env file."""
    for n in ("CNA_FIRECRAWL_API_KEY", "FIRECRAWL_API_KEY"):
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    v = settings.firecrawl_api_key
    return v.strip() if isinstance(v, str) and v.strip() else None


@register
class WebConnector(Connector):
    """Open-web search + page reader."""

    name = "web"
    title = "Open web"
    description = "Search engine results and page text, via Firecrawl when a key is present, DuckDuckGo HTML otherwise."
    homepage = "https://duckduckgo.com"
    licence = "Third-party content; each result keeps its own source URL for attribution."
    attribution = "Open web"
    rate_limit = 1.5
    # A search result page is worth re-using for a working session but not for a week.
    cache_ttl_hours = 12
    # Search engines disallow their result paths in robots.txt. We honour that for the *crawler*
    # tiers; the DuckDuckGo HTML endpoint is the documented no-JS interface and is queried once
    # per analyst question, at the analyst's explicit request, not crawled.
    respect_robots = False

    def _mk_client(self, legacy: bool = False) -> httpx.Client:
        """Declare ourselves honestly, and only that.

        The base client also sends the browser's `Sec-Fetch-*` / `Upgrade-Insecure-Requests`
        navigation headers. Paired with a non-browser agent string those signals contradict each
        other, and Wikimedia (among others) answers 403. Send one coherent identity instead; the
        browser headers are still available per call through `_fetch_either_agent`.
        """
        from .base import legacy_ssl_context

        kw: dict = dict(timeout=self.timeout, follow_redirects=True, headers=dict(HONEST_HEADERS))
        if legacy:
            kw["verify"] = legacy_ssl_context()
        return httpx.Client(**kw)

    def _fetch_either_agent(self, url: str, **kw):
        """Try the declared agent, then the browser headers. Sites reject one or the other, rarely both."""
        res = self.fetch(url, **kw)
        if res.ok:
            return res
        return self.fetch(url, headers={**DEFAULT_HEADERS, **(kw.pop("headers", None) or {})},
                          **{k: v for k, v in kw.items() if k != "headers"})

    # ------------------------------------------------------------------ firecrawl
    def _firecrawl(self, path: str, payload: dict, timeout: float = 60.0) -> dict | None:
        key = firecrawl_key()
        if not key:
            return None
        try:
            r = httpx.post(f"{FIRECRAWL_BASE}{path}", json=payload, timeout=timeout,
                           headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            if r.status_code >= 400:
                log.warning("firecrawl %s -> HTTP %s: %s", path, r.status_code, r.text[:200])
                return None
            return r.json()
        except Exception as exc:
            log.warning("firecrawl %s failed: %s", path, exc)
            return None

    # ------------------------------------------------------------------ search
    def search(self, query: str, limit: int = 6, fetch_content: bool = False) -> dict:
        """Search the open web. Returns {tier, query, results:[{title,url,snippet,content?}]}."""
        if fc := self._search_firecrawl(query, limit, fetch_content):
            return fc
        return self._search_duckduckgo(query, limit, fetch_content)

    def _search_firecrawl(self, query: str, limit: int, fetch_content: bool) -> dict | None:
        payload: dict = {"query": query, "limit": max(1, min(limit, 10))}
        if fetch_content:
            payload["scrapeOptions"] = {"formats": ["markdown"], "onlyMainContent": True}
        data = self._firecrawl("/search", payload)
        if not data:
            return None
        raw = data.get("data")
        rows = raw.get("web", []) if isinstance(raw, dict) else (raw or [])
        results = []
        for r in rows[:limit]:
            results.append({"title": (r.get("title") or "").strip(), "url": r.get("url", ""),
                            "snippet": (r.get("description") or "")[:400],
                            "content": (r.get("markdown") or "")[:6000] or None})
        if not results:
            return None
        return {"tier": "firecrawl", "query": query, "results": results}

    def _search_duckduckgo(self, query: str, limit: int, fetch_content: bool) -> dict:
        res = self._fetch_either_agent(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                                       headers={"Referer": "https://duckduckgo.com/"})
        if not res.ok:
            return {"tier": "unavailable", "query": query, "results": [],
                    "reason": res.reason or "search endpoint unreachable"}
        results = self._parse_ddg(res.text, limit)
        if fetch_content:
            for r in results[:3]:
                page = self.read_page(r["url"], max_chars=4000)
                if page.get("text"):
                    r["content"] = page["text"]
        return {"tier": "cached" if res.from_cache else "duckduckgo", "query": query, "results": results}

    @staticmethod
    def _parse_ddg(page: str, limit: int) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|</div>\s*</div>\s*</div>)',
            page, re.DOTALL)
        for href, title, tail in blocks:
            url = unquote(parse_qs(urlparse(_html.unescape(href)).query).get("uddg", [_html.unescape(href)])[0])
            if not url.startswith("http"):
                continue
            host = urlparse(url).netloc
            if host in seen:
                continue
            seen.add(host)
            snippet = re.sub(r"<[^>]+>", " ", tail)
            snippet = re.sub(r"\s+", " ", _html.unescape(snippet)).strip()
            out.append({"title": re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", title))).strip(),
                        "url": url, "snippet": snippet[:400], "content": None})
        out.sort(key=lambda r: (0 if any(p in r["url"] for p in PREFERRED) else 1))
        return out[:limit]

    # ------------------------------------------------------------------ page read
    def read_page(self, url: str, max_chars: int = 8000) -> dict:
        """Fetch one URL as readable text. Firecrawl first (renders JS), plain HTTP otherwise."""
        if firecrawl_key():
            data = self._firecrawl("/scrape", {"url": url, "formats": ["markdown"], "onlyMainContent": True})
            doc = (data or {}).get("data") or {}
            md = doc.get("markdown") or ""
            if md.strip():
                meta = doc.get("metadata") or {}
                return {"tier": "firecrawl", "url": url, "title": meta.get("title") or url,
                        "text": md[:max_chars], "truncated": len(md) > max_chars}
        res = self._fetch_either_agent(url)
        if not res.ok:
            return {"tier": "unavailable", "url": url, "title": "", "text": "",
                    "reason": res.reason or f"HTTP {res.http_status}"}
        raw = res.text
        title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.DOTALL | re.IGNORECASE)
        text = self.strip_html(raw)
        return {"tier": "cached" if res.from_cache else "http", "url": url,
                "title": _html.unescape(title.group(1)).strip() if title else url,
                "text": text[:max_chars], "truncated": len(text) > max_chars}

    # ------------------------------------------------------------------ connector interface
    def probe(self) -> SourceReport:
        if firecrawl_key():
            return SourceReport(self.name, "ok", reason="firecrawl key present", details={"tier": "firecrawl"})
        r = self.fetch("https://html.duckduckgo.com/html/?q=test", use_cache=False)
        return SourceReport(self.name, "ok" if r.ok else r.status, reason=r.reason, details={"tier": "duckduckgo"})

    def harvest(self, db, query: str = "", limit: int = 5, **_) -> SourceReport:
        """The web connector is a read tool for the agent, not a bulk ingester."""
        if not query:
            return SourceReport(self.name, "unavailable", reason="web source is query-driven; pass a query")
        res = self.search(query, limit)
        return SourceReport(self.name, "ok" if res["results"] else "unavailable", records=len(res["results"]),
                            reason=res.get("reason", ""), details={"tier": res["tier"], "urls": [r["url"] for r in res["results"]]})


def web() -> WebConnector:
    return WebConnector()


def tier() -> str:
    return "firecrawl" if firecrawl_key() else "duckduckgo"
