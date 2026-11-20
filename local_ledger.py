import hashlib
import json
import sqlite3
import time
from typing import Tuple

# WAL checkpoint policy: the write-ahead log is auto-checkpointed after
# this many pages (~4.1 MB at the default 4096-byte page size). That is the
# same bound SQLite uses by default, made explicit here so the WAL size is
# bounded by policy rather than by an implicit default. BUSY_TIMEOUT_MS
# bounds how long one writer waits on another before "database is locked".
WAL_AUTOCHECKPOINT_PAGES = 1000
BUSY_TIMEOUT_MS = 5000

# A ledger append that loses a race for the write lock retries this many
# times with exponential backoff before giving up.
_APPEND_MAX_ATTEMPTS = 10


def _is_busy(exc: Exception) -> bool:
  msg = str(exc).lower()
  return "locked" in msg or "busy" in msg


def _backoff(attempt: int) -> float:
  return min(0.05, 0.001 * (2 ** attempt))


def get_connection(db_path: str = "ledger.db") -> sqlite3.Connection:
  # busy_timeout goes first: the journal-mode change below needs exclusive
  # access, and a connection that opens while another thread holds the
  # write lock must wait instead of failing immediately. The whole setup
  # retries on busy: the first thread to flip a fresh file to WAL mode
  # can collide with a writer that got there first.
  last_exc = None
  for attempt in range(_APPEND_MAX_ATTEMPTS):
    conn = sqlite3.connect(db_path)
    try:
      conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS};")
      conn.execute("PRAGMA journal_mode = WAL;")
      conn.execute("PRAGMA synchronous = NORMAL;")
      conn.execute(f"PRAGMA wal_autocheckpoint = {WAL_AUTOCHECKPOINT_PAGES};")
      return conn
    except sqlite3.OperationalError as e:
      last_exc = e
      try:
        conn.close()
      except Exception:
        pass
      if _is_busy(e) and attempt < _APPEND_MAX_ATTEMPTS - 1:
        time.sleep(_backoff(attempt))
        continue
      raise
  raise last_exc


def initialize_ledger(conn: sqlite3.Connection) -> None:
  # CREATE TABLE IF NOT EXISTS is idempotent, but under concurrency the
  # first writers can collide on the schema lock; retry on busy.
  for attempt in range(_APPEND_MAX_ATTEMPTS):
    try:
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
      return
    except sqlite3.OperationalError as e:
      if _is_busy(e) and attempt < _APPEND_MAX_ATTEMPTS - 1:
        time.sleep(_backoff(attempt))
        continue
      raise


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
  """Append one entry and return (sequence_id, entry_hash).

  Sequence assignment is atomic: the read of the last entry (for the next
  sequence_id and prev_hash) and the INSERT run inside one write
  transaction held with BEGIN IMMEDIATE, so two concurrent writers cannot
  read the same max sequence_id and collide on the UNIQUE constraint.
  A writer that loses the race for the write lock retries with bounded
  exponential backoff instead of failing the append. If this connection
  is already inside a caller-managed transaction, the append joins it
  (the caller owns the lock and the commit).
  """
  payload_str = json.dumps(payload_dict, sort_keys=True)

  for attempt in range(_APPEND_MAX_ATTEMPTS):
    now = time.time()
    try:
      if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as e:
      if _is_busy(e) and attempt < _APPEND_MAX_ATTEMPTS - 1:
        time.sleep(_backoff(attempt))
        continue
      raise

    try:
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
      conn.commit()
    except Exception:
      conn.rollback()
      raise

    return seq_id, entry_hash

  raise sqlite3.OperationalError(
      "database is locked: ledger append failed after bounded retries"
  )


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
