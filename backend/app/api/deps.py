"""Shared analysis service: caches the analytics snapshot, recomputes when data changes."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from ..db import AnalysisSnapshot, Entity
from ..graph import analytics
from ..graph.anomalies import AnomalyDetector, anomaly_hits, persist_alerts
from ..graph.store import graph_cache

log = logging.getLogger("cna.analysis")


class AnalysisService:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] | None = None
        self._version = -1
        self.last_run: dict[str, Any] = {}

    def snapshot(self, db: Session, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._snapshot is not None and self._version == graph_cache.version and not force:
                return self._snapshot
            row = db.query(AnalysisSnapshot).filter(AnalysisSnapshot.kind == "network").first()
            if row is not None and not row.stale and not force and self._snapshot is None:
                self._snapshot, self._version = row.payload, graph_cache.version
                return self._snapshot
            return self._recompute(db)

    def _recompute(self, db: Session) -> dict[str, Any]:
        t0 = time.time()
        G, D = graph_cache.get(db), graph_cache.get_directed(db)
        base = analytics.run_all(G, D)
        alerts = AnomalyDetector(db, G, D).run_all(base["metrics"]) if G.number_of_nodes() else []
        n_alerts = persist_alerts(db, alerts)
        snap = analytics.run_all(G, D, anomaly_hits(alerts))
        snap["computed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        snap["alert_count"] = n_alerts
        # persist risk scores on entities for sorting / search
        prio = snap.get("priority", {})
        if prio:
            for e in db.query(Entity).filter(Entity.id.in_(list(prio))).all():
                e.risk_score = float(prio.get(e.id, 0.0))
        
        # governance gate: track who has high-severity unreviewed alerts
        from ..db import Alert
        pending = set()
        for a in db.query(Alert).filter(Alert.review_status == "pending", Alert.severity.in_(["high", "critical"])).all():
            for eid in (a.entity_ids or []):
                pending.add(eid)
        snap["pending_reviews"] = list(pending)

        row = db.query(AnalysisSnapshot).filter(AnalysisSnapshot.kind == "network").first()
        if row is None:
            row = AnalysisSnapshot(kind="network", payload=snap, stale=False)
            db.add(row)
        else:
            row.payload, row.stale = snap, False
        db.commit()
        self._snapshot, self._version = snap, graph_cache.version
        self.last_run = {"seconds": round(time.time() - t0, 2), "alerts": n_alerts, "nodes": G.number_of_nodes()}
        log.info("analytics recomputed in %.2fs (%d alerts)", time.time() - t0, n_alerts)
        return snap

    def invalidate(self):
        with self._lock:
            self._snapshot = None


analysis_service = AnalysisService()
