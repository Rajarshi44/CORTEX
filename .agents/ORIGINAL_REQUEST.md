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
