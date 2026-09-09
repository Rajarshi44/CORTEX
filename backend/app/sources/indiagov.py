"""
Indian government connectors.

  datagovin   - Open Government Data platform API (NCRB / MHA statistics, 1,500+ crime datasets).
                Uses the public sample key by default; set CNA_DATA_GOV_IN_KEY for your own.
  ncrb        - NCRB "Crime in India" publication pages (year-wise PDFs/tables).
  wanted      - NIA / state police most-wanted & proclaimed-offender pages (public notices).

The wanted-list pages are plain public HTML. NIA renders names in image alt text and
card headings; state portals vary, so we extract conservatively (capitalised multi-word
names near "wanted"/"accused" cues) and store the page as an INTEL document so the
narrative NER also runs over it.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ingestion.pipeline import IngestionService
from .base import Connector, SourceReport, register

SAMPLE_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"


@register
class DataGovInConnector(Connector):
    name = "datagovin"
    title = "data.gov.in - NCRB / MHA open statistics"
    description = "Official Open Government Data API. District/state crime statistics from NCRB and MHA."
    homepage = "https://api.data.gov.in/lists?format=json&limit=1&api-key=" + SAMPLE_KEY
    licence = "Government Open Data License - India (GODL)"
    attribution = "Open Government Data (OGD) Platform India / NCRB"
    rate_limit = 3.0  # the shared sample key is throttled hard; a personal key (CNA_DATA_GOV_IN_KEY) can go faster
    respect_robots = False
    cache_ttl_hours = 24 * 3
    max_retries = 2

    def fetch(self, url, **kw):  # surface a precise, actionable reason when the shared key is throttled
        r = super().fetch(url, **kw)
        if not r.ok and r.reason.startswith("HTTP 429"):
            r.reason = ("HTTP 429 - the shared data.gov.in sample key is rate-limited; register a free key at "
                        "https://data.gov.in/user/register and set CNA_DATA_GOV_IN_KEY")
        return r

    @property
    def key(self) -> str:
        return os.getenv("CNA_DATA_GOV_IN_KEY", SAMPLE_KEY)

    def search(self, title: str = "crime", limit: int = 40, official_only: bool = True) -> list[dict]:
        r = self.fetch("https://api.data.gov.in/lists", params={"format": "json", "api-key": self.key, "limit": limit,
                                                                "filters[title]": title})
        if not r.ok:
            return []
        out = []
        for rec in r.json().get("records", []):
            org = rec.get("org") or []
            if official_only and not any("Ministry" in o or "Bureau" in o or "Department" in o for o in org):
                continue
            out.append({"resource_id": rec.get("index_name"), "title": rec.get("title"), "org": org,
                        "sector": rec.get("sector"), "updated": rec.get("updated"), "desc": (rec.get("desc") or "")[:200]})
        return out

    def resource(self, resource_id: str, limit: int = 500, offset: int = 0) -> dict:
        r = self.fetch(f"https://api.data.gov.in/resource/{resource_id}",
                       params={"format": "json", "api-key": self.key, "limit": limit, "offset": offset})
        if not r.ok:
            return {"status": r.status, "reason": r.reason, "records": []}
        j = r.json()
        return {"status": "ok", "title": j.get("title"), "total": j.get("total"), "fields": j.get("field"),
                "records": j.get("records", [])}

    def harvest(self, db: Session, resource_id: str | None = None, title: str = "crime", limit: int = 500, **_) -> SourceReport:
        """Store a statistics resource as a STATS document (used by the hotspot map, not the entity graph)."""
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        if not resource_id:
            hits = self.search(title, 10)
            if not hits:
                rep.status, rep.reason = "unavailable", "no official datasets found"
                return rep
            resource_id = hits[0]["resource_id"]
        res = self.resource(resource_id, limit)
        if res.get("status") != "ok":
            rep.status, rep.reason = "unavailable", res.get("reason", "")
            return rep
        svc = IngestionService(db)
        svc._doc("STATS", f"data.gov.in: {res.get('title') or resource_id}", "",
                 {"resource_id": resource_id, "fields": res.get("fields"), "records": res["records"][:limit],
                  "total": res.get("total"), "source": "datagovin"}, records=len(res["records"]))
        db.commit()
        rep.records, rep.documents = len(res["records"]), 1
        rep.details = {"resource_id": resource_id, "title": res.get("title"), "total": res.get("total")}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep


@register
class NCRBConnector(Connector):
    """NCRB publishes `Disallow: /` in robots.txt, so this connector never crawls ncrb.gov.in.

    NCRB's machine-readable channel is the Open Government Data platform, where it is a listed
    publisher. `harvest` therefore pulls the NCRB-published datasets from data.gov.in and records
    the year-wise publication URL for analysts to open in a browser.
    """

    name = "ncrb"
    title = "NCRB - Crime in India (via data.gov.in)"
    description = ("NCRB statistical publications. ncrb.gov.in disallows crawlers, so data is taken from NCRB's "
                   "official datasets on data.gov.in; publication PDFs are linked for manual download.")
    homepage = "https://api.data.gov.in/lists?format=json&limit=1&api-key=" + SAMPLE_KEY
    licence = "Government Open Data License - India (GODL)"
    attribution = "National Crime Records Bureau, Ministry of Home Affairs (via OGD Platform India)"
    rate_limit = 3.0
    respect_robots = False  # the probe/harvest only ever touch the data.gov.in API, never ncrb.gov.in

    def probe(self) -> SourceReport:
        rep = super().probe()
        rep.details["policy"] = "ncrb.gov.in publishes 'Disallow: /'; connector serves NCRB data via data.gov.in only"
        return rep

    @staticmethod
    def publication_url(year: int = 2024) -> str:
        return f"https://www.ncrb.gov.in/crime-in-india-year-wise.html?year={year}&keyword="

    def datasets(self, limit: int = 40) -> list[dict]:
        dg = DataGovInConnector(offline=self.offline)
        seen, out = set(), []
        for q in ("Crime in India", "cognizable crime"):
            for rec in dg.search(q, limit, official_only=True):
                if rec["resource_id"] in seen:
                    continue
                if any("Crime Records" in o or "Home Affairs" in o for o in rec["org"]):
                    seen.add(rec["resource_id"])
                    out.append(rec)
            if len(out) >= limit:
                break
        return out[:limit]

    def harvest(self, db: Session, year: int = 2024, max_datasets: int = 3, rows: int = 300, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        ds = self.datasets(12)
        if not ds:
            rep.status, rep.reason = "unavailable", "data.gov.in returned no NCRB datasets (rate limited?)"
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep
        dg = DataGovInConnector(offline=self.offline)
        svc = IngestionService(db)
        loaded = []
        for rec in ds[:max_datasets]:
            res = dg.resource(rec["resource_id"], rows)
            if res.get("status") != "ok":
                continue
            svc._doc("STATS", f"NCRB: {res.get('title') or rec['title']}", "",
                     {"resource_id": rec["resource_id"], "fields": res.get("fields"), "records": res["records"],
                      "total": res.get("total"), "org": rec["org"], "source": "ncrb", "publication_url": self.publication_url(year)},
                     records=len(res["records"]))
            loaded.append({"title": rec["title"][:90], "rows": len(res["records"]), "total": res.get("total")})
        db.commit()
        rep.records = sum(x["rows"] for x in loaded)
        rep.documents = len(loaded)
        rep.status = "ok" if loaded else "unavailable"
        rep.reason = "" if loaded else "datasets found but resource fetch failed"
        rep.details = {"robots": "ncrb.gov.in disallows crawling; served from data.gov.in", "datasets": loaded,
                       "publication_url": self.publication_url(year), "available": [d["title"][:80] for d in ds]}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep


@register
class WantedListsConnector(Connector):
    name = "wanted"
    title = "NIA & state police wanted / proclaimed-offender notices"
    description = "Public most-wanted and proclaimed-offender pages from NIA and state police portals."
    homepage = "https://nia.gov.in/most-wanted-photos"
    licence = "Public notices (Government of India / state governments)"
    attribution = "National Investigation Agency; Uttar Pradesh Police; Assam Police"
    rate_limit = 3.0

    # page -> (label, url, extraction modes). Pages that render their list client-side ("Your browser does
    # not support JavaScript") are table-only here and get real content via the browser connector.
    PAGES = {
        "nia": ("NIA Most Wanted", "https://nia.gov.in/most-wanted-photos", ("alt", "table")),
        "nia_cases": ("NIA Cases (FIR list)", "https://nia.gov.in/nia-cases", ("table",)),
        "up": ("Uttar Pradesh Police Most Wanted", "https://uppolice.gov.in/en/MostWanted", ("table",)),
        "assam": ("Assam Police Most Wanted", "https://police.assam.gov.in/information-services/most-wanted", ("table", "alt")),
    }
    NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]\.|@\s*[A-Z][a-z]+)){1,4})\b")
    STOP = {"Most Wanted", "National Investigation", "Investigation Agency", "Skip Main", "Main Content", "Screen Reader",
            "Government Of", "Uttar Pradesh", "Police Station", "Home Page", "View FIR", "Read More", "Text Size"}

    UI_WORDS = {"icon", "logo", "emblem", "banner", "arrow", "text size", "screen reader", "skip", "menu", "search", "close",
                "sitemap", "login", "home", "toggle", "increase", "decrease", "reset", "english", "hindi", "accessibility"}
    # tokens that never occur inside an Indian personal name but are common in page chrome / notice headings
    NOT_NAME_TOKENS = {"act", "media", "press", "release", "photo", "photos", "cases", "case", "view", "share", "input", "about",
                       "terror", "terrorist", "activities", "contact", "us", "others", "recruitment", "local", "police", "accused",
                       "status", "proclaimed", "offender", "offenders", "officer", "court", "wanted", "most", "notice", "reward",
                       "arrested", "absconding", "national", "investigation", "agency", "state", "district", "station", "unit",
                       "branch", "list", "details", "date", "name", "father", "address", "read", "more", "click", "here", "new",
                       "delhi", "mumbai", "india", "government", "ministry", "home", "affairs", "public", "information", "services",
                       "parentage", "range", "officials", "ps", "hotel", "behind", "dist", "tender", "vision", "helpline", "work",
                       "good", "app", "download", "title", "organisation", "verification", "tenant", "gallery", "awards", "facilities",
                       "control", "room", "dept", "wing", "brigade", "line", "traffic", "missing", "persons", "complaint",
                       "registration", "cyber", "crime", "women", "fire", "economic", "offences", "citizen", "near", "village",
                       "road", "nagar", "colony", "bihar", "pradesh", "uttar", "assam", "rifles"}

    def _clean_person(self, raw: str) -> str | None:
        n = re.sub(r"\s+", " ", raw).strip(" .,-")
        n = re.sub(r"\s*\b(?:alias(?:es)?|@.*|a\.k\.a\.?.*)$", "", n, flags=re.I).strip()
        low = n.lower()
        if any(w in low for w in self.UI_WORDS) or n in self.STOP or any(s in n for s in self.STOP):
            return None
        toks = n.split()
        # a person name: 2-4 tokens, each starting with a capital, no long all-caps runs, no digits, no chrome vocabulary
        if not (2 <= len(toks) <= 4) or any(re.search(r"\d", t) for t in toks):
            return None
        if any(t.lower().strip(".") in self.NOT_NAME_TOKENS for t in toks):
            return None
        if not all(t[0].isupper() for t in toks) or len(n) > 45:
            return None
        if sum(1 for t in toks if t.isupper() and len(t) > 3) > 1:  # "NIA NATIONAL INVESTIGATION" style
            return None
        return n

    def extract_table_names(self, html_text: str) -> list[str]:
        """State portals publish wanted lists as tables: read the 'Name' column explicitly."""
        names: list[str] = []
        for table in re.findall(r"<table.*?</table>", html_text, re.S | re.I):
            rows = re.findall(r"<tr.*?</tr>", table, re.S | re.I)
            if len(rows) < 2:
                continue
            header = [self.strip_html(c).strip().lower() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S | re.I)]
            idx = next((i for i, h in enumerate(header) if re.search(r"\bname\b", h) and not re.search(r"father|parent|station|court", h)), None)
            if idx is None:
                continue
            for row in rows[1:]:
                cells = [self.strip_html(c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S | re.I)]
                if idx < len(cells):
                    raw = re.split(r"\s+(?:s/o|d/o|w/o|@|alias)\s+", cells[idx], flags=re.I)[0]
                    n = self._clean_person(raw.title() if raw.isupper() else raw)
                    if n:
                        names.append(n)
        return names

    def extract_names(self, html_text: str, modes: tuple[str, ...] = ("alt", "table", "prose")) -> list[str]:
        names: list[str] = []
        if "alt" in modes:
            for alt in re.findall(r'<img[^>]+alt="([^"]{4,80})"', html_text):
                if re.fullmatch(r"[A-Za-z .@'\-()]+", alt):
                    n = self._clean_person(alt)
                    if n:
                        names.append(n)
        if "table" in modes:
            names += self.extract_table_names(html_text)
        if "prose" in modes and len(names) < 3:  # prose fallback only when the page has no structured list
            text = self.strip_html(html_text)
            for m in self.NAME_RE.finditer(text):
                n = self._clean_person(m.group(1))
                if not n or len(n.split()) > 3:
                    continue
                ctx = text[max(0, m.start() - 60): m.end() + 60].lower()
                if any(k in ctx for k in ("wanted", "accused", "absconder", "proclaimed", "reward", "arrest")):
                    names.append(n)
        return list(dict.fromkeys(names))

    def harvest(self, db: Session, pages: list[str] | None = None, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        svc = IngestionService(db)
        from ..ingestion.ner import PERSON
        from ..graph.store import add_entity_evidence

        got, blocked, total_names = [], [], 0
        for key in pages or list(self.PAGES):
            label, url, modes = self.PAGES[key]
            r = self.fetch(url)
            if not r.ok:
                blocked.append({"page": label, "status": r.status, "reason": r.reason})
                continue
            names = self.extract_names(r.text, modes)
            if not names and "does not support javascript" in r.text.lower():
                blocked.append({"page": label, "status": "unavailable", "reason": "list is rendered client-side; use the browser connector"})
                continue
            text = self.strip_html(r.text)[:20000]
            # store the page for provenance but do NOT run narrative NER over navigation chrome
            doc = svc._doc("INTEL", f"{label} (public notice)", text, {"url": url, "source": "wanted", "names": names})
            anchor = svc.resolver.resolve("REPORT", f"{label} (public notice)", {"url": url, "document_id": doc.id})
            for n in names:
                p = svc.resolver.resolve(PERSON, n, {"wanted_notice": label, "source": "wanted-list"})
                svc.acc.add(p.id, anchor.id, "WANTED_IN", weight=3.0, confidence=0.85, doc_id=doc.id,
                            snippet=f"Listed on {label}", extractor="structured")
                add_entity_evidence(db, doc.id, p.id, f"Listed on {label}: {n}", 0.85, None, "structured")
            total_names += len(names)
            got.append({"page": label, "names": len(names), "cached": r.from_cache})
        svc._finish()
        rep.records, rep.documents = total_names, len(got)
        rep.status = "ok" if got else "unavailable"
        rep.details = {"pages": got, "blocked": blocked}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep
