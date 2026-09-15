"""
Published criminal / covert network benchmarks with ground truth (Netzschleuder catalogue).

  crime            St. Louis police records - people <-> crime events with suspect/victim/witness roles
  montreal         Montreal Police intelligence DB - 35 gangs with true allegiance groups
  terrorists_911   Krebs' 9/11 network - 62 named actors, cell membership
  train_terrorists Madrid 2004 - 64 actors, tie strength weights
  email_enron      36,692 addresses, 367,662 timestamped messages (real temporal communication graph)

Each loads into its own namespace so evaluations can be run against the known structure.
`evaluate()` scores our community detection / key-player ranking against the published labels.
"""
from __future__ import annotations

import csv
import io
import time
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ingestion.ner import CASE, ORGANIZATION, PERSON
from ..ingestion.pipeline import IngestionService
from .base import Connector, SourceReport, register

BASE = "https://networks.skewed.de"
CATALOG = {
    "crime": {"title": "St. Louis crime network (police records)", "node_type": PERSON, "bipartite": True,
              "cite": "Decker, Kohfeld, Rosenfeld & Sprague, St. Louis Homicide Project (1991)"},
    "montreal": {"title": "Montreal street gangs (police intelligence)", "node_type": ORGANIZATION, "label_col": "Allegiances",
                 "cite": "Descormiers & Morselli, Int. Criminal Justice Review 21(3) 2011"},
    "terrorists_911": {"title": "9/11 hijacker network (Krebs)", "node_type": PERSON, "label_col": "group",
                       "cite": "V. Krebs, Mapping networks of terrorist cells, Connections 24 (2002)"},
    "train_terrorists": {"title": "Madrid 2004 train bombing network", "node_type": PERSON, "weighted": True,
                         "cite": "B. Hayes, American Scientist 94 (2006)"},
    "email_enron": {"title": "Enron email network (temporal)", "node_type": PERSON, "large": True,
                    "cite": "Klimt & Yang, ECML 2004 / SNAP"},
}


@register
class BenchmarkConnector(Connector):
    name = "benchmarks"
    title = "Published criminal-network benchmarks (Netzschleuder)"
    description = "Real covert/criminal networks with published ground truth, used to validate our algorithms."
    homepage = BASE + "/api/nets"
    licence = "Per dataset (academic, cite the paper); catalogue CC-BY"
    attribution = "Netzschleuder network catalogue (T. Peixoto) and the original authors"
    rate_limit = 1.0
    respect_robots = False
    cache_ttl_hours = 24 * 60

    def load(self, key: str) -> dict | None:
        r = self.fetch(f"{BASE}/net/{key}/files/{key}.csv.zip", cache_key=f"nz:{key}")
        if not r.ok:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        out: dict[str, list[dict]] = {}
        for fn in z.namelist():
            if not fn.endswith(".csv"):
                continue
            rows = list(csv.reader(io.StringIO(z.read(fn).decode("utf-8", "replace"))))
            if not rows:
                continue
            header = [h.strip().lstrip("#").strip() for h in rows[0]]
            out[fn.rsplit(".", 1)[0]] = [dict(zip(header, [c.strip() for c in r])) for r in rows[1:] if r]
        return out

    def harvest(self, db: Session, dataset: str = "montreal", max_edges: int = 60000, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        spec = CATALOG.get(dataset)
        if not spec:
            rep.status, rep.reason = "error", f"unknown benchmark '{dataset}'"
            return rep
        data = self.load(dataset)
        if not data or "edges" not in data:
            rep.status, rep.reason = "unavailable", "download failed"
            return rep
        nodes = {r.get("index") or r.get("id") or str(i): r for i, r in enumerate(data.get("nodes", []))}
        svc = IngestionService(db)
        from ..graph.store import add_entity_evidence

        doc = svc._doc("BENCHMARK", f"Benchmark: {spec['title']}", spec["cite"], {"dataset": dataset, "source": "netzschleuder", **spec}, records=len(nodes))
        ids: dict[str, str] = {}
        label_col = spec.get("label_col")
        for idx, row in nodes.items():
            name = row.get("name") or row.get("label") or f"{dataset}-{idx}"
            name = name.replace("_", " ")
            etype = spec["node_type"]
            attrs = {"benchmark": dataset, **{k: v for k, v in row.items() if k not in ("_pos", "index", "name") and v}}
            if spec.get("bipartite") and row.get("meta") in ("0", "2"):  # crime dataset: right nodes = events
                etype = CASE
                name = f"St. Louis crime event {idx}"
            ent = svc.resolver.resolve(etype, name, attrs)
            ids[idx] = ent.id
            add_entity_evidence(db, doc.id, ent.id, f"{spec['title']}: node {idx} {name}" + (f" [{label_col}={row.get(label_col)}]" if label_col else ""), 1.0, None, "structured")
        n = 0
        for e in data["edges"][:max_edges]:
            s, t = ids.get(e.get("source")), ids.get(e.get("target"))
            if not s or not t:
                continue
            w = float(e.get("weight") or 1.0)
            rel = "INVOLVED_IN" if spec.get("bipartite") else ("COMMUNICATED_WITH" if dataset == "email_enron" else "ASSOCIATE_OF")
            svc.acc.add(s, t, rel, weight=w, confidence=1.0, doc_id=doc.id if n < 200 else None, snippet=f"{spec['title']} edge", extractor="structured")
            n += 1
        svc._finish()
        rep.records, rep.documents = len(ids), 1
        rep.details = {"dataset": dataset, "nodes": len(ids), "edges": n, "ground_truth_label": label_col}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, db: Session, dataset: str = "montreal") -> dict:
        """Compare our Louvain communities with the dataset's published labels (ARI / NMI / purity)."""
        import numpy as np
        from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

        from ..db import Entity
        from ..graph.analytics import actor_projection, compute_metrics, detect_communities
        from ..graph.store import graph_cache

        spec = CATALOG.get(dataset, {})
        label_col = spec.get("label_col")
        ents = db.query(Entity).filter(Entity.attributes["benchmark"].as_string() == dataset).all() if hasattr(Entity.attributes, "as_string") else \
            [e for e in db.query(Entity).all() if (e.attributes or {}).get("benchmark") == dataset]
        if not ents:
            return {"status": "unavailable", "reason": "benchmark not loaded"}
        D = graph_cache.get_directed(db)
        P = actor_projection(D)
        keep = [e.id for e in ents if e.id in P]
        sub = P.subgraph(keep).copy()
        if not label_col:
            m = compute_metrics(sub)
            top = sorted(m.items(), key=lambda kv: -kv[1]["influence"])[:10]
            return {"status": "ok", "dataset": dataset, "nodes": sub.number_of_nodes(), "edges": sub.number_of_edges(),
                    "top_influence": [{"label": sub.nodes[n]["label"], **v} for n, v in top]}
        import networkx as nx
        from collections import Counter, defaultdict

        truth = {e.id: str((e.attributes or {}).get(label_col)) for e in ents if e.id in sub}
        ids = [i for i in truth]
        y = [truth[i] for i in ids]

        def score(comm: dict) -> dict:
            yhat = [comm.get(i, -1) for i in ids]
            groups = defaultdict(Counter)
            for a, b in zip(yhat, y):
                groups[a][b] += 1
            purity = sum(c.most_common(1)[0][1] for c in groups.values()) / len(ids) if ids else 0.0
            return {"detected_communities": len(set(yhat)), "adjusted_rand_index": round(float(adjusted_rand_score(y, yhat)), 4),
                    "normalized_mutual_info": round(float(normalized_mutual_info_score(y, yhat)), 4), "purity": round(purity, 4)}

        # Louvain resolution sweep: the default (1.0) over-splits small covert cells; report the sweep transparently
        sweep = {}
        for res in (0.4, 0.6, 0.8, 1.0, 1.2):
            comms = nx.community.louvain_communities(sub, weight="weight", seed=42, resolution=res)
            sweep[str(res)] = score({n: i for i, c in enumerate(comms) for n in c})
        default = score(detect_communities(sub))
        best_res = max(sweep, key=lambda r: sweep[r]["adjusted_rand_index"])
        return {"status": "ok", "dataset": dataset, "nodes": sub.number_of_nodes(), "edges": sub.number_of_edges(),
                "true_groups": len(set(y)), "ground_truth_label": label_col, "default": default,
                "best_resolution": float(best_res), "best": sweep[best_res], "resolution_sweep": sweep}
