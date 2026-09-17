## 2026-09-18T02:23:07Z
You are worker_m2_victim, a specialized implementation worker.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m2_victim`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Python environment: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe`
Pytest: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your assigned task: Milestone M2 — Victim Protection & Masking (R1)
"Add party roles (victim, complainant, witness, police). Exclude these roles from risk scoring, first-time-offender scoring, and community membership. Mask victim identities by role throughout the UI (including the Brief and PDF).
Acceptance: No victim or complainant entities appear in the top risk rankings; victim names are replaced with masked roles (e.g., '[VICTIM]') in frontend."

Requirements & Steps:
1. Party Roles:
   - Standardize party roles: `victim`, `complainant`, `witness`, `police`.
   - In `backend/app/ingestion/load_demo_case.py`:
     - Ensure entities from `01_entities_nodes.csv` (like P001 whose status/role is Complainant) and complainants from `04_ncrp_complaints.csv` have `attrs["party_role"]` properly set (`"victim"`, `"complainant"`, etc.).
     - Map P001 to `party_role = "victim"` (or `"complainant"`).
   - In `backend/app/graph/quality.py` or helper:
     Define `PROTECTED_PARTY_ROLES = {"victim", "complainant", "witness", "police"}`.
     Define `is_protected_party(node_type: str, label: str, attrs: dict) -> bool`.

2. Exclude from Analytics, Risk Scoring & Community Membership:
   - In `backend/app/graph/analytics.py`:
     - In `suspicion_signals`:
       Check `is_protected_party`. If True, force `score = 0.0`, `reasons = []`, zero out all adverse flags.
     - In `priority_scores`:
       Protected parties must receive `0.0` priority score.
     - In `detect_communities`:
       Protected parties must NOT be grouped into criminal communities (assign `community = -1` or exclude from community detection graph).
     - In `classify_roles`:
       Assign their role as their party role (e.g. `"victim"`, `"complainant"`), with label `ROLE_LABELS` updated to include `"victim": "Protected Victim"`, `"complainant": "Complainant"`, `"witness": "Witness"`, `"police": "Law Enforcement"`.
     - In first-time offender scoring / proximity risk:
       Ensure protected parties are NEVER flagged as first-time offenders.

3. Brief and PDF Export Masking:
   - In `backend/app/reports/generator.py`:
     - Mask victim and complainant names in `build_markdown` and `build_pdf`:
       Replace any victim identity / name with `[VICTIM]` (or role mask, e.g. `[VICTIM]`).
       Ensure no unmasked victim names appear in the generated brief or exported PDF.

4. Frontend Masking:
   - In `frontend-next/src/lib/notation.ts` (or `types.ts`):
     Add a masking helper:
     ```typescript
     export function isProtectedParty(role?: string | null, partyRole?: string | null, label?: string | null): boolean {
       const r = (role || "").toLowerCase();
       const pr = (partyRole || "").toLowerCase();
       const l = (label || "").toLowerCase();
       return r === "victim" || r === "complainant" || r === "witness" || r === "police" ||
              pr === "victim" || pr === "complainant" || pr === "witness" || pr === "police" ||
              l.includes("victim") || l.includes("complainant");
     }
     export function maskLabel(label: string, role?: string | null, partyRole?: string | null): string {
       const r = (role || "").toLowerCase();
       const pr = (partyRole || "").toLowerCase();
       if (r === "victim" || pr === "victim" || label.toLowerCase().includes("victim")) return "[VICTIM]";
       if (r === "complainant" || pr === "complainant") return "[COMPLAINANT]";
       if (r === "witness" || pr === "witness") return "[WITNESS]";
       if (r === "police" || pr === "police") return "[POLICE]";
       return label;
     }
     ```
   - Update frontend lenses to use `maskLabel`:
     - `frontend-next/src/app/(sheet)/overview/page.tsx`
     - `frontend-next/src/app/(sheet)/players/page.tsx`
     - `frontend-next/src/components/chart/LinkChart.tsx`
     - `frontend-next/src/components/sheet/NotesDrawer.tsx`
     - `frontend-next/src/app/(sheet)/alerts/page.tsx`
     - `frontend-next/src/app/(sheet)/map/page.tsx`

5. Verification:
   - Write comprehensive tests in `backend/tests/test_m2_victim_protection.py`:
     - Test that P001 (Victim/Complainant) has suspicion == 0.0 and priority == 0.0.
     - Test that P001 does NOT appear in top key players ranking.
     - Test that P001 is not assigned to any criminal community.
     - Test that `build_markdown` and `build_pdf` mask victim name to `[VICTIM]`.
     - Test that no victim entity has first-time offender risk.
   - Run tests:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m2_victim_protection.py -v`
   - Ensure all tests pass 100%.

6. Handoff:
   - Write `handoff.md` and `progress.md` in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m2_victim\`.
   - Send completion message to orchestrator.
