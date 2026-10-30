import sqlite3
import hashlib
import time
import json

DB_FILE = "protocol_ledger.db"

def init_ledger():
    conn = sqlite3.connect(DB_FILE)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state_chain (
                index_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                state_name TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                block_hash TEXT NOT NULL
            )
        """)
    conn.close()

def append_state(state_name: str, payload: dict) -> str:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT block_hash FROM state_chain ORDER BY index_id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_hash = row[0] if row else "0" * 64

    ts = time.time()
    payload_str = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    
    block_raw = f"{ts}:{state_name}:{payload_hash}:{prev_hash}".encode("utf-8")
    block_hash = hashlib.sha256(block_raw).hexdigest()

    with conn:
        conn.execute("""
            INSERT INTO state_chain (timestamp, state_name, payload_hash, prev_hash, block_hash)
            VALUES (?, ?, ?, ?, ?)
        """, (ts, state_name, payload_hash, prev_hash, block_hash))
    conn.close()
    return block_hash

if __name__ == "__main__":
    init_ledger()
    h = append_state("InvariantLocked", {"status": "active", "node": "primary"})
    print(f"[+] State committed to immutable ledger. Block Hash: {h}")
