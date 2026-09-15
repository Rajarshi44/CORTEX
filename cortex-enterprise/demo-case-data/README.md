# Delhi Police Crime Branch — Criminal Network Analysis Demo Dataset

> **DISCLAIMER**: This dataset is constructed for demonstration purposes based on publicly reported facts from the Delhi Police Crime Branch Cyber Cell announcement of 13 December 2025 (Tribune News Service). All FIR numbers, account numbers, and CNR numbers are **illustrative and synthetic** — they do not represent actual case identifiers. All named individuals are **accused persons, not convicted**. Synthetic names are clearly marked.

## Source Case
- **Announcing Authority**: Delhi Police Crime Branch Cyber Cell
- **Date**: 13 December 2025
- **Key Facts**: ₹1.16 crore defrauded from 82-year-old victim via digital arrest scam; interstate and transnational network dismantled

## Three Sub-Networks

### SN-A: Digital Arrest / NGO Hub Scam
- Modus operandi: Fake arrest order shown via WhatsApp video call
- ₹1.16 crore transferred under psychological duress
- ₹1.10 crore traced to NGO current account in Himachal Pradesh
- NGO account had **32 separate NCRP complaints** totalling ~₹24 crore
- **Accused**: Prabhakar Kumar, Rupesh Kumar Singh, Dev Raj
- **Demo capability**: Hub/centrality detection

### SN-B: Operation CyberHawk 2.0 — Student Mule Ring
- Two 19-year-old students opened mule bank accounts + SIM cards
- ₹1.08 lakh traced across 3 accounts
- Main beneficiary: **"Rahul alias Happy"** — still at large
- **Demo capability**: Entity resolution / alias matching

### SN-C: IFSO Transnational Syndicate
- Dwarka hotel raid on 26 November 2025
- 9 arrested across three tiers: account holders → middlemen → end users
- Laundering via hawala and crypto conversion
- One account: **10,000+ transactions worth ₹5.24 crore in 5 days**
- **Demo capability**: Anomaly detection, community detection, multi-hop path-finding

## Files

| File | Description | Rows | Key Demo Feature |
|------|-------------|------|------------------|
| `01_entities_nodes.csv` | All network nodes (persons, orgs, accounts, phones, SIMs, crypto wallets) | ~40 | Node types, risk flags |
| `02_relationships_edges.csv` | All connections between entities | ~65 | Hub detection, community structure |
| `03_financial_transactions.csv` | Detailed transaction records across all sub-networks | ~110 | Burst anomaly, money trail |
| `04_ncrp_complaints.csv` | NCRP complaints linking to NGO hub account | 12 | Hub accumulation pattern |
| `05_case_documents.csv` | FIRs, arrest memos, raid reports, forensic reports | ~15 | Document-entity linking |
| `06_aliases_unresolved.csv` | Alias matching records | ~12 | Entity resolution demo |
| `07_timeline_events.csv` | Chronological event timeline | ~28 | Temporal analysis |
| `08_geo_locations.csv` | Geographic coordinates for all locations | ~15 | Map visualization |

## How to Use

1. **Upload** all CSV files to the criminal network analysis platform
2. **Entities & Relationships** (`01_` and `02_`) form the core graph — watch the NGO account (A001) emerge as a high-betweenness hub
3. **Transactions** (`03_`) feed the financial analysis — the 5-day burst on A006 should trigger anomaly alerts
4. **NCRP Complaints** (`04_`) demonstrate how the hub would have been flagged early (after complaint #3, not #32)
5. **Aliases** (`06_`) demonstrate entity resolution — 'Rahul' ↔ 'Happy' as a pending match
6. **Timeline** (`07_`) and **Geo** (`08_`) power the temporal and spatial views
7. **Community detection** (Leiden algorithm) should automatically split SN-A, SN-B, and SN-C into distinct clusters

## Entity ID Reference

- **P001–P016**: Persons
- **O001–O003**: Organizations  
- **A001–A012**: Bank Accounts
- **PH001–PH005**: Phone Numbers
- **SIM001–SIM003**: SIM Cards
- **CW001–CW002**: Crypto Wallets
- **LOC001–LOC015**: Locations
