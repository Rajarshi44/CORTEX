"""
Synthetic multi-source crime intelligence dataset generator.

Produces a realistic, internally-consistent corpus for "Operation Saltwater" - a fictional
narcotics-trafficking + hawala network operating around Mumbai / JNPT - buried in a large
amount of unrelated noise (ordinary citizens, unrelated FIRs, everyday transactions).

Outputs (data/samples/):
  firs.json             - FIR narratives (unstructured text)
  cdr.csv               - Call Detail Records (structured)
  kyc.csv               - Telecom subscriber KYC (phone -> holder)
  transactions.csv      - Bank / UPI transfers
  surveillance.json     - Field surveillance reports (semi-structured)
  social_media.json     - Social media intelligence
  intel_reports.json    - Intelligence agency notes (unstructured)
  ground_truth.json     - The hidden network (for evaluation only; never ingested)

All personal data is fictional. Deterministic via --seed.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "samples"

# ---------------------------------------------------------------------------------------
# Gazetteer (Mumbai Metropolitan Region + a few outstation nodes) with coordinates
# ---------------------------------------------------------------------------------------
LOCATIONS: dict[str, tuple[float, float]] = {
    "Dongri": (18.9583, 72.8347),
    "Nagpada": (18.9695, 72.8283),
    "Kalbadevi": (18.9484, 72.8288),
    "Colaba": (18.9067, 72.8147),
    "Bandra West": (19.0596, 72.8295),
    "Kurla": (19.0726, 72.8845),
    "Dharavi": (19.0423, 72.8530),
    "Andheri East": (19.1136, 72.8697),
    "Malad": (19.1874, 72.8484),
    "Borivali": (19.2307, 72.8567),
    "Mira Road": (19.2813, 72.8712),
    "Bhiwandi": (19.2967, 73.0631),
    "Thane": (19.2183, 72.9781),
    "Kalyan": (19.2403, 73.1305),
    "Vashi": (19.0771, 72.9986),
    "Panvel": (18.9894, 73.1175),
    "Nhava Sheva": (18.9500, 72.9500),
    "Uran": (18.8780, 72.9310),
    "Alibaug": (18.6414, 72.8722),
    "Kondhwa": (18.4634, 73.8930),
    "Surat": (21.1702, 72.8311),
    "Vasco da Gama": (15.3860, 73.8154),
    "Ghatkopar": (19.0863, 72.9081),
    "Chembur": (19.0522, 72.9005),
    "Powai": (19.1176, 72.9060),
    "Worli": (19.0176, 72.8156),
    "Byculla": (18.9793, 72.8324),
    "Sewri": (19.0000, 72.8600),
    "Mumbra": (19.1868, 73.0248),
    "Ulhasnagar": (19.2215, 73.1645),
}

POLICE_STATIONS = [
    "Dongri PS", "Nagpada PS", "Colaba PS", "Bandra PS", "Kurla PS", "Dharavi PS", "Andheri PS",
    "Malad PS", "Bhiwandi City PS", "Thane Nagar PS", "Vashi PS", "Panvel City PS", "Uran PS",
    "Nhava Sheva PS", "Mira Road PS", "Ghatkopar PS", "Chembur PS", "Powai PS", "Byculla PS", "Mumbra PS",
]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Sai", "Arjun", "Rohan", "Karan", "Nikhil", "Rahul", "Amit", "Vijay",
    "Sanjay", "Manoj", "Prakash", "Ganesh", "Santosh", "Dinesh", "Rajesh", "Sachin", "Mahesh", "Suresh",
    "Ramesh", "Naresh", "Umesh", "Pravin", "Nitin", "Sunita", "Anjali", "Pooja", "Neha", "Kavita",
    "Sneha", "Priyanka", "Deepika", "Shweta", "Rekha", "Meena", "Asha", "Usha", "Lata", "Farhan",
    "Irfan", "Zubair", "Nadeem", "Sameer", "Tariq", "Junaid", "Shabana", "Nazia", "Ayesha", "Fatima",
    "Joseph", "Michael", "Peter", "Francis", "Savio", "Melwyn", "Gurpreet", "Harpreet", "Simran",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patil", "Jadhav", "More", "Kadam", "Pawar", "Shinde", "Deshmukh", "Kulkarni",
    "Joshi", "Bhosale", "Gaikwad", "Chavan", "Salunkhe", "Kamble", "Sawant", "Rane", "Naik", "Mhatre",
    "Khan", "Shaikh", "Ansari", "Qureshi", "Siddiqui", "Sayed", "Pathan", "Memon", "Fernandes", "D'Souza",
    "Pereira", "Gomes", "Rodrigues", "Singh", "Kaur", "Gupta", "Agarwal", "Jain", "Mehta", "Shah",
    "Yadav", "Mishra", "Tiwari", "Dubey", "Pandey", "Reddy", "Nair", "Menon", "Iyer", "Pillai",
]
ORGS_NOISE = [
    "Om Sai Traders", "Shree Ganesh Enterprises", "Star Mobile Shop", "Royal Bakery", "Sunrise Hotel",
    "Metro Cabs", "Apex Builders", "Bharat Electricals", "New India Medical Stores", "Krishna Dairy",
]

BANKS = [("HDFC", "HDFC0000{:03d}"), ("SBI", "SBIN000{:04d}"), ("ICICI", "ICIC000{:04d}"),
         ("AXIS", "UTIB000{:04d}"), ("KOTAK", "KKBK000{:04d}"), ("BOB", "BARB0{:06d}")]


# ---------------------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------------------
@dataclass
class Person:
    name: str
    alias: str | None
    role: str  # ground-truth role
    home: str
    phones: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    vehicles: list[str] = field(default_factory=list)
    handle: str | None = None
    org: str | None = None
    in_network: bool = False
    cluster: str | None = None


class Generator:
    def __init__(self, seed: int = 26189):
        self.rng = random.Random(seed)
        self.start = datetime(2026, 1, 1)
        self.end = datetime(2026, 4, 30)
        self.people: list[Person] = []
        self.phone_owner: dict[str, Person] = {}
        self.account_owner: dict[str, Person | str] = {}
        self.account_meta: dict[str, dict] = {}
        self.burners: list[dict] = []
        self.firs: list[dict] = []
        self.cdr: list[dict] = []
        self.kyc: list[dict] = []
        self.tx: list[dict] = []
        self.surv: list[dict] = []
        self.social: list[dict] = []
        self.intel: list[dict] = []

    # ---------------------------------------------------------------- helpers
    def phone(self) -> str:
        while True:
            p = self.rng.choice("6789") + "".join(self.rng.choice("0123456789") for _ in range(9))
            if p not in self.phone_owner:
                return p

    def plate(self, rto: str | None = None) -> str:
        rto = rto or self.rng.choice(["MH 01", "MH 02", "MH 03", "MH 04", "MH 43", "MH 46", "MH 47", "MH 12", "GJ 05"])
        letters = "".join(self.rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
        return f"{rto} {letters} {self.rng.randint(1000, 9999)}"

    def account(self, holder: Person | str, bank: str | None = None) -> str:
        bank_name, ifsc_fmt = self.rng.choice(BANKS) if bank is None else next(b for b in BANKS if b[0] == bank)
        acc = "".join(self.rng.choice("0123456789") for _ in range(self.rng.choice([11, 12, 14])))
        self.account_owner[acc] = holder
        self.account_meta[acc] = {"bank": bank_name, "ifsc": ifsc_fmt.format(self.rng.randint(1, 999)),
                                  "holder": holder.name if isinstance(holder, Person) else holder}
        if isinstance(holder, Person):
            holder.accounts.append(acc)
        return acc

    def rand_dt(self, a: datetime | None = None, b: datetime | None = None, night_bias: float = 0.0) -> datetime:
        a = a or self.start
        b = b or self.end
        span = int((b - a).total_seconds())
        t = a + timedelta(seconds=self.rng.randint(0, max(span, 1)))
        if self.rng.random() < night_bias:
            t = t.replace(hour=self.rng.choice([0, 1, 2, 3, 23]), minute=self.rng.randint(0, 59))
        else:
            t = t.replace(hour=self.rng.choice(list(range(7, 23))), minute=self.rng.randint(0, 59))
        return t

    def add_person(self, name: str, alias: str | None, role: str, home: str, n_phones=1, n_acc=1, n_veh=0,
                   handle=None, org=None, in_network=False, cluster=None) -> Person:
        p = Person(name, alias, role, home, handle=handle, org=org, in_network=in_network, cluster=cluster)
        for _ in range(n_phones):
            ph = self.phone()
            p.phones.append(ph)
            self.phone_owner[ph] = p
            self.kyc.append({"msisdn": ph, "subscriber_name": name, "address": f"{home}, Mumbai",
                             "id_type": self.rng.choice(["Aadhaar", "Voter ID", "Passport", "DL"]),
                             "activation_date": (self.start - timedelta(days=self.rng.randint(120, 2000))).date().isoformat(),
                             "operator": self.rng.choice(["Jio", "Airtel", "Vi", "BSNL"])})
        for _ in range(n_acc):
            self.account(p)
        for _ in range(n_veh):
            p.vehicles.append(self.plate())
        self.people.append(p)
        return p

    def random_name(self) -> str:
        used = {p.name for p in self.people}
        while True:
            n = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            if n not in used:
                return n

    # ---------------------------------------------------------------- actors
    def build_actors(self):
        # --- Core narcotics network (cluster A)
        self.kingpin = self.add_person("Rafiq Sheikh", "Bhai", "kingpin", "Dongri", n_phones=2, n_acc=1, n_veh=1,
                                       in_network=True, cluster="A")
        self.kingpin.vehicles = ["MH 02 CX 4521"]
        self.salim = self.add_person("Salim Qureshi", "Salim Bhai", "lieutenant", "Nagpada", n_phones=2, n_acc=1,
                                     n_veh=1, in_network=True, cluster="A")
        self.vikram = self.add_person("Vikram Naik", None, "logistics", "Bhiwandi", n_phones=1, n_acc=2, n_veh=2,
                                      org="Naik Cargo Movers Pvt Ltd", in_network=True, cluster="A")
        self.vikram.vehicles = ["MH 04 JK 2211", "MH 04 HB 7830"]
        self.anthony = self.add_person("Anthony D'Souza", "Tony", "port_insider", "Uran", n_phones=1, n_acc=1,
                                       org="Seagull Clearing Agency", in_network=True, cluster="A")
        self.imran = self.add_person("Imran Ansari", "Chikna", "distributor", "Kurla", n_phones=1, n_acc=1, n_veh=1,
                                     handle="@imran_kurla", in_network=True, cluster="A")
        self.sunil = self.add_person("Sunil Pawar", None, "distributor", "Dharavi", n_phones=1, n_acc=1,
                                     in_network=True, cluster="A")
        self.deepak = self.add_person("Deepak Yadav", "DK", "distributor", "Mira Road", n_phones=1, n_acc=1,
                                      handle="@dk_miraroad", in_network=True, cluster="A")
        self.mules = [
            self.add_person("Ravi Kumar", None, "mule", "Ghatkopar", in_network=True, cluster="A"),
            self.add_person("Anita Shinde", None, "mule", "Chembur", in_network=True, cluster="A"),
            self.add_person("Mohd Farhan", None, "mule", "Mumbra", in_network=True, cluster="A"),
            self.add_person("Suresh Gaikwad", None, "mule", "Kalyan", in_network=True, cluster="A"),
        ]
        # --- Financial bridge (broker between clusters)
        self.jain = self.add_person("Mahesh Jain", "Seth", "hawala_operator", "Kalbadevi", n_phones=2, n_acc=2,
                                    org="Jain Bullion & Traders", in_network=True, cluster="BRIDGE")
        self.priya = self.add_person("Priya Deshmukh", None, "accountant", "Andheri East", n_phones=1, n_acc=1,
                                     org="Skyline Infra Ventures Pvt Ltd", in_network=True, cluster="BRIDGE")
        # --- Real-estate laundering ring (cluster B)
        self.rakesh = self.add_person("Rakesh Mehta", None, "builder", "Bandra West", n_phones=1, n_acc=2, n_veh=1,
                                      org="Mehta Realty LLP", in_network=True, cluster="B")
        self.kiran = self.add_person("Kiran Patel", None, "investor", "Surat", n_phones=1, n_acc=1,
                                     in_network=True, cluster="B")
        self.nilesh = self.add_person("Nilesh Shah", None, "agent", "Borivali", n_phones=1, n_acc=1,
                                      in_network=True, cluster="B")
        # Foreign handler (phone only, appears in CDR as international number)
        self.abu_phone = "971501234567"
        # Shell company accounts
        self.skyline_acc = self.account("Skyline Infra Ventures Pvt Ltd", "AXIS")
        self.naik_cargo_acc = self.account("Naik Cargo Movers Pvt Ltd", "ICICI")
        self.jain_bullion_acc = self.account("Jain Bullion & Traders", "HDFC")
        self.mehta_realty_acc = self.account("Mehta Realty LLP", "KOTAK")

        # --- Noise citizens
        for _ in range(70):
            self.add_person(self.random_name(), None, "citizen", self.rng.choice(list(LOCATIONS)),
                            n_phones=1, n_acc=1, n_veh=self.rng.choice([0, 0, 1]))

        # --- Burner phones (no valid KYC), used by Salim around shipments
        for i, (a, b) in enumerate([(datetime(2026, 1, 8), datetime(2026, 1, 13)),
                                    (datetime(2026, 3, 29), datetime(2026, 4, 3))]):
            ph = self.phone()
            self.burners.append({"msisdn": ph, "active_from": a, "active_to": b, "user": self.salim})
            self.phone_owner[ph] = self.salim  # ground truth only
            self.kyc.append({"msisdn": ph, "subscriber_name": f"Ramesh Kumar {i+1}", "address": "Unverified",
                             "id_type": "Unverified", "activation_date": (a - timedelta(days=1)).date().isoformat(),
                             "operator": "Vi"})

    # ---------------------------------------------------------------- CDR
    def call(self, a: str, b: str, when: datetime, dur: int | None = None, tower: str | None = None):
        owner = self.phone_owner.get(a)
        tower = tower or (owner.home if owner else self.rng.choice(list(LOCATIONS)))
        self.cdr.append({
            "call_id": f"C{len(self.cdr)+1:06d}",
            "caller": a, "callee": b,
            "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": dur if dur is not None else self.rng.randint(20, 900),
            "call_type": self.rng.choice(["VOICE", "VOICE", "VOICE", "SMS"]),
            "tower_location": tower,
            "imei": self.imei_for(a),
        })

    def imei_for(self, msisdn: str) -> str:
        # burner SIMs are swapped into the same handset as Salim's second number (a classic IMEI clue)
        for b in self.burners:
            if b["msisdn"] == msisdn:
                msisdn = self.salim.phones[1]
        h = 0
        for ch in msisdn:
            h = (h * 31 + ord(ch)) % (10**13)
        return f"35{h:013d}"

    def build_cdr(self):
        rng = self.rng
        # Noise: citizens calling within realistic social circles (3-7 regular contacts, occasional strangers)
        citizens = [p for p in self.people if p.role == "citizen"]
        self.circles: dict[str, list[Person]] = {}
        for c in citizens:
            friends = rng.sample([x for x in citizens if x is not c], rng.randint(3, 7))
            self.circles.setdefault(c.name, [])
            for f in friends:
                if f not in self.circles[c.name]:
                    self.circles[c.name].append(f)
                self.circles.setdefault(f.name, [])
                if c not in self.circles[f.name]:
                    self.circles[f.name].append(c)
        for _ in range(2200):
            a = rng.choice(citizens)
            b = rng.choice(citizens) if rng.random() < 0.05 else rng.choice(self.circles[a.name])
            if a is not b:
                self.call(a.phones[0], b.phones[0], self.rand_dt())
        # Network structure: hierarchical, kingpin insulated
        def link(pa: Person, pb: Person, n: int, night=0.35, pa_idx=0, pb_idx=0):
            for _ in range(n):
                if rng.random() < 0.5:
                    self.call(pa.phones[pa_idx], pb.phones[pb_idx], self.rand_dt(night_bias=night))
                else:
                    self.call(pb.phones[pb_idx], pa.phones[pa_idx], self.rand_dt(night_bias=night))

        link(self.kingpin, self.salim, 38, pa_idx=1, pb_idx=1)         # kingpin's 2nd phone <-> Salim's 2nd phone
        link(self.kingpin, self.jain, 14, pa_idx=1, pb_idx=1)
        link(self.salim, self.vikram, 45)
        link(self.salim, self.imran, 30)
        link(self.salim, self.sunil, 26)
        link(self.salim, self.deepak, 24)
        link(self.vikram, self.anthony, 33, night=0.5)
        link(self.imran, self.deepak, 18, night=0.1)
        link(self.imran, self.sunil, 11, night=0.1)
        link(self.jain, self.priya, 22, night=0.05)
        link(self.jain, self.rakesh, 19, night=0.05, pa_idx=0)
        link(self.priya, self.rakesh, 9, night=0.0)
        link(self.rakesh, self.kiran, 21, night=0.0)
        link(self.rakesh, self.nilesh, 27, night=0.0)
        link(self.nilesh, self.kiran, 8, night=0.0)
        for m in self.mules:
            link(self.salim, m, 7, night=0.2)
            link(self.priya, m, 4, night=0.0)
        # Network members also have ordinary contacts (noise)
        for p in [x for x in self.people if x.in_network]:
            for _ in range(rng.randint(3, 8)):
                c = rng.choice(citizens)
                self.call(p.phones[0], c.phones[0], self.rand_dt(night_bias=0.05))
        # Kingpin's international contact (rare, very short, late night)
        for _ in range(6):
            self.call(self.abu_phone, self.kingpin.phones[1], self.rand_dt(night_bias=0.9), dur=rng.randint(30, 120),
                      tower="Dongri")
        # Shipment bursts: night before consignment landings
        for ship_dt in [datetime(2026, 1, 11, 20, 0), datetime(2026, 4, 1, 21, 0)]:
            burner = next(b for b in self.burners if b["active_from"] <= ship_dt <= b["active_to"])
            for _ in range(22):
                t = ship_dt + timedelta(minutes=rng.randint(0, 540))
                pair = rng.choice([(burner["msisdn"], self.vikram.phones[0]),
                                   (burner["msisdn"], self.anthony.phones[0]),
                                   (self.vikram.phones[0], self.anthony.phones[0])])
                self.call(pair[0], pair[1], t, dur=rng.randint(15, 240), tower=rng.choice(["Nhava Sheva", "Uran", "Panvel"]))
            # burner also pings Salim's second handset a few times (attribution clue)
            for _ in range(4):
                self.call(burner["msisdn"], self.salim.phones[1], burner["active_from"] + timedelta(hours=rng.randint(1, 90)),
                          dur=rng.randint(10, 60), tower="Nagpada")
        self.cdr.sort(key=lambda r: r["timestamp"])

    # ---------------------------------------------------------------- Transactions
    def transfer(self, src: str, dst: str, amt: float, when: datetime, mode="NEFT", remark=""):
        self.tx.append({
            "txn_id": f"T{len(self.tx)+1:07d}",
            "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
            "from_account": src, "from_holder": self.account_meta[src]["holder"], "from_bank": self.account_meta[src]["bank"],
            "to_account": dst, "to_holder": self.account_meta[dst]["holder"], "to_bank": self.account_meta[dst]["bank"],
            "amount_inr": round(amt, 2), "mode": mode, "remarks": remark,
        })

    def build_transactions(self):
        rng = self.rng
        citizens = [p for p in self.people if p.role == "citizen"]
        # Noise (transfers mostly within social circles)
        for _ in range(1400):
            a = rng.choice(citizens)
            b = rng.choice(citizens) if rng.random() < 0.1 else rng.choice(self.circles[a.name])
            if a is b:
                continue
            self.transfer(a.accounts[0], b.accounts[0], rng.choice([rng.randint(200, 5000), rng.randint(1000, 40000)]),
                          self.rand_dt(), mode=rng.choice(["UPI", "UPI", "IMPS", "NEFT"]),
                          remark=rng.choice(["rent", "food", "loan", "gift", "", "bill", "salary", "shopping"]))
        # Salaries / legit business flows for realism
        for p in [self.vikram, self.rakesh, self.jain, self.priya]:
            for _ in range(6):
                c = rng.choice(citizens)
                self.transfer(p.accounts[0], c.accounts[0], rng.randint(8000, 35000), self.rand_dt(), mode="NEFT", remark="salary")
        # STRUCTURING: cash-out to mules in sub-threshold chunks, then layering to shell -> hawala -> realty
        for base in [datetime(2026, 2, 3, 10, 0), datetime(2026, 3, 12, 10, 0), datetime(2026, 4, 6, 10, 0)]:
            for m in self.mules:
                for k in range(rng.randint(4, 6)):
                    t = base + timedelta(hours=rng.randint(0, 40))
                    amt = rng.choice([45000, 47000, 48500, 49000, 49500, 49900])
                    # cash deposit shows as CDM with no from-account -> we use distributor accounts as source
                    src = rng.choice([self.imran, self.sunil, self.deepak]).accounts[0]
                    self.transfer(src, m.accounts[0], amt, t, mode="CDM", remark="cash deposit")
                # mule forwards to shell company within a day
                total = sum(r["amount_inr"] for r in self.tx if r["to_account"] == m.accounts[0] and r["timestamp"] >= base.strftime("%Y-%m-%d"))
                self.transfer(m.accounts[0], self.skyline_acc, total * 0.97, base + timedelta(hours=rng.randint(30, 60)),
                              mode="RTGS", remark="consultancy fee")
            # Shell -> Jain Bullion -> Mehta Realty (layering, similar amounts, quick succession)
            skyline_in = sum(r["amount_inr"] for r in self.tx if r["to_account"] == self.skyline_acc and r["timestamp"] >= base.strftime("%Y-%m-%d"))
            self.transfer(self.skyline_acc, self.jain_bullion_acc, skyline_in * 0.95, base + timedelta(hours=70), mode="RTGS", remark="purchase of goods")
            self.transfer(self.jain_bullion_acc, self.mehta_realty_acc, skyline_in * 0.90, base + timedelta(hours=78), mode="RTGS", remark="advance booking - Sky Residency")
            self.transfer(self.mehta_realty_acc, self.kiran.accounts[0], skyline_in * 0.40, base + timedelta(hours=100), mode="RTGS", remark="investor payout")
        # Kingpin skimming via Jain in small transfers
        for _ in range(9):
            self.transfer(self.jain.accounts[1], self.kingpin.accounts[0], rng.randint(90000, 240000), self.rand_dt(), mode="NEFT", remark="loan repayment")
        # Logistics payments
        for _ in range(7):
            self.transfer(self.naik_cargo_acc, self.anthony.accounts[0], rng.randint(60000, 150000), self.rand_dt(), mode="NEFT", remark="clearing charges")
        for _ in range(5):
            self.transfer(self.salim.accounts[0], self.naik_cargo_acc, rng.randint(150000, 400000), self.rand_dt(), mode="RTGS", remark="transport")
        self.tx.sort(key=lambda r: r["timestamp"])

    # ---------------------------------------------------------------- FIRs
    def fir(self, ps: str, date: datetime, sections: str, text: str, complainant: str, accused: list[str], crime: str):
        no = f"{len(self.firs)+1:04d}/2026"
        self.firs.append({"fir_no": no, "police_station": ps, "date": date.strftime("%d/%m/%Y"), "sections": sections,
                          "crime_head": crime, "complainant": complainant, "accused": accused, "text": text})

    def build_firs(self):
        rng = self.rng
        # Key FIRs tying the story together
        self.fir("Bhiwandi City PS", datetime(2026, 2, 20), "u/s 8(c) r/w 20(b)(ii)(C), 29 NDPS Act", (
            "On 20/02/2026 at about 0315 hrs, acting on specific information received by the Anti-Narcotics Cell, "
            "a raid was conducted at Godown No. 14, Rahnal Village, Bhiwandi. During the raid, contraband suspected to be "
            "Mephedrone (MD) weighing approx. 12.4 kg was recovered concealed inside cartons of ceramic tiles. Accused "
            "Sunil Pawar (age 34) r/o Dharavi was apprehended at the spot. The cartons bore consignment labels of "
            "Naik Cargo Movers Pvt Ltd. A truck bearing registration no. MH 04 JK 2211 was found parked outside the godown. "
            "During interrogation accused Sunil Pawar stated that the consignment was received on instructions of one "
            "Salim Qureshi @ Salim Bhai r/o Nagpada, Mumbai and that payments were made through mobile no. "
            f"{self.salim.phones[0]}. One mobile phone (no. {self.sunil.phones[0]}) and cash Rs. 3,40,000/- were seized. "
            "Efforts are on to trace the owner of the vehicle and the godown."
        ), "PSI R. B. Mane (ANC)", ["Sunil Pawar", "Salim Qureshi"], "NDPS")
        self.fir("Nhava Sheva PS", datetime(2026, 1, 14), "u/s 135 Customs Act, u/s 29 NDPS Act", (
            "Complainant Shri Dinesh Rathod, Superintendent of Customs, JNPT reported that on 12/01/2026 a container "
            "(No. MSKU 771 2091 8) declared as ceramic tiles imported from Jebel Ali, UAE was cleared through the green channel "
            "based on documents filed by Seagull Clearing Agency, Uran. Subsequent intelligence indicates the consignment "
            "was cleared irregularly. The clearing agent Anthony D'Souza @ Tony r/o Uran (mobile no. "
            f"{self.anthony.phones[0]}) was present at the gate. CCTV shows the container being loaded on to truck no. "
            "MH 04 JK 2211 owned by Naik Cargo Movers Pvt Ltd, Bhiwandi. Inquiry is in progress."
        ), "Dinesh Rathod", ["Anthony D'Souza"], "Customs")
        self.fir("Kurla PS", datetime(2026, 3, 2), "u/s 8(c) r/w 22(b) NDPS Act", (
            "On 01/03/2026 at about 2240 hrs near Kurla Station (West), accused Imran Ansari @ Chikna (age 29) r/o "
            "Kurla was found in possession of 210 gm Mephedrone. He was riding a motorcycle bearing no. "
            f"{self.imran.vehicles[0]}. During search a mobile phone no. {self.imran.phones[0]} was seized which contained "
            "chats with one 'DK' and one 'Salim Bhai'. Accused disclosed that he receives material from Salim Qureshi of "
            "Nagpada and sells in Kurla, Chembur and Ghatkopar areas along with Deepak Yadav @ DK of Mira Road."
        ), "PSI A. K. Tambe", ["Imran Ansari", "Deepak Yadav"], "NDPS")
        self.fir("Colaba PS", datetime(2026, 3, 9), "u/s 3 & 4 PMLA (ED reference), u/s 120B IPC", (
            "Reference received from Directorate of Enforcement regarding suspicious layering of funds. It is alleged that "
            "Mahesh Jain @ Seth, proprietor of Jain Bullion & Traders, Kalbadevi, is operating an unlicensed hawala channel "
            "through which proceeds of narcotics trade are routed via Skyline Infra Ventures Pvt Ltd (Director: Priya Deshmukh, "
            "Andheri East) into real estate projects of Mehta Realty LLP promoted by Rakesh Mehta r/o Bandra West. "
            "Surveillance recorded a meeting between Mahesh Jain and one Rafiq Sheikh @ Bhai r/o Dongri at Hotel Sea Breeze, "
            "Colaba on 08/03/2026. Rafiq Sheikh arrived in a white SUV bearing registration no. MH 02 CX 4521. "
            "Investigation is in progress."
        ), "ED (Mumbai Zonal Office)", ["Mahesh Jain", "Priya Deshmukh", "Rakesh Mehta", "Rafiq Sheikh"], "PMLA")
        self.fir("Dongri PS", datetime(2019, 6, 4), "u/s 307, 34 IPC, u/s 25 Arms Act", (
            "(Archived record) On 03/06/2019 complainant Shri Abdul Karim reported that accused Rafiq Sheikh @ Bhai "
            "r/o Dongri along with Salim Qureshi fired at him near Chor Bazaar over a dispute regarding extortion money. "
            "Accused Rafiq Sheikh was earlier convicted u/s 392 IPC in the year 2011. Both accused are known history-sheeters "
            "of Dongri PS."
        ), "Abdul Karim", ["Rafiq Sheikh", "Salim Qureshi"], "Attempt to murder")
        self.fir("Ghatkopar PS", datetime(2026, 2, 27), "u/s 420, 467, 468, 471 IPC", (
            "Complainant, Branch Manager, HDFC Bank Ghatkopar reported that account holder Ravi Kumar r/o Ghatkopar "
            "received multiple cash deposits of Rs. 45,000/- to Rs. 49,900/- through CDM within 48 hours which were "
            "immediately transferred by RTGS to Skyline Infra Ventures Pvt Ltd. On enquiry Ravi Kumar stated he had lent "
            "his account to one 'Salim Bhai' for a commission of Rs. 5,000/- per lakh. Similar pattern noticed in accounts of "
            "Anita Shinde (Chembur) and Suresh Gaikwad (Kalyan)."
        ), "Branch Manager, HDFC Bank", ["Ravi Kumar", "Anita Shinde", "Suresh Gaikwad"], "Cheating/Forgery")
        self.fir("Mumbra PS", datetime(2026, 3, 20), "u/s 8(c) r/w 21(b) NDPS Act", (
            f"Accused Mohd Farhan r/o Mumbra was apprehended near Mumbra Bypass with 48 gm Heroin. Mobile no. {self.mules[2].phones[0]} "
            "seized. Call records show frequent contact with a number registered in the name of Salim Qureshi of Nagpada. "
            "Accused stated that he also receives cash deposits in his bank account on instructions of Salim Bhai."
        ), "PSI S. D. Bhoir", ["Mohd Farhan"], "NDPS")

        # Noise FIRs (unrelated crimes involving random citizens)
        heads = [
            ("u/s 379 IPC", "Theft", "reported that his mobile phone was stolen from his pocket while travelling in a crowded local train between {a} and {b}."),
            ("u/s 392 IPC", "Robbery", "reported that two unknown persons on a motorcycle bearing no. {plate} snatched her gold chain weighing 15 gm near {a}."),
            ("u/s 279, 337 IPC", "Rash driving", "reported that a car bearing no. {plate} driven rashly dashed his two-wheeler near {a} causing injuries."),
            ("u/s 420 IPC, u/s 66D IT Act", "Cyber fraud", "reported that he received a call from mobile no. {phone} posing as bank official and lost Rs. {amt}/- through UPI."),
            ("u/s 323, 504, 506 IPC", "Assault", "reported that accused {acc} r/o {a} assaulted him over a parking dispute near {b}."),
            ("u/s 454, 380 IPC", "House break-in", "reported that unknown persons broke into his flat at {a} and stole cash and jewellery worth Rs. {amt}/-."),
        ]
        citizens = [p for p in self.people if p.role == "citizen"]
        for i in range(34):
            sec, head, tmpl = rng.choice(heads)
            c = rng.choice(citizens)
            acc = rng.choice(citizens)
            a, b = rng.sample(list(LOCATIONS), 2)
            d = self.rand_dt()
            body = tmpl.format(a=a, b=b, plate=self.plate(), phone=self.phone(), amt=f"{rng.randint(5, 90)*1000:,}", acc=acc.name)
            text = f"On {d.strftime('%d/%m/%Y')} at about {d.strftime('%H%M')} hrs, complainant {rng.choice(['Shri','Smt'])} {c.name} r/o {c.home} {body}"
            self.fir(rng.choice(POLICE_STATIONS), d, sec, text, c.name, [acc.name] if "{acc}" in tmpl else [], head)
        self.firs.sort(key=lambda f: datetime.strptime(f["date"], "%d/%m/%Y"))

    # ---------------------------------------------------------------- Surveillance
    def sighting(self, dt: datetime, loc: str, persons: list[Person], vehicles: list[str], note: str, officer: str | None = None):
        lat, lon = LOCATIONS[loc]
        self.surv.append({
            "report_id": f"SR-{len(self.surv)+1:04d}",
            "timestamp": dt.strftime("%Y-%m-%d %H:%M"),
            "location": loc, "lat": lat + self.rng.uniform(-0.004, 0.004), "lon": lon + self.rng.uniform(-0.004, 0.004),
            "subjects": [p.name for p in persons], "vehicles": vehicles,
            "observation": note, "officer": officer or f"HC {self.rng.choice(LAST_NAMES)} (Unit {self.rng.randint(1,6)})",
            "unit": self.rng.choice(["ANC Unit-2", "Crime Branch Unit-5", "DRI Mumbai", "SB-I"]),
        })

    def build_surveillance(self):
        self.sighting(datetime(2026, 1, 12, 4, 20), "Nhava Sheva", [self.vikram, self.anthony], ["MH 04 JK 2211"],
                      "Truck MH 04 JK 2211 exited JNPT Gate 3 escorted by clearing agent Anthony D'Souza in a grey Scorpio. Vikram Naik seen at the wheel. Proceeded towards Panvel.")
        self.sighting(datetime(2026, 1, 12, 6, 50), "Bhiwandi", [self.vikram], ["MH 04 JK 2211"],
                      "Truck offloaded cartons at Godown No. 14, Rahnal. Two unidentified labourers assisted.")
        self.sighting(datetime(2026, 1, 15, 22, 10), "Nagpada", [self.salim, self.vikram], ["MH 04 HB 7830"],
                      "Salim Qureshi met Vikram Naik at Sarvi Restaurant for ~40 min. Vikram handed over a black bag.")
        self.sighting(datetime(2026, 2, 1, 23, 30), "Dongri", [self.kingpin, self.salim], ["MH 02 CX 4521"],
                      "Subject Rafiq Sheikh @ Bhai seen entering residence with Salim Qureshi. White Fortuner MH 02 CX 4521 parked outside.")
        self.sighting(datetime(2026, 3, 8, 20, 15), "Colaba", [self.kingpin, self.jain], ["MH 02 CX 4521"],
                      "Rafiq Sheikh met Mahesh Jain @ Seth at Hotel Sea Breeze, table 12, for 1 hr 10 min. Jain carried a leather briefcase which he did not have on exit.")
        self.sighting(datetime(2026, 3, 11, 12, 0), "Kalbadevi", [self.jain, self.priya], [],
                      "Priya Deshmukh visited Jain Bullion & Traders shop; stayed 25 min; carried documents folder.")
        self.sighting(datetime(2026, 3, 14, 17, 45), "Bandra West", [self.rakesh, self.jain, self.nilesh], [self.rakesh.vehicles[0]],
                      "Meeting at Mehta Realty site office, Sky Residency project. Nilesh Shah arrived separately.")
        self.sighting(datetime(2026, 3, 15, 23, 50), "Kurla", [self.imran, self.deepak], [self.imran.vehicles[0]],
                      "Imran Ansari and Deepak Yadav at Kurla Nights lounge; multiple short interactions with unknown youths in parking lot.")
        self.sighting(datetime(2026, 4, 2, 3, 40), "Uran", [self.vikram, self.anthony], ["MH 04 JK 2211"],
                      "Second consignment movement suspected. Truck MH 04 JK 2211 exited port area at 0340 hrs. Anthony D'Souza on phone continuously.")
        self.sighting(datetime(2026, 4, 2, 5, 30), "Panvel", [self.vikram], ["MH 04 JK 2211"],
                      "Truck halted at Panvel; Vikram Naik made calls from a second handset.")
        self.sighting(datetime(2026, 4, 10, 21, 0), "Dongri", [self.kingpin], ["MH 02 CX 4521"],
                      "Rafiq Sheikh hosted a gathering of ~15 persons at residence; attendees included Salim Qureshi and two unidentified males.")
        # Noise surveillance of citizens
        citizens = [p for p in self.people if p.role == "citizen"]
        for _ in range(14):
            c = self.rng.choice(citizens)
            self.sighting(self.rand_dt(), self.rng.choice(list(LOCATIONS)), [c], c.vehicles[:1],
                          self.rng.choice(["Routine check at nakabandi; documents verified.", "Subject seen at market; nothing suspicious.",
                                           "Vehicle parked at no-parking zone; challan issued.", "Subject attended a public rally."]))
        self.surv.sort(key=lambda r: r["timestamp"])

    # ---------------------------------------------------------------- Social media
    def build_social(self):
        rng = self.rng
        posts = [
            (self.imran, datetime(2026, 3, 15, 23, 10), "Kurla", "Night out with @dk_miraroad at Kurla Nights 🔥 #squad", ["@dk_miraroad"]),
            (self.deepak, datetime(2026, 3, 16, 1, 30), "Kurla", "bhai log full paisa vasool 😎 @imran_kurla", ["@imran_kurla"]),
            (self.deepak, datetime(2026, 2, 5, 19, 0), "Mira Road", "New bike new life 🏍️ MH 04 HB 7830 style", []),
            (self.imran, datetime(2026, 1, 20, 21, 0), "Nagpada", "Dinner at Sarvi with Salim Bhai. Respect. 🙏", []),
            (self.rakesh, datetime(2026, 3, 14, 18, 30), "Bandra West", "Sky Residency bookings open! Contact Nilesh Shah for site visit. #MehtaRealty", []),
            (self.kiran, datetime(2026, 3, 20, 11, 0), "Surat", "Proud investor in Sky Residency, Bandra. Thanks Rakesh Mehta ji!", []),
            (self.vikram, datetime(2026, 1, 13, 9, 0), "Bhiwandi", "Naik Cargo Movers - now handling JNPT import clearances end to end. DM for rates.", []),
        ]
        for p, dt, loc, text, mentions in posts:
            self.social.append({"post_id": f"SM-{len(self.social)+1:04d}", "platform": rng.choice(["Instagram", "X", "Facebook"]),
                                "handle": p.handle or f"@{p.name.lower().replace(' ', '_').replace(chr(39), '')}",
                                "author_name": p.name, "timestamp": dt.strftime("%Y-%m-%d %H:%M"), "location_tag": loc,
                                "text": text, "mentions": mentions, "likes": rng.randint(5, 900)})
        citizens = [p for p in self.people if p.role == "citizen"]
        fillers = ["Good morning Mumbai ☀️", "Traffic at {loc} is insane today", "Best vada pav at {loc} 🤤", "Monday blues",
                   "Family time at {loc} ❤️", "Cricket tonight! 🏏", "Rain rain go away", "Weekend vibes at {loc}"]
        for _ in range(45):
            c = rng.choice(citizens)
            loc = rng.choice(list(LOCATIONS))
            self.social.append({"post_id": f"SM-{len(self.social)+1:04d}", "platform": rng.choice(["Instagram", "X", "Facebook"]),
                                "handle": f"@{c.name.lower().replace(' ', '_').replace(chr(39), '')}{rng.randint(1,99)}",
                                "author_name": c.name, "timestamp": self.rand_dt().strftime("%Y-%m-%d %H:%M"), "location_tag": loc,
                                "text": rng.choice(fillers).format(loc=loc), "mentions": [], "likes": rng.randint(0, 200)})
        self.social.sort(key=lambda r: r["timestamp"])

    # ---------------------------------------------------------------- Intel
    def build_intel(self):
        self.intel = [
            {"ref": "IB/MUM/2026/0117", "agency": "IB", "date": "2026-01-17", "classification": "SECRET", "text": (
                "Source reporting indicates that a Dubai-based handler known as Abu Hamza (contact +971 50 123 4567) is "
                "coordinating Mephedrone consignments to Mumbai via JNPT using ceramic tile imports. The Mumbai end is "
                "controlled by Rafiq Sheikh @ Bhai of Dongri who insulates himself through his lieutenant Salim Qureshi. "
                "Logistics are handled by Naik Cargo Movers Pvt Ltd (Vikram Naik, Bhiwandi). A customs clearing agent in "
                "Uran, Anthony D'Souza, is believed to be compromised.")},
            {"ref": "FIU-IND/STR/2026/0442", "agency": "FIU-IND", "date": "2026-02-26", "classification": "CONFIDENTIAL", "text": (
                "Suspicious Transaction Report: Multiple cash deposits below the Rs. 50,000 reporting threshold observed in "
                "accounts of Ravi Kumar, Anita Shinde, Mohd Farhan and Suresh Gaikwad, followed by RTGS transfers to "
                "Skyline Infra Ventures Pvt Ltd (AXIS Bank). Funds are further layered through Jain Bullion & Traders and "
                "Mehta Realty LLP. Pattern consistent with structuring and trade-based laundering.")},
            {"ref": "DRI/MZU/2026/0331", "agency": "DRI", "date": "2026-03-31", "classification": "SECRET", "text": (
                "Advance intelligence: second consignment expected at JNPT around 01-02 April 2026 via container declared as "
                "sanitary ware. Same modus operandi; Seagull Clearing Agency filing documents. Vikram Naik's truck MH 04 JK 2211 "
                "likely to be used. Salim Qureshi has activated a new prepaid number as per source.")},
            {"ref": "SB-I/MUM/2026/0402", "agency": "Special Branch", "date": "2026-04-12", "classification": "CONFIDENTIAL", "text": (
                "Rafiq Sheikh hosted a gathering at Dongri on 10 April attended by Salim Qureshi and Mahesh Jain. Chatter "
                "suggests expansion to Pune (Kondhwa) through a distributor identified only as 'Bunty'. Deepak Yadav @ DK is "
                "reportedly liaising with Pune contacts.")},
            {"ref": "SB-I/MUM/2026/0118", "agency": "Special Branch", "date": "2026-01-25", "classification": "RESTRICTED", "text": (
                "Routine: Political rally at Vashi passed off peacefully. No untoward incident. Estimated attendance 4,000.")},
            {"ref": "IB/MUM/2026/0203", "agency": "IB", "date": "2026-02-03", "classification": "RESTRICTED", "text": (
                "Routine: Monitoring of communal harmony in Byculla and Nagpada during festival period. No adverse inputs.")},
        ]

    # ---------------------------------------------------------------- Ground truth
    def ground_truth(self) -> dict:
        members = [p for p in self.people if p.in_network]
        return {
            "operation": "Operation Saltwater",
            "description": "Fictional narcotics trafficking + hawala laundering network for evaluation.",
            "members": [{"name": p.name, "alias": p.alias, "role": p.role, "cluster": p.cluster, "phones": p.phones,
                         "accounts": p.accounts, "vehicles": p.vehicles, "org": p.org} for p in members],
            "key_players": ["Rafiq Sheikh", "Salim Qureshi", "Mahesh Jain", "Vikram Naik", "Rakesh Mehta"],
            "brokers": ["Mahesh Jain", "Priya Deshmukh"],
            "burner_phones": [{"msisdn": b["msisdn"], "true_user": b["user"].name,
                               "active_from": b["active_from"].isoformat(), "active_to": b["active_to"].isoformat()} for b in self.burners],
            "structuring_mules": [m.name for m in self.mules],
            "shell_companies": ["Skyline Infra Ventures Pvt Ltd", "Jain Bullion & Traders", "Mehta Realty LLP", "Naik Cargo Movers Pvt Ltd"],
            "foreign_handler_phone": self.abu_phone,
            "events": [
                {"date": "2026-01-12", "event": "Consignment 1 cleared at JNPT"},
                {"date": "2026-02-03", "event": "Structuring wave 1"},
                {"date": "2026-02-20", "event": "Bhiwandi godown raid"},
                {"date": "2026-03-08", "event": "Rafiq-Jain meeting at Colaba"},
                {"date": "2026-04-02", "event": "Consignment 2 movement"},
            ],
        }

    # ---------------------------------------------------------------- Run
    def run(self, out: Path = OUT):
        self.build_actors()
        self.build_cdr()
        self.build_transactions()
        self.build_firs()
        self.build_surveillance()
        self.build_social()
        self.build_intel()
        out.mkdir(parents=True, exist_ok=True)

        def dump_json(name, obj):
            (out / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

        def dump_csv(name, rows):
            with (out / name).open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        dump_json("firs.json", self.firs)
        dump_csv("cdr.csv", self.cdr)
        dump_csv("kyc.csv", self.kyc)
        dump_csv("transactions.csv", self.tx)
        dump_json("surveillance.json", self.surv)
        dump_json("social_media.json", self.social)
        dump_json("intel_reports.json", self.intel)
        dump_json("ground_truth.json", self.ground_truth())
        dump_json("gazetteer.json", {k: {"lat": v[0], "lon": v[1]} for k, v in LOCATIONS.items()})
        print(f"Generated: {len(self.firs)} FIRs, {len(self.cdr)} CDR rows, {len(self.tx)} transactions, "
              f"{len(self.surv)} surveillance reports, {len(self.social)} posts, {len(self.intel)} intel notes, "
              f"{len(self.kyc)} KYC rows -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=26189)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    Generator(args.seed).run(args.out)
