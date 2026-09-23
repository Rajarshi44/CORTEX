## 2026-09-23T14:21:28Z
You are worker_m9_impl, an implementation worker for Milestone M9 (CORTEX SIH 2026 Demo Preparation & Rebranding: Requirements R1 through R5).
Your working directory is: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m9_impl`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Orchestrator conversation ID: `afb5f31a-635c-4f1f-a04e-bc5395058e32`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Input Documents:
Read these three handoff reports before implementing:
1. `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_rebrand_r1\handoff.md` (exact lines and replacements for R1 branding removal across 16 files)
2. `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_data_r2_r3\handoff.md` (exact appendable CSV lines for R2 real Indian cybercrime cases & R3 case documents)
3. `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_chart_search_r4_r5\handoff.md` (exact React component code for R4 Chart search bar & R5 ingestion commands)

Your Tasks:
1. Execute R1 (Branding Removal):
   - In `backend/app/api/routes_graph.py` and `cortex-enterprise/backend/app/api/routes_graph.py`:
     Update `sheet_identity()` in all 3 branches (demo, unverified, real):
     title: "National Cyber Crime Investigation Corpus", code: "NCIC-2026", subtitle: "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"
   - In `backend/app/ingestion/load_demo_case.py`:
     SHEET_TITLE = "National Cyber Crime Investigation Corpus", SHEET_SUBTITLE = "Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"
     Update the watch notes on Rahul (line 149) to reference "beneficiary of the student mule ring".
   - In `backend/app/ai/demo_fallback.py`:
     Replace all narrative references to "CyberHawk" / "CyberHawk 2.0" with references to the student mule ring, IFSO investigation, or specific persons/entities.
   - In `backend/tests/test_m3_m6_tagging_map.py` and `cortex-enterprise/backend/tests/test_m3_m6_tagging_map.py`:
     Update assertions to check title == "National Cyber Crime Investigation Corpus", code == "NCIC-2026", subtitle matching "Cyber Crime Branch / IFSO".
   - In `backend/tests/test_m2_victim_protection.py`:
     Update case_name to "NCIC Investigation Brief".
   - In `demo-case-data/01_entities_nodes.csv`:
     Rename entity O003 to "Student Mule Ring".
     Replace all occurrences of "CyberHawk 2.0 Operation" with "NCIC Investigation" and "CyberHawk 2.0 Bust" with "NCIC Arrest" in the last column.
   - In `demo-case-data/05_case_documents.csv`:
     Update DOC-005 title to "FIR No. [Illustrative: 112/2025] - Student mule operation" and source_name to "Special Cell IFSO HQ".
   - In `demo-case-data/07_timeline_events.csv`, `08_geo_locations.csv`, `add_locations.py`, `generate_2000.py`, `README.md`, `demo-case-data/README.md`, `run_demo.ps1`:
     Apply all replacements detailed in `explorer_rebrand_r1\handoff.md`.
   - Run verification in terminal:
     `git grep -i "cyberhawk"` or `rg -i "cyberhawk" backend frontend-next demo-case-data` to confirm ZERO occurrences remain in backend/, frontend-next/, demo-case-data/.

2. Execute R2 & R3 (Real Indian Cyber Crime Data & Documents):
   - From `explorer_data_r2_r3\handoff.md`:
     Append the 64 new entity rows (P4001..P4044, A4001..A4016, O301..O310, PH301..PH312) to `demo-case-data/01_entities_nodes.csv`.
     Append the 36 new edge rows (E071..E106, including 6 cross-case links) to `demo-case-data/02_relationships_edges.csv`.
     Append the 12 new transactions (TXN202300101..TXN202300112) to `demo-case-data/03_financial_transactions.csv`.
     Append the 9 new documents (DOC-CH2-001..003, DOC-JAM-001..003, DOC-LOAN-001..003) to `demo-case-data/05_case_documents.csv`.
   - In `backend/app/ingestion/load_demo_case.py`:
     Update `DOC_KIND` dictionary mapping to properly recognize "FIR", "ARREST_MEMO", "NEWS", and "JUDGMENT".

3. Execute R4 (Chart Search Bar):
   - In `frontend-next/src/app/(sheet)/chart/page.tsx`:
     Insert the live entity search input and dropdown component as the first child of the control bar `<div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">` before `<span className="label label-ink">`.
     Follow exact styling, `searchQuery` and `searchOpen` state, node label filtering (query >= 2), max 8 items, click `select(node.id)`, Escape key handling, and 150ms blur timeout.
   - Run `npx tsc --noEmit` in `frontend-next/` and verify zero errors.

4. Execute R5 (Database Re-ingestion & Full Test Verification):
   - Run `cd backend && .\venv\Scripts\python.exe -m app.ingestion.load_demo_case`
   - Verify entity count is strictly higher than 5612:
     `.\venv\Scripts\python.exe -c "from app.db import SessionLocal; from app.db import Entity; db=SessionLocal(); print('Entities:', db.query(Entity).count())"`
   - Verify document query:
     `.\venv\Scripts\python.exe -c "from app.db import SessionLocal; from app.db import Document; db=SessionLocal(); print('FIR/Arrest docs:', db.query(Document).filter(Document.source_type.in_(['FIR', 'ARREST_MEMO'])).count())"` (must be >= 3)
   - Run backend test suite:
     `.\venv\Scripts\pytest.exe -k "not test_live_agent_db_and_llm_e2e"`
     Must pass 100%!
   - Run enterprise tests:
     `.\venv\Scripts\pytest.exe -v ..\cortex-enterprise\backend\tests\test_m3_m6_tagging_map.py`
     Must pass 100%!

5. Write your complete handoff report to `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m9_impl\handoff.md`. Include all command outputs and verification evidence.
6. Send a completion message to the orchestrator (`afb5f31a-635c-4f1f-a04e-bc5395058e32`).
