"""Read-side graph queries shared by the REST API, the investigator assistant and the report generator."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import Alert, Document, Entity, Evidence, TimelineEvent
from ..ingestion import provenance

REL_VERB = {
    "CALLED": "called", "TRANSFERRED_TO": "transferred money to", "USES_PHONE": "uses phone", "OWNS_ACCOUNT": "holds account",
    "MET": "met", "SEEN_AT": "seen at", "RESIDES_AT": "resides at", "ACCUSED_IN": "accused in", "COMPLAINANT_IN": "complainant in",
    "MENTIONED_IN": "mentioned in", "ASSOCIATED_VEHICLE": "associated with vehicle", "OWNS": "owns", "DIRECTOR_OF": "director of",
    "AFFILIATED_WITH": "affiliated with", "REPORTS_TO": "acts on instructions of", "CO_ACCUSED": "co-accused with",
    "MENTIONED_WITH": "mentioned alongside", "COMMUNICATED_WITH": "communicates with", "OWNS_HANDLE": "owns handle",
    "MENTIONED": "mentioned", "POSTED_FROM": "posted from", "PINGED_AT": "pinged tower at", "SUBJECT_OF": "subject of",
    "REGISTERED_AT": "registered at", "LOCATED_AT": "located at", "OWNED_BY": "owned by", "SHARED_HANDSET": "shares handset (IMEI) with",
}


def node_view(G: nx.Graph, n: str, snapshot: dict | None = None) -> dict:
    d = G.nodes[n]
    snap = snapshot or {}
    m = snap.get("metrics", {}).get(n, {})
    fm = snap.get("full_metrics", {}).get(n, {})
    return {
        "id": n, "type": d["type"], "label": d["label"], "aliases": d.get("aliases", []), "attrs": d.get("attrs", {}),
        "mentions": d.get("mentions", 0), "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
        "community": snap.get("community", {}).get(n), "role": snap.get("roles", {}).get(n, {}).get("label"),
        "role_reasons": snap.get("roles", {}).get(n, {}).get("reasons", []),
        "influence": m.get("influence", 0.0), "priority": snap.get("priority", {}).get(n, 0.0),
        "suspicion": snap.get("suspicion", {}).get(n, {}).get("score", 0.0),
        "suspicion_reasons": snap.get("suspicion", {}).get(n, {}).get("reasons", []),
        "degree": fm.get("degree", G.degree(n)), "pagerank": fm.get("pagerank", 0.0), "metrics": m,
    }


def edge_view(D: nx.DiGraph, u: str, v: str, d: dict) -> dict:
    return {"id": d["id"], "source": u, "target": v, "rel_type": d["rel_type"], "weight": d["weight"], "count": d["count"],
            "attrs": d.get("attrs", {}), "confidence": d.get("confidence", 1.0), "first_seen": d.get("first_seen"),
            "last_seen": d.get("last_seen"), "verb": REL_VERB.get(d["rel_type"], d["rel_type"].lower().replace("_", " "))}


def subgraph_payload(G: nx.Graph, D: nx.DiGraph, nodes: set[str], snapshot: dict | None = None, max_edges: int = 6000) -> dict:
    edges = []
    for u, v, d in D.edges(data=True):
        if u in nodes and v in nodes:
            edges.append(edge_view(D, u, v, d))
            if len(edges) >= max_edges:
                break
    return {"nodes": [node_view(G, n, snapshot) for n in nodes], "edges": edges}


def find_entities(db: Session, q: str, types: list[str] | None = None, limit: int = 20) -> list[Entity]:
    q = q.strip()
    if not q:
        return []
    query = db.query(Entity)
    if types:
        query = query.filter(Entity.type.in_(types))
    digits = re.sub(r"\D", "", q)
    conds = [Entity.label.ilike(f"%{q}%"), Entity.canonical_key.ilike(f"%{q.lower()}%")]
    if len(digits) >= 4:
        conds.append(Entity.canonical_key.ilike(f"%{digits}%"))
    rows = query.filter(or_(*conds)).limit(limit * 3).all()
    # alias hits
    alias_rows = [e for e in db.query(Entity).filter(Entity.type == "PERSON").all() if any(q.lower() in a.lower() for a in (e.aliases or []))]
    seen, out = set(), []
    for e in rows + alias_rows:
        if e.id not in seen:
            seen.add(e.id)
            out.append(e)
    out.sort(key=lambda e: (-fuzz.WRatio(q, e.label), -(e.mention_count or 0)))
    return out[:limit]


def fuzzy_entity(G: nx.Graph, name: str, types: tuple[str, ...] = ("PERSON", "ORGANIZATION"), threshold: int = 80) -> str | None:
    cands = {}
    for n, d in G.nodes(data=True):
        if d["type"] in types:
            cands[d["label"]] = n
            for a in d.get("aliases", []):
                cands.setdefault(a, n)
    if not cands:
        return None
    best = process.extractOne(name, list(cands), scorer=fuzz.WRatio)
    return cands[best[0]] if best and best[1] >= threshold else None


def shortest_paths(G: nx.Graph, src: str, dst: str, k: int = 3, cutoff: int = 6) -> list[list[str]]:
    if src not in G or dst not in G or not nx.has_path(G, src, dst):
        return []
    paths = []
    try:
        gen = nx.shortest_simple_paths(G, src, dst)
        for p in gen:
            if len(p) - 1 > cutoff:
                break
            paths.append(p)
            if len(paths) >= k:
                break
    except nx.NetworkXNoPath:
        return []
    return paths


def describe_path(G: nx.Graph, D: nx.DiGraph, path: list[str]) -> list[dict]:
    hops = []
    for a, b in zip(path, path[1:]):
        d = D.get_edge_data(a, b) or D.get_edge_data(b, a) or {}
        rt = d.get("rel_type", "linked to")
        hops.append({"from": {"id": a, "label": G.nodes[a]["label"], "type": G.nodes[a]["type"]},
                     "to": {"id": b, "label": G.nodes[b]["label"], "type": G.nodes[b]["type"]},
                     "rel_type": rt, "verb": REL_VERB.get(rt, rt.lower()), "count": d.get("count", 1), "attrs": d.get("attrs", {})})
    return hops


def ego(G: nx.Graph, n: str, depth: int = 1, max_nodes: int = 150, skip_types: tuple[str, ...] = ()) -> set[str]:
    if n not in G:
        return set()
    seen, frontier = {n}, {n}
    for _ in range(depth):
        nxt = set()
        for u in frontier:
            for v in sorted(G.neighbors(u), key=lambda x: -G[u][x].get("weight", 1)):
                if G.nodes[v]["type"] in skip_types:
                    continue
                if v not in seen:
                    nxt.add(v)
                if len(seen) + len(nxt) >= max_nodes:
                    break
        seen |= nxt
        frontier = nxt
        if len(seen) >= max_nodes:
            break
    return seen


def entity_timeline(db: Session, eid: str, limit: int = 300) -> list[dict]:
    rows = (db.query(TimelineEvent).filter(TimelineEvent.entity_ids.contains([eid]))
            if False else [e for e in db.query(TimelineEvent).order_by(TimelineEvent.occurred_at).all() if eid in (e.entity_ids or [])])
    return [{"id": e.id, "kind": e.kind, "at": e.occurred_at.isoformat(), "summary": e.summary, "details": e.details,
             "lat": e.lat, "lon": e.lon, "entity_ids": e.entity_ids, "document_id": e.document_id} for e in rows[-limit:]]


def entity_dossier(db: Session, G: nx.Graph, D: nx.DiGraph, snapshot: dict, eid: str) -> dict | None:
    if eid not in G:
        return None
    nv = node_view(G, eid, snapshot)
    # relationships grouped by type
    rels: dict[str, list[dict]] = defaultdict(list)
    for u, v, d in list(D.out_edges(eid, data=True)) + list(D.in_edges(eid, data=True)):
        other = v if u == eid else u
        rels[d["rel_type"]].append({"direction": "out" if u == eid else "in", "other": node_view(G, other),
                                    "count": d["count"], "weight": d["weight"], "attrs": d.get("attrs", {}),
                                    "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"), "confidence": d.get("confidence", 1)})
    for k in rels:
        rels[k].sort(key=lambda r: -r["weight"])
    # projection neighbours with channel explanations
    assoc = []
    for e in snapshot.get("projection_edges", []):
        if eid in (e["source"], e["target"]):
            other = e["target"] if e["source"] == eid else e["source"]
            if other in G:
                assoc.append({"other": node_view(G, other, snapshot), **{k: v for k, v in e.items() if k not in ("source", "target")}})
    assoc.sort(key=lambda a: -a["weight"])
    evidence = [{"snippet": ev.snippet, "confidence": ev.confidence, "at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                 "extractor": ev.extractor, "document_id": ev.document_id, "document_title": ev.document.title,
                 **provenance.describe(ev.document)}
                for ev in db.query(Evidence).filter(Evidence.entity_id == eid).order_by(Evidence.occurred_at).limit(60).all()]
    alerts = [{"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "score": a.score, "status": a.status}
              for a in db.query(Alert).order_by(Alert.score.desc()).all() if eid in (a.entity_ids or [])]
    timeline = entity_timeline(db, eid)
    # activity histogram by week
    weeks = Counter()
    for t in timeline:
        dt = datetime.fromisoformat(t["at"])
        weeks[dt.strftime("%G-W%V")] += 1
    impact = snapshot.get("removal_impact", {}).get(eid)
    return {"entity": nv, "relationships": dict(rels), "associates": assoc[:40], "evidence": evidence, "alerts": alerts,
            "timeline": timeline[-120:], "activity": sorted(weeks.items()), "removal_impact": impact,
            "documents": [{"id": d.id, "title": d.title, "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None,
                           **provenance.describe(d)} for d in
                          db.query(Document).filter(Document.id.in_({e["document_id"] for e in evidence} | {t["document_id"] for t in timeline})).limit(50).all()]}


def money_flow(db: Session, G: nx.Graph, D: nx.DiGraph, eid: str) -> dict:
    if eid not in G:
        ent = db.get(Entity, eid)
        if ent:
            G.add_node(ent.id, label=ent.label, type=ent.type, aliases=ent.aliases or [], attrs=ent.attrs or {})
            D.add_node(ent.id, label=ent.label, type=ent.type, aliases=ent.aliases or [], attrs=ent.attrs or {})
    etype = G.nodes[eid].get("type") if eid in G else ""
    accounts = [eid] if etype == "BANK_ACCOUNT" else [v for _, v, d in D.out_edges(eid, data=True) if d.get("rel_type") == "OWNS_ACCOUNT"]
    inflow, outflow = defaultdict(float), defaultdict(float)
    tx = []
    for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "TRANSFER").order_by(TimelineEvent.occurred_at).all():
        ids = e.entity_ids or []
        if len(ids) != 2:
            continue
        if ids[1] in accounts:
            inflow[e.details.get("from_holder") or ids[0]] += e.details.get("amount", 0)
            tx.append({"at": e.occurred_at.isoformat(), "dir": "in", "counterparty": e.details.get("from_holder"), "amount": e.details.get("amount"), "mode": e.details.get("mode"), "remarks": e.details.get("remarks")})
        elif ids[0] in accounts:
            outflow[e.details.get("to_holder") or ids[1]] += e.details.get("amount", 0)
            tx.append({"at": e.occurred_at.isoformat(), "dir": "out", "counterparty": e.details.get("to_holder"), "amount": e.details.get("amount"), "mode": e.details.get("mode"), "remarks": e.details.get("remarks")})
    return {"accounts": [G.nodes[a].get("label", a) if a in G else a for a in accounts], "total_in": round(sum(inflow.values()), 2), "total_out": round(sum(outflow.values()), 2),
            "top_sources": sorted(inflow.items(), key=lambda kv: -kv[1])[:8], "top_destinations": sorted(outflow.items(), key=lambda kv: -kv[1])[:8],
            "transactions": tx[-200:]}


def call_profile(db: Session, G: nx.Graph, D: nx.DiGraph, eid: str) -> dict:
    phones = [eid] if G.nodes[eid]["type"] == "PHONE" else [v for _, v, d in D.out_edges(eid, data=True) if d["rel_type"] == "USES_PHONE"]
    contacts: Counter = Counter()
    night = total = 0
    hours = Counter()
    for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "CALL").all():
        ids = e.entity_ids or []
        if len(ids) != 2:
            continue
        for me, other in ((ids[0], ids[1]), (ids[1], ids[0])):
            if me in phones:
                owner = next((u for u, _, d in D.in_edges(other, data=True) if d["rel_type"] == "USES_PHONE"), None)
                contacts[(other, owner)] += 1
                total += 1
                night += 1 if e.details.get("night") else 0
                hours[e.occurred_at.hour] += 1
    return {"phones": [G.nodes[p]["label"] for p in phones], "total_calls": total, "night_ratio": round(night / total, 3) if total else 0,
            "top_contacts": [{"phone": G.nodes[p]["label"], "owner": G.nodes[o]["label"] if o else None, "owner_id": o, "calls": c}
                             for (p, o), c in contacts.most_common(12)],
            "by_hour": [hours.get(h, 0) for h in range(24)]}
