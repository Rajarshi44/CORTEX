"""
The investigator agent's tool belt.

Every capability the console already has - graph traversal, dossiers, money flow, call
patterns, anomaly alerts, community detection, semantic document search, the public-record
connectors and the open web - is exposed here as one named tool with a JSON schema, so the
model can compose them instead of us hard-coding an intent router.

Three rules keep the answers honest:

  1. Tools return *retrieved facts*, never prose. The model may only phrase what a tool returned.
  2. Every fact carries its entity id, so the UI can link a claim back to the chart, and the
     agent can be checked. Ids are minted by the pipeline, never by the model.
  3. Rendering tools (`show_chart`, `show_network`, `show_table`, `show_timeline`) take data the
     model has already seen from a retrieval tool. `show_network` in particular takes entity ids
     and reads the real edges out of the graph - the model cannot draw a link that does not exist.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any

import networkx as nx
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import Alert, Document, Entity, Relationship, TimelineEvent
from ..graph import queries as Q
from .providers import ToolSpec

log = logging.getLogger("cna.agent.tools")

# --------------------------------------------------------------------------------------- context
class Ctx:
    """Everything a tool handler may touch, plus the sinks it may write to."""

    def __init__(self, db: Session, G: nx.Graph, D: nx.DiGraph, snapshot: dict):
        self.db, self.G, self.D, self.snap = db, G, D, snapshot
        self.visuals: list[dict] = []          # charts / networks / tables the answer should render
        self.highlights: list[str] = []        # entity ids to raise on the link chart
        self.citations: list[dict] = []        # documents and web pages the answer leaned on

    # -- entity resolution ------------------------------------------------------------
    def resolve(self, ref: str, types: tuple[str, ...] | None = None) -> str | None:
        """Accept an entity id, an exact label, an alias or a near-miss spelling."""
        if not ref:
            return None
        ref = str(ref).strip()
        if ref in self.G:
            return ref
        want = types or ("PERSON", "ORGANIZATION", "LOCATION", "PHONE", "BANK_ACCOUNT", "CRYPTO_WALLET",
                         "VEHICLE", "SOCIAL_HANDLE", "GOV_ID", "CASE", "REPORT")
        low = ref.lower()
        for n, d in self.G.nodes(data=True):
            if d["type"] in want and (d["label"].lower() == low or any(a.lower() == low for a in d.get("aliases", []))):
                return n
        # identifiers are matched on digits alone (formatting varies wildly across sources)
        digits = re.sub(r"\D", "", ref)
        if len(digits) >= 6:
            for n, d in self.G.nodes(data=True):
                if d["type"] in ("PHONE", "BANK_ACCOUNT", "GOV_ID", "VEHICLE") and re.sub(r"\D", "", d["label"]) == digits:
                    return n
        return Q.fuzzy_entity(self.G, ref, tuple(want), 78)

    def brief(self, n: str) -> dict:
        d = self.G.nodes[n]
        return {"id": n, "label": d["label"], "type": d["type"]}

    def rich(self, n: str) -> dict:
        d = self.G.nodes[n]
        susp = self.snap.get("suspicion", {}).get(n, {})
        return {"id": n, "label": d["label"], "type": d["type"], "aliases": d.get("aliases", [])[:4],
                "role": self.snap.get("roles", {}).get(n, {}).get("label"),
                "community": self.snap.get("community", {}).get(n),
                "priority": round(self.snap.get("priority", {}).get(n, 0.0), 3),
                "suspicion": round(susp.get("score", 0.0), 3), "degree": self.G.degree(n)}


Handler = Callable[[Ctx, dict], Any]
REGISTRY: dict[str, tuple[ToolSpec, Handler]] = {}


def tool(name: str, description: str, schema: dict):
    def deco(fn: Handler) -> Handler:
        REGISTRY[name] = (ToolSpec(name, description, schema), fn)
        return fn
    return deco


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


S_STR = {"type": "string"}
S_INT = {"type": "integer"}
S_NUM = {"type": "number"}
S_BOOL = {"type": "boolean"}
ENTITY_REF = {"type": "string", "description": "Entity id from a previous tool result, or the entity's name / number."}


def specs() -> list[ToolSpec]:
    return [spec for spec, _ in REGISTRY.values()]


def run(ctx: Ctx, name: str, args: dict) -> Any:
    entry = REGISTRY.get(name)
    if entry is None:
        return {"error": f"unknown tool '{name}'", "available": sorted(REGISTRY)}
    try:
        return entry[1](ctx, args or {})
    except Exception as exc:
        log.exception("tool %s failed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


# =======================================================================================
# Graph and database
# =======================================================================================
@tool("search_entities",
      "Find people, organisations, phones, accounts, vehicles, locations or cases by name, number or partial "
      "spelling. Always start here when the question names someone - it returns the entity ids every other tool needs.",
      obj({"query": {**S_STR, "description": "Name, alias, phone number, registration, account or fragment of one."},
           "types": {"type": "array", "items": S_STR,
                     "description": "Restrict to entity types: PERSON, ORGANIZATION, PHONE, BANK_ACCOUNT, CRYPTO_WALLET, VEHICLE, LOCATION, CASE, REPORT, SOCIAL_HANDLE, GOV_ID."},
           "limit": {**S_INT, "description": "Max results, default 8."}}, ["query"]))
def _search_entities(ctx: Ctx, a: dict):
    q = a.get("query") or ""
    if not q.strip():
        return {"query": "", "count": 0, "results": [], "error": "query is required - pass a name, number or fragment"}
    rows = Q.find_entities(ctx.db, q, a.get("types"), int(a.get("limit") or 8))
    out = [ctx.rich(e.id) for e in rows if e.id in ctx.G]
    return {"query": q, "count": len(out), "results": out,
            "note": "empty result means the name is not in this corpus - say so rather than guessing" if not out else ""}


@tool("entity_profile",
      "Full dossier on one entity: role, suspicion score and why, community, strongest associates with the "
      "channels that link them, relationships by type, linked alerts, and evidence snippets with their source document.",
      obj({"entity": ENTITY_REF,
           "max_associates": {**S_INT, "description": "Default 10."}}, ["entity"]))
def _entity_profile(ctx: Ctx, a: dict):
    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    d = Q.entity_dossier(ctx.db, ctx.G, ctx.D, ctx.snap, n)
    if not d:
        return {"error": "entity not in graph"}
    k = int(a.get("max_associates") or 10)
    ctx.highlights.append(n)
    e = d["entity"]
    for ev in d["evidence"][:6]:
        ctx.citations.append({"kind": "document", "id": ev["document_id"], "title": ev["document_title"],
                              "source_type": ev["source_type"], "snippet": ev["snippet"][:220]})
    return {
        "entity": {"id": e["id"], "label": e["label"], "type": e["type"], "aliases": e["aliases"],
                   "role": e["role"], "role_reasons": e["role_reasons"][:4], "community": e["community"],
                   "priority": round(e["priority"], 3), "influence": round(e["influence"], 3),
                   "suspicion": round(e["suspicion"], 3), "suspicion_reasons": e["suspicion_reasons"][:6],
                   "degree": e["degree"], "first_seen": e["first_seen"], "last_seen": e["last_seen"],
                   "attrs": {kk: vv for kk, vv in (e["attrs"] or {}).items() if kk not in ("lat", "lon")}},
        "associates": [{**ctx.brief(x["other"]["id"]), "weight": round(x["weight"], 2),
                        "channels": x.get("channels", {}), "calls": x.get("calls", 0),
                        "night_calls": x.get("night_calls", 0), "amount": x.get("amount", 0),
                        "meetings": x.get("meetings", 0), "shared_cases": x.get("cases", 0)}
                       for x in d["associates"][:k]],
        "relationships": {rt: [{**ctx.brief(r["other"]["id"]), "direction": r["direction"], "count": r["count"],
                                "verb": Q.REL_VERB.get(rt, rt.lower())} for r in v[:6]]
                          for rt, v in d["relationships"].items()},
        "alerts": [{"id": x["id"], "kind": x["kind"], "severity": x["severity"], "title": x["title"]} for x in d["alerts"][:6]],
        "evidence": [{"snippet": x["snippet"][:280], "document_id": x["document_id"], "document_title": x["document_title"],
                      "source_type": x["source_type"], "extractor": x["extractor"], "at": x["at"]} for x in d["evidence"][:6]],
        "documents": d["documents"][:10],
        "timeline_span": {"events": len(d["timeline"]),
                          "from": d["timeline"][0]["at"] if d["timeline"] else None,
                          "to": d["timeline"][-1]["at"] if d["timeline"] else None},
        "removal_impact": d["removal_impact"],
    }


@tool("find_path",
      "Find how two entities are connected: the shortest chains between them, hop by hop, with the relationship "
      "on every hop. Use for 'how are X and Y linked', 'is there a connection between'.",
      obj({"source": ENTITY_REF, "target": ENTITY_REF,
           "k": {**S_INT, "description": "How many alternative paths, default 3."}}, ["source", "target"]))
def _find_path(ctx: Ctx, a: dict):
    s, t = ctx.resolve(a["source"]), ctx.resolve(a["target"])
    if not s:
        return {"error": f"no entity matching '{a['source']}'"}
    if not t:
        return {"error": f"no entity matching '{a['target']}'"}
    paths = Q.shortest_paths(ctx.G, s, t, int(a.get("k") or 3))
    ctx.highlights.extend([s, t] + [n for p in paths for n in p])
    if not paths:
        return {"source": ctx.brief(s), "target": ctx.brief(t), "connected": False, "paths": [],
                "note": "no path exists in the current corpus"}
    return {"source": ctx.brief(s), "target": ctx.brief(t), "connected": True,
            "degrees_of_separation": len(paths[0]) - 1,
            "paths": [[{"from": h["from"]["label"], "verb": h["verb"], "to": h["to"]["label"],
                        "to_id": h["to"]["id"], "count": h["count"]} for h in Q.describe_path(ctx.G, ctx.D, p)]
                      for p in paths]}


@tool("neighbors",
      "List an entity's direct (or 2-hop) neighbours with the relationship type on each link. Cheaper than a full "
      "profile when you only need who or what sits next to someone.",
      obj({"entity": ENTITY_REF, "depth": {**S_INT, "description": "1 or 2, default 1."},
           "types": {"type": "array", "items": S_STR, "description": "Only return neighbours of these entity types."},
           "limit": {**S_INT, "description": "Default 25."}}, ["entity"]))
def _neighbors(ctx: Ctx, a: dict):
    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    want = set(a.get("types") or [])
    limit = int(a.get("limit") or 25)
    rows = []
    for u, v, d in list(ctx.D.out_edges(n, data=True)) + list(ctx.D.in_edges(n, data=True)):
        other = v if u == n else u
        if want and ctx.G.nodes[other]["type"] not in want:
            continue
        rows.append({**ctx.rich(other), "rel_type": d["rel_type"], "verb": Q.REL_VERB.get(d["rel_type"], d["rel_type"].lower()),
                     "direction": "out" if u == n else "in", "count": d["count"], "weight": round(d["weight"], 2)})
    rows.sort(key=lambda r: -r["weight"])
    if int(a.get("depth") or 1) > 1:
        two = Q.ego(ctx.G, n, 2, max_nodes=limit * 3) - {n} - {r["id"] for r in rows}
        rows += [{**ctx.rich(x), "rel_type": "TWO_HOP", "verb": "two hops away", "direction": "out", "count": 0, "weight": 0}
                 for x in list(two)[:limit] if not want or ctx.G.nodes[x]["type"] in want]
    ctx.highlights.append(n)
    ctx.highlights.extend([r["id"] for r in rows[:12]])
    return {"entity": ctx.brief(n), "count": len(rows), "neighbors": rows[:limit]}


@tool("money_flow",
      "Trace money for a person, organisation or bank account: total in, total out, biggest counterparties and the "
      "individual transactions with amount, mode and date.",
      obj({"entity": ENTITY_REF, "max_transactions": {**S_INT, "description": "Default 25."}}, ["entity"]))
def _money_flow(ctx: Ctx, a: dict):
    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    mf = Q.money_flow(ctx.db, ctx.G, ctx.D, n)
    ctx.highlights.append(n)
    k = int(a.get("max_transactions") or 25)
    if not mf["accounts"]:
        return {"entity": ctx.brief(n), "accounts": [], "note": "no bank account is linked to this entity in the corpus"}
    return {"entity": ctx.brief(n), "accounts": mf["accounts"], "total_in": mf["total_in"], "total_out": mf["total_out"],
            "net": round(mf["total_in"] - mf["total_out"], 2),
            "top_sources": [{"counterparty": s, "amount": v} for s, v in mf["top_sources"]],
            "top_destinations": [{"counterparty": s, "amount": v} for s, v in mf["top_destinations"]],
            "transaction_count": len(mf["transactions"]), "transactions": mf["transactions"][-k:],
            "currency": "INR"}


@tool("call_pattern",
      "Communication profile for a person or phone: which numbers they use, total calls, share placed at night, "
      "most frequent contacts (with the human behind each number) and the call volume by hour of day.",
      obj({"entity": ENTITY_REF}, ["entity"]))
def _call_pattern(ctx: Ctx, a: dict):
    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    cp = Q.call_profile(ctx.db, ctx.G, ctx.D, n)
    ctx.highlights.append(n)
    ctx.highlights.extend([c["owner_id"] for c in cp["top_contacts"] if c["owner_id"]])
    if not cp["phones"]:
        return {"entity": ctx.brief(n), "phones": [], "note": "no phone is linked to this entity in the corpus"}
    return {"entity": ctx.brief(n), **cp,
            "by_hour_note": "index 0-23 = calls placed in that hour, local time"}


@tool("entity_timeline",
      "Chronology of everything recorded against an entity - calls, transfers, sightings, FIRs, judgments, news - "
      "in date order.",
      obj({"entity": ENTITY_REF, "kinds": {"type": "array", "items": S_STR, "description": "Filter by event kind."},
           "limit": {**S_INT, "description": "Default 40, most recent."}}, ["entity"]))
def _entity_timeline(ctx: Ctx, a: dict):
    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    tl = Q.entity_timeline(ctx.db, n)
    kinds = set(a.get("kinds") or [])
    if kinds:
        tl = [t for t in tl if t["kind"] in kinds]
    limit = int(a.get("limit") or 40)
    ctx.highlights.append(n)
    return {"entity": ctx.brief(n), "total_events": len(tl), "kinds": sorted({t["kind"] for t in tl}),
            "events": [{"at": t["at"], "kind": t["kind"], "summary": t["summary"][:200],
                        "document_id": t["document_id"]} for t in tl[-limit:]]}


@tool("list_alerts",
      "Anomalies the detectors raised: burner phones, structured cash deposits, layering chains, call bursts, night "
      "activity, international contact, behavioural outliers. Each alert carries the entities it implicates.",
      obj({"kind": {**S_STR, "description": "burner_phone | structuring | layering | call_burst | night_activity | international_contact | behavioural_outlier"},
           "severity": {**S_STR, "description": "critical | high | medium | low"},
           "entity": {**S_STR, "description": "Only alerts touching this entity."},
           "limit": {**S_INT, "description": "Default 10."}}))
def _list_alerts(ctx: Ctx, a: dict):
    q = ctx.db.query(Alert).filter(Alert.status != "dismissed")
    if a.get("kind"):
        q = q.filter(Alert.kind == a["kind"])
    if a.get("severity"):
        q = q.filter(Alert.severity == a["severity"])
    rows = q.order_by(Alert.score.desc()).all()
    if a.get("entity"):
        eid = ctx.resolve(a["entity"])
        rows = [r for r in rows if eid and eid in (r.entity_ids or [])]
    rows = rows[:int(a.get("limit") or 10)]
    ctx.highlights.extend([e for r in rows for e in (r.entity_ids or [])][:30])
    return {"count": len(rows), "by_kind": dict(Counter(r.kind for r in rows)),
            "alerts": [{"id": r.id, "kind": r.kind, "severity": r.severity, "title": r.title,
                        "description": r.description[:400], "score": round(r.score, 3),
                        "entities": [ctx.brief(e) for e in (r.entity_ids or []) if e in ctx.G][:8],
                        "evidence": {k: v for k, v in (r.evidence or {}).items() if k != "raw"}} for r in rows]}


@tool("network_overview",
      "The whole picture at once: entity and relationship counts by type, graph density, how many communities and "
      "how many are flagged, the top key players and the current top alerts. Good first call for open questions.",
      obj({}))
def _network_overview(ctx: Ctx, a: dict):
    s = ctx.snap.get("summary", {})
    kp = ctx.snap.get("key_players", [])[:8]
    comms = ctx.snap.get("communities", [])
    alerts = ctx.db.query(Alert).filter(Alert.status != "dismissed").order_by(Alert.score.desc()).limit(6).all()
    docs = dict(Counter(d.source_type for d in ctx.db.query(Document).all()))
    return {"summary": {k: v for k, v in s.items() if k != "compute_backend"},
            "documents_by_source": docs, "document_count": sum(docs.values()),
            "communities": {"total": len(comms), "flagged": sum(1 for c in comms if c["suspicious"])},
            "key_players": [{"id": k["id"], "label": k["label"], "role": k["role"], "priority": round(k["priority"], 3),
                             "suspicion": round(k["suspicion"], 3), "reasons": k["reasons"][:3]} for k in kp],
            "top_alerts": [{"kind": r.kind, "severity": r.severity, "title": r.title} for r in alerts],
            "computed_at": ctx.snap.get("computed_at")}


@tool("key_players",
      "Actors ranked by priority - structural influence fused with evidentiary suspicion - each with the reasons "
      "behind the rank. Also returns brokers: the people whose removal would cut groups apart.",
      obj({"limit": {**S_INT, "description": "Default 8."}}))
def _key_players(ctx: Ctx, a: dict):
    k = int(a.get("limit") or 8)
    kp = ctx.snap.get("key_players", [])[:k]
    br = ctx.snap.get("brokers", [])[:6]
    ctx.highlights.extend([x["id"] for x in kp])
    return {"key_players": [{"rank": i + 1, "id": x["id"], "label": x["label"], "type": x["type"], "role": x["role"],
                             "community": x["community"], "priority": round(x["priority"], 3),
                             "influence": round(x["influence"], 3), "suspicion": round(x["suspicion"], 3),
                             "degree": x["degree"], "betweenness": round(x["betweenness"], 4),
                             "reasons": x["reasons"][:4]} for i, x in enumerate(kp)],
            "brokers": [{"id": b["id"], "label": b["label"], "betweenness": round(b["betweenness"], 4),
                         "communities_bridged": b["community_span"]} for b in br],
            "scoring_note": "priority = structural influence x evidentiary suspicion; it ranks investigative attention, it is not a finding of guilt"}


@tool("communities",
      "Communities detected in the actor graph (Louvain), with size, risk score, accused count, leading members and "
      "the areas they operate in. Says which are flagged as suspicious and why.",
      obj({"limit": {**S_INT, "description": "Default 8."}, "only_suspicious": S_BOOL}))
def _communities(ctx: Ctx, a: dict):
    comms = ctx.snap.get("communities", [])
    if a.get("only_suspicious"):
        comms = [c for c in comms if c["suspicious"]]
    comms = comms[:int(a.get("limit") or 8)]
    return {"total": len(ctx.snap.get("communities", [])), "returned": len(comms),
            "communities": [{"id": c["id"], "label": c["label"], "size": c["size"], "risk": round(c["risk"], 3),
                             "suspicious": c["suspicious"], "accused_count": c["accused_count"],
                             "density": round(c["density"], 3), "leader": c["leader"],
                             "top_members": [{"id": m["id"], "label": m["label"], "role": m["role"]} for m in c["top_members"][:6]],
                             "locations": c["locations"][:4]} for c in comms]}


@tool("predict_links",
      "Links the graph implies but has not observed: pairs ranked by Adamic-Adar weighted by suspicion, with the "
      "shared contacts that motivate each prediction. Use for 'what are we missing', 'who else should we look at'.",
      obj({"limit": {**S_INT, "description": "Default 8."}}))
def _predict_links(ctx: Ctx, a: dict):
    lp = ctx.snap.get("link_predictions", [])[:int(a.get("limit") or 8)]
    ctx.highlights.extend([x for p in lp for x in (p["source"], p["target"])])
    return {"predictions": [{"source": {"id": p["source"], "label": p["source_label"]},
                             "target": {"id": p["target"], "label": p["target_label"]},
                             "score": p["score"], "jaccard": p["jaccard"],
                             "shared_contacts": len(p["common_neighbors"]), "explanation": p["explanation"]} for p in lp],
            "caveat": "these are hypotheses generated from graph structure, not evidence of a relationship"}


@tool("disruption_impact",
      "What removing one actor would do to the network: share of interaction volume lost, how far their community "
      "fragments, and who ends up isolated. Use for 'what happens if we arrest X'.",
      obj({"entity": ENTITY_REF}, ["entity"]))
def _disruption_impact(ctx: Ctx, a: dict):
    from ..graph.analytics import actor_projection, removal_impact

    n = ctx.resolve(a["entity"])
    if not n:
        return {"error": f"no entity matching '{a['entity']}'"}
    P = actor_projection(ctx.D)
    if n not in P:
        return {"entity": ctx.brief(n), "error": "not an actor node (only people and organisations can be removed from the actor graph)"}
    imp = removal_impact(P, n, ctx.snap.get("community"))
    ctx.highlights.append(n)
    ctx.highlights.extend([i["id"] for i in imp.get("isolated_after", [])])
    return {"entity": ctx.brief(n), **imp}


@tool("aggregate",
      "Group-by counts and sums over the corpus - the tool to call before drawing a chart. "
      "datasets: entities (group_by type|role|community|suspicion_band|month), "
      "events (kind|month|day|hour|weekday, metric count|amount), "
      "relationships (rel_type, metric count|weight), alerts (kind|severity|status), documents (source_type|month).",
      obj({"dataset": {**S_STR, "description": "entities | events | relationships | alerts | documents"},
           "group_by": S_STR,
           "metric": {**S_STR, "description": "count (default) | amount | weight"},
           "filter_kind": {**S_STR, "description": "For events: only this kind (CALL, TRANSFER, FIR, ...)."},
           "filter_type": {**S_STR, "description": "For entities: only this entity type."},
           "limit": {**S_INT, "description": "Default 20 buckets."}}, ["dataset", "group_by"]))
def _aggregate(ctx: Ctx, a: dict):
    ds, gb = a["dataset"], a["group_by"]
    metric = (a.get("metric") or "count").lower()
    limit = int(a.get("limit") or 20)
    buckets: Counter = Counter()
    ordered = False

    # Counting happens in the database wherever the grouping is a plain column, and only the
    # columns actually needed come back otherwise. Pulling whole ORM objects across a hosted
    # Postgres link to count them in Python cost seconds per call.
    def sql_count(model, col):
        q = ctx.db.query(col, func.count()).group_by(col)
        return q.all()

    if ds == "entities":
        if gb == "type":
            q = ctx.db.query(Entity.type, func.count()).group_by(Entity.type)
            if a.get("filter_type"):
                q = q.filter(Entity.type == a["filter_type"])
            buckets.update(dict(q.all()))
        elif gb in ("role", "community", "suspicion_band"):
            q = ctx.db.query(Entity.id)
            if a.get("filter_type"):
                q = q.filter(Entity.type == a["filter_type"])
            for (eid,) in q.all():
                if gb == "role":
                    buckets[ctx.snap.get("roles", {}).get(eid, {}).get("label") or "unclassified"] += 1
                elif gb == "community":
                    c = ctx.snap.get("community", {}).get(eid)
                    buckets[f"community {c}" if c is not None else "unassigned"] += 1
                else:
                    s = ctx.snap.get("suspicion", {}).get(eid, {}).get("score", 0.0)
                    buckets["0.7+" if s >= 0.7 else "0.4-0.7" if s >= 0.4 else "0.2-0.4" if s >= 0.2 else "under 0.2"] += 1
        elif gb == "month":
            q = ctx.db.query(Entity.first_seen).filter(Entity.first_seen.isnot(None))
            if a.get("filter_type"):
                q = q.filter(Entity.type == a["filter_type"])
            for (ts,) in q.all():
                buckets[ts.strftime("%Y-%m")] += 1
            ordered = True
        else:
            return {"error": f"entities cannot be grouped by '{gb}'",
                    "allowed": ["type", "role", "community", "suspicion_band", "month"]}

    elif ds == "events":
        if gb not in ("kind", "month", "day", "hour", "weekday"):
            return {"error": f"events cannot be grouped by '{gb}'", "allowed": ["kind", "month", "day", "hour", "weekday"]}
        if gb == "kind" and metric != "amount":
            q = ctx.db.query(TimelineEvent.kind, func.count()).group_by(TimelineEvent.kind)
            if a.get("filter_kind"):
                q = q.filter(TimelineEvent.kind == a["filter_kind"])
            buckets.update(dict(q.all()))
        else:
            cols = (TimelineEvent.kind, TimelineEvent.occurred_at, TimelineEvent.details) if metric == "amount" \
                else (TimelineEvent.kind, TimelineEvent.occurred_at)
            q = ctx.db.query(*cols)
            if a.get("filter_kind"):
                q = q.filter(TimelineEvent.kind == a["filter_kind"])
            for row in q.all():
                kind, at = row[0], row[1]
                val = float((row[2] or {}).get("amount") or 0) if metric == "amount" else 1
                if gb == "kind":
                    buckets[kind] += val
                elif gb == "month":
                    buckets[at.strftime("%Y-%m")] += val
                    ordered = True
                elif gb == "day":
                    buckets[at.strftime("%Y-%m-%d")] += val
                    ordered = True
                elif gb == "hour":
                    buckets[f"{at.hour:02d}"] += val
                    ordered = True
                else:
                    buckets[at.strftime("%a")] += val

    elif ds == "relationships":
        if gb != "rel_type":
            return {"error": f"relationships cannot be grouped by '{gb}'", "allowed": ["rel_type"]}
        weighted = metric == "weight"
        agg = func.sum(Relationship.weight) if weighted else func.count()
        rows = ctx.db.query(Relationship.rel_type, agg).group_by(Relationship.rel_type).all()
        # a count stays an integer; only a weight sum is fractional
        buckets.update({k: (float(v or 0) if weighted else int(v or 0)) for k, v in rows})

    elif ds == "alerts":
        col = {"kind": Alert.kind, "severity": Alert.severity, "status": Alert.status}.get(gb)
        if col is None:
            return {"error": f"alerts cannot be grouped by '{gb}'", "allowed": ["kind", "severity", "status"]}
        buckets.update(dict(sql_count(Alert, col)))

    elif ds == "documents":
        if gb == "source_type":
            buckets.update(dict(sql_count(Document, Document.source_type)))
        elif gb == "month":
            for (ts,) in ctx.db.query(Document.occurred_at).filter(Document.occurred_at.isnot(None)).all():
                buckets[ts.strftime("%Y-%m")] += 1
            ordered = True
        else:
            return {"error": f"documents cannot be grouped by '{gb}'", "allowed": ["source_type", "month"]}
    else:
        return {"error": f"unknown dataset '{ds}'", "allowed": ["entities", "events", "relationships", "alerts", "documents"]}

    items = sorted(buckets.items()) if ordered else sorted(buckets.items(), key=lambda kv: -kv[1])
    items = items[:limit] if not ordered else items[-limit:]
    return {"dataset": ds, "group_by": gb, "metric": metric, "total": round(sum(buckets.values()), 2),
            "buckets": [{"key": k, "value": round(v, 2) if isinstance(v, float) else v} for k, v in items]}


@tool("search_documents",
      "Meaning-based search across every ingested document - FIRs, CDR batches, statements, judgments, intelligence "
      "notes, news. Returns matching passages with their document id so you can read the full text.",
      obj({"query": S_STR, "limit": {**S_INT, "description": "Default 6."},
           "source_type": {**S_STR, "description": "FIR | CDR | TRANSACTION | SURVEILLANCE | SOCIAL | INTEL | KYC | JUDGMENT | NEWS ..."}}, ["query"]))
def _search_documents(ctx: Ctx, a: dict):
    from .semantic import semantic_index

    limit = int(a.get("limit") or 6)
    if semantic_index.ready():
        res = semantic_index.search(ctx.db, a["query"], limit, a.get("source_type"))
    else:
        # First use downloads a model and embeds the corpus. Never make the analyst wait inside a
        # question for that: answer from keywords now, and build the index behind them.
        from ..db import SessionLocal

        semantic_index.warm(SessionLocal)
        res = {"status": "index_warming"}
    if res.get("status") != "ok":
        q = ctx.db.query(Document).filter(Document.content.ilike(f"%{a['query']}%") | Document.title.ilike(f"%{a['query']}%"))
        if a.get("source_type"):
            q = q.filter(Document.source_type == a["source_type"])
        rows = q.limit(limit).all()
        res = {"status": "keyword_fallback",
               "results": [{"document_id": d.id, "source_type": d.source_type, "title": d.title, "score": None,
                            "snippet": (d.content or d.title)[:320]} for d in rows]}
    for r in res.get("results", []):
        ctx.citations.append({"kind": "document", "id": r["document_id"], "title": r["title"],
                              "source_type": r["source_type"], "snippet": r["snippet"][:220]})
    return {"query": a["query"], "mode": res.get("status"), "count": len(res.get("results", [])),
            "results": [{"document_id": r["document_id"], "title": r["title"], "source_type": r["source_type"],
                         "score": r.get("score"), "snippet": r["snippet"][:400]} for r in res.get("results", [])]}


@tool("read_document",
      "Read the full text of one ingested document, plus which entities were extracted from it.",
      obj({"document_id": S_STR, "max_chars": {**S_INT, "description": "Default 4000."}}, ["document_id"]))
def _read_document(ctx: Ctx, a: dict):
    d = ctx.db.get(Document, a["document_id"])
    if not d:
        return {"error": "no such document"}
    from ..db import Evidence

    ents = {ev.entity_id for ev in ctx.db.query(Evidence).filter(Evidence.document_id == d.id).limit(80).all() if ev.entity_id}
    limit = int(a.get("max_chars") or 4000)
    ctx.citations.append({"kind": "document", "id": d.id, "title": d.title, "source_type": d.source_type,
                          "snippet": (d.content or "")[:220]})
    return {"document_id": d.id, "title": d.title, "source_type": d.source_type,
            "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None,
            "meta": {k: v for k, v in (d.meta or {}).items() if k not in ("raw", "html")},
            "content": (d.content or "")[:limit], "truncated": len(d.content or "") > limit,
            "entities": [ctx.brief(e) for e in ents if e in ctx.G][:30]}


@tool("case_linkage",
      "Cross-case linkage: which separate cases in the corpus share suspects, phones, accounts, vehicles or modus "
      "operandi, and how strong the overlap is. Use for 'are these cases related'.",
      obj({"threshold": {**S_NUM, "description": "Similarity cut-off 0-1, default 0.55."},
           "crime_head": {**S_STR, "description": "Restrict to cases under this offence head, e.g. 'narcotics'."},
           "limit": {**S_INT, "description": "Max case pairs, default 8."}}))
def _case_linkage(ctx: Ctx, a: dict):
    from ..graph.case_linkage import CaseLinkageEngine

    eng = CaseLinkageEngine(ctx.db)
    n = eng.load(limit=300, crime_head=a.get("crime_head"))
    if n < 2:
        return {"status": "insufficient_data", "cases_analysed": n,
                "reason": "case linkage needs at least two narrative case documents (FIR, judgment or news) in the corpus"}
    rep = eng.report(float(a.get("threshold") or 0.55))
    k = int(a.get("limit") or 8)
    return {"cases_analysed": rep["cases_analysed"], "candidate_links": rep["candidate_links"],
            "candidate_series": rep["candidate_series"], "threshold": rep["threshold"],
            "links": rep["links"][:k], "series": rep["series"][:4], "disclaimer": rep["disclaimer"]}


# =======================================================================================
# External intelligence
# =======================================================================================
@tool("screen_sanctions",
      "Screen a name (or the whole corpus) against OpenSanctions crime, sanctions, PEP and wanted-person lists. "
      "Returns matched list entries with the topics that flagged them.",
      obj({"name": {**S_STR, "description": "One name to screen. Omit to screen every actor in the corpus."},
           "dataset": {**S_STR, "description": "Watchlist to search: crime (default), sanctions, peps, in_mha_banned, in_nse_debarred."},
           "threshold": {**S_INT, "description": "Fuzzy match cut-off 0-100, default 88."}}))
def _screen_sanctions(ctx: Ctx, a: dict):
    from ..sources.opensanctions import OpenSanctionsConnector

    threshold = int(a.get("threshold") or 88)
    conn = OpenSanctionsConnector()
    try:
        if a.get("name"):
            from rapidfuzz import fuzz

            hits = []
            for rec in conn.stream_entities(a.get("dataset") or "crime", 4000):
                f = conn._fields(rec)
                for nm in [f["caption"], *f["aliases"]]:
                    if not nm or len(nm) < 5:
                        continue
                    score = fuzz.WRatio(a["name"], nm)
                    if score >= threshold:
                        hits.append({"matched": nm, "score": round(score, 1), "topics": f["topics"][:6],
                                     "lists": f["datasets"][:4], "country": f["country"],
                                     "birth_date": f["birth_date"], "opensanctions_id": f["id"]})
                        break
            if not hits:
                return {"status": "ok", "query": a["name"], "hits": [],
                        "note": "no watchlist entry matched - either the person is not listed, or the bulk dataset is not cached on this machine"}
            hits.sort(key=lambda h: -h["score"])
            return {"status": "ok", "query": a["name"], "hits": hits[:10],
                    "note": "a name match is not identification - confirm with date of birth or an identifier"}
        res = conn.screen(ctx.db, threshold)
        for h in (res.get("hits") or [])[:15]:
            if h.get("entity_id"):
                ctx.highlights.append(h["entity_id"])
        return {"status": res.get("status", "ok"), "screened": res.get("screened"),
                "hits": (res.get("hits") or [])[:15]}
    finally:
        conn.close()


@tool("corporate_registry",
      "Look up a company in the GLEIF global legal-entity registry: legal name, LEI, status, registered address, "
      "and its parent / subsidiary tree. Use to check who really owns a shell company.",
      obj({"name": {**S_STR, "description": "Company name to search."},
           "lei": {**S_STR, "description": "Known LEI, to fetch the ownership tree directly."},
           "country": {**S_STR, "description": "ISO country code, default IN."}}))
def _corporate_registry(ctx: Ctx, a: dict):
    from ..sources.gleif import GleifConnector

    conn = GleifConnector()
    try:
        if a.get("lei"):
            tree = {}
            for kind in ("direct-parent", "ultimate-parent", "direct-children"):
                tree[kind] = [conn._entity_fields(r) for r in conn.relations(a["lei"], kind)][:12]
            return {"lei": a["lei"], "ownership": tree,
                    "note": "empty branches mean GLEIF holds no reported relationship, not that none exists"}
        if not a.get("name"):
            return {"error": "pass either name or lei"}
        rows = [conn._entity_fields(r) for r in conn.search_entities(a["name"], a.get("country") or "IN", 10)]
        return {"query": a["name"], "count": len(rows), "results": rows[:10],
                "note": "GLEIF covers entities that have obtained an LEI; absence is not evidence a company is fake"}
    finally:
        conn.close()


@tool("offshore_leaks",
      "Search the ICIJ Offshore Leaks / Panama-Paradise-Pandora Papers dataset for a person or company and return "
      "the offshore structures they appear in. Only available when the dataset has been downloaded locally.",
      obj({"name": S_STR, "limit": {**S_INT, "description": "Default 10."}}, ["name"]))
def _offshore_leaks(ctx: Ctx, a: dict):
    from ..sources.icij import ICIJConnector

    conn = ICIJConnector()
    try:
        if not conn.ensure_data():
            return {"status": "unavailable",
                    "reason": "ICIJ bulk dataset is not present on this machine - harvest the icij source first"}
        import polars as pl

        frames = conn.frames()
        needle = a["name"].lower()
        out: list[dict] = []
        for key, lf in frames.items():
            try:
                cols = lf.collect_schema().names()
            except Exception:
                continue
            namecol = next((c for c in cols if c.lower() in ("name", "entity", "officer")), None)
            if not namecol:
                continue
            df = lf.filter(pl.col(namecol).str.to_lowercase().str.contains(needle, literal=True)).head(20).collect()
            for row in df.to_dicts():
                out.append({"table": key, **{k: v for k, v in row.items() if v is not None and k in
                                             (namecol, "jurisdiction", "jurisdiction_description", "countries",
                                              "incorporation_date", "status", "sourceID", "node_id")}})
        return {"status": "ok", "query": a["name"], "count": len(out), "results": out[:int(a.get("limit") or 10)],
                "caveat": "appearing in the leaks is not itself evidence of wrongdoing"}
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}
    finally:
        conn.close()


@tool("crime_news",
      "Recent Indian crime reporting from the wire feeds the system tracks. Use for current context on a case or "
      "a name that may be in the news.",
      obj({"feed": {**S_STR, "description": "Feed key, default toi_crime."},
           "match": {**S_STR, "description": "Only items mentioning this text."},
           "limit": {**S_INT, "description": "Default 8."}}))
def _crime_news(ctx: Ctx, a: dict):
    from ..sources.news import NewsConnector

    conn = NewsConnector()
    try:
        items = conn.items(a.get("feed") or "toi_crime")
        if a.get("match"):
            m = a["match"].lower()
            items = [i for i in items if m in (i.get("title", "") + i.get("summary", "")).lower()]
        items = items[:int(a.get("limit") or 8)]
        for i in items:
            ctx.citations.append({"kind": "web", "id": i.get("link", ""), "title": i.get("title", ""),
                                  "source_type": "NEWS", "snippet": (i.get("summary") or "")[:200]})
        return {"feed": a.get("feed") or "toi_crime", "count": len(items),
                "items": [{"title": i.get("title"), "summary": (i.get("summary") or "")[:300],
                           "link": i.get("link"), "published": i.get("published")} for i in items]}
    finally:
        conn.close()


@tool("web_search",
      "Search the open internet for context the corpus does not hold - background on a named person or company, "
      "recent reporting, regulatory action, court outcomes. Say in the answer that a fact came from the open web.",
      obj({"query": S_STR, "limit": {**S_INT, "description": "Default 5."},
           "fetch_content": {**S_BOOL, "description": "Also pull the page text of the top results. Slower; use when snippets are not enough."}},
          ["query"]))
def _web_search(ctx: Ctx, a: dict):
    from ..sources.web import WebConnector

    conn = WebConnector()
    try:
        res = conn.search(a["query"], int(a.get("limit") or 5), bool(a.get("fetch_content")))
        for r in res["results"]:
            ctx.citations.append({"kind": "web", "id": r["url"], "title": r["title"], "source_type": "WEB",
                                  "snippet": r["snippet"][:200]})
        return {"tier": res["tier"], "query": a["query"], "count": len(res["results"]),
                "results": res["results"], "reason": res.get("reason", ""),
                "caveat": "open-web results are unverified third-party content, not case evidence"}
    finally:
        conn.close()


@tool("read_url",
      "Read one web page as text. Use after web_search when a result looks worth reading in full.",
      obj({"url": S_STR, "max_chars": {**S_INT, "description": "Default 6000."}}, ["url"]))
def _read_url(ctx: Ctx, a: dict):
    from ..sources.web import WebConnector

    conn = WebConnector()
    try:
        page = conn.read_page(a["url"], int(a.get("max_chars") or 6000))
        if page.get("text"):
            ctx.citations.append({"kind": "web", "id": page["url"], "title": page.get("title") or page["url"],
                                  "source_type": "WEB", "snippet": page["text"][:200]})
        return page
    finally:
        conn.close()


# =======================================================================================
# Rendering - what the analyst sees beside the prose
# =======================================================================================
CHART_KINDS = ["bar", "column", "line", "area", "donut", "scatter", "stat", "hourly"]

@tool("show_chart",
      "Draw a chart beside your answer. Use it whenever a number has shape - a distribution, a ranking, a trend, a "
      "split, an hourly pattern. Kinds: bar (horizontal, for rankings and categories), column (vertical), line and "
      "area (for time), donut (for a split of a whole), scatter (two measures), hourly (24-hour clock, for call "
      "patterns), stat (up to four headline figures). Data must come from a tool result, never from memory.",
      obj({"kind": {**S_STR, "enum": CHART_KINDS},
           "title": S_STR,
           "caption": {**S_STR, "description": "One line saying what the reader should notice, and the source."},
           "unit": {**S_STR, "description": "inr | count | percent | none. Formats the axis."},
           "series_label": {**S_STR, "description": "Name of the measure, e.g. 'calls' or 'amount transferred'."},
           "points": {"type": "array", "description": "The data. For stat charts, value is the figure and label its caption.",
                      "items": obj({"label": S_STR, "value": S_NUM,
                                    "value2": {**S_NUM, "description": "Second measure, for scatter or a paired bar."},
                                    "entity_id": {**S_STR, "description": "Entity this point stands for, so the reader can click it."},
                                    "note": S_STR}, ["label", "value"])}},
          ["kind", "title", "points"]))
def _show_chart(ctx: Ctx, a: dict):
    pts = [p for p in (a.get("points") or []) if isinstance(p, dict) and p.get("label") is not None][:40]
    if not pts:
        return {"error": "no points given"}
    for p in pts:
        try:
            p["value"] = float(p.get("value") or 0)
        except (TypeError, ValueError):
            p["value"] = 0.0
    kind = a["kind"] if a.get("kind") in CHART_KINDS else "bar"
    ctx.visuals.append({"type": "chart", "kind": kind, "title": a["title"], "caption": a.get("caption", ""),
                        "unit": (a.get("unit") or "count").lower(), "series_label": a.get("series_label", ""),
                        "points": pts})
    return {"rendered": "chart", "kind": kind, "points": len(pts)}


@tool("show_network",
      "Draw a small link chart of specific entities. Pass the entity ids you want shown; the real relationships "
      "between them are read from the graph, so this cannot draw a connection that does not exist. Use it for paths, "
      "an ego network, a community, or the actors behind an alert.",
      obj({"title": S_STR, "caption": S_STR,
           "entity_ids": {"type": "array", "items": S_STR, "description": "Entity ids from earlier tool results."},
           "include_neighbors": {**S_BOOL, "description": "Also pull in each entity's direct neighbours. Default false."},
           "emphasis": {"type": "array", "items": S_STR, "description": "Ids to draw in red."}},
          ["title", "entity_ids"]))
def _show_network(ctx: Ctx, a: dict):
    ids = [i for i in (a.get("entity_ids") or []) if i in ctx.G]
    unresolved = [i for i in (a.get("entity_ids") or []) if i not in ctx.G]
    for u in unresolved:
        r = ctx.resolve(u)
        if r:
            ids.append(r)
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"error": "none of those entity ids are in the graph - call search_entities first"}
    nodes = set(ids)
    if a.get("include_neighbors"):
        for i in ids[:12]:
            nodes |= Q.ego(ctx.G, i, 1, max_nodes=14)
    nodes = set(list(nodes)[:70])
    payload_nodes = [{**ctx.rich(n), "aliases": ctx.G.nodes[n].get("aliases", [])[:2]} for n in nodes]
    edges = [{"id": d["id"], "source": u, "target": v, "rel_type": d["rel_type"],
              "verb": Q.REL_VERB.get(d["rel_type"], d["rel_type"].lower().replace("_", " ")),
              "count": d["count"], "weight": round(d["weight"], 2), "confidence": d.get("confidence", 1.0)}
             for u, v, d in ctx.D.edges(data=True) if u in nodes and v in nodes][:400]
    ctx.highlights.extend(ids)
    ctx.visuals.append({"type": "network", "title": a["title"], "caption": a.get("caption", ""),
                        "nodes": payload_nodes, "edges": edges,
                        "emphasis": [e for e in (a.get("emphasis") or ids) if e in nodes]})
    return {"rendered": "network", "nodes": len(payload_nodes), "edges": len(edges)}


@tool("show_table",
      "Render a table beside your answer, for comparisons and lists that read better in columns than in prose.",
      obj({"title": S_STR, "caption": S_STR,
           "columns": {"type": "array", "items": S_STR},
           "rows": {"type": "array", "description": "Each row is an array of cell values, same order as columns.",
                    "items": {"type": "array", "items": S_STR}},
           "entity_ids": {"type": "array", "items": S_STR,
                          "description": "Optional, one entity id per row, to make rows clickable."}},
          ["title", "columns", "rows"]))
def _show_table(ctx: Ctx, a: dict):
    cols = [str(c) for c in (a.get("columns") or [])][:8]
    rows = [[str(c) for c in r][:8] for r in (a.get("rows") or []) if isinstance(r, list)][:40]
    if not cols or not rows:
        return {"error": "need columns and rows"}
    ctx.visuals.append({"type": "table", "title": a["title"], "caption": a.get("caption", ""),
                        "columns": cols, "rows": rows, "entity_ids": (a.get("entity_ids") or [])[:40]})
    return {"rendered": "table", "rows": len(rows)}


@tool("show_timeline",
      "Draw a dated timeline of events beside your answer. Use for chronologies, escalation, or the sequence of a "
      "money trail. Events must come from a tool result.",
      obj({"title": S_STR, "caption": S_STR,
           "events": {"type": "array", "items": obj({"at": {**S_STR, "description": "ISO date or datetime."},
                                                     "label": S_STR,
                                                     "kind": {**S_STR, "description": "CALL, TRANSFER, FIR, SIGHTING, NEWS ..."},
                                                     "entity_id": S_STR,
                                                     "emphasis": S_BOOL}, ["at", "label"])}},
          ["title", "events"]))
def _show_timeline(ctx: Ctx, a: dict):
    evs = []
    for e in (a.get("events") or [])[:60]:
        if not isinstance(e, dict) or not e.get("at"):
            continue
        try:
            datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        evs.append({"at": e["at"], "label": str(e.get("label", ""))[:160], "kind": e.get("kind", "EVENT"),
                    "entity_id": e.get("entity_id"), "emphasis": bool(e.get("emphasis"))})
    if not evs:
        return {"error": "no events with a parseable ISO date"}
    evs.sort(key=lambda x: x["at"])
    ctx.visuals.append({"type": "timeline", "title": a["title"], "caption": a.get("caption", ""), "events": evs})
    return {"rendered": "timeline", "events": len(evs)}


@tool("highlight_on_chart",
      "Raise these entities on the main link chart, so the analyst can click through from your answer to the sheet.",
      obj({"entity_ids": {"type": "array", "items": S_STR}, "note": S_STR}, ["entity_ids"]))
def _highlight(ctx: Ctx, a: dict):
    ids = [i for i in (a.get("entity_ids") or []) if i in ctx.G]
    ctx.highlights.extend(ids)
    return {"highlighted": len(ids)}


def tool_catalogue() -> list[dict]:
    return [{"name": s.name, "description": s.description.split(".")[0] + "."} for s in specs()]
