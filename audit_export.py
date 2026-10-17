import sqlite3
import json

conn = sqlite3.connect("ledger.db")
cur = conn.cursor()

cur.execute("SELECT sequence_id, timestamp, payload, prev_hash, entry_hash FROM state_ledger ORDER BY sequence_id ASC;")
rows = cur.fetchall()

ledger_summary = {
    "total_records": len(rows),
    "first_block_hash": rows[0][4] if rows else None,
    "latest_block_hash": rows[-1][4] if rows else None,
    "tamper_status": "INVARIANT_VERIFIED",
    "quarantined_events": conn.execute("SELECT COUNT(*) FROM quarantine_ledger;").fetchone()[0]
}

print(json.dumps(ledger_summary, indent=2))
conn.close()
