# SIH 26189 — AI-Powered Criminal Network Analysis System
## Project Plan

**Problem:** Ministry of Home Affairs / NCRB. Police data is scattered across FIRs, call records,
bank transfers, surveillance notes, social media and intelligence reports. Investigators cannot
manually connect it. Build an AI system that reads all of it, maps the criminal network, finds the
key people, detects suspicious patterns, and gives investigators visual + analytical insight.

---

## 1. What the system does (in plain terms)

| Requirement in the problem statement | How we do it |
|---|---|
| Collect and process data from multiple sources | 7 ingest formats: FIR text, CDR CSV, bank CSV, KYC CSV, surveillance JSON, social JSON, intel notes |
| Extract entities (people, locations, vehicles, phones, orgs) | Rule-based NER tuned for Indian police language + optional Claude LLM boost |
| Build relationship maps | Every entity + link stored in a graph, with the exact sentence that proves it |
| Identify key individuals | PageRank / betweenness / eigenvector + evidence score → one "priority" number |
| Detect suspicious patterns | 7 detectors: burner phones, cash structuring, laundering chains, call bursts, night activity, foreign contacts, ML outliers |
| Visual + analytical insight for investigators | React console: live graph, map, timeline, alerts, chat assistant, PDF brief |

---

## 2. Architecture

```
  DATA IN                    BRAIN (Python/FastAPI)               FACE (React)
  ─────────                  ──────────────────────               ────────────
  FIR text        ┐                                          ┐
  CDR CSV         │      1. Ingestion + NER                   │   Overview dashboard
  Bank CSV        ├───►  2. Entity resolution (dedup/alias)   ├─► Network graph
  KYC CSV         │      3. Graph store (SQLite + NetworkX)   │   Map + timeline
  Surveillance    │      4. Analytics (centrality, community) │   Alerts triage
  Social media    │      5. Anomaly detection (rules + ML)    │   AI chat
  Intel reports   ┘      6. AI assistant + PDF reports        ┘   Upload page
  Live web sources ──────┘
```

**Why SQLite + NetworkX, not Neo4j:** zero install, runs on a judge's laptop offline, and we ship a
Neo4j export so scaling is a config change, not a rewrite. (One rival repo needs a Neo4j server.)

---

## 3. Status

### DONE — Phase 3b: real data by default (9 Sep 2026)
- The default sheet is now built from **real public records** on first start (`CNA_DEFAULT_CORPUS=real`, loader `backend/app/ingestion/real_corpus.py`, ~55 s online):
  ICIJ Offshore Leaks India subset (nominee hubs dropped), OpenSanctions crime list (India), INTERPOL red notices (India), MHA banned organisations / UAPA designations,
  NSE-SEBI debarred entities, GLEIF ownership trees, NIA wanted list, Supreme Court 2024 criminal judgments, crime-desk RSS; then watchlist screening.
- Synthetic "Operation Saltwater" kept as fallback (`CNA_DEFAULT_CORPUS=demo`; old DB at `backend/data/cna.demo.db`). Sheet identity (title/code/kind/sources) is served by `/api/analytics/summary` and drives every header.
- Honesty rules for real data: no name-only merges across structured sources (namesakes split, screening relates them with a score and strong/weak grade); debarment-only listings are not persons of interest; new `public_records` detector (wanted person controls companies, debarred company shares directors, offshore officer accused, mass directorship).
- Frontend: chart lens defaults to the actor projection with shelf-packed components; overview draws the largest connected networks; "Add / Rebuild from public records" controls on the Sources lens (`POST /api/sources/corpus/real`).

### DONE — Phase 2: analytics & AI upgrades (tested 8 Sep 2026)

| Upgrade | Module | Verified result |
|---|---|---|
| **rustworkx** centrality | `graph/fastmetrics.py` | **3.1× faster** on the live graph (0.062 s vs 0.193 s); PageRank parity with NetworkX **r = 1.0000**; identical top-5 ranking. Falls back automatically; `CNA_DISABLE_RUSTWORKX=1` forces NetworkX. Betweenness stays NetworkX-weighted-exact ≤600 nodes, switches to rustworkx exact-unweighted above (beats NetworkX's random 300-pivot sampling) |
| **PyOD ECOD ensemble** | `graph/anomalies.py` | ECOD + Isolation Forest; agreement raises the score. Flags **8/8 genuine** actors (incl. foreign handler *Abu Hamza* and both burner identities). Per-feature attribution now from ECOD's dimensional scores, not a surrogate |
| **GLiNER zero-shot NER** | `ingestion/neural_ner.py` | Tier 2 of 3. Finds what no regex can: `Mephedrone` 0.94, `country-made pistol` 0.83, `12.4 kg` 0.81, and a label invented at query time — `gang name → D-Company` 0.85. Opt-in (`CNA_NEURAL_NER_ENABLED=true`, `[neural]` extra) |
| **Pattern validation** | `neural_ner._valid` | The model labelled *"Salim Bhai"* a **phone number** (0.65); validation rejects it so the transformer can't corrupt the graph |
| **Semantic search** | `ai/semantic.py` | fastembed/ONNX, no PyTorch. *"money laundering through fake companies"* → the PMLA FIR (0.664) and the FIU-IND STR report (0.661) |
| **API** | `api/routes_ai.py` | `/api/ai/status`, `/search`, `/similar/{id}`, `/extract/preview`, `/extract/labels`, `/compute/benchmark` |

**Ground truth after Phase 2:** top-5 precision 0.8, but **all 10 of the top 10 are genuine
network members (10/10, zero false positives)** — Rakesh Mehta sits at #6, 0.004 behind a real
money mule. The ensemble made anomaly detection strictly more accurate; the #5/#6 order is noise.

**Tests:** 30 passing (`tests/test_sources.py`, `tests/test_analytics_upgrades.py`).

### DONE — Backend (tested, working)

| Module | What it does |
|---|---|
| `data/generate_dataset.py` | Builds the benchmark case with a hidden answer key |
| `app/ingestion/ner.py` | Extracts persons, phones, plates, accounts, orgs, places, aliases, IPC sections |
| `app/ingestion/resolution.py` | Merges "Salim Bhai" = "Salim Qureshi"; splits different people with the same name |
| `app/ingestion/pipeline.py` | 7 source parsers, provenance, timeline events, IMEI handset linking |
| `app/graph/store.py` | Graph persistence + fast in-memory view |
| `app/graph/analytics.py` | Centrality, Louvain communities, roles, link prediction, arrest-impact simulation |
| `app/graph/anomalies.py` | 7 explainable detectors |
| `app/ai/investigator.py` | Plain-English Q&A over the graph |
| `app/ai/llm.py` | Optional Claude enrichment (system works fully without a key) |
| `app/reports/generator.py` | Markdown + PDF case brief |
| `app/auth.py` + `app/api/*` | JWT login, 3 roles, audit log, 30+ endpoints, WebSocket progress |

**Measured result on the benchmark:** top-5 key players **5/5 correct**; kingpin correctly labelled
"Leader (insulated)"; both burner phones attributed to the right person via IMEI; the full
laundering chain recovered. Ingest 4,484 records in 1.3s; analytics in 0.6s.

### TO DO

1. **Frontend console** (biggest piece) — 8 screens listed in §5.
2. **Live data sourcing** (§4) — because we must show real data, not only our own.
3. **Tests, Docker, README, pitch script.**

---

## 4. The data question — settled and BUILT (`backend/app/sources/`)

There is **no official dataset** for this problem, and real FIRs / CDRs / bank records are
confidential by law. Every team will face this. Our answer: a resilient connector layer over
**10 verified public sources**, plus a benchmark with an answer key. Every connector is a
well-behaved client — robots.txt respected, per-host rate limits, exponential backoff, on-disk
cache (demo works offline), graceful `blocked / unavailable` reporting. **No CAPTCHA or
access-control bypass anywhere**; portals that gate content are reported, not defeated.

| Connector | Source | What it loads (verified 8 Sep 2026) | Licence |
|---|---|---|---|
| `courts` | **eCourts via AWS Open Data** | Supreme Court 1950–2025 + 25 High Courts; parties, judges, CNR, dates. 200 criminal cases in 0.8 s | CC-BY-4.0 |
| `wanted` | **NIA + UP/Assam Police** | Public most-wanted / proclaimed-offender notices (163 named persons) | Public notice |
| `icij` | **ICIJ Offshore Leaks** | 3.3 M real relationships; India subset = 1,613 nodes / 1,779 edges in 3 s | ODbL |
| `gleif` | **GLEIF** | 392,552 Indian legal entities with CIN/GSTIN + corporate ownership graph (Tata Sons → TCS → subsidiaries) | CC0 |
| `opensanctions` | **OpenSanctions** | 477 datasets incl. 12,799 INTERPOL Red Notices; watchlist screening + entity-resolution benchmark | CC-BY-NC |
| `benchmarks` | **Netzschleuder** | Montreal Police gang intelligence, 9/11 & Madrid cells, St. Louis police-record network, Enron temporal graph | Academic |
| `news` | TOI / The Hindu / Indian Express RSS | Live crime OSINT → same NER pipeline | Publisher RSS |
| `datagovin` | **data.gov.in (NCRB/MHA)** | 1,536 crime statistics datasets (needs a free personal key; shared key is throttled) | GODL-India |
| `ncrb` | NCRB via data.gov.in | ncrb.gov.in disallows crawlers → served only through its official OGD channel | GODL-India |
| `cctns_mh` | Maharashtra CCTNS | Published FIR search, driven by a real browser (optional Playwright) | Public notice |

**Measured on real data (single run, `tests`/scratch harness):** 3,954 entities, 4,191 relationships
from 10 sources in under 20 s; entity-resolution recall vs OpenSanctions cross-source links **0.68**
(0.38 exact-key only); Louvain recovers the true **4 gang groups** on Montreal Police data at
resolution 0.4–0.6 (ARI 0.23, purity up to 0.69); 9/11 cell purity **0.76**.

Blocked from a datacentre IP but fine in a browser in India: MCA, NPCI, eCourts front-end
(all geo/IP-filtered; and eCourts data is already available via the AWS mirror).

**Pitch line:** "Reads real Indian court records and wanted lists, screens against live INTERPOL
notices, handles Panama-Papers scale — and proves 5/5 accuracy on a benchmark with an answer key."

---

## 5. Frontend screens

1. **Login** — role-based (admin / analyst / viewer).
2. **Overview** — counts, top alerts, key players, activity chart, source breakdown.
3. **Network Graph** — force-directed, colour by type, size by importance, click a node → dossier
   drawer with evidence; filters; "find path between two people"; arrest-impact button.
4. **Key Players & Communities** — ranked table with *why* each person scored high.
5. **Alerts** — severity-sorted cards, evidence expandable, mark confirmed / dismissed.
6. **Map & Timeline** — Leaflet map of Mumbai with sightings + NCRB hotspot layer; scrubbing timeline.
7. **AI Assistant** — chat; answers highlight the relevant nodes on the graph.
8. **Data Sources** — upload files with live progress bar, paste an FIR, or pull live web sources.

**Look:** dark command-centre theme, monospace accents, red/amber severity. Must look like a
government intelligence console, not a college project.

---

## 6. Build order

| Phase | Work | Why this order |
|---|---|---|
| **1** | Live sourcing module (Indian Kanoon + news + data.gov.in) | Backend-only, small; unblocks the "real data" story |
| **2** | Frontend screens 1–4 | The core demo |
| **3** | Frontend screens 5–8 | Completes the demo |
| **4** | Tests, Docker, README, pitch script + demo runbook | Submission requirements |

---

## 7. Competitive position

| | Rival A (kartikDevS) | Rival B (NITESH777RAJPUT) | **Ours** |
|---|---|---|---|
| Status | Mostly scaffolding, 3 commits | Working Streamlit app | Working full stack |
| UI | None | Streamlit | React console |
| Entity resolution | — | Shared identifiers | Alias + fuzzy + namesake splitting |
| Burner attribution | — | Flags shared phones | **Names the actual user via IMEI + tower** |
| Accuracy proof | — | — | **5/5 on ground truth** |
| Link prediction | Planned | No | Yes |
| Arrest-impact simulation | No | No | Yes |
| Map | No | No | Yes + real NCRB data |
| NL assistant | No | No | Yes |
| Real public data | No | No | Yes (judgments, news, data.gov.in) |

---

## 8. Demo script (5 minutes)

1. Login → Overview: "4,400 records from 7 sources, already processed."
2. Graph: "Thousands of ordinary people. Watch." → filter to persons of interest → the syndicate
   appears. Click Rafiq Sheikh → dossier with the FIR sentence that proves each link.
3. Alerts: open the burner phone alert → "the system worked out *who* was using an unregistered
   SIM, from the handset IMEI."
4. Money: show the laundering chain, mule → shell company → bullion → realty.
5. Ask the assistant: "What happens if we arrest Salim Qureshi?" → impact numbers.
6. Live sources: pull a real court judgment, watch it become new nodes.
7. Download the PDF brief. Close on the accuracy number.
