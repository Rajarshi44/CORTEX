# Project: CORTEX SIH 2026 Fix, Polish & Rebranding

## Architecture
- **Backend**: FastAPI app in `backend/app` (`main.py`, `api/`, `graph/`, `ingestion/`, `ai/`, `reports/`, `sources/`, `watch/`).
- **Frontend**: Next.js 15 app in `frontend-next/src` (`app/(sheet)/`, `components/`, `lib/`).
- **Data & Ingestion**: `demo-case-data/*.csv` ingested by `backend/app/ingestion/load_demo_case.py`.
- **Analytics & Algorithms**: Heterogeneous graph analytics in `backend/app/graph/` (`analytics.py`, `anomalies.py`, `fastmetrics.py`, `ledger.py`).
- **Investigator AI**: Tool-calling agent in `backend/app/ai/` (`agent.py`, `tools.py`, `providers.py`, `investigator.py`).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Demo Loader Fixes & Call Detail Records | `load_demo_case.py`, `09_cdr.csv`, `analytics.py` | none | DONE |
| M2 | Victim Protection & Identity Masking | `quality.py`, `analytics.py`, `generator.py`, `notation.ts` | M1 | DONE |
| M3 | Synthetic Data Tagging & Provenance UI | `routes_graph.py`, `routes_sources.py`, `sources/page.tsx` | none | DONE |
| M4 | Verifiable Evidence Ledger | `ed25519.py`, `ledger.py`, `routes_forensics.py`, `generator.py`, `ledger/page.tsx` | none | DONE |
| M5 | Investigator AI Chat & Web Search | `agent.py`, `providers.py`, `tools.py`, `investigator/page.tsx` | none | DONE |
| M6 | Map Rendering & UI Polish | `map/page.tsx`, `routes_geo.py`, overview/landing UI | M3 | DONE |
| M7 | End-to-End Acceptance Verification & Forensic Audit | Verification test suites, Reviewers, Challengers, Forensic Auditor | M1-M6 | DONE |
| M8 | Investigator Chat History Persistence | `backend/app/db.py`, `backend/app/api/routes_intel.py`, `backend/app/ai/`, `frontend-next/src/app/(sheet)/investigator/`, `backend/tests/test_investigator.py` | none | DONE |
| M9 | Demo Preparation & Rebranding (R1-R5) | Branding elimination (R1), 3 Real Cybercrime Cases CSVs (R2), Case Documents (R3), Chart Entity Search Bar (R4), DB Re-ingestion & Verification (R5) | none | IN_PROGRESS |

## Interface Contracts & Specifications (M9)
### R1: Rebranding & Neutral Sheet Identity
- Title: `"National Cyber Crime Investigation Corpus"`
- Code: `"NCIC-2026"`
- Subtitle: `"Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"` (API) / `"Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"` (Loader)
- Tag conversions: `CyberHawk 2.0 Operation` -> `NCIC Investigation`, `CyberHawk 2.0 Bust` -> `NCIC Arrest`
- Zero CyberHawk matches allowed across `backend/`, `frontend-next/`, `demo-case-data/`.

### R2 & R3: New Crime Cases & Case Documents Data
- Case A: Operation Chakra-II (CBI/Interpol, tech support fraud)
- Case B: Jamtara Phishing Syndicate (OTP phishing, SIM cloning, KYC scams)
- Case C: Chinese Loan App Fraud (predatory lending apps CashZone/RuPay Now, mule accounts)
- Data requirements:
  - `>= 45` new entity rows in `01_entities_nodes.csv`
  - Continue entity ID sequences (e.g., P3001+, A3001+, O301+, PH301+)
  - `>= 5` cross-case relationships in `02_relationships_edges.csv` linking across cases/existing data
  - Realistic financial transactions in `03_financial_transactions.csv`
  - `>= 8` realistic document entries in `05_case_documents.csv` with `>= 3` FIR or ARREST_MEMO

### R4: Chart Page Entity Search Bar
- Location: `frontend-next/src/app/(sheet)/chart/page.tsx`
- First child inside `<div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">`
- Input with placeholder `"Search entities…"`, dropdown of matching entities (query >= 2 chars), max 8 items
- Clicking item selects entity via `select(node.id)` and clears query; Escape clears query; blur with 150ms delay closes dropdown.

### R5: Database Re-ingestion & Verification
- `load_demo_case.py` executes successfully (exit code 0)
- Ingested entity count is strictly higher than pre-task count
- All backend tests pass and frontend builds with 0 errors.
