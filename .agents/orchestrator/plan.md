# Orchestrator Execution Plan: cortex-enterprise

## Overview
This plan governs the execution of the cortex-enterprise project per the user requirements R1-R5 and acceptance criteria.
We utilize the Project Pattern: Explorer -> Worker -> Reviewer -> Challenger -> Forensic Auditor per milestone, and dual-track implementation + testing.

## Milestone Plan

### Milestone 1: Survey & Scaffolding (In Progress)
- Survey existing `batcave/backend`, `batcave/frontend-next`, and `batcave/demo-case-data`.
- Create project directory `cortex-enterprise/` containing `backend/`, `frontend/`, and `data/`.
- Ensure directory layout, virtual environment readiness, and base configurations are in place.

### Milestone 2: Ingestion Pipeline & Entity Resolution (R1, R2)
- Target: `cortex-enterprise/backend/app/ingestion/`
- CSV and unstructured data parsing (demo-case-data with entities, relationships, transactions, aliases, timeline).
- Entity resolution engine (alias matching, e.g. "Rahul alias Happy", deduplication).
- API routes `/api/ingest` and `/api/entities/{id}`.
- Automated tests: `test_ingestion_pipeline.py` testing sample dataset ingestion (HTTP 200/201) and query for resolved alias returning unified profile.

### Milestone 3: Graph Analytics & Proximity Risk (R3)
- Target: `cortex-enterprise/backend/app/graph/`
- Centrality metrics (degree, betweenness, PageRank) and Community detection (Louvain / Leiden).
- Benchmark performance: run on >= 500 nodes in < 2.0 seconds.
- Proximity risk engine: node with 0 historical crimes but direct links to 3 high-suspicion nodes receives high proximity risk score (first-time offender flagging).
- Automated tests: `test_graph_analytics.py`.

### Milestone 4: Automated Insights & Contradiction Detection (R4)
- Target: `cortex-enterprise/backend/app/insights/`
- Timeline narrative contradiction detection (location claim vs CDR tower hit).
- Ghost node / anti-forensic alert detection (two highly clustered communities lacking direct bridge).
- API routes `/api/insights/alerts`.
- Automated tests: `test_insights.py`.

### Milestone 5: Full-Stack UI Integration (R5)
- Target: `cortex-enterprise/frontend/`
- Adapt Next.js frontend to connect to the backend REST API.
- Visual graph display, alert triage dashboard, entity explorer view.
- Verify clean compilation/build with zero fatal errors.
- Integration test verifying UI loads and connects to backend.

### Milestone 6: Adversarial Hardening & Final Forensic Audit
- Dual-track complete pass: all automated tests run and pass 100%.
- Challenger stress-testing (edge cases, adversarial inputs).
- Forensic Auditor audit against cheating, dummy mocks, and hardcoded values.
- Claim completion to Sentinel for victory audit.
