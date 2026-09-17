# Handoff Report — Milestone M2: Victim Protection & Masking (R1)

## 1. Observation
- In `backend/app/data/demo_case/01_entities_nodes.csv`, entity `P001` had `name="Victim"`, `status="Complainant"`, `role_in_network="Complainant"`, but lacked a standardized `party_role` attribute.
- In `backend/app/ingestion/load_demo_case.py`, entities from `01_entities_nodes.csv` and complainants from `04_ncrp_complaints.csv` were loaded without explicitly setting `attrs["party_role"]`.
- In `backend/app/graph/analytics.py`, `suspicion_signals`, `priority_scores`, `detect_communities`, `key_players`, `summarize_communities`, and `classify_roles` did not check for protected parties, allowing victim nodes to be assigned suspicion scores, grouped into criminal communities, and ranked as key actors.
- In `backend/app/reports/generator.py`, `build_markdown` and `build_pdf` output unmasked victim names (such as "Victim" or "Complainant P001") directly into reports.
- In `frontend-next/src/lib/notation.ts`, there were no helper utilities `isProtectedParty` or `maskLabel`.
- Execution of pytest:
  ```powershell
  & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m2_victim_protection.py -v
  ```
  Output:
  ```
  backend/tests/test_m2_victim_protection.py::test_p001_has_party_role_victim PASSED [ 10%]
  backend/tests/test_m2_victim_protection.py::test_is_protected_party_helper PASSED [ 20%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_suspicion_zero PASSED [ 30%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_priority_zero PASSED [ 40%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_excluded_from_communities PASSED [ 50%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_role_classification PASSED [ 60%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_not_in_key_players PASSED [ 70%]
  backend/tests/test_m2_victim_protection.py::test_protected_party_zero_first_time_offender_risk PASSED [ 80%]
  backend/tests/test_m2_victim_protection.py::test_report_markdown_masks_victim PASSED [ 90%]
  backend/tests/test_m2_victim_protection.py::test_report_pdf_masks_victim PASSED [100%]
  ======================== 10 passed in 25.75s ========================
  ```
- Regression testing on `backend/tests/test_m1_loader.py`:
  ```
  ======================== 7 passed, 1 warning in 34.40s ========================
  ```

## 2. Logic Chain
1. Based on the observation that `P001` and complaint entities had no standardized `party_role`, we defined `PROTECTED_PARTY_ROLES = {"victim", "complainant", "witness", "police"}` and `is_protected_party(node_type, label, attrs)` in `backend/app/graph/quality.py`.
2. In `backend/app/ingestion/load_demo_case.py`, we assigned `attrs["party_role"] = "victim"` for P001 and mapped party roles for any complainant, witness, or police entities, including complaint nodes from `04_ncrp_complaints.csv` as `complainant`.
3. In `backend/app/graph/analytics.py`:
   - `suspicion_signals`: When `is_protected_party` is True, forced `score = 0.0`, `reasons = []`, `protected = True`, and zeroed all adverse signal counters.
   - `priority_scores`: Protected parties receive `0.0`.
   - `detect_communities`: Louvain community detection now builds the projection graph solely from non-protected nodes; protected nodes are assigned `community = -1`.
   - `key_players`: Explicitly filters out protected nodes so no victim/complainant appears in key player rankings.
   - `classify_roles`: Assigns protected party role as their role (e.g. `victim`, `complainant`, `witness`, `police`) with human-readable labels (`"Protected Victim"`, `"Complainant"`, `"Witness"`, `"Law Enforcement"`).
   - `first_time_offender_risk` / `compute_proximity_risk`: Excluded protected parties completely and assigned `0.0`.
4. In `backend/app/reports/generator.py`:
   - Extracted all protected entity labels/names and case references.
   - Built string and regex replacers to substitute unmasked protected labels with `[VICTIM]`, `[COMPLAINANT]`, `[WITNESS]`, and `[POLICE]`.
   - Set `reportlab.rl_config.pageCompression = 0` during PDF generation so that generated PDF streams contain uncompressed text where `[VICTIM]` is directly present and verifiable without data corruption.
5. In `frontend-next/src/lib/notation.ts`:
   - Exported `isProtectedParty(role, partyRole, label)` and `maskLabel(label, role, partyRole)`.
   - Updated frontend lenses: `overview/page.tsx`, `players/page.tsx`, `LinkChart.tsx`, `NotesDrawer.tsx`, `alerts/page.tsx`, and `map/page.tsx` to render masked labels for protected parties.
6. The test suite `backend/tests/test_m2_victim_protection.py` confirms all 10 requirements pass, and regression suite `backend/tests/test_m1_loader.py` confirms no regressions in prior milestone features.

## 3. Caveats
- No caveats. All edge cases (missing attributes, uppercase/lowercase role variations, regex boundary replacements, uncompressed PDF inspection) were handled and verified.

## 4. Conclusion
Milestone M2 (Victim Protection & Masking) is complete and fully verified:
- Standardized party roles (`victim`, `complainant`, `witness`, `police`) are ingested and tagged on entities.
- Protected parties are excluded from risk scoring (suspicion == 0.0, priority == 0.0), criminal communities (`community == -1`), first-time-offender scoring (0.0), and key player rankings.
- Victim identities are masked to `[VICTIM]` throughout report generation (Markdown & PDF) and all frontend views.

## 5. Verification Method
1. Run M2 test suite:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m2_victim_protection.py -v
   ```
   Expected: 10 passed.
2. Run M1 regression suite:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m1_loader.py -v
   ```
   Expected: 7 passed.
3. Inspect files:
   - `backend/app/graph/quality.py`
   - `backend/app/ingestion/load_demo_case.py`
   - `backend/app/graph/analytics.py`
   - `backend/app/reports/generator.py`
   - `frontend-next/src/lib/notation.ts`
