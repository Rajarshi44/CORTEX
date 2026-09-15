"""
GLEIF connector - the global Legal Entity Identifier registry.

Free, no API key, official (GLEIF is the LEI regulator). Gives us two things
MCA's CAPTCHA-walled portal would have given us, legitimately:

  * 392,552 Indian legal entities with LEI, legal name, status, address and
    `registeredAs` (the CIN / GSTIN)
  * a real corporate OWNERSHIP GRAPH - direct/ultimate parent and child
    relationships, including cross-border subsidiaries

Verified live: TATA CONSULTANCY SERVICES -> parent TATA SONS PRIVATE LIMITED,
5 children (India, Canada, Mexico); STATE BANK OF INDIA -> 15 children.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ingestion.ner import ORGANIZATION
from ..ingestion.pipeline import IngestionService
from .base import Connector, SourceReport, register

API = "https://api.gleif.org/api/v1"
GOLDEN = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes"


@register
class GleifConnector(Connector):
    name = "gleif"
    title = "GLEIF - Global Legal Entity Identifier"
    description = ("Official global company registry: legal entities with LEI/CIN/GSTIN plus the "
                   "corporate parent-child ownership graph. Free, no API key.")
    homepage = "https://api.gleif.org/api/v1/lei-records?page[size]=1"
    licence = "CC0 1.0 (GLEIF public data)"
    attribution = "Global Legal Entity Identifier Foundation (GLEIF)"
    rate_limit = 0.35
    respect_robots = False  # documented public JSON:API, not a crawled website

    HEADERS = {"Accept": "application/vnd.api+json"}

    # ------------------------------------------------------------------ raw api
    def search_entities(self, name: str | None = None, country: str = "IN", limit: int = 25) -> list[dict]:
        params: dict[str, str | int] = {"page[size]": min(limit, 200)}
        if name:
            params["filter[entity.legalName]"] = name
        if country:
            params["filter[entity.legalAddress.country]"] = country
        r = self.fetch(f"{API}/lei-records", params=params, headers=self.HEADERS)
        if not r.ok:
            return []
        return r.json().get("data", [])

    def relations(self, lei: str, kind: str) -> list[dict]:
        """kind: direct-parent | ultimate-parent | direct-children | ultimate-children"""
        r = self.fetch(f"{API}/lei-records/{lei}/{kind}", params={"page[size]": 50}, headers=self.HEADERS)
        if not r.ok:
            return []
        d = r.json().get("data")
        if d is None:
            return []
        return [d] if isinstance(d, dict) else d

    def bulk_manifest(self, kind: str = "rr") -> dict:
        """Latest Golden Copy bulk file URLs. kind 'rr' = relationship records, 'lei2' = entities."""
        r = self.fetch(f"{GOLDEN}/{kind}", params={"page": 1, "per_page": 1}, use_cache=False)
        if not r.ok:
            return {}
        data = r.json().get("data") or [{}]
        return data[0] if data else {}

    # ------------------------------------------------------------------ mapping
    @staticmethod
    def _entity_fields(rec: dict) -> dict:
        a = rec.get("attributes", {})
        e = a.get("entity", {})
        addr = e.get("legalAddress", {}) or {}
        return {
            "lei": a.get("lei"),
            "name": (e.get("legalName") or {}).get("name") or "",
            "status": e.get("status"),
            "country": addr.get("country"),
            "city": addr.get("city"),
            "registered_as": e.get("registeredAs"),
            "category": e.get("category"),
            "legal_form": ((e.get("legalForm") or {}).get("id")),
            "incorporation_date": (a.get("registration") or {}).get("initialRegistrationDate"),
        }

    # ------------------------------------------------------------------ harvest
    def harvest(self, db: Session, query: str | None = None, country: str = "IN", limit: int = 40,
                depth: int = 1, **_) -> SourceReport:
        """Ingest entities matching `query` plus their ownership relationships."""
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        records = self.search_entities(query, country, limit)
        if not records:
            rep.status = "unavailable"
            rep.reason = "no records returned (source blocked or empty result)"
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep

        svc = IngestionService(db)
        doc = svc._doc("GLEIF", f"GLEIF corporate registry: {query or country} ({len(records)} entities)", "",
                       {"query": query, "country": country, "source": "gleif"}, records=len(records))
        seen: dict[str, str] = {}   # lei -> entity id
        edges = 0

        def upsert(fields: dict):
            if not fields.get("name") or not fields.get("lei"):
                return None
            lei = fields["lei"]
            if lei in seen:
                return seen[lei]
            ent = svc.resolver.resolve(ORGANIZATION, fields["name"], {
                "lei": lei, "status": fields["status"], "country": fields["country"], "city": fields["city"],
                "registered_as": fields["registered_as"], "legal_form": fields["legal_form"],
                "incorporation_date": fields["incorporation_date"], "source": "GLEIF",
            })
            seen[lei] = ent.id
            from ..graph.store import add_entity_evidence

            add_entity_evidence(db, doc.id, ent.id,
                                f"GLEIF LEI {lei} - {fields['name']} ({fields['city']}, {fields['country']}), "
                                f"status {fields['status']}, registered as {fields['registered_as']}",
                                1.0, None, "structured")
            # city -> location edge
            if fields.get("city"):
                loc = svc._loc(str(fields["city"]).title())
                svc.acc.add(ent.id, loc.id, "LOCATED_AT", confidence=0.95, doc_id=doc.id,
                            snippet=f"Registered address: {fields['city']}, {fields['country']}", extractor="structured")
            return ent.id

        frontier = []
        for rec in records:
            f = self._entity_fields(rec)
            eid = upsert(f)
            if eid:
                frontier.append((f["lei"], eid))
        rep.records = len(frontier)

        # ownership graph
        for _ in range(max(0, depth)):
            nxt = []
            for lei, eid in frontier:
                for kind, rel, direction in (("direct-parent", "SUBSIDIARY_OF", "up"),
                                             ("direct-children", "SUBSIDIARY_OF", "down")):
                    for rec in self.relations(lei, kind):
                        f = self._entity_fields(rec)
                        other = upsert(f)
                        if not other:
                            continue
                        src, dst = (eid, other) if direction == "up" else (other, eid)
                        svc.acc.add(src, dst, rel, weight=3.0, confidence=1.0, doc_id=doc.id,
                                    snippet=f"GLEIF Level-2 ownership: {kind.replace('-', ' ')}", extractor="structured",
                                    attrs={"gleif_relationship": kind})
                        edges += 1
                        nxt.append((f["lei"], other))
            frontier = nxt
            if not frontier:
                break

        svc._finish()
        rep.documents = 1
        rep.details = {"entities": len(seen), "ownership_edges": edges, "query": query, "country": country}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep
