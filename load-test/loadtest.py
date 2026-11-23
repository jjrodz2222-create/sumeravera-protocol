#!/usr/bin/env python3
"""Concurrent-writer load test for the fixed SumerAvera public-repo code.

TEST-ONLY. Reads code from --tree, never modifies it. Uses a throwaway
32-byte test key via env var only. All databases live under --workdir
(a fresh temp dir per run, deleted by the driver).

Modes:
  gate1-shared     One Gate1 constructed with ledger_db_path, shared across
                   N threads -- each calling thread gets its own ledger
                   connection (the fixed code). The old form (one shared
                   ledger connection) is obsolete: no shared-connection API
                   remains in the gate path.
  gate1-perthread  Each thread opens its own ledger connection to the same
                   file DB + its own Gate1 (own guardian).
  core-nonce       sumeravera_core.verify_ingress_packet(ledger_conn=None)
                   -- the per-thread nonce connection (WAL mode, bounded
                   retry on busy), N threads.
  ledger-only      Direct local_ledger.append_state_entry, per-thread
                   connections to the same file DB -- isolates ledger appends.

Usage:
  python load-test/loadtest.py --mode gate1-perthread --threads 8 --iters 500 \
      --workdir /tmp/svp-load-XXX --tree .

Prints one JSON line to stdout with the run's measurements.
"""
import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import threading
import time

KEY = b"K" * 32
PAYLOAD = b'{"load": "test"}'


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def summarize(latencies):
    s = sorted(latencies)
    return {
        "count": len(s),
        "mean_ms": (sum(s) / len(s) * 1000) if s else None,
        "min_ms": (s[0] * 1000) if s else None,
        "max_ms": (s[-1] * 1000) if s else None,
        "p50_ms": (percentile(s, 50) * 1000) if s else None,
        "p95_ms": (percentile(s, 95) * 1000) if s else None,
        "p99_ms": (percentile(s, 99) * 1000) if s else None,
    }


def sign(nonce, ts):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + PAYLOAD
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def file_sizes(path):
    out = {}
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        out["db" + suffix if suffix else "db"] = (
            os.path.getsize(p) if os.path.exists(p) else 0
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=[
        "gate1-shared", "gate1-perthread", "core-nonce", "ledger-only"])
    ap.add_argument("--threads", type=int, required=True)
    ap.add_argument("--iters", type=int, required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--tree", required=True)
    args = ap.parse_args()

    os.chdir(args.workdir)
    os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
    os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"
    os.environ["SUMERAVERA_LEDGER_DB"] = os.path.join(args.workdir, "ledger.db")
    sys.path.insert(0, args.tree)

    ledger_db = os.path.join(args.workdir, "ledger.db")
    nonce_db = os.path.join(args.workdir, "nonce_cache.db")

    # Import per mode (importing sumeravera_core creates nonce_cache.db in CWD).
    if args.mode in ("gate1-shared", "gate1-perthread"):
        import gate1_ingress
        import local_ledger
    elif args.mode == "core-nonce":
        import sumeravera_core
    elif args.mode == "ledger-only":
        import local_ledger

    nthreads = args.threads
    iters = args.iters
    barrier = threading.Barrier(nthreads, timeout=30)
    latencies = []
    err_latencies_all = []
    lat_lock = threading.Lock()
    errors = {}
    err_lock = threading.Lock()
    outcomes = {}
    out_lock = threading.Lock()
    conns = []  # per-thread connections to close after measurement

    def note_error(exc):
        name = type(exc).__name__
        with err_lock:
            entry = errors.setdefault(name, {"count": 0, "example": str(exc)[:200]})
            entry["count"] += 1

    def note_outcome(key):
        with out_lock:
            outcomes[key] = outcomes.get(key, 0) + 1

    def worker(tid):
        local_lat = []
        local_err = []
        try:
            if args.mode == "gate1-shared":
                gate = SHARED["gate"]
            elif args.mode == "gate1-perthread":
                conn = local_ledger.get_connection(ledger_db)
                local_ledger.initialize_ledger(conn)
                conns.append(conn)
                gate = gate1_ingress.Gate1(ledger_conn=conn)
            elif args.mode == "ledger-only":
                conn = local_ledger.get_connection(ledger_db)
                local_ledger.initialize_ledger(conn)
                conns.append(conn)
            barrier.wait()
            for i in range(iters):
                nonce = f"t{tid}-{i}"
                ts = time.time()
                t0 = time.perf_counter()
                try:
                    if args.mode in ("gate1-shared", "gate1-perthread"):
                        r = gate.route(PAYLOAD, sign(nonce, ts), nonce, ts)
                        note_outcome(r["tier"])
                        ok = r["status_code"] in (200, 202)
                    elif args.mode == "core-nonce":
                        ok = sumeravera_core.verify_ingress_packet(
                            PAYLOAD, sign(nonce, ts), nonce, ts)
                        note_outcome("verified" if ok else "rejected")
                    elif args.mode == "ledger-only":
                        seq, _h = local_ledger.append_state_entry(conn, {
                            "event": "load_test", "nonce": nonce})
                        note_outcome("appended")
                        ok = True
                    if not ok:
                        note_outcome("unexpected_reject")
                        local_err.append(time.perf_counter() - t0)
                    else:
                        local_lat.append(time.perf_counter() - t0)
                except Exception as e:  # noqa: BLE001 - counted, run continues
                    note_error(e)
                    local_err.append(time.perf_counter() - t0)
            if args.mode == "gate1-shared":
                # Close this thread's ledger connection inside the gate.
                gate.close()
            elif args.mode in ("gate1-perthread", "ledger-only"):
                # Close this thread's own connection here, in its owning
                # thread: closing it later from the main thread would raise
                # (thread affinity) and silently leak the connection.
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001 - setup failure (e.g. barrier)
            note_error(e)
        with lat_lock:
            latencies.extend(local_lat)
            err_latencies_all.extend(local_err)

    SHARED = {}
    if args.mode == "gate1-shared":
        # Initialize the schema once in the main thread, then share one
        # Gate1 (ledger_db_path form: one ledger connection per calling
        # thread) across the workers.
        init_conn = local_ledger.get_connection(ledger_db)
        local_ledger.initialize_ledger(init_conn)
        init_conn.close()
        SHARED["gate"] = gate1_ingress.Gate1(ledger_db_path=ledger_db)
    elif args.mode in ("gate1-perthread", "ledger-only"):
        # Initialize the schema once up front so 16-32 workers do not race
        # on first-use schema creation; workers still open their own
        # connections (initialize_ledger is idempotent).
        init_conn = local_ledger.get_connection(ledger_db)
        local_ledger.initialize_ledger(init_conn)
        init_conn.close()

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(nthreads)]
    t_start = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wall = time.perf_counter() - t_start

    total_attempts = nthreads * iters
    total_errors = sum(v["count"] for v in errors.values())
    success = total_attempts - total_errors - outcomes.get("unexpected_reject", 0)
    # For gate modes, "success" means a STABLE/REBALANCING route; count from tiers.
    if args.mode in ("gate1-shared", "gate1-perthread"):
        success = outcomes.get("STABLE", 0) + outcomes.get("REBALANCING", 0)
    elif args.mode == "core-nonce":
        success = outcomes.get("verified", 0)
    elif args.mode == "ledger-only":
        success = outcomes.get("appended", 0)

    result = {
        "mode": args.mode,
        "threads": nthreads,
        "iters_per_thread": iters,
        "attempts": total_attempts,
        "success": success,
        "errors": errors,
        "outcomes": outcomes,
        "wall_s": round(wall, 3),
        "throughput_per_s": round(success / wall, 1) if wall > 0 else None,
        "latency": summarize(latencies),
        "error_latency": summarize(err_latencies_all),
        "cpus": os.cpu_count(),
        "python": sys.version.split()[0],
    }

    # Post-run checks: ledger chain validity + row counts + file sizes.
    if args.mode in ("gate1-shared", "gate1-perthread", "ledger-only"):
        sizes_before_close = file_sizes(ledger_db)
        result["ledger_files_before_close"] = sizes_before_close
        check_conn = sqlite3.connect(ledger_db)
        try:
            rowcount = check_conn.execute(
                "SELECT COUNT(*) FROM state_ledger").fetchone()[0]
            import local_ledger as _ll
            result["ledger_rows"] = rowcount
            result["chain_valid"] = _ll.verify_chain_integrity(check_conn)
        except Exception as e:  # noqa: BLE001
            result["ledger_rows"] = None
            result["chain_valid"] = False
            result["chain_check_error"] = f"{type(e).__name__}: {e}"
        finally:
            check_conn.close()
        for c in conns:
            try:
                c.close()
            except Exception:
                pass
        result["ledger_files_after_close"] = file_sizes(ledger_db)
    elif args.mode == "core-nonce":
        try:
            check = sqlite3.connect(nonce_db)
            try:
                n = check.execute("SELECT COUNT(*) FROM seen_nonces").fetchone()[0]
            finally:
                check.close()
            result["nonce_rows"] = n
            result["nonce_expected"] = success
        except Exception as e:  # noqa: BLE001
            result["nonce_rows"] = None
            result["nonce_check_error"] = f"{type(e).__name__}: {e}"
        result["nonce_files"] = file_sizes(nonce_db)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
