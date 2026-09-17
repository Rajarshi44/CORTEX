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
