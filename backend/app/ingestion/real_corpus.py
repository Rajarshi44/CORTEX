"""Build the default sheet from real public records instead of the synthetic demo.

Every step is a live connector already in `app.sources`. Each is optional: a source that is
blocked, offline or empty is skipped and reported, never faked. The order matters a little:
structured networks first (they create the actors), watchlists next (they flag them), then
unstructured text (judgments, wanted pages, news) whose NER attaches to the existing actors.

    python -m app.ingestion.real_corpus            # populate the configured database
    CNA_DEFAULT_CORPUS=real uvicorn app.main:app   # autoload on an empty database
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..sources import get_connector

log = logging.getLogger("cna.real")

ProgressCb = Callable[[str, int, int], None] | None

# (connector, params, why it is on the sheet)
STEPS: list[tuple[str, dict[str, Any], str]] = [
    ("icij", {"country": "India", "max_officers": 350, "hops": 1},
     "ICIJ Offshore Leaks: Indian officers, the offshore entities they control, their intermediaries and addresses"),
    ("opensanctions", {"dataset": "crime", "limit": 600, "countries": ["in"], "scan": 120_000},
     "OpenSanctions crime list: Indian persons and companies of criminal interest (debarments, disqualified directors, fugitives)"),
    ("opensanctions", {"dataset": "interpol_red_notices", "limit": 800, "countries": ["in"]},
     "INTERPOL red notices for Indian nationals or wanted by India"),
    ("opensanctions", {"dataset": "in_mha_banned", "limit": 400},
     "Ministry of Home Affairs: organisations banned and individuals designated under UAPA"),
    ("opensanctions", {"dataset": "in_nse_debarred", "limit": 2500},
     "NSE / SEBI debarred entities: persons and companies barred from the securities market"),
    ("gleif", {"query": "Adani", "limit": 6, "depth": 1},
     "GLEIF: legal-entity identifiers and ownership tree of a listed Indian group"),
    ("gleif", {"query": "Reliance", "limit": 6, "depth": 1},
     "GLEIF: a second Indian corporate ownership tree"),
    ("wanted", {}, "NIA and state police wanted / absconder lists"),
    ("courts", {"court": "sc", "year": 2024, "limit": 120, "criminal_only": True},
     "Supreme Court of India 2024 criminal judgments (AWS Open Data mirror of eCourts)"),
    ("news", {"limit": 40}, "Crime desks of Indian national newspapers (RSS)"),
]


def load_real_corpus(db: Session, progress: ProgressCb = None, steps=None, offline: bool = False) -> dict:
    steps = steps or STEPS
    report: list[dict] = []
    t0 = time.monotonic()
    for i, (name, params, why) in enumerate(steps):
        if progress:
            progress(f"{name}: {why}", i, len(steps))
        try:
            conn = get_connector(name, offline=offline)
            rep = conn.harvest(db, **params)
            entry = {"source": name, "params": params, "status": rep.status, "records": rep.records,
                     "documents": rep.documents, "reason": rep.reason, "elapsed": rep.elapsed, "details": rep.details}
            log.info("%s %s -> %s (%s records, %ss)", name, params, rep.status, rep.records, rep.elapsed)
        except Exception as exc:  # a broken source never breaks the sheet
            log.warning("%s failed: %s", name, exc)
            entry = {"source": name, "params": params, "status": "error", "records": 0, "reason": str(exc)}
        report.append(entry)
        db.commit()
    if progress:
        progress("screening actors against watchlists", len(steps), len(steps))
    try:
        screen = get_connector("opensanctions", offline=offline).screen(db, threshold=92, limit=40_000,
                                                                          datasets=["interpol_red_notices", "in_nse_debarred", "in_mha_banned"])
        hits = screen.get("hits", [])
        if hits:  # persist: the match becomes a signal the analytics can explain
            from ..db import Entity
            from ..graph.store import graph_cache

            for h in hits:
                e = db.get(Entity, h["entity_id"])
                if e is None:
                    continue
                # a two-token Indian name ("Sanjay Kumar") matches thousands of people: keep the hit, but as a weak lead
                tokens = [t for t in h["matched"].replace(".", " ").split() if t.lower() not in ("mr", "mrs", "shri", "smt", "ms", "dr")]
                strength = "strong" if (len(tokens) >= 3 and h["score"] >= 95) or e.type == "ORGANIZATION" and h["score"] >= 97 else "weak"
                e.attributes = {**(e.attributes or {}), "watchlist": True, "screened_match": h["matched"], "screen_score": h["score"],
                                "screen_strength": strength, "watchlist_topics": h.get("topics") or [], "watchlist_datasets": h.get("lists") or []}
            db.commit()
            graph_cache.invalidate()
        report.append({"source": "opensanctions:screen", "status": screen.get("status", "ok"), "records": len(hits),
                       "details": {"hits": len(hits), "screened": screen.get("screened")}})
    except Exception as exc:
        log.warning("screening failed: %s", exc)
    return {"steps": report, "elapsed": round(time.monotonic() - t0, 1),
            "loaded": sum(1 for r in report if r["status"] == "ok" and r.get("records")),
            "records": sum(r.get("records", 0) for r in report if r["status"] == "ok")}


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    from ..db import SessionLocal, init_db

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    s = SessionLocal()
    try:
        out = load_real_corpus(s, progress=lambda m, i, n: print(f"[{i}/{n}] {m}", file=sys.stderr))
        from ..api.deps import analysis_service

        analysis_service.snapshot(s, force=True)
    finally:
        s.close()
    print(json.dumps(out, indent=1, default=str))
