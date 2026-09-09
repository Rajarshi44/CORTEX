"""
Standing watches: the alert that fires when a record arrives, not when a batch is recomputed.

`graph/anomalies.py` reasons over the whole corpus and its open alerts are replaced on every
recompute. That is the right shape for "this cluster looks like structuring" and the wrong shape for
"tell me the moment anything mentions this number". CCTNS runs the second kind nationally - the two
auto-match services for missing/found persons and missing/found vehicles, and the national criminal
and MO searches behind them. This is that, generalised: one selector, checked against every record
at the moment it lands, kept forever alongside the document that triggered it.

A hit is never inferred. It names the watch, the arriving document, the entity it matched and the
sentence it matched in, so an analyst reads the record rather than trusting a score. Matching is
exact on the same canonical key the resolver uses, which rules out a watch quietly widening into a
fuzzy name search. It does not rule out a namesake: two different men called Rajiv Singh share one
canonical name key, so a name watch fires on both. That is why a hit is presented as a record to
read rather than as an identity, and why an identifier, phone or plate is the better selector
wherever one exists.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from ..db import Document, Entity, Evidence, Relationship, TimelineEvent, Watch, WatchHit, utcnow
from ..ingestion import identifiers as ids
from ..ingestion.ner import BANK_ACCOUNT, GOV_ID, ORGANIZATION, PERSON, PHONE, VEHICLE, RuleNER
from ..ingestion.resolution import canonical_key

log = logging.getLogger("cna.watch")

TEXT = "TEXT"
WATCH_KINDS: tuple[str, ...] = (PERSON, ORGANIZATION, PHONE, VEHICLE, BANK_ACCOUNT, GOV_ID, TEXT)
SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
HIT_STATUSES: tuple[str, ...] = ("new", "reviewing", "dismissed", "confirmed")

# A fingerprinted identifier and a plain one both live in the GOV_ID key space, so the salted hash
# is prefixed to keep them from ever colliding.
FP = "fp:"

# SQLite caps a statement at 999 bound parameters; every IN clause here is fed in slices.
CHUNK = 400

_WS = re.compile(r"\s+")


class WatchError(ValueError):
    """A selector that could not become a matching key, phrased for the analyst who typed it."""


# --------------------------------------------------------------------------------- normalisation
def normalize(kind: str, value: str) -> tuple[str, str]:
    """Turn what an analyst typed into (matching key, display label).

    Raises WatchError rather than storing a watch that could never fire, or one so broad that every
    document would hit it.
    """
    kind = (kind or "").strip().upper()
    raw = (value or "").strip()
    if kind not in WATCH_KINDS:
        raise WatchError(f"Unknown watch kind {kind!r}. Use one of: {', '.join(WATCH_KINDS)}.")
    if not raw:
        raise WatchError("A watch needs something to watch for.")

    if kind == PHONE:
        norm = RuleNER.norm_phone(raw)
        if len(norm) < 10:
            raise WatchError(f"{raw!r} is not a full phone number - a watch needs all ten digits to match on.")
        return norm, norm

    if kind == VEHICLE:
        norm = RuleNER.norm_vehicle(raw)
        if len(norm) < 6:
            raise WatchError(f"{raw!r} is too short for a registration plate.")
        return norm, norm

    if kind == GOV_ID:
        return _normalize_gov_id(raw)

    if kind == TEXT:
        norm = _WS.sub(" ", raw).strip().lower()
        if len(norm) < 4:
            raise WatchError("A text watch needs at least four characters, or it would match almost every record.")
        return norm, norm

    # PERSON / ORGANIZATION / BANK_ACCOUNT all key the way the resolver keys them, so a watch and an
    # ingested entity agree on what "the same" means.
    norm = canonical_key(kind, raw)
    if len(norm) < 3:
        raise WatchError(f"{raw!r} is too short to identify a {kind.lower()}.")
    return norm, _WS.sub(" ", raw).strip()


def _normalize_gov_id(raw: str) -> tuple[str, str]:
    """Validate the identifier, then key it the way the graph keys it.

    A sensitive identifier (Aadhaar, PAN, passport) is keyed by its salted fingerprint and displayed
    masked, so watching an Aadhaar number never writes that number to the database.
    """
    found = ids.extract(raw, include_invalid=True)
    valid = [i for i in found if i.valid]
    if not valid:
        why = found[0].attrs.get("reason", "checksum failed") if found else "not a recognised identifier format"
        raise WatchError(f"That identifier did not validate: {why}. A watch is only stored once the number checks out.")
    if len(valid) > 1:
        raise WatchError("Enter one identifier per watch.")
    idf = valid[0]
    if idf.kind in ("IFSC", "UPI"):
        raise WatchError(f"{idf.kind} is stored as a bank account - watch it as BANK_ACCOUNT.")
    fp = idf.attrs.get("fingerprint")
    if fp:
        return FP + fp, idf.normalized  # already masked by the extractor
    return canonical_key(GOV_ID, idf.normalized), idf.normalized


def entity_keys(e: Entity) -> list[str]:
    """Every key an entity could be watched by. GOV_ID carries both a fingerprint and a plain key."""
    keys = [e.canonical_key]
    if e.type == GOV_ID:
        fp = (e.attributes or {}).get("fingerprint")
        if fp:
            keys.append(FP + fp)
    return [k for k in keys if k]


# --------------------------------------------------------------------------------- scanning
def _chunks(seq: Sequence[str], n: int = CHUNK) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _snippet(text: str, at: int, width: int = 90) -> str:
    return _WS.sub(" ", text[max(0, at - width): at + width]).strip()


def scan(db: Session, doc_ids: Sequence[str] | None = None, watches: Sequence[Watch] | None = None,
         commit: bool = True) -> list[WatchHit]:
    """Check documents against watches and record every match.

    `doc_ids` None means the whole corpus - what a newly created watch is backfilled against, so an
    analyst who adds a number already on the sheet is told immediately rather than waiting for the
    next record to arrive. `watches` None means every active watch, which is the ingestion path.
    """
    active = list(watches) if watches is not None else db.query(Watch).filter(Watch.active.is_(True)).all()
    if not active:
        return []
    if doc_ids is not None and not doc_ids:
        return []

    by_key: dict[tuple[str, str], Watch] = {}
    text_watches: list[Watch] = []
    for w in active:
        if w.kind == TEXT:
            text_watches.append(w)
        else:
            by_key[(w.kind, w.norm)] = w

    doc_list = list(doc_ids) if doc_ids is not None else [row[0] for row in db.query(Document.id).all()]
    if not doc_list:
        return []

    seen = _existing(db, [w.id for w in active], doc_list)
    hits: list[WatchHit] = []
    if by_key:
        hits += _scan_entities(db, doc_list, by_key, seen)
    if text_watches:
        hits += _scan_text(db, doc_list, text_watches, seen)
    if not hits:
        return []

    tally: dict[str, list[WatchHit]] = {}
    for h in hits:
        db.add(h)
        tally.setdefault(h.watch_id, []).append(h)
    by_id = {w.id: w for w in active}
    now = utcnow().replace(tzinfo=None)
    for wid, rows in tally.items():
        w = by_id.get(wid)
        if w is None:
            continue
        w.hit_count = (w.hit_count or 0) + len(rows)
        latest = max((r.occurred_at or now for r in rows), default=now)
        if w.last_hit_at is None or latest > w.last_hit_at:
            w.last_hit_at = latest
    if commit:
        db.commit()
    log.info("watch scan: %s hit(s) across %s document(s)", len(hits), len(doc_list))
    return hits


def _existing(db: Session, watch_ids: Sequence[str], doc_ids: Sequence[str]) -> set[tuple[str, str, str]]:
    """Hits already recorded, so a rescan over the same records adds nothing."""
    out: set[tuple[str, str, str]] = set()
    for dchunk in _chunks(list(doc_ids)):
        for wchunk in _chunks(list(watch_ids)):
            rows = (db.query(WatchHit.watch_id, WatchHit.document_id, WatchHit.entity_id)
                    .filter(WatchHit.document_id.in_(list(dchunk)), WatchHit.watch_id.in_(list(wchunk))).all())
            out.update((r[0], r[1], r[2] or "") for r in rows)
    return out


def _scan_entities(db: Session, doc_ids: Sequence[str], by_key: dict[tuple[str, str], Watch],
                   seen: set[tuple[str, str, str]]) -> list[WatchHit]:
    """Match on resolved entities.

    Three paths put an entity into a document, and all three are read here, best snippet first:

      Evidence.entity_id       prose the extractor read a name out of; carries the sentence.
      TimelineEvent.entity_ids structured batches (a call, a transfer); carries the parties.
      Evidence.relationship_id an entity that only ever appeared as one end of an extracted
                               relationship, so the sentence is filed under the edge and the entity
                               has no evidence row of its own.

    The third looks like an edge case and is not. On a public-record sheet 218 entities - 158 of
    them people, including the most-mentioned person on it - are reachable *only* that way, because
    a named party in a judgment enters as ACCUSED_IN or PETITIONER_IN rather than as a standalone
    mention. Reading the first two paths alone left a watch on any of them silently never firing.
    """
    context: dict[tuple[str, str], tuple[str, datetime | None]] = {}  # (entity, doc) -> (snippet, when)
    rel_ctx: dict[tuple[str, str], tuple[str, datetime | None]] = {}  # (relationship, doc) -> (snippet, when)
    for chunk in _chunks(list(doc_ids)):
        for ev in db.query(Evidence).filter(Evidence.document_id.in_(list(chunk))).all():
            snippet = _WS.sub(" ", ev.snippet or "").strip()
            if ev.entity_id:
                key = (ev.entity_id, ev.document_id)
                if key not in context or (not context[key][0] and snippet):
                    context[key] = (snippet, ev.occurred_at)
            elif ev.relationship_id:
                rel_ctx.setdefault((ev.relationship_id, ev.document_id), (snippet, ev.occurred_at))
        for te in db.query(TimelineEvent).filter(TimelineEvent.document_id.in_(list(chunk))).all():
            for eid in te.entity_ids or []:
                key = (eid, te.document_id)
                if key not in context:
                    context[key] = (_WS.sub(" ", te.summary or "").strip(), te.occurred_at)

    if rel_ctx:  # fold each edge's evidence onto both of its endpoints, without displacing a
        rel_ids = sorted({rid for rid, _ in rel_ctx})  # sentence the entity already has of its own
        endpoints: dict[str, tuple[str, str]] = {}
        for chunk in _chunks(rel_ids):
            for r in db.query(Relationship).filter(Relationship.id.in_(list(chunk))).all():
                endpoints[r.id] = (r.source_id, r.target_id)
        for (rid, did), value in rel_ctx.items():
            for eid in endpoints.get(rid, ()):
                context.setdefault((eid, did), value)

    if not context:
        return []

    wanted_types = {k[0] for k in by_key}
    entity_ids = sorted({eid for eid, _ in context})
    entities: dict[str, Entity] = {}
    for chunk in _chunks(entity_ids):
        for e in db.query(Entity).filter(Entity.id.in_(list(chunk)), Entity.type.in_(list(wanted_types))).all():
            entities[e.id] = e
    if not entities:
        return []

    out: list[WatchHit] = []
    for (eid, did), (snippet, when) in context.items():
        e = entities.get(eid)
        if e is None:
            continue
        for key in entity_keys(e):
            w = by_key.get((e.type, key))
            if w is None:
                continue
            ident = (w.id, did, eid)
            if ident in seen:
                break
            seen.add(ident)
            out.append(WatchHit(watch_id=w.id, document_id=did, entity_id=eid,
                                matched_on=f"{e.type.lower().replace('_', ' ')} {e.label}"[:200],
                                snippet=snippet[:1000], occurred_at=when, status="new"))
            break  # one hit per (watch, document, entity), whichever key matched
    return out


def _scan_text(db: Session, doc_ids: Sequence[str], watches: Sequence[Watch],
               seen: set[tuple[str, str, str]]) -> list[WatchHit]:
    """Match a phrase against document title and body.

    Kept deliberately literal - a case-folded substring. Anything cleverer (stemming, synonyms) would
    make a hit something the analyst has to second-guess rather than something they can see.
    """
    out: list[WatchHit] = []
    for chunk in _chunks(list(doc_ids)):
        for doc in db.query(Document).filter(Document.id.in_(list(chunk))).all():
            hay = f"{doc.title}\n{doc.content or ''}"
            low = hay.lower()
            for w in watches:
                at = low.find(w.norm)
                if at < 0:
                    continue
                ident = (w.id, doc.id, "")
                if ident in seen:
                    continue
                seen.add(ident)
                out.append(WatchHit(watch_id=w.id, document_id=doc.id, entity_id="",
                                    matched_on=f'text "{w.selector}"'[:200],
                                    snippet=_snippet(hay, at)[:1000], occurred_at=doc.occurred_at, status="new"))
    return out


# --------------------------------------------------------------------------------- create / remove
def create(db: Session, kind: str, value: str, reason: str = "", severity: str = "high",
           created_by: str = "", backfill: bool = True) -> tuple[Watch, int, bool]:
    """Create a watch (or return the one already watching this selector) and backfill it.

    Returns (watch, hits found in the records already held, created). Backfilling is the half of a
    standing query that CCTNS calls a national search: "has this ever appeared" is asked once against
    everything already held, then continuously against everything that arrives.
    """
    if severity not in SEVERITIES:
        raise WatchError(f"Severity must be one of: {', '.join(SEVERITIES)}.")
    norm, display = normalize(kind, value)
    kind = kind.strip().upper()
    existing = db.query(Watch).filter(Watch.kind == kind, Watch.norm == norm).one_or_none()
    if existing is not None:
        if not existing.active:  # re-arming an old watch, rather than a silent no-op
            existing.active = True
            db.commit()
        return existing, 0, False
    w = Watch(id=str(uuid.uuid4()), kind=kind, selector=display, norm=norm, reason=(reason or "").strip(),
              severity=severity, active=True, created_by=created_by)
    db.add(w)
    db.commit()
    found = len(scan(db, None, [w])) if backfill else 0
    return w, found, True


def remove(db: Session, watch_id: str) -> bool:
    """Delete a watch and the hits that only exist because of it."""
    w = db.get(Watch, watch_id)
    if w is None:
        return False
    db.query(WatchHit).filter(WatchHit.watch_id == watch_id).delete(synchronize_session=False)
    db.delete(w)
    db.commit()
    return True
