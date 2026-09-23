# M9 R1 Handoff Report: Rebrand "Operation CyberHawk 2.0" to Neutral NCIC-2026 Corpus

## 1. Observation

A full codebase audit was executed across all directories (`backend/`, `frontend-next/`, `demo-case-data/`, `cortex-enterprise/`, root files, docs, scripts, and tests) to identify every occurrence of `"CyberHawk"`, `"Operation CyberHawk 2.0"`, `"OPS-CH2"`, and related branding.

### Exact Matches Observed by File

1. **`backend/app/api/routes_graph.py`** (4 code/doc matches):
   - Line 231 (docstring): `By default, all ingested case corpus data is treated as 'real' system data (Operation CyberHawk 2.0,`
   - Line 265 (`demo` branch): `return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "demo", "sources": srcs, "subtitle": "Delhi Crime Branch / I4C Cyber Crime Investigation (Synthetic Data)."}`
   - Line 268 (`unverified` branch): `return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "unverified", "sources": srcs, "subtitle": "Delhi Crime Branch / IFSO Investigation Corpus (Unverified Records)."}`
   - Line 272 (`real` branch): `return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "real", "sources": srcs, "subtitle": "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."}`

2. **`backend/app/ingestion/load_demo_case.py`** (2 matches):
   - Line 45: `SHEET_TITLE = "Operation CyberHawk 2.0"`
   - Line 46: `SHEET_SUBTITLE = "Delhi Police Crime Branch / IFSO — digital-arrest fraud, mule accounts, hawala and crypto layering."`
   - Line 149: `("PERSON", "Rahul", "Named as the main beneficiary of the CyberHawk mule ring and not arrested. Report any record naming him.", "critical"),`

3. **`backend/app/ai/demo_fallback.py`** (7 matches):
   - Line 31: `"**Rahul alias Happy** (P005) — the main beneficiary of the CyberHawk mule ring (SN-B) — remains "`
   - Line 64: `"**Rahul alias Happy** (P005) is the main beneficiary of the CyberHawk 2.0 mule ring (SN-B). "`
   - Line 136: `"**SN-B — CyberHawk 2.0 Mule Ring**\n"`
   - Line 174: `"**Operation CyberHawk 2.0** — Delhi Police Crime Branch / IFSO investigation announced 13 Dec 2025.\n\n"`
   - Line 222: `"- The **Transnational Hawala Network** (O002) and **CyberHawk Mule Ring** (O003) are the other two orgs "`
   - Line 277: `"| 01 Dec 2025 | CyberHawk 2.0 FIR filed | SN-B |\n"`
   - Line 289: `"This corpus covers **Operation CyberHawk 2.0** — a Delhi Police Crime Branch investigation into a "`

4. **`backend/tests/test_m3_m6_tagging_map.py`** (4 matches):
   - Line 5: `kind: "real", title: "Operation CyberHawk 2.0", code: "OPS-CH2",`
   - Line 69: `"""Ingested case corpus data must default to real system data: kind='real', Operation CyberHawk 2.0."""`
   - Line 83: `assert ident["title"] == "Operation CyberHawk 2.0"`
   - Line 84: `assert ident["code"] == "OPS-CH2"`
   - Line 85: `assert "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)" in ident["subtitle"]`

5. **`backend/tests/test_m2_victim_protection.py`** (2 matches):
   - Line 227: `md = build_markdown(demo_session, G, D, snap, case_name="Operation CyberHawk 2.0 Brief")`
   - Line 238: `pdf_bytes = build_pdf(md, title="Operation CyberHawk 2.0 Brief", db=demo_session)`

6. **`cortex-enterprise/backend/app/api/routes_graph.py`** (4 matches):
   - Identical to `backend/app/api/routes_graph.py` (lines 231, 265, 268, 272).

7. **`cortex-enterprise/backend/tests/test_m3_m6_tagging_map.py`** (4 matches):
   - Identical to `backend/tests/test_m3_m6_tagging_map.py` (lines 5, 69, 83, 84, 85).

8. **`demo-case-data/01_entities_nodes.csv`** (3,801 matches total):
   - Line 20: `O003,ORGANIZATION,CyberHawk Mule Ring,,,Mule Ring,SN-B,,,Active,HIGH,`
   - Lines 1709 to 3708 (2,000 occurrences in notes/tags column): `CyberHawk 2.0 Operation`
   - Lines 1710 to 5508 (1,800 occurrences in notes/tags column): `CyberHawk 2.0 Bust`

9. **`demo-case-data/05_case_documents.csv`** (1 match with 2 occurrences):
   - Line 6: `DOC-005,FIR_EXTRACT,"FIR No. [Illustrative: 112/2025] - CyberHawk 2.0 operation",2025-12-01,2025-12-01,NCRP,Cyber Hawk HQ,National,"Two 19-year-old students arrested for opening mule accounts and SIM cards. ₹1,08,000 traced across 3 accounts. Main beneficiary 'Rahul alias Happy' at large.","P005;P006;P007",SN-B,CONFIDENTIAL,Main accused P005 absconding`

10. **`demo-case-data/07_timeline_events.csv`** (2 matches):
    - Line 4: `EV-003,2025-10-05,11:15,ACCOUNT_OPENED,CyberHawk mule accounts opened by students,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-005`
    - Line 14: `EV-013,2025-12-02,11:00,ARREST,CyberHawk arrests P006 and P007,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-006`

11. **`demo-case-data/08_geo_locations.csv`** (41 matches total across 28 lines):
    - Line 9: `LOC008,Rohini Student Mules Residence,New Delhi,Delhi,India,28.7041,77.1025,RESIDENCE,P005;P006;SIM002;SIM003,SN-B,5,Residence of 19-year-old accused student mules recruited under Operation CyberHawk 2.0 to open bank accounts and procure SIMs`
    - Lines 17 to 30 (LOC100 to LOC113): `...CyberHawk Safehouse...` in location_name and `1000 Crore CyberHawk Bust Location` in notes.
    - Lines 31 to 56 (LOC200 to LOC225): `...CyberHawk 2.0 Base...` in location_name and `CyberHawk 2.0 Extended Network` in notes.

12. **`demo-case-data/README.md`** (1 match):
    - Line 20: `### SN-B: Operation CyberHawk 2.0 — Student Mule Ring`

13. **`demo-case-data/add_locations.py`** (2 matches - generator script in demo-case-data):
    - Line 48: `"location_name": f"{city} CyberHawk Safehouse {i//chunk_size + 1}",`
    - Line 58: `"notes": "1000 Crore CyberHawk Bust Location"`

14. **`demo-case-data/generate_2000.py`** (6 matches - generator script in demo-case-data):
    - Line 19: `# CyberHawk 2.0: 2000 People (P2001-P4000)`
    - Line 53: `"sub_network": "SN-E", # CyberHawk 2.0`
    - Line 58: `"notes": "CyberHawk 2.0 Operation"`
    - Line 76: `"notes": "CyberHawk 2.0 Bust"`
    - Line 217: `"location_name": f"{city} CyberHawk 2.0 Base {i//chunk_size + 1}",`
    - Line 227: `"notes": "CyberHawk 2.0 Extended Network"`

15. **`README.md`** (1 match):
    - Line 31: `**The demo sheet.** `npm run dev:demo` (or `./run_demo.ps1`) loads Operation CyberHawk 2.0 from`

16. **`run_demo.ps1`** (1 match):
    - Line 4: `Write-Host " CORTEX - Operation CyberHawk 2.0 demo"`

17. **`frontend-next/`**:
    - Checked all `*.ts` and `*.tsx` files: ZERO matches found. Only Turbopack build cache (`.next/`) contained transient tokens which will clear on re-build.

---

## 2. Logic Chain

1. **Acceptance Criteria Verification**:
   The acceptance test is:
   `grep -r "CyberHawk" backend/ frontend-next/ demo-case-data/ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.csv"`
   Because `add_locations.py` and `generate_2000.py` reside in `demo-case-data/` with `.py` extensions, and `08_geo_locations.csv`, `05_case_documents.csv`, `07_timeline_events.csv`, and `01_entities_nodes.csv` reside in `demo-case-data/` with `.csv` extensions, ANY leftover mention in these files will fail the acceptance test. Therefore, all 16 files identified must be modified.

2. **Entity Consistency (O003)**:
   In `demo-case-data/01_entities_nodes.csv`, entity `O003` was named `"CyberHawk Mule Ring"`. In `backend/app/ai/demo_fallback.py` line 222, `O003` was referenced as `CyberHawk Mule Ring`. In `02_relationships_edges.csv`, lines 22-23 associate student mules `P006` and `P007` with `O003`. Renaming `O003` to `"Student Mule Ring"` preserves semantic consistency with `SN-B` ("Student Mule Ring") and eliminates the branding string without breaking relationship IDs.

3. **Neutral Rebranding Values**:
   Per the specification:
   - Returned sheet title: `"National Cyber Crime Investigation Corpus"`
   - Code: `"NCIC-2026"`
   - Subtitle (API `sheet_identity()`): `"Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"` (applied across all three branches: `demo`, `unverified`, `real`)
   - Loader subtitle (`load_demo_case.py` `SHEET_SUBTITLE`): `"Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"`
   - CSV tags:
     - `"CyberHawk 2.0 Operation"` -> `"NCIC Investigation"`
     - `"CyberHawk 2.0 Bust"` -> `"NCIC Arrest"`

4. **Test Fixtures & Assertions**:
   `backend/tests/test_m3_m6_tagging_map.py` directly asserts `ident["title"] == "Operation CyberHawk 2.0"`, `ident["code"] == "OPS-CH2"`, and subtitle substring. Updating these assertions to `"National Cyber Crime Investigation Corpus"` and `"NCIC-2026"` ensures 100% test passing.
   Similarly, `backend/tests/test_m2_victim_protection.py` passes `case_name="Operation CyberHawk 2.0 Brief"`. Updating it to `case_name="National Cyber Crime Investigation Corpus Brief"` maintains green test status while removing the brand name.

---

## 3. Caveats

1. **Database Re-ingestion (R5 dependency)**:
   `backend/demo.db` is an SQLite database containing pre-ingested nodes with old CyberHawk tags. Modifying the CSVs and loader code does not automatically rewrite `demo.db` until re-ingestion (`python -m app.ingestion.load_demo_case`) is triggered. Re-ingestion belongs to Milestone M9 R5.
2. **Turbopack Cache**:
   `frontend-next/.next/cache` contains binary compiler artifacts from previous dev runs. Deleting `.next` or restarting `npm run dev` clears these cache files automatically. No frontend source files contained any CyberHawk tokens.

---

## 4. Conclusion & Precise Edit Plan

The Worker implementer should execute the following line-by-line edits across the 16 files:

### File 1: `backend/app/api/routes_graph.py`
- **Lines 231-233 (Docstring)**:
  *Before*:
  ```python
  By default, all ingested case corpus data is treated as 'real' system data (Operation CyberHawk 2.0,
  Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)), unless explicitly marked as
  unverified or synthetic.
  ```
  *After*:
  ```python
  By default, all ingested case corpus data is treated as 'real' system data (National Cyber Crime Investigation Corpus,
  Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis), unless explicitly marked as
  unverified or synthetic.
  ```
- **Line 265 (`demo` branch)**:
  *Before*:
  ```python
  return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "demo", "sources": srcs,
          "subtitle": "Delhi Crime Branch / I4C Cyber Crime Investigation (Synthetic Data)."}
  ```
  *After*:
  ```python
  return {"title": "National Cyber Crime Investigation Corpus", "code": "NCIC-2026", "kind": "demo", "sources": srcs,
          "subtitle": "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"}
  ```
- **Line 268 (`unverified` branch)**:
  *Before*:
  ```python
  return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "unverified", "sources": srcs,
          "subtitle": "Delhi Crime Branch / IFSO Investigation Corpus (Unverified Records)."}
  ```
  *After*:
  ```python
  return {"title": "National Cyber Crime Investigation Corpus", "code": "NCIC-2026", "kind": "unverified", "sources": srcs,
          "subtitle": "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"}
  ```
- **Line 272 (`real` branch)**:
  *Before*:
  ```python
  return {"title": "Operation CyberHawk 2.0", "code": "OPS-CH2", "kind": "real", "sources": srcs,
          "subtitle": "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."}
  ```
  *After*:
  ```python
  return {"title": "National Cyber Crime Investigation Corpus", "code": "NCIC-2026", "kind": "real", "sources": srcs,
          "subtitle": "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"}
  ```

### File 2: `backend/app/ingestion/load_demo_case.py`
- **Lines 45-46**:
  *Before*:
  ```python
  SHEET_TITLE = "Operation CyberHawk 2.0"
  SHEET_SUBTITLE = "Delhi Police Crime Branch / IFSO — digital-arrest fraud, mule accounts, hawala and crypto layering."
  ```
  *After*:
  ```python
  SHEET_TITLE = "National Cyber Crime Investigation Corpus"
  SHEET_SUBTITLE = "Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"
  ```
- **Line 149**:
  *Before*:
  ```python
  ("PERSON", "Rahul", "Named as the main beneficiary of the CyberHawk mule ring and not arrested. "
                      "Report any record naming him.", "critical"),
  ```
  *After*:
  ```python
  ("PERSON", "Rahul", "Named as the main beneficiary of the student mule ring and not arrested. "
                      "Report any record naming him.", "critical"),
  ```

### File 3: `backend/app/ai/demo_fallback.py`
- **Line 31**:
  Replace `CyberHawk mule ring (SN-B)` with `student mule ring (SN-B)`
- **Line 64**:
  Replace `CyberHawk 2.0 mule ring (SN-B)` with `student mule ring (SN-B)`
- **Line 136**:
  Replace `**SN-B — CyberHawk 2.0 Mule Ring**` with `**SN-B — Student Mule Ring**`
- **Line 174**:
  Replace `**Operation CyberHawk 2.0** — Delhi Police Crime Branch / IFSO investigation announced 13 Dec 2025.` with:
  `**National Cyber Crime Investigation Corpus** — Delhi Police Crime Branch / IFSO investigation announced 13 Dec 2025.`
- **Line 222**:
  Replace `**CyberHawk Mule Ring** (O003)` with `**Student Mule Ring** (O003)`
- **Line 277**:
  Replace `| 01 Dec 2025 | CyberHawk 2.0 FIR filed | SN-B |` with:
  `| 01 Dec 2025 | Student mule network FIR filed | SN-B |`
- **Line 289**:
  Replace `This corpus covers **Operation CyberHawk 2.0** — a Delhi Police Crime Branch investigation into a ` with:
  `This corpus covers the **National Cyber Crime Investigation Corpus** — a Delhi Police Crime Branch / IFSO investigation into a `

### File 4: `backend/tests/test_m3_m6_tagging_map.py`
- **Lines 5-6 (Docstring)**:
  *Before*:
  ```python
     kind: "real", title: "Operation CyberHawk 2.0", code: "OPS-CH2",
     subtitle: "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."
  ```
  *After*:
  ```python
     kind: "real", title: "National Cyber Crime Investigation Corpus", code: "NCIC-2026",
     subtitle: "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"
  ```
- **Line 69 (Test docstring)**:
  *Before*:
  ```python
      """Ingested case corpus data must default to real system data: kind='real', Operation CyberHawk 2.0."""
  ```
  *After*:
  ```python
      """Ingested case corpus data must default to real system data: kind='real', NCIC-2026."""
  ```
- **Lines 83-85 (Assertions)**:
  *Before*:
  ```python
      assert ident["title"] == "Operation CyberHawk 2.0"
      assert ident["code"] == "OPS-CH2"
      assert "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)" in ident["subtitle"]
  ```
  *After*:
  ```python
      assert ident["title"] == "National Cyber Crime Investigation Corpus"
      assert ident["code"] == "NCIC-2026"
      assert "Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis" in ident["subtitle"]
  ```

### File 5: `backend/tests/test_m2_victim_protection.py`
- **Line 227**:
  *Before*: `case_name="Operation CyberHawk 2.0 Brief"`
  *After*: `case_name="National Cyber Crime Investigation Corpus Brief"`
- **Line 238**:
  *Before*: `title="Operation CyberHawk 2.0 Brief"`
  *After*: `title="National Cyber Crime Investigation Corpus Brief"`

### File 6: `cortex-enterprise/backend/app/api/routes_graph.py`
- Apply identical edits as in `backend/app/api/routes_graph.py` (lines 231, 265, 268, 272).

### File 7: `cortex-enterprise/backend/tests/test_m3_m6_tagging_map.py`
- Apply identical edits as in `backend/tests/test_m3_m6_tagging_map.py` (lines 5, 69, 83, 84, 85).

### File 8: `demo-case-data/01_entities_nodes.csv`
- **Line 20 (Entity O003)**:
  *Before*: `O003,ORGANIZATION,CyberHawk Mule Ring,,,Mule Ring,SN-B,,,Active,HIGH,`
  *After*: `O003,ORGANIZATION,Student Mule Ring,,,Mule Ring,SN-B,,,Active,HIGH,`
- **Global Find/Replace across entire file**:
  - Replace `CyberHawk 2.0 Operation` with `NCIC Investigation` (2,000 occurrences in lines 1709-3708)
  - Replace `CyberHawk 2.0 Bust` with `NCIC Arrest` (1,800 occurrences in lines 1710-5508)

### File 9: `demo-case-data/05_case_documents.csv`
- **Line 6 (DOC-005)**:
  *Before*:
  ```csv
  DOC-005,FIR_EXTRACT,"FIR No. [Illustrative: 112/2025] - CyberHawk 2.0 operation",2025-12-01,2025-12-01,NCRP,Cyber Hawk HQ,National,"Two 19-year-old students arrested for opening mule accounts and SIM cards. ₹1,08,000 traced across 3 accounts. Main beneficiary 'Rahul alias Happy' at large.","P005;P006;P007",SN-B,CONFIDENTIAL,Main accused P005 absconding
  ```
  *After*:
  ```csv
  DOC-005,FIR_EXTRACT,"FIR No. [Illustrative: 112/2025] - NCIC Investigation",2025-12-01,2025-12-01,NCRP,Special Cell HQ,National,"Two 19-year-old students arrested for opening mule accounts and SIM cards. ₹1,08,000 traced across 3 accounts. Main beneficiary 'Rahul alias Happy' at large.","P005;P006;P007",SN-B,CONFIDENTIAL,Main accused P005 absconding
  ```

### File 10: `demo-case-data/07_timeline_events.csv`
- **Line 4 (EV-003)**:
  *Before*: `EV-003,2025-10-05,11:15,ACCOUNT_OPENED,CyberHawk mule accounts opened by students,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-005`
  *After*: `EV-003,2025-10-05,11:15,ACCOUNT_OPENED,Student mule accounts opened by students,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-005`
- **Line 14 (EV-013)**:
  *Before*: `EV-013,2025-12-02,11:00,ARREST,CyberHawk arrests P006 and P007,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-006`
  *After*: `EV-013,2025-12-02,11:00,ARREST,Police arrests P006 and P007,Delhi,Delhi,"P006;P007",SN-B,MEDIUM,DOC-006`

### File 11: `demo-case-data/08_geo_locations.csv`
- **Line 9 (LOC008)**:
  *Before*: `...recruited under Operation CyberHawk 2.0 to open bank accounts...`
  *After*: `...recruited to open bank accounts...`
- **Lines 17-30 (LOC100 to LOC113)**:
  Replace all `CyberHawk Safehouse` with `Investigation Safehouse` and `1000 Crore CyberHawk Bust Location` with `1000 Crore Investigation Bust Location`
- **Lines 31-56 (LOC200 to LOC225)**:
  Replace all `CyberHawk 2.0 Base` with `Regional Base` and `CyberHawk 2.0 Extended Network` with `NCIC Extended Network`

### File 12: `demo-case-data/README.md`
- **Line 20**:
  *Before*: `### SN-B: Operation CyberHawk 2.0 — Student Mule Ring`
  *After*: `### SN-B: Student Mule Ring`

### File 13: `demo-case-data/add_locations.py`
- **Line 48**:
  *Before*: `"location_name": f"{city} CyberHawk Safehouse {i//chunk_size + 1}",`
  *After*: `"location_name": f"{city} Investigation Safehouse {i//chunk_size + 1}",`
- **Line 58**:
  *Before*: `"notes": "1000 Crore CyberHawk Bust Location"`
  *After*: `"notes": "1000 Crore Investigation Bust Location"`

### File 14: `demo-case-data/generate_2000.py`
- **Line 19**:
  *Before*: `# CyberHawk 2.0: 2000 People (P2001-P4000)`
  *After*: `# NCIC Investigation: 2000 People (P2001-P4000)`
- **Line 53**:
  *Before*: `"sub_network": "SN-E", # CyberHawk 2.0`
  *After*: `"sub_network": "SN-E", # NCIC Investigation`
- **Line 58**:
  *Before*: `"notes": "CyberHawk 2.0 Operation"`
  *After*: `"notes": "NCIC Investigation"`
- **Line 76**:
  *Before*: `"notes": "CyberHawk 2.0 Bust"`
  *After*: `"notes": "NCIC Arrest"`
- **Line 217**:
  *Before*: `"location_name": f"{city} CyberHawk 2.0 Base {i//chunk_size + 1}",`
  *After*: `"location_name": f"{city} Regional Base {i//chunk_size + 1}",`
- **Line 227**:
  *Before*: `"notes": "CyberHawk 2.0 Extended Network"`
  *After*: `"notes": "NCIC Extended Network"`

### File 15: `README.md`
- **Line 31**:
  *Before*: `**The demo sheet.** `npm run dev:demo` (or `./run_demo.ps1`) loads Operation CyberHawk 2.0 from`
  *After*: `**The demo sheet.** `npm run dev:demo` (or `./run_demo.ps1`) loads the National Cyber Crime Investigation Corpus (NCIC-2026) from`

### File 16: `run_demo.ps1`
- **Line 4**:
  *Before*: `Write-Host " CORTEX - Operation CyberHawk 2.0 demo"`
  *After*: `Write-Host " CORTEX - National Cyber Crime Investigation Corpus (NCIC-2026) demo"`

---

## 5. Verification Method

Once the Worker completes implementation, run the following verification steps:

1. **Acceptance Test (Zero CyberHawk Results)**:
   ```bash
   grep -r "CyberHawk" backend/ frontend-next/ demo-case-data/ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.csv"
   ```
   *Expected result*: Exit code 1 (ZERO matches returned).

2. **Case-Insensitive Global Check**:
   ```bash
   git grep -i "cyberhawk"
   ```
   *Expected result*: Only matches in agent metadata (`.agents/`) if any; zero in repo source/tests/CSVs/docs.

3. **Backend Test Suite Verification**:
   ```powershell
   & ".\backend\venv\Scripts\pytest.exe" backend/tests/test_m3_m6_tagging_map.py
   & ".\backend\venv\Scripts\pytest.exe" backend/tests/test_m2_victim_protection.py
   ```
   *Expected result*: All 18 tests (8 in `test_m3_m6_tagging_map.py` and 10 in `test_m2_victim_protection.py`) pass cleanly.
