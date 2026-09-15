## 2026-09-15T20:50:48Z

You are the Implementation Worker for the Criminal Network Analysis (CNA) system project named cortex-enterprise.

Your working directory is:
c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_impl

Target project directory:
c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Python Environment:
Use `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe` (or `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe"` in PowerShell) to run Python commands and pytest.

Your Objectives:
Execute Milestones M1 through M5 in `cortex-enterprise`:

1. Milestone 1: Finalize Scaffolding & Setup
   - Verify `cortex-enterprise/backend`, `cortex-enterprise/frontend`, and `cortex-enterprise/demo-case-data`.
   - Verify `python.exe -c "import app; print('Backend OK')"` succeeds.

2. Milestone 2: Ingestion & Knowledge Graph / Entity Resolution (R1, R2)
   - Ensure the backend RESTful API (FastAPI) properly supports ingestion of structured CSVs (from `demo-case-data`) and unstructured text, and normalizes into knowledge graph entities.
   - Ensure entity resolution correctly links aliases (e.g. "Rahul" alias "Happy") into unified canonical entity profiles.
   - Create and run `cortex-enterprise/backend/tests/test_ingestion_pipeline.py`:
     * Test 1: Ingest sample dataset via API / TestClient and assert HTTP 200/201 without errors.
     * Test 2: Query API for a specific entity and verify that resolved aliases return a unified entity profile.
   - Ensure all tests in `test_ingestion_pipeline.py` pass.

3. Milestone 3: Graph Analytics Engine & Proximity Risk (R3)
   - Ensure graph engine calculates centrality (betweenness, degree, PageRank) and community detection (Louvain/Leiden), plus proximity risk / first-time offender flagging.
   - Create and run `cortex-enterprise/backend/tests/test_graph_analytics.py`:
     * Test 1: Run community detection and centrality algorithms on a dataset of at least 500 nodes and assert execution returns ranked results within 2.0 seconds.
     * Test 2: Verify that a node with 0 historical crimes but direct links to 3 "high-suspicion" nodes receives a high "proximity risk" score (first-time offender flagging).
   - Ensure all tests in `test_graph_analytics.py` pass.

4. Milestone 4: Automated Insights & Contradictions (R4)
   - Ensure timeline narrative contradiction detection (location claim vs CDR placement) and ghost node / anti-forensic detection are functional.
   - Create and run `cortex-enterprise/backend/tests/test_insights.py`:
     * Test 1: Feed contradictory timeline data (e.g., Person A claims to be at Location X, but CDR data places them at Location Y) and assert that a "CONTRADICTION" alert is generated.
     * Test 2: Assert that a "ghost node" or "anti-forensic" alert is generated when two highly clustered communities lack a direct bridge.
   - Ensure all tests in `test_insights.py` pass.

5. Milestone 5: Full-Stack UI Dashboard & Integration (R5)
   - In `cortex-enterprise/frontend`:
     * Check build cleanly: run `npm run build` or verify TypeScript compilation (`npx tsc --noEmit`).
   - Create an integration test `cortex-enterprise/backend/tests/test_e2e_integration.py` verifying that the backend API exposes all necessary endpoints for the dashboard (entities, graph analytics, alerts, proximity risk) and that a client can fetch dashboard data successfully.

6. Run Complete Test Suite:
   - Run `python -m pytest tests/ -v` in `cortex-enterprise/backend` and ensure 100% of test files pass.
   - Document all test results, commands executed, and file paths.

7. Deliverables:
   - Update `.agents/worker_impl/progress.md` with timestamps.
   - Write comprehensive report in `.agents/worker_impl/handoff.md`.
   - Send completion message to parent orchestrator.
