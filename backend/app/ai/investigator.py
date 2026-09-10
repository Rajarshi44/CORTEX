"""
Natural-language investigator assistant.

A deterministic intent router retrieves facts from the graph (paths, dossiers, alerts, money flows,
key players...). Those facts are always returned as structured data + node highlights for the UI;
the narrative is produced by templates and, when an API key is present, rewritten by Claude
grounded in exactly the same facts (no free-form hallucination surface).
"""
from __future__ import annotations

import re
from typing import Any

import networkx as nx
from sqlalchemy.orm import Session

from ..db import Alert
from ..graph import queries as Q
from . import llm

PLATE_RE = re.compile(r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4})\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\-\s]?)?([6-9]\d{9})(?!\d)|(?<!\d)\+?(971\d{9})(?!\d)")
STOP = {"who", "is", "the", "what", "tell", "me", "about", "show", "find", "how", "and", "between", "path", "connected", "connection",
        "to", "of", "with", "for", "in", "on", "at", "a", "an", "does", "did", "has", "have", "are", "any", "list", "give", "explain",
        "why", "which", "where", "when", "was", "were", "do", "from", "money", "calls", "call", "contacts", "associates", "network",
        "link", "links", "related", "relationship", "relationships", "suspicious", "anomalies", "alerts", "phone", "vehicle", "summary",
        "summarise", "summarize", "overview", "brief", "case", "key", "players", "player", "most", "influential", "leader", "kingpin",
        "community", "communities", "group", "cluster", "timeline", "chronology", "predict", "hidden", "likely", "transactions",
        "transfers", "flow", "fund", "funds", "burner", "night", "structuring", "layering", "international", "his", "her", "their",
        "vs", "versus", "&", "vehicles", "owns", "own", "uses", "use", "number", "numbers", "account", "accounts", "meet", "met",
        "seen", "location", "locations", "top", "role", "roles", "important", "person", "people", "everyone", "all"}


class Investigator:
    def __init__(self, db: Session, G: nx.Graph, D: nx.DiGraph, snapshot: dict):
        self.db, self.G, self.D, self.snap = db, G, D, snapshot

    # ------------------------------------------------------------------ entity spotting
    def _entities_in(self, q: str) -> list[str]:
        found: list[str] = []
        for m in PLATE_RE.finditer(q):
            n = Q.fuzzy_entity(self.G, m.group(1).upper().replace(" ", "").replace("-", ""), ("VEHICLE",), 60)
            key = re.sub(r"[\s\-]", "", m.group(1).upper())
            n = n or next((x for x, d in self.G.nodes(data=True) if d["type"] == "VEHICLE" and d["label"].replace(" ", "") == key), None)
            if n:
                found.append(n)
        for m in PHONE_RE.finditer(q):
            num = m.group(1) or m.group(2)
            n = next((x for x, d in self.G.nodes(data=True) if d["type"] == "PHONE" and d["label"].lstrip("+") == num), None)
            if n:
                found.append(n)
        # quoted names first, then capitalised runs, then leftover tokens
        cands = re.findall(r"[\"“']([^\"”']{3,40})[\"”']", q)
        cands += re.findall(r"\b([A-Z][a-z'\.]+(?:\s+[A-Z][a-z'\.]+){0,2})\b", q)
        low_tokens = [t for t in re.findall(r"[A-Za-z'@][A-Za-z'\.@]+", q) if t.lower() not in STOP]
        for i in range(len(low_tokens)):
            cands.append(low_tokens[i])
            if i + 1 < len(low_tokens):
                cands.append(low_tokens[i] + " " + low_tokens[i + 1])
        for c in cands:
            if c.lower() in STOP or len(c) < 3:
                continue
            n = Q.fuzzy_entity(self.G, c, ("PERSON", "ORGANIZATION", "LOCATION", "SOCIAL_HANDLE"), 86)
            if n and n not in found:
                found.append(n)
        return found

    def _lab(self, n: str) -> str:
        return self.G.nodes[n]["label"]

    # ------------------------------------------------------------------ intents
    def answer(self, question: str) -> dict[str, Any]:
        q = question.strip()
        ql = q.lower()
        ents = self._entities_in(q)
        if re.search(r"\b(path|connect|connection|link|linked|between|relation|related|how .* know)\b", ql) and len(ents) >= 2:
            return self._path(q, ents[0], ents[1])
        if re.search(r"\b(communit|cluster|faction|gang)\w*", ql) and not ents:
            return self._communities(q)
        if re.search(r"\b(burner|prepaid|unverified sim|fake sim)\b", ql):
            return self._alerts(q, kind="burner_phone", ents=ents)
        if re.search(r"\b(structur|cash deposit|under .*threshold|smurf)\w*", ql):
            return self._alerts(q, kind="structuring", ents=ents)
        if re.search(r"\b(layer|launder|hawala|shell)\w*", ql):
            return self._alerts(q, kind="layering", ents=ents)
        if re.search(r"\b(burst|coordinat|spike)\w*", ql):
            return self._alerts(q, kind="call_burst", ents=ents)
        if re.search(r"\b(anomal|suspicious|alert|red flag|unusual|outlier|pattern)\w*", ql):
            return self._alerts(q, ents=ents)
        if re.search(r"\b(money|fund|transaction|transfer|paid|payment|flow|financ|account)\w*", ql) and ents:
            return self._money(q, ents[0])
        if re.search(r"\b(call|phone|contact|talk|spoke|dial)\w*", ql) and ents and not re.search(r"\bwho is\b", ql):
            return self._calls(q, ents[0])
        if re.search(r"\b(timeline|chronolog|when|history|activity)\w*", ql) and ents:
            return self._timeline(q, ents[0])
        if re.search(r"\b(key player|influential|kingpin|leader|most important|top |ringleader|mastermind|who runs|head of)", ql):
            return self._key_players(q)
        if re.search(r"\b(broker|bridge|intermediar|middleman|go-between|connects .* group)", ql):
            return self._brokers(q)
        if re.search(r"\b(communit|group|cluster|gang|cell|faction)\w*", ql):
            return self._communities(q)
        if re.search(r"\b(predict|hidden|undiscovered|likely|probable|missing link|should we look)\w*", ql):
            return self._predictions(q)
        if re.search(r"\b(remove|arrest|take out|disrupt|impact|neutrali)\w*", ql) and ents:
            return self._impact(q, ents[0])
        if re.search(r"\b(summar|overview|brief|what do we know|big picture|status)\w*", ql) and not ents:
            return self._summary(q)
        if ents:
            return self._dossier(q, ents[0])
        return self._help(q)

    # ------------------------------------------------------------------ handlers
    def _finish(self, q: str, intent: str, text: str, facts: dict, nodes: list[str], edges: list[str] | None = None, data=None) -> dict:
        narrative, used = llm.narrate(q, facts, text)
        return {"question": q, "intent": intent, "answer": narrative, "fallback_answer": text, "llm": used,
                "highlights": {"nodes": list(dict.fromkeys(nodes)), "edges": edges or []}, "data": data if data is not None else facts}

    def _path(self, q: str, a: str, b: str) -> dict:
        paths = Q.shortest_paths(self.G, a, b, k=3)
        if not paths:
            return self._finish(q, "path", f"No path found between **{self._lab(a)}** and **{self._lab(b)}** in the current graph.",
                                {"source": self._lab(a), "target": self._lab(b), "paths": []}, [a, b])
        described = [Q.describe_path(self.G, self.D, p) for p in paths]
        lines = [f"**{self._lab(a)}** and **{self._lab(b)}** are connected in {len(paths[0]) - 1} hop(s). {len(paths)} path(s) found:"]
        for i, hops in enumerate(described, 1):
            lines.append(f"{i}. " + " → ".join([hops[0]["from"]["label"]] + [f"*{h['verb']}*" + (f" ({h['count']}×)" if h["count"] > 1 else "") + f" → {h['to']['label']}" for h in hops]))
        nodes = [n for p in paths for n in p]
        edges = []
        for p in paths:
            for x, y in zip(p, p[1:]):
                d = self.D.get_edge_data(x, y) or self.D.get_edge_data(y, x)
                if d:
                    edges.append(d["id"])
        return self._finish(q, "path", "\n".join(lines), {"source": self._lab(a), "target": self._lab(b), "paths": described}, nodes, edges)

    def _dossier(self, q: str, n: str) -> dict:
        d = Q.entity_dossier(self.db, self.G, self.D, self.snap, n)
        e = d["entity"]
        parts = [f"**{e['label']}** ({e['type'].title().replace('_', ' ')})"]
        if e["aliases"]:
            parts.append(f"alias {', '.join(e['aliases'])}")
        head = " — ".join(parts) + "."
        lines = [head]
        if e["role"]:
            lines.append(f"Role: **{e['role']}** — " + "; ".join(e["role_reasons"][:3]) + ".")
        if e["suspicion_reasons"]:
            lines.append(f"Suspicion {e['suspicion']:.2f}: " + "; ".join(e["suspicion_reasons"]) + ".")
        if e["community"] is not None:
            comm = next((c for c in self.snap.get("communities", []) if c["id"] == e["community"]), None)
            if comm:
                lines.append(f"Member of community #{comm['id']} (“{comm['label']}”, {comm['size']} actors).")
        if d["associates"]:
            top = d["associates"][:5]
            lines.append("Strongest associates: " + ", ".join(
                f"**{a['other']['label']}** ({', '.join(f'{k} {v}' for k, v in a['channels'].items())})" for a in top) + ".")
        summary_rels = []
        for rt in ("USES_PHONE", "OWNS_ACCOUNT", "ASSOCIATED_VEHICLE", "RESIDES_AT", "ACCUSED_IN", "OWNS", "DIRECTOR_OF"):
            if rt in d["relationships"]:
                summary_rels.append(f"{Q.REL_VERB[rt]}: " + ", ".join(r["other"]["label"] for r in d["relationships"][rt][:4]))
        if summary_rels:
            lines.append("; ".join(summary_rels) + ".")
        if d["alerts"]:
            lines.append(f"Linked alerts ({len(d['alerts'])}): " + "; ".join(f"[{a['severity']}] {a['title']}" for a in d["alerts"][:4]) + ".")
        if d["evidence"]:
            lines.append(f"Evidence: {len(d['evidence'])} snippet(s) across {len(d['documents'])} document(s); e.g. “{d['evidence'][0]['snippet'][:160].strip()}…”")
        nodes = [n] + [a["other"]["id"] for a in d["associates"][:12]]
        facts = {"entity": e, "associates": d["associates"][:8], "alerts": d["alerts"][:6], "evidence": d["evidence"][:5],
                 "relationships": {k: [{"other": r["other"]["label"], "count": r["count"]} for r in v[:5]] for k, v in d["relationships"].items()}}
        return self._finish(q, "dossier", "\n".join(lines), facts, nodes, data=d)

    def _key_players(self, q: str) -> dict:
        kp = self.snap.get("key_players", [])[:8]
        if not kp:
            return self._finish(q, "key_players", "No analytics available yet - ingest data first.", {}, [])
        lines = ["Key players ranked by priority (structural influence fused with evidentiary suspicion):"]
        for i, k in enumerate(kp, 1):
            lines.append(f"{i}. **{k['label']}** — {k['role']} · priority {k['priority']:.2f} (influence {k['influence']:.2f}, suspicion {k['suspicion']:.2f}); "
                         + "; ".join(k["reasons"][:3]))
        return self._finish(q, "key_players", "\n".join(lines), {"key_players": kp}, [k["id"] for k in kp])

    def _brokers(self, q: str) -> dict:
        br = self.snap.get("brokers", [])[:6]
        lines = ["Brokers (actors whose removal would cut communication between groups):"]
        for b in br:
            lines.append(f"- **{b['label']}** bridges {b['community_span']} communities, betweenness {b['betweenness']:.3f}")
        return self._finish(q, "brokers", "\n".join(lines) if br else "No brokers detected.", {"brokers": br}, [b["id"] for b in br])

    def _communities(self, q: str) -> dict:
        comms = self.snap.get("communities", [])[:8]
        lines = [f"{len(self.snap.get('communities', []))} communities detected (Louvain). Most notable:"]
        for c in comms:
            flag = "⚠ suspicious" if c["suspicious"] else "no adverse signals"
            lines.append(f"- #{c['id']} **{c['label']}** — {c['size']} actors, {c['accused_count']} accused, risk {c['risk']:.2f} ({flag}); "
                         f"key members: {', '.join(m['label'] for m in c['top_members'][:4])}; areas: {', '.join(c['locations'][:3])}")
        nodes = [m["id"] for c in comms if c["suspicious"] for m in c["top_members"]]
        return self._finish(q, "communities", "\n".join(lines), {"communities": comms}, nodes)

    def _alerts(self, q: str, kind: str | None = None, ents: list[str] | None = None) -> dict:
        rows = self.db.query(Alert).filter(Alert.status != "dismissed").order_by(Alert.score.desc()).all()
        if kind:
            rows = [a for a in rows if a.kind == kind]
        if ents:
            rows = [a for a in rows if any(e in (a.entity_ids or []) for e in ents)]
        rows = rows[:8]
        if not rows:
            return self._finish(q, "alerts", "No matching alerts.", {"alerts": []}, ents or [])
        lines = [f"{len(rows)} alert(s)" + (f" of type {kind}" if kind else "") + (f" involving {', '.join(self._lab(e) for e in ents)}" if ents else "") + ":"]
        for a in rows:
            lines.append(f"- [{a.severity.upper()}] **{a.title}** — {a.description[:220]}")
        nodes = [e for a in rows for e in (a.entity_ids or [])][:40]
        facts = {"alerts": [{"kind": a.kind, "severity": a.severity, "title": a.title, "description": a.description, "score": a.score} for a in rows]}
        return self._finish(q, "alerts", "\n".join(lines), facts, nodes, data={"alerts": [{"id": a.id, **facts["alerts"][i]} for i, a in enumerate(rows)]})

    def _money(self, q: str, n: str) -> dict:
        mf = Q.money_flow(self.db, self.G, self.D, n)
        lines = [f"Money flow for **{self._lab(n)}** across account(s) {', '.join(mf['accounts']) or '—'}: inbound ₹{mf['total_in']:,.0f}, outbound ₹{mf['total_out']:,.0f}."]
        if mf["top_sources"]:
            lines.append("Top sources: " + ", ".join(f"{s} (₹{v:,.0f})" for s, v in mf["top_sources"][:5]))
        if mf["top_destinations"]:
            lines.append("Top destinations: " + ", ".join(f"{s} (₹{v:,.0f})" for s, v in mf["top_destinations"][:5]))
        nodes = [n] + [x for x in Q.ego(self.G, n, 2) if self.G.nodes[x]["type"] in ("BANK_ACCOUNT",)][:20]
        facts = {"subject": self._lab(n), "subject_id": n,
                 **{k: v for k, v in mf.items() if k != "transactions"}}
        return self._finish(q, "money", "\n".join(lines), facts, nodes, data=mf)

    def _calls(self, q: str, n: str) -> dict:
        cp = Q.call_profile(self.db, self.G, self.D, n)
        lines = [f"**{self._lab(n)}** uses {len(cp['phones'])} number(s) ({', '.join(cp['phones'])}); {cp['total_calls']} calls, {cp['night_ratio']:.0%} at night."]
        if cp["top_contacts"]:
            lines.append("Most frequent contacts: " + ", ".join(f"**{c['owner'] or c['phone']}** ({c['calls']}×)" for c in cp["top_contacts"][:6]))
        nodes = [n] + [c["owner_id"] for c in cp["top_contacts"] if c["owner_id"]]
        return self._finish(q, "calls", "\n".join(lines), {"subject": self._lab(n), "subject_id": n, **cp}, nodes, data=cp)

    def _timeline(self, q: str, n: str) -> dict:
        tl = Q.entity_timeline(self.db, n)
        keyev = [t for t in tl if t["kind"] in ("FIR", "SIGHTING", "INTEL", "POST")][-8:]
        lines = [f"Timeline for **{self._lab(n)}**: {len(tl)} events" + (f" from {tl[0]['at'][:10]} to {tl[-1]['at'][:10]}" if tl else "") + "."]
        for t in keyev:
            lines.append(f"- {t['at'][:16]} [{t['kind']}] {t['summary'][:140]}")
        return self._finish(q, "timeline", "\n".join(lines),
                            {"subject": self._lab(n), "subject_id": n, "events": keyev, "event_count": len(tl)},
                            [n], data={"timeline": tl})

    def _predictions(self, q: str) -> dict:
        lp = self.snap.get("link_predictions", [])[:8]
        lines = ["Predicted (not yet observed) links, ranked by Adamic-Adar score weighted by suspicion:"]
        for p in lp:
            lines.append(f"- **{p['source_label']}** ↔ **{p['target_label']}** (score {p['score']}): {p['explanation']}")
        nodes = [x for p in lp for x in (p["source"], p["target"])]
        return self._finish(q, "predictions", "\n".join(lines) if lp else "No predictions available.", {"predictions": lp}, nodes)

    def _impact(self, q: str, n: str) -> dict:
        from ..graph.analytics import actor_projection, removal_impact

        P = actor_projection(self.D)
        imp = removal_impact(P, n, self.snap.get("community"))
        if not imp:
            return self._finish(q, "impact", f"**{self._lab(n)}** is not an actor node.", {}, [n])
        text = (f"Removing **{self._lab(n)}** would cut {imp.get('flow_share', 0):.0%} of the weighted interaction volume inside their community, "
                f"fragment it by {imp.get('community_fragmentation', 0):.0%} and leave {len(imp.get('isolated_after', []))} member(s) isolated"
                + (": " + ", ".join(i["label"] for i in imp["isolated_after"]) if imp.get("isolated_after") else "") + ".")
        return self._finish(q, "impact", text, imp, [n] + [i["id"] for i in imp.get("isolated_after", [])])

    def _summary(self, q: str) -> dict:
        s = self.snap.get("summary", {})
        kp = self.snap.get("key_players", [])[:5]
        alerts = self.db.query(Alert).filter(Alert.status != "dismissed").order_by(Alert.score.desc()).limit(5).all()
        comms = [c for c in self.snap.get("communities", []) if c["suspicious"]]
        lines = [f"Graph: {s.get('nodes', 0)} entities, {s.get('edges', 0)} relationships, {s.get('actors', 0)} actors in {s.get('communities', 0)} communities "
                 f"({len(comms)} flagged). {s.get('persons_of_interest', 0)} persons of interest."]
        if kp:
            lines.append("Key players: " + ", ".join(f"**{k['label']}** ({k['role']})" for k in kp) + ".")
        if alerts:
            lines.append("Top alerts: " + "; ".join(f"[{a.severity}] {a.title}" for a in alerts) + ".")
        facts = {"summary": s, "key_players": kp, "alerts": [{"severity": a.severity, "title": a.title, "description": a.description} for a in alerts],
                 "suspicious_communities": comms[:3]}
        return self._finish(q, "summary", "\n".join(lines), facts, [k["id"] for k in kp])

    def _help(self, q: str) -> dict:
        """What to ask instead, phrased with names that are actually on this sheet.

        The suggestions used to be a fixed list written against the synthetic corpus. On any other
        sheet every example named somebody who does not exist, so following the advice produced a
        second failure - the worst thing an empty-handed answer can do. Draw them from the ranking.
        """
        players = [k for k in (self.snap.get("key_players") or []) if k.get("label")]
        names = [k["label"] for k in players[:3]]
        orgs = [k["label"] for k in players if k.get("type") == "ORGANIZATION"][:1]
        money = orgs[0] if orgs else (names[0] if names else None)

        tries = []
        if names:
            tries.append(f"“Who is {names[0]}?”")
        if len(names) >= 2:
            tries.append(f"“Path between {names[0]} and {names[1]}”")
        if money:
            tries.append(f"“Money flow for {money}”")
        tries += ["“Who are the key players?”", "“Which communities are suspicious?”"]
        if names:
            tries.append(f"“What happens if we arrest {names[0]}?”")
        tries.append("“Show the open alerts”")

        lead = ("I couldn't match that to an entity on this sheet." if names
                else "I couldn't match that to an entity, and this sheet has no ranked actors yet.")
        text = lead + " Try: " + ", ".join(f"*{t}*" for t in tries)
        return {"question": q, "intent": "help", "answer": text, "fallback_answer": text, "llm": False,
                "highlights": {"nodes": [], "edges": []}, "data": {"suggestions": tries}}
