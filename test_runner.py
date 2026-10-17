import subprocess
import sys
import sqlite3
from protocol_gateway import get_connection, initialize_ledger, commit_ingress
from local_ledger import verify_chain_integrity

def run_tests():
    print("=== [1/3] Running TLA+ Model Checker ===")
    tla_cmd = ["java", "-cp", "tla2tools.jar", "tlc2.TLC", "SumerAvera.tla", "-config", "sumeravera.cfg", "-deadlock"]
    res = subprocess.run(tla_cmd, capture_output=True, text=True)
    if "Model checking completed. No error has been found." not in res.stdout:
        print("[FAIL] TLA+ formal verification failed.")
        sys.exit(1)
    print("[PASS] TLA+ Model Checker verified 0 errors.")

    print("\n=== [2/3] Testing Ingress Gate ===")
    conn = get_connection("ledger.db")
    initialize_ledger(conn)
    ok_valid, _ = commit_ingress(conn, {"source": "test_node", "event_type": "handshake", "data": {"step": 1}})
    ok_invalid, _ = commit_ingress(conn, {"unauthorized": True})
    if not (ok_valid and not ok_invalid):
        print("[FAIL] Ingress gate failed to validate schemas.")
        sys.exit(1)
    print("[PASS] Ingress gate correctly accepted valid and rejected invalid payloads.")

    print("\n=== [3/3] Auditing Ledger Cryptographic Invariants ===")
    if not verify_chain_integrity(conn):
        print("[FAIL] Ledger cryptographic integrity check failed.")
        sys.exit(1)
    print("[PASS] Local ledger hash chain intact and invariant.")
    conn.close()

    print("\n>>> ALL LOCAL INVARIANTS PASS: SYSTEM READY <<<")

if __name__ == "__main__":
    run_tests()
