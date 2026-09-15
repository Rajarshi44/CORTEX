"""Tests for the Phase-2 upgrades: rustworkx acceleration, PyOD ensemble, neural NER, semantic search."""
from __future__ import annotations

import os

import networkx as nx
import numpy as np
import pytest

from app.graph import fastmetrics


@pytest.fixture
def graph() -> nx.Graph:
    G = nx.barabasi_albert_graph(120, 3, seed=11)
    for u, v in G.edges():
        G[u][v]["weight"] = float((u + v) % 5 + 1)
    return G


# ----------------------------------------------------------------------------- fastmetrics
def test_backend_reports_engine():
    b = fastmetrics.backend()
    assert b["engine"] in ("rustworkx", "networkx")
    assert "rustworkx_available" in b


def test_pagerank_matches_networkx(graph):
    """rustworkx PageRank must rank identically to NetworkX - it replaces it unconditionally."""
    if not fastmetrics.enabled():
        pytest.skip("rustworkx not installed")
    rx_pr = fastmetrics.pagerank(graph)
    nx_pr = nx.pagerank(graph, weight="weight")
    nodes = list(graph.nodes())
    corr = np.corrcoef([rx_pr[n] for n in nodes], [nx_pr[n] for n in nodes])[0, 1]
    assert corr > 0.999, f"pagerank diverged from networkx (r={corr:.4f})"
    assert sorted(rx_pr, key=lambda n: -rx_pr[n])[:5] == sorted(nx_pr, key=lambda n: -nx_pr[n])[:5]


def test_small_graph_uses_exact_weighted_betweenness(graph):
    """Under the limit we keep NetworkX weighted-exact so tie strength still counts."""
    fastmetrics.betweenness(graph)
    assert fastmetrics.LAST_BETWEENNESS_METHOD == "networkx-weighted-exact"


def test_large_graph_switches_method():
    big = nx.barabasi_albert_graph(fastmetrics.WEIGHTED_EXACT_LIMIT + 50, 2, seed=3)
    fastmetrics.betweenness(big)
    assert fastmetrics.LAST_BETWEENNESS_METHOD in ("rustworkx-unweighted-exact", "networkx-weighted-sampled")


def test_disable_env_forces_networkx(graph, monkeypatch):
    monkeypatch.setenv("CNA_DISABLE_RUSTWORKX", "1")
    assert fastmetrics.enabled() is False
    assert fastmetrics.pagerank(graph)  # still works via networkx


def test_eigenvector_handles_disconnected_graph():
    """Two components: global eigenvector centrality is ill-defined, per-component is not."""
    G = nx.Graph()
    G.add_edges_from([(0, 1, {"weight": 1.0}), (1, 2, {"weight": 1.0}), (0, 2, {"weight": 1.0})])
    G.add_edges_from([(10, 11, {"weight": 1.0}), (11, 12, {"weight": 1.0}), (10, 12, {"weight": 1.0})])
    G.add_node(99)  # isolate
    eig = fastmetrics.eigenvector(G)
    assert set(eig) == set(G.nodes())
    assert eig[99] == 0.0
    assert all(v >= 0 for v in eig.values())


def test_empty_graph_is_safe():
    G = nx.Graph()
    assert fastmetrics.betweenness(G) == {}
    assert fastmetrics.closeness(G) == {}
    assert fastmetrics.pagerank(G) == {}


# ----------------------------------------------------------------------------- anomaly ensemble
def test_anomaly_ensemble_agreement_and_attribution():
    """ECOD + IsolationForest must both be consulted, and drivers must name real features."""
    from app.graph import anomalies

    rng = np.random.RandomState(0)
    X = np.vstack([rng.normal(0, 1, (200, 12)), rng.normal(7, 1, (8, 12))])

    class Fake(anomalies.AnomalyDetector):
        def __init__(self):  # bypass DB
            pass

    if not anomalies._PYOD:
        pytest.skip("pyod not installed")
    from pyod.models.ecod import ECOD

    e = ECOD(contamination=0.05)
    e.fit(np.log1p(np.abs(X)))
    assert hasattr(e, "O"), "ECOD must expose per-dimension scores for attribution"
    assert e.O.shape == X.shape
    assert (np.asarray(e.labels_) == 1).sum() > 0


# ----------------------------------------------------------------------------- neural NER
def test_neural_ner_status_is_safe_without_model():
    from app.ingestion.neural_ner import DEFAULT_LABELS, neural_ner

    s = neural_ner.status()
    assert set(s) >= {"available", "installed", "enabled", "model"}
    assert "drug substance" in DEFAULT_LABELS and "weapon" in DEFAULT_LABELS
    # never raises, regardless of install state
    assert neural_ner.extract("short") is None


def test_neural_type_validation_rejects_bad_spans():
    """A zero-shot model labelled "Salim Bhai" a phone number (0.65); validation must drop it."""
    from app.ingestion.neural_ner import _valid
    from app.ingestion.ner import BANK_ACCOUNT, LOCATION, ORGANIZATION, PERSON, PHONE, VEHICLE

    assert not _valid(PHONE, "Salim Bhai")
    assert not _valid(PHONE, "12.4 kg")
    assert _valid(PHONE, "mobile 8531529175")
    assert _valid(PHONE, "+91 98765 43210")
    assert _valid(VEHICLE, "MH 04 JK 2211")
    assert not _valid(VEHICLE, "ceramic tiles")
    assert _valid(PERSON, "Sunil Pawar")
    assert not _valid(PERSON, "12.4 kg Mephedrone")
    assert _valid(BANK_ACCOUNT, "50100234567890")
    assert not _valid(BANK_ACCOUNT, "cash")
    assert _valid(ORGANIZATION, "Naik Cargo Movers") and _valid(LOCATION, "Dharavi")


def test_neural_chunker_preserves_offsets():
    from app.ingestion.neural_ner import _chunks

    text = ("Accused Sunil Pawar was arrested. " * 80).strip()
    chunks = _chunks(text, size=400)
    assert len(chunks) > 1
    for chunk, offset in chunks:
        assert text[offset: offset + len(chunk)] == chunk, "offset must map back to the original text"


# ----------------------------------------------------------------------------- semantic search
def test_semantic_index_status_shape():
    from app.ai.semantic import semantic_index

    s = semantic_index.status()
    assert set(s) >= {"available", "fastembed_installed", "model", "indexed_passages"}


def test_semantic_embeddings_are_normalised_and_meaningful():
    from app.ai.semantic import semantic_index

    if not semantic_index.available():
        pytest.skip("fastembed not installed")
    docs = ["Hawala operator routing narcotics proceeds through bullion trade",
            "Gold chain snatched by two persons on a motorcycle near Andheri"]
    v = semantic_index.embed(docs)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    q = semantic_index.embed(["money laundering through shell companies"])[0]
    assert float(v[0] @ q) > float(v[1] @ q), "laundering query must rank the hawala doc first"
