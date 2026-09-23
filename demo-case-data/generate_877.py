import csv
import random
import uuid
from datetime import datetime, timedelta
import os

FIRST_NAMES = ["Amit", "Rahul", "Sandeep", "Rajesh", "Vikram", "Suresh", "Ramesh", "Mahesh", "Anil", "Sunil", "Pooja", "Neha", "Kavita", "Anita", "Sunita", "Raj", "Vijay", "Sanjay", "Ravi", "Deepak", "Ajay", "Mohammad", "Abdul", "Irfan", "Tariq", "Imran", "Arjun", "Karan", "Rohit", "Mohit", "Sachin"]
LAST_NAMES = ["Kumar", "Singh", "Sharma", "Verma", "Gupta", "Yadav", "Patel", "Das", "Mishra", "Pandey", "Chauhan", "Thakur", "Reddy", "Rao", "Jain", "Shah", "Khan", "Ansari", "Shaikh", "Qureshi", "Bhat"]
CITIES = [("Delhi", "Delhi"), ("Mumbai", "Maharashtra"), ("Bengaluru", "Karnataka"), ("Jaipur", "Rajasthan"), ("Patna", "Bihar"), ("Noida", "UP"), ("Gurgaon", "Haryana")]

def random_date(start, end):
    return start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))

def generate_network():
    nodes = []
    edges = []
    txns = []

    # 877 People
    # 2 Masterminds (P1001-P1002)
    # 10 Middlemen (P1003-P1012)
    # 88 Operators (P1013-P1100)
    # 777 Mules (P1101-P1877)
    
    start_time = datetime(2025, 6, 1)
    end_time = datetime(2025, 11, 25)

    people = []
    accounts = []

    for i in range(1001, 1878):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        city, state = random.choice(CITIES)
        
        if i <= 1002:
            role = "Syndicate Leader"
            status = "At Large"
            risk = "HIGH"
        elif i <= 1012:
            role = "Middleman"
            status = "Accused"
            risk = "HIGH"
        elif i <= 1100:
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
            "age": str(random.randint(18, 50)),
            "role_in_network": role,
            "sub_network": "SN-D",
            "location_city": city,
            "location_state": state,
            "status": status,
            "risk_flag": risk,
            "notes": ""
        })
        people.append(f"P{i}")

        # Accounts
        if i <= 1012 or i > 1100:
            acc_id = f"A{i}"
            acc_name = f"{name} Account - [XXXX{random.randint(1000, 9999)}]"
            nodes.append({
                "entity_id": acc_id,
                "entity_type": "BANK_ACCOUNT",
                "name": acc_name,
                "alias": "",
                "age": "",
                "role_in_network": role + " Account",
                "sub_network": "SN-D",
                "location_city": "",
                "location_state": "",
                "status": "Frozen" if status == "Accused" else "Active",
                "risk_flag": "HIGH",
                "notes": "Part of 1000 Crore Bust"
            })
            accounts.append(acc_id)
            
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

    # Build hierarchy edges
    # Middlemen to Masterminds
    for i in range(1003, 1013):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(1001, 1002)}",
            "relationship_type": "MANAGED_BY",
            "confidence_score": "0.9",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })
    # Mules to Middlemen
    for i in range(1101, 1878):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(1003, 1012)}",
            "relationship_type": "RECRUITED_BY",
            "confidence_score": "0.85",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })
    # Operators to Middlemen
    for i in range(1013, 1101):
        edges.append({
            "source_id": f"P{i}",
            "target_id": f"P{random.randint(1003, 1012)}",
            "relationship_type": "WORKED_WITH",
            "confidence_score": "0.8",
            "valid_from": "",
            "valid_to": "",
            "source_document": "Interrogation",
            "notes": ""
        })

    # Financial Transactions
    # 777 Mules. Goal: 10,000,000,000 total.
    # ~1.28 crore per mule
    total_txns = 0
    txn_id_counter = 10000

    for i in range(1101, 1878):
        mule_acc = f"A{i}"
        mule_total = random.uniform(1_000_0000, 1_500_0000) # 1 to 1.5 crore
        
        # 3 to 6 incoming victim txns
        num_incoming = random.randint(3, 6)
        amt_per_txn = mule_total / num_incoming
        
        for _ in range(num_incoming):
            t_time = random_date(start_time, end_time)
            txns.append({
                "transaction_id": f"TXN-CYH-{txn_id_counter}",
                "from_account_id": "External_Victim", # Will create a dummy node below if needed, or leave unlinked to internal node
                "to_account_id": mule_acc,
                "amount": f"{amt_per_txn:.2f}",
                "currency": "INR",
                "timestamp": t_time.isoformat(),
                "transaction_type": "IMPS/NEFT",
                "status": "COMPLETED",
                "source_document": "Bank Statement",
                "notes": "Victim deposit"
            })
            txn_id_counter += 1

        # Funnel to middleman
        middleman_acc = f"A{random.randint(1003, 1012)}"
        t_time = end_time - timedelta(days=random.randint(1, 30))
        txns.append({
            "transaction_id": f"TXN-CYH-{txn_id_counter}",
            "from_account_id": mule_acc,
            "to_account_id": middleman_acc,
            "amount": f"{mule_total * 0.95:.2f}", # keep 5% commission
            "currency": "INR",
            "timestamp": t_time.isoformat(),
            "transaction_type": "RTGS",
            "status": "COMPLETED",
            "source_document": "Bank Statement",
            "notes": "Upward funneling"
        })
        txn_id_counter += 1

    # Funnel Middleman to Mastermind
    for mid in range(1003, 1013):
        mid_acc = f"A{mid}"
        master_acc = f"A{random.randint(1001, 1002)}"
        t_time = end_time - timedelta(days=random.randint(0, 5))
        txns.append({
            "transaction_id": f"TXN-CYH-{txn_id_counter}",
            "from_account_id": mid_acc,
            "to_account_id": master_acc,
            "amount": f"{77 * 1_200_0000 * 0.9:.2f}", # rough aggregate
            "currency": "INR",
            "timestamp": t_time.isoformat(),
            "transaction_type": "RTGS",
            "status": "COMPLETED",
            "source_document": "Bank Statement",
            "notes": "Mastermind consolidation"
        })
        txn_id_counter += 1

    # Write to CSVs
    data_dir = r"c:\Users\NIRJHAR BARMA\Desktop\batcave\demo-case-data"
    
    # 01_entities_nodes.csv
    nodes_path = os.path.join(data_dir, "01_entities_nodes.csv")
    with open(nodes_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=nodes[0].keys())
        for n in nodes:
            writer.writerow(n)
            
    # 02_relationships_edges.csv
    edges_path = os.path.join(data_dir, "02_relationships_edges.csv")
    with open(edges_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=edges[0].keys())
        for e in edges:
            writer.writerow(e)
            
    # 03_financial_transactions.csv
    txns_path = os.path.join(data_dir, "03_financial_transactions.csv")
    with open(txns_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=txns[0].keys())
        for t in txns:
            writer.writerow(t)
            
    print(f"Generated {len(nodes)} nodes, {len(edges)} edges, {len(txns)} transactions.")

if __name__ == "__main__":
    generate_network()
