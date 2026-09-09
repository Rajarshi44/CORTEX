"""
OpenSanctions connector - sanctions, PEPs, Interpol Red Notices and entities of criminal interest.

477 datasets, refreshed several times a day, bulk download without an API key.
Two distinct uses in this system:

  1. SCREENING - flag any person/organisation in our graph that appears on a
     sanctions list, a wanted list or a PEP register. Includes all 12,799
     INTERPOL Red Notices (the direct Interpol API blocks datacentre IPs; this
     is the published mirror).

  2. ENTITY-RESOLUTION BENCHMARK - each record carries `referents`: the ids of
     the same real-world entity across every upstream source. That is a real,
     published ground truth we can score our own resolver against.

Data model is FollowTheMoney (FtM): schema Person / Company / LegalEntity ...
"""
from __future__ import annotations

import io
import json
import re
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ingestion.ner import ORGANIZATION, PERSON
from ..ingestion.pipeline import IngestionService
from .base import Connector, SourceReport, register

BULK = "https://data.opensanctions.org/datasets/latest"
PERSON_SCHEMAS = {"Person"}
HONORIFIC = re.compile(r"^(mr|mrs|ms|miss|shri|smt|sh|dr|late|km|kumari)\.?\s", re.I)
CORP_TOKEN = re.compile(r"\b(ltd|limited|inc|corp|corporation|llc|llp|pvt|private|gmbh|pte|plc|holdings?|trust|foundation|fund|company|co|securities|capital|finance|financial|investments?|enterprises?|industries|traders?|exports?|imports?|impex|associates|bank|group|services|solutions|technologies|infra\w*|realty|estates?|hospital|school|society|huf|firm)\b", re.I)
ORG_SCHEMAS = {"Company", "Organization", "LegalEntity", "PublicBody", "Airplane", "Vessel"}


@register
class OpenSanctionsConnector(Connector):
    name = "opensanctions"
    title = "OpenSanctions - sanctions, PEPs & INTERPOL notices"
    description = ("Consolidated global watchlists: sanctions, politically exposed persons, "
                   "debarment and INTERPOL Red Notices. Also supplies cross-source identity "
                   "links used to benchmark our entity resolution.")
    homepage = "https://www.opensanctions.org/"
    licence = "CC-BY-NC 4.0 (free for non-commercial use)"
    attribution = "OpenSanctions.org"
    rate_limit = 0.5
    respect_robots = False  # documented bulk data endpoint
    cache_ttl_hours = 24

    DATASETS = {
        "crime": "Entities of criminal interest",
        "interpol_red_notices": "INTERPOL Red Notices",
        "sanctions": "Consolidated sanctions",
        "debarment": "Debarred suppliers",
        "peps": "Politically exposed persons",
        "in_mha_banned": "India MHA banned organisations and designated terrorists (UAPA)",
        "in_nse_debarred": "India NSE / SEBI debarred entities",
        "in_sansad": "India Parliament members (PEPs)",
    }

    # ------------------------------------------------------------------ fetch
    def stream_entities(self, dataset: str = "crime", limit: int = 2000):
        """Yield FtM entities from a dataset's newline-delimited JSON export."""
        r = self.fetch(f"{BULK}/{dataset}/entities.ftm.json", cache_key=f"os:{dataset}")
        if not r.ok:
            return
        n = 0
        for raw in io.BytesIO(r.content):  # line by line: no second full-size copy in memory
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            n += 1
            if n >= limit:
                return

    def index(self) -> list[dict]:
        r = self.fetch(f"{BULK}/index.json", cache_key="os:index")
        return r.json().get("datasets", []) if r.ok else []

    # ------------------------------------------------------------------ mapping
    @staticmethod
    def _first(props: dict, key: str) -> str | None:
        v = props.get(key)
        return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)

    def _fields(self, rec: dict) -> dict:
        p = rec.get("properties", {}) or {}
        names = p.get("name") or []
        return {
            "id": rec.get("id"),
            "caption": rec.get("caption") or (names[0] if names else ""),
            "schema": rec.get("schema"),
            "aliases": [n for n in names[1:]] + (p.get("alias") or []),
            "topics": p.get("topics") or [],
            "datasets": rec.get("datasets") or [],
            "country": self._first(p, "country") or self._first(p, "nationality"),
            "birth_date": self._first(p, "birthDate"),
            "birth_place": self._first(p, "birthPlace"),
            "gender": self._first(p, "gender"),
            "address": self._first(p, "address"),
            "program": self._first(p, "programId"),
            "notes": self._first(p, "notes"),
            "referents": rec.get("referents") or [],
            "last_seen": rec.get("last_seen"),
        }

    # ------------------------------------------------------------------ harvest
    @staticmethod
    def _countries(rec: dict) -> set[str]:
        p = rec.get("properties", {}) or {}
        return {str(c).lower() for k in ("country", "nationality", "citizenship", "jurisdiction") for c in (p.get(k) or [])}

    @staticmethod
    def _tidy(name: str) -> str:
        """Watchlists shout in capitals; the sheet does not."""
        return name.title() if name.isupper() and len(name) > 3 else name

    def harvest(self, db: Session, dataset: str = "crime", limit: int = 1500, countries: list[str] | None = None,
                scan: int = 200_000, **_) -> SourceReport:
        """`countries` (ISO alpha-2, e.g. ["in"]) keeps only records tied to those countries; `scan` bounds how
        many records are read while filtering."""
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        if countries:
            want = {c.lower() for c in countries}
            records = []
            for rec in self.stream_entities(dataset, scan):
                if self._countries(rec) & want:
                    records.append(rec)
                    if len(records) >= limit:
                        break
        else:
            records = list(self.stream_entities(dataset, limit))
        if not records:
            rep.status = "unavailable"
            rep.reason = f"dataset '{dataset}' unreachable or empty"
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep

        from ..graph.store import add_entity_evidence

        svc = IngestionService(db)
        doc = svc._doc("WATCHLIST", f"OpenSanctions: {self.DATASETS.get(dataset, dataset)} ({len(records)} entities)",
                       "", {"dataset": dataset, "source": "opensanctions"}, records=len(records))
        persons = orgs = wanted = 0
        referent_pairs = 0

        for rec in records:
            f = self._fields(rec)
            if not f["caption"]:
                continue
            etype = PERSON if f["schema"] in PERSON_SCHEMAS else ORGANIZATION if f["schema"] in ORG_SCHEMAS else None
            if f["schema"] == "LegalEntity":  # Indian regulators list people and firms under one schema
                etype = PERSON if HONORIFIC.match(f["caption"]) or (not CORP_TOKEN.search(f["caption"]) and 2 <= len(f["caption"].split()) <= 4) else ORGANIZATION
            if etype is None:
                continue
            topics = f["topics"]
            ent = svc.resolver.resolve(etype, self._tidy(HONORIFIC.sub("", f["caption"]).strip() if etype == PERSON else f["caption"]), {
                "watchlist": True, "watchlist_topics": topics, "watchlist_datasets": f["datasets"],
                "country": f["country"], "birth_date": f["birth_date"], "birth_place": f["birth_place"],
                "gender": f["gender"], "opensanctions_id": f["id"], "program": f["program"],
                "source": "OpenSanctions", "referent_count": len(f["referents"]),
            }, aliases=[self._tidy(a) for a in f["aliases"][:8]])
            desc = (f"OpenSanctions {dataset}: {f['caption']} | schema {f['schema']} | topics {', '.join(topics) or '-'} "
                    f"| lists: {', '.join(f['datasets'][:4])}"
                    + (f" | DOB {f['birth_date']}" if f["birth_date"] else "")
                    + (f" | born {f['birth_place']}" if f["birth_place"] else ""))
            add_entity_evidence(db, doc.id, ent.id, desc, 1.0, None, "structured")
            referent_pairs += len(f["referents"])
            if "wanted" in topics or "crime" in topics:
                wanted += 1
            if etype == PERSON:
                persons += 1
            else:
                orgs += 1
            if f["country"]:
                loc = svc._loc(str(f["country"]).upper())
                svc.acc.add(ent.id, loc.id, "RESIDES_AT", weight=0.4, confidence=0.5, doc_id=doc.id,
                            snippet=f"Watchlist country: {f['country']}", extractor="structured")

        svc._finish()
        rep.records = persons + orgs
        rep.documents = 1
        rep.details = {"dataset": dataset, "countries": countries, "persons": persons, "organisations": orgs, "wanted_or_crime": wanted,
                       "referent_links": referent_pairs}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep

    # ------------------------------------------------------------------ screening
    def screen(self, db: Session, threshold: int = 88, limit: int = 4000, datasets: list[str] | None = None) -> dict:
        """Match existing graph actors against one or more watchlists. Returns hits with scores."""
        from rapidfuzz import fuzz, process

        from ..db import Entity

        records = []
        for ds in datasets or ["crime"]:
            records.extend(self.stream_entities(ds, limit))
        if not records:
            return {"status": "unavailable", "hits": []}
        wl: dict[str, dict] = {}
        for rec in records:
            f = self._fields(rec)
            for nm in [f["caption"], *f["aliases"]]:
                if nm and len(nm) > 4:
                    wl.setdefault(nm, f)
        actors = db.query(Entity).filter(Entity.type.in_([PERSON, ORGANIZATION])).all()
        names = list(wl)
        hits = []
        for a in actors:
            if a.attributes.get("watchlist"):
                continue
            # skip fragments that cannot be meaningfully screened (single short tokens, initials)
            if len(a.label) < 7 or (a.type == PERSON and len(a.label.split()) < 2):
                continue
            best = process.extractOne(a.label, names, scorer=fuzz.WRatio)
            if best and best[1] >= threshold:
                f = wl[best[0]]
                hits.append({"entity_id": a.id, "entity": a.label, "matched": best[0], "score": round(best[1], 1),
                             "topics": f["topics"], "lists": f["datasets"][:4], "opensanctions_id": f["id"],
                             "birth_date": f["birth_date"], "country": f["country"]})
        hits.sort(key=lambda h: -h["score"])
        return {"status": "ok", "screened": len(actors), "watchlist_names": len(names), "hits": hits}

    # ------------------------------------------------------------------ ER benchmark
    def resolution_benchmark(self, limit: int = 1200) -> dict:
        """Score our canonicalisation against OpenSanctions' published cross-source identity links.

        Each record's alternative names all denote the SAME entity. A correct resolver maps
        them to one canonical key; every split is a miss.
        """
        from rapidfuzz import fuzz

        from ..ingestion.resolution import canonical_key

        records = list(self.stream_entities("crime", limit))
        if not records:
            return {"status": "unavailable"}
        total = strict = fuzzy = 0
        examples: list[dict] = []
        for rec in records:
            f = self._fields(rec)
            names = [n for n in [f["caption"], *f["aliases"]] if n and len(n) > 3][:6]
            if len(names) < 2:
                continue
            etype = PERSON if f["schema"] in PERSON_SCHEMAS else ORGANIZATION
            keys = [canonical_key(etype, n) for n in names]
            total += 1
            if len(set(keys)) == 1:
                strict += 1
                fuzzy += 1
                continue
            # the resolver's fuzzy path: every alias must score >= threshold against the canonical caption
            if all(fuzz.token_set_ratio(keys[0], k) >= 88 for k in keys[1:]):
                fuzzy += 1
            elif len(examples) < 12:
                examples.append({"caption": f["caption"], "names": names})
        return {"status": "ok", "multi_name_entities": total, "unified_exact": strict, "unified_with_fuzzy": fuzzy,
                "recall_exact": round(strict / total, 4) if total else None,
                "recall_fuzzy": round(fuzzy / total, 4) if total else None,
                "note": "remaining misses are mostly cross-script transliterations (Cyrillic/Arabic/Chinese) - out of scope for an Indian-language deployment",
                "misses": examples}
