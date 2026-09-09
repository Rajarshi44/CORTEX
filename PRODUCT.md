# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js 16 (App Router) + TypeScript, Tailwind CSS 4, shadcn/ui, Sigma.js 3 + graphology (WebGL graph), MapLibre GL + OpenFreeMap tiles (no key), TanStack Query 5, Zustand 5, Motion 13, nuqs. Pinned by the user. Backend already built: FastAPI at `localhost:8000`, 50+ endpoints under `/api/*`, JWT bearer auth, WebSocket at `/api/ingest/ws`. Frontend lives in `frontend/` (currently an empty Vite scaffold to be replaced).

## Name

**SUTRA** — Sanskrit for *thread*. The system follows the thread that runs through fragmented records (an FIR here, a call record there, a bank transfer elsewhere) and ties them into one network. Name chosen by the assistant at the user's request; user may rename. Expansion for formal use: *System for Unified Threat Relationship Analytics*.

## Users

- **Investigating officers and crime-branch analysts** (the durable user): at a district or state police desk, working a case across weeks, moving between FIR text, CDRs, bank statements and surveillance notes. Job: find who is connected to whom, who matters, what is suspicious, and produce a brief that survives a court.
- **SIH 2026 judges** (the decisive first audience): a 5-minute live demo on a laptop, presenter-driven, evaluating whether the system is real, accurate and different from other teams'. The user asked for both audiences to be served equally: a presentation mode that changes density and pacing, not a separate product.

## Product Purpose

Turn fragmented, multi-source crime data into an explorable criminal network with explainable scores, so an investigator finds hidden relationships and key individuals in minutes instead of weeks, and every claim carries the sentence and document that supports it. Success: an officer can answer "who runs this, who bridges the groups, what is suspicious, and why" with evidence attached, and a judge believes it within five minutes.

## Positioning

Problem statement SIH 26189 (Ministry of Home Affairs / NCRB, Women Safety Division). What a neighbouring project cannot truthfully copy:

- **Measured accuracy** on a benchmark case with a hidden answer key (top-10 key players 10/10 genuine network members; 8/8 anomaly flags genuine), plus validation on published real networks (Montreal Police gang intelligence, Madrid/9-11 cells, Elliptic, OpenSanctions cross-source identity links).
- **Real Indian data live**: eCourts judgments (25 High Courts + Supreme Court), NIA and state police wanted lists, data.gov.in NCRB statistics, GLEIF, ICIJ Offshore Leaks, OpenSanctions/INTERPOL — through robots-respecting connectors with offline cache.
- **Provenance on every edge** and a tamper-evident evidence hash-chain; Aadhaar/PAN checksum-validated and stored masked.
- **Burner-phone attribution via handset IMEI and cell towers**, behavioural case linkage (serial-offender leads), disruption simulation ("what if we arrest X").
- Runs fully offline on one laptop; no cloud, no paid services, no CAPTCHA or access-control bypass anywhere.

## Operating Context

- Inputs in real police formats: FIR narratives (Indian legal English: `r/o`, `u/s 302 IPC`, `X @ alias`), CDR CSV with towers and IMEI, bank/UPI transfer CSV, KYC CSV, surveillance JSON, social posts, intel notes, court judgments, wanted-list pages, news RSS.
- Demo corpus: "Operation Saltwater", a fictional Mumbai/JNPT narcotics + hawala network (Rafiq Sheikh @ Bhai, Salim Qureshi, Vikram Naik, Mahesh Jain, Rakesh Mehta; burner phones, structured deposits, a layering chain) buried in ordinary citizens' records. Labelled synthetic; ground truth in `backend/data/samples/ground_truth.json`.
- Demo machine: a laptop, likely 1366×768 or 1920×1080, projector, presenter talking while clicking. Real deployment: district-office desktops, often offline.
- Backend concepts the UI must carry faithfully: entity types (PERSON, PHONE, LOCATION, VEHICLE, ORGANIZATION, BANK_ACCOUNT, CASE, REPORT, SOCIAL_HANDLE, GOV_ID), 25+ relationship types, communities, roles (Leader (insulated), Broker / Bridge, Coordinator / Hub, Financial conduit, Operative, Money mule, Unverified identity, Well-connected (no adverse record)), three scores (influence = structural, suspicion = evidentiary, priority = fusion), alert severities (critical/high/medium/low) and kinds (burner_phone, structuring, layering, call_burst, night_activity, international_contact, behavioural_outlier), evidence with document + snippet + extractor tier (rules / gliner / llm / checksum / structured), ledger entries, case-linkage series ("candidate leads, never matches").

## Capabilities and Constraints

- Every score and alert is explainable: reasons, drivers, and the evidence snippet must be one click away, never hidden.
- Analytical outputs are leads, not accusations: copy must never assert guilt; case linkage is labelled "candidate leads".
- Aadhaar/PAN/passport appear only masked (`XXXX-XXXX-6789`).
- Must work with the backend offline (cached sources), and must degrade gracefully when a live source is `blocked`/`unavailable` (the API reports this; the UI must show it, not break).
- Optional tiers may be absent on a given machine: neural NER (GLiNER), Claude, Playwright; the UI must reflect `/api/ai/status` truthfully.
- Auth: JWT, roles admin / analyst / viewer. Viewer cannot ingest or change alert status.
- Graph sizes: demo ≈ 460 nodes / 2,500 edges; real-data loads reach ~4,000 nodes; ICIJ full is 3.3M edges (served in subsets). Rendering must stay smooth at a few thousand nodes.
- Undecided: final production hosting; whether presentation mode persists per user or per session.

## Brand Commitments

None imposed. User granted full creative freedom; no Government of India emblem required, no mandated colours. Product name SUTRA (see Name). Voice: precise, calm, evidentiary; never sensational.

## Evidence on Hand

- Working backend with measured results (see Positioning); numbers recorded in `PLAN.md`.
- Demo corpus files in `backend/data/samples/`; ICIJ India subset, court metadata, wanted lists and news load live via `/api/sources/*`.
- Screenshots, logos, imagery: none exist. Anything visual is authored in this build and labelled synthetic where a viewer could mistake it for real. No testimonials, deployments or endorsements exist and must not be invented.

## Product Principles

1. Evidence before assertion: every number, label and line can be traced to a document and a sentence.
2. The network is the interface: exploration starts from the graph, everything else is a lens on it.
3. Explain, never accuse: scores are decomposed, language names leads and signals, not guilt.
4. Two audiences, one truth: presentation mode changes pacing and density, never the data or its caveats.
5. Works on the desk it lands on: offline, single laptop, degrades honestly when a source or model is missing.

## Accessibility & Inclusion

No standard mandated. Applied baseline: WCAG 2.1 AA contrast, full keyboard operation of graph selection and panels, visible focus, reduced-motion respected, screen-reader labels on all controls and on graph node selection.
