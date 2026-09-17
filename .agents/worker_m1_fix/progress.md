# Progress — Milestone M1 Demo Loader Fixes & CDR

Last visited: 2026-09-18T02:22:30+05:30

## Status: COMPLETED

### Tasks:
- [x] 1. Inspect `backend/app/ingestion/load_demo_case.py`, `demo-case-data/02_relationships_edges.csv`, and `backend/app/graph/analytics.py`
- [x] 2. Update `backend/app/graph/analytics.py` to add `"CONTROLS": 3.0` to `DIRECT_WEIGHTS`
- [x] 3. Create `demo-case-data/09_cdr.csv` with realistic calls, night calls, call bursts, and international calls (66 records)
- [x] 4. Update `backend/app/ingestion/load_demo_case.py` with contextual edge mapping and CDR ingestion
- [x] 5. Run demo loader verification (loaded 66 calls, 9 alerts, 197 relationships)
- [x] 6. Create pytest tests in `backend/tests/test_m1_loader.py` and run with pytest (7/7 passed, 100% success)
- [x] 7. Write `handoff.md` and send completion message to parent
