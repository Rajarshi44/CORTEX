## 2026-09-23T14:15:37Z
You are explorer_rebrand_r1_gen3, an exploration agent for Milestone M9 Requirement R1 (Remove all Operation CyberHawk 2.0 branding from the entire codebase with NO replacement operation name).
Your working directory is: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_rebrand_r1_gen3`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Orchestrator conversation ID: `afb5f31a-635c-4f1f-a04e-bc5395058e32`

Your Tasks:
1. Search the ENTIRE codebase for all occurrences of "CyberHawk", "Operation CyberHawk 2.0", "OPS-CH2" across:
   - `backend/app/api/routes_graph.py` (check all 3 branches: demo, unverified, real for `sheet_identity()`)
   - `backend/app/ingestion/load_demo_case.py` (`SHEET_TITLE` and `SHEET_SUBTITLE`)
   - `backend/app/ai/demo_fallback.py` (narrative text referencing CyberHawk)
   - `demo-case-data/01_entities_nodes.csv` (replace `CyberHawk 2.0 Operation` -> `NCIC Investigation`, `CyberHawk 2.0 Bust` -> `NCIC Arrest`)
   - `backend/tests/test_m3_m6_tagging_map.py` (assertion strings)
   - `backend/tests/test_m2_victim_protection.py` (case_name strings)
   - `cortex-enterprise/backend/app/api/routes_graph.py`
   - `cortex-enterprise/backend/tests/test_m3_m6_tagging_map.py`
   - `README.md`
   - Any other files in `backend/`, `frontend-next/`, `demo-case-data/`
2. Specify exact replacements:
   - Returned title: `"National Cyber Crime Investigation Corpus"`
   - Code: `"NCIC-2026"`
   - Subtitle: `"Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"` (API)
   - Loader subtitle: `"Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"`
3. Verify that the acceptance test command:
   `grep -r "CyberHawk" backend/ frontend-next/ demo-case-data/ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.csv"`
   will return ZERO matches when these edits are applied!
4. Write your comprehensive handoff report to `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_rebrand_r1_gen3\handoff.md`.
5. Send a completion message to the orchestrator (`afb5f31a-635c-4f1f-a04e-bc5395058e32`).
