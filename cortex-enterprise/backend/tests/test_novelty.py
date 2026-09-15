"""
Tests for the three novel intelligence engines.

Run with:
    cd cortex-enterprise/backend
    python -m pytest tests/test_novelty.py -v
"""
from __future__ import annotations

import math
import time

import networkx as nx
import pytest

from app.graph.novelty import (
    FirstTimeOffenderEngine,
    GhostNodeEngine,
    IcebergEstimator,
    run_novelty,
)


# ═══════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════

def _make_criminal_graph():
    """
    Synthetic directed graph with:
    - 5 known criminals (P1-P5, high suspicion)
    - 2 "clean" individuals (P6, P7) embedded in the network
    - Phones, FIR edges, CDR edges for multi-source testing
    - A structural hole between P1 and P3 (ghost node candidate)
    """
    D = nx.DiGraph()

    # Persons
    for pid, label, attrs in [
        ("P1", "Rajan Mehta",     {"sources": ["FIR", "CDR"]}),
        ("P2", "Suresh Desai",    {"sources": ["FIR", "CDR", "TRANSFER"]}),
        ("P3", "Farouk Ansari",   {"sources": ["FIR"]}),
        ("P4", "Meena Pillai",    {"sources": ["CDR", "TRANSFER"]}),
        ("P5", "Govind Rao",      {"sources": ["FIR"]}),
        ("P6", "Anil Kumar",      {"sources": ["CDR"]}),   # "clean" — high proximity risk
        ("P7", "Sheela Nair",     {"sources": ["CDR"]}),   # "clean" — high proximity risk
    ]:
        D.add_node(pid, type="PERSON", label=label, attrs=attrs, aliases=[])

    # Phones (proxy nodes)
    for ph, owner in [("PH1", "P1"), ("PH2", "P2"), ("PH3", "P3"), ("PH6", "P6"), ("PH7", "P7")]:
        D.add_node(ph, type="PHONE", label=ph, attrs={"kyc_status": "unverified"}, aliases=[])
        D.add_edge(owner, ph, rel_type="USES_PHONE", count=1, attrs={})

    # FIR edges (P1, P2, P3, P5 are accused)
    c1 = "C1"
    D.add_node(c1, type="CASE", label="Case 1", attrs={"criminal": True}, aliases=[])
    for p in ["P1", "P2", "P3", "P5"]:
        D.add_edge(p, c1, rel_type="ACCUSED_IN", count=1, attrs={})

    # CDR edges: P1↔P2, P2↔P3, P4↔P2, P6↔P1, P6↔P2, P7↔P2, P7↔P4
    # (P6 and P7 are "clean" but talk to known criminals)
    for caller, callee, cnt in [
        ("PH1", "PH2", 25), ("PH2", "PH3", 18), ("PH6", "PH1", 12),
        ("PH6", "PH2", 9),  ("PH7", "PH2", 15), ("PH7", "PH3", 6),
    ]:
        D.add_edge(caller, callee, rel_type="CALLED", count=cnt, attrs={"night_calls": cnt // 3})
        D.add_edge(callee, caller, rel_type="CALLED", count=cnt // 2, attrs={"night_calls": 0})

    # Financial transfers
    acc1 = "ACC1"
    D.add_node(acc1, type="ACCOUNT", label="Acc1", attrs={}, aliases=[])
    D.add_edge("P2", acc1, rel_type="OWNS_ACCOUNT", count=1, attrs={})
    acc4 = "ACC4"
    D.add_node(acc4, type="ACCOUNT", label="Acc4", attrs={}, aliases=[])
    D.add_edge("P4", acc4, rel_type="OWNS_ACCOUNT", count=1, attrs={})
    D.add_edge(acc1, acc4, rel_type="TRANSFERRED_TO", count=8, attrs={"total_amount": 850000})

    return D


def _make_actor_projection():
    """Undirected actor projection for ghost node and FTO tests."""
    P = nx.Graph()
    # Persons
    persons = {
        "P1": "Rajan Mehta", "P2": "Suresh Desai", "P3": "Farouk Ansari",
        "P4": "Meena Pillai", "P5": "Govind Rao", "P6": "Anil Kumar", "P7": "Sheela Nair",
    }
    for pid, label in persons.items():
        P.add_node(pid, type="PERSON", label=label, attrs={}, aliases=[])

    # Edges: P1-P2, P2-P3, P2-P4, P6-P1, P6-P2, P7-P2, P7-P3, P3-P5
    # Note: NO direct edge P1↔P3 (ghost node scenario)
    edges = [
        ("P1", "P2", {"weight": 3.0, "channels": {"calls": 25}, "calls": 25}),
        ("P2", "P3", {"weight": 2.5, "channels": {"calls": 18}, "calls": 18}),
        ("P2", "P4", {"weight": 2.0, "channels": {"transfers": 8}, "amount": 850000}),
        ("P3", "P5", {"weight": 1.5, "channels": {"cases": 1}, "cases": 1}),
        ("P6", "P1", {"weight": 1.0, "channels": {"calls": 12}, "calls": 12}),
        ("P6", "P2", {"weight": 0.8, "channels": {"calls": 9},  "calls": 9}),
        ("P7", "P2", {"weight": 1.2, "channels": {"calls": 15}, "calls": 15}),
        ("P7", "P3", {"weight": 0.6, "channels": {"calls": 6},  "calls": 6}),
    ]
    for u, v, data in edges:
        P.add_edge(u, v, **data)
    return P


def _make_suspicion():
    return {
        "P1": {"score": 0.75, "accused": 1, "surveillance": 0, "intel": 0, "unverified": 1, "international": 0, "anomaly": 0.0, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": ["named accused in 1 FIR"]},
        "P2": {"score": 0.85, "accused": 1, "surveillance": 1, "intel": 1, "unverified": 1, "international": 2, "anomaly": 0.6, "watchlist": "wanted", "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": ["named accused", "on wanted watchlist"]},
        "P3": {"score": 0.60, "accused": 1, "surveillance": 0, "intel": 0, "unverified": 0, "international": 0, "anomaly": 0.0, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": ["named accused"]},
        "P4": {"score": 0.45, "accused": 0, "surveillance": 0, "intel": 1, "unverified": 0, "international": 0, "anomaly": 0.4, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": []},
        "P5": {"score": 0.55, "accused": 1, "surveillance": 0, "intel": 0, "unverified": 0, "international": 0, "anomaly": 0.0, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": ["named accused"]},
        "P6": {"score": 0.05, "accused": 0, "surveillance": 0, "intel": 0, "unverified": 0, "international": 0, "anomaly": 0.0, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": []},
        "P7": {"score": 0.08, "accused": 0, "surveillance": 0, "intel": 0, "unverified": 0, "international": 0, "anomaly": 0.0, "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0, "press": 0, "complainant": 0, "org_flag": None, "reasons": []},
    }


# ═══════════════════════════════════════════════════════
# Test: IcebergEstimator
# ═══════════════════════════════════════════════════════

class TestIcebergEstimator:
    def test_estimate_returns_valid_structure(self):
        D = _make_criminal_graph()
        result = IcebergEstimator().estimate(D)
        assert "observed" in result
        assert "estimated_total" in result
        assert "dark_number" in result
        assert "visibility_pct" in result
        assert "interpretation" in result

    def test_estimated_total_gte_observed(self):
        D = _make_criminal_graph()
        result = IcebergEstimator().estimate(D)
        assert result["estimated_total"] >= result["observed"]

    def test_dark_number_nonnegative(self):
        D = _make_criminal_graph()
        result = IcebergEstimator().estimate(D)
        assert result["dark_number"] >= 0

    def test_visibility_pct_in_range(self):
        D = _make_criminal_graph()
        result = IcebergEstimator().estimate(D)
        assert 0.0 <= result["visibility_pct"] <= 100.0

    def test_large_network_estimation(self):
        """500+ node stress test — must complete within 2 seconds."""
        D = nx.DiGraph()
        # 300 FIR criminals + 250 CDR criminals with 50 overlap
        for i in range(300):
            D.add_node(f"P{i}", type="PERSON", label=f"Person {i}", attrs={"sources": ["FIR"]}, aliases=[])
            case = f"C{i}"
            D.add_node(case, type="CASE", label=f"Case {i}", attrs={"criminal": True}, aliases=[])
            D.add_edge(f"P{i}", case, rel_type="ACCUSED_IN", count=1, attrs={})
        for i in range(250, 500):
            D.add_node(f"P{i}", type="PERSON", label=f"Person {i}", attrs={"sources": ["CDR"]}, aliases=[])
            ph = f"PH{i}"
            D.add_node(ph, type="PHONE", label=ph, attrs={}, aliases=[])
            D.add_edge(f"P{i}", ph, rel_type="USES_PHONE", count=1, attrs={})
        for i in range(270, 300):  # 30 overlap: in FIR and CDR
            ph = f"PH_fir_{i}"
            D.add_node(ph, type="PHONE", label=ph, attrs={}, aliases=[])
            D.add_edge(f"P{i}", ph, rel_type="USES_PHONE", count=1, attrs={})

        start = time.perf_counter()
        result = IcebergEstimator().estimate(D)
        elapsed = time.perf_counter() - start

        assert result["observed"] >= 500, f"Expected ≥500 observed, got {result['observed']}"
        assert elapsed < 2.0, f"Iceberg estimation took {elapsed:.2f}s — must be < 2s"


# ═══════════════════════════════════════════════════════
# Test: GhostNodeEngine
# ═══════════════════════════════════════════════════════

class TestGhostNodeEngine:
    def test_detects_ghost_nodes(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        engine = GhostNodeEngine(similarity_threshold=0.3, min_shared_neighbors=1)
        ghosts = engine.detect(P, community, susp, top=20)
        assert len(ghosts) > 0, "Expected ghost nodes to be detected"

    def test_no_direct_edge_on_ghost_pairs(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        engine = GhostNodeEngine(similarity_threshold=0.3, min_shared_neighbors=1)
        ghosts = engine.detect(P, community, susp, top=20)
        for g in ghosts:
            a, b = g["node_a"]["id"], g["node_b"]["id"]
            assert not P.has_edge(a, b), f"Ghost pair {a}-{b} actually has a direct edge!"

    def test_confidence_score_in_range(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        engine = GhostNodeEngine(similarity_threshold=0.3, min_shared_neighbors=1)
        ghosts = engine.detect(P, community, susp, top=20)
        for g in ghosts:
            assert 0 <= g["confidence_score"] <= 1.0

    def test_as_alerts_format(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        engine = GhostNodeEngine(similarity_threshold=0.3, min_shared_neighbors=1)
        ghosts = engine.detect(P, community, susp, top=5)
        alerts = engine.as_alerts(ghosts)
        for a in alerts:
            assert "id" in a
            assert a["kind"] == "GHOST_NODE"
            assert a["severity"] in ("low", "medium", "high", "critical")

    def test_performance_500_nodes(self):
        """Ghost node detection on 500-node graph must complete within 2 seconds."""
        P = nx.Graph()
        susp = {}
        community = {}
        for i in range(500):
            P.add_node(f"N{i}", type="PERSON", label=f"Person {i}", attrs={}, aliases=[])
            susp[f"N{i}"] = {"score": 0.3 if i < 300 else 0.05}
            community[f"N{i}"] = i // 50  # 10 communities of 50
        # Add edges to create structural holes
        for i in range(0, 490, 2):
            P.add_edge(f"N{i}", f"N{i+1}", weight=1.0, channels={})
            P.add_edge(f"N{i}", f"N{i+2}", weight=0.5, channels={})

        engine = GhostNodeEngine(similarity_threshold=0.5, min_shared_neighbors=1)
        start = time.perf_counter()
        ghosts = engine.detect(P, community, susp, top=15)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Ghost node detection took {elapsed:.2f}s — must be < 2s"


# ═══════════════════════════════════════════════════════
# Test: FirstTimeOffenderEngine
# ═══════════════════════════════════════════════════════

class TestFirstTimeOffenderEngine:
    def test_flags_clean_individuals_near_criminals(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        metrics = {n: {"degree": P.degree(n), "influence": 0.3} for n in P.nodes()}
        engine = FirstTimeOffenderEngine()
        results = engine.detect(P, susp, community, metrics, top=20)

        flagged_ids = {r["id"] for r in results}
        # P6 and P7 are "clean" but embedded — they MUST be flagged
        assert "P6" in flagged_ids, "P6 (clean, embedded in criminal network) must be flagged"
        assert "P7" in flagged_ids, "P7 (clean, embedded in criminal network) must be flagged"

    def test_no_accused_in_fto_results(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        metrics = {n: {"degree": P.degree(n), "influence": 0.3} for n in P.nodes()}
        engine = FirstTimeOffenderEngine()
        results = engine.detect(P, susp, community, metrics, top=20)
        for r in results:
            s = susp.get(r["id"], {})
            assert s.get("score", 0) < 0.2, f"{r['id']} has suspicion >= 0.2 but appeared in FTO results"
            assert s.get("accused", 0) == 0

    def test_risk_score_in_range(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        metrics = {n: {"degree": P.degree(n), "influence": 0.3} for n in P.nodes()}
        engine = FirstTimeOffenderEngine()
        results = engine.detect(P, susp, community, metrics, top=20)
        for r in results:
            assert 0.0 <= r["risk_score"] <= 1.0

    def test_as_alerts_format(self):
        P = _make_actor_projection()
        susp = _make_suspicion()
        community = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0, "P7": 0}
        metrics = {n: {"degree": P.degree(n), "influence": 0.3} for n in P.nodes()}
        engine = FirstTimeOffenderEngine()
        fto = engine.detect(P, susp, community, metrics, top=20)
        alerts = engine.as_alerts(fto)
        for a in alerts:
            assert a["kind"] == "FIRST_TIME_OFFENDER_RISK"
            assert "evidence" in a
            assert "proximity_score" in a["evidence"]

    def test_performance_500_nodes(self):
        """FTO detection on 500-node graph must complete within 2 seconds."""
        P = nx.Graph()
        susp = {}
        community = {}
        metrics = {}
        for i in range(500):
            P.add_node(f"N{i}", type="PERSON", label=f"Person {i}", attrs={}, aliases=[])
            susp[f"N{i}"] = {"score": 0.5 if i < 300 else 0.02, "accused": 1 if i < 200 else 0, "watchlist": None}
            community[f"N{i}"] = i // 50
            metrics[f"N{i}"] = {"degree": 3, "influence": 0.2}
        for i in range(0, 490):
            P.add_edge(f"N{i}", f"N{(i + 50) % 500}", weight=1.0, channels={"calls": 1})

        engine = FirstTimeOffenderEngine()
        start = time.perf_counter()
        results = engine.detect(P, susp, community, metrics, top=20)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"FTO detection took {elapsed:.2f}s — must be < 2s"
