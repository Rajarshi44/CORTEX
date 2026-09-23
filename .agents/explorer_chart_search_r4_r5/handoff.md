# Handoff Report: Milestone M9 (R4 - Chart Search Bar & R5 - DB Re-ingestion / Verification)

## 1. Observation

### R4: Chart Page (`frontend-next/src/app/(sheet)/chart/page.tsx`)
- **Control Bar Location**: In `frontend-next/src/app/(sheet)/chart/page.tsx`:
  - Lines 87-88:
    ```tsx
    87:         <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">
    88:           <span className="label label-ink">{focus ? "Redrawn around selection" : infra ? "Full record" : "Actor chart"}</span>
    ```
  - Inserting the search component as the first child immediately before `<span className="label label-ink">` places it directly at line 88.
- **Imports**:
  - Line 2: `import { Suspense, useEffect, useMemo, useState } from "react";` (`useState` and `useMemo` are already imported).
  - Line 16: `import { REL_GROUPS } from "@/lib/notation";` — can be extended to `import { REL_GROUPS, TYPE_LABEL } from "@/lib/notation";` to support rendering formatted entity type tags (`TYPE_LABEL[node.type] ?? node.type`).
- **State and Data Availability**:
  - `ChartLens` extracts `nodes` from `src` (lines 52-58), which contains the active `NodeView[]` instances (with fields `id: string`, `label: string`, `type: EntityType`).
  - Store actions `select` and `selected` are available via `useSheet` (lines 31-32):
    ```tsx
    const selected = useSheet((s) => s.selected);
    const select = useSheet((s) => s.select);
    ```
    Calling `select(node.id)` updates global selection and automatically opens `notesDrawer` for that entity.
- **Styling Standards**:
  - Border and backgrounds: `border border-rule-strong bg-film`, `bg-film-lift`, `hover:bg-film-deep`.
  - Typography: `label text-[length:var(--fs-note)]`, `text-ink`, `text-ink-faint`.

---

### R5: Database Re-ingestion & Verification Pipeline
- **Baseline Entity Count Command**:
  ```powershell
  cd backend && .\venv\Scripts\python.exe -c "from app.db import SessionLocal; from app.db import Entity; db=SessionLocal(); print('Entities:', db.query(Entity).count())"
  ```
  - **Output**:
    ```
    Entities: 5612
    ```
- **Re-ingestion Command**:
  ```powershell
  cd backend && .\venv\Scripts\python.exe -m app.ingestion.load_demo_case
  ```
  - **Execution Output**:
    ```
    Clearing the demo sheet…
    Computing analytics…

    Operation CyberHawk 2.0 loaded
      entities              5612
      relationships         3074
      documents             20
      sealed                20
      events                219
      alerts                9
      watches               3
      watch hits            5
      transfers             9712
      calls                 66
      span                  15 Mar 2025 – 01 Dec 2025
      nodes                 5612
      edges                 3070
      communities           2880
      persons of interest   16
    ```
  - Confirmed idempotent execution: resets and re-populates exactly 5,612 entities and 20 sealed documents.
- **Backend Test Suite**:
  - Test command: `cd backend && .\venv\Scripts\pytest.exe -k "not test_live_agent_db_and_llm_e2e"`
  - Result: `116 passed, 1 deselected, 2 warnings in 80.80s`
  - Covered suites:
    - `tests/test_analytics_upgrades.py`: 13 passed
    - `tests/test_m1_loader.py`: 7 passed
    - `tests/test_m2_victim_protection.py`: 10 passed
    - `tests/test_m3_m6_tagging_map.py`: 8 passed
    - `tests/test_m4_ledger.py`: 9 passed
    - `tests/test_m5_investigator_chat.py`: 13 passed (offline tests)
    - `tests/test_novelty.py`: 15 passed
    - `tests/test_sources.py`: 17 passed
    - `tests/test_watch.py`: 24 passed
  - Note on `test_live_agent_db_and_llm_e2e`: Only runs if external `GEMINI_API_KEY` is set, and tries to hit deprecated endpoint `models/gemini-2.5-flash` which fails on live network calls. Excluding it or running without external network passes 100% of offline unit/integration tests.
- **Cortex-Enterprise Test Suite**:
  - Test command: `cd backend && .\venv\Scripts\pytest.exe -v ..\cortex-enterprise\backend\tests\test_m3_m6_tagging_map.py`
  - Result: `8 passed, 1 warning in 20.16s`
- **Frontend Codebase Health**:
  - Command: `cd frontend-next && npx tsc --noEmit`
  - Result: The entire `src/` tree compiles with **zero type errors**. (The only unrelated warning/error is a single type discrepancy in `next.config.ts(6,5)` regarding `devIndicators.appIsrStatus` in Next 16).

---

## 2. Logic Chain

1. **R4 Component Insertion**:
   - The user requested live entity search in the Chart control bar as the FIRST child before `<span className="label label-ink">`.
   - In `frontend-next/src/app/(sheet)/chart/page.tsx`, `<div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">` hosts the controls.
   - Adding `<div className="relative">...</div>` at the start of this flex container ensures the search input is positioned on the far left of the control bar before the lens title badge.
   - When the user types $\ge 2$ characters, filtering `nodes` using `(node.label ?? "").toLowerCase().includes(searchQuery.toLowerCase())` matches all relevant visible/projected entities.
   - Slicing results to at most 8 items matches the maximum capacity requirement.
   - Rendering `<li onMouseDown={(e) => e.preventDefault()} onClick={() => { select(node.id); setSearchQuery(""); setSearchOpen(false); }}>` prevents immediate blur before click registration and invokes `select(node.id)` while clearing the query.
   - Adding `onKeyDown={(e) => { if (e.key === "Escape") { setSearchQuery(""); setSearchOpen(false); } }}` and `onBlur={() => setTimeout(() => setSearchOpen(false), 150)}` satisfies the keyboard and blur requirements precisely.

2. **R5 Database Re-ingestion & Verification Pipeline**:
   - `app.ingestion.load_demo_case` loads the standardized demo case data from `demo-case-data/*.csv`.
   - Running `load_demo_case` regenerates the graph cache, re-attests the ledger, arms standing watches, and computes the analytics snapshot.
   - The baseline entity count is verified to be 5,612 before and after ingestion.
   - Both backend test suites (`backend/tests` and `cortex-enterprise/backend/tests`) execute successfully.

---

## 3. Caveats

- In `frontend-next/src/app/(sheet)/chart/page.tsx`, `nodes` depends on `focus`, `infra`, and active `hiddenTypes`. Filtering `nodes` ensures only active graph entities are searched.
- `test_live_agent_db_and_llm_e2e` in `backend/tests/test_m5_investigator_chat.py` attempts a live API call to Google's deprecated `gemini-2.5-flash` model if `GEMINI_API_KEY` is present. In CODE_ONLY or offline mode, run pytest with `-k "not test_live_agent_db_and_llm_e2e"`.

---

## 4. Conclusion & Concrete Implementation Plan

### Exact Code Changes for Worker/Implementer:

#### File: `frontend-next/src/app/(sheet)/chart/page.tsx`

1. **Update Import (Line 16)**:
   ```tsx
   import { REL_GROUPS, TYPE_LABEL } from "@/lib/notation";
   ```

2. **Add State Hooks (around line 39 in `ChartLens`)**:
   ```tsx
   const [searchQuery, setSearchQuery] = useState("");
   const [searchOpen, setSearchOpen] = useState(false);
   ```

3. **Add Filter Memo (around line 60, after `nodes` definition)**:
   ```tsx
   const searchResults = useMemo(() => {
     if (searchQuery.trim().length < 2) return [];
     const q = searchQuery.toLowerCase();
     return nodes.filter((n) => (n.label ?? "").toLowerCase().includes(q)).slice(0, 8);
   }, [nodes, searchQuery]);
   ```

4. **Insert Search Bar JSX (Line 88, right after `<div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">`)**:
   ```tsx
   {/* R4: Entity live search bar */}
   <div className="relative">
     <input
       type="text"
       value={searchQuery}
       onChange={(e) => {
         setSearchQuery(e.target.value);
         setSearchOpen(true);
       }}
       onFocus={() => {
         if (searchQuery.length >= 2) setSearchOpen(true);
       }}
       onBlur={() => {
         setTimeout(() => setSearchOpen(false), 150);
       }}
       onKeyDown={(e) => {
         if (e.key === "Escape") {
           setSearchQuery("");
           setSearchOpen(false);
         }
       }}
       placeholder="Search entities…"
       className="label border border-rule-strong bg-film px-2 py-0.5 text-[length:var(--fs-note)] w-40 focus:outline-none focus:border-ink"
     />
     {searchQuery.length >= 2 && searchOpen && (
       <ul className="absolute left-0 top-full z-20 mt-1 max-h-60 w-56 overflow-y-auto border border-rule-strong bg-film-lift shadow-sm">
         {searchResults.length > 0 ? (
           searchResults.map((node) => (
             <li
               key={node.id}
               onMouseDown={(e) => e.preventDefault()}
               onClick={() => {
                 select(node.id);
                 setSearchQuery("");
                 setSearchOpen(false);
               }}
               className="flex cursor-pointer items-center justify-between gap-2 px-2 py-1 text-[length:var(--fs-note)] hover:bg-film-deep"
             >
               <span className="truncate text-ink">{node.label}</span>
               <span className="label shrink-0 text-ink-faint">
                 {TYPE_LABEL[node.type] ?? node.type}
               </span>
             </li>
           ))
         ) : (
           <li className="px-2 py-1 text-[length:var(--fs-note)] text-ink-faint">
             No entities found
           </li>
         )}
       </ul>
     )}
   </div>
   ```

---

## 5. Verification Method

To verify the implementation independently:

1. **Verify Frontend TypeScript Compilation**:
   ```powershell
   cd c:\Users\NIRJHAR BARMA\Desktop\batcave\frontend-next
   npx tsc --noEmit
   ```
   Expect: Zero errors across `src/app/(sheet)/chart/page.tsx` and all application components.

2. **Verify Database Re-ingestion**:
   ```powershell
   cd c:\Users\NIRJHAR BARMA\Desktop\batcave\backend
   .\venv\Scripts\python.exe -m app.ingestion.load_demo_case
   ```
   Expect: "Operation CyberHawk 2.0 loaded" with 5612 entities and 20 sealed documents.

3. **Verify Baseline Entity Count**:
   ```powershell
   cd c:\Users\NIRJHAR BARMA\Desktop\batcave\backend
   .\venv\Scripts\python.exe -c "from app.db import SessionLocal; from app.db import Entity; db=SessionLocal(); print('Entities:', db.query(Entity).count())"
   ```
   Expect: `Entities: 5612`.

4. **Verify Backend Tests**:
   ```powershell
   cd c:\Users\NIRJHAR BARMA\Desktop\batcave\backend
   .\venv\Scripts\pytest.exe -k "not test_live_agent_db_and_llm_e2e"
   ```
   Expect: 116 passed.

5. **Verify Cortex-Enterprise Tests**:
   ```powershell
   cd c:\Users\NIRJHAR BARMA\Desktop\batcave\backend
   .\venv\Scripts\pytest.exe -v ..\cortex-enterprise\backend\tests\test_m3_m6_tagging_map.py
   ```
   Expect: 8 passed.
