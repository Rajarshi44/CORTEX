# CORTEX SIH 2026 Fix & Polish Plan

## Strategy Overview
The CORTEX application is an enterprise-grade Criminal Network Analysis system (`backend`, `frontend-next`, and `demo-case-data`).
We will execute 6 targeted implementation milestones followed by comprehensive end-to-end testing and adversarial forensic audit.

---

## Milestones

### M1: Demo Loader Fixes & Call Detail Records (R3, R6-part)
- **Objective**: Fix command structure edge types (`REL_TYPE` mapping) in `load_demo_case.py` and supply a realistic CDR dataset.
- **Key Actions**:
  - In `backend/app/ingestion/load_demo_case.py`:
    - Differentiate `CONTROLS` based on source and target types:
      - PERSON -> PERSON with `CONTROLS` must be recorded as `CONTROLS` or `REPORTS_TO` (command structure), NOT `OWNS_ACCOUNT`.
      - PERSON -> BANK_ACCOUNT / CRYPTO_WALLET => `OWNS_ACCOUNT`.
      - PERSON -> PHONE / SIM => `USES_PHONE`.
    - Ensure graph edge types preserve command hierarchy.
  - In `demo-case-data/09_cdr.csv`:
    - Create small realistic CDR records between target numbers (Prabhakar PH003, Dev Raj PH005, Rahul PH004, etc.) including call bursts, night calls (23:00-05:00), and international calls.
    - Update `load_demo_case.py` to ingest CDR rows into `TimelineEvent(kind="CALL")` and `CALLED` graph edges.
  - Verify:
    - Run `python -m app.ingestion.load_demo_case`.
    - Verify command structure edges appear correctly in graph database.
    - Verify call anomaly detectors (`call_bursts`, `night_activity`, `burner_phones`) fire.

### M2: Victim Protection & Identity Masking (R1)
- **Objective**: Implement party roles, exclude them from suspicion/risk scoring and community membership, and mask victim identities across the UI and export reports.
- **Key Actions**:
  - Add party roles: `victim`, `complainant`, `witness`, `police`.
  - In `backend/app/graph/analytics.py`:
    - Exclude protected party roles from `suspicion_signals`, `priority_scores`, and first-time-offender calculations.
    - Exclude protected party roles from `detect_communities` (or mark them as non-members).
  - In `backend/app/reports/generator.py`:
    - Mask victim identities in generated briefs and PDF exports with `[VICTIM]` or role-based masks.
  - In `frontend-next`:
    - Mask victim entities in players lists, overview table, chart, notes drawer, alerts, and search.
  - Verify:
    - No victim/complainant entities appear in top risk rankings.
    - Frontend displays `[VICTIM]` for victim entities.

### M3: Synthetic Data Tagging & Provenance UI (R4, R6-part)
- **Objective**: Default all ingested data as "Real" system data unless explicitly marked unverified/uploaded; add manual tagging UI; remove synthetic banners.
- **Key Actions**:
  - In `backend/app/api/routes_graph.py` and `ingestion/provenance.py`:
    - Default sheet identity to real / verified unless explicit override.
    - Treat case data as authentic investigation data with "Real" provenance.
  - In `frontend-next`:
    - Add manual tagging capability in the UI (e.g. Sources page / Entity inspector) to toggle or edit provenance tags.
    - Remove "SYNTHETIC DEMO DATA" ribbon and replace with "Real" / "Verified Investigation Data".

### M4: Verifiable Evidence Ledger (Ed25519 & Merkle) (R5)
- **Objective**: Implement genuine Ed25519 cryptographic signing, Merkle batching with inclusion proofs, external anchor persistence, and "verify this brief" QR code generation.
- **Key Actions**:
  - In `backend/app/graph/ledger.py`:
    - Add Ed25519 keypair generation / loading and cryptographic signature verification.
    - Implement Merkle tree batching over ledger entries with proof generation and verification.
    - Implement external anchor persistence (e.g. state file or DB anchor table).
    - Seal CSV bytes and PDF exports with cryptographic signatures and Merkle inclusion proofs.
    - Add QR code generation linking to verification endpoint / payload for PDF and brief exports.
  - Add API endpoints `/api/ledger/verify-proof` and `/api/ledger/export-sealed`.

### M5: Investigator AI Chat & Web Search (R2)
- **Objective**: Remove hardcoded demo fallback; enable dynamic database retrieval via real LLM API; functional web search.
- **Key Actions**:
  - In `backend/app/ai/agent.py`:
    - Remove the hardcoded fallback interception that short-circuits demo questions.
    - Configure real LLM provider (Gemini / OpenAI / OpenRouter).
    - Ensure tool calls dynamically query database for case facts (`search_entities`, `entity_profile`, `read_document`, etc.).
    - Ensure `web_search` tool functions reliably using DuckDuckGo / web connector with live open-web search results.
  - In `frontend-next/src/app/(sheet)/investigator/page.tsx`:
    - Add clear UI toggle / control for web search option.
    - Prompt for case details when queries need disambiguation.

### M6: Map Rendering & UI Polish (R6)
- **Objective**: Fix MapLibre rendering bugs, center on Delhi, ensure tile loading, and polish demo experience.
- **Key Actions**:
  - In `frontend-next/src/app/(sheet)/map/page.tsx`:
    - Fix MapLibre initialization: use reliable raster OSM or Carto tile style that avoids remote font/glyph CORS failures.
    - Set default center to Delhi `[77.2090, 28.6139]`.
    - Ensure location markers and timeline event pins render cleanly.
  - Complete general UI polish across lenses.

### M7: Verification & Forensic Audit
- **Objective**: Execute automated test suite for all R1-R6 acceptance criteria; run adversarial challenger tests and forensic integrity audit.
