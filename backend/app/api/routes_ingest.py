"""Ingestion endpoints + live progress over WebSocket."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import audit, current_user, require_role
from ..db import Document, Entity, Relationship, SessionLocal, TimelineEvent, User, get_session
from ..graph.store import graph_cache
from ..ingestion.pipeline import IngestionService, load_demo_dataset
from .deps import analysis_service

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class ProgressHub:
    """Fan-out ingestion progress to connected WebSocket clients (thread-safe producer)."""

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.state: dict[str, Any] = {"status": "idle", "stage": None, "done": 0, "total": 0, "history": []}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def publish(self, stage: str, done: int, total: int, status: str = "running", extra: dict | None = None):
        with self._lock:
            self.state.update({"status": status, "stage": stage, "done": done, "total": total, "ts": time.time(), **(extra or {})})
            if status in ("done", "error"):
                self.state["history"] = (self.state.get("history") or [])[-9:] + [{"stage": stage, "status": status, "ts": time.time(), **(extra or {})}]
            payload = json.dumps(self.state, default=str)
        if self.loop:
            for ws in list(self.clients):
                asyncio.run_coroutine_threadsafe(self._send(ws, payload), self.loop)

    async def _send(self, ws: WebSocket, payload: str):
        try:
            await ws.send_text(payload)
        except Exception:
            self.clients.discard(ws)


hub = ProgressHub()
_job_lock = threading.Lock()


def _run_job(fn, label: str, username: str):
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Another ingestion job is running")

    def work():
        db = SessionLocal()
        try:
            hub.publish(label, 0, 0, "running")
            stats = fn(db, lambda s, d, t: hub.publish(s, d, t))
            hub.publish("analytics", 0, 0, "running")
            analysis_service.snapshot(db, force=True)
            hub.publish(label, 1, 1, "done", {"stats": stats, "analysis": analysis_service.last_run})
            audit(db, username, "ingest", f"{label}: {json.dumps(stats, default=str)[:500]}")
        except Exception as exc:  # surface to UI
            hub.publish(label, 0, 0, "error", {"error": str(exc)})
        finally:
            db.close()
            _job_lock.release()

    threading.Thread(target=work, daemon=True).start()


@router.post("/demo", dependencies=[Depends(require_role("analyst"))])
def ingest_demo(user: Annotated[User, Depends(current_user)]):
    _run_job(lambda db, cb: load_demo_dataset(db, cb), "demo dataset", user.username)
    return {"started": True}


@router.post("/upload", dependencies=[Depends(require_role("analyst"))])
async def upload(user: Annotated[User, Depends(current_user)], source_type: Annotated[str, Form()], file: Annotated[UploadFile, File()]):
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large (50 MB limit)")
    name = file.filename or "upload"

    def job(db, cb):
        svc = IngestionService(db, cb)
        return svc.ingest_payload(source_type, name, raw).as_dict()

    _run_job(job, f"{source_type.upper()} {name}", user.username)
    return {"started": True, "file": name, "source_type": source_type}


class TextIn(BaseModel):
    source_type: str = "FIR"
    title: str
    text: str


@router.post("/text", dependencies=[Depends(require_role("analyst"))])
def ingest_text(body: TextIn, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_session)]):
    """Synchronous ingestion of a single narrative (fast) - returns what was extracted."""
    svc = IngestionService(db)
    doc = svc.ingest_text(body.source_type.upper(), body.title, body.text)
    snap = analysis_service.snapshot(db, force=True)
    audit(db, user, "ingest_text", body.title)
    from ..db import Evidence

    ents = {ev.entity_id for ev in db.query(Evidence).filter(Evidence.document_id == doc.id).all() if ev.entity_id}
    G = graph_cache.get(db)
    return {"document_id": doc.id, "stats": svc.stats.as_dict(),
            "entities": [{"id": e, "label": G.nodes[e]["label"], "type": G.nodes[e]["type"]} for e in ents if e in G],
            "alerts": snap.get("alert_count")}


@router.get("/status")
def status_(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    by_source = dict(db.query(Document.source_type, func.count()).group_by(Document.source_type).all())
    records = dict(db.query(Document.source_type, func.sum(Document.record_count)).group_by(Document.source_type).all())
    return {"job": hub.state, "documents": by_source, "records": {k: int(v or 0) for k, v in records.items()},
            "entities": db.query(Entity).count(), "relationships": db.query(Relationship).count(),
            "events": db.query(TimelineEvent).count(), "graph_version": graph_cache.version}


@router.get("/documents")
def documents(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], source_type: str | None = None,
              q: str | None = None, limit: int = 100):
    query = db.query(Document)
    if source_type:
        query = query.filter(Document.source_type == source_type.upper())
    if q:
        query = query.filter(Document.title.ilike(f"%{q}%") | Document.content.ilike(f"%{q}%"))
    rows = query.order_by(Document.occurred_at.desc().nullslast()).limit(limit).all()
    return [{"id": d.id, "source_type": d.source_type, "title": d.title, "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None,
             "records": d.record_count, "preview": (d.content or "")[:200]} for d in rows]


@router.get("/documents/{doc_id}")
def document(doc_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    from ..db import Evidence

    G = graph_cache.get(db)
    evs = db.query(Evidence).filter(Evidence.document_id == doc_id).all()
    ents = {}
    for ev in evs:
        if ev.entity_id and ev.entity_id in G:
            ents[ev.entity_id] = {"id": ev.entity_id, "label": G.nodes[ev.entity_id]["label"], "type": G.nodes[ev.entity_id]["type"],
                                  "snippet": ev.snippet, "confidence": ev.confidence, "extractor": ev.extractor}
    return {"id": d.id, "source_type": d.source_type, "title": d.title, "content": d.content, "meta": d.meta,
            "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None, "records": d.record_count,
            "entities": sorted(ents.values(), key=lambda e: e["type"])}


@router.delete("/reset", dependencies=[Depends(require_role("admin"))])
def reset(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_session)]):
    from ..db import Alert, AnalysisSnapshot, Evidence

    for model in (Evidence, TimelineEvent, Alert, Relationship, Entity, Document, AnalysisSnapshot):
        db.query(model).delete()
    db.commit()
    graph_cache.invalidate()
    analysis_service.invalidate()
    audit(db, user, "reset")
    return {"ok": True}


@router.websocket("/ws")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    hub.loop = asyncio.get_running_loop()
    hub.clients.add(ws)
    try:
        await ws.send_text(json.dumps(hub.state, default=str))
        while True:
            await ws.receive_text()  # keep-alive pings from client
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
