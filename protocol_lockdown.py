import sqlite3
import hashlib
import json
import time
from typing import Dict, Tuple

REQUIRED_INGRESS_KEYS = {"source", "event_type", "data"}

def get_connection(db_path: str = "ledger.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def initialize_lockdown_storage(conn: sqlite3.Connection) -> None:
    with conn:
        # Standard verified ledger
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_ledger (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL UNIQUE
            );
            """
        )
        # Isolated quarantine table for rejected ingress attempts
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quarantine_ledger (
                incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                raw_payload TEXT NOT NULL,
                rejection_reason TEXT NOT NULL,
                incident_hash TEXT NOT NULL UNIQUE
            );
            """
        )

def validate_schema(payload: Dict) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "PAYLOAD_NOT_OBJECT"
    if not REQUIRED_INGRESS_KEYS.issubset(payload.keys()):
        missing = REQUIRED_INGRESS_KEYS - payload.keys()
        return False, f"MISSING_KEYS_{','.join(sorted(missing))}"
    if len(json.dumps(payload)) > 65536:
        return False, "PAYLOAD_EXCEEDS_64KB"
    return True, "VALID"

def process_ingress_secure(conn: sqlite3.Connection, raw_input: Dict) -> Tuple[str, str]:
    is_valid, reason = validate_schema(raw_input)
    now = time.time()
    raw_str = json.dumps(raw_input, sort_keys=True)

    with conn:
        cursor = conn.cursor()
        if is_valid:
            cursor.execute("SELECT sequence_id, entry_hash FROM state_ledger ORDER BY sequence_id DESC LIMIT 1;")
            row = cursor.fetchone()
            seq_id = 1 if row is None else row[0] + 1
            prev_hash = "0" * 64 if row is None else row[1]
            
            entry_hash = hashlib.sha256(f"{seq_id}:{now:.6f}:{raw_str}:{prev_hash}".encode("utf-8")).hexdigest()
            cursor.execute(
                "INSERT INTO state_ledger (sequence_id, timestamp, payload, prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?);",
                (seq_id, now, raw_str, prev_hash, entry_hash)
            )
            return "COMMITTED", entry_hash
        else:
            incident_hash = hashlib.sha256(f"{now:.6f}:{raw_str}:{reason}".encode("utf-8")).hexdigest()
            cursor.execute(
                "INSERT INTO quarantine_ledger (timestamp, raw_payload, rejection_reason, incident_hash) VALUES (?, ?, ?, ?);",
                (now, raw_str, reason, incident_hash)
            )
            return "QUARANTINED", incident_hash

if __name__ == "__main__":
    conn = get_connection("ledger.db")
    initialize_lockdown_storage(conn)

    print("--- Testing Lockdown Protocol ---")
    status1, hash1 = process_ingress_secure(conn, {
        "source": "local_daemon",
        "event_type": "state_sync",
        "data": {"block_height": 100}
    })
    print(f"Action 1 (Valid Input)     : [{status1}] Hash: {hash1[:16]}...")

    status2, hash2 = process_ingress_secure(conn, {
        "malicious_field": "injection_vector"
    })
    print(f"Action 2 (Malformed Input) : [{status2}] Quarantine Hash: {hash2[:16]}...")

    # Verify separation of tables
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM state_ledger;")
    valid_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM quarantine_ledger;")
    quarantine_count = cur.fetchone()[0]

    print(f"\nAudit Totals -> Active Ledger: {valid_count} | Honeypot Quarantine: {quarantine_count}")
    conn.close()
