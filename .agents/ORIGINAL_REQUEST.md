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
