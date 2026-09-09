import csv
import os
import uuid
import uuid as uuid_pkg
from datetime import datetime
from dotenv import load_dotenv

# Load demo env variables to ensure we connect to the demo DB
load_dotenv(".env.demo")

from ..db import Case, Document, Entity, Evidence, Relationship, SessionLocal, TimelineEvent, init_db
from ..api.deps import analysis_service

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "demo-case-data")

def safe_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0

def _read_csv(filename):
    path = os.path.join(DEMO_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def load_demo_data():
    init_db()
    db = SessionLocal()
    
    print("Wiping existing demo data...")
    db.query(Evidence).delete()
    db.query(TimelineEvent).delete()
    db.query(Relationship).delete()
    db.query(Entity).delete()
    db.query(Document).delete()
    db.query(Case).delete()
    from ..db import AnalysisSnapshot
    db.query(AnalysisSnapshot).delete()
    db.flush()

    print("Loading demo case data...")

    # Create Case
    case_id = "DEMO-01"
    db.add(Case(id=case_id, name="Delhi Crime Branch — Cyber Cell", description="Operation CyberHawk 2.0 Demo"))

    # Load 08_geo_locations.csv into a lookup
    geo_data = {}
    for row in _read_csv("08_geo_locations.csv"):
        geo_data[row["location_id"]] = row

    # Load 01_entities_nodes.csv
    entity_map = {} # Store true DB uuid mapped from string ID
    for row in _read_csv("01_entities_nodes.csv"):
        e_id = str(uuid_pkg.uuid4())
        entity_map[row["entity_id"]] = e_id
        
        attrs = {
            "sub_network": row["sub_network"],
            "role_in_network": row["role_in_network"],
            "risk_flag": row["risk_flag"],
            "status": row["status"],
            "notes": row["notes"],
            "age": row["age"]
        }
        
        # Add geo data if linked to a location (assuming location_id isn't directly in entity, we'll map backwards from geo_data)
        for loc_id, loc in geo_data.items():
            if row["entity_id"] in loc["linked_entity_ids"].split(";"):
                attrs["lat"] = safe_float(loc["latitude"])
                attrs["lon"] = safe_float(loc["longitude"])
                attrs["location_name"] = loc["location_name"]
                attrs["city"] = loc["city"]
                break

        e = Entity(
            id=e_id,
            type=row["entity_type"],
            label=row["name"],
            canonical_key=row["name"].lower().replace(" ", "_"),
            aliases=[row["alias"]] if row["alias"] else [],
            attributes=attrs,
            risk_score=1.0 if row["risk_flag"] == "HIGH" else (0.5 if row["risk_flag"] == "MED" else 0.1)
        )
        db.add(e)
        
    db.flush()
        
    # Load 06_aliases_unresolved.csv
    for row in _read_csv("06_aliases_unresolved.csv"):
        if row["entity_id"] and row["entity_id"] in entity_map:
            db_id = entity_map[row["entity_id"]]
            entity = db.get(Entity, db_id)
            if entity:
                aliases = set(entity.aliases) if entity.aliases else set()
                if row["name_variant_1"]: aliases.add(row["name_variant_1"])
                if row["name_variant_2"]: aliases.add(row["name_variant_2"])
                entity.aliases = list(aliases)

    # Load 02_relationships_edges.csv
    REL_MAP = {
        "OPERATED_BY": "USES_PHONE",
        "CONTROLS": "OWNS_ACCOUNT",
        "ASSOCIATED_WITH": "ASSOCIATE_OF",
        "LINKED_TO": "ASSOCIATE_OF",
        "RECRUITED": "REPORTS_TO",
        "PROCURED_FOR": "ASSOCIATE_OF",
        "CONVERTED_VIA": "TRANSFERRED_TO",
        "LAUNDERED_THROUGH": "TRANSFERRED_TO",
    }
    for row in _read_csv("02_relationships_edges.csv"):
        u = entity_map.get(row["source_id"])
        v = entity_map.get(row["target_id"])
        if not u or not v:
            continue
        rt = row["relationship_type"].upper()
        rt = REL_MAP.get(rt, rt)
        
        db.add(Relationship(
            id=str(uuid_pkg.uuid4()),
            source_id=u,
            target_id=v,
            rel_type=rt,
            weight=float(row["weight"]) if row["weight"] else 1.0,
            attributes={"sub_network": row["sub_network"], "detected_date": row["detected_date"], "description": row["description"]}
        ))
        
    # Load 05_case_documents.csv
    doc_map = {}
    for row in _read_csv("05_case_documents.csv"):
        d_id = str(uuid_pkg.uuid4())
        doc_map[row["doc_id"]] = d_id
        doc = Document(
            id=d_id,
            case_id=case_id,
            source_type=row["doc_type"],
            title=row["title"],
            content=row["brief_description"] + " " + row["notes"],
            meta={
                "source_file": "05_case_documents.csv",
                "issuing_authority": row.get("issuing_authority", ""),
                "police_station": row.get("police_station", ""),
                "jurisdiction": row.get("jurisdiction", ""),
                "classification": row.get("classification", "")
            },
            occurred_at=datetime.strptime(row["date_filed"], "%Y-%m-%d") if row["date_filed"] else None,
        )
        db.add(doc)
        
        # Add Evidence links
        for e_id_raw in row["linked_entity_ids"].split(";"):
            if e_id_raw in entity_map:
                ev = Evidence(
                    document_id=d_id,
                    entity_id=entity_map[e_id_raw],
                    snippet=row["brief_description"],
                    extractor="demo-loader"
                )
                db.add(ev)

    # Load 04_ncrp_complaints.csv
    ncrp_doc_id = str(uuid_pkg.uuid4())
    db.add(Document(id=ncrp_doc_id, case_id=case_id, source_type="FIR", title="NCRP Complaints Rollup", content="Multiple complaints mapped to A001", record_count=32, meta={"source_file": "04_ncrp_complaints.csv"}))
    for row in _read_csv("04_ncrp_complaints.csv"):
        if row["linked_account"] in entity_map:
            db.add(Evidence(document_id=ncrp_doc_id, entity_id=entity_map[row["linked_account"]], snippet=f"Complaint {row['complaint_id']} for {row['amount_defrauded_inr']}", extractor="demo-loader"))

    # Load 03_financial_transactions.csv
    txn_doc_id = str(uuid_pkg.uuid4())
    db.add(Document(id=txn_doc_id, case_id=case_id, source_type="TRANSACTION", title="Financial Ledger Extraction", content="All demo case financial transfers", meta={"source_file": "03_financial_transactions.csv"}))
    
    for row in _read_csv("03_financial_transactions.csv"):
        dt = f"{row['txn_date']} {row['txn_time']}"
        try:
            occurred = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        except:
            occurred = datetime.now()
            
        e_ids = []
        if row["from_account"] in entity_map: e_ids.append(entity_map[row["from_account"]])
        if row["to_account"] in entity_map: e_ids.append(entity_map[row["to_account"]])
        
        db.add(TimelineEvent(
            document_id=txn_doc_id,
            kind="TRANSFER",
            occurred_at=occurred,
            entity_ids=e_ids,
            summary=f"Transfer of {row['amount_inr']} via {row['channel']}",
            details={"type": row["txn_type"], "flag": row["flag"], "notes": row["notes"]}
        ))

    # Load 07_timeline_events.csv
    tl_doc_id = str(uuid_pkg.uuid4())
    db.add(Document(id=tl_doc_id, case_id=case_id, source_type="INTEL", title="Master Timeline Reconstruction", content="Chronological events from Investigation", meta={"source_file": "07_timeline_events.csv"}))
    for row in _read_csv("07_timeline_events.csv"):
        dt = f"{row['event_date']} {row['event_time']}"
        try:
            occurred = datetime.strptime(dt, "%Y-%m-%d %H:%M")
        except:
            occurred = datetime.now()
            
        e_ids = [entity_map[x] for x in row["linked_entity_ids"].split(";") if x in entity_map]
        
        db.add(TimelineEvent(
            document_id=tl_doc_id,
            kind=row["event_type"],
            occurred_at=occurred,
            entity_ids=e_ids,
            summary=row["description"],
            details={"severity": row["severity"], "sub_network": row["sub_network"]}
        ))
        
    db.commit()
    print("Pre-computing analytics...")
    analysis_service.snapshot(db)
    print("Demo load complete!")

if __name__ == "__main__":
    load_demo_data()
