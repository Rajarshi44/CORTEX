"""
Repair passes over data that is already in the database.

The connectors are fixed going forward, but a corpus harvested before the fix still carries the
artifacts. These passes are idempotent and each one reports what it touched, so a run can be read
as an audit entry rather than an unexplained change in the numbers:

  purge_junk      - drop entities that are not entities (stopwords, bare numbers, ISO codes used
                    as places) together with the edges and evidence that hung off them
  stamp_roles     - record each entity's standing (judge / institution / authority / party)
  geocode_entities- give LOCATION rows a point derived from their own text
  geocode_events  - place timeline events at their court, desk city or named place
  link_namesakes  - propose SAME_AS across sources where the evidence is strong enough to suggest
                    it and weak enough that it must stay a proposal
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..db import Document, Entity, Evidence, Relationship, TimelineEvent
from . import geo
from .quality import is_junk, role_of

log = logging.getLogger("cna.backfill")


def purge_junk(db: Session, dry_run: bool = False) -> dict[str, Any]:
    """Remove entities that should never have been created, and everything anchored to them."""
    victims: list[tuple[Entity, str]] = []
    for e in db.execute(select(Entity)).scalars():
        rejected, why = is_junk(e.type, e.label)
        if rejected:
            victims.append((e, why))
    ids = [e.id for e, _ in victims]
    report: dict[str, Any] = {
        "entities": len(ids),
        "examples": [{"label": e.label, "type": e.type, "mentions": e.mention_count, "reason": why}
                     for e, why in sorted(victims, key=lambda x: -(x[0].mention_count or 0))[:10]],
        "relationships": 0, "evidence": 0, "dry_run": dry_run,
    }
    if not ids:
        return report
    # Evidence points at both entities and relationships, so the relationship ids have to be known
    # before anything is deleted: dropping the edges first orphans the evidence that cites them.
    rel_ids = [r for (r,) in db.execute(
        select(Relationship.id).where(or_(Relationship.source_id.in_(ids), Relationship.target_id.in_(ids)))).all()]
    report["relationships"] = len(rel_ids)
    report["evidence"] = db.query(Evidence).filter(
        or_(Evidence.entity_id.in_(ids), Evidence.relationship_id.in_(rel_ids) if rel_ids else False)).count()
    if dry_run:
        return report
    db.execute(delete(Evidence).where(or_(Evidence.entity_id.in_(ids),
                                          Evidence.relationship_id.in_(rel_ids) if rel_ids else False)))
    db.execute(delete(Relationship).where(Relationship.id.in_(rel_ids)))
    db.execute(delete(Entity).where(Entity.id.in_(ids)))
    # timeline events keep their own entity_ids list; drop the dead references
    for ev in db.execute(select(TimelineEvent)).scalars():
        kept = [i for i in (ev.entity_ids or []) if i not in set(ids)]
        if len(kept) != len(ev.entity_ids or []):
            ev.entity_ids = kept
    db.commit()
    log.info("purged %d junk entities", len(ids))
    return report


def stamp_roles(db: Session) -> dict[str, Any]:
    """Record standing in the case on each entity so ranking can hold roles apart."""
    counts: dict[str, int] = {}
    changed = 0
    for e in db.execute(select(Entity)).scalars():
        role = role_of(e.type, e.label, e.attributes or {})
        if not role:
            continue
        counts[role] = counts.get(role, 0) + 1
        if (e.attributes or {}).get("record_role") != role:
            e.attributes = {**(e.attributes or {}), "record_role": role}
            changed += 1
    db.commit()
    return {"roles": counts, "updated": changed}


def geocode_entities(db: Session) -> dict[str, Any]:
    """Give every LOCATION a point we can defend, derived from its own text."""
    done = 0
    by_precision: dict[str, int] = {}
    for e in db.execute(select(Entity).where(Entity.type == "LOCATION")).scalars():
        attrs = e.attributes or {}
        if attrs.get("lat") is not None:
            continue
        hit = geo.locate(e.label, attrs.get("countries"), attrs.get("country_code"))
        if not hit:
            continue
        e.attributes = {**attrs, "lat": hit["lat"], "lon": hit["lon"],
                        "geo_precision": hit["precision"], "geo_matched": hit["matched"]}
        by_precision[hit["precision"]] = by_precision.get(hit["precision"], 0) + 1
        done += 1
    # watchlisted people carry a country of listing rather than an address
    for e in db.execute(select(Entity).where(Entity.type.in_(("PERSON", "ORGANIZATION")))).scalars():
        attrs = e.attributes or {}
        if attrs.get("lat") is not None or not attrs.get("country_code"):
            continue
        named = geo.country_of(str(attrs["country_code"]))
        if named:
            e.attributes = {**attrs, "country": named[0], "lat": named[1], "lon": named[2],
                            "geo_precision": "country"}
            by_precision["country"] = by_precision.get("country", 0) + 1
            done += 1
    db.commit()
    return {"located": done, "by_precision": by_precision}


def geocode_events(db: Session) -> dict[str, Any]:
    """
    Place timeline events. A judgment goes to the seat of its court, a news item to its desk city.

    `details.geo.precision` travels with the point so the map can say what it means rather than
    implying we know where something happened.
    """
    docs = {d.id: d for d in db.execute(select(Document)).scalars()}
    done = 0
    by_precision: dict[str, int] = {}
    for ev in db.execute(select(TimelineEvent)).scalars():
        if ev.lat is not None:
            continue
        doc = docs.get(ev.document_id)
        meta = (doc.meta or {}) if doc else {}
        if ev.kind == "JUDGMENT":
            hit = geo.locate(meta.get("court"), meta.get("respondent"), meta.get("petitioner"), ev.summary)
        elif ev.kind == "NEWS":
            hit = geo.locate(meta.get("feed"), ev.summary, (doc.content or "")[:400] if doc else None)
        else:
            hit = geo.locate(meta.get("country"), ev.summary, (doc.content or "")[:400] if doc else None)
        if not hit:
            continue
        ev.lat, ev.lon = hit["lat"], hit["lon"]
        ev.details = {**(ev.details or {}), "geo": hit}
        by_precision[hit["precision"]] = by_precision.get(hit["precision"], 0) + 1
        done += 1
    db.commit()
    return {"located": done, "by_precision": by_precision}


def link_namesakes(db: Session, threshold: int = 92, limit_per_entity: int = 3) -> dict[str, Any]:
    """
    Connect imported watchlist rows to the rest of the sheet, locally.

    A watchlist is a list, not a network: OpenSanctions rows arrive with no edges at all, which is
    why most of the graph is isolated points. The names in them do overlap the court and leak data,
    and that overlap is the only honest bridge available without re-fetching the source.

    The link is POSSIBLE_SAME_AS - a proposal carrying its score, never a merge. Cross-source
    identity stays something a person confirms: "Rajiv Singh" in the leaks and "Rajiv Singh" on a
    SEBI order are not the same man because their names match.
    """
    from rapidfuzz import fuzz, process

    def screenable(e: Entity) -> bool:
        if len(e.label) < 7:
            return False
        return not (e.type == "PERSON" and len(e.label.split()) < 2)

    actors = [e for e in db.execute(
        select(Entity).where(Entity.type.in_(("PERSON", "ORGANIZATION")))).scalars() if screenable(e)]
    listed = [e for e in actors if (e.attributes or {}).get("watchlist")]
    others = [e for e in actors if not (e.attributes or {}).get("watchlist")]
    if not listed or not others:
        return {"proposed": 0, "reason": "nothing to screen"}

    # block by type so a person is never proposed as the same entity as a company
    pools: dict[str, list[Entity]] = {"PERSON": [], "ORGANIZATION": []}
    for e in others:
        pools[e.type].append(e)
    existing = {(r.source_id, r.target_id) for r in db.execute(
        select(Relationship).where(Relationship.rel_type == "POSSIBLE_SAME_AS")).scalars()}

    proposed, by_score = 0, {"strong": 0, "probable": 0}
    for e in listed:
        pool = pools.get(e.type) or []
        if not pool:
            continue
        names = [p.label for p in pool]
        for matched, score, idx in process.extract(e.label, names, scorer=fuzz.WRatio, limit=limit_per_entity):
            if score < threshold:
                break
            other = pool[idx]
            if other.id == e.id or (e.id, other.id) in existing or (other.id, e.id) in existing:
                continue
            strength = "strong" if score >= 96 else "probable"
            db.add(Relationship(
                id=str(uuid.uuid4()), source_id=e.id, target_id=other.id,
                rel_type="POSSIBLE_SAME_AS", weight=0.3, count=1, confidence=round(score / 100.0, 3),
                attributes={"score": round(float(score), 1), "strength": strength, "basis": "name similarity",
                            "matched_label": matched, "screened_locally": True,
                            "note": "proposed identity link, not a merge - confirm before relying on it"},
                first_seen=e.first_seen, last_seen=e.last_seen))
            existing.add((e.id, other.id))
            by_score[strength] += 1
            proposed += 1
    db.commit()
    return {"proposed": proposed, "by_strength": by_score, "listed_screened": len(listed),
            "pool": len(others), "threshold": threshold}


def run_all(db: Session) -> dict[str, Any]:
    """Every repair pass, in the order their dependencies require."""
    out = {
        "purge_junk": purge_junk(db),
        "stamp_roles": stamp_roles(db),
        "geocode_entities": geocode_entities(db),
        "geocode_events": geocode_events(db),
    }
    from ..graph.store import graph_cache

    graph_cache.invalidate()
    return out
