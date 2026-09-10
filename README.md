# CORTEX — Criminal Organization Relationship & Threat EXplorer

**SIH 26189 · Ministry of Home Affairs / NCRB · Women Safety Division**

Crime information is scattered. The phone log sits with a telecom operator, the transfer with a
bank, the judgment with a court, the wanted notice on a police website. No single office sees all
of it, so a criminal network stays invisible. CORTEX collects those pieces, joins them, draws one
map, and says who matters on it and why.

Nothing on a CORTEX sheet asserts guilt. Every line is backed by a document and a sentence, and
every score decomposes into reasons you can read.

---

## Run it

```bash
npm install          # once, at the repo root, for the two-process dev scripts
npm run dev          # API on :8000, console on :3000, against whatever backend/.env points at
```

Or start the two halves by hand:

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000   # docs at /docs
cd frontend-next && npm run dev                                             # http://localhost:3000
```

**The demo sheet.** `npm run dev:demo` (or `./run_demo.ps1`) loads Operation CyberHawk 2.0 from
`demo-case-data/*.csv` into its own SQLite file and serves it on :8001 / :3001, so it never touches
the database `backend/.env` names. `npm run demo:seed` reloads just the data. The loader is
idempotent - entity ids are derived with uuid5 from the case, so a reload replaces the sheet rather
than doubling it.

Sign in as `analyst` / `analyst@123` (or `admin` / `admin@123` for the destructive controls).

Configuration lives in `backend/.env` (never committed). `backend/.env.example` documents every
setting. The one that matters most is `CNA_DATABASE_URL`; `CNA_DEFAULT_CORPUS` decides what an
empty database fills itself with (`real`, `demo`, or `none`).

---

## How a record becomes a finding

Two phases. Ingestion turns records into a graph; analysis turns the graph into findings.

| # | Stage | What happens | Where |
|---|-------|--------------|-------|
| 1 | Collect | Nine public sources are fetched, politely (robots.txt, rate limits, retries, disk cache) | `app/sources/`, `app/ingestion/real_corpus.py` |
| 2 | Seal | Each document is hashed into an append-only chain, so later tampering is detectable | `app/graph/ledger.py` |
| 3 | Read | Names, phones, vehicles, orgs and the verbs between them are extracted from prose | `app/ingestion/ner.py` |
| 4 | Verify | Aadhaar, PAN, GSTIN, IFSC are checksum-validated, stored masked | `app/ingestion/identifiers.py` |
| 5 | Resolve | Decide whether two mentions are the same person. The hardest step | `app/ingestion/resolution.py` |
| 6 | Accumulate | Repeated observations collapse into one weighted edge that remembers its count | `app/graph/store.py` |
| 7 | Project | Phones and accounts fold onto their owners, leaving a person-to-person graph | `app/graph/analytics.py` |
| 8 | Score | Suspicion from the papers, influence from the position, then rank | `app/graph/analytics.py` |
| 9 | Detect | Ten detectors look for burner phones, structuring, layering routes, pass-through accounts, complaint hubs, cross-source patterns | `app/graph/anomalies.py` |
| 10 | Snapshot | Conclusions are computed once and stored, so the console loads instantly | `app/api/deps.py` |

The ranking is **55% structural influence + 45% evidentiary suspicion**. Both are required, which
is why a well-connected businessman with no adverse record is labelled *well connected* rather
than flagged as a suspect.

---

## Backend: where is what

Everything is under `backend/app/`.

### Start here
| File | Its one job |
|------|-------------|
| `main.py` | Starts the API, mounts routes, fills an empty database on first run |
| `config.py` | Every setting, with defaults. Read this to learn what can be tuned |
| `db.py` | The nine database tables. The whole data model in one file |

### `sources/` — getting data in
| File | Source |
|------|--------|
| `base.py` | Shared fetching: robots.txt, rate limits, retries, disk cache. Every connector inherits this |
| `icij.py` | ICIJ Offshore Leaks — officers, offshore companies, intermediaries |
| `opensanctions.py` | OpenSanctions: crime list, INTERPOL red notices, MHA banned list, SEBI debarred |
| `courts.py` | Supreme Court judgments via the AWS Open Data mirror of eCourts |
| `gleif.py` | GLEIF — corporate ownership trees |
| `indiagov.py` | data.gov.in, NCRB, NIA and state police wanted lists |
| `news.py` | Crime desks of Indian national newspapers (RSS) |
| `benchmarks.py` | Labelled research networks, used to validate the algorithms. Not operational data |
| `browser.py` | Playwright fallback for pages rendered client-side. Optional |

### `ingestion/` — turning records into a graph
| File | Its one job |
|------|-------------|
| `pipeline.py` | **The spine.** Every source funnels through here. Read this first |
| `ner.py` | Rule-based extraction tuned for Indian police text. Deterministic, no model |
| `neural_ner.py` | Optional zero-shot transformer tier (GLiNER). Off by default |
| `resolution.py` | Is this the same person? Aliases, nicknames, fuzzy matching, namesake splitting |
| `quality.py` | Entity hygiene. What is allowed to become a node at all |
| `identifiers.py` | Aadhaar (Verhoeff), PAN, GSTIN, IFSC validation and masking |
| `provenance.py` | Turns a document into a source name and a verifiable URL |
| `geo.py` | Indian cities, states and their coordinates |
| `real_corpus.py` | Chains every connector to build the default public-record sheet |
| `load_demo_case.py` | Loads `demo-case-data/*.csv` as a structured sheet, in the vocabulary the analytics read |
| `enrich_text.py` | Re-fetches article bodies for documents stored as headlines, then extracts |
| `cleanup.py` | One-off repairs: contamination, duplicate documents, addresses stored as places |
| `backfill.py` | Repeatable repairs over data already loaded |

### `graph/` — the analysis engine
| File | Its one job |
|------|-------------|
| `store.py` | Edge accumulation, and the in-memory graph the analysis runs on |
| `analytics.py` | Projection, suspicion, centralities, communities, roles, ranking, predictions |
| `fastmetrics.py` | Chooses between rustworkx (fast) and NetworkX (weighted), and says which it used |
| `anomalies.py` | The ten detectors, and the roster the register reads to say why a quiet one is quiet |
| `ledger.py` | The tamper-evident evidence chain |
| `queries.py` | Everything the API reads: entity dossiers, paths, timelines, money and call profiles |
| `case_linkage.py` | Behavioural linkage — which offences may share an offender |

### `watch/` — standing queries
| File | Its one job |
|------|-------------|
| `matcher.py` | Selector normalisation, and the scan that fires a watch on every arriving record |

A detector reads the whole sheet and is redrawn on every recompute. A watch does the opposite: it
names one selector - a person, organisation, phone, vehicle, account, government identifier or a
literal phrase - and checks it against each record as that record arrives, keeping the hit with the
document that caused it. Arming a watch also searches everything already held, so *has this ever
appeared* is answered immediately rather than only from the next harvest.

### `ai/` — optional language-model tier
| File | Its one job |
|------|-------------|
| `llm.py` | OpenRouter client. Span-grounded extraction and answer narration |
| `investigator.py` | Plain-language question answering, retrieved from the graph |
| `semantic.py` | Meaning-based document search (embeddings, runs locally) |

### `api/` — the HTTP surface
One router per area: `routes_auth`, `routes_graph`, `routes_ingest`, `routes_intel`,
`routes_sources`, `routes_ai`, `routes_forensics`, `routes_watch`. `deps.py` holds the analysis service that
computes the snapshot once and caches it.

---

## Frontend: where is what

Under `frontend-next/src/`. Next.js App Router.

| Path | What it is |
|------|------------|
| `app/(sheet)/page.tsx` | Overview — the sheet's front matter |
| `app/(sheet)/chart/page.tsx` | The link chart |
| `app/(sheet)/players/page.tsx` | Key players, brokers, communities, disruption |
| `app/(sheet)/alerts/page.tsx` | The register of detector findings, and the standing watches that fire on arrival |
| `app/(sheet)/map/page.tsx` | Geography |
| `app/(sheet)/investigator/page.tsx` | Ask questions in plain language |
| `app/(sheet)/sources/page.tsx` | What is on the sheet, and how to add more |
| `app/(sheet)/ledger/page.tsx` | Chain of custody, benchmarks, the brief |
| `components/chart/LinkChart.tsx` | The canvas renderer for the chart |
| `components/sheet/` | Chrome shared by every lens |
| `lib/api.ts` | Every API call, in one file |
| `lib/notation.ts` | The visual language: shapes per entity type, line styles per evidence grade |
| `lib/types.ts` | TypeScript types matching the API |
| `app/globals.css` | Design tokens. Read before touching any styling |

**The notation matters.** Shape encodes entity type (circle person, square organisation, diamond
phone, hexagon account, cut hexagon crypto wallet). Line style encodes how the link was learned: solid from a structured record, dashed
extracted from text by rules, dotted inferred by a model. Blue means money. That way a reader can
see the strength of the evidence without asking.

---

## Maintenance commands

```bash
cd backend
.venv/Scripts/python.exe -m app.ingestion.real_corpus         # build a public-record sheet
.venv/Scripts/python.exe -m app.ingestion.cleanup --dry-run   # show what a cleanup would remove
.venv/Scripts/python.exe -m app.ingestion.enrich_text --limit 40   # fetch article bodies, extract
.venv/Scripts/python.exe -m pytest -q tests                   # 54 tests
```

---

## Design decisions worth knowing

**Cross-source identity is never assumed from a name.** Two records naming "Rajiv Singh" in
different sources become two people. Screening may relate them later, with a score and a strength
grade. An earlier build merged them and produced a confident, entirely false alert about a wanted
man controlling a company, assembled from two different men.

**The evidence ledger is a hash chain, not a blockchain.** Consensus solves the problem of an
untrusted writer. Here the investigating agency *is* the trusted writer; what is needed is proof
that history was not silently rewritten. A chain gives that at zero cost.

**The language-model tier is optional and grounded.** It must quote the exact span it based each
relation on, and the quote is checked against the source text. Anything unverifiable is dropped, so
a hallucinated relationship cannot be stored. Per-document extraction is off by default because
one call costs tens of seconds.

**A watch is not an alert.** A detector alert is an inference over the whole corpus, so it is
recomputed and replaced whenever the corpus changes. A watch hit is a fact about one document that
arrived, so it is written once and never touched again - an analyst's decision on it survives every
recompute. They are stored in separate tables for that reason, and shown as separate registers.
Matching is exact on the resolver's canonical key: that rules out a watch silently widening into a
fuzzy name search, but it cannot rule out a namesake, which is why a hit shows the record and lets
the analyst judge rather than asserting an identity.

**A quiet detector is not a broken one, and the register says which.** `/api/alerts/detectors`
returns every detector with what it looks for and how many records of its kind the sheet actually
holds, so the Alerts lens can tell a reader that structuring *read 104 transfers and found nothing*
rather than leaving a gap where an explanation should be. The two silences are different findings:
one is a result, the other is a missing source.

**Scores never come from a model.** Centralities, communities and ranking are deterministic
mathematics, so "why is this person ranked highest" always has an arithmetic answer.
