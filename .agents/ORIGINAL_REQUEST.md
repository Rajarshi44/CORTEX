# Original User Request

## 2026-09-15T15:50:36Z

An enterprise-grade, highly scalable Criminal Network Analysis (CNA) system modeled after industry leaders (e.g., Palantir Gotham, Chorus Intelligence) and top-tier Smart India Hackathon architectures. The system must feature robust backend graph algorithms, data ingestion pipelines, and a full-stack UI dashboard.

Working directory: c:\Users\NIRJHAR BARMA\Desktop\batcave\cortex-enterprise
Integrity mode: development

## Requirements

### R1. Scalable Data Ingestion & Integration
The system must provide a modular, cloud-ready ingestion layer capable of processing structured data (e.g., CSVs) and unstructured text. It must normalize this data into a unified, entity-centric schema.

### R2. Enterprise Knowledge Graph & Resolution
The system must construct a knowledge graph representing entities and relationships. It must include an entity resolution mechanism to handle aliases and fragmented identities across sources. The underlying technology is up to the team, but it must be scalable (e.g., capable of running as a microservice).

### R3. Analytical Engine (Influence & Suspicion)
The system must compute structural influence (centrality) and evidentiary suspicion. It must proactively flag "first-time offenders" or high-risk individuals based on their proximity to known criminal hubs within the network graph.

### R4. Automated Insights & Contradiction Detection
The system must automatically generate insights, specifically detecting deliberate communication gaps (anti-forensics/ghost nodes) and cross-referencing timeline events to flag narrative contradictions.

### R5. Full-Stack User Interface
The system must include a functioning web-based UI dashboard connected to the backend API, allowing an investigator to visualize the graph, view alerts, and explore entities.

## Acceptance Criteria

### Data & API Verification
- [ ] The backend must expose a RESTful or GraphQL API.
- [ ] An automated test script (`test_ingestion_pipeline.py` or equivalent) must successfully ingest a sample dataset (provided in the repository) and return HTTP 200/201 without errors.
- [ ] A test script must query the API for a specific entity and verify that resolved aliases return a unified entity profile.

### Graph Analytics Verification
- [ ] An automated test (`test_graph_analytics.py` or equivalent) must run community detection and centrality algorithms on a mock dataset of at least 500 nodes and return ranked results within 2 seconds.
- [ ] A test must verify that a node with 0 historical crimes but direct links to 3 "high-suspicion" nodes receives a high "proximity risk" score (first-time offender flagging).

### Insight Generation Verification
- [ ] A test script must feed contradictory timeline data (e.g., Person A claims to be at Location X, but CDR data places them at Location Y) and assert that a "CONTRADICTION" alert is generated.
- [ ] A test must assert that a "ghost node" or "anti-forensic" alert is generated when two highly clustered communities lack a direct bridge.

### UI Verification
- [ ] The frontend must successfully compile/build without fatal errors.
- [ ] A basic integration test or end-to-end test (e.g., using Playwright or basic curl checks on frontend routes) must verify that the dashboard loads and successfully connects to the backend API.

## 2026-09-17T20:10:06Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Fix and polish the CORTEX application for an SIH 2026 demo, focusing on victim protection, demo reliability, AI chat, data tagging, and a verifiable ledger.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Integrity mode: benchmark

## Requirements

### R1. Victim Protection & Masking
Add party roles (victim, complainant, witness, police). Exclude these roles from risk scoring, first-time-offender scoring, and community membership. Mask victim identities by role throughout the UI (including the Brief and PDF).

### R2. Investigator AI Chat
Replace the canned answers with a functional chat. Use a real LLM API (e.g., Gemini or OpenAI). The chat must ask for case-specific details to answer accurately, fetch data from the database, and provide a functional option to search the internet (articles, news, etc.).

### R3. Demo Loader Fixes
Correctly fix the command structure edges (`REL_TYPE` mapping) in the demo loader (e.g., preventing `CONTROLS` from becoming `OWNS_ACCOUNT`).

### R4. Synthetic Data Tagging
Treat all ingested data as real system data by default, unless explicitly marked as unverified or from uploaded sources. Add UI capabilities for manual tagging if automated tagging fails to correctly tag.

### R5. Verifiable Evidence Ledger
Implement the "blockchain" claims using real cryptography: Sign entries (Ed25519) and create Merkle batches with inclusion proofs using a standard Python crypto library. Persist an external anchor, seal CSV bytes and PDF exports, and add a "verify this brief" QR code.

### R6. Demo Reliability & UI Polish
Fix the map rendering (resolve the MapLibre bug, center on Delhi). Add a small CDR file to ensure call detectors fire. Remove the "SYNTHETIC DEMO DATA" ribbon and fix provenance labels. 
*Note: Do NOT fix security flaws like the JWT secret, rate limiting, or raw PII storage, as requested by the user.*

## Acceptance Criteria

### Victim Protection
- [ ] No victim or complainant entities appear in the top risk rankings.
- [ ] Victim names are replaced with masked roles (e.g., "[VICTIM]") in the frontend.

### Investigator AI Chat
- [ ] Queries for case facts retrieve actual database content using a real LLM.
- [ ] A web search fallback/option successfully retrieves live data from the internet.

### Loader & Data Tagging
- [ ] Graph database shows correct edge types for command structures.
- [ ] Ingested data displays "Real" or verified provenance unless manually overridden.

### Ledger & Demo Reliability
- [ ] Ledger exports contain verifiable cryptographic signatures and a QR code.
- [ ] Map renders correctly, centered on Delhi, with visible basemap tiles.
- [ ] Call detectors fire successfully using the provided CDR file.

## 2026-09-23T13:29:42Z

Implement chat history persistence for the Investigator AI assistant so that context is retained across questions during a session. 

Working directory: c:\Users\NIRJHAR BARMA\Desktop\batcave
Integrity mode: benchmark

## Requirements

### R1. Database Persistence
Create a new database model (e.g. `ChatSession`) to store investigator chat histories permanently, linked to the active `User`.

### R2. Backend API Integration
Update the `/assistant/ask` route to accept a `session_id`. If omitted, generate a new session. Read the past session history from the database, append it to the LLM context so the assistant can answer follow-up questions, and save the newly generated response back to the database.

### R3. Frontend UI Updates
Modify the Investigator UI in the Next.js frontend to maintain the current `session_id` in its state, pass it on subsequent requests, and render the entire conversation history instead of just the latest Q&A pair. Ensure it persists correctly across browser reloads if the user re-opens that session.

## Acceptance Criteria

### Backend Verification
- [ ] An automated test script (`test_investigator.py`) exists that makes two sequential API calls to `/assistant/ask` sharing the same `session_id`, and verifies that the LLM successfully references the entity from the first question in the second question.

### Frontend Verification
- [ ] Asking "Who is the mastermind?" followed by "What did they do?" correctly surfaces the context of the mastermind in the UI.
- [ ] Refreshing the investigator page and retrieving the active session restores the full chat history.

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

## 2026-09-23T13:59:39Z

The server restarted and all tasks were stopped. Please revive the Project Orchestrator (afb5f31a-635c-4f1f-a04e-bc5395058e32) and continue the 5 milestones to completion. Check the current status and resume where you left off.

## 2026-09-23T14:11:00Z

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


