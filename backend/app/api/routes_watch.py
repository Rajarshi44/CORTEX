"""Standing watches: create a selector, and every arriving record is checked against it."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import audit, current_user, require_role
from ..db import Document, Entity, User, Watch, WatchHit, get_session
from ..ingestion.quality import is_non_subject, role_of
from ..watch import matcher

router = APIRouter(prefix="/api/watches", tags=["watches"])

# What each kind is for, in the words an analyst would use. Served to the UI so the form explains
# itself rather than needing a manual beside it.
KIND_HELP: dict[str, str] = {
    "PERSON": "A named individual, matched on the exact canonical name - a different spelling will not fire it, but a different person with the same name will. Watch an identifier instead where you have one.",
    "ORGANIZATION": "A company, trust or firm, matched on its registry-normalised name. Same caveat as a person: the name is not the identity.",
    "PHONE": "A ten-digit number. Fires on call records as well as on prose that names it.",
    "VEHICLE": "A registration plate, spacing and hyphens ignored.",
    "BANK_ACCOUNT": "An account number or a UPI handle.",
    "GOV_ID": "Aadhaar, PAN, passport, voter ID, GSTIN or driving licence. Checksum-validated on entry; a sensitive number is stored only as a salted fingerprint and displayed masked.",
    "TEXT": "A literal phrase in a document's title or body. Case-folded substring, nothing cleverer.",
}


def _watch_view(w: Watch) -> dict:
    return {"id": w.id, "kind": w.kind, "selector": w.selector, "reason": w.reason, "severity": w.severity,
            "active": w.active, "created_by": w.created_by, "created_at": w.created_at.isoformat(),
            "last_hit_at": w.last_hit_at.isoformat() if w.last_hit_at else None, "hit_count": w.hit_count}


def _hit_view(h: WatchHit, w: Watch | None, doc: Document | None, ent: Entity | None) -> dict:
    return {"id": h.id, "watch_id": h.watch_id, "status": h.status, "matched_on": h.matched_on,
            "snippet": h.snippet, "created_at": h.created_at.isoformat(),
            "occurred_at": h.occurred_at.isoformat() if h.occurred_at else None,
            "watch": {"kind": w.kind, "selector": w.selector, "reason": w.reason, "severity": w.severity} if w else None,
            "document": {"id": doc.id, "title": doc.title, "source_type": doc.source_type} if doc else None,
            "entity": _entity_view(ent)}


def _entity_view(ent: Entity | None) -> dict | None:
    """Carry the entity's standing in the record onto the hit.

    A name watch fires on every appearance of that name, and on a corpus of judgments the busiest
    name is often the judge. Saying so on the row is the difference between a lead and a distraction
    - the analyst sees at a glance that this is the machinery of a case rather than a subject of it.
    """
    if ent is None:
        return None
    attrs = ent.attributes or {}
    return {"id": ent.id, "label": ent.label, "type": ent.type,
            "record_role": role_of(ent.type, ent.label, attrs),
            "non_subject": is_non_subject(ent.type, ent.label, attrs)}


@router.get("/kinds")
def kinds(_: Annotated[User, Depends(current_user)]):
    """What can be watched, and what each kind means."""
    return {"kinds": [{"kind": k, "help": KIND_HELP[k]} for k in matcher.WATCH_KINDS],
            "severities": list(matcher.SEVERITIES), "statuses": list(matcher.HIT_STATUSES)}


# Declared before /{watch_id} so "hits" is never read as an id.
@router.get("/hits")
def hits(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
         status: str | None = None, watch_id: str | None = None, limit: int = 200):
    """Every record that matched a watch, newest first."""
    q = db.query(WatchHit)
    if status:
        q = q.filter(WatchHit.status == status)
    if watch_id:
        q = q.filter(WatchHit.watch_id == watch_id)
    rows = q.order_by(WatchHit.created_at.desc(), WatchHit.id.desc()).limit(max(1, min(limit, 1000))).all()
    watches = {w.id: w for w in db.query(Watch).all()}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_([h.document_id for h in rows]))} if rows else {}
    eids = [h.entity_id for h in rows if h.entity_id]
    ents = {e.id: e for e in db.query(Entity).filter(Entity.id.in_(eids))} if eids else {}
    return [_hit_view(h, watches.get(h.watch_id), docs.get(h.document_id), ents.get(h.entity_id)) for h in rows]


class HitPatch(BaseModel):
    status: str


@router.patch("/hits/{hit_id}")
def patch_hit(hit_id: int, body: HitPatch, db: Annotated[Session, Depends(get_session)],
              user: Annotated[User, Depends(current_user)]):
    """Record an analyst's decision on a hit. The hit itself is never deleted by a recompute."""
    h = db.get(WatchHit, hit_id)
    if not h:
        raise HTTPException(404, "Hit not found")
    if body.status not in matcher.HIT_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(matcher.HIT_STATUSES)}")
    h.status = body.status
    db.commit()
    audit(db, user, "watch_hit_status", f"{h.matched_on} -> {body.status}")
    w = db.get(Watch, h.watch_id)
    return _hit_view(h, w, db.get(Document, h.document_id), db.get(Entity, h.entity_id) if h.entity_id else None)


@router.get("")
def list_watches(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
                 active: bool | None = None):
    q = db.query(Watch)
    if active is not None:
        q = q.filter(Watch.active.is_(active))
    rows = q.order_by(Watch.created_at.desc()).all()
    new_counts = dict(db.query(WatchHit.watch_id, func.count(WatchHit.id))
                      .filter(WatchHit.status == "new").group_by(WatchHit.watch_id).all())
    return [{**_watch_view(w), "new_hits": int(new_counts.get(w.id, 0))} for w in rows]


class WatchIn(BaseModel):
    kind: str
    value: str
    reason: str = ""
    severity: str = "high"


@router.post("", dependencies=[Depends(require_role("analyst"))])
def create_watch(body: WatchIn, db: Annotated[Session, Depends(get_session)],
                 user: Annotated[User, Depends(current_user)]):
    """Arm a watch and immediately check it against the records already held.

    The backfill is what makes this useful on day one: the answer to "has this number ever
    appeared" comes back with the watch, rather than only from the next harvest.
    """
    try:
        w, found, created = matcher.create(db, body.kind, body.value, body.reason, body.severity, user.username)
    except matcher.WatchError as exc:
        raise HTTPException(400, str(exc))
    audit(db, user, "watch_create" if created else "watch_reuse", f"{w.kind} {w.selector} ({found} in existing records)")
    return {**_watch_view(w), "created": created, "backfill_hits": found,
            "note": ("This selector was already being watched; it has been joined rather than duplicated."
                     if not created else None)}


class WatchPatch(BaseModel):
    active: bool | None = None
    severity: str | None = None
    reason: str | None = None


@router.patch("/{watch_id}", dependencies=[Depends(require_role("analyst"))])
def patch_watch(watch_id: str, body: WatchPatch, db: Annotated[Session, Depends(get_session)],
                user: Annotated[User, Depends(current_user)]):
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "Watch not found")
    if body.severity is not None:
        if body.severity not in matcher.SEVERITIES:
            raise HTTPException(400, f"Severity must be one of: {', '.join(matcher.SEVERITIES)}")
        w.severity = body.severity
    if body.active is not None:
        w.active = body.active
    if body.reason is not None:
        w.reason = body.reason.strip()
    db.commit()
    audit(db, user, "watch_update", f"{w.kind} {w.selector}")
    return _watch_view(w)


@router.post("/{watch_id}/rescan", dependencies=[Depends(require_role("analyst"))])
def rescan(watch_id: str, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    """Re-run one watch over the whole corpus. Hits already recorded are not duplicated."""
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "Watch not found")
    found = len(matcher.scan(db, None, [w]))
    audit(db, user, "watch_rescan", f"{w.kind} {w.selector}: {found} new")
    return {**_watch_view(w), "new_hits": found}


@router.delete("/{watch_id}", dependencies=[Depends(require_role("analyst"))])
def delete_watch(watch_id: str, db: Annotated[Session, Depends(get_session)],
                 user: Annotated[User, Depends(current_user)]):
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "Watch not found")
    label = f"{w.kind} {w.selector}"
    matcher.remove(db, watch_id)
    audit(db, user, "watch_delete", label)
    return {"deleted": True}
