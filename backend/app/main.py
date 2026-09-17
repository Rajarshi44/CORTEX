"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .api import (routes_agent, routes_ai, routes_auth, routes_forensics, routes_graph, routes_ingest,
                  routes_intel, routes_novelty, routes_sources, routes_watch, routes_search)
from .api.deps import analysis_service
from .auth import bootstrap_users
from .config import settings
from .db import Document, SessionLocal, init_db
from .ingestion.pipeline import load_demo_dataset
from .ai.semantic import semantic_index
from .ingestion.real_corpus import load_real_corpus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cna")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        bootstrap_users(db)
        corpus = os.getenv("CNA_DEFAULT_CORPUS", settings.default_corpus).lower()
        if os.getenv("CNA_AUTOLOAD_DEMO", "true").lower() in ("1", "true", "yes") and corpus != "none" and db.query(Document).count() == 0:
            loaded = False
            if corpus == "real":
                log.info("Empty database - building the sheet from public records")
                rep = load_real_corpus(db)
                loaded = rep["records"] > 0
                log.info("Public records loaded: %s sources, %s records in %ss", rep["loaded"], rep["records"], rep["elapsed"])
            if not loaded:
                log.info("Loading bundled demo corpus (Operation Saltwater)")
                stats = load_demo_dataset(db)
                log.info("Demo loaded: %s", stats)
        analysis_service.snapshot(db)
        # Embedding the corpus takes a minute on a cold cache; warm it now so the first
        # investigator question does not appear to hang.
        semantic_index.warm(SessionLocal)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              description="AI-powered criminal network analysis: multi-source ingestion, entity resolution, graph analytics, anomaly detection.")
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for r in (routes_auth.router, routes_ingest.router, routes_graph.router, routes_intel.router, routes_sources.router,
          routes_ai.router, routes_agent.router, routes_forensics.router, routes_watch.router,
          routes_novelty.router, routes_search.router):
    app.include_router(r)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
