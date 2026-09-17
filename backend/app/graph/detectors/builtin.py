import uuid
import networkx as nx
from typing import Any, Dict, List
from collections import Counter, defaultdict
from datetime import timedelta
import numpy as np
from sqlalchemy.orm import Session
from .base import Detector
from .registry import register
from ...db import TimelineEvent

# Helpers
def _owners(D: nx.DiGraph) -> dict[str, list[str]]:
    o: dict[str, list[str]] = defaultdict(list)
    for u, v, d in D.edges(data=True):
        if d["rel_type"] in ("USES_PHONE", "OWNS_ACCOUNT") and D.nodes[u]["type"] in ("PERSON", "ORGANIZATION"):
            o[v].append(u)
    return o

def _label(G: nx.Graph, n: str) -> str:
    return G.nodes[n]["label"] if n in G else n

def _owner_label(G: nx.Graph, D: nx.DiGraph, proxy: str) -> str:
    os_ = _owners(D).get(proxy, [])
    return _label(G, os_[0]) if os_ else "unknown"

def _alert(kind: str, title: str, description: str, score: float, entity_ids: list[str], evidence: dict) -> dict:
    sev = "critical" if score >= 0.85 else "high" if score >= 0.65 else "medium" if score >= 0.4 else "low"
    return {"id": str(uuid.uuid4()), "kind": kind, "severity": sev, "title": title, "description": description,
            "score": round(float(score), 3), "entity_ids": list(dict.fromkeys(entity_ids)), "evidence": evidence,
            "reasons": []}


@register
class NightActivityDetector(Detector):
    name = "night_activity"
    severity_weight = 0.5

    def run(self, graph: nx.Graph, directed_graph: nx.DiGraph, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        calls = snapshot.get("calls", [])
        owner = _owners(directed_graph)
        per: dict[str, list[bool]] = defaultdict(list)
        for e in calls:
            for pid in e.entity_ids:
                per[pid].append(bool(e.details.get("night")))
        for pid, flags in per.items():
            node = graph.nodes.get(pid)
            if not node or node["type"] != "PHONE" or len(flags) < 15:
                continue
            ratio = sum(flags) / len(flags)
            if ratio >= 0.4:
                out.append(_alert(
                    "night_activity", f"Night-time communication pattern: {node['label']} ({_owner_label(graph, directed_graph, pid)})",
                    f"{ratio:.0%} of {len(flags)} calls occur between 23:00 and 05:00 (population baseline ≈ 8%).",
                    min(1.0, 0.3 + ratio), [pid] + owner.get(pid, []), {"night_ratio": round(ratio, 3), "calls": len(flags)}))
        return out

@register
class InternationalContactDetector(Detector):
    name = "international_contact"
    severity_weight = 0.6

    def run(self, graph: nx.Graph, directed_graph: nx.DiGraph, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        calls = snapshot.get("calls", [])
        owner = _owners(directed_graph)
        per: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in calls:
            ids = e.entity_ids
            if len(ids) != 2:
                continue
            for a, b in ((ids[0], ids[1]), (ids[1], ids[0])):
                if graph.nodes.get(a, {}).get("attrs", {}).get("international"):
                    per[b].append(e)
        for pid, evs in per.items():
            node = graph.nodes.get(pid)
            if not node:
                continue
            foreign = Counter(x for e in evs for x in e.entity_ids if x != pid)
            night = sum(1 for e in evs if e.details.get("night"))
            out.append(_alert(
                "international_contact", f"International contact: {node['label']} ({_owner_label(graph, directed_graph, pid)})",
                f"{len(evs)} call(s) with foreign number(s) {', '.join(_label(graph, f) for f in foreign)}; {night} at night.",
                min(1.0, 0.5 + 0.05 * len(evs) + (0.15 if night / max(len(evs), 1) > 0.5 else 0)),
                [pid] + list(foreign) + owner.get(pid, []),
                {"calls": len(evs), "foreign_numbers": [_label(graph, f) for f in foreign], "night_calls": night}))
        return out
