import hashlib
import json
import sqlite3
import sys
import time
from typing import Dict, Tuple

REQUIRED_INGRESS_KEYS = {"source", "event_type", "data"}


def get_connection(db_path: str = "ledger.db") -> sqlite3.Connection:
  conn = sqlite3.connect(db_path)
  conn.execute("PRAGMA journal_mode = WAL;")
  conn.execute("PRAGMA synchronous = NORMAL;")
  return conn


def initialize_ledger(conn: sqlite3.Connection) -> None:
  with conn:
    conn.execute("""
            CREATE TABLE IF NOT EXISTS state_ledger (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL UNIQUE
            );
            """)


def validate_ingress_payload(payload: Dict) -> bool:
  if not isinstance(payload, dict):
    return False
  if not REQUIRED_INGRESS_KEYS.issubset(payload.keys()):
    return False
  if len(json.dumps(payload)) > 65536:
    return False
  return True


def compute_hash(
    seq_id: int, timestamp: float, payload: str, prev_hash: str
) -> str:
  data_stream = f"{seq_id}:{timestamp:.6f}:{payload}:{prev_hash}".encode(
      "utf-8"
  )
  return hashlib.sha256(data_stream).hexdigest()


def commit_ingress(
    conn: sqlite3.Connection, payload: Dict
) -> Tuple[bool, str]:
  if not validate_ingress_payload(payload):
    return False, "ERR_INVALID_INGRESS_SCHEMA"

  payload_str = json.dumps(payload, sort_keys=True)
  now = time.time()

  with conn:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sequence_id, entry_hash FROM state_ledger ORDER BY sequence_id"
        " DESC LIMIT 1;"
    )
    row = cursor.fetchone()

    seq_id = 1 if row is None else row[0] + 1
    prev_hash = (
        "0000000000000000000000000000000000000000000000000000000000000000"
        if row is None
        else row[1]
    )
    entry_hash = compute_hash(seq_id, now, payload_str, prev_hash)

    cursor.execute(
        """
            INSERT INTO state_ledger (sequence_id, timestamp, payload, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?);
            """,
        (seq_id, now, payload_str, prev_hash, entry_hash),
    )

  return True, entry_hash


if __name__ == "__main__":
  conn = get_connection("ledger.db")
  initialize_ledger(conn)

  # Test valid ingress
  ok1, res1 = commit_ingress(
      conn,
      {
          "source": "edge_node_01",
          "event_type": "telemetry",
          "data": {"status": "ok"},
      },
  )
  print(f"Ingress Test 1 (Valid Schema): {'PASS' if ok1 else 'FAIL'} -> {res1}")

  # Test invalid ingress (missing required key)
  ok2, res2 = commit_ingress(
      conn, {"source": "untrusted_input", "unknown_blob": 123}
  )
  print(f"Ingress Test 2 (Malformed Schema): {'PASS' if not ok2 else 'FAIL'}")

  conn.close()
