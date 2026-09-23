"""Hardcoded fallback answers for demo showcasing.

When the LLM provider is unavailable (rate-limited, down, no key), the investigator
falls back to these pre-built answers derived directly from the demo-case-data CSVs.
No database queries are made — every fact here is from the CSV files.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Answer bank: each entry is (keywords, answer_text, highlights, visuals, citations)
# Keywords are checked with `all(kw in question for kw in keywords)`
# More specific patterns (more keywords) are checked first.
# ---------------------------------------------------------------------------

_ANSWERS: list[dict[str, Any]] = [
    # ---- Overview / who runs this ----
    {
        "keywords": ["who", "run"],
        "answer": (
            "**Prabhakar Kumar** (P002) is the primary operator of the digital-arrest fraud network (SN-A), "
            "operating the spoofed WhatsApp number used to extort ₹1,16,00,000 from the 82-year-old victim. "
            "**Rupesh Kumar Singh** (P003) recruited operators from Bihar. **Dev Raj** (P004) fronted the NGO "
            "in Sirmaur, HP that received ₹1.10 crore and was linked to 32 NCRP complaints totalling ~₹24 crore.\n\n"
            "In the transnational syndicate (SN-C), **Arjun Das** (P013) and **Nitin Rawat** (P014) are the "
            "end-user tier, while **Abdul Karim** (P015) runs the hawala channel and **Vikram Joshi** (P016) "
            "handles crypto conversion. The IFSO primary account (A006) processed 10,000+ transactions worth "
            "₹5.24 crore in just 5 days.\n\n"
            "**Rahul alias Happy** (P005) — the main beneficiary of the student mule ring (SN-B) — remains "
            "**at large**.\n\n"
            "*(Source: 01_entities_nodes.csv, 02_relationships_edges.csv, 05_case_documents.csv)*\n\n"
            "**Next step**: Prioritise locating Rahul (P005) — he bridges SN-B to the other networks and is the only HIGH-risk accused not yet arrested."
        ),
        "visuals": [{"kind": "stat", "title": "Network at a glance",
                     "items": [{"label": "Accused persons", "value": "15"},
                               {"label": "Sub-networks", "value": "3"},
                               {"label": "Total defrauded", "value": "₹24+ Cr"},
                               {"label": "At large", "value": "1 (Rahul)"}]}],
    },
    # ---- Prabhakar Kumar ----
    {
        "keywords": ["prabhakar"],
        "answer": (
            "**Prabhakar Kumar** (P002) is an accused caller/operator in Sub-Network A (Digital Arrest Scam), "
            "based in Nalanda, Bihar. Risk flag: **HIGH**.\n\n"
            "- Operated the spoofed WhatsApp number (+919999999991) to impersonate law enforcement "
            "*(source: 02_relationships_edges.csv, E001)*\n"
            "- Called the victim's phone, showing a fake arrest order via video call "
            "*(source: 05_case_documents.csv, DOC-001)*\n"
            "- Arrested on 05 Dec 2025 from Nalanda, Bihar "
            "*(source: 05_case_documents.csv, DOC-002 — Arrest Memo)*\n"
            "- Connected to Rupesh Kumar Singh (recruiter) and Dev Raj (NGO front) "
            "*(source: 02_relationships_edges.csv)*\n\n"
            "**Next step**: Pull CDR analysis on his phone (PH003) to map his full contact network."
        ),
        "visuals": [],
    },
    # ---- Rahul / Happy ----
    {
        "keywords": ["rahul"],
        "answer": (
            "**Rahul alias Happy** (P005) is the main beneficiary of the student mule ring (SN-B). "
            "Status: **AT LARGE** — not yet arrested. Risk flag: **HIGH**.\n\n"
            "- Two 19-year-old students (Amit Verma, Sunil Yadav) opened mule accounts and SIM cards for him "
            "*(source: 01_entities_nodes.csv, 05_case_documents.csv DOC-005)*\n"
            "- ₹1,08,000 traced across 3 mule accounts (A003, A004, A005) "
            "*(source: 03_financial_transactions.csv)*\n"
            "- Phone PH004 (+919999999994) — alias 'Happy' on this number "
            "*(source: 01_entities_nodes.csv)*\n"
            "- Cross-network links: phone contact with Abdul Karim's hawala network (SN-C) "
            "*(source: 02_relationships_edges.csv, E050)*\n"
            "- 4 alias variants on file: Rahul Kumar, R. Kumar, Happy Singh — confidence 0.38–0.95 "
            "*(source: 06_aliases_unresolved.csv)*\n\n"
            "**Next step**: Issue a standing watch on all alias variants and monitor mule account A003–A005 for new inflows."
        ),
        "visuals": [],
    },
    # ---- Money trail / trace money ----
    {
        "keywords": ["money"],
        "answer": (
            "The money flows through three distinct channels:\n\n"
            "**SN-A (Digital Arrest Fraud)**:\n"
            "- Victim (A002) → NGO Current Account A001: ₹1,16,00,000 via NEFT "
            "*(source: 03_financial_transactions.csv, TXN202500017)*\n"
            "- A001 received ₹24+ crore from 12+ NCRP complainants across India "
            "*(source: 04_ncrp_complaints.csv)*\n"
            "- A001 → Intermediary A010 → Prabhakar's personal A011 → Rupesh's personal A012 "
            "*(source: 03_financial_transactions.csv, TXN202500018–25)*\n\n"
            "**SN-B (Mule Ring)**: ₹1,08,000 layered through 3 student mule accounts A003–A005 "
            "*(source: 03_financial_transactions.csv, TXN202500026–35)*\n\n"
            "**SN-C (IFSO Syndicate)**:\n"
            "- Primary account A006: **10,000+ transactions, ₹5.24 crore in 5 days** "
            "*(source: 01_entities_nodes.csv, 03_financial_transactions.csv TXN202500036–95)*\n"
            "- A006 → Secondary A007/A008 → Hawala clearing A009 → Crypto wallets CW001/CW002 "
            "*(source: 02_relationships_edges.csv, 03_financial_transactions.csv)*\n\n"
            "*(Source: 03_financial_transactions.csv — 104 transactions total, span Mar–Dec 2025)*\n\n"
            "**Next step**: Freeze A009 (hawala clearing) — it is the single choke point between fiat and crypto."
        ),
        "visuals": [{"kind": "stat", "title": "Financial summary",
                     "items": [{"label": "Total transactions", "value": "104"},
                               {"label": "SN-A defrauded", "value": "₹24+ Cr"},
                               {"label": "SN-C 5-day burst", "value": "₹5.24 Cr"},
                               {"label": "SN-B traced", "value": "₹1.08 L"}]}],
    },
    # ---- Key players ----
    {
        "keywords": ["key", "player"],
        "answer": (
            "The 6 highest-risk actors across all three sub-networks:\n\n"
            "| # | Name | Role | Sub-network | Risk | Status |\n"
            "|---|------|------|-------------|------|--------|\n"
            "| 1 | **Prabhakar Kumar** (P002) | Caller/Operator | SN-A | HIGH | Accused |\n"
            "| 2 | **Rahul alias Happy** (P005) | Main Beneficiary | SN-B | HIGH | **At Large** |\n"
            "| 3 | **Dev Raj** (P004) | NGO Front Operator | SN-A | HIGH | Accused |\n"
            "| 4 | **Abdul Karim** (P015) | Hawala Operator | SN-C | HIGH | Accused |\n"
            "| 5 | **Vikram Joshi** (P016) | Crypto Converter | SN-C | HIGH | Accused |\n"
            "| 6 | **Arjun Das** (P013) | End-user Tier | SN-C | HIGH | Accused |\n\n"
            "*(Source: 01_entities_nodes.csv — all HIGH-risk flagged persons)*\n\n"
            "**Next step**: Map cross-network edges between these 6 — E050–E054 show Rahul bridging SN-B to SN-C."
        ),
        "visuals": [],
    },
    # ---- Communities / sub-networks ----
    {
        "keywords": ["communit"],
        "answer": (
            "The corpus contains **3 distinct sub-networks** (communities):\n\n"
            "**SN-A — Digital Arrest / NGO Hub Scam**\n"
            "- 3 accused: Prabhakar Kumar, Rupesh Kumar Singh, Dev Raj\n"
            "- Hub node: NGO Current Account A001 (32 NCRP complaints, ~₹24 Cr)\n"
            "- Modus: fake arrest order via WhatsApp video call\n"
            "*(source: 01_entities_nodes.csv, 04_ncrp_complaints.csv)*\n\n"
            "**SN-B — Student Mule Ring**\n"
            "- 3 persons: Rahul (at large), Amit Verma, Sunil Yadav (both 19-yr students)\n"
            "- 3 mule accounts, 3 mule SIMs\n"
            "- ₹1,08,000 traced\n"
            "*(source: 01_entities_nodes.csv, 05_case_documents.csv DOC-005)*\n\n"
            "**SN-C — IFSO Transnational Syndicate**\n"
            "- 9 accused across 3 tiers: account holders → middlemen → end users\n"
            "- Dwarka hotel raid on 26 Nov 2025\n"
            "- A006: 10,000+ txns, ₹5.24 Cr in 5 days; laundered via hawala + crypto\n"
            "*(source: 01_entities_nodes.csv, 07_timeline_events.csv EV-015)*\n\n"
            "**Cross-network bridges**: 12 edges link the three networks (E050–E070) "
            "*(source: 02_relationships_edges.csv)*\n\n"
            "**Next step**: Focus on the 12 cross-network edges — dismantling the bridges isolates each cell."
        ),
        "visuals": [],
    },
    # ---- NGO / account A001 ----
    {
        "keywords": ["ngo"],
        "answer": (
            "The **Unidentified NGO** (O001) in Sirmaur, HP is the money laundering front for SN-A. "
            "Operated by **Dev Raj** (P004). Risk flag: **HIGH**.\n\n"
            "- Its current account **A001** is the central hub node with 32 NCRP complaints totalling ~₹24 crore "
            "*(source: 01_entities_nodes.csv, 04_ncrp_complaints.csv)*\n"
            "- Received ₹1,16,00,000 from the 82-year-old victim "
            "*(source: 03_financial_transactions.csv, TXN202500017)*\n"
            "- Complainants span 7 states: Delhi, Maharashtra, West Bengal, Tamil Nadu, Karnataka, Rajasthan, UP "
            "*(source: 04_ncrp_complaints.csv)*\n"
            "- ₹1.10 crore of victim's funds traced to this account "
            "*(source: 05_case_documents.csv, DOC-001)*\n\n"
            "**Next step**: Obtain full KYC and account-opening records for A001 to identify the beneficial owner chain."
        ),
        "visuals": [],
    },
    # ---- Case overview / what is this ----
    {
        "keywords": ["case"],
        "answer": (
            "**National Cyber Crime Investigation Corpus** — Delhi Police Crime Branch / IFSO investigation announced 13 Dec 2025.\n\n"
            "An 82-year-old victim was defrauded of ₹1,16,00,000 through a 'digital arrest' scam — a fake arrest "
            "order shown via WhatsApp video call. The investigation uncovered three interconnected criminal sub-networks:\n\n"
            "- **SN-A**: Digital arrest fraud ring (Bihar → HP), using an NGO as a money laundering front. "
            "32 NCRP complaints, ~₹24 Cr total. 3 arrested.\n"
            "- **SN-B**: Student mule ring (2 students, age 19). ₹1.08L traced. Main beneficiary Rahul **at large**.\n"
            "- **SN-C**: Transnational syndicate. 9 arrested in Dwarka hotel raid (26 Nov 2025). "
            "₹5.24 Cr laundered in 5 days via hawala and crypto.\n\n"
            "**Corpus**: 16 persons, 3 orgs, 12 bank accounts, 5 phones, 3 SIMs, 2 crypto wallets, 15 locations. "
            "104 financial transactions. 16 documents (FIRs, arrest memos, raid reports, forensic reports).\n\n"
            "*(Source: demo-case-data/README.md, 01_entities_nodes.csv, 05_case_documents.csv)*\n\n"
            "**Next step**: Run community detection to verify whether the 12 cross-network edges warrant merging SN-A and SN-C into a single investigation."
        ),
        "visuals": [{"kind": "stat", "title": "Case at a glance",
                     "items": [{"label": "Victim loss", "value": "₹1.16 Cr"},
                               {"label": "Total NCRP complaints", "value": "32"},
                               {"label": "Accused", "value": "15"},
                               {"label": "At large", "value": "1"}]}],
    },
    # ---- Alerts / suspicious ----
    {
        "keywords": ["alert"],
        "answer": (
            "The system flagged **5 alerts** from the demo case data:\n\n"
            "1. **Burst anomaly** on A006 — 10,000+ transactions in 5 days (₹5.24 Cr) "
            "*(source: 01_entities_nodes.csv, 03_financial_transactions.csv)*\n"
            "2. **Hub accumulation** on A001 — 32 NCRP complaints converging on one account "
            "*(source: 04_ncrp_complaints.csv)*\n"
            "3. **Unverified SIM cluster** — 3 mule SIMs (SIM001–003) with no KYC "
            "*(source: 01_entities_nodes.csv)*\n"
            "4. **Cross-network bridge** — Rahul (P005) linked to both SN-B and SN-C "
            "*(source: 02_relationships_edges.csv, E050)*\n"
            "5. **Hawala channel** — Abdul Karim (P015) operating parallel settlement "
            "*(source: 02_relationships_edges.csv, 03_financial_transactions.csv)*\n\n"
            "**Next step**: Prioritise the burst anomaly on A006 — the 5-day window suggests an active operation window that may recur."
        ),
        "visuals": [],
    },
    # ---- Biggest company / organisation ----
    {
        "keywords": ["biggest", "company"],
        "answer": (
            "The largest organisation in this corpus is the **Unidentified NGO** (O001) based in Sirmaur, "
            "Himachal Pradesh — a shell entity used as a money laundering front for the digital arrest scam (SN-A).\n\n"
            "- Operated by **Dev Raj** (P004), arrested 08 Dec 2025 "
            "*(source: 05_case_documents.csv, DOC-004)*\n"
            "- Its current account A001 accumulated **₹24+ crore** across **32 NCRP complaints** from 7 states "
            "*(source: 04_ncrp_complaints.csv, 01_entities_nodes.csv)*\n"
            "- The **Transnational Hawala Network** (O002) and **Student Mule Ring** (O003) are the other two orgs "
            "*(source: 01_entities_nodes.csv)*\n\n"
            "**Next step**: Check MCA/ROC filings for O001's registration details and director history."
        ),
        "visuals": [],
    },
    # ---- Dev Raj ----
    {
        "keywords": ["dev raj"],
        "answer": (
            "**Dev Raj** (P004) is the NGO Front Operator in Sub-Network A, based in Sirmaur, Himachal Pradesh. "
            "Risk flag: **HIGH**.\n\n"
            "- Controlled the Unidentified NGO (O001) and its current account A001 "
            "*(source: 02_relationships_edges.csv, E013)*\n"
            "- A001 received ₹1.10 Cr from the victim and ~₹24 Cr from 32 NCRP complainants "
            "*(source: 04_ncrp_complaints.csv, 03_financial_transactions.csv)*\n"
            "- Arrested on 08 Dec 2025 from Sirmaur, HP "
            "*(source: 05_case_documents.csv, DOC-004)*\n"
            "- Phone: PH005 (+919999999995) "
            "*(source: 01_entities_nodes.csv)*\n\n"
            "**Next step**: Examine A001's full statement for outflows to identify upstream beneficiaries."
        ),
        "visuals": [],
    },
    # ---- IFSO / raid / dwarka ----
    {
        "keywords": ["ifso"],
        "answer": (
            "The **IFSO (Intelligence Fusion and Strategic Operations)** unit conducted a raid at a Dwarka Sector 12 "
            "hotel on **26 November 2025**, arresting 9 accused across three tiers:\n\n"
            "- **Account Holders**: Mohammad Irfan (P008), Vijay Sharma (P009), Ravi Tiwari (P010)\n"
            "- **Middlemen**: Deepak Mehra (P011), Sanjay Gupta (P012)\n"
            "- **End Users**: Arjun Das (P013), Nitin Rawat (P014)\n"
            "- **Hawala**: Abdul Karim (P015)\n"
            "- **Crypto**: Vikram Joshi (P016)\n\n"
            "Primary account A006 processed **10,000+ transactions worth ₹5.24 crore in 5 days**. "
            "Funds were layered through A007/A008, cleared via hawala (A009), and converted to crypto (CW001/CW002).\n\n"
            "*(Source: 01_entities_nodes.csv, 05_case_documents.csv DOC-006/007, 07_timeline_events.csv EV-015)*\n\n"
            "**Next step**: Trace the crypto wallets CW001/CW002 on-chain to identify the final beneficiary addresses."
        ),
        "visuals": [],
    },
    # ---- Timeline / chronology ----
    {
        "keywords": ["timeline"],
        "answer": (
            "**Key events** (from 07_timeline_events.csv):\n\n"
            "| Date | Event | Sub-network |\n"
            "|------|-------|-------------|\n"
            "| Mar 2025 | First NCRP complaints filed against A001 | SN-A |\n"
            "| Oct 2025 | Mule accounts opened by students | SN-B |\n"
            "| 05 Nov 2025 | Victim receives digital arrest WhatsApp call | SN-A |\n"
            "| 15 Nov 2025 | ₹1.16 Cr transferred to NGO account | SN-A |\n"
            "| 21–25 Nov 2025 | A006 burst: 10,000+ txns in 5 days | SN-C |\n"
            "| 26 Nov 2025 | IFSO raid at Dwarka hotel — 9 arrested | SN-C |\n"
            "| 01 Dec 2025 | Student mule network FIR filed | SN-B |\n"
            "| 05–08 Dec 2025 | Arrests: Prabhakar, Rupesh, Dev Raj | SN-A |\n"
            "| 13 Dec 2025 | Intelligence note linking all 3 networks | Cross |\n\n"
            "*(Source: 07_timeline_events.csv — 24 events total, span Mar–Dec 2025)*\n\n"
            "**Next step**: Overlay the transaction timeline on the event timeline to find the 48-hour window where SN-C and SN-A moved money simultaneously."
        ),
        "visuals": [],
    },
]

# ---- Generic fallback ----
_GENERIC = (
    "This corpus covers the **National Cyber Crime Investigation Corpus** — a Delhi Police Crime Branch / IFSO investigation into a "
    "digital-arrest fraud, mule-account ring, and transnational hawala/crypto syndicate.\n\n"
    "The sheet contains **94 entities**, **192 relationships**, **104 financial transactions**, and "
    "**16 case documents** across 3 sub-networks (SN-A, SN-B, SN-C).\n\n"
    "Try asking:\n"
    "- *Who runs this network?*\n"
    "- *Trace the money trail*\n"
    "- *Who is Rahul?*\n"
    "- *What communities exist?*\n"
    "- *Show the timeline*\n\n"
    "*(Source: demo-case-data — all 8 CSV files)*"
)


def match(question: str) -> dict | None:
    """Find the best matching hardcoded answer for a question. Returns None if no match."""
    q = question.lower().strip()
    # Try most-specific matches first (most keywords)
    scored = []
    for entry in _ANSWERS:
        kws = entry["keywords"]
        if all(kw in q for kw in kws):
            scored.append((len(kws), entry))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])  # most keywords = best match
    return scored[0][1]


def fallback_stream(question: str):
    """Yield agent-compatible events for a hardcoded answer."""
    entry = match(question)
    answer = entry["answer"] if entry else _GENERIC
    visuals = entry.get("visuals", []) if entry else []

    yield {"type": "start", "providers": [{"key": "fallback", "label": "Demo Fallback", "model": "hardcoded", "available": True}],
           "provider": "fallback", "model": "hardcoded (demo-case-data)", "tools": 0}
    yield {"type": "step", "n": 1}
    yield {"type": "text", "delta": answer}
    for v in visuals:
        yield {"type": "visual", "visual": v}
    yield {"type": "done", "answer": answer, "steps": 1, "seconds": 0.01,
           "highlight_nodes": [], "highlights": {"nodes": [], "edges": []},
           "visuals": visuals, "citations": [], "usage": {"provider": "fallback", "model": "hardcoded"}}
