import csv
import random
import uuid
from datetime import datetime, timedelta
import os

FIRST_NAMES = ["Rakesh", "Saurabh", "Manish", "Gaurav", "Nitin", "Pramod", "Kishore", "Tarun", "Prakash", "Ganesh", "Ashok", "Sushil", "Sneha", "Jyoti", "Priyanka", "Anjali", "Swati", "Nisha", "Manoj", "Dinesh", "Naresh", "Suraj", "Vikas", "Vishal", "Yash", "Zahir", "Faizan", "Salman", "Aman", "Rishabh", "Varun"]
LAST_NAMES = ["Tiwari", "Shukla", "Pandey", "Dixit", "Chopra", "Malhotra", "Mehta", "Desai", "Rathore", "Rajput", "Shetty", "Nair", "Iyer", "Pillai", "Bose", "Ghosh", "Mukherjee", "Banerjee", "Chatterjee", "Bhattacharya", "Sengupta"]
CITIES = [("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"), ("Pune", "Maharashtra"), ("Nagpur", "Maharashtra"), ("Indore", "Madhya Pradesh"), ("Bhopal", "Madhya Pradesh"), ("Lucknow", "UP"), ("Kanpur", "UP"), ("Varanasi", "UP"), ("Kolkata", "West Bengal"), ("Hyderabad", "Telangana"), ("Chennai", "Tamil Nadu"), ("Kochi", "Kerala")]

def random_date(start, end):
    return start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))

def generate_network():
    nodes = []
    edges = []
    txns = []

    # NCIC 2.0: 2000 People (P2001-P4000)
    # 5 Masterminds, 40 Middlemen, 200 Operators, 1755 Mules
    
    start_time = datetime(2025, 8, 1)
    end_time = datetime(2025, 12, 15)

    for i in range(2001, 4001):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        city, state = random.choice(CITIES)
        
        if i <= 2005:
            role = "Syndicate Leader"
            status = "At Large"
            risk = "HIGH"
        elif i <= 2045:
            role = "Middleman"
            status = "Accused"
            risk = "HIGH"
        elif i <= 2245:
            role = "Call Center Operator"
            status = "Accused"
            risk = "HIGH"
        else:
            role = "Mule Account Holder"
            status = "Accused"
            risk = "MED"

        nodes.append({
            "entity_id": f"P{i}",
            "entity_type": "PERSON",
            "name": name,
            "alias": "",
            "age": str(random.randint(18, 55)),
            "role_in_network": role,
            "sub_network": "SN-E", # NCIC 2.0
            "location_city": city,
            "location_state": state,
            "status": status,
            "risk_flag": risk,
            "notes": "NCIC Investigation"
        })

        if i <= 2045 or i > 2245:
            acc_id = f"A{i}"
            acc_name = f"{name} Account - [XXXX{random.randint(1000, 9999)}]"
            nodes.append({
                "entity_id": acc_id,
                "entity_type": "BANK_ACCOUNT",
                "name": acc_name,
                "alias": "",
                "age": "",
                "role_in_network": role + " Account",
                "sub_network": "SN-E",
                "location_city": "",
                "location_state": "",
                "status": "Frozen",
                "risk_flag": "HIGH",
                "notes": "NCIC Arrest"
            })
            
            edges.append({
                "source_id": f"P{i}",
                "target_id": acc_id,
                "relationship_type": "OWNS",
                "confidence_score": "1.0",
                "valid_from": "",
                "valid_to": "",
                "source_document": "NCRP DB",
                "notes": ""
            })

    # Middlemen to Masterminds
    for i in range(2006, 2046):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(2001, 2005)}",
            "relationship_type": "MANAGED_BY",
            "confidence_score": "0.9",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })
    # Mules to Middlemen
    for i in range(2246, 4001):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(2006, 2045)}",
            "relationship_type": "RECRUITED_BY",
            "confidence_score": "0.85",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })
    # Operators to Middlemen
    for i in range(2046, 2246):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(2006, 2045)}",
            "relationship_type": "WORKED_WITH",
            "confidence_score": "0.8",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })

    # Transactions (Less dense to save time: 2 per mule)
    txn_id_counter = 20000
    for i in range(2246, 4001):
        mule_acc = f"A{i}"
        mule_total = random.uniform(5_000_000, 1_000_0000)
        
        for _ in range(2):
            t_time = random_date(start_time, end_time)
            txns.append({
                "transaction_id": f"TXN-CYH-{txn_id_counter}",
                "from_account_id": "External_Victim",
                "to_account_id": mule_acc,
                "amount": f"{mule_total / 2:.2f}",
                "currency": "INR",
                "timestamp": t_time.isoformat(),
                "transaction_type": "IMPS/NEFT",
                "status": "COMPLETED",
                "source_document": "Bank Statement",
                "notes": "Victim deposit"
            })
            txn_id_counter += 1

        middleman_acc = f"A{random.randint(2006, 2045)}"
        t_time = end_time - timedelta(days=random.randint(1, 15))
        txns.append({
            "transaction_id": f"TXN-CYH-{txn_id_counter}",
            "from_account_id": mule_acc,
            "to_account_id": middleman_acc,
            "amount": f"{mule_total * 0.95:.2f}",
            "currency": "INR",
            "timestamp": t_time.isoformat(),
            "transaction_type": "RTGS",
            "status": "COMPLETED",
            "source_document": "Bank Statement",
            "notes": "Upward funneling"
        })
        txn_id_counter += 1

    for mid in range(2006, 2046):
        mid_acc = f"A{mid}"
        master_acc = f"A{random.randint(2001, 2005)}"
        t_time = end_time - timedelta(days=random.randint(0, 3))
        txns.append({
            "transaction_id": f"TXN-CYH-{txn_id_counter}",
            "from_account_id": mid_acc,
            "to_account_id": master_acc,
            "amount": f"{44 * 7_500_000 * 0.9:.2f}",
            "currency": "INR",
            "timestamp": t_time.isoformat(),
            "transaction_type": "RTGS",
            "status": "COMPLETED",
            "source_document": "Bank Statement",
            "notes": "Mastermind consolidation"
        })
        txn_id_counter += 1

    # Geo Locations
    coords = {
        "Ahmedabad": ("23.0225", "72.5714"),
        "Surat": ("21.1702", "72.8311"),
        "Pune": ("18.5204", "73.8567"),
        "Nagpur": ("21.1458", "79.0882"),
        "Indore": ("22.7196", "75.8577"),
        "Bhopal": ("23.2599", "77.4126"),
        "Lucknow": ("26.8467", "80.9462"),
        "Kanpur": ("26.4499", "80.3319"),
        "Varanasi": ("25.3176", "82.9739"),
        "Kolkata": ("22.5726", "88.3639"),
        "Hyderabad": ("17.3850", "78.4867"),
        "Chennai": ("13.0827", "80.2707"),
        "Kochi": ("9.9312", "76.2673")
    }

    locs = []
    loc_id_counter = 200
    people_by_city = {}
    for n in nodes:
        if n["entity_type"] == "PERSON":
            c = n["location_city"]
            if c not in people_by_city: people_by_city[c] = []
            people_by_city[c].append(n["entity_id"])

    for city, ps in people_by_city.items():
        if city not in coords: continue
        lat, lon = coords[city]
        chunk_size = 100
        for i in range(0, len(ps), chunk_size):
            chunk = ps[i:i+chunk_size]
            locs.append({
                "location_id": f"LOC{loc_id_counter}",
                "location_name": f"{city} NCIC 2.0 Base {i//chunk_size + 1}",
                "city": city,
                "state": [s for c, s in CITIES if c == city][0],
                "country": "India",
                "latitude": str(float(lat) + random.uniform(-0.05, 0.05)),
                "longitude": str(float(lon) + random.uniform(-0.05, 0.05)),
                "location_type": "OPERATIONAL_BASE",
                "linked_entity_ids": ";".join(chunk),
                "sub_network": "SN-E",
                "event_count": str(len(chunk) * 2),
                "notes": "NCIC 2.0 Extended Network"
            })
            loc_id_counter += 1

    data_dir = r"c:\Users\NIRJHAR BARMA\Desktop\batcave\demo-case-data"
    
    with open(os.path.join(data_dir, "01_entities_nodes.csv"), "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=nodes[0].keys())
        writer.writerows(nodes)
            
    with open(os.path.join(data_dir, "02_relationships_edges.csv"), "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=edges[0].keys())
        writer.writerows(edges)
            
    with open(os.path.join(data_dir, "03_financial_transactions.csv"), "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=txns[0].keys())
        writer.writerows(txns)

    with open(os.path.join(data_dir, "08_geo_locations.csv"), "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["location_id","location_name","city","state","country","latitude","longitude","location_type","linked_entity_ids","sub_network","event_count","notes"])
        writer.writerows(locs)
            
    print(f"Generated 2000 new people + their accounts ({len(nodes)} nodes), {len(edges)} edges, {len(txns)} transactions, {len(locs)} geo-locations.")

if __name__ == "__main__":
    generate_network()
