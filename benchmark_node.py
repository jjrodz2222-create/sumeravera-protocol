import time
import os
import sqlite3
from protocol_lockdown import get_connection, initialize_lockdown_storage, process_ingress_secure

def run_empirical_benchmark(iterations=1000):
    db_file = "benchmark_ledger.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    conn = get_connection(db_file)
    initialize_lockdown_storage(conn)
    
    print(f"--- Running Empirical Benchmark ({iterations} Writes) ---")
    
    # 1. Measure Valid Ingress Latency
    t0 = time.perf_counter()
    for i in range(iterations):
        process_ingress_secure(conn, {
            "source": f"sensor_node_{i % 5}",
            "event_type": "telemetry",
            "data": {"voltage": 12.4 + (i % 10) * 0.1, "index": i}
        })
    t_valid = time.perf_counter() - t0
    
    # 2. Measure Malformed / Quarantine Latency
    t0_q = time.perf_counter()
    for i in range(iterations // 10):
        process_ingress_secure(conn, {"bad_payload_index": i})
    t_quarantine = time.perf_counter() - t0_q
    
    # 3. Measure Storage Footprint
    conn.commit()
    conn.close()
    
    db_size_bytes = os.path.getsize(db_file)
    wal_size_bytes = os.path.getsize(db_file + "-wal") if os.path.exists(db_file + "-wal") else 0
    total_bytes = db_size_bytes + wal_size_bytes
    
    avg_latency_ms = (t_valid / iterations) * 1000
    tps = iterations / t_valid
    bytes_per_entry = total_bytes / (iterations + (iterations // 10))
    
    print("\n=== VERIFIED HARDWARE METRICS ===")
    print(f"Hardware Platform       : Chromebook Linux Container")
    print(f"Transactions Processed  : {iterations} valid, {iterations // 10} quarantined")
    print(f"Mean Ingress Latency    : {avg_latency_ms:.3f} ms / write")
    print(f"Sustained Throughput    : {tps:.1f} writes / second (single-threaded)")
    print(f"Total Storage Overhead  : {total_bytes / 1024:.2f} KB")
    print(f"Storage Footprint       : {bytes_per_entry:.1f} bytes / recorded state")
    print("=================================")

if __name__ == "__main__":
    run_empirical_benchmark(1000)
