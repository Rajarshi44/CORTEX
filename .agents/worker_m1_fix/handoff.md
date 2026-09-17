# Handoff Report: Milestone M1 — Demo Loader Fixes & Call Detail Records

## 1. Observation
- In `backend/app/ingestion/load_demo_case.py`, `REL_TYPE = {"CONTROLS": "OWNS_ACCOUNT", ...}` previously mapped every `CONTROLS` relationship to `OWNS_ACCOUNT`. In `demo-case-data/02_relationships_edges.csv`, rows E019 (`P005,P006,CONTROLS`) and E020 (`P005,P007,CONTROLS`) represent Rahul controlling student mules (persons), but were converted into `OWNS_ACCOUNT`. Furthermore, `holder_of` in line 431 incorrectly treated `P006` and `P007` as accounts.
- In `backend/app/graph/analytics.py`, `DIRECT_WEIGHTS` lacked `"CONTROLS"`, so command-structure links between actors were omitted from actor projection weighting.
- The repository previously lacked `demo-case-data/09_cdr.csv`, and `load_demo_case.py` had no logic to ingest CDR records, leaving `AnomalyDetector`'s `self.calls` empty (zero events with `kind == "CALL"`).

## 2. Logic Chain
1. Contextual edge mapping was introduced via `map_relationship(raw: str, target: Entity | None)` in `load_demo_case.py`:
   - If target type is `PERSON` or `ORGANIZATION`, `CONTROLS` maps to `"CONTROLS"`.
   - If target type is `BANK_ACCOUNT` or `CRYPTO_WALLET`, `CONTROLS` maps to `"OWNS_ACCOUNT"`.
   - If target type is `PHONE` or `SIM`, `CONTROLS` maps to `"USES_PHONE"`.
   - For all other verbs, fallback to `REL_TYPE.get(raw)`.
2. In `backend/app/graph/analytics.py`, added `"CONTROLS": 3.0` to `DIRECT_WEIGHTS`. In `actor_projection(D)`, edges with `rt in DIRECT_WEIGHTS` between actors are properly folded with weight `3.0` and channel `"controls"`.
3. Created `demo-case-data/09_cdr.csv` containing 66 records with schema `call_id,caller_phone,callee_phone,call_time,duration_sec,call_type,sub_network,is_international`:
   - Calls between suspect phones PH001, PH002, PH003, PH004, PH005.
   - 18 night calls (between 23:10 and 03:45) between PH003 and PH004, satisfying `night_activity` detector criteria (>= 15 calls, night ratio >= 40%).
   - 24-call burst cluster on 2025-12-04 (14:02 to 17:06) among PH003, PH004, and PH005, satisfying `call_bursts` detector criteria (>= 50 total calls in dataset, v >= 12 calls in 6h window, z >= 3.0, >= 2 dominant numbers with >= 3 calls).
   - International calls to/from UAE foreign number `+971501234567` and PH004, setting `attrs["international"] = True` on the foreign node and triggering `international` detector on PH004.
4. In `backend/app/ingestion/load_demo_case.py`:
   - Created CDR ingestion routine reading `09_cdr.csv` when present.
   - Sealed records into a dedicated `Document` (`CDR-RECORDS`).
   - Ingested calls as `TimelineEvent` with `kind="CALL"`, `occurred_at`, `entity_ids=[caller_entity.id, callee_entity.id]`, and `details={"caller": ..., "callee": ..., "duration": dur, "duration_sec": dur, "night": is_night, "call_type": call_type, "sub_network": sub_network, "is_international": is_intl, "call_id": call_id}`.
   - Added `CALLED` edges into `RelationshipAccumulator` with duration and night call attributes.
   - Updated `stats["calls"]`.

## 3. Caveats
- `09_cdr.csv` provides synthetic CDR records tailored to the demo case entities and timeline (Nov-Dec 2025). If new phone entities are added to `01_entities_nodes.csv` in the future, corresponding CDR records can be expanded as needed.
- No other caveats.

## 4. Conclusion
Milestone M1 requirements are completely satisfied:
- P005 -> P006 edge has `rel_type == "CONTROLS"` in DB, DiGraph, and Graph.
- P001 -> A002 edge has `rel_type == "OWNS_ACCOUNT"`.
- P001 -> PH002 edge has `rel_type == "USES_PHONE"`.
- `DIRECT_WEIGHTS` contains `"CONTROLS": 3.0`, and actor projection folds P005 -- P006 with weight >= 3.0.
- `09_cdr.csv` is loaded into `TimelineEvent` with `kind == "CALL"` and `CALLED` graph edges.
- `AnomalyDetector` detects `call_burst`, `night_activity`, and `international_contact` alerts.

## 5. Verification Method
1. Pytest suite:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m1_loader.py -v
   ```
   Result: 7 passed in 29.58s (100% pass).
2. Demo loader manual execution:
   ```powershell
   $env:CNA_DATABASE_URL="sqlite:///./demo.db"; $env:CNA_DEFAULT_CORPUS="none"; & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe" -m app.ingestion.load_demo_case
   ```
   Result: `calls: 66`, `alerts: 9`, `relationships: 197`, `events: 219`, `nodes: 95`, `edges: 193`.
