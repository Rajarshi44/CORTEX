"""
Graph persistence + in-memory NetworkX view.

RelationshipAccumulator batches edge observations during ingestion and upserts them
(merging counts / weights / temporal bounds) in one pass. GraphCache builds the NetworkX
graph from SQLite lazily and invalidates on ingestion.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import networkx as nx
from sqlalchemy.orm import Session

from ..db import Entity, Evidence, Relationship, TimelineEvent

# Relationship types that are semantically symmetric (stored once, canonical ordering).
SYMMETRIC = {"MET", "MENTIONED_WITH", "COMMUNICATED_WITH", "ASSOCIATE_OF", "CO_ACCUSED", "CO_LOCATED", "SHARED_HANDSET"}


@dataclass
class EdgeObs:
    source_id: str
    target_id: str
    rel_type: str
    weight: float = 1.0
    count: int = 1
    first: datetime | None = None
    last: datetime | None = None
    confidence: float = 1.0
    attrs: dict[str, Any] = field(default_factory=dict)
    evidence: list[tuple[str, str, float, datetime | None, str]] = field(default_factory=list)  # (doc_id, snippet, conf, at, extractor)


class RelationshipAccumulator:
    def __init__(self):
        self.edges: dict[tuple[str, str, str], EdgeObs] = {}

    def add(self, source_id: str, target_id: str, rel_type: str, *, weight: float = 1.0, at: datetime | None = None,
            confidence: float = 1.0, attrs: dict | None = None, doc_id: str | None = None, snippet: str = "",
            extractor: str = "structured", amount: float | None = None):
        if source_id == target_id:
            return
        if rel_type in SYMMETRIC and source_id > target_id:
            source_id, target_id = target_id, source_id
        k = (source_id, target_id, rel_type)
        e = self.edges.get(k)
        if e is None:
            e = EdgeObs(source_id, target_id, rel_type, weight=0.0, count=0, confidence=confidence)
            self.edges[k] = e
        e.weight += weight
        e.count += 1
        e.confidence = max(e.confidence, confidence)
        if at:
            e.first = at if e.first is None or at < e.first else e.first
            e.last = at if e.last is None or at > e.last else e.last
        if amount is not None:
            e.attrs["total_amount"] = round(e.attrs.get("total_amount", 0.0) + amount, 2)
            e.attrs["max_amount"] = max(e.attrs.get("max_amount", 0.0), amount)
        for k2, v in (attrs or {}).items():
            if k2 == "duration_sec":
                e.attrs["total_duration_sec"] = e.attrs.get("total_duration_sec", 0) + int(v)
            elif k2 == "night":
                e.attrs["night_calls"] = e.attrs.get("night_calls", 0) + (1 if v else 0)
            elif k2 not in e.attrs:
                e.attrs[k2] = v
        if doc_id and len(e.evidence) < 12:  # cap evidence per edge to keep DB small; counts still aggregate
            e.evidence.append((doc_id, snippet[:500], confidence, at, extractor))

    def flush(self, db: Session) -> tuple[int, int]:
        """Upsert accumulated edges, then the evidence that cites them. Returns (created, updated).

        The two passes are not cosmetic. `Evidence.relationship_id` is a bare column FK with no ORM
        `relationship()` behind it, so the unit of work has no dependency edge to sort on and orders
        the tables by name - inserting `evidence` before `relationships`. With SQLite's
        `PRAGMA foreign_keys=ON` (see db.py) that is a FOREIGN KEY constraint failure on every edge
        that carries a citation. Flushing the edges first makes the row exist before anything
        points at it.
        """
        created = updated = 0
        pending: list[tuple[Relationship, list[tuple[str, str, float, datetime | None, str]]]] = []
        existing: dict[tuple[str, str, str], Relationship] = {}
        if self.edges:
            src_ids = {k[0] for k in self.edges}
            for r in db.query(Relationship).filter(Relationship.source_id.in_(src_ids)).all():
                existing[(r.source_id, r.target_id, r.rel_type)] = r
        for k, obs in self.edges.items():
            r = existing.get(k)
            if r is None:
                r = Relationship(id=str(uuid.uuid4()), source_id=obs.source_id, target_id=obs.target_id, rel_type=obs.rel_type,
                                 weight=obs.weight, count=obs.count, attributes=dict(obs.attrs), first_seen=obs.first,
                                 last_seen=obs.last, confidence=obs.confidence)
                db.add(r)
                created += 1
            else:
                r.weight = (r.weight or 0) + obs.weight
                r.count = (r.count or 0) + obs.count
                r.confidence = max(r.confidence or 0, obs.confidence)
                merged = dict(r.attributes or {})
                for ak, av in obs.attrs.items():
                    if isinstance(av, (int, float)) and ak.startswith(("total_", "night_")):
                        merged[ak] = merged.get(ak, 0) + av
                    elif ak == "max_amount":
                        merged[ak] = max(merged.get(ak, 0), av)
                    else:
                        merged.setdefault(ak, av)
                r.attributes = merged
                if obs.first and (r.first_seen is None or obs.first < r.first_seen):
                    r.first_seen = obs.first
                if obs.last and (r.last_seen is None or obs.last > r.last_seen):
                    r.last_seen = obs.last
                db.add(r)
                updated += 1
            if obs.evidence:
                pending.append((r, obs.evidence))
        if pending:
            db.flush()
            for r, evidence in pending:
                for doc_id, snippet, conf, at, extractor in evidence:
                    db.add(Evidence(document_id=doc_id, relationship_id=r.id, snippet=snippet, confidence=conf,
                                    occurred_at=at, extractor=extractor))
        self.edges.clear()
        return created, updated


def add_entity_evidence(db: Session, doc_id: str, entity_id: str, snippet: str, confidence: float = 1.0,
                        at: datetime | None = None, extractor: str = "rules"):
    db.add(Evidence(document_id=doc_id, entity_id=entity_id, snippet=snippet[:500], confidence=confidence,
                    occurred_at=at, extractor=extractor))


def add_event(db: Session, doc_id: str, kind: str, at: datetime, entity_ids: list[str], summary: str,
              details: dict | None = None, lat: float | None = None, lon: float | None = None):
    db.add(TimelineEvent(document_id=doc_id, kind=kind, occurred_at=at, entity_ids=entity_ids, summary=summary[:500],
                         details=details or {}, lat=lat, lon=lon))


# --------------------------------------------------------------------------------------
# NetworkX cache
# --------------------------------------------------------------------------------------
class GraphCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._graph: nx.Graph | None = None
        self._digraph: nx.DiGraph | None = None
        self.version = 0

    def invalidate(self):
        with self._lock:
            self._graph = None
            self._digraph = None
            self.version += 1

    def get(self, db: Session) -> nx.Graph:
        with self._lock:
            if self._graph is None:
                self._graph, self._digraph = self._build(db)
            return self._graph

    def get_directed(self, db: Session) -> nx.DiGraph:
        with self._lock:
            if self._digraph is None:
                self._graph, self._digraph = self._build(db)
            return self._digraph

    @staticmethod
    def _build(db: Session) -> tuple[nx.Graph, nx.DiGraph]:
        G = nx.Graph()
        D = nx.DiGraph()
        for e in db.query(Entity).all():
            data = dict(id=e.id, type=e.type, label=e.label, aliases=e.aliases or [], attrs=e.attributes or {},
                        mentions=e.mention_count or 0, risk=e.risk_score or 0.0,
                        first_seen=e.first_seen.isoformat() if e.first_seen else None,
                        last_seen=e.last_seen.isoformat() if e.last_seen else None)
            G.add_node(e.id, **data)
            D.add_node(e.id, **data)
        for r in db.query(Relationship).all():
            if r.source_id not in G or r.target_id not in G:
                continue
            edata = dict(id=r.id, rel_type=r.rel_type, weight=float(r.weight or 1.0), count=int(r.count or 1),
                         attrs=r.attributes or {}, confidence=float(r.confidence or 1.0),
                         first_seen=r.first_seen.isoformat() if r.first_seen else None,
                         last_seen=r.last_seen.isoformat() if r.last_seen else None)
            D.add_edge(r.source_id, r.target_id, **edata)
            if G.has_edge(r.source_id, r.target_id):
                ex = G[r.source_id][r.target_id]
                ex["weight"] += edata["weight"]
                ex["count"] += edata["count"]
                ex.setdefault("rel_types", []).append(r.rel_type)
                ex.setdefault("ids", []).append(r.id)
            else:
                G.add_edge(r.source_id, r.target_id, **edata, rel_types=[r.rel_type], ids=[r.id])
        return G, D


graph_cache = GraphCache()
