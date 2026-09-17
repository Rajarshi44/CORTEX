## 2026-09-17T20:25:50Z

You are worker_m1_fix, a specialized implementation worker.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m1_fix`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Python environment: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe`
Pytest: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your assigned task: Milestone M1 — Demo Loader Fixes & Call Detail Records (R3, R6-part)

1. Inspect `backend/app/ingestion/load_demo_case.py` and `demo-case-data/02_relationships_edges.csv`:
   - Currently, `REL_TYPE = {"CONTROLS": "OWNS_ACCOUNT", ...}` indiscriminately converts all `CONTROLS` edges to `OWNS_ACCOUNT`. For example, P005 (Rahul) -> P006 (Amit Verma) in rows E019 and E020 becomes `OWNS_ACCOUNT`, which incorrectly represents Rahul owning student mules as accounts!
   - In `load_demo_case.py`, implement contextual edge mapping for `CONTROLS` based on the target entity type:
     - Target is PERSON or ORGANIZATION -> `CONTROLS` (command structure edge).
     - Target is BANK_ACCOUNT or CRYPTO_WALLET -> `OWNS_ACCOUNT`.
     - Target is PHONE or SIM -> `USES_PHONE`.
   - In `backend/app/graph/analytics.py`: ensure `DIRECT_WEIGHTS` includes `"CONTROLS": 3.0` so that command structure edges between actors are properly weighted in actor projection.

2. Create `demo-case-data/09_cdr.csv`:
   - Include realistic CDR records with columns:
     `call_id,caller_phone,callee_phone,call_time,duration_sec,call_type,sub_network,is_international`
   - Include:
     - Regular calls between suspect phones: PH001 (+919999999991), PH002 (+919999999992), PH003 (+919999999993), PH004 (+919999999994), PH005 (+919999999995).
     - Night calls (between 23:00 and 05:00) so `night_activity` detector detects night calls.
     - A call burst cluster (frequent calls within a 6-hour window) so `call_bursts` detector detects a burst.
     - An international call to/from a foreign number (e.g. +971501234567) so `international` detector detects foreign calls.
   - Update `backend/app/ingestion/load_demo_case.py` to:
     - Read `09_cdr.csv` (if present in `demo-case-data`).
     - Ingest each call as a `TimelineEvent` with `kind="CALL"`, `occurred_at`, `entity_ids=[caller_phone_id, callee_phone_id]`, `details={"caller": ..., "callee": ..., "duration": ..., "night": ...}`.
     - Add `CALLED` edge in the graph between the phone nodes.

3. Verification:
   - Run demo loader:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe" -m app.ingestion.load_demo_case`
     (with Cwd="c:\Users\NIRJHAR BARMA\Desktop\batcave\backend", and environment CNA_DATABASE_URL="sqlite:///./demo.db", CNA_DEFAULT_CORPUS="none").
   - Write automated pytest tests in `backend/tests/test_m1_loader.py` that verify:
     a) P005 -> P006 edge has `rel_type == "CONTROLS"` in the graph and DB.
     b) P001 -> A002 edge has `rel_type == "OWNS_ACCOUNT"`.
     c) P001 -> PH002 edge has `rel_type == "USES_PHONE"`.
     d) Calls from `09_cdr.csv` are loaded into `TimelineEvent` with `kind == "CALL"`.
     e) Instantiate `AnomalyDetector` on the graph/db and verify that `call_bursts()`, `night_activity()`, or call detectors fire alerts.
   - Execute the test with:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m1_loader.py -v`
   - Ensure all tests pass with 100% success.

4. Handoff:
   - Write `handoff.md` and `progress.md` in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m1_fix\`.
   - Send a message to orchestrator with your results.

## 2026-09-17T20:43:48Z

**Context**: Milestone M1 (Demo Loader Fixes & CDR)
**Content**: Checking in on progress. Noticed `09_cdr.csv` has been created. Are you currently updating `load_demo_case.py` and `analytics.py`?
**Action**: Please share current status and any blockers.
