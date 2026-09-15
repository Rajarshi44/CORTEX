"""
Multi-source ingestion pipeline.

Every source goes through the same stages:
  parse -> Document row -> entity mentions -> EntityResolver -> RelationshipAccumulator
        -> Evidence (provenance) -> TimelineEvents -> flush -> invalidate graph cache

Supported sources:
  FIR (json/text)  CDR (csv)  KYC (csv)  TRANSACTION (csv)  SURVEILLANCE (json)  SOCIAL (json)  INTEL (json/text)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from dateutil import parser as dtparser
from sqlalchemy.orm import Session

from ..config import settings
from ..db import AnalysisSnapshot, Document
from ..graph.store import RelationshipAccumulator, add_entity_evidence, add_event, graph_cache
from . import geo
from .ner import (BANK_ACCOUNT, CASE, GOV_ID, LOCATION, ORGANIZATION, PERSON, PHONE, REPORT, SOCIAL_HANDLE,
                  VEHICLE, ExtractionResult, RuleNER)
from .resolution import EntityResolver, JunkMention

log = logging.getLogger("cna.ingest")

ProgressCb = Callable[[str, int, int], None]  # (stage, done, total)

ORG_HINT = re.compile(r"\b(pvt|ltd|llp|limited|traders|enterprises|agency|movers|realty|ventures|bank|corp|industries|"
                      r"logistics|builders|developers|infra|bullion|stores|shop|hotel|company|co\.)\b", re.I)


def _dt(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return _naive(v)
    s = str(v).strip()
    try:  # ISO 8601 first (YYYY-MM-DD[ HH:MM[:SS]]) - dateutil's dayfirst would misread it
        return _naive(datetime.fromisoformat(s.replace("T", " ").replace("Z", "")))
    except ValueError:
        pass
    try:
        return _naive(dtparser.parse(s, dayfirst=True))
    except (ValueError, OverflowError, TypeError):
        return None


def _naive(d: datetime) -> datetime:
    """All stored timestamps are naive UTC so comparisons across sources never mix aware/naive."""
    if d.tzinfo is not None:
        from datetime import timezone as _tz

        d = d.astimezone(_tz.utc).replace(tzinfo=None)
    return d


def _is_night(d: datetime | None) -> bool:
    return bool(d) and (d.hour >= 23 or d.hour < 5)


@dataclass
class IngestStats:
    documents: int = 0
    records: int = 0
    entities_created: int = 0
    entities_merged: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    events: int = 0
    llm_enriched: int = 0
    neural_enriched: int = 0
    identifiers_found: int = 0
    identifiers_rejected: int = 0
    sealed: int = 0
    watch_hits: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class IngestionService:
    def __init__(self, db: Session, progress: ProgressCb | None = None, use_llm: bool | None = None,
                 use_neural: bool | None = None, neural_labels: list[str] | None = None,
                 actor: str = "system", seal_documents: bool | None = None):
        self.db = db
        self.progress = progress or (lambda *_: None)
        self.resolver = EntityResolver(db)
        self.ner = RuleNER()
        self.acc = RelationshipAccumulator()
        self.stats = IngestStats()
        self.gazetteer = self.ner.gazetteer
        # Per-document LLM extraction is opt-in and OFF by default even when a key is configured:
        # one call costs tens of seconds, so a routine harvest of a few hundred documents would
        # otherwise silently become hours. Narration and the investigator stay available on the same
        # key; only this tier is gated. Pass use_llm=True, or set CNA_LLM_EXTRACTION_ENABLED, to run
        # it over a corpus worth the wait.
        if use_llm is None:
            from ..ai.llm import available as _llm_available

            self.use_llm = settings.llm_extraction_enabled and _llm_available()
        else:
            self.use_llm = use_llm
        if use_neural is None:
            from .neural_ner import neural_ner

            self.use_neural = neural_ner.available()
        else:
            self.use_neural = use_neural
        self.neural_labels = neural_labels
        self.actor = actor
        self.seal_documents = settings.evidence_ledger_enabled if seal_documents is None else seal_documents
        # Documents added since the last flush. Standing watches are checked against these and only
        # these, so a harvest of one new article does not rescan the whole corpus.
        self._run_doc_ids: list[str] = []
        self._refresh_dictionary()

    # ------------------------------------------------------------------ utils
    def _refresh_dictionary(self):
        self.ner.set_known(self.resolver.known_person_names(), self.resolver.known_org_names())

    def _doc(self, source_type: str, title: str, content: str, meta: dict | None = None, occurred_at: datetime | None = None,
             records: int = 1) -> Document:
        d = Document(id=str(uuid.uuid4()), source_type=source_type, title=title[:300], content=content, meta=meta or {},
                     occurred_at=occurred_at, record_count=records)
        self.db.add(d)
        self._run_doc_ids.append(d.id)
        self.stats.documents += 1
        if self.seal_documents:
            # tamper-evident chain of custody: seal the document at the moment of collection
            from ..graph.ledger import attest_document

            attest_document(self.db, self.actor, d.id, d.title, content or "", source_type, commit=False)
            self.stats.sealed += 1
        return d

    def _loc(self, name: str, seen: datetime | None = None):
        """
        Resolve a place, geocoding it where we can. Returns None for a mention that is not a place
        at all (a stopword, a bare ISO country code) so the caller drops the link rather than
        hanging it off an entity with no evidence behind it.
        """
        g = self.gazetteer.get(name) or {}
        attrs: dict = {"lat": g.get("lat"), "lon": g.get("lon")}
        if attrs["lat"] is None:  # not a bundled neighbourhood - try the wider gazetteer
            hit = geo.locate(name)
            if hit:
                attrs = {"lat": hit["lat"], "lon": hit["lon"], "geo_precision": hit["precision"],
                         "geo_matched": hit["matched"]}
        return self.resolver.resolve_opt(LOCATION, name, attrs, seen)

    @staticmethod
    def _event_point(source_type: str, title: str, text: str, meta: dict) -> dict | None:
        """
        Where a document-level event happened, in the terms each source actually gives us.

        JUDGMENT carries a court and a state party ("THE STATE OF BIHAR"); NEWS carries a desk
        ("Indian Express - Mumbai"); anything else falls back to the first place named in the text.
        """
        if source_type == "JUDGMENT":
            return geo.locate(meta.get("court"), meta.get("respondent"), meta.get("petitioner"), title)
        if source_type == "NEWS":
            return geo.locate(meta.get("feed"), title, text[:400])
        return geo.locate(meta.get("country"), title, text[:400])

    def _holder_entity(self, holder: str, seen: datetime | None):
        etype = ORGANIZATION if ORG_HINT.search(holder or "") else PERSON
        return self.resolver.resolve(etype, holder, {}, seen)

    def _finish(self):
        c, u = self.acc.flush(self.db)
        self.stats.relationships_created += c
        self.stats.relationships_updated += u
        self.stats.entities_created = self.resolver.new_entities
        self.stats.entities_merged = self.resolver.merges
        self.db.commit()
        self._fire_watches()
        for snap in self.db.query(AnalysisSnapshot).all():
            snap.stale = True
        self.db.commit()
        graph_cache.invalidate()
        self._refresh_dictionary()

    def _fire_watches(self):
        """Check the records that just arrived against every standing watch.

        Runs after the entities and evidence of this batch are committed and before the snapshot is
        marked stale, because a watch is about one document landing rather than about the shape of
        the corpus - it must not wait for the next analytics recompute. A failure here is recorded
        as a warning and never fails the ingestion: losing an alert is bad, losing the record it
        would have fired on is worse.
        """
        doc_ids, self._run_doc_ids = self._run_doc_ids, []
        if not doc_ids:
            return
        try:
            from ..watch.matcher import scan

            self.stats.watch_hits += len(scan(self.db, doc_ids))
        except Exception as exc:  # pragma: no cover - a watch must never break a harvest
            self.db.rollback()
            log.warning("standing-watch scan failed: %s", exc)
            self.stats.warnings.append(f"standing-watch scan failed: {exc}")

    # ------------------------------------------------------------------ unstructured text (FIR / INTEL / free text)
    def _apply_extraction(self, doc: Document, text: str, res: ExtractionResult, when: datetime | None,
                          anchor=None, anchor_rel: str = "MENTIONED_IN", extractor: str = "rules") -> dict[tuple[str, str], Any]:
        ents: dict[tuple[str, str], Any] = {}
        for m in res.mentions:
            attrs = {k: v for k, v in m.attrs.items() if k not in ("alias", "raw", "dictionary")}
            # A name read out of prose must not silently become an existing watchlist or registry
            # identity. "Ketan Agarwal" murdered in a Pune report is not the Ketan Agarwal on a US
            # exclusions list, and merging them puts a sanctions listing on a victim. Tagging every
            # text mention with one shared origin lets the resolver's cross-source guard split them
            # while still merging the same name across two articles.
            attrs.setdefault("source", "text")
            if m.type == LOCATION:
                g = self.gazetteer.get(m.text) or {}
                attrs.update({"lat": g.get("lat"), "lon": g.get("lon")})
                if attrs["lat"] is None:
                    hit = geo.locate(m.text)
                    if hit:
                        attrs.update({"lat": hit["lat"], "lon": hit["lon"], "geo_precision": hit["precision"],
                                      "geo_matched": hit["matched"]})
            aliases = [m.attrs["alias"]] if m.attrs.get("alias") else None
            # free text yields grammar as often as names: a rejected mention is skipped, not stored
            e = self.resolver.resolve_opt(m.type, m.text, attrs, when, aliases)
            if e is None:
                continue
            ents[m.key] = e
            snippet = text[max(0, m.start - 60): m.end + 60]
            add_entity_evidence(self.db, doc.id, e.id, snippet, m.confidence, when, extractor)
            if anchor is not None and e.id != anchor.id:
                rel = anchor_rel
                role = m.attrs.get("role")
                if role in ("accused", "suspect"):
                    rel = "ACCUSED_IN"
                elif role == "complainant":
                    rel = "COMPLAINANT_IN"
                self.acc.add(e.id, anchor.id, rel, at=when, confidence=m.confidence, doc_id=doc.id, snippet=snippet, extractor=extractor)
        for r in res.relations:
            s, t = ents.get(r.source.key), ents.get(r.target.key)
            if s is None or t is None or s.id == t.id:
                continue
            self.acc.add(s.id, t.id, r.rel_type, at=when, confidence=r.confidence, doc_id=doc.id, snippet=r.snippet,
                         extractor=extractor, attrs=r.attrs)
        if extractor == "rules":
            self._apply_identifiers(doc, text, ents, when)
        return ents

    def _apply_identifiers(self, doc: Document, text: str, ents: dict, when: datetime | None) -> None:
        """Checksum-validated Indian IDs. Aadhaar/PAN/passport are stored masked with a salted
        fingerprint, so two records citing the same number still resolve to one person while the
        number itself never enters the database."""
        from .identifiers import extract as extract_ids

        found = extract_ids(text, include_invalid=True)
        # person mentions with their position in the narrative, for ownership attribution
        # Sort on the position alone. Two mentions can resolve to the same offset, and the tuple
        # comparison then falls through to comparing Entity objects, which raises.
        person_positions = sorted(
            ((pos, e) for (t, txt), e in ents.items() if t == PERSON
             for pos in [text.find(txt)] if pos >= 0),
            key=lambda pair: pair[0],
        )
        for idf in found:
            if not idf.valid:
                self.stats.identifiers_rejected += 1
                continue
            self.stats.identifiers_found += 1
            if idf.kind in ("IFSC", "UPI"):
                continue  # already handled as BANK_ACCOUNT
            attrs = {k: v for k, v in idf.attrs.items() if k != "reason"}
            ent = self.resolver.resolve(GOV_ID, idf.normalized,
                                        {**attrs, "id_kind": idf.kind, "sensitive": idf.sensitive}, when)
            snippet = text[max(0, idf.start - 60): idf.end + 60]
            add_entity_evidence(self.db, doc.id, ent.id, snippet, 1.0, when, "checksum")
            if not person_positions:
                continue
            # "Sunil Pawar holding Aadhaar XXXX" - the holder is the nearest person named before the id,
            # falling back to the closest person anywhere in the document
            before = [(p, e) for p, e in person_positions if p <= idf.start]
            owner = before[-1][1] if before else min(person_positions, key=lambda x: abs(x[0] - idf.start))[1]
            self.acc.add(owner.id, ent.id, "HOLDS_ID", weight=3.0, at=when, confidence=0.9, doc_id=doc.id,
                         snippet=snippet, extractor="checksum", attrs={"id_kind": idf.kind})

    def _neural_enrich(self, doc: Document, text: str, when: datetime | None, anchor=None):
        """Tier 2: zero-shot transformer NER. Adds entity types the rules cannot express."""
        if not self.use_neural:
            return
        from .neural_ner import neural_ner

        res = neural_ner.extract(text, self.neural_labels)
        if res and res.mentions:
            self._apply_extraction(doc, text, res, when, anchor, extractor="gliner")
            self.stats.neural_enriched += 1

    def _llm_enrich(self, doc: Document, text: str, when: datetime | None, anchor=None):
        """Tier 3: LLM reasoning over ambiguous narrative."""
        if not self.use_llm:
            return
        try:
            from ..ai.llm import extract_entities_llm

            res = extract_entities_llm(text)
        except Exception as exc:  # pragma: no cover - network
            self.stats.warnings.append(f"LLM extraction failed for {doc.title}: {exc}")
            return
        if res:
            self._apply_extraction(doc, text, res, when, anchor, extractor="llm")
            self.stats.llm_enriched += 1

    def _enrich(self, doc: Document, text: str, when: datetime | None, anchor=None):
        self._neural_enrich(doc, text, when, anchor)
        self._llm_enrich(doc, text, when, anchor)

    def ingest_text(self, source_type: str, title: str, text: str, meta: dict | None = None, when: datetime | None = None,
                    finish: bool = True) -> Document:
        res = self.ner.extract(text)
        when = when or (_dt(res.dates[0]) if res.dates else None)
        doc = self._doc(source_type, title, text, meta, when)
        anchor_type = CASE if source_type == "FIR" else REPORT if source_type in ("INTEL", "REPORT") else None
        anchor = None
        if anchor_type:
            anchor = self.resolver.resolve(anchor_type, title, {"source_type": source_type, "sections": res.sections, **(meta or {})}, when)
            anchor.attributes = {**anchor.attributes, "document_id": doc.id}
            add_entity_evidence(self.db, doc.id, anchor.id, text[:300], 1.0, when, "structured")
        ents = self._apply_extraction(doc, text, res, when, anchor)
        self._enrich(doc, text, when, anchor)
        if when:
            # Place the event. A judgment sits at the seat of its court and a news item at its desk
            # city - never at a scene we were never told about, so `geo_precision` travels with it.
            g = self._event_point(source_type, title, text, meta or {})
            add_event(self.db, doc.id, source_type, when, [e.id for e in ents.values()] + ([anchor.id] if anchor else []),
                      f"{source_type}: {title}", {"sections": res.sections, **({"geo": g} if g else {})},
                      lat=(g or {}).get("lat"), lon=(g or {}).get("lon"))
            self.stats.events += 1
        self.stats.records += 1
        if finish:
            self._finish()
        return doc

    # ------------------------------------------------------------------ FIR (json list)
    def ingest_firs(self, records: list[dict]) -> IngestStats:
        total = len(records)
        for i, f in enumerate(records):
            title = f"FIR {f.get('fir_no', '?')} - {f.get('police_station', '')}".strip(" -")
            when = _dt(f.get("date"))
            text = f.get("text", "")
            meta = {k: v for k, v in f.items() if k != "text"}
            res = self.ner.extract(text)
            doc = self._doc("FIR", title, text, meta, when)
            case = self.resolver.resolve(CASE, title, {"police_station": f.get("police_station"), "sections": f.get("sections"),
                                                       "crime_head": f.get("crime_head"), "fir_no": f.get("fir_no"),
                                                       "document_id": doc.id}, when)
            add_entity_evidence(self.db, doc.id, case.id, text[:300], 1.0, when, "structured")
            ents = self._apply_extraction(doc, text, res, when, case)
            # structured accused / complainant fields (high confidence)
            for name in f.get("accused") or []:
                p = self.resolver.resolve(PERSON, name, {"role": "accused"}, when)
                self.acc.add(p.id, case.id, "ACCUSED_IN", at=when, confidence=1.0, doc_id=doc.id, snippet=f"Accused: {name}", extractor="structured")
                ents[(PERSON, name)] = p
            comp = f.get("complainant")
            if comp and not re.search(r"\b(PSI|PI|API|HC|Manager|Branch|ED|Superintendent|Directorate)\b", comp):
                p = self.resolver.resolve(PERSON, comp, {"role": "complainant"}, when)
                self.acc.add(p.id, case.id, "COMPLAINANT_IN", at=when, confidence=1.0, doc_id=doc.id, snippet=f"Complainant: {comp}", extractor="structured")
            # co-accused edges
            accused = [self.resolver.resolve(PERSON, n, {}, when) for n in (f.get("accused") or [])]
            for a in range(len(accused)):
                for b in range(a + 1, len(accused)):
                    self.acc.add(accused[a].id, accused[b].id, "CO_ACCUSED", weight=2.0, at=when, doc_id=doc.id,
                                 snippet=f"Co-accused in {title}", extractor="structured")
            # police station -> location
            ps = (f.get("police_station") or "").replace(" PS", "").replace(" City", "").replace(" Nagar", "").strip()
            lat = lon = None
            for g in self.gazetteer:
                if g.lower() == ps.lower():
                    lat, lon = self.gazetteer[g]["lat"], self.gazetteer[g]["lon"]
                    ps_loc = self._loc(g, when)
                    if ps_loc:
                        self.acc.add(case.id, ps_loc.id, "REGISTERED_AT", at=when, doc_id=doc.id, snippet=f.get("police_station", ""), extractor="structured")
            self._enrich(doc, text, when, case)
            if when:
                add_event(self.db, doc.id, "FIR", when, [e.id for e in ents.values()] + [case.id],
                          f"{title}: {f.get('crime_head', '')}", {"sections": f.get("sections"), "crime_head": f.get("crime_head")}, lat, lon)
                self.stats.events += 1
            self.stats.records += 1
            self.progress("FIR", i + 1, total)
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ INTEL
    def ingest_intel(self, records: list[dict]) -> IngestStats:
        total = len(records)
        for i, r in enumerate(records):
            title = f"{r.get('agency', 'INTEL')} {r.get('ref', '')}".strip()
            self.ingest_text("INTEL", title, r.get("text", ""), {k: v for k, v in r.items() if k != "text"}, _dt(r.get("date")), finish=False)
            self.progress("INTEL", i + 1, total)
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ KYC
    def ingest_kyc(self, rows: list[dict]) -> IngestStats:
        doc = self._doc("KYC", f"Telecom subscriber records ({len(rows)} rows)", "", {"rows": len(rows)}, records=len(rows))
        for i, r in enumerate(rows):
            msisdn, name = r.get("msisdn") or r.get("phone") or "", r.get("subscriber_name") or r.get("name") or ""
            if not msisdn:
                continue
            unverified = (r.get("id_type") or "").lower() in ("", "unverified", "fake", "na", "n/a")
            ph = self.resolver.resolve(PHONE, msisdn, {"operator": r.get("operator"), "activation_date": r.get("activation_date"),
                                                       "kyc_status": "unverified" if unverified else "verified",
                                                       "kyc_name": name, "kyc_address": r.get("address")})
            if name:
                p = self.resolver.resolve(PERSON, name, {"address": r.get("address")} if not unverified else {"kyc_unverified": True},
                                          discriminator="address" if not unverified else None)
                self.acc.add(p.id, ph.id, "USES_PHONE", confidence=0.6 if unverified else 0.95, doc_id=doc.id,
                             snippet=f"KYC: {msisdn} registered to {name} ({r.get('id_type')})", extractor="structured",
                             attrs={"kyc_status": "unverified" if unverified else "verified"})
                addr = (r.get("address") or "").split(",")[0].strip()
                if addr and addr in self.gazetteer:
                    addr_loc = self._loc(addr)
                    if addr_loc:
                        self.acc.add(p.id, addr_loc.id, "RESIDES_AT", confidence=0.8, doc_id=doc.id, snippet=f"KYC address: {r.get('address')}", extractor="structured")
            self.stats.records += 1
            if i % 25 == 0:
                self.progress("KYC", i + 1, len(rows))
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ CDR
    def ingest_cdr(self, rows: list[dict]) -> IngestStats:
        doc = self._doc("CDR", f"Call Detail Records batch ({len(rows)} calls)", "", {"rows": len(rows)}, records=len(rows))
        total = len(rows)
        imei_phones: dict[str, set[str]] = {}
        for i, r in enumerate(rows):
            a, b = r.get("caller") or r.get("a_party"), r.get("callee") or r.get("b_party")
            if not a or not b:
                continue
            when = _dt(r.get("timestamp") or r.get("datetime"))
            dur = int(float(r.get("duration_sec") or r.get("duration") or 0))
            pa = self.resolver.resolve(PHONE, a, {}, when)
            pb = self.resolver.resolve(PHONE, b, {}, when)
            for p, raw in ((pa, a), (pb, b)):
                if len(RuleNER.norm_phone(raw)) > 10:
                    p.attributes = {**p.attributes, "international": True}
            imei = (r.get("imei") or "").strip()
            if imei:
                imei_phones.setdefault(imei, set()).add(pa.id)
                if imei not in (pa.attributes.get("imeis") or []):
                    pa.attributes = {**pa.attributes, "imeis": [*(pa.attributes.get("imeis") or []), imei]}
            night = _is_night(when)
            self.acc.add(pa.id, pb.id, "CALLED", weight=1.0, at=when, doc_id=doc.id if i < 1 else None,
                         attrs={"duration_sec": dur, "night": night, "call_type": r.get("call_type")}, extractor="structured")
            tower = r.get("tower_location") or r.get("cell_tower")
            lat = lon = None
            if tower:
                loc = self._loc(tower, when)
                if loc:
                    lat, lon = loc.attributes.get("lat"), loc.attributes.get("lon")
                    self.acc.add(pa.id, loc.id, "PINGED_AT", weight=0.2, at=when, extractor="structured")
            add_event(self.db, doc.id, "CALL", when or datetime.now(), [pa.id, pb.id],
                      f"{'SMS' if r.get('call_type') == 'SMS' else 'Call'} {pa.label} -> {pb.label} ({dur}s)",
                      {"duration_sec": dur, "tower": tower, "call_type": r.get("call_type"), "night": night, "call_id": r.get("call_id")}, lat, lon)
            self.stats.events += 1
            self.stats.records += 1
            if i % 200 == 0:
                self.progress("CDR", i + 1, total)
        # handset analysis: numbers that were used in the same physical device (same IMEI)
        for imei, phones in imei_phones.items():
            ps = sorted(phones)
            for x in range(len(ps)):
                for y in range(x + 1, len(ps)):
                    self.acc.add(ps[x], ps[y], "SHARED_HANDSET", weight=5.0, confidence=0.95, doc_id=doc.id,
                                 snippet=f"Both numbers used in handset IMEI {imei}", extractor="structured", attrs={"imei": imei})
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ Transactions
    def ingest_transactions(self, rows: list[dict]) -> IngestStats:
        doc = self._doc("TRANSACTION", f"Financial transactions batch ({len(rows)} transfers)", "", {"rows": len(rows)}, records=len(rows))
        total = len(rows)
        for i, r in enumerate(rows):
            src, dst = r.get("from_account"), r.get("to_account")
            if not src or not dst:
                continue
            when = _dt(r.get("timestamp") or r.get("date"))
            amt = float(r.get("amount_inr") or r.get("amount") or 0)
            sa = self.resolver.resolve(BANK_ACCOUNT, src, {"bank": r.get("from_bank"), "holder": r.get("from_holder")}, when)
            da = self.resolver.resolve(BANK_ACCOUNT, dst, {"bank": r.get("to_bank"), "holder": r.get("to_holder")}, when)
            for acc, holder in ((sa, r.get("from_holder")), (da, r.get("to_holder"))):
                if holder:
                    h = self._holder_entity(holder, when)
                    self.acc.add(h.id, acc.id, "OWNS_ACCOUNT", confidence=0.95, doc_id=doc.id if i < 1 else None,
                                 snippet=f"Account {acc.label} held by {holder}", extractor="structured")
            self.acc.add(sa.id, da.id, "TRANSFERRED_TO", weight=1.0, at=when, amount=amt, attrs={"mode": r.get("mode")}, extractor="structured")
            add_event(self.db, doc.id, "TRANSFER", when or datetime.now(), [sa.id, da.id],
                      f"₹{amt:,.0f} {r.get('mode', '')} {r.get('from_holder', sa.label)} -> {r.get('to_holder', da.label)}",
                      {"amount": amt, "mode": r.get("mode"), "remarks": r.get("remarks"), "txn_id": r.get("txn_id"),
                       "from_holder": r.get("from_holder"), "to_holder": r.get("to_holder")})
            self.stats.events += 1
            self.stats.records += 1
            if i % 200 == 0:
                self.progress("TRANSACTION", i + 1, total)
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ Surveillance
    def ingest_surveillance(self, records: list[dict]) -> IngestStats:
        total = len(records)
        for i, r in enumerate(records):
            when = _dt(r.get("timestamp"))
            title = f"Surveillance {r.get('report_id', '')} @ {r.get('location', '')}".strip()
            text = r.get("observation", "")
            doc = self._doc("SURVEILLANCE", title, text, {k: v for k, v in r.items() if k != "observation"}, when)
            rep = self.resolver.resolve(REPORT, title, {"unit": r.get("unit"), "officer": r.get("officer"), "document_id": doc.id}, when)
            lat, lon = r.get("lat"), r.get("lon")
            loc = self._loc(r["location"], when) if r.get("location") else None
            subjects = [self.resolver.resolve(PERSON, n, {}, when) for n in r.get("subjects") or []]
            vehicles = [self.resolver.resolve(VEHICLE, v, {}, when) for v in r.get("vehicles") or []]
            for s in subjects:
                add_entity_evidence(self.db, doc.id, s.id, text, 1.0, when, "structured")
                self.acc.add(s.id, rep.id, "SUBJECT_OF", at=when, doc_id=doc.id, snippet=text, extractor="structured")
                if loc:
                    self.acc.add(s.id, loc.id, "SEEN_AT", at=when, doc_id=doc.id, snippet=text, extractor="structured")
                for v in vehicles:
                    self.acc.add(s.id, v.id, "ASSOCIATED_VEHICLE", at=when, confidence=0.8, doc_id=doc.id, snippet=text, extractor="structured")
            for a in range(len(subjects)):
                for b in range(a + 1, len(subjects)):
                    self.acc.add(subjects[a].id, subjects[b].id, "MET", weight=2.0, at=when, doc_id=doc.id, snippet=text, extractor="structured")
            for v in vehicles:
                if loc:
                    self.acc.add(v.id, loc.id, "SEEN_AT", at=when, doc_id=doc.id, snippet=text, extractor="structured")
            # free-text observation may name extra people / vehicles / orgs
            res = self.ner.extract(text)
            ents = self._apply_extraction(doc, text, res, when, rep, anchor_rel="MENTIONED_IN")
            self._enrich(doc, text, when, rep)
            ids = list({*(s.id for s in subjects), *(v.id for v in vehicles), *(e.id for e in ents.values()), rep.id})
            if when:
                add_event(self.db, doc.id, "SIGHTING", when, ids, f"{r.get('location', '')}: {text[:140]}",
                          {"unit": r.get("unit"), "vehicles": r.get("vehicles"), "subjects": r.get("subjects")}, lat, lon)
                self.stats.events += 1
            self.stats.records += 1
            self.progress("SURVEILLANCE", i + 1, total)
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ Social media
    def ingest_social(self, records: list[dict]) -> IngestStats:
        total = len(records)
        for i, r in enumerate(records):
            when = _dt(r.get("timestamp"))
            handle = r.get("handle") or ""
            text = r.get("text", "")
            title = f"{r.get('platform', 'Social')} post {r.get('post_id', '')} by {handle}".strip()
            doc = self._doc("SOCIAL", title, text, {k: v for k, v in r.items() if k != "text"}, when)
            h = self.resolver.resolve(SOCIAL_HANDLE, handle, {"platform": r.get("platform")}, when) if handle else None
            author = self.resolver.resolve(PERSON, r["author_name"], {}, when) if r.get("author_name") else None
            if h and author:
                self.acc.add(author.id, h.id, "OWNS_HANDLE", confidence=0.9, doc_id=doc.id, snippet=f"{handle} -> {r['author_name']}", extractor="structured")
            loc = self._loc(r["location_tag"], when) if r.get("location_tag") and r["location_tag"] in self.gazetteer else None
            if loc and author:
                self.acc.add(author.id, loc.id, "POSTED_FROM", weight=0.5, at=when, doc_id=doc.id, snippet=text, extractor="structured")
            for m in r.get("mentions") or []:
                mh = self.resolver.resolve(SOCIAL_HANDLE, m, {}, when)
                if h:
                    self.acc.add(h.id, mh.id, "MENTIONED", at=when, doc_id=doc.id, snippet=text, extractor="structured")
            res = self.ner.extract(text)
            ents = self._apply_extraction(doc, text, res, when, None)
            for e in ents.values():
                if author and e.id != author.id and e.type in (PERSON, VEHICLE, ORGANIZATION):
                    self.acc.add(author.id, e.id, "MENTIONED_WITH" if e.type == PERSON else "MENTIONED", weight=0.7, at=when,
                                 confidence=0.7, doc_id=doc.id, snippet=text, extractor="rules")
            ids = list({*(x.id for x in (h, author, loc) if x), *(e.id for e in ents.values())})
            g = self.gazetteer.get(r.get("location_tag") or "") or {}
            if when:
                add_event(self.db, doc.id, "POST", when, ids, f"{handle}: {text[:140]}", {"platform": r.get("platform"), "likes": r.get("likes")},
                          g.get("lat"), g.get("lon"))
                self.stats.events += 1
            self.stats.records += 1
            self.progress("SOCIAL", i + 1, total)
        self._finish()
        return self.stats

    # ------------------------------------------------------------------ dispatcher for uploads
    def ingest_payload(self, source_type: str, filename: str, raw: bytes) -> IngestStats:
        st = source_type.upper()
        text = raw.decode("utf-8", errors="replace")
        if filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(text)))
            if st == "CDR":
                return self.ingest_cdr(rows)
            if st == "KYC":
                return self.ingest_kyc(rows)
            if st == "TRANSACTION":
                return self.ingest_transactions(rows)
            raise ValueError(f"CSV upload not supported for source type {st}")
        if filename.lower().endswith(".json"):
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            if st == "FIR":
                return self.ingest_firs(data)
            if st == "SURVEILLANCE":
                return self.ingest_surveillance(data)
            if st == "SOCIAL":
                return self.ingest_social(data)
            if st == "INTEL":
                return self.ingest_intel(data)
            raise ValueError(f"JSON upload not supported for source type {st}")
        # plain text -> treat as narrative document
        self.ingest_text(st if st in ("FIR", "INTEL") else "REPORT", filename, text)
        return self.stats


def load_demo_dataset(db: Session, progress: ProgressCb | None = None) -> dict:
    """Ingest the bundled multi-source sample corpus in dependency-friendly order."""
    d = settings.samples_dir
    if not (d / "firs.json").exists():
        from data.generate_dataset import Generator  # type: ignore

        Generator().run(d)
    svc = IngestionService(db, progress)
    order = [
        ("KYC", "kyc.csv", svc.ingest_kyc, "csv"),
        ("TRANSACTION", "transactions.csv", svc.ingest_transactions, "csv"),
        ("FIR", "firs.json", svc.ingest_firs, "json"),
        ("SURVEILLANCE", "surveillance.json", svc.ingest_surveillance, "json"),
        ("INTEL", "intel_reports.json", svc.ingest_intel, "json"),
        ("SOCIAL", "social_media.json", svc.ingest_social, "json"),
        ("CDR", "cdr.csv", svc.ingest_cdr, "csv"),
    ]
    for _, fname, fn, kind in order:
        p = d / fname
        if not p.exists():
            continue
        if kind == "csv":
            with p.open(encoding="utf-8") as f:
                fn(list(csv.DictReader(f)))
        else:
            fn(json.loads(p.read_text(encoding="utf-8")))
    return svc.stats.as_dict()
