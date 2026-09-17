# Project: CORTEX SIH 2026 Fix & Polish

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
| M7 | End-to-End Acceptance Verification & Forensic Audit | Verification test suites, Reviewers, Challengers, Forensic Auditor | M1-M6 | IN_PROGRESS |

## Interface Contracts
### Loader ↔ Graph Analytics
- Edges between persons with relationship `CONTROLS` must be represented as `CONTROLS` / `REPORTS_TO`, allowing hierarchical command tree tracing without distorting account ownership.
- Timeline events with kind `CALL` must populate caller/callee phone entity IDs and timestamps for anomaly detectors (`call_bursts`, `night_activity`, `burner_phones`).

### Victim Protection Contract
- Entities with `party_role` in `{"victim", "complainant", "witness", "police"}` must:
  - Have suspicion score 0.0 and priority score 0.0.
  - Be excluded from community detection.
  - Render as `[VICTIM]` or masked name in UI, brief, and PDF exports.

### Evidence Ledger Contract
- Cryptographic signatures: Ed25519 standard keypair.
- Merkle batch: SHA-256 binary tree with inclusion proof `{leaf_index, root_hash, audit_path}`.
- QR code: encodes brief verification URL or cryptographic attestation payload.
