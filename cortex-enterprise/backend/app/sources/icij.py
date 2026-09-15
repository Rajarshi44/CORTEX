"""
ICIJ Offshore Leaks connector (Panama / Paradise / Pandora Papers, Bahamas & Offshore Leaks).

771,315 officers, 814,344 entities, 3,339,267 relationships. Open Database License.
We download the bulk zip once (~72 MB), cache it, and stream the CSVs with Polars so
the India subset (2,330 officers) loads in seconds and the full graph is optional.

Mapping onto our schema:
  officer -> PERSON            entity/intermediary -> ORGANIZATION      address -> LOCATION
  officer_of -> DIRECTOR_OF    intermediary_of -> AFFILIATED_WITH       registered_address -> LOCATED_AT
  same_name_as / similar -> resolver hints (candidate duplicates)        connected_to -> ASSOCIATE_OF
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from sqlalchemy.orm import Session

from ..config import settings
from ..ingestion.ner import LOCATION, ORGANIZATION, PERSON
from ..ingestion.pipeline import IngestionService
from .base import Connector, SourceReport, register

ZIP_URL = "https://offshoreleaks-data.icij.org/offshoreleaks/csv/full-oldb.LATEST.zip"
PLACEHOLDER = re.compile(r"^(the\s+)?bearer(\s*\d+)?$|^(el\s+)?portador|^issued\s+to|^not\s+applicable|^n/?a$", re.I)
CORP_TOKEN = re.compile(r"\b(ltd|limited|inc|corp|corporation|llc|llp|s\.?a\.?|gmbh|pte|plc|holdings?|trust|foundation|fund|company|co\.)\b", re.I)
REL_MAP = {"officer_of": "DIRECTOR_OF", "intermediary_of": "AFFILIATED_WITH", "registered_address": "LOCATED_AT",
           "connected_to": "ASSOCIATE_OF", "same_company_as": "ASSOCIATE_OF", "same_as": "ASSOCIATE_OF",
           "same_name_as": "POSSIBLE_SAME_AS", "similar": "POSSIBLE_SAME_AS", "underlying": "AFFILIATED_WITH"}


@register
class ICIJConnector(Connector):
    name = "icij"
    title = "ICIJ Offshore Leaks (Panama / Pandora Papers)"
    description = ("3.3M real relationships between offshore companies, their officers, intermediaries and "
                   "addresses from five ICIJ investigations. Country-filtered subsets load in seconds.")
    homepage = "https://offshoreleaks.icij.org/"
    licence = "ODbL 1.0 (database) / CC BY-SA 4.0 (contents)"
    attribution = "International Consortium of Investigative Journalists (ICIJ) Offshore Leaks Database"
    rate_limit = 2.0
    timeout = 600.0
    cache_ttl_hours = 24 * 30

    @property
    def extract_dir(self) -> Path:
        return settings.data_dir / "icij"

    # ------------------------------------------------------------------ download
    def ensure_data(self) -> bool:
        d = self.extract_dir
        if (d / "relationships.csv").exists():
            return True
        r = self.fetch(ZIP_URL, cache_key="icij:zip")
        if not r.ok:
            return False
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(d)
        return True

    def frames(self) -> dict[str, pl.LazyFrame]:
        d = self.extract_dir
        return {k: pl.scan_csv(d / f"nodes-{k}.csv", ignore_errors=True, infer_schema_length=2000)
                for k in ("officers", "entities", "intermediaries", "addresses")} | {
            "relationships": pl.scan_csv(d / "relationships.csv", ignore_errors=True, infer_schema_length=2000)}

    # ------------------------------------------------------------------ harvest
    def harvest(self, db: Session, country: str | None = "India", max_officers: int = 400, hops: int = 1,
                max_hub_degree: int = 120, **_) -> SourceReport:
        """`max_hub_degree` removes nominee directors / mass-registration agents (an ICIJ node tied to
        hundreds of companies carries no investigative signal and would swamp every centrality)."""
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        if not self.ensure_data():
            rep.status, rep.reason = "unavailable", "bulk download failed and nothing cached"
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep
        F = self.frames()
        off = F["officers"]
        if country:
            off = off.filter(pl.col("countries").str.contains(country))
        seeds = off.select(["node_id", "name", "countries", "sourceID"]).head(max_officers).collect()
        seed_ids = set(seeds["node_id"].to_list())
        if not seed_ids:
            rep.status, rep.reason = "unavailable", f"no officers for country={country}"
            return rep

        # expand `hops` around seeds
        rels = F["relationships"]
        frontier, all_ids = set(seed_ids), set(seed_ids)
        edges = pl.DataFrame()
        for _ in range(hops + 1):
            e = rels.filter(pl.col("node_id_start").is_in(list(frontier)) | pl.col("node_id_end").is_in(list(frontier))).collect()
            edges = pl.concat([edges, e]).unique() if edges.height else e
            new = set(e["node_id_start"].to_list()) | set(e["node_id_end"].to_list())
            frontier = new - all_ids
            all_ids |= new
            if not frontier or len(all_ids) > 25000:
                break
        hubs: set[int] = set()
        if max_hub_degree and edges.height:
            from collections import Counter

            deg = Counter(edges["node_id_start"].to_list()) + Counter(edges["node_id_end"].to_list())
            hubs = {n for n, d in deg.items() if d > max_hub_degree and n not in seed_ids}
            if hubs:
                edges = edges.filter(~pl.col("node_id_start").is_in(list(hubs)) & ~pl.col("node_id_end").is_in(list(hubs)))
                all_ids = (set(edges["node_id_start"].to_list()) | set(edges["node_id_end"].to_list()) | seed_ids)
        ids = list(all_ids)
        names: dict[int, tuple[str, str, dict]] = {}
        for kind, etype in (("officers", PERSON), ("entities", ORGANIZATION), ("intermediaries", ORGANIZATION)):
            df = F[kind].filter(pl.col("node_id").is_in(ids)).collect()
            cols = df.columns
            for row in df.iter_rows(named=True):
                attrs = {k: row.get(k) for k in ("countries", "jurisdiction_description", "status", "incorporation_date",
                                                  "company_type", "sourceID", "valid_until") if k in cols and row.get(k)}
                attrs["icij_type"] = kind[:-1]
                nm = (row.get("name") or "").strip()
                if PLACEHOLDER.match(nm):  # "THE BEARER", "BEARER 1": bearer shares, not a person
                    continue
                t = ORGANIZATION if etype == PERSON and CORP_TOKEN.search(nm) else etype
                if t == PERSON and nm.isupper():
                    nm = nm.title()
                names[row["node_id"]] = (t, nm, attrs)
        addr = F["addresses"].filter(pl.col("node_id").is_in(ids)).select(["node_id", "address", "countries"]).collect()
        for row in addr.iter_rows(named=True):
            names[row["node_id"]] = (LOCATION, (row.get("address") or "")[:200], {"countries": row.get("countries")})

        svc = IngestionService(db)
        doc = svc._doc("LEAK", f"ICIJ Offshore Leaks: {country or 'global'} subset ({len(names)} nodes)", "",
                       {"country": country, "seed_officers": len(seed_ids), "source": "icij"}, records=len(names))
        from ..graph.store import add_entity_evidence

        eid: dict[int, str] = {}
        for nid, (etype, label, attrs) in names.items():
            if not label or len(label) < 2:
                continue
            ent = svc.resolver.resolve(etype, label, {**attrs, "icij_node_id": nid, "source": "ICIJ"})
            eid[nid] = ent.id
            add_entity_evidence(db, doc.id, ent.id, f"ICIJ {attrs.get('sourceID', '')}: {label} [{attrs.get('icij_type', 'address')}]"
                                + (f", {attrs['countries']}" if attrs.get("countries") else ""), 1.0, None, "structured")
        n_edges = 0
        for row in edges.iter_rows(named=True):
            s, t = eid.get(row["node_id_start"]), eid.get(row["node_id_end"])
            if not s or not t:
                continue
            rt = REL_MAP.get(row["rel_type"], "ASSOCIATE_OF")
            svc.acc.add(s, t, rt, weight=2.0 if rt in ("DIRECTOR_OF", "AFFILIATED_WITH") else 1.0, confidence=1.0,
                        doc_id=doc.id if n_edges < 500 else None,
                        snippet=f"ICIJ {row.get('sourceID', '')}: {row['rel_type']} ({row.get('link') or ''}) {row.get('start_date') or ''}",
                        extractor="structured", attrs={"icij_rel": row["rel_type"], "link": row.get("link")})
            n_edges += 1
        svc._finish()
        rep.records, rep.documents = len(eid), 1
        rep.details = {"hubs_dropped": len(hubs), "country": country, "seed_officers": len(seed_ids), "nodes": len(eid), "edges": n_edges}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep

    def stats(self) -> dict:
        if not (self.extract_dir / "relationships.csv").exists():
            return {"downloaded": False}
        F = self.frames()
        return {"downloaded": True, **{k: F[k].select(pl.len()).collect().item() for k in F},
                "india_officers": F["officers"].filter(pl.col("countries").str.contains("India")).select(pl.len()).collect().item()}
