import sqlite3
import hashlib
import json
import time
from typing import Dict, Tuple

# Sanitized test variables
TEST_KEYS = {"key1", "key2", "key3"}

def get_connection(db_path: str = "test_db.sqlite") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_test_db(conn: sqlite3.Connection) -> None:
    with conn:
        # Generic test table structure
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generic_table (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL,
                link_a TEXT NOT NULL,
                link_b TEXT NOT NULL UNIQUE
            );
            """
        )
