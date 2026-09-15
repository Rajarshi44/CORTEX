"""Live data-source endpoints: catalogue, health probes, harvesting, screening, benchmarks."""
from __future__ import annotations

import json
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, current_user, require_role
from ..db import SessionLocal, User, get_session
from ..sources import REGISTRY, cache, get_connector
from .deps import analysis_service
from .routes_ingest import _job_lock, hub

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def catalogue(_: Annotated[User, Depends(current_user)]):
    return {"sources": [cls().info() | {"name": n} for n, cls in REGISTRY.items()], "cache": cache.stats()}


@router.get("/health")
def health(_: Annotated[User, Depends(current_user)], name: str | None = None):
    names = [name] if name else list(REGISTRY)
    out = []
    for n in names:
        if n not in REGISTRY:
            raise HTTPException(404, f"unknown source {n}")
        try:
            out.append(get_connector(n).probe().as_dict())
        except Exception as exc:  # never let one probe kill the panel
            out.append({"name": n, "status": "error", "reason": str(exc)})
    return out


class HarvestIn(BaseModel):
    source: str
    params: dict[str, Any] = {}
    offline: bool = False


@router.post("/harvest", dependencies=[Depends(require_role("analyst"))])
def harvest(body: HarvestIn, user: Annotated[User, Depends(current_user)]):
    if body.source not in REGISTRY:
        raise HTTPException(404, f"unknown source {body.source}")
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Another ingestion job is running")

    def work():
        db = SessionLocal()
        label = f"source:{body.source}"
        try:
            hub.publish(label, 0, 0, "running")
            conn = get_connector(body.source, offline=body.offline)
            rep = conn.harvest(db, **body.params)
            if rep.status == "ok" and rep.records:
                hub.publish("analytics", 0, 0, "running")
                analysis_service.snapshot(db, force=True)
            hub.publish(label, 1, 1, "done" if rep.status == "ok" else "error", {"report": rep.as_dict()})
            audit(db, user.username, "harvest", f"{body.source} {json.dumps(body.params)} -> {rep.status} {rep.records} records")
        except Exception as exc:
            hub.publish(label, 0, 0, "error", {"error": str(exc)})
        finally:
            db.close()
            _job_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return {"started": True, "source": body.source}


class CorpusIn(BaseModel):
    reset: bool = False  # drop everything first (admin only)


@router.post("/corpus/real", dependencies=[Depends(require_role("analyst"))])
def build_real_corpus(body: CorpusIn, user: Annotated[User, Depends(current_user)]):
    """Chain every public-record connector into the current database (optionally after wiping it)."""
    if body.reset and user.role != "admin":
        raise HTTPException(403, "only an admin may reset the sheet")
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Another ingestion job is running")

    def work():
        from ..ingestion.real_corpus import load_real_corpus

        db = SessionLocal()
        try:
            if body.reset:
                from ..db import Alert, AnalysisSnapshot, Document, Entity, Evidence, Relationship, TimelineEvent
                from ..graph.store import graph_cache

                for model in (Evidence, TimelineEvent, Alert, Relationship, Entity, Document, AnalysisSnapshot):
                    db.query(model).delete()
                db.commit()
                graph_cache.invalidate()
                analysis_service.invalidate()
            hub.publish("public records", 0, 0, "running")
            rep = load_real_corpus(db, progress=lambda m, i, n: hub.publish(m, i, n, "running"))
            hub.publish("analytics", 0, 0, "running")
            analysis_service.snapshot(db, force=True)
            hub.publish("public records", 1, 1, "done", {"report": rep})
            audit(db, user.username, "corpus", f"real corpus -> {rep['loaded']} sources, {rep['records']} records")
        except Exception as exc:
            hub.publish("public records", 0, 0, "error", {"error": str(exc)})
        finally:
            db.close()
            _job_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


@router.post("/harvest/sync", dependencies=[Depends(require_role("analyst"))])
def harvest_sync(body: HarvestIn, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_session)]):
    """Blocking variant for small pulls (tests / CLI)."""
    if body.source not in REGISTRY:
        raise HTTPException(404, f"unknown source {body.source}")
    rep = get_connector(body.source, offline=body.offline).harvest(db, **body.params)
    if rep.status == "ok" and rep.records:
        analysis_service.snapshot(db, force=True)
    audit(db, user, "harvest", f"{body.source} -> {rep.status} {rep.records}")
    return rep.as_dict()


@router.get("/datagovin/search")
def datagov_search(_: Annotated[User, Depends(current_user)], q: str = "crime", limit: int = 30, official_only: bool = True):
    return get_connector("datagovin").search(q, limit, official_only)


@router.get("/datagovin/resource/{resource_id}")
def datagov_resource(resource_id: str, _: Annotated[User, Depends(current_user)], limit: int = 200, offset: int = 0):
    return get_connector("datagovin").resource(resource_id, limit, offset)


@router.get("/gleif/search")
def gleif_search(_: Annotated[User, Depends(current_user)], q: str, country: str = "IN", limit: int = 20):
    c = get_connector("gleif")
    return [c._entity_fields(r) for r in c.search_entities(q, country, limit)]


@router.get("/gleif/{lei}/tree")
def gleif_tree(lei: str, _: Annotated[User, Depends(current_user)]):
    c = get_connector("gleif")
    return {k: [c._entity_fields(r) for r in c.relations(lei, k)] for k in ("direct-parent", "ultimate-parent", "direct-children")}


@router.get("/icij/stats")
def icij_stats(_: Annotated[User, Depends(current_user)]):
    return get_connector("icij").stats()


@router.post("/opensanctions/screen", dependencies=[Depends(require_role("analyst"))])
def screen(db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)], threshold: int = 88):
    res = get_connector("opensanctions").screen(db, threshold)
    audit(db, user, "watchlist_screen", f"{len(res.get('hits', []))} hits")
    return res


@router.get("/opensanctions/resolution-benchmark")
def er_benchmark(_: Annotated[User, Depends(current_user)], limit: int = 1200):
    return get_connector("opensanctions").resolution_benchmark(limit)


@router.get("/benchmarks/evaluate/{dataset}")
def bench_eval(dataset: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    return get_connector("benchmarks").evaluate(db, dataset)


@router.get("/courts/high-courts")
def hc_files(_: Annotated[User, Depends(current_user)], year: int = 2024, bench: str | None = None):
    return get_connector("courts").high_court_files(year, bench)[:200]


@router.get("/news/preview")
def news_preview(_: Annotated[User, Depends(current_user)], feed: str = "toi_crime"):
    from ..sources.news import FEEDS

    if feed not in FEEDS:
        raise HTTPException(404, "unknown feed")
    return get_connector("news").items(feed)[:30]
