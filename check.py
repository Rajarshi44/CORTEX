import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.abspath('backend'))

from app.graph.store import graph_cache
from app.graph.analytics import is_non_subject

db = sqlite3.connect('backend/demo.db')
c = db.cursor()

c.execute('SELECT payload FROM analysis_snapshots ORDER BY computed_at DESC LIMIT 1')
res = c.fetchone()
data = json.loads(res[0])
priority = data.get("priority", {})
metrics = data.get("metrics", {})

from app.db import SessionLocal
from sqlalchemy import create_engine
engine = create_engine('sqlite:///backend/demo.db')
SessionLocal.configure(bind=engine)
session = SessionLocal()

D = graph_cache.get_directed(session)

missing = list(priority.keys())[0]
print("Missing node from priority:", missing)
print("Is missing in D?", missing in D)
if missing in D:
    print("Missing node data:", D.nodes[missing])

