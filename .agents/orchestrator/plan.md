# CORTEX SIH 2026 Demo Preparation & Rebranding Plan (Milestone M9)

## Overview
Execution plan for Milestone M9 (User Request 2026-09-23T13:50:27Z):
1. R1: Remove all "Operation CyberHawk 2.0" branding across the codebase with NO replacement operation name. Neutral title: "National Cyber Crime Investigation Corpus", code: "NCIC-2026".
2. R2: Add 3 real Indian cyber crime cases (Operation Chakra-II, Jamtara Phishing Syndicate, Chinese Loan App Fraud) to CSV files with >=45 new entities, 10-12 transactions, >=5 cross-case links.
3. R3: Populate Sources tab with >=8 realistic document entries in `05_case_documents.csv` (>=3 FIR/ARREST_MEMO).
4. R4: Add live entity search bar to Chart page in `frontend-next/src/app/(sheet)/chart/page.tsx`.
5. R5: Re-ingest database, verify higher entity count, verify all tests pass.

---

## Detailed Phases

### Phase 1: Exploration & Impact Analysis (3 Parallel Explorers)
- **Explorer 1 (`explorer_rebrand_r1`)**:
  - Scan entire repository for `CyberHawk`, `Operation CyberHawk 2.0`, `OPS-CH2` across `backend/`, `frontend-next/`, `demo-case-data/`, `cortex-enterprise/`, `tests/`, `README.md`, docs.
  - Detail exact files and lines needing update.
  - Verify requirement: Title `"National Cyber Crime Investigation Corpus"`, Code `"NCIC-2026"`, Subtitle `"Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"`.
  - Check `demo_fallback.py` narratives, `01_entities_nodes.csv` tag replacements (`CyberHawk 2.0 Operation` -> `NCIC Investigation`, `CyberHawk 2.0 Bust` -> `NCIC Arrest`), test assertions.
- **Explorer 2 (`explorer_data_r2_r3`)**:
  - Analyze current CSVs in `demo-case-data/` (`01_entities_nodes.csv`, `02_relationships_edges.csv`, `03_financial_transactions.csv`, `05_case_documents.csv`).
  - Check current highest IDs and record counts.
  - Draft >=45 new entity definitions across:
    - Case A: Operation Chakra-II (CBI/Interpol)
    - Case B: Jamtara Phishing Syndicate
    - Case C: Chinese Loan App Fraud
  - Draft 10-12 transactions in `03_financial_transactions.csv`.
  - Draft >=5 cross-case relationships in `02_relationships_edges.csv`.
  - Draft >=8 realistic document entries in `05_case_documents.csv` (>=3 FIR or ARREST_MEMO).
- **Explorer 3 (`explorer_chart_search_r4_r5`)**:
  - Inspect `frontend-next/src/app/(sheet)/chart/page.tsx` for control bar structure.
  - Design search input and dropdown component matching exact styling and behavioral requirements.
  - Inspect database ingestion pipeline in `backend/app/ingestion/load_demo_case.py` and test execution requirements.
  - Document pre-task entity count and test suite baseline.

### Phase 2: Implementation (Worker)
- Dispatch single unified Worker (`worker_m9_impl`):
  - Execute R1 branding elimination and CSV find-replace.
  - Execute R2 & R3 CSV data population with validated schemas.
  - Execute R4 Chart search bar addition in `chart/page.tsx`.
  - Execute R5 Database re-ingestion (`python -m app.ingestion.load_demo_case`).
  - Verify:
    - `grep -r "CyberHawk"` returns 0 results.
    - Entity count is higher than pre-task.
    - `SELECT COUNT(*) FROM documents WHERE source_type IN ('FIR', 'ARREST_MEMO') >= 3`.
    - Backend test suite passes.
    - Frontend build succeeds.

### Phase 3: Review & Challenge (2 Reviewers, 2 Challengers)
- **Reviewer 1**: Review R1 (branding elimination across all repos/branches) and R4 (Chart search UI semantics and responsiveness).
- **Reviewer 2**: Review R2 & R3 (CSV integrity, schema adherence, Indian cybercrime authenticity, cross-case links).
- **Challenger 1**: Empirical verification of search bar behavior, query filtering, and frontend compilation.
- **Challenger 2**: Empirical verification of database contents, entity count increase, document types, and backend test passes.

### Phase 4: Forensic Integrity Audit
- Dispatch `teamwork_preview_auditor` to audit authenticity:
  - Verify no hardcoded test responses or facades.
  - Verify real entity and document rows in database and CSVs.
  - Verify zero remaining CyberHawk mentions.

### Phase 5: Sentinel Victory Reporting
- Send victory message to Sentinel parent for final Victory Audit trigger.
