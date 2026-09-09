import sqlite3
import json
import sys

sys.path.insert(0, 'backend')
from app.db import SessionLocal
from app.graph.builder import GraphBuilder
from app.graph.analytics import actor_projection, key_players

db = SessionLocal()
G, D = GraphBuilder(db).build()
P = actor_projection(D)
print("Actors in P:", P.number_of_nodes())
print("Edges in P:", P.number_of_edges())
print("Degrees in P:", [P.degree(n) for n in P])
