"""
Enterprise Novel Analytics — Three groundbreaking additions to the CORTEX analysis engine:

1. IcebergEstimator — Estimates the TRUE unobserved network size using capture-recapture
   statistics (Chapman bias-corrected estimator) across multi-source entity overlaps.

2. GhostNodeEngine — Infers unobserved intermediaries (cutouts, handlers, dead-drops)
   by finding structurally equivalent pairs with zero direct communication.

3. FirstTimeOffenderEngine — Proximity-based risk scoring for individuals with no prior
   record who are structurally embedded in known criminal networks.

These are designed to plug directly into the existing run_all() pipeline and are
exposed via a new /api/novelty/* endpoint group.
"""
from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

import networkx as nx
import numpy as np

from .discrepancy import run_discrepancy_detection

# ── Shared internal severity helper ────────────────────────────────────────────
def _sev(score: float) -> str:
    return "critical" if score >= 0.85 else "high" if score >= 0.65 else "medium" if score >= 0.4 else "low"


def _alert(kind: str, title: str, description: str, score: float, entity_ids: list[str], evidence: dict) -> dict:
    return {
        "id": str(uuid.uuid4()), "kind": kind, "severity": _sev(score),
        "title": title, "description": description, "score": round(float(score), 3),
        "entity_ids": list(dict.fromkeys(entity_ids)), "evidence": evidence,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. ICEBERG ESTIMATOR
# ══════════════════════════════════════════════════════════════════════════════

class IcebergEstimator:
    """
    Estimates the true, unobserved size of a criminal network using capture-recapture
    statistics.  The Chapman bias-corrected estimator is applied to every pair of
    distinct intelligence sources (FIR, CDR, TRANSFER, COMPLAINT, SOCIAL) by counting
    how many entity IDs appear in both.

    Formula:
        N̂ = ((n₁ + 1)(n₂ + 1) / (m + 1)) − 1
        Var(N̂) ≈ (n₁+1)(n₂+1)(n₁−m)(n₂−m) / ((m+1)²(m+2))

    where n₁, n₂ are the capture sizes and m is the overlap (recapture).

    Interpretation:
        - "dark_number": estimated criminals NOT yet in any dataset
        - "visibility_pct": what fraction of the true network we can currently see
    """

    SOURCE_PRIORITY = ["FIR", "CDR", "TRANSFER", "COMPLAINT", "REPORT", "SOCIAL"]

    def estimate(self, D: nx.DiGraph) -> dict[str, Any]:
        """Extract entity sets per data source from the directed graph and estimate."""
        source_sets: dict[str, set[str]] = defaultdict(set)

        for n, data in D.nodes(data=True):
            if data.get("type") not in ("PERSON", "ORGANIZATION"):
                continue
            attrs = data.get("attrs") or {}
            for src in attrs.get("sources", []):
                source_sets[src.upper()].add(n)

        # Also bucket by relationship type — every node reachable through FIR/CDR edges
        for u, v, edata in D.edges(data=True):
            rt = edata.get("rel_type", "")
            if rt in ("ACCUSED_IN", "WANTED_IN", "MENTIONED_IN", "COMPLAINANT_IN"):
                source_sets["FIR"].add(u)
            elif rt == "CALLED":
                source_sets["CDR"].update([u, v])
            elif rt == "TRANSFERRED_TO":
                source_sets["TRANSFER"].update([u, v])

        # Keep only sources with enough data for estimation
        source_sets = {k: v for k, v in source_sets.items() if len(v) >= 3}

        observed_total = len(set().union(*source_sets.values())) if source_sets else 0
        pairwise: list[dict] = []

        for s1, s2 in combinations(source_sets.keys(), 2):
            set1, set2 = source_sets[s1], source_sets[s2]
            n1, n2 = len(set1), len(set2)
            m = len(set1 & set2)

            if m < 1:
                continue  # no overlap → estimator undefined

            # Chapman estimator
            N_hat = ((n1 + 1) * (n2 + 1) / (m + 1)) - 1
            variance = ((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m)) / (((m + 1) ** 2) * (m + 2))
            ci_half = 1.96 * math.sqrt(max(variance, 0))

            pairwise.append({
                "sources": [s1, s2],
                "n1": n1, "n2": n2, "overlap": m,
                "estimate": round(N_hat),
                "ci_low": round(max(observed_total, N_hat - ci_half)),
                "ci_high": round(N_hat + ci_half),
            })

        # Best estimate: median across pairs (robust to outliers)
        if pairwise:
            median_est = float(np.median([p["estimate"] for p in pairwise]))
            final_est = max(observed_total, median_est)
        else:
            final_est = float(observed_total)

        dark = max(0, round(final_est - observed_total))
        visibility = round(100.0 * observed_total / final_est, 1) if final_est > 0 else 100.0

        return {
            "observed": observed_total,
            "estimated_total": round(final_est),
            "dark_number": dark,
            "visibility_pct": visibility,
            "source_sets": {k: len(v) for k, v in source_sets.items()},
            "pairwise_estimates": pairwise,
            "interpretation": (
                f"We observe {observed_total} entities across all sources. "
                f"Statistical capture-recapture suggests the true network size is ~{round(final_est)}. "
                f"An estimated {dark} individuals ({100 - visibility:.1f}% of the network) "
                f"remain undetected across all current intelligence channels."
            ),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 2. GHOST NODE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class GhostNodeEngine:
    """
    Infers unobserved criminal intermediaries — handlers, cutouts, coordinators —
    who deliberately avoid direct contact with each other while sharing the same
    criminal environment.

    Detection logic:
    - Within each community, find pairs (A, B) with NO direct edge.
    - Compute Jaccard similarity on neighbor sets.
    - Flag pairs above a threshold as likely connected via an unobserved intermediary.
    - Rank by confidence score and cross-weight with suspicion scores.

    Why this works: In law enforcement intelligence (e.g., COINTELPRO, DEA cell models),
    professional criminals deliberately avoid direct contact with distant hierarchy members.
    A shared social footprint without a direct call record is the signature of a handler
    relationship or a cutout.
    """

    def __init__(self, similarity_threshold: float = 0.55, min_shared_neighbors: int = 2):
        self.threshold = similarity_threshold
        self.min_shared = min_shared_neighbors

    def detect(
        self,
        P: nx.Graph,
        community: dict[str, int],
        susp: dict[str, dict],
        top: int = 15,
    ) -> list[dict]:
        """Return the most suspicious unobserved links in the actor projection."""
        groups: dict[int, list[str]] = defaultdict(list)
        for n, c in community.items():
            groups[c].append(n)

        alerts: list[dict] = []

        for cid, members in groups.items():
            # Only scan communities with meaningful criminal suspicion
            mean_susp = float(np.mean([susp.get(m, {}).get("score", 0) for m in members])) if members else 0.0
            if mean_susp < 0.1 and len(members) < 4:
                continue

            for a, b in combinations(members, 2):
                if P.has_edge(a, b):
                    continue
                if a not in P or b not in P:
                    continue

                nbrs_a = set(P.neighbors(a))
                nbrs_b = set(P.neighbors(b))
                shared = nbrs_a & nbrs_b

                if len(shared) < self.min_shared:
                    continue

                union = nbrs_a | nbrs_b
                jaccard = len(shared) / len(union) if union else 0.0

                if jaccard < self.threshold:
                    continue

                # Boost score by combined suspicion
                susp_a = susp.get(a, {}).get("score", 0)
                susp_b = susp.get(b, {}).get("score", 0)
                confidence = round(min(1.0, jaccard * (1 + 0.5 * (susp_a + susp_b))), 3)

                shared_labels = [P.nodes[n]["label"] for n in sorted(shared, key=lambda x: -susp.get(x, {}).get("score", 0))[:4]]
                alerts.append({
                    "type": "GHOST_NODE",
                    "node_a": {"id": a, "label": P.nodes[a]["label"], "suspicion": susp_a},
                    "node_b": {"id": b, "label": P.nodes[b]["label"], "suspicion": susp_b},
                    "community": cid,
                    "confidence_score": confidence,
                    "jaccard_similarity": round(jaccard, 3),
                    "shared_neighbors_count": len(shared),
                    "shared_neighbors": shared_labels,
                    "interpretation": (
                        f"{P.nodes[a]['label']} and {P.nodes[b]['label']} share {len(shared)} "
                        f"mutual associate(s) ({', '.join(shared_labels[:3])}) but have zero "
                        f"direct recorded contact. This structural pattern suggests deliberate "
                        f"compartmentalisation via an unobserved intermediary (handler / cutout)."
                    ),
                })

        alerts.sort(key=lambda x: -x["confidence_score"])
        return alerts[:top]

    def as_alerts(self, ghost_nodes: list[dict]) -> list[dict]:
        """Convert ghost node detections into the standard Alert format."""
        out = []
        for g in ghost_nodes:
            score = g["confidence_score"]
            out.append(_alert(
                kind="GHOST_NODE",
                title=f"Unobserved link: {g['node_a']['label']} ↔ {g['node_b']['label']}",
                description=g["interpretation"],
                score=score,
                entity_ids=[g["node_a"]["id"], g["node_b"]["id"]],
                evidence={
                    "jaccard_similarity": g["jaccard_similarity"],
                    "shared_neighbors": g["shared_neighbors"],
                    "shared_count": g["shared_neighbors_count"],
                    "community": g["community"],
                },
            ))
        return out


# ══════════════════════════════════════════════════════════════════════════════
# 3. FIRST-TIME OFFENDER RISK ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class FirstTimeOffenderEngine:
    """
    Flags individuals with NO prior criminal record who are structurally embedded
    within known criminal networks — the 'clean hands' problem.

    This mirrors the approach used in Palantir Gotham's 'proximity scoring' and
    in academic research on co-offending networks (Papachristos et al., 2013):
    the single strongest predictor of future criminal involvement is network
    proximity to existing offenders, not individual history.

    Scoring factors:
    - proximity_score: weighted average suspicion of direct neighbours
    - exposure_depth: how many 'hops' to the nearest high-suspicion node
    - community_risk: mean suspicion of the community they belong to
    - contact_quality: are their direct contacts accused/watchlisted?
    - channel_diversity: do they connect via calls, transfers AND meetings?

    Only surfaces individuals who are NOT already flagged as suspects (suspicion < 0.2)
    to avoid duplicating existing alerts.
    """

    def detect(
        self,
        P: nx.Graph,
        susp: dict[str, dict],
        community: dict[str, int],
        metrics: dict[str, dict],
        top: int = 20,
    ) -> list[dict]:
        """Return the highest-risk first-time-offenders in the projection."""
        # Build community risk map
        comm_members: dict[int, list[str]] = defaultdict(list)
        for n, c in community.items():
            comm_members[c].append(n)
        comm_risk: dict[int, float] = {
            c: float(np.mean([susp.get(m, {}).get("score", 0) for m in members]))
            for c, members in comm_members.items()
        }

        results: list[dict] = []
        
        def proximity_risk(hop_distance: int, edge_weights_by_channel: dict[str, float], flagged_severity: float) -> float:
            decay = {1: 1.0, 2: 0.3, 3: 0.09}.get(hop_distance, 0)
            if decay == 0:
                return 0.0
            # channel amplification: independent channels multiply, not add
            channel_factor = 1.0
            for channel, weight in edge_weights_by_channel.items():
                channel_factor *= (1 + weight)
            channel_factor = min(channel_factor, 3.0)  # Cap channel factor at 3.0
            return decay * flagged_severity * channel_factor

        for n in P.nodes():
            node = P.nodes[n]
            if node.get("type") != "PERSON":
                continue

            from .quality import is_protected_party
            if is_protected_party(node.get("type", ""), node.get("label", ""), node.get("attrs") or {}):
                continue

            s = susp.get(n, {})
            if s.get("protected"):
                continue
            # Only flag "clean" individuals
            if s.get("score", 0) >= 0.2 or s.get("accused", 0) > 0 or s.get("watchlist"):
                continue

            # BFS out to 3 hops to compute proximity score
            proximity_score = 0.0
            visited = {n}
            queue = [(n, 0, 1.0)]  # (node, hops, cumulative_path_multiplier)
            
            # Simple BFS to aggregate risk from nearby flagged nodes
            for hop in range(1, 4):
                next_queue = []
                for current_node, current_hops, _ in queue:
                    for nb in P.neighbors(current_node):
                        if nb not in visited:
                            visited.add(nb)
                            # Get edge channels and weights
                            edge_data = P[current_node][nb]
                            channels = edge_data.get("channels", {"unknown": 1.0})
                            # Weights: in this simple model we just use 0.5 per channel if not explicitly set
                            weights = {k: 0.5 for k in channels}
                            
                            nb_susp = susp.get(nb, {}).get("score", 0)
                            if nb_susp > 0.2:
                                risk = proximity_risk(hop, weights, nb_susp)
                                proximity_score = max(proximity_score, risk)  # Take highest risk path
                            
                            next_queue.append((nb, hop, 1.0))
                queue = next_queue
            
            proximity_score = min(1.0, proximity_score)

            # Contact quality: count high-risk neighbours (direct)
            neighbors = list(P.neighbors(n))
            hq_contacts = [nb for nb in neighbors if susp.get(nb, {}).get("score", 0) >= 0.35]
            accused_contacts = [nb for nb in neighbors if susp.get(nb, {}).get("accused", 0) > 0]
            watchlisted_contacts = [nb for nb in neighbors if susp.get(nb, {}).get("watchlist")]

            # Community risk
            c_id = community.get(n, -1)
            c_risk = comm_risk.get(c_id, 0.0)

            # Channel diversity for direct neighbors
            edge_channels = set()
            for nb in neighbors:
                if P.has_edge(n, nb):
                    edge_channels.update(P[n][nb].get("channels", {}).keys())
            channel_diversity = len(edge_channels) / 5.0  # normalise to 5 known types

            # Final composite risk score (adjusted to rely heavily on the new proximity_score)
            risk = round(min(1.0,
                0.60 * proximity_score
                + 0.20 * c_risk
                + 0.10 * min(len(hq_contacts) / max(len(neighbors), 1), 1.0)
                + 0.10 * channel_diversity
            ), 3)

            if risk < 0.15:
                continue

            reasons = []
            if accused_contacts:
                reasons.append(f"directly connected to {len(accused_contacts)} accused individual(s)")
            if watchlisted_contacts:
                reasons.append(f"directly connected to {len(watchlisted_contacts)} watchlisted individual(s)")
            if c_risk >= 0.25:
                reasons.append(f"embedded in a high-risk community (avg suspicion {c_risk:.2f})")
            if len(edge_channels) >= 3:
                reasons.append(f"interacts via {len(edge_channels)} channel types: {', '.join(sorted(edge_channels))}")

            results.append({
                "id": n,
                "label": node["label"],
                "type": "FIRST_TIME_OFFENDER_RISK",
                "risk_score": risk,
                "suspicion_score": s.get("score", 0),
                "proximity_score": round(proximity_score, 3),
                "community_risk": round(c_risk, 3),
                "degree": len(neighbors),
                "high_risk_contacts": len(hq_contacts),
                "accused_contacts": len(accused_contacts),
                "watchlisted_contacts": len(watchlisted_contacts),
                "channel_types": sorted(edge_channels),
                "reasons": reasons,
                "community": c_id,
                "interpretation": (
                    f"{node['label']} has NO prior criminal record but carries a proximity risk "
                    f"score of {risk:.2f}. They are directly connected to {len(hq_contacts)} "
                    f"high-suspicion individual(s) within community {c_id}. "
                    + (" ".join(reasons) if reasons else "")
                ),
            })

        results.sort(key=lambda x: -x["risk_score"])
        return results[:top]

    def as_alerts(self, fto_results: list[dict]) -> list[dict]:
        """Convert FTO detections into the standard Alert format."""
        out = []
        for r in fto_results:
            out.append(_alert(
                kind="FIRST_TIME_OFFENDER_RISK",
                title=f"Clean-record individual in criminal network: {r['label']}",
                description=r["interpretation"],
                score=r["risk_score"],
                entity_ids=[r["id"]],
                evidence={
                    "proximity_score": r["proximity_score"],
                    "community_risk": r["community_risk"],
                    "high_risk_contacts": r["high_risk_contacts"],
                    "accused_contacts": r["accused_contacts"],
                    "watchlisted_contacts": r["watchlisted_contacts"],
                    "channel_types": r["channel_types"],
                },
            ))
        return out


# ══════════════════════════════════════════════════════════════════════════════
# 4. ORCHESTRATION: run_novelty()
# ══════════════════════════════════════════════════════════════════════════════

def run_novelty(
    G: nx.Graph,
    D: nx.DiGraph,
    analytics_snapshot: dict[str, Any],
    top_ghost: int = 15,
    top_fto: int = 20,
) -> dict[str, Any]:
    """
    Top-level entry point. Call after run_all() in analytics.py.
    Returns all three novel analysis outputs in a single dict.
    """
    P_metrics = analytics_snapshot.get("metrics", {})
    community = analytics_snapshot.get("community", {})
    susp = analytics_snapshot.get("suspicion", {})

    # Reconstruct actor projection from the snapshot edges
    P = nx.Graph()
    for n, data in G.nodes(data=True):
        if data.get("type") in ("PERSON", "ORGANIZATION"):
            P.add_node(n, **data)
    for edge in analytics_snapshot.get("projection_edges", []):
        u, v = edge["source"], edge["target"]
        if u in P and v in P:
            P.add_edge(u, v, **{k: v2 for k, v2 in edge.items() if k not in ("source", "target")})

    # 1. Iceberg
    iceberg = IcebergEstimator().estimate(D)

    # 2. Ghost Nodes
    ghost_engine = GhostNodeEngine()
    ghost_nodes = ghost_engine.detect(P, community, susp, top=top_ghost)
    ghost_alerts = ghost_engine.as_alerts(ghost_nodes)

    # 3. First-Time Offender Risk
    fto_engine = FirstTimeOffenderEngine()
    fto_results = fto_engine.detect(P, susp, community, P_metrics, top=top_fto)
    fto_alerts = fto_engine.as_alerts(fto_results)

    # 4. Source Discrepancies
    discrepancy_results = run_discrepancy_detection(D)
    discrepancy_alerts = discrepancy_results["alerts"]

    all_alerts = ghost_alerts + fto_alerts + discrepancy_alerts
    all_alerts.sort(key=lambda x: -x["score"])

    return {
        "iceberg": iceberg,
        "ghost_nodes": ghost_nodes,
        "first_time_offenders": fto_results,
        "discrepancies": discrepancy_results,
        "alerts": all_alerts,
        "summary": {
            "ghost_nodes_detected": len(ghost_nodes),
            "first_time_offenders_flagged": len(fto_results),
            "discrepancies_detected": len(discrepancy_alerts),
            "estimated_dark_network_size": iceberg.get("dark_number", 0),
            "visibility_pct": iceberg.get("visibility_pct", 100.0),
            "critical_alerts": sum(1 for a in all_alerts if a["severity"] == "critical"),
            "high_alerts": sum(1 for a in all_alerts if a["severity"] == "high"),
        },
    }
