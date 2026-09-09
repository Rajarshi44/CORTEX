import sqlite3
import json

db = sqlite3.connect('backend/demo.db')
c = db.cursor()
c.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 5")
print("audit_log:")
for row in c.fetchall():
    print(row)
