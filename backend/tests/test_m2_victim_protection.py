"""Tests for Milestone M2: Victim Protection & Masking.

Verifies:
1. Party roles standardization: 'victim', 'complainant', 'witness', 'police'.
2. P001 (Victim/Complainant) has suspicion == 0.0 and priority == 0.0.
3. P001 does NOT appear in top key players ranking.
4. P001 is not assigned to any criminal community (community == -1).
5. Protected parties are never flagged as first-time offenders.
6. build_markdown and build_pdf mask victim/complainant names to [VICTIM]/[COMPLAINANT].
7. Role classification assigns role='victim' with label 'Protected Victim'.
"""
from __future__ import annotations

import io
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Entity, Relationship, TimelineEvent
from app.graph.quality import PROTECTED_PARTY_ROLES, is_protected_party
from app.graph.analytics import (
    ROLE_LABELS,
    actor_projection,
    classify_roles,
    compute_metrics,
    compute_proximity_risk,
    detect_communities,
    first_time_offender_risk,
    key_players,
    priority_scores,
    run_all,
    suspicion_signals,
)
from app.graph.store import graph_cache
from app.ingestion.load_demo_case import load_demo_data
from app.reports.generator import build_markdown, build_pdf, get_protected_pairs, mask_report_text


@pytest.fixture(scope="module")
def demo_session(tmp_path_factory):
    """Load the demo case data into an isolated test database once for this test module."""
    db_file = tmp_path_factory.mktemp("m2_data") / "test_demo.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    graph_cache.invalidate()
    load_demo_data(session)

    yield session

    session.close()
    engine.dispose()
    graph_cache.invalidate()


def _get_entity(session, record_id: str) -> Entity:
    ent = session.query(Entity).filter(Entity.attributes["record_id"].as_string() == record_id).first()
    assert ent is not None, f"Entity with record_id {record_id} must exist in DB"
    return ent


def test_party_roles_standardization():
    """Verify standardization of party roles and is_protected_party helper."""
    assert "victim" in PROTECTED_PARTY_ROLES
    assert "complainant" in PROTECTED_PARTY_ROLES
    assert "witness" in PROTECTED_PARTY_ROLES
    assert "police" in PROTECTED_PARTY_ROLES

    # Test is_protected_party with various inputs
    assert is_protected_party("PERSON", "Victim", {"party_role": "victim"}) is True
    assert is_protected_party("PERSON", "Complainant 1", {"party_role": "complainant"}) is True
    assert is_protected_party("PERSON", "Witness A", {"party_role": "witness"}) is True
    assert is_protected_party("PERSON", "Inspector Sharma", {"party_role": "police"}) is True
    assert is_protected_party("PERSON", "Victim", {"record_id": "P001"}) is True

    # Scammer/Accused should NOT be protected
    assert is_protected_party("PERSON", "Rahul", {"role_in_network": "Main Beneficiary", "status": "At Large"}) is False
    assert is_protected_party("PERSON", "Amit Verma", {"role_in_network": "Student Mule", "status": "Accused"}) is False


def test_p001_party_role_and_ingestion(demo_session):
    """Verify P001 has party_role set properly in DB."""
    p001 = _get_entity(demo_session, "P001")
    assert p001.attributes.get("party_role") == "victim"
    assert is_protected_party(p001.type, p001.label, p001.attributes) is True


def test_p001_suspicion_and_priority_zero(demo_session):
    """Verify P001 (Victim/Complainant) has suspicion == 0.0 and priority == 0.0."""
    p001 = _get_entity(demo_session, "P001")
    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)

    susp = suspicion_signals(D)
    metrics = compute_metrics(P)
    prio = priority_scores(metrics, susp, P)

    assert p001.id in susp, "P001 must be present in suspicion output"
    assert susp[p001.id]["score"] == 0.0, f"P001 suspicion score must be 0.0, got {susp[p001.id]['score']}"
    assert susp[p001.id]["reasons"] == [], f"P001 suspicion reasons must be empty, got {susp[p001.id]['reasons']}"
    assert susp[p001.id].get("protected") is True, "P001 must be marked as protected"

    assert prio[p001.id] == 0.0, f"P001 priority score must be 0.0, got {prio[p001.id]}"


def test_p001_excluded_from_key_players(demo_session):
    """Verify P001 does NOT appear in top key players ranking."""
    p001 = _get_entity(demo_session, "P001")
    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)

    susp = suspicion_signals(D)
    metrics = compute_metrics(P)
    comm = detect_communities(P)
    roles = classify_roles(P, metrics, comm, D, susp)
    prio = priority_scores(metrics, susp, P)

    top_players = key_players(P, metrics, roles, comm, prio, susp, top=50)
    top_ids = [kp["id"] for kp in top_players]

    assert p001.id not in top_ids, "P001 (Victim) must NOT appear in key players ranking"
    # Ensure no protected party appears in key players
    for kp in top_players:
        node = P.nodes[kp["id"]]
        assert not is_protected_party(node.get("type", ""), node.get("label", ""), node.get("attrs") or {}), \
            f"Protected node {kp['label']} must not be in key players"


def test_p001_excluded_from_criminal_communities(demo_session):
    """Verify P001 is not assigned to any criminal community (community == -1)."""
    p001 = _get_entity(demo_session, "P001")
    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)

    comm = detect_communities(P)
    assert comm.get(p001.id) == -1, f"P001 community must be -1, got {comm.get(p001.id)}"


def test_p001_role_classification(demo_session):
    """Verify role classification assigns 'victim' / 'Protected Victim'."""
    p001 = _get_entity(demo_session, "P001")
    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)

    susp = suspicion_signals(D)
    metrics = compute_metrics(P)
    comm = detect_communities(P)
    roles = classify_roles(P, metrics, comm, D, susp)

    assert p001.id in roles
    assert roles[p001.id]["role"] == "victim"
    assert roles[p001.id]["label"] == "Protected Victim"
    assert roles[p001.id]["accused_count"] == 0


def test_first_time_offender_risk_excludes_protected_parties(demo_session):
    """Verify that protected parties are NEVER flagged as first-time offenders."""
    p001 = _get_entity(demo_session, "P001")
    D = graph_cache.get_directed(demo_session)
    P = actor_projection(D)
    susp = suspicion_signals(D)
    comm = detect_communities(P)
    metrics = compute_metrics(P)

    # 1. First-time offender risk list
    fto = first_time_offender_risk(P, susp, comm, metrics)
    fto_ids = [item["id"] for item in fto]
    assert p001.id not in fto_ids, "Victim P001 must NEVER be flagged as first-time offender"

    # 2. Proximity risk scores
    prox_scores = compute_proximity_risk(P, susp)
    assert prox_scores.get(p001.id) == 0.0, f"Victim P001 proximity risk must be 0.0, got {prox_scores.get(p001.id)}"


def test_first_time_offender_synthetic_embedded_victim():
    """Verify that even if a victim has 3+ direct connections to high-suspicion nodes, they receive 0.0 risk."""
    import networkx as nx

    P = nx.Graph()
    # Scammers
    P.add_node("scammer1", type="PERSON", label="Scammer 1", attrs={"status": "Accused"})
    P.add_node("scammer2", type="PERSON", label="Scammer 2", attrs={"status": "Accused"})
    P.add_node("scammer3", type="PERSON", label="Scammer 3", attrs={"status": "Accused"})
    # Victim connected to all 3
    P.add_node("victim1", type="PERSON", label="Victim", attrs={"party_role": "victim", "status": "Complainant"})
    P.add_edge("victim1", "scammer1", channels={"calls": 10}, weight=1.0)
    P.add_edge("victim1", "scammer2", channels={"transfers": 2}, weight=1.0)
    P.add_edge("victim1", "scammer3", channels={"calls": 5}, weight=1.0)

    # Clean non-victim embedded node
    P.add_node("clean_mule", type="PERSON", label="Clean Person", attrs={})
    P.add_edge("clean_mule", "scammer1", channels={"transfers": 1}, weight=1.0)
    P.add_edge("clean_mule", "scammer2", channels={"transfers": 1}, weight=1.0)
    P.add_edge("clean_mule", "scammer3", channels={"transfers": 1}, weight=1.0)

    susp = {
        "scammer1": {"score": 0.8, "accused": 1},
        "scammer2": {"score": 0.9, "accused": 1},
        "scammer3": {"score": 0.7, "accused": 1},
        "victim1": {"score": 0.0, "accused": 0, "protected": True},
        "clean_mule": {"score": 0.0, "accused": 0},
    }

    fto = first_time_offender_risk(P, susp)
    fto_ids = [item["id"] for item in fto]

    # Clean mule connected to 3 high-suspicion nodes should be flagged
    assert "clean_mule" in fto_ids, "Clean individual connected to 3 high-suspicion nodes should be flagged"
    # Victim MUST NOT be flagged
    assert "victim1" not in fto_ids, "Victim connected to 3 high-suspicion nodes must NEVER be flagged"

    prox = compute_proximity_risk(P, susp)
    assert prox["victim1"] == 0.0
    assert prox["clean_mule"] >= 0.85


def test_brief_markdown_and_pdf_masking(demo_session):
    """Verify build_markdown and build_pdf mask victim and complainant names."""
    G = graph_cache.get(demo_session)
    D = graph_cache.get_directed(demo_session)

    from app.api.deps import analysis_service
    snap = analysis_service.snapshot(demo_session, force=False)

    md = build_markdown(demo_session, G, D, snap, case_name="Operation CyberHawk 2.0 Brief")

    # The mask [VICTIM] must be present
    assert "[VICTIM]" in md, "Masked token [VICTIM] must appear in generated markdown brief"
    # Standalone unmasked "Victim" should not appear as a player name
    import re
    # Check that any line with "Victim" is actually [VICTIM]
    unmasked_victim = re.findall(r"\bVictim\b(?!\s*\])", md)
    assert len(unmasked_victim) == 0, f"Found unmasked victim mentions in brief markdown: {unmasked_victim}"

    # Test build_pdf produces valid PDF bytes with masked content
    pdf_bytes = build_pdf(md, title="Operation CyberHawk 2.0 Brief", db=demo_session)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF"), "Output must be a valid PDF document"
    assert len(pdf_bytes) > 2000, "PDF output must contain content"
    assert b"[VICTIM]" in pdf_bytes, "PDF binary stream must contain [VICTIM] mask"


def test_ncrp_complainants_protection(demo_session):
    """Verify that NCRP complainants have party_role and are protected."""
    complainants = demo_session.query(Entity).filter(
        Entity.attributes["party_role"].as_string() == "complainant"
    ).all()
    assert len(complainants) > 0, "NCRP complainants should be present with party_role == 'complainant'"

    D = graph_cache.get_directed(demo_session)
    susp = suspicion_signals(D)
    for c in complainants:
        assert is_protected_party(c.type, c.label, c.attributes) is True
        if c.id in susp:
            assert susp[c.id]["score"] == 0.0
            assert susp[c.id]["reasons"] == []
