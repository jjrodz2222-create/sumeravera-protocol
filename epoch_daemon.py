import time
import sqlite3
from epoch_sealer import get_connection, seal_latest_epoch

def run_epoch_daemon(poll_interval: float = 2.0, batch_size: int = 10):
    print("=== SumerAvera Autonomous Epoch Daemon Active ===")
    print(f"Polling cadence: {poll_interval}s | Epoch threshold: {batch_size} blocks")
    while True:
        try:
            conn = get_connection("ledger.db")
            receipt = seal_latest_epoch(conn, batch_size=batch_size)
            if receipt:
                print(f"[SEALED] Epoch for seq {receipt['start_seq']}..{receipt['end_seq']} | Root: {receipt['merkle_root'][:16]}...")
                conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
            conn.close()
        except Exception as e:
            print(f"[WARN] Daemon sweep encountered: {e}")
        time.sleep(poll_interval)

if __name__ == "__main__":
    run_epoch_daemon()
