"""
Suspicious pattern detection over the graph + timeline.

Detectors are loaded dynamically from the `detectors` module.
"""
from __future__ import annotations

import logging
import networkx as nx
from sqlalchemy.orm import Session
from .detectors.registry import REGISTRY
from .detectors import builtin  # Ensure builtins are registered
from ..db import TimelineEvent

log = logging.getLogger("cna.anomalies")

class AnomalyDetector:
    def __init__(self, db: Session, G: nx.Graph, D: nx.DiGraph):
        self.db = db
        self.G = G
        self.D = D
        self.calls = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "CALL").all()]
        self.transfers = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "TRANSFER").all()]
        self.complaints = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "COMPLAINT").all()]

    def run_all(self, projection_metrics: dict | None = None) -> list[dict]:
        alerts: list[dict] = []
        snapshot = {
            "calls": self.calls,
            "transfers": self.transfers,
            "complaints": self.complaints,
            "projection_metrics": projection_metrics
        }
        
        for name, detector in REGISTRY.items():
            try:
                flags = detector.run(self.G, self.D, snapshot)
                alerts.extend(flags)
            except Exception as exc:
                log.error(f"Detector {name} failed: {exc}")
                
        alerts.sort(key=lambda a: -a.get("score", 0.0))
        return alerts

DETECTORS: list[dict] = [
    {"name": k, "method": k, "feed": "MIXED", "kinds": [k], "needs": "various", "looks_for": "various"}
    for k in REGISTRY.keys()
]
