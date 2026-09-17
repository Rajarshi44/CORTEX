## 2026-09-18T02:23:28Z

You are worker_m3_m6_polish, a specialized implementation worker.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m3_m6_polish`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Python environment: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe`
Pytest: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your assigned task: Milestone M3 & M6 — Synthetic Data Tagging & Map/UI Polish (R4, R6)
"Treat all ingested data as real system data by default, unless explicitly marked as unverified or from uploaded sources. Add UI capabilities for manual tagging if automated tagging fails to correctly tag. Fix map rendering (resolve MapLibre bug, center on Delhi, visible basemap tiles). Remove 'SYNTHETIC DEMO DATA' ribbon and fix provenance labels."

Requirements & Steps:
1. Default to Real System Data (R4):
   - In `backend/app/api/routes_graph.py`:
     Update `sheet_identity(db: Session)`:
     By default, treat all ingested case corpus data as "real" system data.
     Return `kind: "real"`, title: "Operation CyberHawk 2.0", code: "OPS-CH2",
     subtitle: "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence).",
     unless explicitly marked as unverified or synthetic.
   - In `backend/app/ingestion/provenance.py` and `frontend-next/src/lib/provenance.ts`:
     Ensure source types default to verified investigation provenance ("Real / Official Records").

2. Manual Tagging Capabilities (R4):
   - In `backend/app/api/routes_sources.py` (or `routes_ingest.py`):
     Add an endpoint `POST /api/sources/tag` or `PUT /api/documents/{id}/provenance` allowing analysts to manually override / update document provenance (e.g., `provenance: "Real" | "Unverified" | "Synthetic Override"`, with user notes).
   - In `frontend-next/src/app/(sheet)/sources/page.tsx`:
     Add an interactive UI capability allowing the user to view provenance tags and manually toggle/change the provenance status (e.g. from "Real" to "Unverified" or vice versa) with immediate UI feedback and persistence.

3. Fix Map Rendering & Center on Delhi (R6):
   - In `frontend-next/src/app/(sheet)/map/page.tsx`:
     - Resolve MapLibre rendering bug:
       The default `https://tiles.openfreemap.org/styles/positron` often fails or blocks without fallback.
       Configure a robust style that loads reliably:
       Use raster tiles (e.g. OpenStreetMap `https://tile.openstreetmap.org/{z}/{x}/{y}.png` or CartoDB Positron `https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`) or a reliable vector style with fallback so tiles are always visible.
     - Set default center to Delhi: `[77.2090, 28.6139]` (lng, lat).
     - Ensure zoom level is appropriate (e.g. 10 or 11 for Delhi National Capital Region).
     - Ensure location markers and timeline pins render accurately.

4. Remove "SYNTHETIC DEMO DATA" ribbon & fix provenance labels (R6):
   - Check `frontend-next/src/app/(sheet)/overview/page.tsx` line 226:
     Ensure Corpus card displays "Verified Case Corpus" / "Official records" when kind is "real".
   - Check `frontend-next/src/app/page.tsx` line 375:
     Replace any references to "labelled-synthetic" with "Official CORTEX Case Corpus".
   - Ensure NO "SYNTHETIC DEMO DATA" ribbon or banner is shown anywhere in the UI.

5. Verification:
   - Write automated pytest tests in `backend/tests/test_m3_m6_tagging_map.py`:
     - Test that `sheet_identity` returns `kind: "real"` and verified provenance by default.
     - Test that manual provenance tagging endpoint successfully updates and persists a document's provenance tag.
     - Test that map configuration or API endpoints return Delhi coordinates `[77.2090, 28.6139]`.
   - Run tests:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m3_m6_tagging_map.py -v`
   - In `frontend-next`, run typecheck or build test if applicable:
     `npx.cmd tsc --noEmit` from `frontend-next` directory to ensure no syntax/TypeScript errors.

6. Handoff:
   - Write `handoff.md` and `progress.md` in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m3_m6_polish\`.
   - Send completion message to orchestrator.

## 2026-09-18T02:42:17Z
**Context**: Milestone M3 & M6 verification and completion
**Content**: Checking status on your test execution and handoff report. Please report current test results and write handoff.md if complete.
**Action**: Provide current status, test results for test_m3_m6_tagging_map.py, and finalize handoff.md.
