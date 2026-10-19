import sqlite3
import hashlib
import time
from typing import List, Optional

def get_connection(db_path: str = "ledger.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def initialize_epoch_table(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS epoch_receipts (
                epoch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_seq INTEGER NOT NULL,
                end_seq INTEGER NOT NULL,
                block_count INTEGER NOT NULL,
                merkle_root TEXT NOT NULL UNIQUE,
                sealed_at REAL NOT NULL
            );
            """
        )

def calculate_merkle_root(leaf_hashes: List[str]) -> str:
    if not leaf_hashes:
        return "0" * 64
    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    current_level = leaf_hashes
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            combined = hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest()
            next_level.append(combined)
        current_level = next_level
    return current_level[0]

def seal_latest_epoch(conn: sqlite3.Connection, batch_size: int = 10) -> Optional[dict]:
    initialize_epoch_table(conn)
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(end_seq) FROM epoch_receipts;")
    row = cursor.fetchone()
    last_sealed_seq = 0 if (row is None or row[0] is None) else row[0]

    cursor.execute(
        """
        SELECT sequence_id, entry_hash FROM state_ledger
        WHERE sequence_id > ?
        ORDER BY sequence_id ASC
        LIMIT ?;
        """,
        (last_sealed_seq, batch_size)
    )
    unsealed_entries = cursor.fetchall()

    if not unsealed_entries:
        return None

    start_seq = unsealed_entries[0][0]
    end_seq = unsealed_entries[-1][0]
    block_count = len(unsealed_entries)
    hashes = [entry[1] for entry in unsealed_entries]

    merkle_root = calculate_merkle_root(hashes)
    now = time.time()

    with conn:
        conn.execute(
            """
            INSERT INTO epoch_receipts (start_seq, end_seq, block_count, merkle_root, sealed_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (start_seq, end_seq, block_count, merkle_root, now)
        )

    return {
        "start_seq": start_seq,
        "end_seq": end_seq,
        "block_count": block_count,
        "merkle_root": merkle_root,
        "sealed_at": now
    }

if __name__ == "__main__":
    conn = get_connection("ledger.db")
    receipt = seal_latest_epoch(conn, batch_size=10)
    if receipt:
        print("=== MERKLE EPOCH RECEIPT SEALED ===")
        print(f"Sequence Range : {receipt["start_seq"]} -> {receipt["end_seq"]}")
        print(f"Blocks Rooted  : {receipt["block_count"]}")
        print(f"Merkle Root    : {receipt["merkle_root"]}")
        print("===================================")
    else:
        print("[INFO] No unsealed blocks available to seal.")
    conn.close()
