## 2026-09-15T20:51:00Z
You are Worker Backend for cortex-enterprise Criminal Network Analysis (CNA).
Your working directory is: c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_backend
Target directory: c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise\backend

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Key Objectives:
1. Ingestion Pipeline & Entity Resolution (R1, R2):
   - Review and wire `cortex-enterprise/backend/app/ingestion/` (`load_demo_case.py`, `pipeline.py`, `resolution.py`) to the API.
   - Expose/verify REST API endpoint (`POST /api/ingest/demo` or `POST /api/ingest/case`) that ingests sample dataset (`cortex-enterprise/demo-case-data` CSVs: entities, relationships, transactions, aliases, timeline) and returns HTTP 200 or 201 without errors.
   - Ensure entity resolution handles aliases (e.g. 'Rahul' alias 'Happy' in `06_aliases_unresolved.csv`) and queries to `/api/entities/{id}` return a unified entity profile with all aliases and relationships merged.
   - Create and run `tests/test_ingestion_pipeline.py`:
     * Test ingests sample dataset and returns HTTP 200/201 without errors.
     * Test queries API for specific entity and verifies resolved aliases return a unified entity profile.

2. Graph Analytics Engine (R3):
   - Review/extend `cortex-enterprise/backend/app/graph/analytics.py` and `fastmetrics.py`.
   - Implement community detection (Louvain/Leiden) and centrality (PageRank, betweenness, degree). Ensure scalable execution on mock dataset >= 500 nodes returning ranked results in < 2.0 seconds.
   - Implement proximity risk calculation: proactively flag first-time offenders (a node with 0 historical crimes/charges but direct links to 3 high-suspicion nodes receives a high "proximity risk" score).
   - Create and run `tests/test_graph_analytics.py`:
     * Test runs community detection and centrality on mock dataset >= 500 nodes and returns ranked results within 2 seconds.
     * Test verifies a node with 0 historical crimes but direct links to 3 high-suspicion nodes receives a high proximity risk score (first-time offender flagging).

3. Automated Insights & Contradiction Detection (R4):
   - Implement/extend contradiction detection: cross-reference timeline events (e.g. Person A claims to be at Location X, but CDR data places them at Location Y at the same time) and assert a "CONTRADICTION" alert is generated.
   - Implement ghost node / anti-forensic detection: when two highly clustered communities lack a direct bridge, assert a "GHOST_NODE" or "ANTI_FORENSIC" alert is generated.
   - Create and run `tests/test_insights.py`:
     * Test feeds contradictory timeline data (claimed Location X vs CDR Location Y) and asserts CONTRADICTION alert generated.
     * Test asserts ghost node / anti-forensic alert generated when two highly clustered communities lack a direct bridge.

4. Run all tests with pytest using the python virtual environment in `c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise\backend\venv`:
   `venv\Scripts\python -m pytest tests/test_ingestion_pipeline.py tests/test_graph_analytics.py tests/test_insights.py -v`
   Ensure all tests pass 100%.

5. Update `progress.md` throughout execution.
6. Write your detailed implementation report to `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_backend\changes.md` and write a self-contained `handoff.md` with exact commands and passing test output.
7. Notify parent via send_message when complete.
