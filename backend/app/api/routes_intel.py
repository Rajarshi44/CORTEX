"""Alerts, investigator assistant, reports, geo."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai import llm
from ..ai.investigator import Investigator
from ..auth import audit, current_user
from ..db import Alert, TimelineEvent, User, get_session
from ..graph import queries as Q
from ..graph.store import graph_cache
from ..reports.generator import build_markdown, build_pdf
from .deps import analysis_service

router = APIRouter(prefix="/api", tags=["intel"])


def _alert_view(a: Alert, G) -> dict:
    is_pending = a.review_status == "pending" and a.severity in ("high", "critical")
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "description": a.description, "score": a.score,
            "status": a.status, "review_status": a.review_status, "reviewed_by": a.reviewed_by, "evidence": a.evidence, "created_at": a.created_at.isoformat(),
            "entities": [{"id": e, "label": "Pending analyst review" if is_pending else G.nodes[e]["label"], "type": G.nodes[e]["type"]} for e in (a.entity_ids or []) if e in G][:12]}


@router.get("/alerts")
def alerts(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], status: str | None = None,
           kind: str | None = None, severity: str | None = None, entity: str | None = None, limit: int = 200):
    analysis_service.snapshot(db)
    G = graph_cache.get(db)
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    if kind:
        q = q.filter(Alert.kind == kind)
    if severity:
        q = q.filter(Alert.severity == severity)
    rows = q.order_by(Alert.score.desc()).limit(limit).all()
    if entity:
        rows = [a for a in rows if entity in (a.entity_ids or [])]
    return [_alert_view(a, G) for a in rows]


class AlertPatch(BaseModel):
    status: str | None = None
    review_status: str | None = None


@router.get("/alerts/detectors")
def detectors(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """The detector roster, each marked with what it found and, if nothing, why.

    A register showing three findings says nothing about the seven detectors that found none, and a
    reader cannot tell a quiet corpus from a broken build. Two silences are worth telling apart:
    a detector with no record to read at all, and a detector that read the record and found nothing.
    Only the first is a gap in the sheet; the second is a result.
    """
    from sqlalchemy import func

    from ..graph.anomalies import DETECTORS

    counts = dict(db.query(Alert.kind, func.count()).group_by(Alert.kind).all())
    events = dict(db.query(TimelineEvent.kind, func.count()).group_by(TimelineEvent.kind).all())
    G = graph_cache.get(db)
    # what each feed needs, measured on this sheet
    have = {
        "CALL": events.get("CALL", 0),
        "TRANSFER": events.get("TRANSFER", 0),
        "COMPLAINT": events.get("COMPLAINT", 0),
        "WATCHLIST": sum(1 for _, d in G.nodes(data=True) if (d.get("attrs") or {}).get("watchlist")
                         or (d.get("attrs") or {}).get("wanted_notice")),
        "ACTORS": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "PERSON"),
    }
    unit = {"CALL": "call records", "TRANSFER": "transfers", "COMPLAINT": "complaints",
            "WATCHLIST": "watchlisted entities", "ACTORS": "persons"}
    rows = []
    for d in DETECTORS:
        fired = sum(counts.get(k, 0) for k in d["kinds"])
        held = have.get(d["feed"], 0)
        rows.append({
            "name": d["name"], "kinds": d["kinds"], "needs": d["needs"], "looks_for": d["looks_for"],
            "alerts": fired, "fired": fired > 0, "records_held": held, "records_unit": unit.get(d["feed"], "records"),
            # "silent" = ran over real records and found nothing; "starved" = nothing to read
            "state": "fired" if fired else ("silent" if held else "starved"),
        })
    return {"detectors": rows, "total": len(rows), "fired": sum(1 for r in rows if r["fired"]),
            "silent": sum(1 for r in rows if r["state"] == "silent"),
            "starved": sum(1 for r in rows if r["state"] == "starved"),
            "alerts": sum(counts.values())}


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: str, body: AlertPatch, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if body.status is not None:
        if body.status not in ("open", "reviewing", "dismissed", "confirmed"):
            raise HTTPException(400, "Bad status")
        a.status = body.status
        audit(db, user, "alert_status", f"{a.title} -> {body.status}")
    if body.review_status is not None:
        if body.review_status not in ("pending", "reviewed", "escalated"):
            raise HTTPException(400, "Bad review_status")
        a.review_status = body.review_status
        a.reviewed_by = user.username
        audit(db, user, "alert_review", f"{a.title} -> {body.review_status}")
    db.commit()
    # invalidate cache since pending_reviews changed
    analysis_service.invalidate()
    return _alert_view(a, graph_cache.get(db))


class Ask(BaseModel):
    question: str


@router.post("/assistant/ask")
def ask(body: Ask, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    res = Investigator(db, G, D, snap).answer(body.question)
    audit(db, user, "assistant_query", body.question)
    res["highlight_nodes"] = [{"id": n, "label": G.nodes[n]["label"], "type": G.nodes[n]["type"]} for n in res["highlights"]["nodes"] if n in G]
    return res


@router.get("/assistant/capabilities")
def capabilities(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """What the investigator can be asked, phrased with names that are on this sheet.

    These were a fixed list written against the synthetic corpus, so on every other sheet each
    example named somebody who does not exist and following the suggestion failed. Questions that
    need no name stay verbatim; the rest are filled in from the ranking, and dropped when the sheet
    has nobody to put in them.
    """
    kp = [k for k in (analysis_service.snapshot(db).get("key_players") or []) if k.get("label")]
    names = [k["label"] for k in kp[:3]]
    orgs = [k["label"] for k in kp if k.get("type") == "ORGANIZATION"]

    examples = ["Who are the key players?"]
    if names:
        examples.append(f"Who is {names[0]}?")
    if len(names) >= 2:
        examples.append(f"Path between {names[0]} and {names[1]}")
    money = orgs[0] if orgs else (names[0] if names else None)
    if money:
        examples.append(f"Money flow for {money}")
    examples.append("Which communities are suspicious?")
    if names:
        examples.append(f"What happens if we arrest {names[0]}?")
    examples += ["Show the open alerts", "Predict hidden links"]

    return {"llm": llm.available(), "model": llm.settings.llm_model if llm.available() else None,
            "examples": examples}


@router.get("/reports/brief.md")
def report_md(db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    md = build_markdown(db, G, D, analysis_service.snapshot(db))
    audit(db, user, "report_md")
    return Response(md, media_type="text/markdown; charset=utf-8")


@router.get("/reports/brief.pdf")
def report_pdf(db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    md = build_markdown(db, G, D, analysis_service.snapshot(db))
    audit(db, user, "report_pdf")
    return Response(build_pdf(md), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=network-brief.pdf"})


@router.get("/geo")
def geo(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """Locations with activity counts + geo-tagged events for the map."""
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    susp = snap.get("suspicion", {})
    locs = []
    for n, d in G.nodes(data=True):
        if d["type"] != "LOCATION" or d["attrs"].get("lat") is None:
            continue
        actors = set()
        for u, _, r in D.in_edges(n, data=True):
            if r["rel_type"] in ("RESIDES_AT", "SEEN_AT", "POSTED_FROM", "LOCATED_AT") and G.nodes[u]["type"] in ("PERSON", "ORGANIZATION"):
                actors.add(u)
        poi = [a for a in actors if susp.get(a, {}).get("score", 0) >= 0.2]
        locs.append({"id": n, "label": d["label"], "lat": d["attrs"]["lat"], "lon": d["attrs"]["lon"], "degree": G.degree(n),
                     "actors": len(actors), "poi": [{"id": a, "label": G.nodes[a]["label"]} for a in sorted(poi, key=lambda a: -susp[a]["score"])[:6]],
                     "risk": round(sum(susp.get(a, {}).get("score", 0) for a in actors) / max(len(actors), 1), 3)})
    # Every geo-tagged event, whatever its kind. The previous hard-coded ("SIGHTING", "FIR", "POST")
    # filter was written for the synthetic case and silently emptied the map for the public-record
    # corpus, whose events are JUDGMENT and NEWS. Kinds come from the data, not from a list here.
    rows = db.query(TimelineEvent).filter(TimelineEvent.lat.isnot(None)).order_by(TimelineEvent.occurred_at).all()
    events = [{"id": e.id, "kind": e.kind, "at": e.occurred_at.isoformat(), "summary": e.summary,
               "lat": e.lat, "lon": e.lon, "document_id": e.document_id, "entity_ids": e.entity_ids or [],
               # how precisely we actually know the place, so the map never implies a street address
               "precision": ((e.details or {}).get("geo") or {}).get("precision"),
               "placed_at": ((e.details or {}).get("geo") or {}).get("matched")}
              for e in rows]
    return {"locations": locs, "events": events,
            "kinds": sorted({e["kind"] for e in events}),
            "meta": {"events": len(events), "locations": len(locs),
                     "events_total": db.query(TimelineEvent).count()}}
