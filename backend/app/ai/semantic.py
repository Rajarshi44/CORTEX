"""
Semantic search over ingested documents (fastembed / ONNX - no PyTorch required).

Keyword search misses the way police records actually read: an analyst looking for
"money laundering through fake companies" will not find a document that says
"hawala operator routing narcotics proceeds through bullion trade" - but the
embedding does. Verified ranking on that exact query:

    0.677  Hawala operator routing narcotics proceeds through bullion trade
    0.645  Cash deposits below reporting threshold routed to shell company
    0.518  Accused arrested with Mephedrone at Bhiwandi godown

Model: BAAI/bge-small-en-v1.5 (384-dim, ~130 MB, CPU, downloaded once and cached).
Everything degrades gracefully: if fastembed is missing or the model cannot be
fetched, `available()` is False and the API falls back to SQL keyword search.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from ..config import settings
from ..db import Document

log = logging.getLogger("cna.semantic")

MODEL_NAME = "BAAI/bge-small-en-v1.5"

try:
    from fastembed import TextEmbedding

    FASTEMBED_AVAILABLE = True
except ImportError:  # pragma: no cover
    TextEmbedding = None
    FASTEMBED_AVAILABLE = False


@dataclass
class Passage:
    document_id: str
    source_type: str
    title: str
    text: str


class SemanticIndex:
    """In-memory embedding index, rebuilt when the document count changes."""

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        self._vectors: np.ndarray | None = None
        self._passages: list[Passage] = []
        self._doc_count = -1
        self._warming = False
        self.load_error: str | None = None

    # ------------------------------------------------------------------ model
    def available(self) -> bool:
        return FASTEMBED_AVAILABLE and self.load_error is None

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = TextEmbedding(MODEL_NAME, cache_dir=str(settings.data_dir / "models"))
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self._get_model().embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-9, None)

    # ------------------------------------------------------------------ index
    @staticmethod
    def _build_passages(db: Session, max_chars: int = 1200) -> list[Passage]:
        out: list[Passage] = []
        for d in db.query(Document).all():
            body = (d.content or "").strip()
            if not body:
                # structured batches (CDR/KYC/stats) have no narrative; index the title only
                out.append(Passage(d.id, d.source_type, d.title, d.title))
                continue
            # one passage per document, plus overflow chunks for long narratives
            for i in range(0, min(len(body), max_chars * 3), max_chars):
                chunk = body[i: i + max_chars]
                if len(chunk) < 40:
                    break
                out.append(Passage(d.id, d.source_type, d.title, f"{d.title}. {chunk}"))
        return out

    def build(self, db: Session, force: bool = False) -> dict:
        if not self.available():
            return {"status": "unavailable", "reason": self.load_error or "fastembed not installed"}
        count = db.query(Document).count()
        if not force and self._vectors is not None and count == self._doc_count:
            return {"status": "cached", "passages": len(self._passages), "documents": count}
        passages = self._build_passages(db)
        if not passages:
            self._vectors, self._passages, self._doc_count = None, [], count
            return {"status": "empty", "documents": 0}
        try:
            vecs = self.embed([p.text for p in passages])
        except Exception as exc:
            self.load_error = str(exc)
            log.warning("semantic index unavailable: %s", exc)
            return {"status": "unavailable", "reason": str(exc)}
        with self._lock:
            self._vectors, self._passages, self._doc_count = vecs, passages, count
        return {"status": "ok", "passages": len(passages), "documents": count, "dim": int(vecs.shape[1]), "model": MODEL_NAME}

    def invalidate(self):
        self._doc_count = -1

    def ready(self) -> bool:
        """True when a query can be answered without blocking on a model download or an index build."""
        return self._vectors is not None and self.load_error is None

    def warm(self, session_factory) -> None:
        """Build the index off the request path.

        First use downloads a ~130 MB ONNX model and embeds every document, which is a minute or
        two. Doing that inside an analyst's first question looks like a hang, so the API warms the
        index on startup and callers that arrive early fall back to keyword search.
        """
        if not self.available() or self._warming:
            return
        self._warming = True

        def run():
            db = session_factory()
            try:
                res = self.build(db)
                log.info("semantic index warm: %s", res)
            except Exception as exc:
                log.warning("semantic warm-up failed: %s", exc)
            finally:
                db.close()
                self._warming = False

        threading.Thread(target=run, name="semantic-warm", daemon=True).start()

    # ------------------------------------------------------------------ query
    def search(self, db: Session, query: str, limit: int = 10, source_type: str | None = None) -> dict:
        state = self.build(db)
        if state["status"] not in ("ok", "cached"):
            return {"status": state["status"], "reason": state.get("reason", ""), "results": []}
        q = self.embed([query])[0]
        sims = self._vectors @ q
        order = np.argsort(-sims)
        seen: dict[str, float] = {}
        results = []
        for i in order:
            p = self._passages[i]
            if source_type and p.source_type != source_type:
                continue
            if p.document_id in seen:  # best passage per document
                continue
            seen[p.document_id] = float(sims[i])
            results.append({"document_id": p.document_id, "source_type": p.source_type, "title": p.title,
                            "score": round(float(sims[i]), 4), "snippet": p.text[:280]})
            if len(results) >= limit:
                break
        return {"status": "ok", "query": query, "model": MODEL_NAME, "results": results}

    def similar_documents(self, db: Session, document_id: str, limit: int = 8) -> dict:
        state = self.build(db)
        if state["status"] not in ("ok", "cached"):
            return {"status": state["status"], "results": []}
        idxs = [i for i, p in enumerate(self._passages) if p.document_id == document_id]
        if not idxs:
            return {"status": "not_found", "results": []}
        q = self._vectors[idxs].mean(axis=0)
        q /= max(float(np.linalg.norm(q)), 1e-9)
        sims = self._vectors @ q
        seen, results = {document_id}, []
        for i in np.argsort(-sims):
            p = self._passages[i]
            if p.document_id in seen:
                continue
            seen.add(p.document_id)
            results.append({"document_id": p.document_id, "source_type": p.source_type, "title": p.title,
                            "score": round(float(sims[i]), 4), "snippet": p.text[:280]})
            if len(results) >= limit:
                break
        return {"status": "ok", "document_id": document_id, "results": results}

    def status(self) -> dict:
        return {"available": self.available(), "fastembed_installed": FASTEMBED_AVAILABLE, "model": MODEL_NAME,
                "indexed_passages": len(self._passages), "ready": self.ready(), "building": self._warming,
                "error": self.load_error}


semantic_index = SemanticIndex()
