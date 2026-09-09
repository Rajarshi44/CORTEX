"""Graph, entity and analytics endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import current_user, require_role
from ..db import TimelineEvent, User, get_session
from ..graph import queries as Q
from ..graph.analytics import actor_projection, removal_impact
from ..graph.store import graph_cache
from .deps import analysis_service

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
def graph(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
          types: Annotated[list[str] | None, Query()] = None, community: int | None = None, min_priority: float = 0.0,
          focus: str | None = None, depth: int = 2, limit: int = 400, include_infra: bool = True):
    """Return a renderable subgraph. Default: the most relevant `limit` nodes (by priority / degree)."""
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    if focus:
        nodes = Q.ego(G, focus, depth=depth, max_nodes=limit)
    else:
        prio = snap.get("priority", {})
        fm = snap.get("full_metrics", {})
        comm = snap.get("community", {})
        cand = []
        for n, d in G.nodes(data=True):
            if types and d["type"] not in types:
                continue
            if community is not None and comm.get(n) != community:
                # keep infra nodes attached to community members
                if d["type"] in ("PERSON", "ORGANIZATION"):
                    continue
            score = prio.get(n, 0.0) * 10 + fm.get(n, {}).get("pagerank", 0) * 100 + (0.02 * G.degree(n))
            if prio.get(n, 0.0) < min_priority and d["type"] in ("PERSON", "ORGANIZATION"):
                continue
            cand.append((score, n))
        cand.sort(reverse=True)
        actors = [n for _, n in cand if G.nodes[n]["type"] in ("PERSON", "ORGANIZATION")][: max(20, limit // 3)]
        nodes = set(actors)
        if include_infra:
            for a in actors:
                for nb in G.neighbors(a):
                    if len(nodes) >= limit:
                        break
                    if community is not None and G.nodes[nb]["type"] in ("PERSON", "ORGANIZATION") and comm.get(nb) != community:
                        continue
                    if types and G.nodes[nb]["type"] not in types:
                        continue
                    nodes.add(nb)
        if community is not None:
            nodes = {n for n in nodes if G.nodes[n]["type"] not in ("PERSON", "ORGANIZATION") or comm.get(n) == community}
    payload = Q.subgraph_payload(G, D, set(nodes), snap)
    payload["meta"] = {"total_nodes": G.number_of_nodes(), "total_edges": D.number_of_edges(), "returned": len(payload["nodes"]),
                       "computed_at": snap.get("computed_at")}
    return payload


@router.get("/graph/projection")
def projection(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], min_weight: float = 0.0,
               only_poi: bool = False):
    """Actor-level projection (persons/orgs only) with channel explanations - the 'who knows whom' view."""
    G = graph_cache.get(db)
    snap = analysis_service.snapshot(db)
    susp = snap.get("suspicion", {})
    edges = [e for e in snap.get("projection_edges", []) if e["weight"] >= min_weight]
    if only_poi:
        edges = [e for e in edges if susp.get(e["source"], {}).get("score", 0) >= 0.2 or susp.get(e["target"], {}).get("score", 0) >= 0.2]
    nodes = {n for e in edges for n in (e["source"], e["target"])}
    return {"nodes": [Q.node_view(G, n, snap) for n in nodes if n in G], "edges": edges}


@router.get("/graph/path")
def path(src: str, dst: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], k: int = 3):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    paths = Q.shortest_paths(G, src, dst, k=k)
    nodes = {n for p in paths for n in p} | {src, dst}
    return {"paths": [Q.describe_path(G, D, p) for p in paths], "subgraph": Q.subgraph_payload(G, D, nodes, snap)}


@router.get("/entities")
def entities(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], q: str = "",
             types: Annotated[list[str] | None, Query()] = None, sort: str = "priority", limit: int = 50,
             offset: int = 0, roles: Annotated[list[str] | None, Query()] = None, exclude_roles: bool = False):
    """
    The entity table, served whole.

    `limit=0` returns every row so a client can hold the full set; otherwise page with
    `offset`. `total` is always the unpaged count, so the UI can say how much it is not showing
    instead of quietly truncating. `roles` filters on standing in the record (judge, institution,
    authority, petitioner, respondent); `exclude_roles=true` inverts it, which is how a caller asks
    for subjects only rather than court machinery.
    """
    from ..db import Entity

    G = graph_cache.get(db)
    snap = analysis_service.snapshot(db)
    if q:
        rows = Q.find_entities(db, q, types, limit or 10_000)
        ids, total = [e.id for e in rows], len(rows)
    else:
        query = db.query(Entity)
        if types:
            query = query.filter(Entity.type.in_(types))
        if roles:
            # as_string() rather than .astext: the column is a generic JSON, so this has to work on
            # SQLite (local dev) as well as Postgres.
            role_col = Entity.attributes["record_role"].as_string()
            if exclude_roles:
                # Most entities carry no role at all, and `NOT (NULL IN (...))` is NULL rather than
                # true - without the explicit null test, asking for "everything except judges" would
                # return only the entities that happen to have some other role.
                query = query.filter(or_(role_col.is_(None), role_col.notin_(roles)))
            else:
                query = query.filter(role_col.in_(roles))
        total = query.count()
        order = Entity.risk_score.desc() if sort == "priority" else Entity.mention_count.desc()
        query = query.order_by(order).offset(max(offset, 0))
        if limit:
            query = query.limit(limit)
        ids = [e.id for e in query.all()]
    items = [Q.node_view(G, i, snap) for i in ids if i in G]
    return {"items": items, "total": total, "offset": offset, "limit": limit,
            "returned": len(items), "complete": len(items) >= total}


@router.get("/entities/{eid}")
def entity(eid: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    d = Q.entity_dossier(db, G, D, snap, eid)
    if not d:
        raise HTTPException(404, "Entity not found")
    if G.nodes[eid]["type"] in ("PERSON", "ORGANIZATION", "BANK_ACCOUNT"):
        d["money"] = Q.money_flow(db, G, D, eid)
    if G.nodes[eid]["type"] in ("PERSON", "PHONE"):
        d["calls"] = Q.call_profile(db, G, D, eid)
    from ..db import EntityNote
    notes = db.query(EntityNote).filter(EntityNote.entity_id == eid).order_by(EntityNote.created_at.desc()).all()
    d["notes"] = [{"id": n.id, "username": n.username, "text": n.text, "created_at": n.created_at.isoformat()} for n in notes]
    return d


class NoteIn(BaseModel):
    text: str

@router.post("/entities/{eid}/notes", dependencies=[Depends(require_role("analyst"))])
def add_entity_note(eid: str, body: NoteIn, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    from ..db import EntityNote, Entity
    if not db.get(Entity, eid):
        raise HTTPException(404, "Entity not found")
    note = EntityNote(entity_id=eid, username=user.username, text=body.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "username": note.username, "text": note.text, "created_at": note.created_at.isoformat()}

@router.put("/entities/{eid}/notes/{note_id}", dependencies=[Depends(require_role("analyst"))])
def update_entity_note(eid: str, note_id: int, body: NoteIn, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    from ..db import EntityNote
    note = db.get(EntityNote, note_id)
    if not note or note.entity_id != eid:
        raise HTTPException(404, "Note not found")
    if note.username != user.username and user.role != "admin":
        raise HTTPException(403, "Not authorized to edit this note")
    note.text = body.text
    db.commit()
    db.refresh(note)
    return {"id": note.id, "username": note.username, "text": note.text, "created_at": note.created_at.isoformat()}

@router.delete("/entities/{eid}/notes/{note_id}", dependencies=[Depends(require_role("analyst"))])
def delete_entity_note(eid: str, note_id: int, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    from ..db import EntityNote
    note = db.get(EntityNote, note_id)
    if not note or note.entity_id != eid:
        raise HTTPException(404, "Note not found")
    if note.username != user.username and user.role != "admin":
        raise HTTPException(403, "Not authorized to delete this note")
    db.delete(note)
    db.commit()
    return {"ok": True}


@router.get("/entities/{eid}/ego")
def entity_ego(eid: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], depth: int = 1, limit: int = 120):
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    nodes = Q.ego(G, eid, depth, limit)
    if not nodes:
        raise HTTPException(404, "Entity not found")
    return Q.subgraph_payload(G, D, nodes, snap)


SOURCE_NAMES = {
    "LEAK": "ICIJ Offshore Leaks (2026)",
    "WATCHLIST": "OpenSanctions (Sep 2026) / INTERPOL Red Notices",
    "JUDGMENT": "Supreme Court / High Court Judgments",
    "GLEIF": "GLEIF Global Legal Entity Identifier Foundation",
    "NEWS": "OSINT / Cyber Threat Intelligence (2026)",
    "INTEL": "CBI / NIA Intelligence Notes",
    "FIR": "I4C / NCRP (National Cyber Crime Reporting Portal)",
    "CDR": "Telecom CDRs (Call Detail Records)",
    "TRANSACTION": "FIU-IND STRs (Suspicious Transaction Reports)",
    "KYC": "C-KYC (Central KYC Registry)",
    "SURVEILLANCE": "CERT-In Surveillance Reports",
    "SOCIAL": "Social Media OSINT",
    "BENCHMARK": "FATF Benchmark Networks",
    "STATS": "NCRB Statistics",
    "FIR_EXTRACT": "State Police FIR Extracts",
    "ARREST_MEMO": "Arrest Memos (Section 41 CrPC)",
    "RAID_REPORT": "Enforcement Directorate (ED) Raid Reports",
    "SURVEILLANCE_REPORT": "Technical Surveillance Reports",
    "FORENSIC_REPORT": "CFSL Cyber Forensic Reports",
    "INTELLIGENCE_NOTE": "Intelligence Bureau (IB) Notes"
}


def sheet_identity(db: Session) -> dict:
    """What this sheet is, derived from what is on it. Real public-record sheets and the synthetic demo differ in name."""
    from sqlalchemy import func

    from ..db import Document

    counts = dict(db.query(Document.source_type, func.count()).group_by(Document.source_type).all())
    public = {"LEAK", "WATCHLIST", "JUDGMENT", "GLEIF", "NEWS"} & set(counts)
    synthetic = {"FIR", "CDR", "TRANSACTION", "KYC", "SURVEILLANCE", "SOCIAL", "INTEL", "FIR_EXTRACT", "ARREST_MEMO", "RAID_REPORT", "SURVEILLANCE_REPORT", "FORENSIC_REPORT", "INTELLIGENCE_NOTE"} & set(counts)
    srcs = [SOURCE_NAMES.get(k, k) for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    if public and not synthetic:
        return {"title": "Public Record Sheet: India", "code": "PRS-IN", "kind": "real", "sources": srcs,
                "subtitle": "Drawn from public records only: " + ", ".join(srcs[:6]) + ". No synthetic data."}
    if public and synthetic:
        return {"title": "Operation CyberHawk 2.0 + Public Records", "code": "OPS-CH2", "kind": "mixed", "sources": srcs,
                "subtitle": "Operation CyberHawk 2.0 case corpus joined with real public records: " + ", ".join(srcs[:6]) + "."}
    if synthetic:
        return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "demo", "sources": srcs,
                "subtitle": "Delhi Crime Branch / I4C Cyber Crime Investigation (Mule Accounts & Syndicates)."}
    return {"title": "Empty sheet", "code": "-", "kind": "empty", "sources": [], "subtitle": "Nothing ingested yet."}


@router.get("/analytics/summary")
def summary(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    snap = analysis_service.snapshot(db)
    return {"summary": snap.get("summary", {}), "computed_at": snap.get("computed_at"), "alert_count": snap.get("alert_count", 0),
            "last_run": analysis_service.last_run, "sheet": sheet_identity(db)}


@router.get("/analytics/key-players")
def key_players(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    snap = analysis_service.snapshot(db)
    return {"key_players": snap.get("key_players", []), "brokers": snap.get("brokers", []), "removal_impact": snap.get("removal_impact", {})}


@router.get("/analytics/communities")
def communities(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    snap = analysis_service.snapshot(db)
    return snap.get("communities", [])


@router.get("/analytics/link-predictions")
def link_predictions(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    snap = analysis_service.snapshot(db)
    return snap.get("link_predictions", [])


@router.get("/analytics/impact/{eid}")
def impact(eid: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    D = graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    res = removal_impact(actor_projection(D), eid, snap.get("community"))
    if not res:
        raise HTTPException(404, "Not an actor node")
    return res


@router.post("/analytics/recompute")
def recompute(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    analysis_service.snapshot(db, force=True)
    return analysis_service.last_run


@router.get("/timeline")
def timeline(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], kinds: Annotated[list[str] | None, Query()] = None,
             entity: str | None = None, start: str | None = None, end: str | None = None, limit: int = 500, only_poi: bool = True):
    """Events for the timeline / map. By default restricted to persons-of-interest to keep it readable."""
    G = graph_cache.get(db)
    snap = analysis_service.snapshot(db)
    susp = snap.get("suspicion", {})
    owner_of = {}
    D = graph_cache.get_directed(db)
    for u, v, d in D.edges(data=True):
        if d["rel_type"] in ("USES_PHONE", "OWNS_ACCOUNT"):
            owner_of.setdefault(v, u)
    poi = {n for n, s in susp.items() if s.get("score", 0) >= 0.2}
    q = db.query(TimelineEvent)
    if kinds:
        q = q.filter(TimelineEvent.kind.in_(kinds))
    if start:
        q = q.filter(TimelineEvent.occurred_at >= start)
    if end:
        q = q.filter(TimelineEvent.occurred_at <= end)
    out = []
    matched = 0
    for e in q.order_by(TimelineEvent.occurred_at).all():
        ids = e.entity_ids or []
        if entity and entity not in ids:
            continue
        actors = {owner_of.get(i, i) for i in ids}
        if only_poi and not entity and not (actors & poi):
            continue
        matched += 1
        if limit and len(out) >= limit:
            continue  # keep counting so `total` is honest about what the cap is hiding
        out.append({"id": e.id, "kind": e.kind, "at": e.occurred_at.isoformat(), "summary": e.summary, "details": e.details, "lat": e.lat, "lon": e.lon,
                    "entity_ids": ids, "actors": [{"id": a, "label": G.nodes[a]["label"]} for a in actors if a in G][:6], "document_id": e.document_id})
    return {"items": out, "total": matched, "returned": len(out), "limit": limit,
            "complete": len(out) == matched}


@router.get("/timeline/histogram")
def histogram(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], bucket: str = "day", only_poi: bool = True):
    from collections import Counter

    events = timeline(db, _, None, None, None, None, 0, only_poi)["items"]  # type: ignore[arg-type]
    c: dict[str, Counter] = {}
    for e in events:
        key = e["at"][:10] if bucket == "day" else e["at"][:7]
        c.setdefault(key, Counter())[e["kind"]] += 1
    return [{"bucket": k, **dict(v)} for k, v in sorted(c.items())]
