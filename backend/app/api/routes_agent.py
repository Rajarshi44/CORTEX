"""Investigator agent: streaming tool-calling endpoint plus a non-streaming fallback."""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.agent import InvestigatorAgent, capabilities
from ..auth import audit, current_user
from ..db import SessionLocal, User, get_session
from ..graph.store import graph_cache
from .deps import analysis_service

log = logging.getLogger("cna.api.agent")
router = APIRouter(prefix="/api/agent", tags=["agent"])


class Turn(BaseModel):
    question: str = ""
    answer: str = ""


class AskIn(BaseModel):
    question: str
    history: list[Turn] = []


@router.get("/capabilities")
def agent_capabilities(_: Annotated[User, Depends(current_user)]):
    """Which providers, tools and web tier are live on this deployment."""
    return capabilities()


@router.post("/stream")
def agent_stream(body: AskIn, user: Annotated[User, Depends(current_user)]):
    """Run the agent, streaming newline-delimited JSON events as they happen.

    The generator owns its own session: FastAPI tears a `Depends(get_session)` session down when
    the handler returns, which for a streaming response is *before* the first token is produced.
    """
    history = [t.model_dump() for t in body.history]
    question = body.question

    def gen():
        db = SessionLocal()
        try:
            G, D = graph_cache.get(db), graph_cache.get_directed(db)
            snap = analysis_service.snapshot(db)
            audit(db, user, "agent_query", question[:400])
            agent = InvestigatorAgent(db, G, D, snap)
            for ev in agent.stream(question, history):
                yield json.dumps(ev, default=str, ensure_ascii=False) + "\n"
        except Exception as exc:  # a crash mid-stream must still reach the UI as an event
            log.exception("agent stream failed")
            yield json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n"
        finally:
            db.close()

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.post("/ask")
def agent_ask(body: AskIn, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Same agent, one JSON response. Slower to first byte; used when streaming is unavailable."""
    G, D = graph_cache.get(db), graph_cache.get_directed(db)
    snap = analysis_service.snapshot(db)
    audit(db, user, "agent_query", body.question[:400])
    return InvestigatorAgent(db, G, D, snap).answer(body.question, [t.model_dump() for t in body.history])
