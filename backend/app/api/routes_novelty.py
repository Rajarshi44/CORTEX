"""
Novel intelligence endpoints — exposes the three enterprise-grade features:

  GET /api/novelty/summary          — All three analyses in one call (for the dashboard)
  GET /api/novelty/iceberg          — Network size estimation (capture-recapture)
  GET /api/novelty/ghost-nodes      — Unobserved intermediary inference
  GET /api/novelty/first-time-risk  — Clean-record individuals embedded in criminal nets
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import User, get_session
from ..graph.novelty import (
    FirstTimeOffenderEngine,
    GhostNodeEngine,
    IcebergEstimator,
    run_novelty,
)
from ..graph.discrepancy import run_discrepancy_detection
from ..graph.store import graph_cache
from .deps import analysis_service

router = APIRouter(prefix="/api/novelty", tags=["novelty"])


@router.get("/summary")
def novelty_summary(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
    top_ghost: int = 15,
    top_fto: int = 20,
):
    """
    Full novel-intelligence summary.  Runs all three engines and returns a single
    consolidated payload suitable for powering a 'Novel Intel' dashboard tab.
    """
    G = graph_cache.get(db)
    D = graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    return run_novelty(G, D, snap, top_ghost=top_ghost, top_fto=top_fto)


@router.get("/iceberg")
def iceberg(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
):
    """
    Capture-recapture network size estimation.

    Returns the observed count, the statistically estimated true network size, the
    'dark number' of undetected individuals, and a confidence interval per source pair.

    The Chapman bias-corrected estimator is used across every pair of intelligence
    sources present in the data (FIR, CDR, TRANSFER, etc.).
    """
    D = graph_cache.get_directed(db)
    return IcebergEstimator().estimate(D)


@router.get("/ghost-nodes")
def ghost_nodes(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
    threshold: float = 0.55,
    min_shared: int = 2,
    top: int = 15,
):
    """
    Unobserved intermediary inference.

    Scans the actor projection for pairs of individuals who share a high structural
    similarity (Jaccard ≥ threshold) but have zero direct recorded contact.  This
    signature — shared criminal environment, deliberate non-communication — indicates
    a handler/cutout relationship.

    Each result includes:
    - confidence_score: Jaccard × suspicion boost
    - shared_neighbors: the mutual contacts that connect the pair indirectly
    - interpretation: plain-English explanation of the pattern
    """
    G = graph_cache.get(db)
    D = graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)

    community = snap.get("community", {})
    susp = snap.get("suspicion", {})

    # Rebuild actor projection from snapshot edges
    import networkx as nx
    P = nx.Graph()
    for n, data in G.nodes(data=True):
        if data.get("type") in ("PERSON", "ORGANIZATION"):
            P.add_node(n, **data)
    for edge in snap.get("projection_edges", []):
        u, v = edge["source"], edge["target"]
        if u in P and v in P:
            P.add_edge(u, v, **{k: val for k, val in edge.items() if k not in ("source", "target")})

    engine = GhostNodeEngine(similarity_threshold=threshold, min_shared_neighbors=min_shared)
    ghosts = engine.detect(P, community, susp, top=top)
    return {"ghost_nodes": ghosts, "count": len(ghosts), "alerts": engine.as_alerts(ghosts)}


@router.get("/first-time-risk")
def first_time_risk(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
    top: int = 20,
):
    """
    First-time offender proximity risk.

    Identifies individuals with NO prior criminal record (suspicion < 0.2, never
    accused, not watchlisted) who are structurally embedded within known criminal
    communities.

    Risk is a weighted composite of:
    - proximity_score   (0.40 weight): mean suspicion of direct neighbours
    - community_risk    (0.25 weight): mean suspicion of their community
    - contact_quality   (0.20 weight): fraction of neighbours who are high-risk
    - channel_diversity (0.15 weight): breadth of criminal communication channels

    This mirrors real-world intelligence systems (e.g., Operation LASER) and is
    grounded in network criminology research (Papachristos et al., 2013).
    """
    G = graph_cache.get(db)
    snap = analysis_service.snapshot(db)

    susp = snap.get("suspicion", {})
    community = snap.get("community", {})
    metrics = snap.get("metrics", {})

    import networkx as nx
    P = nx.Graph()
    for n, data in G.nodes(data=True):
        if data.get("type") in ("PERSON", "ORGANIZATION"):
            P.add_node(n, **data)
    for edge in snap.get("projection_edges", []):
        u, v = edge["source"], edge["target"]
        if u in P and v in P:
            P.add_edge(u, v, **{k: val for k, val in edge.items() if k not in ("source", "target")})

    engine = FirstTimeOffenderEngine()
    fto = engine.detect(P, susp, community, metrics, top=top)
    return {"first_time_offenders": fto, "count": len(fto), "alerts": engine.as_alerts(fto)}


@router.get("/discrepancies")
def discrepancies(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
):
    """
    Source discrepancy detection.

    Flags cases where two or more intelligence sources provide conflicting
    information about the same entity. Detects:

    - OWNERSHIP_CONFLICT:  Same phone/account/vehicle attributed to multiple owners
    - ATTRIBUTE_CONFLICT:  Same entity with different DOB, age, address across sources
    - STATUS_CONFLICT:     Entity marked deceased in one source but active in others

    These discrepancies are high-value investigative leads: they indicate either
    identity fraud, record tampering, SIM-swap operations, or ghost identity use.
    """
    D = graph_cache.get_directed(db)
    return run_discrepancy_detection(D)
