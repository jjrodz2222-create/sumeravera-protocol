#!/usr/bin/env python3
"""SumerAvera benchmark harness.

Measures, on the machine it runs on:

  1. Core ingress validation latency -- mean ms per verify_ingress_packet
     call and verifications/second.
  2. Edge guardian latency -- mean ms per EdgeTelemetryGuardian
     .verify_edge_ingress call.
  3. Ledger append throughput -- append_state_entry writes/second, plus
     storage density (bytes per recorded state) and on-disk footprint.
  4. Malformed-packet rejection rate -- bad signature, replay, and stale
     packets presented to the guardian; the fraction rejected.

Fail-closed: SUMERAVERA_SECRET_KEY must be set in the environment and be
>= 32 bytes, or the harness exits non-zero. All on-disk state (the nonce
store and the benchmark ledger) lives in a temporary directory, so a run
never writes into the repository.

Usage:
    python3 benchmark.py [--iterations N] [--json [path]]

With --json the results are also written as JSON (default path
benchmark_results.json in the current directory). The numbers printed are
the ones BENCHMARKS.md should quote, labelled with the run date and host.
"""

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import time

MIN_SECRET_BYTES = 32
DEFAULT_ITERATIONS = 2000
DEFAULT_LEDGER_ENTRIES = 1000


def _sign(secret, nonce, ts, payload):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def run_benchmark(iterations=DEFAULT_ITERATIONS):
    key = os.environ.get("SUMERAVERA_SECRET_KEY", "")
    if len(key.encode("utf-8")) < MIN_SECRET_BYTES:
        print(
            "[benchmark] SUMERAVERA_SECRET_KEY (>= 32 bytes) is required.",
            file=sys.stderr,
        )
        return None
    secret = key.encode("utf-8")

    tmp = tempfile.mkdtemp(prefix="svp_bench_")
    os.chdir(tmp)

    import edge_guardian as eg
    import local_ledger
    from sumeravera_core import verify_ingress_packet

    payload = b'{"benchmark": true, "metric": "latency"}'
    results = {}

    # 1. Core ingress validation latency.
    start = time.perf_counter()
    for i in range(iterations):
        ts = time.time()
        nonce = f"bench_core_{i}_{int(ts * 1000)}"
        assert verify_ingress_packet(
            payload, _sign(secret, nonce, ts, payload), nonce, ts
        )
    elapsed = time.perf_counter() - start
    results["core_ingress"] = {
        "iterations": iterations,
        "total_seconds": round(elapsed, 4),
        "mean_latency_ms": round((elapsed / iterations) * 1000, 3),
        "verifications_per_second": round(iterations / elapsed, 1),
    }

    # 2. Edge guardian latency.
    g = eg.EdgeTelemetryGuardian()
    start = time.perf_counter()
    for i in range(iterations):
        ts = time.time()
        nonce = f"bench_edge_{i}_{int(ts * 1000)}"
        assert g.verify_edge_ingress(
            payload, _sign(secret, nonce, ts, payload), nonce, ts
        )
    elapsed = time.perf_counter() - start
    results["edge_guardian"] = {
        "iterations": iterations,
        "total_seconds": round(elapsed, 4),
        "mean_latency_ms": round((elapsed / iterations) * 1000, 3),
        "verifications_per_second": round(iterations / elapsed, 1),
    }

    # 3. Ledger append throughput, density, footprint (file-backed ledger).
    db_path = os.path.join(tmp, "bench_ledger.db")
    conn = local_ledger.get_connection(db_path)
    local_ledger.initialize_ledger(conn)
    n_entries = DEFAULT_LEDGER_ENTRIES
    start = time.perf_counter()
    for i in range(n_entries):
        local_ledger.append_state_entry(
            conn, {"event": "benchmark", "i": i, "payload": "x" * 64}
        )
    elapsed = time.perf_counter() - start
    conn.close()
    db_bytes = sum(
        os.path.getsize(os.path.join(tmp, f))
        for f in os.listdir(tmp)
        if f.startswith("bench_ledger.db")
    )
    results["ledger"] = {
        "entries": n_entries,
        "total_seconds": round(elapsed, 4),
        "writes_per_second": round(n_entries / elapsed, 1),
        "bytes_per_state": round(db_bytes / n_entries, 1),
        "disk_footprint_bytes": db_bytes,
        "disk_footprint_kb": round(db_bytes / 1024, 2),
    }

    # 4. Malformed-packet rejection rate (guardian).
    g2 = eg.EdgeTelemetryGuardian()
    now = time.time()
    malformed = 0
    rejected = 0
    for i in range(100):
        malformed += 1
        if not g2.verify_edge_ingress(payload, "00" * 32, f"bad-{i}", now):
            rejected += 1
    for i in range(50):
        nonce = f"replay-{i}"
        sig = _sign(secret, nonce, now, payload)
        g2.verify_edge_ingress(payload, sig, nonce, now)
        malformed += 1
        if not g2.verify_edge_ingress(payload, sig, nonce, now):
            rejected += 1
    for i in range(50):
        old = now - 600
        malformed += 1
        if not g2.verify_edge_ingress(
            payload, _sign(secret, f"stale-{i}", old, payload), f"stale-{i}", old
        ):
            rejected += 1
    results["rejection"] = {
        "malformed_presented": malformed,
        "malformed_rejected": rejected,
        "rejection_rate_percent": round(100.0 * rejected / malformed, 2),
    }

    return results


def _print_results(results):
    c = results["core_ingress"]
    e = results["edge_guardian"]
    l = results["ledger"]
    r = results["rejection"]
    print("[*] SumerAvera benchmark results (this machine, this run)")
    print(f"  Core ingress validation : {c['mean_latency_ms']:.3f} ms/packet, "
          f"{c['verifications_per_second']:.1f} verifications/sec "
          f"({c['iterations']} iterations)")
    print(f"  Edge guardian           : {e['mean_latency_ms']:.3f} ms/packet, "
          f"{e['verifications_per_second']:.1f} verifications/sec "
          f"({e['iterations']} iterations)")
    print(f"  Ledger append           : {l['writes_per_second']:.1f} writes/sec, "
          f"{l['bytes_per_state']:.1f} bytes/state, "
          f"{l['disk_footprint_kb']:.2f} KB for {l['entries']} entries")
    print(f"  Malformed rejection     : {r['malformed_rejected']}/{r['malformed_presented']} "
          f"rejected ({r['rejection_rate_percent']:.2f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SumerAvera benchmark harness")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--json", nargs="?", const="benchmark_results.json",
                        default=None, help="also write results as JSON")
    args = parser.parse_args()
    res = run_benchmark(args.iterations)
    if res is None:
        sys.exit(1)
    _print_results(res)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
        print(f"[+] Results written to {args.json}")
