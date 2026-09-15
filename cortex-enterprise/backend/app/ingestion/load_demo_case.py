"""Load the Delhi Crime Branch demo case (`demo-case-data/*.csv`) into a working sheet.

This is a *structured* loader, not the text pipeline: the CSVs already carry resolved entity ids,
so there is nothing for the extractor to guess and re-running it must produce the same graph. What
it does have to do is speak the vocabulary the rest of the system reads, because every downstream
stage is keyed on it:

  * entity types are the canonical ten (`ingestion/ner.ENTITY_TYPES`). A `PHONE_NUMBER` node is
    invisible to the burner-phone detector and shapeless on the chart;
  * an arrest memo becomes an `ACCUSED_IN` edge to a `CASE`, because that is the only thing that
    puts evidentiary suspicion on a person - without it every actor scores 0 and the timeline,
    which shows persons of interest, comes back empty;
  * a transfer becomes a `TimelineEvent` carrying `amount` / `from_holder` / `to_holder` / `txn_id`
    in `details`, which is the exact shape the structuring and layering detectors read;
  * a location becomes a real `LOCATION` node with coordinates, and events are geo-tagged, or the
    map has nothing to draw;
  * every document is sealed into the evidence ledger, so the chain of custody is not empty.

Ids are derived with uuid5 from the case and the CSV key, so a reload rewrites the same rows rather
than accumulating a second copy of the network.
"""
from __future__ import annotations

import csv
import os
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..db import (AnalysisSnapshot, Alert, Case, Document, Entity, Evidence, SessionLocal,
                  TimelineEvent, init_db)
from ..graph.ledger import LedgerEntry, attest_document
from ..watch import matcher
from ..graph.store import RelationshipAccumulator, add_entity_evidence, add_event, graph_cache
from .resolution import canonical_key

DEMO_DIR = Path(__file__).resolve().parents[3] / "demo-case-data"
CASE_ID = "DEMO-01"
NS = uuid.UUID("6f1d5e2c-9b3a-4a7e-8f21-0c4d8e6b1a55")  # stable namespace for this demo case

SHEET_TITLE = "Operation CyberHawk 2.0"
SHEET_SUBTITLE = "Delhi Police Crime Branch / IFSO — digital-arrest fraud, mule accounts, hawala and crypto layering."


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def _rows(filename: str) -> list[dict]:
    with open(DEMO_DIR / filename, encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _num(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _dt(date: str, time: str = "") -> datetime | None:
    date = (date or "").strip()
    if not date:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(f"{date} {time}".strip(), fmt)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------------------
# The dataset's own node vocabulary, mapped onto the canonical types. A SIM card is a subscriber
# number and belongs with phones - that is what makes it visible to the burner-phone detector and
# to the handset analysis - and it keeps `sim: true` so the sheet can still say which it was.
ENTITY_TYPE = {
    "PERSON": "PERSON",
    "ORGANIZATION": "ORGANIZATION",
    "BANK_ACCOUNT": "BANK_ACCOUNT",
    "CRYPTO_WALLET": "CRYPTO_WALLET",
    "PHONE_NUMBER": "PHONE",
    "SIM_CARD": "PHONE",
}

# The dataset's verbs, mapped onto the relationship vocabulary the analytics read. The two that
# matter most are the ownership edges: `USES_PHONE` and `OWNS_ACCOUNT` are what fold a phone or an
# account onto the person behind it, and an actor whose infrastructure does not fold has no
# projected links at all.
REL_TYPE = {
    "OPERATED_BY": "USES_PHONE",          # person -> phone they run
    "PROCURED_FOR": "USES_PHONE",         # person -> SIM they obtained
    "CONTROLS": "OWNS_ACCOUNT",           # person/org -> account or wallet
    "LAUNDERED_THROUGH": "OWNS_ACCOUNT",  # person -> the account they wash through
    "CALLED": "CALLED",
    "TRANSFERRED_TO": "TRANSFERRED_TO",
    "CONVERTED_VIA": "TRANSFERRED_TO",    # fiat -> crypto is still value leaving one store for another
    "ASSOCIATED_WITH": "ASSOCIATE_OF",
    "RECRUITED": "REPORTS_TO",            # reversed below: the recruit reports to the recruiter
    "LINKED_TO": "SHARED_HANDSET",        # a SIM seen in another number's handset
}
# Verbs whose direction in the CSV is the opposite of the direction the graph stores.
REVERSED = {"RECRUITED"}

# A document type says what kind of record it is, and that decides what it can assert. An arrest
# memo names an accused; a surveillance or forensic report names a subject; an intelligence note
# names a mention. Only the first carries an adverse finding.
DOC_KIND = {
    "FIR_EXTRACT": ("FIR", "CASE", "ACCUSED_IN"),
    "RAID_REPORT": ("FIR", "CASE", "ACCUSED_IN"),
    "ARREST_MEMO": ("FIR", None, "ACCUSED_IN"),
    "SURVEILLANCE_REPORT": ("SURVEILLANCE", "REPORT", "SUBJECT_OF"),
    "FORENSIC_REPORT": ("REPORT", "REPORT", "MENTIONED_IN"),
    "INTELLIGENCE_NOTE": ("INTEL", "REPORT", "MENTIONED_IN"),
}

# Standing watches the sheet opens with. A watch is not a detector: it names one selector and is
# checked against every record as it arrives, so these are the questions this case leaves open
# rather than conclusions it has reached.
WATCHES: list[tuple[str, str, str, str]] = [
    ("PERSON", "Rahul", "Named as the main beneficiary of the CyberHawk mule ring and not arrested. "
                        "Report any record naming him.", "critical"),
    ("BANK_ACCOUNT", "XXXX1234", "The NGO current account every digital-arrest complaint resolves to. "
                                 "Report any further record touching it.", "critical"),
    ("TEXT", "hawala", "Any record describing settlement through the hawala channel.", "high"),
]

# How a person or organisation is tied to a place, by what the place is.
PLACE_REL = {
    "RESIDENCE": "RESIDES_AT",
    "CRIME_SCENE": "SEEN_AT",
    "RAID_SITE": "SEEN_AT",
    "ARREST_LOCATION": "SEEN_AT",
    "OPERATIONAL_BASE": "SEEN_AT",
    "BANK_BRANCH": "LOCATED_AT",
}



# --------------------------------------------------------------------------------------
def load_demo_data(db: Session | None = None) -> dict:
    own_session = db is None
    db = db or SessionLocal()
    try:
        return _load(db)
    finally:
        if own_session:
            db.close()


def _wipe(db: Session) -> None:
    """Clear everything this loader writes, so a reload replaces the sheet rather than doubling it."""
    from ..db import EntityNote, Relationship, Watch, WatchHit

    db.query(WatchHit).delete()
    db.query(Watch).delete()
    db.query(EntityNote).delete()
    db.query(Evidence).delete()
    db.query(TimelineEvent).delete()
    db.query(Alert).delete()
    db.query(Relationship).delete()
    db.query(Entity).delete()
    db.query(Document).delete()
    db.query(Case).delete()
    db.query(AnalysisSnapshot).delete()
    db.query(LedgerEntry).delete()
    db.commit()


def _load(db: Session) -> dict:
    init_db()
    print("Clearing the demo sheet…")
    _wipe(db)

    acc = RelationshipAccumulator()
    ent: dict[str, Entity] = {}          # CSV entity_id -> Entity
    seen: dict[str, list[datetime]] = {}  # entity id -> observation times

    def touch(e: Entity, when: datetime | None) -> None:
        if when:
            seen.setdefault(e.id, []).append(when)

    taken: set[tuple[str, str]] = set()

    def put(key: str, etype: str, label: str, attrs: dict, *, aliases: list[str] | None = None) -> Entity:
        # Key the way `ingestion/resolution.canonical_key` keys, never on the CSV's own row id. The
        # resolver's key is what a standing watch matches on and what entity search resolves against;
        # storing "p005" here left a watch on "Rahul" armed and permanently silent.
        ck = canonical_key(etype, label) or key.lower()
        if (etype, ck) in taken:                  # two rows that normalise alike stay two entities
            ck = f"{ck}#{key.lower()}"
        taken.add((etype, ck))
        e = Entity(id=_id(etype, key), type=etype, label=label,
                   canonical_key=ck, aliases=aliases or [],
                   attributes={k: v for k, v in attrs.items() if v not in ("", None)})
        db.add(e)
        ent[key] = e
        return e

    db.add(Case(id=CASE_ID, name=SHEET_TITLE, description=SHEET_SUBTITLE))

    # ---------------------------------------------------------------- 1. entities
    for r in _rows("01_entities_nodes.csv"):
        etype = ENTITY_TYPE.get(r["entity_type"])
        if etype is None:
            continue
        role = r["role_in_network"]
        attrs = {
            "record_id": r["entity_id"],
            "sub_network": r["sub_network"],
            "role_in_network": role,
            "status": r["status"],
            "risk_flag": r["risk_flag"],
            "city": r["location_city"],
            "state": r["location_state"],
            "age": int(_num(r["age"])) if _num(r["age"]) else None,
            "notes": r["notes"],
        }
        # A mule SIM and a spoofed number are, in the record, numbers nobody verified. That is the
        # signal the burner detector and the "unverified identity" suspicion term both read.
        if etype == "PHONE":
            attrs["sim"] = r["entity_type"] == "SIM_CARD" or None
            unverified = "Mule SIM" in role or "Spoofed" in r["name"] or "Digital Arrest Call" in role
            attrs["kyc_status"] = "unverified" if unverified else "verified"
        if etype == "CRYPTO_WALLET":
            attrs["chain"] = "EVM-compatible (address quoted in the seizure memo)"
        put(r["entity_id"], etype, r["name"], attrs,
            aliases=[r["alias"]] if r["alias"] else [])

    # unresolved alias records: extra names the resolver would have to reconcile
    for r in _rows("06_aliases_unresolved.csv"):
        e = ent.get(r["entity_id"])
        if not e:
            continue
        names = {n for n in (r["name_variant_1"], r["name_variant_2"]) if n and n != e.label}
        e.aliases = sorted(set(e.aliases or []) | names)
        e.attributes = {**e.attributes, "alias_match_type": r["match_type"],
                        "alias_confidence": _num(r["confidence_score"]) or None,
                        "alias_resolution": r["resolution_status"]}

    # ---------------------------------------------------------------- 2. relationships
    for r in _rows("02_relationships_edges.csv"):
        raw = r["relationship_type"].upper()
        rel = REL_TYPE.get(raw)
        u, v = ent.get(r["source_id"]), ent.get(r["target_id"])
        if not rel or not u or not v:
            continue
        if raw in REVERSED:
            u, v = v, u
        when = _dt(r["detected_date"])
        acc.add(u.id, v.id, rel, weight=_num(r["weight"], 1.0) / 5.0, at=when, confidence=0.95,
                attrs={"evidence_source": r["evidence_source"], "recorded_as": raw,
                       "sub_network": r["sub_network"], "description": r["description"]},
                extractor="structured")
        touch(u, when)
        touch(v, when)

    # ---------------------------------------------------------------- 3. places
    city_pt: dict[str, tuple[float, float]] = {}
    for r in _rows("08_geo_locations.csv"):
        lat, lon = _num(r["latitude"]), _num(r["longitude"])
        if not lat and not lon:
            continue
        loc = put(r["location_id"], "LOCATION", r["location_name"], {
            "record_id": r["location_id"], "lat": lat, "lon": lon, "city": r["city"], "state": r["state"],
            "country": r["country"], "location_type": r["location_type"].replace("_", " ").lower(),
            "sub_network": r["sub_network"], "notes": r["notes"],
        })
        city_pt.setdefault(r["city"].lower(), (lat, lon))
        rel = PLACE_REL.get(r["location_type"], "SEEN_AT")
        for eid in r["linked_entity_ids"].split(";"):
            other = ent.get(eid.strip())
            if not other:
                continue
            # Only an actor can be placed somewhere. An account or a phone reaches a place through
            # whoever holds it, and drawing it directly would put a hexagon on the map.
            if other.type in ("PERSON", "ORGANIZATION"):
                acc.add(other.id, loc.id, rel, weight=1.0, confidence=0.9, extractor="structured",
                        attrs={"location_type": r["location_type"]})
            else:
                acc.add(loc.id, other.id, "LOCATED_AT", weight=0.4, confidence=0.9, extractor="structured")

    # ---------------------------------------------------------------- 4. documents, cases, arrests
    docs: dict[str, Document] = {}
    cases: dict[str, Entity] = {}   # sub_network -> CASE entity
    sealed = 0

    def document(key: str, source_type: str, title: str, content: str, meta: dict,
                 when: datetime | None) -> Document:
        nonlocal sealed
        d = Document(id=_id("doc", key), case_id=CASE_ID, source_type=source_type, title=title,
                     content=content, meta=meta, occurred_at=when)
        db.add(d)
        docs[key] = d
        if settings.evidence_ledger_enabled:
            attest_document(db, "demo-loader", d.id, title, content, source_type, commit=False)
            sealed += 1
        return d

    doc_rows = _rows("05_case_documents.csv")
    # the FIR / raid record that anchors each sub-network, so an arrest memo has a matter to name
    for r in doc_rows:
        kind = DOC_KIND.get(r["doc_type"])
        if not kind or kind[1] != "CASE":
            continue
        sn = r["sub_network"]
        if sn in cases:
            continue
        cases[sn] = put(f"case-{sn}", "CASE", r["title"], {
            "record_id": r["doc_id"], "sub_network": sn, "criminal": True,
            "police_station": r["police_station"], "jurisdiction": r["jurisdiction"],
            "issuing_authority": r["issuing_authority"], "classification": r["classification"],
        })

    for r in doc_rows:
        source_type, anchor_type, verb = DOC_KIND.get(r["doc_type"], ("REPORT", "REPORT", "MENTIONED_IN"))
        when = _dt(r["date_filed"]) or _dt(r["date_created"])
        body = " ".join(x for x in (r["brief_description"], r["notes"]) if x)
        content = (f"{r['title']}\n\n{body}\n\nIssuing authority: {r['issuing_authority']}. "
                   f"Police station: {r['police_station'] or 'not recorded'}. "
                   f"Jurisdiction: {r['jurisdiction'] or 'not recorded'}. "
                   f"Classification: {r['classification'] or 'not recorded'}.")
        doc = document(r["doc_id"], source_type, r["title"], content, {
            "doc_id": r["doc_id"], "doc_type": r["doc_type"], "issuing_authority": r["issuing_authority"],
            "police_station": r["police_station"], "jurisdiction": r["jurisdiction"],
            "classification": r["classification"], "sub_network": r["sub_network"],
            "source_file": "05_case_documents.csv",
        }, when)

        # the matter this record speaks to: its own case node, or the sub-network's
        anchor = cases.get(r["sub_network"]) if anchor_type == "CASE" else None
        if anchor_type == "REPORT":
            anchor = put(f"report-{r['doc_id']}", "REPORT", r["title"], {
                "record_id": r["doc_id"], "source_type": source_type, "sub_network": r["sub_network"],
                "issuing_authority": r["issuing_authority"], "document_id": doc.id,
            })
        elif anchor is None:
            anchor = cases.get(r["sub_network"])
        if anchor is not None:
            add_entity_evidence(db, doc.id, anchor.id, body[:300], 1.0, when, "structured")
            touch(anchor, when)

        subjects = [ent[e] for e in (x.strip() for x in r["linked_entity_ids"].split(";")) if e in ent]
        for s in subjects:
            add_entity_evidence(db, doc.id, s.id, body[:300], 1.0, when, "structured")
            touch(s, when)
            if anchor is None or s.type not in ("PERSON", "ORGANIZATION"):
                continue
            # An arrest memo or an FIR names an accused; a complainant is named as a complainant and
            # must never pick up suspicion for it.
            v = verb
            if v == "ACCUSED_IN" and (s.attributes.get("status") == "Complainant"
                                      or "Complainant" in (s.attributes.get("role_in_network") or "")):
                v = "COMPLAINANT_IN"
            acc.add(s.id, anchor.id, v, weight=1.0, at=when, confidence=1.0, doc_id=doc.id,
                    snippet=f"{r['doc_type'].replace('_', ' ').title()}: {r['title']}", extractor="structured")
        # co-accused in the same record
        people = [s for s in subjects if s.type == "PERSON" and s.attributes.get("status") == "Accused"]
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                acc.add(people[i].id, people[j].id, "CO_ACCUSED", weight=2.0, at=when, doc_id=doc.id,
                        snippet=f"Named together in {r['title']}", extractor="structured")
        if when and subjects:
            add_event(db, doc.id, "FIR" if source_type == "FIR" else "INTEL", when,
                      [s.id for s in subjects] + ([anchor.id] if anchor else []),
                      f"{r['doc_type'].replace('_', ' ').title()}: {r['title']}",
                      {"doc_type": r["doc_type"], "authority": r["issuing_authority"],
                       "sub_network": r["sub_network"]},
                      *(city_pt.get((r["jurisdiction"] or "").lower()) or (None, None)))

    # ---------------------------------------------------------------- 5. NCRP complaints
    ncrp = _rows("04_ncrp_complaints.csv")
    hub = ent.get("A001")
    ncrp_doc = document("NCRP-ROLLUP", "FIR",
                        f"NCRP complaint register — {len(ncrp)} complaints against one account",
                        "Complaints filed on the National Cyber Crime Reporting Portal that resolve to the "
                        "same beneficiary current account. Each was investigated as a separate matter in a "
                        "different city; the account is the only thing they share.",
                        {"source_file": "04_ncrp_complaints.csv", "complaints": len(ncrp)},
                        _dt(min((r["filing_date"] for r in ncrp), default="")))
    ncrp_doc.record_count = len(ncrp)
    for r in ncrp:
        acct = ent.get(r["linked_account"])
        when = _dt(r["filing_date"])
        amount = _num(r["amount_defrauded_inr"])
        if acct:
            add_entity_evidence(db, ncrp_doc.id, acct.id,
                                f"{r['complaint_id']}: ₹{amount:,.0f} — {r['modus_operandi']} "
                                f"({r['complainant_city']}, {r['complainant_state']})", 1.0, when, "structured")
            touch(acct, when)
        if when:
            add_event(db, ncrp_doc.id, "COMPLAINT", when, [acct.id] if acct else [],
                      f"{r['complaint_id']}: ₹{amount:,.0f} defrauded — {r['modus_operandi']}",
                      {"complaint_id": r["complaint_id"], "amount": amount,
                       "modus_operandi": r["modus_operandi"], "city": r["complainant_city"],
                       "police_station": r["police_station"], "status": r["investigation_status"]},
                      *(city_pt.get(r["complainant_city"].lower()) or (None, None)))
    if hub is not None:
        total = sum(_num(r["amount_defrauded_inr"]) for r in ncrp)
        hub.attributes = {**hub.attributes, "ncrp_complaints": len(ncrp),
                          "ncrp_total_inr": total,
                          "ncrp_cities": sorted({r["complainant_city"] for r in ncrp})}

    # ---------------------------------------------------------------- 6. money
    txns = _rows("03_financial_transactions.csv")
    txn_doc = document("TXN-LEDGER", "TRANSACTION",
                       f"Bank and blockchain statement extraction ({len(txns)} transfers)",
                       "Consolidated debit and credit legs recovered from bank statements, hawala "
                       "reconciliation sheets and on-chain analysis for every account on this sheet.",
                       {"source_file": "03_financial_transactions.csv", "rows": len(txns)}, None)
    txn_doc.record_count = len(txns)

    def account(code: str, name: str) -> Entity | None:
        """An account named only in the ledger: a victim, a complainant, an untraced counterparty."""
        if not code:
            return None
        if code in ent:
            return ent[code]
        label = f"{name} — {code}" if name and name.lower() not in ("self", "unknown") else code
        return put(code, "BANK_ACCOUNT", label, {
            "record_id": code, "external": True, "counterparty_name": name,
            "notes": "Counterparty account named in the statement only; not itself a subject of this case.",
        })

    holder_of: dict[str, str] = {}   # account CSV id -> holder name, for the detectors' prose
    for r in _rows("02_relationships_edges.csv"):
        if REL_TYPE.get(r["relationship_type"].upper()) == "OWNS_ACCOUNT":
            u = ent.get(r["source_id"])
            if u is not None:
                holder_of.setdefault(r["target_id"], u.label)

    first_txn = last_txn = None
    for r in txns:
        when = _dt(r["txn_date"], r["txn_time"])
        if when is None:
            continue
        src = account(r["from_account"], r["from_name"])
        dst = account(r["to_account"], r["to_name"])
        if src is None or dst is None:
            continue
        amount = _num(r["amount_inr"])
        first_txn = when if first_txn is None or when < first_txn else first_txn
        last_txn = when if last_txn is None or when > last_txn else last_txn
        acc.add(src.id, dst.id, "TRANSFERRED_TO", weight=1.0, at=when, amount=amount,
                attrs={"mode": r["txn_type"], "channel": r["channel"]}, extractor="structured")
        touch(src, when)
        touch(dst, when)
        # `details` here is a contract: graph/anomalies.py reads amount / from_holder / to_holder /
        # txn_id / remarks off it to build the structuring and layering findings.
        add_event(db, txn_doc.id, "TRANSFER", when, [src.id, dst.id],
                  f"₹{amount:,.0f} {r['txn_type']} — {r['from_name'] or src.label} → {r['to_name'] or dst.label}",
                  {"amount": amount, "mode": r["txn_type"], "channel": r["channel"],
                   "txn_id": r["txn_id"], "remarks": r["notes"], "flag": r["flag"],
                   "sub_network": r["sub_network"],
                   "from_holder": holder_of.get(r["from_account"]) or r["from_name"] or src.label,
                   "to_holder": holder_of.get(r["to_account"]) or r["to_name"] or dst.label})

    # ---------------------------------------------------------------- 7. timeline
    tl_rows = _rows("07_timeline_events.csv")
    tl_doc = document("TIMELINE", "INTEL", "Master timeline reconstruction",
                      "Chronology assembled by the investigating officer from FIRs, arrest memos, "
                      "surveillance logs, bank records and the forensic report.",
                      {"source_file": "07_timeline_events.csv", "events": len(tl_rows)},
                      _dt(min((r["event_date"] for r in tl_rows), default="")))
    tl_doc.record_count = len(tl_rows)
    for r in tl_rows:
        when = _dt(r["event_date"], r["event_time"])
        if when is None:
            continue
        ids = [ent[x].id for x in (y.strip() for y in r["linked_entity_ids"].split(";")) if x in ent]
        city = r["location_city"].lower()
        lat, lon = city_pt.get(city) or (None, None)
        add_event(db, tl_doc.id, r["event_type"], when, ids, r["description"],
                  {"severity": r["severity"].lower(), "sub_network": r["sub_network"],
                   "city": r["location_city"], "state": r["location_state"],
                   "source_document": r["source_document"],
                   "geo": {"precision": "city", "matched": r["location_city"]} if lat else {}},
                  lat, lon)
        for i in ids:
            seen.setdefault(i, []).append(when)

    # ---------------------------------------------------------------- 8. finish
    for e in ent.values():
        ts = sorted(seen.get(e.id, []))
        if ts:
            e.first_seen, e.last_seen = ts[0], ts[-1]
        e.mention_count = len(ts)
    db.flush()
    created, updated = acc.flush(db)
    db.commit()
    graph_cache.invalidate()

    # The three standing queries this investigation would actually be carrying: the one accused who
    # was never picked up, the account every complaint lands on, and the word that names the channel.
    # Arming them here also exercises the backfill, so the register opens with the answer to "has
    # this ever appeared" already in it rather than with an empty table and a form.
    watch_hits = 0
    for kind, value, reason, severity in WATCHES:
        try:
            _, found, _ = matcher.create(db, kind, value, reason=reason, severity=severity,
                                         created_by="demo-loader")
            watch_hits += found
        except matcher.WatchError as exc:
            print(f"  watch {value!r} not armed: {exc}")

    from ..api.deps import analysis_service
    print("Computing analytics…")
    snap = analysis_service.snapshot(db, force=True)

    stats = {
        "entities": len(ent),
        "relationships": created + updated,
        "documents": len(docs),
        "sealed": sealed,
        "events": db.query(TimelineEvent).count(),
        "alerts": db.query(Alert).count(),
        "watches": len(WATCHES),
        "watch_hits": watch_hits,
        "transfers": len(txns),
        "span": f"{first_txn:%d %b %Y} – {last_txn:%d %b %Y}" if first_txn and last_txn else "—",
        "nodes": snap.get("summary", {}).get("nodes", 0),
        "edges": snap.get("summary", {}).get("edges", 0),
        "communities": snap.get("summary", {}).get("communities", 0),
        "persons_of_interest": snap.get("summary", {}).get("persons_of_interest", 0),
    }
    return stats


def main() -> None:
    os.environ.setdefault("CNA_DEFAULT_CORPUS", "none")
    stats = load_demo_data()
    width = max(len(k) for k in stats)
    print(f"\n{SHEET_TITLE} loaded")
    for k, v in stats.items():
        print(f"  {k.replace('_', ' '):<{width + 2}} {v}")


if __name__ == "__main__":
    main()
