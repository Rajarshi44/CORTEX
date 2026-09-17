"""Automated tests for Milestone M1: Demo Loader Fixes & Call Detail Records (CDR).

Verifies:
a) Contextual edge mapping for CONTROLS:
   - P005 (Rahul) -> P006 (Amit Verma) has rel_type == "CONTROLS" in DB and Graph.
   - P001 (Victim) -> A002 (Victim Account) has rel_type == "OWNS_ACCOUNT".
   - P001 (Victim) -> PH002 (Victim Phone) has rel_type == "USES_PHONE".
b) DIRECT_WEIGHTS in analytics.py includes "CONTROLS": 3.0 and actor projection respects it.
c) Calls from 09_cdr.csv are loaded into TimelineEvent with kind == "CALL".
d) AnomalyDetector detects call_bursts, night_activity, and international calls.
"""
from __future__ import annotations

import os
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Entity, Relationship, TimelineEvent, Alert
from app.graph.store import graph_cache
from app.graph.analytics import DIRECT_WEIGHTS, actor_projection
from app.graph.anomalies import AnomalyDetector
from app.ingestion.load_demo_case import load_demo_data


@pytest.fixture(scope="module")
def demo_session(tmp_path_factory):
    """Load the demo case data into an isolated test database once for this test module."""
    db_file = tmp_path_factory.mktemp("m1_data") / "test_demo.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    # Invalidate cache and load demo data
    graph_cache.invalidate()
    stats = load_demo_data(session)
    assert stats["calls"] > 0, "Demo loader should report ingested calls"

    yield session

    session.close()
    engine.dispose()
    graph_cache.invalidate()


def _get_entity(session, record_id: str) -> Entity:
    ent = session.query(Entity).filter(Entity.attributes["record_id"].as_string() == record_id).first()
    assert ent is not None, f"Entity with record_id {record_id} must exist in DB"
    return ent


def test_p005_to_p006_edge_controls(demo_session):
    """Verify P005 (Rahul) -> P006 (Amit Verma) has rel_type == 'CONTROLS' in DB and Graph."""
    p005 = _get_entity(demo_session, "P005")
    p006 = _get_entity(demo_session, "P006")

    # 1. Verify in DB
    rel = demo_session.query(Relationship).filter(
        Relationship.source_id == p005.id,
        Relationship.target_id == p006.id
    ).first()
    assert rel is not None, "Relationship P005 -> P006 must exist in DB"
    assert rel.rel_type == "CONTROLS", f"Expected rel_type 'CONTROLS', got {rel.rel_type}"

    # 2. Verify in Directed Graph (DiGraph)
    D = graph_cache.get_directed(demo_session)
    assert D.has_edge(p005.id, p006.id), "P005 -> P006 edge must exist in DiGraph"
    assert D[p005.id][p006.id]["rel_type"] == "CONTROLS"

    # 3. Verify in Undirected Graph (Graph)
    G = graph_cache.get(demo_session)
    assert G.has_edge(p005.id, p006.id), "P005 -- P006 edge must exist in Graph"
    assert "CONTROLS" in G[p005.id][p006.id]["rel_types"]


def test_p001_to_a002_edge_owns_account(demo_session):
    """Verify P001 (Victim) -> A002 (Victim Account) has rel_type == 'OWNS_ACCOUNT'."""
    p001 = _get_entity(demo_session, "P001")
    a002 = _get_entity(demo_session, "A002")

    # 1. In DB
    rel = demo_session.query(Relationship).filter(
        Relationship.source_id == p001.id,
        Relationship.target_id == a002.id
    ).first()
    assert rel is not None, "Relationship P001 -> A002 must exist in DB"
    assert rel.rel_type == "OWNS_ACCOUNT", f"Expected rel_type 'OWNS_ACCOUNT', got {rel.rel_type}"

    # 2. In DiGraph
    D = graph_cache.get_directed(demo_session)
    assert D.has_edge(p001.id, a002.id)
    assert D[p001.id][a002.id]["rel_type"] == "OWNS_ACCOUNT"


def test_p001_to_ph002_edge_uses_phone(demo_session):
    """Verify P001 (Victim) -> PH002 (Victim Phone) has rel_type == 'USES_PHONE'."""
    p001 = _get_entity(demo_session, "P001")
    ph002 = _get_entity(demo_session, "PH002")

    # 1. In DB
    rel = demo_session.query(Relationship).filter(
        Relationship.source_id == p001.id,
        Relationship.target_id == ph002.id
    ).first()
    assert rel is not None, "Relationship P001 -> PH002 must exist in DB"
    assert rel.rel_type == "USES_PHONE", f"Expected rel_type 'USES_PHONE', got {rel.rel_type}"

    # 2. In DiGraph
    D = graph_cache.get_directed(demo_session)
    assert D.has_edge(p001.id, ph002.id)
    assert D[p001.id][ph002.id]["rel_type"] == "USES_PHONE"


def test_analytics_controls_weight_and_actor_projection(demo_session):
    """Verify DIRECT_WEIGHTS includes CONTROLS: 3.0 and actor projection folds P005 -> P006."""
    assert "CONTROLS" in DIRECT_WEIGHTS, "DIRECT_WEIGHTS must include 'CONTROLS'"
    assert DIRECT_WEIGHTS["CONTROLS"] == 3.0, f"Expected weight 3.0, got {DIRECT_WEIGHTS['CONTROLS']}"

    p005 = _get_entity(demo_session, "P005")
    p006 = _get_entity(demo_session, "P006")

    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)

    assert P.has_edge(p005.id, p006.id), "Actor projection must include P005 -- P006 edge"
    edge_data = P[p005.id][p006.id]
    assert "controls" in edge_data["channels"], "Command structure edge should be recorded in channels"


def test_cdr_calls_loaded_into_timeline_events(demo_session):
    """Verify calls from 09_cdr.csv are loaded as TimelineEvent with kind == 'CALL'."""
    call_events = demo_session.query(TimelineEvent).filter(TimelineEvent.kind == "CALL").all()
    assert len(call_events) >= 50, f"Expected at least 50 call events, got {len(call_events)}"

    for e in call_events:
        assert len(e.entity_ids) == 2, f"Call event {e.id} should link caller and callee entity ids"
        assert isinstance(e.occurred_at, datetime), "Call event must have occurred_at timestamp"
        assert "caller" in e.details, "Call event details must contain caller"
        assert "callee" in e.details, "Call event details must contain callee"
        assert "duration" in e.details or "duration_sec" in e.details, "Call event details must contain duration"
        assert "night" in e.details, "Call event details must contain night boolean flag"


def test_cdr_called_edges_in_graph(demo_session):
    """Verify CALLED edges exist between suspect phones in the graph."""
    ph003 = _get_entity(demo_session, "PH003")
    ph004 = _get_entity(demo_session, "PH004")

    D = graph_cache.get_directed(demo_session)
    assert D.has_edge(ph003.id, ph004.id), "PH003 -> PH004 CALLED edge must exist in DiGraph"
    assert D[ph003.id][ph004.id]["rel_type"] == "CALLED"
    assert D[ph003.id][ph004.id]["count"] > 1, "Multiple calls between PH003 and PH004 should aggregate count"


def test_anomaly_detector_alerts(demo_session):
    """Verify AnomalyDetector finds call_bursts, night_activity, and international contacts."""
    G = graph_cache.get(demo_session)
    D = graph_cache.get_directed(demo_session)
    detector = AnomalyDetector(demo_session, G, D)

    # 1. Call bursts
    bursts = detector.call_bursts()
    assert len(bursts) > 0, "call_bursts() should detect coordinated call burst"
    assert any(b["kind"] == "call_burst" for b in bursts)

    # 2. Night activity
    night = detector.night_activity()
    assert len(night) > 0, "night_activity() should detect night-time communication pattern"
    assert any(n["kind"] == "night_activity" for n in night)

    # 3. International calls
    intl = detector.international()
    assert len(intl) > 0, "international() should detect international calls to/from foreign numbers"
    assert any(i["kind"] == "international_contact" for i in intl)
