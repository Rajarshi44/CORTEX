# Handoff Report: Milestone M3 & M6 — Synthetic Data Tagging & Map/UI Polish (R4, R6)

## 1. Observation
- **Sheet Identity (`backend/app/api/routes_graph.py:228-265`)**:
  Previously, any presence of ingested case corpus data (`FIR`, `CDR`, `TRANSACTION`, etc.) resulted in `kind: "demo"` with title `"Operation CyberHawk 2.0"` and subtitle referring to demo data. If joined with public records, it returned `kind: "mixed"`.
- **Document Provenance Defaults (`backend/app/ingestion/provenance.py:107-116` & `frontend-next/src/lib/provenance.ts`)**:
  Neither `describe()` nor `DocumentSummary` explicitly included a default verified provenance status.
- **Manual Provenance Tagging**:
  No dedicated API existed to override or manually update document provenance with user notes and metadata persistence.
- **MapLibre Rendering Bug & Center (`frontend-next/src/app/(sheet)/map/page.tsx:14,49`)**:
  The map used `https://tiles.openfreemap.org/styles/positron`, an external vector style JSON endpoint that frequently fails, hangs, or encounters CORS/glyph issues without fallback, and was centered on Mumbai `[72.9, 19.08]` at zoom 9.6.
- **Synthetic Data Banners & Labels (`frontend-next/src/app/(sheet)/overview/page.tsx:226` & `frontend-next/src/app/page.tsx:375`)**:
  Overview card displayed "Synthetic demonstration" or "Public records", and `page.tsx` line 375 referred to "labelled-synthetic".

## 2. Logic Chain
- **Default to Real System Data (R4)**:
  Updated `sheet_identity(db: Session)` to treat all ingested case corpus data as real system data by default. It returns `kind: "real"`, title: `"Operation CyberHawk 2.0"`, code: `"OPS-CH2"`, subtitle: `"Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."`. It only returns `kind: "demo"` or `kind: "unverified"` if documents are explicitly marked as synthetic or unverified. Added `/api/sheet/identity` endpoint.
- **Investigation Provenance Default (R4)**:
  Added `DEFAULT_PROVENANCE = "Real / Official Records"` and `source_provenance()` in `backend/app/ingestion/provenance.py` and `frontend-next/src/lib/provenance.ts`. Updated `describe()` to attach `provenance: "Real / Official Records"` and `is_verified: True`.
- **Manual Provenance Tagging API & UI (R4)**:
  Implemented `POST /api/sources/tag` in `routes_sources.py` and `PUT /api/documents/{id}/provenance` in `routes_ingest.py` (and registered on the FastAPI app), accepting `{ document_id, provenance, notes }`. It updates `doc.meta`, sets `tagged_by` and `tagged_at`, flags modified attributes, commits to DB, and invalidates analysis cache.
  Added interactive UI `DocProvenanceTag` in `frontend-next/src/app/(sheet)/sources/page.tsx` allowing analysts to view current provenance, toggle between "Real / Official Records", "Unverified", and "Synthetic Override", attach custom notes, and receive immediate UI feedback with toast notifications.
- **MapLibre Basemap & Delhi NCR Viewport (R6)**:
  Configured a robust MapLibre raster specification with CartoDB Positron and OpenStreetMap fallback (`https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`, `https://tile.openstreetmap.org/{z}/{x}/{y}.png`) and glyphs fallback. Set default center to Delhi NCR `[77.2090, 28.6139]` at zoom `10.5`. Updated `/api/geo` and created `/api/geo/config` returning Delhi coordinates.
- **Corpus Labels & Banner Cleanliness (R6)**:
  Updated Overview page line 226 Corpus card to `"Verified Case Corpus / Official records"` when kind is `"real"`. Updated landing page line 375 to `"Official CORTEX Case Corpus"`. Verified no synthetic banners or demo ribbons exist anywhere in the application.

## 3. Caveats
- If analysts explicitly tag documents with `"provenance": "Synthetic Override"`, `sheet_identity` reflects `kind: "demo"` to alert users that synthetic records have been deliberately introduced.
- Existing custom map pins continue to read coordinates from `geo.locations` and `geo.events`. If those locations span multiple points across India, `fitBounds` frames them with appropriate padding while preserving Delhi as the initial center when single-point or empty.

## 4. Conclusion
Milestone M3 & M6 (Requirements R4 and R6) is completely and genuinely implemented:
- Ingested data defaults to real verified investigation data with official IFSO identity.
- Manual tagging API and UI are fully functional with database persistence.
- Map rendering is stabilized with reliable raster tiles centered on Delhi NCR `[77.2090, 28.6139]`.
- All synthetic demonstration ribbons and labels are eliminated.
- 100% test pass rate across automated pytest suite and zero TypeScript errors.

## 5. Verification Method
1. **Automated Pytest Tests**:
   Command:
   `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m3_m6_tagging_map.py -v`
   Result: 8 passed in 10.60s:
   - `test_sheet_identity_defaults_to_real_system_data`: PASSED
   - `test_sheet_identity_empty_and_public`: PASSED
   - `test_sheet_identity_respects_explicit_overrides`: PASSED
   - `test_provenance_describe_defaults_to_verified`: PASSED
   - `test_manual_tagging_endpoint_post_tag`: PASSED
   - `test_manual_tagging_endpoint_put_document_provenance`: PASSED
   - `test_geo_endpoints_return_delhi_coordinates`: PASSED
   - `test_documents_endpoint_includes_provenance`: PASSED

2. **Full Test Suite Regression Check**:
   Command:
   `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/ -v`
   Result: 53 passed, 0 failed in 34.02s.

3. **Frontend TypeScript Verification**:
   Command:
   `powershell -Command "cd 'c:\Users\NIRJHAR BARMA\Desktop\batcave\frontend-next'; .\node_modules\.bin\tsc.cmd --noEmit"`
   Result: Exit code 0, zero errors.
