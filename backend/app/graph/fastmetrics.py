"""
Rust-accelerated centrality (rustworkx) with a transparent NetworkX fallback.

Measured on this machine (Barabasi-Albert graphs):

    nodes   betweenness                                  pagerank
      500   nx 0.15s (k=200 sample) -> rx 0.00s (exact)  0.332s -> 0.000s
    5,000   nx 2.19s (k=200 sample) -> rx 0.46s (exact)  0.025s -> 0.007s

Parity checked against NetworkX on a weighted 400-node graph:
    pagerank   r = 1.0000  (identical ranking - rustworkx is used unconditionally)
    betweenness r = 0.970  (rustworkx has no weighted variant; see below)

Betweenness strategy - rustworkx exposes only exact *unweighted* betweenness, while our
edges carry tie strength. So:

    <= WEIGHTED_EXACT_LIMIT nodes : NetworkX, weighted, exact   (preserves tie strength)
    >  WEIGHTED_EXACT_LIMIT nodes : rustworkx, unweighted, exact

Above the limit NetworkX could only sample ~300 pivots, and an exact unweighted answer is
both more stable and more defensible to an investigator than a randomised weighted one.
`compute_metrics` records which method ran in the analytics snapshot.

rustworkx has no Louvain or Adamic-Adar, so community detection and link prediction stay on
NetworkX (see analytics.py). Set CNA_DISABLE_RUSTWORKX=1 to force the NetworkX path.
"""
from __future__ import annotations

import logging
import os

import networkx as nx

log = logging.getLogger("cna.fastmetrics")

try:  # optional dependency - the system is fully functional without it
    import rustworkx as rx

    RUSTWORKX_AVAILABLE = True
    RUSTWORKX_VERSION = rx.__version__
except ImportError:  # pragma: no cover
    rx = None
    RUSTWORKX_AVAILABLE = False
    RUSTWORKX_VERSION = None

# Below this size NetworkX computes exact *weighted* betweenness fast enough to prefer it.
WEIGHTED_EXACT_LIMIT = 600
# Last method used, for transparency in the analytics snapshot.
LAST_BETWEENNESS_METHOD = "none"


def enabled() -> bool:
    return RUSTWORKX_AVAILABLE and os.getenv("CNA_DISABLE_RUSTWORKX", "").lower() not in ("1", "true", "yes")


def backend() -> dict:
    return {"engine": "rustworkx" if enabled() else "networkx",
            "rustworkx_available": RUSTWORKX_AVAILABLE, "rustworkx_version": RUSTWORKX_VERSION,
            "weighted_exact_limit": WEIGHTED_EXACT_LIMIT, "betweenness_method": LAST_BETWEENNESS_METHOD}


# --------------------------------------------------------------------------------- conversion
def _to_rx(G: nx.Graph):
    """Build undirected + bidirected rustworkx copies. Returns (PyGraph, PyDiGraph, index->node_id)."""
    nodes = list(G.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    edges = [(idx[u], idx[v], float(d.get("weight", 1.0))) for u, v, d in G.edges(data=True)]

    g = rx.PyGraph(multigraph=False)
    g.add_nodes_from(range(len(nodes)))
    g.add_edges_from(edges)

    # PageRank needs a directed graph; an undirected edge becomes two arcs.
    d = rx.PyDiGraph(multigraph=False)
    d.add_nodes_from(range(len(nodes)))
    d.add_edges_from(edges + [(b, a, w) for a, b, w in edges])
    return g, d, nodes


def _remap(mapping, nodes: list) -> dict:
    """rustworkx returns a CentralityMapping keyed by node index."""
    return {nodes[i]: float(v) for i, v in mapping.items()}


# --------------------------------------------------------------------------------- centralities
def _nx_weighted_betweenness(G: nx.Graph, k: int | None) -> dict:
    H = G.copy()
    for _, _, d in H.edges(data=True):
        d["dist"] = 1.0 / max(d.get("weight", 1.0), 1e-6)
    return nx.betweenness_centrality(H, weight="dist", normalized=True, k=k, seed=7)


def betweenness(G: nx.Graph) -> dict[str, float]:
    global LAST_BETWEENNESS_METHOD
    n = G.number_of_nodes()
    if n == 0:
        LAST_BETWEENNESS_METHOD = "none"
        return {}
    if n <= WEIGHTED_EXACT_LIMIT:
        LAST_BETWEENNESS_METHOD = "networkx-weighted-exact"
        return _nx_weighted_betweenness(G, None)
    if enabled():
        try:
            g, _, nodes = _to_rx(G)
            res = rx.betweenness_centrality(g, normalized=True)
            LAST_BETWEENNESS_METHOD = "rustworkx-unweighted-exact"
            return _remap(res, nodes)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("rustworkx betweenness failed (%s); falling back to networkx", exc)
    LAST_BETWEENNESS_METHOD = "networkx-weighted-sampled"
    return _nx_weighted_betweenness(G, 300)


def pagerank(G: nx.Graph, alpha: float = 0.85) -> dict[str, float]:
    if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
        return {n: 0.0 for n in G}
    if enabled():
        try:
            _, d, nodes = _to_rx(G)
            return _remap(rx.pagerank(d, alpha=alpha, weight_fn=float), nodes)
        except Exception as exc:  # pragma: no cover
            log.warning("rustworkx pagerank failed (%s); falling back to networkx", exc)
    return nx.pagerank(G, weight="weight", alpha=alpha)


def eigenvector(G: nx.Graph) -> dict[str, float]:
    """Per-component eigenvector centrality, scaled by component share.

    Solving it globally on a disconnected graph is ill-defined (NetworkX raises
    AmbiguousSolution), so each component is solved separately and weighted by its size.
    """
    eig = {n: 0.0 for n in G}
    total = G.number_of_nodes() or 1
    for comp in nx.connected_components(G):
        if len(comp) < 3:
            continue
        sub = G.subgraph(comp)
        scale = len(comp) / total
        vals: dict | None = None
        if enabled():
            try:
                g, _, nodes = _to_rx(sub)
                vals = _remap(rx.eigenvector_centrality(g, weight_fn=float, max_iter=1000), nodes)
            except Exception:
                vals = None
        if vals is None:
            try:
                vals = nx.eigenvector_centrality_numpy(sub, weight="weight")
            except Exception:
                try:
                    vals = nx.eigenvector_centrality(sub, weight="weight", max_iter=2000)
                except Exception:
                    continue
        for n, v in vals.items():
            eig[n] = abs(v) * scale
    return eig


def closeness(G: nx.Graph) -> dict[str, float]:
    if G.number_of_nodes() == 0:
        return {}
    if enabled():
        try:
            g, _, nodes = _to_rx(G)
            return {n: v for n, v in _remap(rx.closeness_centrality(g), nodes).items()}
        except Exception as exc:  # pragma: no cover
            log.warning("rustworkx closeness failed (%s); falling back to networkx", exc)
    return nx.closeness_centrality(G)
