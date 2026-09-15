"""Semantic search, neural extraction and compute-backend endpoints."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.semantic import semantic_index
from ..auth import audit, current_user, require_role
from ..db import User, get_session
from ..graph import fastmetrics
from ..ingestion.neural_ner import DEFAULT_LABELS, neural_ner
from .deps import analysis_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status(_: Annotated[User, Depends(current_user)]):
    """What acceleration / AI tiers are active on this deployment."""
    from ..ai import llm

    return {
        "compute": fastmetrics.backend(),
        "extraction_tiers": {
            "rules": {"available": True, "description": "deterministic Indian-police regex + gazetteer"},
            "neural": neural_ner.status(),
            "llm": {**llm.status(), "extraction_enabled": llm.settings.llm_extraction_enabled,
                    "model": llm.settings.llm_model if llm.available() else None},
        },
        "semantic_search": semantic_index.status(),
    }


# ----------------------------------------------------------------------------- semantic search
class SearchIn(BaseModel):
    query: str
    limit: int = 10
    source_type: str | None = None


@router.post("/search")
def semantic_search(body: SearchIn, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
    """Meaning-based document search; falls back to keyword SQL if embeddings are unavailable."""
    res = semantic_index.search(db, body.query, body.limit, body.source_type)
    if res["status"] != "ok":
        from ..db import Document

        q = db.query(Document).filter(Document.content.ilike(f"%{body.query}%") | Document.title.ilike(f"%{body.query}%"))
        if body.source_type:
            q = q.filter(Document.source_type == body.source_type)
        rows = q.limit(body.limit).all()
        res = {"status": "keyword_fallback", "reason": res.get("reason", ""), "query": body.query,
               "results": [{"document_id": d.id, "source_type": d.source_type, "title": d.title, "score": None,
                            "snippet": (d.content or d.title)[:280]} for d in rows]}
    audit(db, user, "semantic_search", body.query)
    return res


@router.get("/similar/{document_id}")
def similar(document_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)], limit: int = 8):
    res = semantic_index.similar_documents(db, document_id, limit)
    if res["status"] == "not_found":
        raise HTTPException(404, "document not indexed")
    return res


@router.post("/search/reindex", dependencies=[Depends(require_role("analyst"))])
def reindex(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    return semantic_index.build(db, force=True)


# ----------------------------------------------------------------------------- neural extraction
class ExtractIn(BaseModel):
    text: str
    labels: list[str] | None = None
    threshold: float | None = None


@router.get("/extract/labels")
def labels(_: Annotated[User, Depends(current_user)]):
    return {"default_labels": DEFAULT_LABELS, "zero_shot": True,
            "note": "any plain-English label works - the model needs no retraining"}


@router.post("/extract/preview")
def extract_preview(body: ExtractIn, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_session)]):
    """Run all available extraction tiers on ad-hoc text without ingesting it.

    This is the zero-shot demo: pass any labels you like (e.g. "explosive", "gang name")
    and the transformer finds them with no training.
    """
    from ..ingestion.ner import RuleNER

    rules = RuleNER().extract(body.text)
    out: dict[str, Any] = {
        "rules": {
            "entities": [{"type": m.type, "text": m.text, "confidence": m.confidence, "attrs": m.attrs} for m in rules.mentions],
            "relations": [{"source": r.source.text, "type": r.rel_type, "target": r.target.text, "confidence": r.confidence}
                          for r in rules.relations if r.rel_type != "MENTIONED_WITH"],
            "sections": rules.sections, "dates": rules.dates,
        },
        "neural": {"available": neural_ner.available(), "entities": []},
    }
    if neural_ner.available():
        res = neural_ner.extract(body.text, body.labels, body.threshold)
        if res:
            out["neural"]["entities"] = [{"type": m.type, "text": m.text, "confidence": round(m.confidence, 3),
                                          "label": m.attrs.get("gliner_label"), "context": m.attrs.get("context")}
                                         for m in res.mentions]
            # offence context (drug substance, weapon, quantity, ...) has no graph-node equivalent but is
            # the clearest evidence the transformer adds over the rules - surface it explicitly.
            out["neural"]["context"] = getattr(res, "context", [])
            out["neural"]["rejected"] = getattr(res, "rejected", [])
            out["neural"]["labels_used"] = body.labels or DEFAULT_LABELS
            rule_spans = {e["text"].lower() for e in out["rules"]["entities"]}
            out["neural"]["only_found_by_transformer"] = (
                [{"label": c["label"], "text": c["text"], "confidence": c["score"]} for c in out["neural"]["context"]]
                + [e for e in out["neural"]["entities"] if e["text"].lower() not in rule_spans])
    else:
        out["neural"]["reason"] = neural_ner.status()["error"] or (
            "GLiNER not installed - run: uv pip install -e \".[neural]\"" if not neural_ner.status()["installed"]
            else "disabled (set CNA_NEURAL_NER_ENABLED=true)")
    audit(db, user, "extract_preview", body.text[:120])
    return out


# ----------------------------------------------------------------------------- benchmark
@router.get("/compute/benchmark")
def compute_benchmark(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """A/B the Rust and NetworkX centrality paths on the live graph."""
    import os
    import time

    from ..graph.analytics import actor_projection, compute_metrics
    from ..graph.store import graph_cache

    P = actor_projection(graph_cache.get_directed(db))
    if P.number_of_nodes() == 0:
        return {"status": "empty"}
    out = {}
    for engine in ("rustworkx", "networkx"):
        prev = os.environ.get("CNA_DISABLE_RUSTWORKX")
        os.environ["CNA_DISABLE_RUSTWORKX"] = "0" if engine == "rustworkx" else "1"
        try:
            t = time.monotonic()
            m = compute_metrics(P)
            out[engine] = {"seconds": round(time.monotonic() - t, 3),
                           "betweenness_method": fastmetrics.LAST_BETWEENNESS_METHOD,
                           "top": [P.nodes[n]["label"] for n, _ in sorted(m.items(), key=lambda kv: -kv[1]["influence"])[:5]]}
        finally:
            if prev is None:
                os.environ.pop("CNA_DISABLE_RUSTWORKX", None)
            else:
                os.environ["CNA_DISABLE_RUSTWORKX"] = prev
    if out.get("networkx", {}).get("seconds"):
        out["speedup"] = round(out["networkx"]["seconds"] / max(out["rustworkx"]["seconds"], 1e-6), 2)
    out["nodes"], out["edges"] = P.number_of_nodes(), P.number_of_edges()
    out["ranking_identical"] = out.get("rustworkx", {}).get("top") == out.get("networkx", {}).get("top")
    return out
