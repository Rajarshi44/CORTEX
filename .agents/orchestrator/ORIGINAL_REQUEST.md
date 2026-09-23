# Original User Request

## 2026-09-15T16:03:13Z

An enterprise-grade, highly scalable Criminal Network Analysis (CNA) system named cortex-enterprise modeled after industry leaders (e.g., Palantir Gotham, Chorus Intelligence) and top-tier Smart India Hackathon architectures. The system must feature robust backend graph algorithms, data ingestion pipelines, and a full-stack UI dashboard.

Working directory: c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise
Integrity mode: development

Key Objectives & Requirements:
R1. Scalable Data Ingestion & Integration (structured CSVs and unstructured text, normalized entity-centric schema)
R2. Enterprise Knowledge Graph & Resolution (graph representation, alias and fragmented identity resolution microservice/module)
R3. Analytical Engine (structural influence/centrality, evidentiary suspicion, proximity risk / first-time offender flagging based on links to high-suspicion nodes)
R4. Automated Insights & Contradiction Detection (deliberate communication gaps / ghost nodes / anti-forensic detection, timeline event narrative contradiction detection)
R5. Full-Stack User Interface (web-based UI dashboard connected to backend API for graph visualization, alerts, entity exploration)

Acceptance Criteria to Implement and Verify:
- Backend RESTful or GraphQL API exposed.
- Automated test (e.g. test_ingestion_pipeline.py) ingests sample dataset and returns HTTP 200/201 without errors.
- Query API for specific entity verifies resolved aliases return unified entity profile.
- Automated test (e.g. test_graph_analytics.py) runs community detection and centrality on mock dataset >= 500 nodes and returns ranked results within 2 seconds.
- Test verifies node with 0 historical crimes but direct links to 3 high-suspicion nodes receives high proximity risk score (first-time offender flagging).
- Test feeds contradictory timeline data (e.g. claims location X, CDR places at location Y) and asserts CONTRADICTION alert generated.
- Test asserts ghost node / anti-forensic alert generated when two highly clustered communities lack direct bridge.
- Frontend compiles/builds without fatal errors.
- Basic integration / e2e test verifies dashboard loads and connects to backend API.

## 2026-09-15T16:17:00Z

You are resuming orchestration for cortex-enterprise. State has already been initialized in:
- c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator\PROJECT.md
- c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator\plan.md
- c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator\progress.md
- c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator\BRIEFING.md
- c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\ORIGINAL_REQUEST.md

Project target directory:
c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise
(Reference existing assets in c:\Users\NIRJHAR BARMA\Desktop\batcave: backend, frontend-next, demo-case-data).

Requirements & Acceptance Criteria:
R1. Scalable Ingestion & Integration (CSVs + unstructured text, normalized schema)
R2. Enterprise Knowledge Graph & Resolution (microservice/module, unified alias profile)
R3. Analytical Engine (centrality/influence, evidentiary suspicion, proximity risk / first-time offender flagging on 0 historical crimes + 3 high-suspicion links)
R4. Automated Insights & Contradiction Detection (timeline narrative contradictions, ghost node / anti-forensics between clusters)
R5. Full-Stack UI Dashboard (web UI connected to backend API)
Benchmark: test_graph_analytics.py on >= 500 nodes <= 2 seconds.
Ingestion test: test_ingestion_pipeline.py returns HTTP 200/201.
UI: builds cleanly and connects to backend.

Your Immediate Steps:
1. Re-read your BRIEFING.md, plan.md, and progress.md in c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator.
2. Note: when invoking subagents, you can specify Model: "pro" if needed.
3. Resume Milestone 1 (Exploration & Scaffolding) and dispatch specialists to execute milestones M1 through M6.
4. Keep progress.md regularly updated with timestamps.
5. On 100% completion of all milestones and tests, message Sentinel (parent) to trigger the mandatory Victory Audit.

## 2026-09-17T20:10:06Z

You are the Project Orchestrator for the CORTEX SIH 2026 fix and polish project.

Your working directory is: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Integrity mode: benchmark

The authoritative user request is documented in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\ORIGINAL_REQUEST.md` under section `## 2026-09-17T20:10:06Z`.

## Objectives & Requirements:
Fix and polish the CORTEX application for an SIH 2026 demo, focusing on victim protection, demo reliability, AI chat, data tagging, and a verifiable ledger.

### R1. Victim Protection & Masking
- Add party roles (victim, complainant, witness, police).
- Exclude these roles from risk scoring, first-time-offender scoring, and community membership.
- Mask victim identities by role throughout the UI (including the Brief and PDF).
- Acceptance: No victim or complainant entities appear in the top risk rankings; victim names are replaced with masked roles (e.g., "[VICTIM]") in frontend.

### R2. Investigator AI Chat
- Replace canned answers with a functional chat using a real LLM API (e.g. Gemini or OpenAI). Check environment variables/configuration.
- The chat must ask for case-specific details to answer accurately, fetch data from the database, and provide a functional option to search the internet (articles, news, etc.).
- Acceptance: Queries for case facts retrieve actual database content using real LLM; web search fallback/option successfully retrieves live data from internet.

### R3. Demo Loader Fixes
- Correctly fix command structure edges (`REL_TYPE` mapping) in the demo loader (e.g., preventing `CONTROLS` from becoming `OWNS_ACCOUNT`).
- Acceptance: Graph database shows correct edge types for command structures.

### R4. Synthetic Data Tagging
- Treat all ingested data as real system data by default, unless explicitly marked as unverified or from uploaded sources.
- Add UI capabilities for manual tagging if automated tagging fails to correctly tag.
- Acceptance: Ingested data displays "Real" or verified provenance unless manually overridden.

### R5. Verifiable Evidence Ledger
- Implement "blockchain" claims using real cryptography: Sign entries (Ed25519) and create Merkle batches with inclusion proofs using a standard Python crypto library.
- Persist an external anchor, seal CSV bytes and PDF exports, and add a "verify this brief" QR code.
- Acceptance: Ledger exports contain verifiable cryptographic signatures and a QR code.

### R6. Demo Reliability & UI Polish
- Fix map rendering (resolve MapLibre bug, center on Delhi, visible basemap tiles).
- Add a small CDR file to ensure call detectors fire.
- Remove "SYNTHETIC DEMO DATA" ribbon and fix provenance labels.
- Acceptance: Map renders correctly centered on Delhi with visible basemap tiles; call detectors fire successfully using provided CDR file.

*Note: Do NOT fix security flaws like the JWT secret, rate limiting, or raw PII storage, as requested by the user.*

## 2026-09-23T13:29:42Z

Title: Implement chat history persistence for the Investigator AI assistant so that context is retained across questions during a session.
Integrity mode: benchmark

Requirements:
1. R1. Database Persistence: Create a new database model (e.g. ChatSession) to store investigator chat histories permanently, linked to the active User.
2. R2. Backend API Integration: Update the `/assistant/ask` route to accept a `session_id`. If omitted, generate a new session. Read the past session history from the database, append it to the LLM context so the assistant can answer follow-up questions, and save the newly generated response back to the database.
3. R3. Frontend UI Updates: Modify the Investigator UI in the Next.js frontend to maintain the current `session_id` in its state, pass it on subsequent requests, and render the entire conversation history instead of just the latest Q&A pair. Ensure it persists correctly across browser reloads if the user re-opens that session.

Acceptance Criteria:
- Backend: An automated test script (`test_investigator.py`) exists that makes two sequential API calls to `/assistant/ask` sharing the same `session_id`, and verifies that the LLM successfully references the entity from the first question in the second question.
- Frontend:
  - Asking "Who is the mastermind?" followed by "What did they do?" correctly surfaces the context of the mastermind in the UI.
  - Refreshing the investigator page and retrieving the active session restores the full chat history.

## 2026-09-23T13:50:27Z

CORTEX is a graph-based criminal intelligence analysis platform for an SIH 2026 demo.
The system already has a substantial dataset of cybercrime entities. The task is to:
1. Remove all "Operation CyberHawk 2.0" branding from the entire codebase with NO replacement operation name — the sheet identity should reflect the actual case corpus content dynamically
2. Add 3 real Indian cyber crime cases as new entity/relationship/document data in the CSV files, interconnected with the existing data where criminals overlap
3. Populate the Sources tab with realistic FIR, arrest notice, and news document entries
4. Add a live entity search bar to the chart page
5. Re-ingest and verify the database is richer and faster

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Integrity mode: demo

---

## Requirements

### R1. Remove All "Operation CyberHawk 2.0" Branding — No Replacement Name

Every occurrence of `Operation CyberHawk 2.0`, `OPS-CH2`, `CyberHawk` must be removed across:
- `backend/app/api/routes_graph.py`: `sheet_identity()` must return a neutral, data-driven title. Change the returned title to `"National Cyber Crime Investigation Corpus"`, code to `"NCIC-2026"`, subtitle to `"Cyber Crime Branch / IFSO — Multi-Jurisdiction Cybercrime Network Analysis"`. This applies to all 3 return branches (demo, unverified, real).
- `backend/app/ingestion/load_demo_case.py`: Change `SHEET_TITLE` to `"National Cyber Crime Investigation Corpus"`, `SHEET_SUBTITLE` to `"Cyber Crime Branch / IFSO — Digital Arrest, Financial Fraud, Mule Networks"`
- `backend/app/ai/demo_fallback.py`: Replace all narrative text referencing CyberHawk with equivalent text referencing the relevant criminal networks and persons by name
- `demo-case-data/01_entities_nodes.csv`: Replace all occurrences of `CyberHawk 2.0 Operation` and `CyberHawk 2.0 Bust` in the last column with `NCIC Investigation` and `NCIC Arrest` respectively (do a global find-replace in the CSV)
- `backend/tests/test_m3_m6_tagging_map.py`: Update assertion strings to match new title/code
- `backend/tests/test_m2_victim_protection.py`: Update case_name strings
- `cortex-enterprise/backend/app/api/routes_graph.py`: Same changes as primary
- `cortex-enterprise/backend/tests/test_m3_m6_tagging_map.py`: Same changes
- `README.md`, any `.agents/*/BRIEFING.md`, `.agents/*/handoff.md` files: update text

### R2. Add 3 Real Indian Cyber Crime Cases to CSV Data

Research using publicly available information and add realistic entity/relationship data for these 3 cases. The new entities must be interconnected with each other AND with existing entities where plausible (e.g., shared hawala networks, shared mule account handlers, same intermediaries used by multiple syndicates). This cross-case linking is critical to make the graph rich.

**Case A — Operation Chakra-II (CBI/Interpol, Oct 2023)**
Real public facts: CBI conducted Operation Chakra-II in partnership with Interpol, Microsoft, Amazon. Arrested individuals running fake tech support centers defrauding US/UK/Canadian victims. Entities to add:
- 8-10 PERSON nodes: arrested accused (e.g., Anil Kumar Trivedi, Vikram Bhai, Rohit Jha — names in public domain from CBI press release), victims (masked as [VICTIM])
- 3-4 ORGANIZATION nodes: fake tech support companies (e.g., "TechAssist Solutions Pvt Ltd"), shell payment processors
- 5-6 BANK_ACCOUNT nodes for money flow
- 3-4 PHONE_NUMBER nodes (call center numbers)
- Relationships: OPERATES, CONTROLS, CALLS, TRANSFERS_TO, MEMBER_OF
- 10-12 transactions in `03_financial_transactions.csv`
- 2 documents in `05_case_documents.csv`: CBI press release excerpt, FIR title

**Case B — Jamtara Phishing Syndicate (Multiple FIRs, 2020-2024)**
Real public facts: Jharkhand's Jamtara district, extensive media coverage (Netflix documentary), multiple state police FIRs. Accused: Naresh Mandal, Mohammad Sikander (named in news). OTP phishing, fake KYC calls, SIM cloning.
- 10-12 PERSON nodes: accused, recruiters, mule account holders (with Jharkhand addresses)
- 2-3 ORGANIZATION nodes: phishing gang cells
- 6-8 BANK_ACCOUNT nodes for mule accounts
- 4-5 PHONE_NUMBER nodes
- Timeline events: arrest dates, FIR registration dates
- 2 documents: FIR excerpt, news article

**Case C — Chinese Loan App Fraud (ED/MHA, 2022-2023)**
Real public facts: Ministry of Home Affairs flagged 100+ predatory loan apps. ED arrested Chinese nationals and Indian agents. Apps: CashZone, RuPay Now (names in public domain). Accused: Luo Sang (Chinese national, named in media), Bengaluru-based Indian intermediaries.
- 8-10 PERSON nodes: Chinese operators, Indian agents, victims (masked)
- 4-5 ORGANIZATION nodes: loan app companies, payment gateways, shell companies
- 6-8 BANK_ACCOUNT nodes
- Cross-links to existing mule network entities where relevant (reuse some existing entity IDs from the current dataset if they could plausibly be shared intermediaries)
- 2 documents: ED press release, news article

Entity ID numbering: continue from existing dataset. Check the last used IDs in `01_entities_nodes.csv` and use the next available numbers. Format: P3001, A3001, O301, etc.

For cross-case linking: add 5-8 relationships in `02_relationships_edges.csv` that connect entities across cases (e.g., a hawala operator who appears in both Chakra-II and the existing dataset, a mule account holder used by both Jamtara and the loan app fraud ring).

### R3. Populate Sources Tab with Public Documents

Add at least 8 realistic document entries to `demo-case-data/05_case_documents.csv`. Each must have:
- `id`: unique doc ID (e.g., DOC-CH2-001, DOC-JAM-001)
- `source_type`: one of `FIR`, `NEWS`, `ARREST_MEMO`, `JUDGMENT`
- `title`: realistic title (e.g., "FIR No. 234/2023 PS Jamtara — OTP Phishing Case")
- `content`: 3-5 sentences of realistic language based on public information (NOT placeholder text)
- `source_name`: e.g., "Jharkhand Police", "CBI Press Release", "Economic Times"
- `occurred_at`: realistic date (2022-2024)
- `case_id`: `DEMO-01`

At least 3 must be `FIR` or `ARREST_MEMO` type.

### R4. Add Entity Search Bar to Chart Page

Edit `frontend-next/src/app/(sheet)/chart/page.tsx`.

Add a search input and dropdown immediately inside the existing control bar `<div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule-strong bg-film-lift px-3 py-1.5">` — insert it as the FIRST child before the existing `<span className="label label-ink">` span.

Implementation:
- Add `useState` for `searchQuery` (string) and `searchOpen` (boolean)
- Filter `nodes` by `node.label.toLowerCase().includes(searchQuery.toLowerCase())` when query length >= 2
- Render a `<div className="relative">` containing:
  - An `<input>` with placeholder "Search entities…", styled as `label border border-rule-strong bg-film px-2 py-0.5 text-[length:var(--fs-note)] w-40 focus:outline-none focus:border-ink`
  - A dropdown `<ul>` (absolute positioned, z-20, max 8 items) that appears when `searchQuery.length >= 2 && searchOpen`
  - Each dropdown `<li>` renders the node label and type; clicking it calls `select(node.id)` and clears the query
  - Pressing Escape clears the query; `onBlur` with 150ms delay closes the dropdown

### R5. Re-ingest the Database After All Changes

After all CSV and code changes are complete, run the ingestion script:
```
cd c:\Users\NIRJHAR BARMA\Desktop\batcave\backend
.\venv\Scripts\python.exe -m app.ingestion.load_demo_case
```

Then verify:
```
.\venv\Scripts\python.exe -c "from app.db import SessionLocal; from app.db import Entity; db=SessionLocal(); print('Entities:', db.query(Entity).count())"
```

The entity count must be higher than the pre-task count.

---

## Acceptance Criteria

### Branding Removal
- [ ] `grep -r "CyberHawk" backend/ frontend-next/ demo-case-data/ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.csv"` returns zero results
- [ ] The `/api/sheet/identity` endpoint (with auth) returns `"code": "NCIC-2026"` and `"title": "National Cyber Crime Investigation Corpus"`

### New Crime Data
- [ ] `01_entities_nodes.csv` contains at least 45 more entity rows than before
- [ ] `05_case_documents.csv` contains at least 8 more document lines than before
- [ ] At least 5 cross-case relationships exist in `02_relationships_edges.csv` linking entities from different cases

### Sources Tab
- [ ] After re-ingestion, `SELECT COUNT(*) FROM documents WHERE source_type IN ('FIR', 'ARREST_MEMO')` returns >= 3
- [ ] The `/sources` page in the frontend shows non-empty document list

### Chart Search
- [ ] A search input labeled "Search entities…" appears in the chart control bar
- [ ] Typing at least 2 characters shows a dropdown of matching entity names
- [ ] Selecting a result from the dropdown opens the side drawer for that entity

### Re-ingestion
- [ ] `load_demo_case.py` exits with code 0
- [ ] Entity count after ingestion is higher than before

## 2026-09-23T14:16:31Z

You are the Project Orchestrator for the CORTEX SIH 2026 demo project.
Your working directory is: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\orchestrator`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Integrity mode: demo

The authoritative user request is in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\ORIGINAL_REQUEST.md`.

Summary of status and assets already completed:
1. Exploration Phase:
   - Data & Documents (R2 & R3): Complete ready-to-insert data is available in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_data_r2_r3\handoff.md`. It contains 46+ new entity rows for Chakra-II, Jamtara Phishing, and Chinese Loan App Fraud, 12 transactions, 7 cross-case edges, and 8 realistic documents (with >=3 FIR/ARREST_MEMO).
   - Chart Search Bar & DB Ingestion (R4 & R5): Exact implementation diff and instructions are available in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_chart_search_r4_r5\handoff.md`.
   - Rebranding (R1): Check `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\explorer_rebrand_r1_gen2/` or review all occurrences of CyberHawk in `backend/app/api/routes_graph.py`, `backend/app/ingestion/load_demo_case.py`, `backend/app/ai/demo_fallback.py`, `demo-case-data/01_entities_nodes.csv`, tests, and `cortex-enterprise/`.
2. Action plan:
   - Initialize your `BRIEFING.md`, `plan.md`, and `progress.md` in `.agents/orchestrator/`.
   - Dispatch Implementation Worker(s) to execute the changes across files.
   - Re-ingest database using `python -m app.ingestion.load_demo_case` in `backend/` and verify the entity count is higher.
   - Run verification checks (grep for CyberHawk returning 0, tests passing, Sources document count).
   - Review and challenge implementation.
   - When all milestones and acceptance criteria are 100% complete and verified, send a message to Sentinel (parent) claiming victory so the mandatory Victory Audit can be initiated. Do NOT report completion to the user directly.

