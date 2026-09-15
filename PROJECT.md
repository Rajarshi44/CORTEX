# Project: cortex-enterprise

## Overview
cortex-enterprise is an enterprise-grade Criminal Network Analysis (CNA) system featuring scalable data ingestion, enterprise knowledge graph with entity resolution, high-performance graph analytics (influence, suspicion, proximity risk), automated insight & contradiction detection, and a modern web dashboard.

## Architecture
- **Ingestion Microservice / Layer (`backend/app/ingestion/`)**:
  - Ingestion pipeline processing structured CSVs (CDR, banking, KYC, cases) and unstructured text (FIR, news, court documents).
  - Entity extraction (rule-based and neural NER) and schema normalizer.
  - Entity Resolution module (`resolution.py`) resolving aliases, nicknames, and fragmented identities into unified canonical entity profiles.
- **Knowledge Graph Core (`backend/app/graph/`)**:
  - Graph Store (`store.py`) maintaining multi-graph representations, edge accumulation, and projections.
  - Fast Metrics (`fastmetrics.py`) using rustworkx / NetworkX for ultra-fast community detection (Louvain) and centralities (betweenness, degree, eigenvector, PageRank).
  - Analytical Engine (`analytics.py`) computing structural influence, evidentiary suspicion, and proximity risk (first-time offender scoring based on links to high-suspicion nodes).
  - Anomaly & Insight Engine (`anomalies.py`):
    - Timeline event contradiction detector (cross-referencing statement vs. technical CDR/financial locations).
    - Deliberate communication gaps / ghost nodes / anti-forensic pattern detection (clustering bridge voids, burner networks).
- **API Surface (`backend/app/api/`)**:
  - FastAPI RESTful API exposing entity dossiers, graph queries, ingestion endpoints, contradiction alerts, and forensic analytics.
- **Frontend Console (`frontend-next/`)**:
  - Next.js 16 + TypeScript + Tailwind CSS UI dashboard connecting to FastAPI.
  - Graph visualization (Sigma.js / WebGL), entity search/profile explorer, alert inspector.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Exploration & Scaffolding | Analyze batcave assets, scaffold cortex-enterprise directory, test environment | None | IN_PROGRESS |
| M2 | Ingestion & Entity Resolution | Structured/unstructured ingestion, unified entity profiles, test_ingestion_pipeline.py | M1 | PLANNED |
| M3 | Graph Analytics & Proximity Risk | Centrality, Louvain, >= 500 node benchmark <= 2s, first-time offender proximity risk | M1 | PLANNED |
| M4 | Insights & Contradiction Engine | Timeline contradiction detection, ghost node / anti-forensic alerts | M2, M3 | PLANNED |
| M5 | Full-Stack UI & Integration | Build frontend-next in cortex-enterprise, e2e dashboard-backend integration test | M1, M2, M3, M4 | PLANNED |
| M6 | Acceptance Verification & Victory Audit | Run all automated test scripts, Challenger validation, Forensic Audit | M1-M5 | PLANNED |

## Interface Contracts
### Ingestion API
- `POST /api/ingest/file` or `POST /api/ingest/structured`: accepts CSV/text data, returns HTTP 200/201.
- `GET /api/graph/entities/{id}` or `GET /api/graph/entity?name=...`: returns unified profile with resolved aliases and consolidated records.

### Graph Analytics API
- `GET /api/graph/analytics` or internal `compute_graph_analytics(graph)`: returns communities and centrality metrics within < 2 seconds for >= 500 nodes.
- `GET /api/graph/proximity-risk`: returns proximity risk scores, flagging 0-crime nodes connected to 3+ high-suspicion hubs as high proximity risk.

### Insights & Contradiction API
- `GET /api/forensics/contradictions` or alert register: flags CONTRADICTION alert when statement location != CDR location.
- `GET /api/forensics/anti-forensics` or alert register: flags GHOST_NODE / ANTI_FORENSIC alert when clustered communities lack direct communication bridge.

## Code Layout
- Target Workspace: `c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise`
  - `backend/`: FastAPI application, virtual environment, tests.
  - `frontend-next/`: Next.js frontend application.
  - `demo-case-data/`: Ingestion sample datasets and ground truth.
  - `backend/tests/`: Automated test suite (`test_ingestion_pipeline.py`, `test_graph_analytics.py`, `test_contradictions.py`, `test_ghost_nodes.py`, `test_e2e_integration.py`).
