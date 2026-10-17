import hashlib
import json
import sqlite3
import time
from typing import Tuple


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


def compute_hash(
    seq_id: int, timestamp: float, payload: str, prev_hash: str
) -> str:
  data_stream = f"{seq_id}:{timestamp:.6f}:{payload}:{prev_hash}".encode(
      "utf-8"
  )
  return hashlib.sha256(data_stream).hexdigest()


def append_state_entry(
    conn: sqlite3.Connection, payload_dict: dict
) -> Tuple[int, str]:
  payload_str = json.dumps(payload_dict, sort_keys=True)
  now = time.time()

  with conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT sequence_id, entry_hash FROM state_ledger ORDER BY sequence_id"
      " DESC LIMIT 1;"
    )
    row = cursor.fetchone()

    if row is None:
      seq_id = 1
      prev_hash = (
          "0000000000000000000000000000000000000000000000000000000000000000"
      )
    else:
      seq_id = row[0] + 1
      prev_hash = row[1]

    entry_hash = compute_hash(seq_id, now, payload_str, prev_hash)

    cursor.execute(
        """
            INSERT INTO state_ledger (sequence_id, timestamp, payload, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?);
            """,
        (seq_id, now, payload_str, prev_hash, entry_hash),
    )

  return seq_id, entry_hash


def verify_chain_integrity(conn: sqlite3.Connection) -> bool:
  cursor = conn.cursor()
  cursor.execute(
      "SELECT sequence_id, timestamp, payload, prev_hash, entry_hash FROM"
      " state_ledger ORDER BY sequence_id ASC;"
  )
  records = cursor.fetchall()

  expected_prev = (
      "0000000000000000000000000000000000000000000000000000000000000000"
  )

  for seq_id, ts, payload, prev_hash, entry_hash in records:
    if prev_hash != expected_prev:
      print(f"[FAIL] Broken hash link at sequence {seq_id}")
      return False

    calculated = compute_hash(seq_id, ts, payload, prev_hash)
    if calculated != entry_hash:
      print(f"[FAIL] Data tampering detected at sequence {seq_id}")
      return False

    expected_prev = entry_hash

  return True


if __name__ == "__main__":
  db_file = "ledger.db"
  conn = get_connection(db_file)
  initialize_ledger(conn)

  print("--- Running State Insertion Test ---")
  s1, h1 = append_state_entry(
      conn, {"event": "node_init", "device": "chromebook_local"}
  )
  print(f"Committed Seq {s1} | Hash: {h1[:16]}...")

  s2, h2 = append_state_entry(
      conn, {"event": "ingress_check", "status": "nominal", "inputs": 4}
  )
  print(f"Committed Seq {s2} | Hash: {h2[:16]}...")

  print("\n--- Running Offline Chain Verification ---")
  is_valid = verify_chain_integrity(conn)
  print(
      "Chain Integrity Status:"
      f" {'[PASS] All Hashes Invariant' if is_valid else '[FAIL] Invalid State'}"
  )

  conn.close()
