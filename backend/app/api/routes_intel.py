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
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "description": a.description, "score": a.score,
            "status": a.status, "evidence": a.evidence, "created_at": a.created_at.isoformat(),
            "entities": [{"id": e, "label": G.nodes[e]["label"], "type": G.nodes[e]["type"]} for e in (a.entity_ids or []) if e in G][:12]}


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
    status: str


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: str, body: AlertPatch, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if body.status not in ("open", "reviewing", "dismissed", "confirmed"):
        raise HTTPException(400, "Bad status")
    a.status = body.status
    db.commit()
    audit(db, user, "alert_status", f"{a.title} -> {body.status}")
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
def capabilities(_: Annotated[User, Depends(current_user)]):
    return {"llm": llm.available(), "model": llm.settings.llm_model if llm.available() else None,
            "examples": ["Who are the key players?", "Who is Rafiq Sheikh?", "Path between Salim Qureshi and Rakesh Mehta",
                         "Show burner phones", "Money flow for Skyline Infra Ventures", "Which communities are suspicious?",
                         "What happens if we arrest Salim Qureshi?", "Who does Vikram Naik call?", "Predict hidden links"]}


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
    events = [{"id": e.id, "kind": e.kind, "at": e.occurred_at.isoformat(), "summary": e.summary, "lat": e.lat, "lon": e.lon}
              for e in db.query(TimelineEvent).filter(TimelineEvent.lat.isnot(None), TimelineEvent.kind.in_(["SIGHTING", "FIR", "POST"])).all()]
    return {"locations": locs, "events": events}
