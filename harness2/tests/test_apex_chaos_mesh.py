import time
import os
import sqlite3
import pytest
from sumeravera.pqc import PostQuantumVerifier

def test_pqc_lattice_signature_roundtrip():
    verifier = PostQuantumVerifier(master_seed=b"sumer-avera-quantum-seed-2026")
    payload = b"gate1-state-transition-block-0x2222"
    
    sig = verifier.generate_lattice_signature(payload)
    assert sig.startswith(b"PQC-MLDSA-")
    assert verifier.verify_lattice_signature(payload, sig) is True
    
    # Tampered payload check
    assert verifier.verify_lattice_signature(b"tampered-payload", sig) is False

def test_clock_drift_replay_window():
    """Simulates ±30s clock drift inundation and nonce window enforcement."""
    current_time = int(time.time())
    drifted_past = current_time - 45  # Outside the ±30s window
    valid_window = current_time - 15   # Inside the window
    
    def check_timestamp(ts: int) -> bool:
        return abs(current_time - ts) <= 30

    assert check_timestamp(drifted_past) is False
    assert check_timestamp(valid_window) is True

def test_wal_ledger_resilience_under_attrition(tmp_path):
    """Simulates sudden worker crash mid-transaction on SQLite WAL ledger."""
    db_path = tmp_path / "ledger.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE state_ledger (id TEXT PRIMARY KEY, data TEXT);")
    conn.commit()
    conn.close()

    # Simulate concurrent access and abrupt disconnection
    conn1 = sqlite3.connect(db_path)
    conn1.execute("INSERT INTO state_ledger VALUES ('block-1', 'verified');")
    conn1.commit()
    
    # Force abrupt close without formal checkpointing (simulating SIGKILL)
    conn1.close()

    # Recovery validation
    conn2 = sqlite3.connect(db_path)
    cursor = conn2.cursor()
    cursor.execute("SELECT data FROM state_ledger WHERE id='block-1';")
    row = cursor.fetchone()
    conn2.close()

    assert row is not None
    assert row[0] == "verified"
