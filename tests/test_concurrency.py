#!/usr/bin/env python3
"""Tests for the per-thread SQLite connections and atomic ledger appends.

Run from the repo root:  python3 tests/test_concurrency.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only. Each test that touches on-disk
state runs inside its own temporary directory.

Covers the load-test fixes: per-thread connections for the nonce store and
the ledger (a sqlite3 connection is never shared across threads), WAL mode
on the nonce DB, atomic ledger sequence assignment under concurrency, and
the explicit WAL auto-checkpoint policy.
"""
import hashlib
import hmac
import os
import sqlite3
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="svp_concurrency_test_")
os.chdir(_TMP)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)
os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"
os.environ["SUMERAVERA_LEDGER_DB"] = os.path.join(_TMP, "ledger.db")

import gate1_ingress
import local_ledger
from sumeravera_core import (
    get_ledger_connection,
    verify_ingress_packet,
    _get_nonce_conn,
)

KEY = b"K" * 32
PAYLOAD = b'{"action": "state_update"}'


def _sig(nonce, ts, payload=PAYLOAD):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def _now():
    return time.time()


def _run_threads(n_threads, n_iters, fn, after=None):
    """Run fn(tid, i) from n_threads x n_iters; return per-thread results.
    after(tid) runs once per worker thread after its loop (teardown)."""
    results = [[] for _ in range(n_threads)]
    errors = []
    barrier = threading.Barrier(n_threads, timeout=30)

    def worker(tid):
        try:
            barrier.wait(timeout=30)
            for i in range(n_iters):
                results[tid].append(fn(tid, i))
            if after is not None:
                after(tid)
        except Exception as e:  # noqa: BLE001 - collected, asserted below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    return results


def test_nonce_db_is_wal_with_explicit_checkpoint():
    conn = _get_nonce_conn()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1000
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_ledger_connection_is_wal_with_explicit_checkpoint():
    path = os.path.join(tempfile.mkdtemp(prefix="svp_pragma_"), "ledger.db")
    conn = local_ledger.get_connection(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1000
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()


def test_get_ledger_connection_is_per_thread():
    main_conn = get_ledger_connection()
    assert get_ledger_connection() is main_conn  # same thread, same conn
    seen = []

    def worker():
        seen.append(get_ledger_connection())

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert len(seen) == 1
    assert seen[0] is not main_conn  # another thread, another conn


def test_gate1_rejects_both_ledger_forms():
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    try:
        gate1_ingress.Gate1(ledger_conn=conn, ledger_db_path="ledger.db")
    except ValueError:
        pass
    else:
        raise AssertionError("Gate1 accepted both ledger_conn and ledger_db_path")
    finally:
        conn.close()


def test_concurrent_verify_all_succeed_and_nonce_rows_match():
    tmp = tempfile.mkdtemp(prefix="svp_nonce_burst_")
    os.chdir(tmp)
    n_threads, n_iters = 8, 50

    def fn(tid, i):
        nonce = f"cc-n-{tid}-{i}"
        now = _now()
        return verify_ingress_packet(PAYLOAD, _sig(nonce, now), nonce, now)

    results = _run_threads(n_threads, n_iters, fn)
    flat = [r for per_thread in results for r in per_thread]
    assert len(flat) == n_threads * n_iters
    assert all(flat), "a concurrent verification failed"

    check = sqlite3.connect(os.path.join(tmp, "nonce_cache.db"))
    try:
        rows = check.execute("SELECT COUNT(*) FROM seen_nonces").fetchone()[0]
    finally:
        check.close()
    # Every verified packet recorded its nonce exactly once: no replay hole
    # (rows lost) and no false replays (rows recorded for failed ops).
    assert rows == n_threads * n_iters

    # A replay of one of those nonces is still rejected. Run it in a fresh
    # thread: the nonce store is one connection per thread, and the main
    # thread's connection may have been opened in another directory, so a
    # fresh thread opens the nonce DB in this test's directory.
    replayed = []

    def _replay():
        nonce = "cc-n-0-0"
        now = _now()
        replayed.append(
            verify_ingress_packet(PAYLOAD, _sig(nonce, now), nonce, now)
        )

    t = threading.Thread(target=_replay)
    t.start()
    t.join()
    assert replayed == [False]


def test_concurrent_ledger_appends_all_succeed_chain_valid():
    tmp = tempfile.mkdtemp(prefix="svp_ledger_burst_")
    path = os.path.join(tmp, "ledger.db")
    main_conn = local_ledger.get_connection(path)
    local_ledger.initialize_ledger(main_conn)
    main_conn.close()
    n_threads, n_iters = 8, 50

    def fn(tid, i):
        conn = local_ledger.get_connection(path)
        try:
            return local_ledger.append_state_entry(
                conn, {"event": "burst", "tid": tid, "i": i}
            )
        finally:
            conn.close()

    results = _run_threads(n_threads, n_iters, fn)
    seqs = sorted(seq for per_thread in results for seq, _h in per_thread)
    assert len(seqs) == n_threads * n_iters
    assert seqs == list(range(1, n_threads * n_iters + 1))

    check = local_ledger.get_connection(path)
    try:
        assert check.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0] == (
            n_threads * n_iters
        )
        assert local_ledger.verify_chain_integrity(check) is True
    finally:
        check.close()


def test_shared_gate1_with_ledger_path_all_threads_succeed():
    tmp = tempfile.mkdtemp(prefix="svp_gate1_burst_")
    path = os.path.join(tmp, "ledger.db")
    gate = gate1_ingress.Gate1(ledger_db_path=path)
    n_threads, n_iters = 8, 50

    def fn(tid, i):
        nonce = f"cc-g-{tid}-{i}"
        now = _now()
        return gate.route(PAYLOAD, _sig(nonce, now), nonce, now)

    results = _run_threads(n_threads, n_iters, fn, after=lambda tid: gate.close())
    flat = [r for per_thread in results for r in per_thread]
    assert len(flat) == n_threads * n_iters
    assert all(r["tier"] == "STABLE" and r["status_code"] == 200 for r in flat)
    assert all(r["ledger_seq"] for r in flat)
    seqs = sorted(r["ledger_seq"] for r in flat)
    assert seqs == list(range(1, n_threads * n_iters + 1))

    check = local_ledger.get_connection(path)
    try:
        assert check.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0] == (
            n_threads * n_iters
        )
        assert local_ledger.verify_chain_integrity(check) is True
    finally:
        check.close()

    # A quarantined packet from the shared gate still writes nothing.
    now = _now()
    bad = gate.route(PAYLOAD, "00" * 32, "cc-g-bad", now)
    assert bad["tier"] == "QUARANTINE" and bad["status_code"] == 403
    assert bad["ledger_seq"] is None
    gate.close()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    failures = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    sys.exit(1 if failures else 0)
