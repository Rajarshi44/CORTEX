# BRIEFING — 2026-09-18T02:43:00Z

## Mission
Implement Milestone M3 & M6: Default to real system data, add manual provenance tagging API and UI, fix MapLibre basemap & center Delhi [77.2090, 28.6139], and remove synthetic demo data ribbons.

## 🔒 My Identity
- Archetype: worker_m3_m6_polish
- Roles: implementer, qa, specialist
- Working directory: c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m3_m6_polish
- Original parent: 6b912dfe-a190-4754-bd68-6406c712353d
- Milestone: M3 & M6 (Synthetic Data Tagging & Map/UI Polish)

## 🔒 Key Constraints
- Treat all ingested data as real system data by default unless explicitly marked unverified.
- Return kind: "real", title: "Operation CyberHawk 2.0", code: "OPS-CH2", subtitle: "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."
- Manual tagging capabilities: POST /api/sources/tag or PUT /api/documents/{id}/provenance with user notes and persistence.
- Fix MapLibre rendering bug: reliable raster basemap tiles (CartoDB Positron / OSM) and center on Delhi [77.2090, 28.6139] at appropriate zoom.
- Remove "SYNTHETIC DEMO DATA" ribbon and fix provenance labels across frontend.
- Independent automated tests in backend/tests/test_m3_m6_tagging_map.py.
- Minimal change principle, genuine implementations, no cheats or dummy facades.

## Current Parent
- Conversation ID: 6b912dfe-a190-4754-bd68-6406c712353d
- Updated: 2026-09-18T02:42:17Z

## Task Summary
- **What to build**: M3 & M6 tasks: real system data default, manual provenance tagging endpoint & UI, Delhi map rendering with reliable tiles, synthetic banner removal.
- **Success criteria**: Pytest tests pass, frontend tsc passes, verified provenance tags display, interactive tagging updates DB, map tiles render centered on Delhi.
- **Interface contracts**: REST API (`/api/sheet/identity`, `/api/sources/tag`, `/api/documents/{id}/provenance`, `/api/geo`, `/api/geo/config`)
- **Code layout**: `backend/app/` and `frontend-next/src/`

## Key Decisions Made
- Configured `sheet_identity` to return `kind: "real"`, title: "Operation CyberHawk 2.0", code: "OPS-CH2", subtitle: "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)." by default for any ingested case corpus data, while respecting explicit `unverified` or `synthetic` metadata flags.
- Defined `DEFAULT_PROVENANCE = "Real / Official Records"` and `source_provenance()` in both backend and frontend.
- Implemented `POST /api/sources/tag` and `PUT /api/documents/{id}/provenance` supporting provenance status updates, analyst notes, and persistence with metadata modification flagging and database commits.
- Added interactive UI `DocProvenanceTag` in `frontend-next/src/app/(sheet)/sources/page.tsx` with immediate optimistic UI feedback and persistence call.
- Replaced unreliable external vector style `https://tiles.openfreemap.org/styles/positron` with robust MapLibre raster specification using CartoDB Positron and OpenStreetMap fallback, centered on Delhi `[77.2090, 28.6139]` at zoom 10.5.
- Updated Corpus card on Overview page to display "Verified Case Corpus / Official records" when kind is "real".
- Replaced "labelled-synthetic" in landing page with "Official CORTEX Case Corpus".
- Verified no "SYNTHETIC DEMO DATA" ribbons or banners exist.

## Artifact Index
- ORIGINAL_REQUEST.md — Initial dispatch prompt and follow-up
- progress.md — Liveness heartbeat and milestone tracking
- handoff.md — 5-component handoff report

## Change Tracker
- **Files modified**:
  - `backend/app/api/routes_graph.py` — Default to real system data, Operation CyberHawk 2.0 IFSO identity, /sheet/identity route
  - `backend/app/ingestion/provenance.py` — DEFAULT_PROVENANCE and describe() provenance field
  - `backend/app/api/routes_sources.py` — POST /api/sources/tag manual tagging endpoint
  - `backend/app/api/routes_ingest.py` — PUT /documents/{id}/provenance, GET /documents provenance field
  - `backend/app/api/routes_intel.py` — /api/geo center & zoom, /api/geo/config Delhi NCR endpoint
  - `backend/app/main.py` — Proxy PUT /api/documents/{id}/provenance route
  - `frontend-next/src/lib/provenance.ts` — DEFAULT_PROVENANCE and sourceProvenance helper
  - `frontend-next/src/lib/types.ts` — DocumentSummary, DocumentDetail, and NodeView attributes field
  - `frontend-next/src/lib/api.ts` — tagDocument, updateDocumentProvenance, geoConfig methods
  - `frontend-next/src/app/(sheet)/sources/page.tsx` — Interactive DocProvenanceTag UI and list provenance tags
  - `frontend-next/src/app/(sheet)/map/page.tsx` — Robust raster basemap, Delhi center [77.2090, 28.6139], zoom 10.5
  - `frontend-next/src/app/(sheet)/overview/page.tsx` — Corpus card Verified Case Corpus / Official records
  - `frontend-next/src/app/page.tsx` — Replaced labelled-synthetic with Official CORTEX Case Corpus
  - `backend/tests/test_m3_m6_tagging_map.py` — 8 automated tests for M3 and M6
- **Build status**: Pass (8/8 M3/M6 tests, 53/53 all backend tests, 0 errors frontend tsc)
- **Pending issues**: None

## Quality Status
- **Build/test result**: Pass (pytest: 8/8 passed in test_m3_m6_tagging_map.py, 53/53 passed in full backend test suite)
- **Lint status**: Pass (`tsc --noEmit` exited with 0 errors)
- **Tests added/modified**: `backend/tests/test_m3_m6_tagging_map.py` (8 test cases covering identity, tagging endpoints, geo Delhi coordinates, and document provenance persistence)

## Loaded Skills
- None
