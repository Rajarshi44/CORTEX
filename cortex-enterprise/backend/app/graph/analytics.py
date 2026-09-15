"""
Graph analytics: who matters, who brokers, who belongs together, who is probably linked.

The ingested graph is heterogeneous (persons, phones, accounts, vehicles, cases, ...). Raw
centrality on it is dominated by infrastructure nodes, so we first build an *actor projection*
(PERSON / ORGANIZATION) where two actors are linked if they talked (via their phones), moved
money (via their accounts), met (surveillance), were co-accused, or were mentioned together.
Every projected edge keeps its channel breakdown so the UI can explain *why* two people are linked.

Scores:
  influence  - purely structural (PageRank, eigenvector, betweenness, weighted degree)
  suspicion  - evidentiary (named accused, surveillance subject, intel mentions, unverified identity,
               international contacts, anomaly involvement)
  priority   - fusion of both; this is what investigators triage on. Popular but innocent people
               have influence without suspicion; they do not surface as key players.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

import networkx as nx
import numpy as np

from ..ingestion.quality import is_non_subject
from . import fastmetrics

ACTOR_TYPES = {"PERSON", "ORGANIZATION"}
PROXY_OWNERSHIP = {"USES_PHONE", "OWNS_ACCOUNT", "OWNS_HANDLE", "ASSOCIATED_VEHICLE"}
DIRECT_WEIGHTS = {
    "MET": 2.0, "CO_ACCUSED": 3.0, "REPORTS_TO": 3.0, "COMMUNICATED_WITH": 1.5, "MENTIONED_WITH": 0.5,
    "OWNS": 2.0, "DIRECTOR_OF": 2.0, "AFFILIATED_WITH": 1.0, "ASSOCIATE_OF": 2.0,
}
ROLE_LABELS = {
    "leader": "Leader (insulated)", "coordinator": "Coordinator / Hub", "broker": "Broker / Bridge",
    "financial": "Financial conduit", "operative": "Operative", "peripheral": "Peripheral",
    "unverified": "Unverified identity", "mule": "Money mule", "connector": "Well-connected (no adverse record)",
}


def _norm(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    vals = np.array(list(d.values()), dtype=float)
    lo, hi = vals.min(), vals.max()
    if hi - lo < 1e-12:
        return {k: 0.0 for k in d}
    return {k: float((v - lo) / (hi - lo)) for k, v in d.items()}


def _is_bank(data: dict) -> bool:
    return data["type"] == "ORGANIZATION" and re.search(r"\bbank\b", data["label"], re.I) is not None


# ----------------------------------------------------------------------------- projection
def actor_projection(D: nx.DiGraph) -> nx.Graph:
    """Collapse proxy nodes (phones, accounts, handles, vehicles) onto their owners."""
    owner: dict[str, list[str]] = defaultdict(list)
    for u, v, data in D.edges(data=True):
        if data["rel_type"] in PROXY_OWNERSHIP and D.nodes[u]["type"] in ACTOR_TYPES:
            owner[v].append(u)
    P = nx.Graph()
    for n, data in D.nodes(data=True):
        if data["type"] in ACTOR_TYPES and not _is_bank(data):
            P.add_node(n, **data)

    def bump(a: str, b: str, w: float, channel: str, extra: dict | None = None):
        if a == b or a not in P or b not in P:
            return
        if not P.has_edge(a, b):
            P.add_edge(a, b, weight=0.0, channels=Counter(), calls=0, night_calls=0, amount=0.0, meetings=0, cases=0, mentions=0)
        e = P[a][b]
        e["weight"] += w
        e["channels"][channel] += 1
        for k, v in (extra or {}).items():
            e[k] = e.get(k, 0) + v

    for u, v, data in D.edges(data=True):
        rt = data["rel_type"]
        if rt == "CALLED":
            for a in owner.get(u, []):
                for b in owner.get(v, []):
                    bump(a, b, math.sqrt(data["count"]), "calls", {"calls": data["count"], "night_calls": data["attrs"].get("night_calls", 0)})
        elif rt == "TRANSFERRED_TO":
            amt = float(data["attrs"].get("total_amount", 0.0))
            for a in owner.get(u, []):
                for b in owner.get(v, []):
                    bump(a, b, math.log10(max(amt, 10.0)) * math.sqrt(data["count"]) / 2, "transfers", {"amount": amt})
        elif rt == "MENTIONED":
            for a in owner.get(u, []):
                for b in owner.get(v, []):
                    bump(a, b, 1.0, "social", {"mentions": data["count"]})
        elif rt == "SHARED_HANDSET":
            for a in owner.get(u, []):
                for b in owner.get(v, []):
                    bump(a, b, 4.0, "shared_handset")
        elif rt in DIRECT_WEIGHTS and D.nodes[u]["type"] in ACTOR_TYPES and D.nodes[v]["type"] in ACTOR_TYPES:
            ch = "meetings" if rt == "MET" else "cases" if rt == "CO_ACCUSED" else "mentions" if rt == "MENTIONED_WITH" else "ties"
            bump(u, v, DIRECT_WEIGHTS[rt] * data["count"], rt.lower(), {ch: data["count"]} if ch in ("meetings", "cases", "mentions") else None)
    # Parties to the same matter are connected in the record, whichever side they were on. Only
    # ACCUSED_IN / MENTIONED_IN counted before, which left a corpus of court judgments - where the
    # parties are petitioners and respondents - almost entirely unprojected.
    CASE_PARTY = {"ACCUSED_IN", "MENTIONED_IN", "PETITIONER_IN", "RESPONDENT_IN", "COMPLAINANT_IN"}
    case_members: dict[str, set[str]] = defaultdict(set)
    for u, v, data in D.edges(data=True):
        if data["rel_type"] in CASE_PARTY and D.nodes[v]["type"] == "CASE" and D.nodes[u]["type"] in ACTOR_TYPES:
            # The State is a party to every criminal matter; linking co-parties through it would
            # join thousands of unrelated people into one clique - the same false hub that an ISO
            # country code used as an address created.
            if is_non_subject(D.nodes[u]["type"], D.nodes[u]["label"], D.nodes[u].get("attrs") or {}):
                continue
            case_members[v].add(u)
    for members in case_members.values():
        ms = sorted(members)
        if len(ms) > 30:  # a case with a cast this large is a listing, not an association
            continue
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                bump(ms[i], ms[j], 1.0, "shared_case", {"cases": 1})
    for _, _, e in P.edges(data=True):
        e["channels"] = dict(e["channels"])
    return P


# ----------------------------------------------------------------------------- suspicion
def suspicion_signals(D: nx.DiGraph, anomaly_hits: dict[str, float] | None = None) -> dict[str, dict]:
    """Evidence-based signals per actor, independent of graph structure."""
    sig: dict[str, dict] = defaultdict(lambda: {"accused": 0, "surveillance": 0, "intel": 0, "unverified": 0,
                                                "international": 0, "anomaly": 0.0, "complainant": 0, "org_flag": None,
                                                "watchlist": None, "wanted": 0, "convicted": 0, "offshore": 0,
                                                "press": 0})
    # public-record signals carried on the entity itself (watchlists, wanted notices, leaks)
    for n, a in D.nodes(data=True):
        at = a.get("attrs") or {}
        # The machinery of a case is not a subject of it: the judge who decided it, the State it was
        # brought against, the court or agency that handled it. None of them carry suspicion.
        if is_non_subject(a.get("type", ""), a.get("label", ""), at):
            continue
        if at.get("watchlist"):
            topics = at.get("watchlist_topics") or []
            if at.get("screened_match"):
                sig[n]["watchlist"] = "screened" if at.get("screen_strength") == "strong" else "weak"
            else:
                sig[n]["watchlist"] = "wanted" if any(t in ("wanted", "crime", "sanction") for t in topics) else "listed"
        if at.get("wanted_notice"):
            sig[n]["wanted"] += 1
        if at.get("source") == "ICIJ" and at.get("icij_type") == "officer":
            sig[n]["offshore"] += 1
    for u, v, d in D.edges(data=True):
        rt, tu, tv = d["rel_type"], D.nodes[u]["type"], D.nodes[v]["type"]
        if rt == "ACCUSED_IN":
            sig[u]["accused"] += 1
        elif rt == "WANTED_IN":
            sig[u]["wanted"] += 1
        elif rt == "PETITIONER_IN" and tv == "CASE" and (D.nodes[v]["attrs"] or {}).get("criminal"):
            sig[u]["convicted"] += 1
        elif rt == "COMPLAINANT_IN":
            sig[u]["complainant"] += 1
        elif rt == "SUBJECT_OF" and tv == "REPORT":
            sig[u]["surveillance"] += 1
        elif rt == "MENTIONED_IN" and tv == "REPORT" and "Surveillance" not in D.nodes[v]["label"]:
            # An intelligence report names a subject; a newspaper names whoever the story is about,
            # including victims, lawyers, ministers and film stars. Treating the two alike put
            # Bollywood actors on the sheet as coordinators. Press coverage is context, not adverse
            # record, so it carries no suspicion of its own.
            if (D.nodes[v]["attrs"] or {}).get("source_type") == "NEWS":
                sig[u]["press"] += 1
            else:
                sig[u]["intel"] += 1
        elif rt == "USES_PHONE":
            if d["attrs"].get("kyc_status") == "unverified" or D.nodes[v]["attrs"].get("kyc_status") == "unverified":
                sig[u]["unverified"] += 1
            # international contacts through this phone
            for _, w, dd in D.out_edges(v, data=True):
                if dd["rel_type"] == "CALLED" and D.nodes[w]["attrs"].get("international"):
                    sig[u]["international"] += dd["count"]
            for w, _, dd in D.in_edges(v, data=True):
                if dd["rel_type"] == "CALLED" and D.nodes[w]["attrs"].get("international"):
                    sig[u]["international"] += dd["count"]
    for n, s in (anomaly_hits or {}).items():
        sig[n]["anomaly"] = max(sig[n]["anomaly"], float(s))
    # organisations are fronts: anomalies on a company reflect on its owner / director
    for u, v, d in D.edges(data=True):
        if d["rel_type"] in ("OWNS", "DIRECTOR_OF", "AFFILIATED_WITH") and D.nodes[v]["type"] == "ORGANIZATION" and v in sig:
            sig[u]["anomaly"] = max(sig[u]["anomaly"], 0.8 * sig[v]["anomaly"])
            sig[u]["org_flag"] = D.nodes[v]["label"]
    out = {}
    for n, s in sig.items():
        score = min(1.0, 0.35 * min(s["accused"], 2) + 0.15 * min(s["surveillance"], 2) + 0.2 * min(s["intel"], 2)
                    + 0.25 * min(s["unverified"], 1) + 0.15 * (1 if s["international"] else 0) + 0.3 * s["anomaly"]
                    + (0.6 if s["watchlist"] == "wanted" else 0.45 if s["watchlist"] == "screened" else 0.12 if s["watchlist"] == "weak" else 0.18 if s["watchlist"] else 0)
                    + 0.5 * min(s["wanted"], 1) + 0.2 * min(s["convicted"], 2) + 0.1 * min(s["offshore"], 1))
        reasons = []
        if s["accused"]:
            reasons.append(f"named accused in {s['accused']} FIR(s) or criminal case(s)")
        if s["watchlist"] == "wanted":
            reasons.append("on a crime or wanted watchlist (OpenSanctions / INTERPOL)")
        elif s["watchlist"] == "screened":
            reasons.append("name screens against a criminal-interest watchlist")
        elif s["watchlist"] == "weak":
            reasons.append("common name also found on a watchlist (unverified lead)")
        elif s["watchlist"]:
            reasons.append("appears on a public watchlist")
        if s["wanted"]:
            reasons.append(f"named in {s['wanted']} police wanted notice(s)")
        if s["convicted"]:
            reasons.append(f"petitioner in {s['convicted']} criminal matter(s)")
        if s["offshore"]:
            reasons.append("officer of offshore entities in ICIJ leaks")
        if s["surveillance"]:
            reasons.append(f"subject of {s['surveillance']} surveillance report(s)")
        if s["intel"]:
            reasons.append(f"named in {s['intel']} intelligence report(s)")
        if s["press"] and not any((s["accused"], s["intel"], s["watchlist"], s["wanted"])):
            reasons.append(f"named in {s['press']} press report(s) - context only, not an adverse record")
        if s["unverified"]:
            reasons.append("uses phone with unverified KYC")
        if s["international"]:
            reasons.append(f"{s['international']} international call(s)")
        if s["anomaly"]:
            reasons.append("involved in detected anomalies" + (f" via {s['org_flag']}" if s.get("org_flag") else ""))
        out[n] = {"score": round(score, 3), "reasons": reasons, **s}
    return out


# ----------------------------------------------------------------------------- metrics
def compute_metrics(P: nx.Graph) -> dict[str, dict[str, float]]:
    """Centralities, Rust-accelerated where rustworkx is available (see graph/fastmetrics.py)."""
    if P.number_of_nodes() == 0:
        return {}
    deg = dict(P.degree())
    wdeg = dict(P.degree(weight="weight"))
    btw = fastmetrics.betweenness(P)
    pr = fastmetrics.pagerank(P)
    eig = fastmetrics.eigenvector(P)
    clo = fastmetrics.closeness(P)
    clu = nx.clustering(P, weight="weight")
    n_w, n_b, n_pr, n_e = _norm(wdeg), _norm(btw), _norm(pr), _norm(eig)
    metrics: dict[str, dict[str, float]] = {}
    for n in P:
        metrics[n] = {
            "degree": deg[n], "weighted_degree": round(wdeg[n], 2), "betweenness": round(btw.get(n, 0.0), 5),
            "pagerank": round(pr.get(n, 0.0), 5), "eigenvector": round(eig.get(n, 0.0), 5),
            "closeness": round(clo.get(n, 0.0), 4), "clustering": round(clu.get(n, 0.0), 4),
            "influence": round(0.35 * n_pr[n] + 0.25 * n_e[n] + 0.25 * n_b[n] + 0.15 * n_w[n], 4),
        }
    return metrics


def detect_communities(P: nx.Graph, seed: int = 42) -> dict[str, int]:
    if P.number_of_edges() == 0:
        return {n: i for i, n in enumerate(P)}
    comms = nx.community.louvain_communities(P, weight="weight", seed=seed, resolution=1.0)
    comms = sorted(comms, key=len, reverse=True)
    return {n: i for i, c in enumerate(comms) for n in c}


def classify_roles(P: nx.Graph, metrics: dict, community: dict[str, int], D: nx.DiGraph, susp: dict) -> dict[str, dict]:
    """Explainable role assignment on the actor projection.

    Structural roles are only assigned to persons of interest (suspicion >= 0.2); well-connected people
    with no adverse record are labelled as such instead of being called 'leaders'. Leaders are detected
    per community: high eigenvector centrality *inside* the community with comparatively few direct
    ties (the insulation pattern typical of organised-crime principals).
    """
    if not metrics:
        return {}
    keys = ("degree", "betweenness", "pagerank", "eigenvector", "weighted_degree")
    arr = {k: np.array([m[k] for m in metrics.values()]) for k in keys}
    pct = lambda k, q: float(np.percentile(arr[k], q))  # noqa: E731
    leaders: dict[str, list[str]] = {}
    groups: dict[int, list[str]] = defaultdict(list)
    for n, c in community.items():
        groups[c].append(n)
    # large inbound funds (>= 5 lakh) into a person's own accounts: principals get paid, operatives pay
    acct_owner = {v: u for u, v, d in D.edges(data=True) if d["rel_type"] == "OWNS_ACCOUNT"}
    inbound: dict[str, float] = defaultdict(float)
    for u, v, d in D.edges(data=True):
        if d["rel_type"] == "TRANSFERRED_TO" and v in acct_owner:
            inbound[acct_owner[v]] += float(d["attrs"].get("total_amount", 0))
    recv_large = {n for n, amt in inbound.items() if amt >= 500_000}
    for cid, members in groups.items():
        poi = [m for m in members if susp.get(m, {}).get("score", 0) >= 0.2]
        mean_susp = float(np.mean([susp.get(m, {}).get("score", 0) for m in members])) if members else 0.0
        if len(members) < 5 or len(poi) < 3 or mean_susp < 0.2:
            continue
        sub = P.subgraph(members)
        try:
            eig = nx.eigenvector_centrality_numpy(sub, weight="weight") if sub.number_of_edges() else {}
        except Exception:
            eig = {}
        if not eig:
            continue
        deg = dict(sub.degree())
        e_n, d_n = _norm({m: abs(eig.get(m, 0)) for m in members}), _norm(deg)
        def lscore(m: str) -> float:
            s = susp.get(m, {})
            bonus = 1.0 + (0.5 if s.get("international") else 0.0) + (0.3 if m in recv_large else 0.0)
            return e_n[m] * (1.0 - 0.7 * d_n[m]) * (0.5 + s.get("score", 0)) * bonus
        scored = sorted(((lscore(m), m) for m in poi if P.nodes[m]["type"] == "PERSON"), reverse=True)
        if scored:
            top_score = scored[0][0]
            for sc, m in scored[:2]:
                if sc > 0 and sc >= 0.9 * top_score:
                    why = [f"highest eigenvector centrality inside community {cid} relative to direct ties (insulation pattern)"]
                    if susp.get(m, {}).get("international"):
                        why.append("maintains international contact")
                    if m in recv_large:
                        why.append(f"receives large inbound funds (₹{inbound[m]:,.0f})")
                    leaders[m] = why
    roles: dict[str, dict] = {}
    for n, m in metrics.items():
        node = P.nodes[n]
        nb = list(P.neighbors(n))
        spans = len({community.get(x) for x in nb} - {community.get(n)})
        s = susp.get(n, {})
        poi = s.get("score", 0) >= 0.2
        big_in = sum(1 for x in nb if P[n][x].get("amount", 0) > 200_000)
        role, reasons = "peripheral", []
        if poi and (m["degree"] >= pct("degree", 75) or s.get("accused") or m["betweenness"] >= pct("betweenness", 75)):
            role, reasons = "operative", [f"{m['degree']} direct associates"]
        if poi and m["degree"] >= pct("degree", 90) and m["pagerank"] >= pct("pagerank", 85):
            role, reasons = "coordinator", [f"top-10% degree ({m['degree']} direct ties)", "high PageRank"]
        if poi and spans >= 2 and m["betweenness"] >= pct("betweenness", 85):
            role, reasons = "broker", [f"bridges {spans + 1} communities", f"betweenness {m['betweenness']:.3f} (top 15%)"]
        if n in leaders:
            role, reasons = "leader", leaders[n]
        if node["type"] == "ORGANIZATION" and big_in >= 1:
            role, reasons = "financial", [f"receives large transfers from {big_in} counterpart(ies)"]
        if node["type"] == "PERSON" and node["attrs"].get("kyc_unverified"):
            role, reasons = "unverified", ["identity behind this phone could not be verified (possible burner)"]
        if not poi and role == "peripheral" and m["degree"] >= pct("degree", 90):
            role, reasons = "connector", [f"{m['degree']} direct ties but no adverse record"]
        if s.get("accused"):
            reasons.append(f"named accused in {s['accused']} FIR(s) or criminal case(s)")
        roles[n] = {"role": role, "label": ROLE_LABELS[role], "reasons": reasons, "community_span": spans + 1,
                    "accused_count": s.get("accused", 0)}
    return roles


def priority_scores(metrics: dict, susp: dict) -> dict[str, float]:
    return {n: round(0.55 * m["influence"] + 0.45 * susp.get(n, {}).get("score", 0.0), 4) for n, m in metrics.items()}


def link_predictions(P: nx.Graph, metrics: dict, susp: dict, top: int = 20) -> list[dict]:
    if P.number_of_edges() == 0:
        return []
    interesting = {n for n, s in susp.items() if s["score"] >= 0.2 and n in P}
    cand = set()
    for n in interesting:
        for nb in P.neighbors(n):
            for nb2 in P.neighbors(nb):
                if nb2 != n and not P.has_edge(n, nb2) and P.nodes[nb2]["type"] == "PERSON":
                    cand.add(tuple(sorted((n, nb2))))
    if not cand:
        return []
    scored = []
    for u, v, s in nx.adamic_adar_index(P, list(cand)):
        cn = sorted(nx.common_neighbors(P, u, v), key=lambda x: -metrics.get(x, {}).get("influence", 0))
        jac = len(cn) / max(len(set(P.neighbors(u)) | set(P.neighbors(v))), 1)
        boost = 1 + susp.get(u, {}).get("score", 0) + susp.get(v, {}).get("score", 0)
        scored.append({"source": u, "target": v, "score": round(float(s) * boost, 3), "raw_score": round(float(s), 3),
                       "jaccard": round(jac, 3), "common_neighbors": cn[:5],
                       "source_label": P.nodes[u]["label"], "target_label": P.nodes[v]["label"],
                       "explanation": f"Share {len(cn)} associate(s): " + ", ".join(P.nodes[x]["label"] for x in cn[:3])})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top]


def removal_impact(P: nx.Graph, node: str, community: dict[str, int] | None = None) -> dict:
    if node not in P:
        return {}

    def pairs(G: nx.Graph) -> int:
        return sum(len(c) * (len(c) - 1) // 2 for c in nx.connected_components(G))

    comp = nx.node_connected_component(P, node)
    sub = P.subgraph(comp)
    sub_after = P.subgraph(comp - {node})
    glob = 1 - (pairs(sub_after) / pairs(sub)) if pairs(sub) else 0.0
    res = {"node": node, "label": P.nodes[node]["label"], "global_fragmentation": round(glob, 3),
           "components_before": nx.number_connected_components(P),
           "components_after": nx.number_connected_components(P.subgraph(set(P) - {node}))}
    if community is not None:
        members = {n for n, c in community.items() if c == community.get(node) and n in P}
        cs = P.subgraph(members)
        cs_after = P.subgraph(members - {node})
        res["community_fragmentation"] = round(1 - (pairs(cs_after) / pairs(cs)), 3) if pairs(cs) else 0.0
        res["community_components_after"] = nx.number_connected_components(cs_after) if cs_after.number_of_nodes() else 0
        res["isolated_after"] = [{"id": n, "label": P.nodes[n]["label"]} for n in members - {node} if cs_after.degree(n) == 0][:10]
        # weighted flow lost: share of community's edge weight touching this node
        tot = sum(d["weight"] for _, _, d in cs.edges(data=True))
        touch = sum(d["weight"] for _, _, d in cs.edges(node, data=True))
        res["flow_share"] = round(touch / tot, 3) if tot else 0.0
    return res


def summarize_communities(P: nx.Graph, D: nx.DiGraph, community: dict[str, int], metrics: dict, roles: dict,
                          priority: dict, susp: dict) -> list[dict]:
    groups: dict[int, list[str]] = defaultdict(list)
    for n, c in community.items():
        groups[c].append(n)
    locs: dict[str, Counter] = defaultdict(Counter)
    for u, v, d in D.edges(data=True):
        if d["rel_type"] in ("RESIDES_AT", "SEEN_AT") and D.nodes[v]["type"] == "LOCATION":
            locs[u][D.nodes[v]["label"]] += d["count"]
    out = []
    for cid, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ranked = sorted(members, key=lambda n: -priority.get(n, 0))
        top = ranked[0]
        loc_counter = Counter()
        for m in members:
            loc_counter.update(locs[m])
        n_accused = sum(susp.get(m, {}).get("accused", 0) for m in members)
        internal = P.subgraph(members)
        risk = float(np.mean([susp.get(m, {}).get("score", 0) for m in members])) if members else 0.0
        out.append({
            "id": cid, "size": len(members),
            "label": f"{P.nodes[top]['label']} network" if len(members) > 2 else P.nodes[top]["label"],
            "leader": top, "members": ranked,
            "top_members": [{"id": n, "label": P.nodes[n]["label"], "role": roles.get(n, {}).get("label"),
                             "priority": priority.get(n, 0)} for n in ranked[:6]],
            "locations": [l for l, _ in loc_counter.most_common(4)], "accused_count": n_accused,
            "internal_edges": internal.number_of_edges(),
            "density": round(nx.density(internal), 3) if len(members) > 1 else 0.0,
            "risk": round(risk, 3), "suspicious": len(members) >= 3 and (risk >= 0.2 or (risk >= 0.12 and n_accused >= 3)),
        })
    return out


def key_players(P: nx.Graph, metrics: dict, roles: dict, community: dict, priority: dict, susp: dict, top: int = 10) -> list[dict]:
    ranked = sorted(priority.items(), key=lambda kv: -kv[1])
    out = []
    # a name with no ties is a record, not a player; and a judge, the State or a court is the
    # machinery of the case rather than a player in it
    ranked = [(n, p) for n, p in ranked
              if metrics[n]["degree"] >= 0
              and not is_non_subject(P.nodes[n].get("type", ""), P.nodes[n].get("label", ""), P.nodes[n].get("attrs") or {})]
    for n, p in ranked[:top]:
        r = roles.get(n, {})
        s = susp.get(n, {})
        out.append({"id": n, "label": P.nodes[n]["label"], "type": P.nodes[n]["type"], "aliases": P.nodes[n].get("aliases", []),
                    "community": community.get(n), "role": r.get("label"), "priority": p, "suspicion": s.get("score", 0.0),
                    "reasons": list(dict.fromkeys(r.get("reasons", []) + s.get("reasons", []))), **metrics[n]})
    return out


def brokers(P: nx.Graph, metrics: dict, roles: dict, community: dict, susp: dict, top: int = 8) -> list[dict]:
    out = []
    for n, m in metrics.items():
        span = roles.get(n, {}).get("community_span", 1)
        if span >= 2 and m["betweenness"] > 0:
            nb_comms = Counter(community.get(x) for x in P.neighbors(n))
            out.append({"id": n, "label": P.nodes[n]["label"], "betweenness": m["betweenness"], "community_span": span,
                        "bridges": [{"community": c, "contacts": k} for c, k in nb_comms.most_common()],
                        "score": round(m["betweenness"] * span * (1 + susp.get(n, {}).get("score", 0)), 4)})
    out.sort(key=lambda x: -x["score"])
    return out[:top]


def full_graph_metrics(G: nx.Graph) -> dict[str, dict[str, float]]:
    if G.number_of_nodes() == 0:
        return {}
    deg = dict(G.degree())
    pr = nx.pagerank(G, weight="weight") if G.number_of_edges() else {n: 0 for n in G}
    return {n: {"degree": deg[n], "pagerank": round(pr[n], 6)} for n in G}


def run_all(G: nx.Graph, D: nx.DiGraph, anomaly_hits: dict[str, float] | None = None) -> dict[str, Any]:
    P = actor_projection(D)
    susp = suspicion_signals(D, anomaly_hits)
    metrics = compute_metrics(P)
    community = detect_communities(P)
    roles = classify_roles(P, metrics, community, D, susp)
    priority = priority_scores(metrics, susp)
    comms = summarize_communities(P, D, community, metrics, roles, priority, susp)
    kp = key_players(P, metrics, roles, community, priority, susp)
    br = brokers(P, metrics, roles, community, susp)
    lp = link_predictions(P, metrics, susp)
    impact = {n["id"]: removal_impact(P, n["id"], community) for n in kp[:6]}
    fm = full_graph_metrics(G)
    type_counts = Counter(d["type"] for _, d in G.nodes(data=True))
    rel_counts = Counter(d["rel_type"] for _, _, d in D.edges(data=True))
    summary = {
        "nodes": G.number_of_nodes(), "edges": D.number_of_edges(), "actors": P.number_of_nodes(), "actor_edges": P.number_of_edges(),
        "density": round(nx.density(P), 4) if P.number_of_nodes() > 1 else 0,
        "components": nx.number_connected_components(P) if P.number_of_nodes() else 0,
        "avg_clustering": round(nx.average_clustering(P, weight="weight"), 4) if P.number_of_nodes() > 1 else 0,
        "communities": len(comms), "suspicious_communities": sum(1 for c in comms if c["suspicious"]),
        "node_types": dict(type_counts), "relationship_types": dict(rel_counts),
        # Actors only. An account or a handset picks up a suspicion score from the anomaly it is
        # involved in, but it is not a person of interest, and counting it made the figure on the
        # overview disagree with the list of people underneath it.
        "persons_of_interest": sum(1 for n, s in susp.items() if n in P and s["score"] >= 0.2),
        "compute_backend": fastmetrics.backend(),
    }
    proj_edges = [{"source": u, "target": v, "weight": round(d["weight"], 2), "channels": d["channels"], "calls": d.get("calls", 0),
                   "night_calls": d.get("night_calls", 0), "amount": round(d.get("amount", 0.0), 2), "meetings": d.get("meetings", 0),
                   "cases": d.get("cases", 0)} for u, v, d in P.edges(data=True)]
    return {"summary": summary, "metrics": metrics, "community": community, "roles": roles, "communities": comms,
            "key_players": kp, "brokers": br, "link_predictions": lp, "removal_impact": impact, "full_metrics": fm,
            "projection_edges": proj_edges, "suspicion": {n: s for n, s in susp.items() if n in P}, "priority": priority}
