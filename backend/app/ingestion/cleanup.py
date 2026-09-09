"""
One-off repair for a corpus that accumulated contamination during development.

Three things got onto the sheet that should never have been on an Indian criminal-network
sheet, and each one is visible to anyone looking at the console:

1. ACADEMIC BENCHMARKS. The Montreal street-gang and 9/11 hijacker networks are real research
   datasets used to validate community detection, but they are neither Indian nor operational.
   Worse, they were harvested repeatedly, so every node in them exists two or three times. To a
   viewer this reads as "the tool invents data".

2. HISTORIC STATISTICS. NCRB tables from 1953 and 1973 are aggregate counts, not entities. They
   contribute nothing to a network and date the sheet by seventy years.

3. ADDRESSES AS PLACES. ICIJ address rows carry the resident's name inside the address string, so
   "Pamela Kambil & Mr Nevin Pradeep Kambil #1 Jayanthi Nagar ..." became a LOCATION. A person's
   name must never appear as a place.

Everything here is idempotent and dry-runnable, and reports what it touched so a run reads as an
audit entry rather than an unexplained drop in the numbers.

    python -m app.ingestion.cleanup --dry-run
    python -m app.ingestion.cleanup
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import Document, Entity, Evidence, Relationship, TimelineEvent
from . import geo

log = logging.getLogger("cna.cleanup")

# Source types that carry no entities worth analysing on an operational sheet.
NON_OPERATIONAL_SOURCES = ("BENCHMARK", "STATS")

# An address masquerading as a place: house numbers, floor/plot markers, or a personal
# name glued to a locality. Real gazetteer places never look like this.
ADDRESS_SHAPED = re.compile(
    r"^\s*(?:#|no\.?\s*\d|plot\b|flat\b|door\b|h\.?no\b|survey\b)|"      # starts like a street address
    r"\d{1,4}\s*(?:st|nd|rd|th)\s+(?:cross|main|floor|phase|street)\b|"  # "15TH CROSS", "4TH PHASE"
    r"\b\d{6}\b|"                                                        # embedded PIN code
    r"\bmr\.?\s|\bmrs\.?\s|\bshri\b|\bsmt\b|&",                          # a person inside the "place"
    re.I)


def _delete_entities(db: Session, ids: list[str]) -> dict[str, int]:
    """Remove entities and everything anchored to them, in FK-safe order."""
    if not ids:
        return {"entities": 0, "relationships": 0, "evidence": 0, "events": 0}
    rels = db.execute(
        select(func.count()).select_from(Relationship).where(
            Relationship.source_id.in_(ids) | Relationship.target_id.in_(ids))).scalar() or 0
    rel_ids = [r for (r,) in db.execute(
        select(Relationship.id).where(Relationship.source_id.in_(ids) | Relationship.target_id.in_(ids)))]
    ev = db.execute(select(func.count()).select_from(Evidence).where(
        Evidence.entity_id.in_(ids) | (Evidence.relationship_id.in_(rel_ids) if rel_ids else False))).scalar() or 0
    db.execute(delete(Evidence).where(Evidence.entity_id.in_(ids)))
    if rel_ids:
        db.execute(delete(Evidence).where(Evidence.relationship_id.in_(rel_ids)))
    db.execute(delete(Relationship).where(Relationship.source_id.in_(ids) | Relationship.target_id.in_(ids)))
    events = 0
    for e in db.execute(select(TimelineEvent)).scalars():
        if set(e.entity_ids or []) & set(ids):
            db.delete(e)
            events += 1
    db.execute(delete(Entity).where(Entity.id.in_(ids)))
    return {"entities": len(ids), "relationships": rels, "evidence": ev, "events": events}


def drop_non_operational(db: Session, dry_run: bool = False) -> dict[str, Any]:
    """Remove academic benchmark networks and historic statistics, with their entities."""
    docs = db.execute(select(Document).where(Document.source_type.in_(NON_OPERATIONAL_SOURCES))).scalars().all()
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return {"documents": 0, "note": "nothing to drop"}
    # entities whose *only* evidence comes from these documents; one cited elsewhere is kept
    theirs = {e for (e,) in db.execute(select(Evidence.entity_id).where(Evidence.document_id.in_(doc_ids))) if e}
    elsewhere = {e for (e,) in db.execute(
        select(Evidence.entity_id).where(Evidence.entity_id.in_(theirs), Evidence.document_id.notin_(doc_ids))) if e}
    orphans = sorted(theirs - elsewhere)
    report: dict[str, Any] = {
        "documents": len(docs),
        "titles": sorted({d.title[:70] for d in docs}),
        "entities_cited_only_here": len(orphans),
        "entities_kept_cited_elsewhere": len(theirs & elsewhere),
    }
    if dry_run:
        report["dry_run"] = True
        return report
    report.update(_delete_entities(db, orphans))
    db.execute(delete(Evidence).where(Evidence.document_id.in_(doc_ids)))
    db.execute(delete(Document).where(Document.id.in_(doc_ids)))
    db.commit()
    return report


def _city_in(text: str) -> str | None:
    """Best-effort city for a dirty address. ICIJ spellings include NEW DALHI and Bangldore, so an
    exact match is tried first and a tight fuzzy match second; anything looser would invent a place."""
    from ..ingestion.geo import CITIES

    m = geo._CITY_RE.search(text)
    if m:
        return m.group(1).title()
    from rapidfuzz import fuzz, process

    for chunk in re.split(r"[;,]", text):
        chunk = re.sub(r"[\d\-]+", " ", chunk).strip()
        if len(chunk) < 4:
            continue
        best = process.extractOne(chunk, list(CITIES), scorer=fuzz.WRatio)
        if best and best[1] >= 88:
            return best[0].title()
    return None


def _merge_entity(db: Session, src: Entity, dst: Entity) -> None:
    """Move every edge and every piece of evidence from `src` onto `dst`, then drop `src`.

    Two addresses in one city mean the same person can hold an edge to both, so redirecting
    blindly would violate the (source, target, rel_type) uniqueness. Where the destination edge
    already exists the two are combined - weights and counts add, the time span widens, the
    evidence moves across - and only the redundant row is dropped.
    """
    for r in db.execute(select(Relationship).where(
            (Relationship.source_id == src.id) | (Relationship.target_id == src.id))).scalars().all():
        new_src = dst.id if r.source_id == src.id else r.source_id
        new_dst = dst.id if r.target_id == src.id else r.target_id
        if new_src == new_dst:                    # the edge collapsed onto itself
            db.execute(delete(Evidence).where(Evidence.relationship_id == r.id))
            db.delete(r)
            continue
        existing = db.execute(select(Relationship).where(
            Relationship.source_id == new_src, Relationship.target_id == new_dst,
            Relationship.rel_type == r.rel_type, Relationship.id != r.id)).scalars().first()
        if existing is None:
            r.source_id, r.target_id = new_src, new_dst
            continue
        existing.weight = (existing.weight or 0) + (r.weight or 0)
        existing.count = (existing.count or 0) + (r.count or 0)
        existing.confidence = max(existing.confidence or 0, r.confidence or 0)
        if r.first_seen and (existing.first_seen is None or r.first_seen < existing.first_seen):
            existing.first_seen = r.first_seen
        if r.last_seen and (existing.last_seen is None or r.last_seen > existing.last_seen):
            existing.last_seen = r.last_seen
        for ev in db.execute(select(Evidence).where(Evidence.relationship_id == r.id)).scalars().all():
            ev.relationship_id = existing.id
        db.delete(r)
        db.flush()                                # release the unique key before the next redirect
    for ev in db.execute(select(Evidence).where(Evidence.entity_id == src.id)).scalars().all():
        ev.entity_id = dst.id
    for e in db.execute(select(TimelineEvent)).scalars():
        if src.id in (e.entity_ids or []):
            e.entity_ids = [dst.id if x == src.id else x for x in e.entity_ids]
    db.flush()
    db.delete(src)
    db.flush()


def fold_address_locations(db: Session, dry_run: bool = False) -> dict[str, Any]:
    """A postal address is not a place, and must never carry a person's name.

    Each address is folded into the city it names, so "14 Aurangzeb Road; New Dehhi; 110011" stops
    being its own node and its edges land on New Delhi. Addresses with no recognisable city are
    dropped: an unplaceable street line is not a location anyone can act on.
    """
    victims = [e for e in db.execute(select(Entity).where(Entity.type == "LOCATION")).scalars()
               if ADDRESS_SHAPED.search(e.label or "")]
    folded, unplaceable, targets = [], [], {}
    for e in victims:
        city = _city_in(e.label or "")
        (folded if city else unplaceable).append((e, city))
    report: dict[str, Any] = {
        "matched": len(victims), "folded_into_city": len(folded), "dropped_unplaceable": len(unplaceable),
        "examples": [f"{e.label[:44]} -> {c}" for e, c in folded[:8]],
    }
    if dry_run:
        report["dry_run"] = True
        return report
    from .resolution import canonical_key

    for e, city in folded:
        key = canonical_key("LOCATION", city)
        dst = targets.get(key)
        if dst is None:
            dst = db.execute(select(Entity).where(Entity.type == "LOCATION",
                                                  Entity.canonical_key == key)).scalars().first()
            if dst is None:
                import uuid as _uuid

                dst = Entity(id=str(_uuid.uuid4()), type="LOCATION", label=city, canonical_key=key,
                             aliases=[], attributes={"source": "address-fold"}, mention_count=0)
                db.add(dst)
                db.flush()
            targets[key] = dst
        if dst.id != e.id:
            _merge_entity(db, e, dst)
    report.update(_delete_entities(db, [e.id for e, _ in unplaceable]))
    db.commit()
    return report


def dedupe_documents(db: Session, dry_run: bool = False) -> dict[str, Any]:
    """Same title harvested more than once: keep the earliest, drop the repeats."""
    rows = db.execute(
        select(Document.title, func.count().label("n")).group_by(Document.title).having(func.count() > 1)).all()
    dupes = {t: n for t, n in rows}
    losers: list[str] = []
    for title in dupes:
        docs = db.execute(select(Document).where(Document.title == title)
                          .order_by(Document.ingested_at.asc())).scalars().all()
        losers.extend(d.id for d in docs[1:])
    report: dict[str, Any] = {"titles_duplicated": len(dupes), "documents_to_drop": len(losers),
                              "examples": [t[:64] for t in list(dupes)[:6]]}
    if dry_run:
        report["dry_run"] = True
        return report
    if losers:
        # A re-ingest duplicated the document's timeline events too, and they hold a foreign key
        # onto it, so they go first or the delete is refused.
        for chunk in (losers[i:i + 200] for i in range(0, len(losers), 200)):
            events = db.execute(delete(TimelineEvent).where(TimelineEvent.document_id.in_(chunk)))
            report["events_dropped"] = report.get("events_dropped", 0) + (events.rowcount or 0)
            db.execute(delete(Evidence).where(Evidence.document_id.in_(chunk)))
            db.execute(delete(Document).where(Document.id.in_(chunk)))
            db.commit()
    return report


def drop_orphan_entities(db: Session, dry_run: bool = False) -> dict[str, Any]:
    """Entities with no evidence and no edges: nothing on the sheet can justify them."""
    cited = {e for (e,) in db.execute(select(Evidence.entity_id).distinct()) if e}
    linked = {x for (x,) in db.execute(select(Relationship.source_id).distinct())}
    linked |= {x for (x,) in db.execute(select(Relationship.target_id).distinct())}
    keep = cited | linked
    orphans = [e for (e,) in db.execute(select(Entity.id)) if e not in keep]
    report: dict[str, Any] = {"orphans": len(orphans)}
    if dry_run:
        report["dry_run"] = True
        return report
    report.update(_delete_entities(db, orphans))
    db.commit()
    return report


def reset_text_extraction(db: Session, source_types: tuple[str, ...] = ("NEWS", "INTEL"),
                          extractors: tuple[str, ...] = ("rules", "llm", "neural"),
                          dry_run: bool = False) -> dict[str, Any]:
    """Undo what was extracted from prose, so it can be extracted again under corrected rules.

    Extraction from text is reproducible: the article bodies are stored and the fetches are cached,
    so removing the derived evidence, edges and entities costs nothing but a re-run. Structured
    records are untouched - only what a reader could see was *inferred from wording* is rolled back.
    """
    doc_ids = [d for (d,) in db.execute(select(Document.id).where(Document.source_type.in_(source_types)))]
    if not doc_ids:
        return {"documents": 0}
    ev = db.execute(select(Evidence).where(Evidence.document_id.in_(doc_ids),
                                           Evidence.extractor.in_(extractors))).scalars().all()
    rel_ids = {e.relationship_id for e in ev if e.relationship_id}
    ent_ids = {e.entity_id for e in ev if e.entity_id}
    # an entity is only removed when *every* mention of it came from this text pass
    survivors = {e for (e,) in db.execute(select(Evidence.entity_id).where(
        Evidence.entity_id.in_(ent_ids),
        ~((Evidence.document_id.in_(doc_ids)) & (Evidence.extractor.in_(extractors))))) if e}
    doomed = sorted(ent_ids - survivors)
    report: dict[str, Any] = {"documents": len(doc_ids), "evidence": len(ev), "relationships": len(rel_ids),
                              "entities_only_from_text": len(doomed), "entities_kept": len(survivors)}
    if dry_run:
        report["dry_run"] = True
        return report
    for chunk in (list(rel_ids)[i:i + 300] for i in range(0, len(rel_ids), 300)):
        db.execute(delete(Evidence).where(Evidence.relationship_id.in_(chunk)))
        db.execute(delete(Relationship).where(Relationship.id.in_(chunk)))
    db.execute(delete(Evidence).where(Evidence.document_id.in_(doc_ids), Evidence.extractor.in_(extractors)))
    db.commit()
    report.update(_delete_entities(db, doomed))
    db.commit()
    return report


def run_all(db: Session, dry_run: bool = False) -> dict[str, Any]:
    return {
        "non_operational": drop_non_operational(db, dry_run),
        "address_locations": fold_address_locations(db, dry_run),
        "duplicate_documents": dedupe_documents(db, dry_run),
        "orphan_entities": drop_orphan_entities(db, dry_run),
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    from ..db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        print(json.dumps(run_all(db, dry_run=dry), indent=1, default=str))
    finally:
        db.close()
