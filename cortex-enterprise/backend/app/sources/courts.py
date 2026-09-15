"""
Indian court judgments from the AWS Open Data Registry (mirrored from eCourts).

  s3://indian-supreme-court-judgments   1950-2025, Parquet metadata per year
  s3://indian-high-court-judgments      25 High Courts, Parquet per year/court/bench, PDF links

No auth, no CAPTCHA - this is the legitimately published copy of the eCourts data.
Metadata alone gives us CASE nodes with petitioner / respondent parties (real Indian
names, frequently with `@` aliases), judge, CNR, dates and disposal. Optional PDF text
extraction feeds the narrative NER for fact-heavy criminal appeals.
"""
from __future__ import annotations

import io
import re
import time
from datetime import datetime, timezone

import polars as pl
from sqlalchemy.orm import Session

from ..ingestion.ner import CASE, PERSON, ORGANIZATION
from ..ingestion.pipeline import IngestionService, _dt
from .base import Connector, SourceReport, register

SC = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"
HC = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com"
STATE_RE = re.compile(r"\b(?:THE\s+)?(?:STATE|UNION|GOVT\.?|GOVERNMENT|CBI|N\.?C\.?B\.?|NARCOTICS CONTROL BUREAU|"
                      r"DIRECTORATE|ENFORCEMENT|COMMISSIONER|INSPECTOR|SUPERINTENDENT|MUNICIPAL|CORPORATION|BANK|"
                      r"LIMITED|LTD|PVT|COMPANY|BOARD|AUTHORITY|UNIVERSITY|TRUST|SOCIETY)\b", re.I)
CRIMINAL_HINT = re.compile(r"\b(STATE OF|CBI|NCB|NARCOTICS|ENFORCEMENT|UNION OF INDIA|POLICE)\b", re.I)


def _party_type(name: str) -> str:
    return ORGANIZATION if STATE_RE.search(name) else PERSON


PARTY_STOP = re.compile(r"^(?:ORS?|ANR|OTHERS?|ANOTHER|ETC\.?|SONS?|BROS?|CO\.?|M/S|THROUGH|THRU|REP\.? BY|BY LRS?|LRS?|"
                        r"DECEASED|DEAD|SINCE|HEIRS|LEGAL HEIRS|SECRETARY|PRINCIPAL|MANAGER|DIRECTOR)\b\.?$", re.I)


def _split_parties(s: str) -> list[str]:
    s = re.sub(r"\s*(?:&|AND)\s*(?:ORS?|ANR|OTHERS?|ANOTHER)\.?(?:\s*ETC\.?)?\s*$", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+ETC\.?\s*$", "", s, flags=re.I)
    s = re.sub(r"\b(?:THROUGH|THRU|REP\.?\s+BY)\b.*$", "", s, flags=re.I)
    parts = re.split(r"\s*(?:,|&|\bAND\b)\s*", s, flags=re.I)
    out = []
    for p in parts:
        p = p.strip(" .-")
        if len(p) <= 2 or PARTY_STOP.match(p) or p.upper() in ("ORS", "ANR", "OTHERS", "ETC"):
            continue
        # a person needs at least two name tokens; organisations may be one word
        if not STATE_RE.search(p) and len(re.findall(r"[A-Za-z]{2,}", p)) < 2:
            continue
        out.append(p)
    return out[:4]


@register
class CourtsConnector(Connector):
    name = "courts"
    title = "Indian Supreme Court & High Court judgments (AWS Open Data)"
    description = ("Official eCourts judgment metadata for the Supreme Court (1950-2025) and 25 High Courts, "
                   "published on the AWS Open Data Registry. Parties, judges, CNR, dates, PDF links.")
    homepage = SC + "/?list-type=2&max-keys=1"
    licence = "Public court records; dataset CC-BY-4.0 (AWS Open Data Registry)"
    attribution = "eCourts India via AWS Open Data Registry (indian-supreme-court-judgments, indian-high-court-judgments)"
    rate_limit = 0.3
    respect_robots = False
    timeout = 180.0

    def list_keys(self, bucket: str, prefix: str, max_keys: int = 200) -> list[str]:
        r = self.fetch(f"{bucket}/", params={"list-type": "2", "max-keys": max_keys, "prefix": prefix}, cache_key=f"s3:{bucket}:{prefix}")
        return re.findall(r"<Key>([^<]+)</Key>", r.text) if r.ok else []

    def supreme_court(self, year: int) -> pl.DataFrame | None:
        r = self.fetch(f"{SC}/metadata/parquet/year={year}/metadata.parquet", cache_key=f"sc:{year}")
        return pl.read_parquet(io.BytesIO(r.content)) if r.ok else None

    # friendly names -> S3 court codes (from the bucket layout)
    HC_ALIASES = {
        "bombay": "court=27_1/", "mumbai": "court=27_1/", "goa": "bench=hcbgoa", "aurangabad": "bench=hcaurdb",
        "calcutta": "court=19_16/", "kolkata": "court=19_16/", "gujarat": "court=24_17/", "karnataka": "court=29_3/",
        "kerala": "court=32_4/", "madras": "court=33_10/", "chennai": "court=33_10/", "punjab": "court=3_22/",
        "haryana": "court=3_22/", "telangana": "court=36_29/", "hyderabad": "court=36_29/", "andhra": "court=28_2/",
        "madhya pradesh": "court=23_23/", "mp": "court=23_23/", "patna": "court=10_8/", "bihar": "court=10_8/",
        "jammu": "court=1_12/", "kashmir": "court=1_12/", "chhattisgarh": "court=22_18/", "jharkhand": "court=20_7/",
        "uttarakhand": "court=5_15/", "meghalaya": "court=17_21/", "manipur": "court=14_25/", "sikkim": "court=11_24/",
        "gauhati": "court=18_6/", "assam": "court=18_6/",
    }

    def high_court_files(self, year: int, court_match: str | None = None) -> list[str]:
        keys = [k for k in self.list_keys(HC, f"metadata/parquet/year={year}/", 1000) if k.endswith(".parquet")]
        if court_match:
            needle = self.HC_ALIASES.get(court_match.strip().lower(), court_match).lower()
            keys = [k for k in keys if needle in k.lower()]
        return keys

    def high_court(self, key: str) -> pl.DataFrame | None:
        r = self.fetch(f"{HC}/{key}", cache_key=f"hc:{key}")
        return pl.read_parquet(io.BytesIO(r.content)) if r.ok else None

    # ------------------------------------------------------------------ harvest
    def harvest(self, db: Session, court: str = "sc", year: int = 2024, limit: int = 300, criminal_only: bool = True,
                bench: str | None = None, keyword: str | None = None, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        frames: list[pl.DataFrame] = []
        if court == "sc":
            df = self.supreme_court(year)
            if df is not None:
                frames.append(df.with_columns(pl.lit("Supreme Court of India").alias("court")) if "court" not in df.columns else df)
        else:
            for k in self.high_court_files(year, bench)[:12]:
                df = self.high_court(k)
                if df is not None and df.height:
                    frames.append(df)
        if not frames:
            rep.status, rep.reason = "unavailable", "no judgment metadata reachable"
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep
        df = pl.concat(frames, how="diagonal")
        if "title" not in df.columns:
            rep.status, rep.reason = "error", "unexpected schema"
            return rep
        if criminal_only:
            df = df.filter(pl.col("title").str.contains(r"(?i)STATE OF|CBI|N\.?C\.?B|NARCOTICS|ENFORCEMENT|UNION OF INDIA|POLICE|CRL|CRIMINAL"))
        if keyword:
            df = df.filter(pl.col("title").str.contains(f"(?i){re.escape(keyword)}"))
        df = df.head(limit)

        svc = IngestionService(db)
        from ..graph.store import add_entity_evidence, add_event

        cases = parties = 0
        for row in df.iter_rows(named=True):
            title = (row.get("title") or "").strip()
            if not title:
                continue
            m = re.split(r"\s+(?:versus|vs\.?|v\.)\s+", title, maxsplit=1, flags=re.I)
            pet, resp = (m[0], m[1]) if len(m) == 2 else (row.get("petitioner") or title, row.get("respondent") or "")
            pet = re.sub(r"^[A-Z/]+\d+/\d+\s+of\s+", "", pet, flags=re.I)
            when = _dt(row.get("decision_date"))
            cnr = row.get("cnr") or row.get("case_id") or title[:60]
            court_name = row.get("court") or ("Supreme Court of India" if court == "sc" else "High Court")
            meta = {k: (str(v) if v is not None else None) for k, v in row.items() if k not in ("raw_html", "description")}
            doc = svc._doc("JUDGMENT", f"{court_name}: {title[:200]}", (row.get("description") or "")[:4000], meta, when)
            case = svc.resolver.resolve(CASE, f"{cnr} {title[:80]}", {
                "court": court_name, "cnr": row.get("cnr"), "citation": row.get("citation"), "judge": row.get("judge"),
                "decision_date": str(row.get("decision_date")), "disposal": row.get("disposal_nature"),
                "pdf": row.get("pdf_link") or row.get("path"), "document_id": doc.id, "source": "eCourts/AWS"}, when)
            add_entity_evidence(db, doc.id, case.id, title, 1.0, when, "structured")
            ids = [case.id]
            for side, names in (("petitioner", _split_parties(pet)), ("respondent", _split_parties(resp))):
                for n in names:
                    et = _party_type(n)
                    alias = None
                    am = re.match(r"^(.+?)\s*@\s*(.+)$", n)
                    if am:
                        n, alias = am.group(1).strip(), am.group(2).strip()
                    label = n.title() if et == PERSON else n
                    p = svc.resolver.resolve(et, label, {"court_role": side, "source": "eCourts"}, when, aliases=[alias] if alias else None)
                    rel = "PETITIONER_IN" if side == "petitioner" else "RESPONDENT_IN"
                    if et == PERSON and CRIMINAL_HINT.search(resp if side == "petitioner" else pet):
                        rel = "ACCUSED_IN" if side == "petitioner" else "COMPLAINANT_IN"
                    svc.acc.add(p.id, case.id, rel, weight=2.0, confidence=0.95, doc_id=doc.id, snippet=title, extractor="structured")
                    ids.append(p.id)
                    parties += 1
            judge = row.get("judge")
            if judge:
                for j in _split_parties(re.sub(r"HON'?BLE|JUSTICE|MR\.?|MRS\.?|MS\.?", "", judge, flags=re.I))[:3]:
                    jp = svc.resolver.resolve(PERSON, j.title(), {"court_role": "judge", "source": "eCourts"}, when)
                    svc.acc.add(jp.id, case.id, "ADJUDICATED", weight=0.5, confidence=0.9, doc_id=doc.id, snippet=f"Judge: {judge}", extractor="structured")
            if when:
                add_event(db, doc.id, "JUDGMENT", when, ids, f"{court_name}: {title[:140]}", {"disposal": row.get("disposal_nature"), "cnr": row.get("cnr")})
            cases += 1
        svc._finish()
        rep.records, rep.documents = cases, cases
        rep.details = {"court": court, "year": year, "cases": cases, "parties": parties, "criminal_only": criminal_only}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep
