#!/usr/bin/env python3
"""Tests for gate1_ingress.py -- three-tier routing.

Run from the repo root:  python3 tests/test_gate1.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only; the ledger is in-memory, so no
files are written.
"""
import hashlib
import hmac
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)
os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"

import gate1_ingress
import local_ledger

KEY = b"K" * 32
PAYLOAD = b'{"gate": 1}'


def _sig(nonce, ts, payload=PAYLOAD):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def _now():
    return time.time()


def _gate():
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    return gate1_ingress.Gate1(ledger_conn=conn), conn


def test_fresh_valid_is_stable_with_ledger_entry():
    gate, conn = _gate()
    now = _now()
    r = gate.route(PAYLOAD, _sig("g1-a", now), "g1-a", now)
    assert r["tier"] == "STABLE" and r["status_code"] == 200
    assert r["action"] == "ACCEPTED_CANONICAL"
    assert r["ledger_seq"] == 1 and r["ledger_hash"]
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


def test_drifted_valid_is_rebalancing():
    gate, conn = _gate()
    old = _now() - 30
    r = gate.route(PAYLOAD, _sig("g1-b", old), "g1-b", old)
    assert r["tier"] == "REBALANCING" and r["status_code"] == 202
    assert r["action"] == "AUTO_STAGED"
    assert r["ledger_seq"] == 1
    conn.close()


def test_bad_signature_is_quarantine_without_ledger_entry():
    gate, conn = _gate()
    now = _now()
    r = gate.route(PAYLOAD, "00" * 32, "g1-c", now)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    assert r["action"] == "ISOLATED"
    assert r["ledger_seq"] is None and r["ledger_hash"] is None
    cur = conn.execute("SELECT COUNT(*) FROM state_ledger")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_replay_is_quarantine():
    gate, conn = _gate()
    now = _now()
    assert gate.route(PAYLOAD, _sig("g1-d", now), "g1-d", now)["tier"] == "STABLE"
    r = gate.route(PAYLOAD, _sig("g1-d", now), "g1-d", now)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    conn.close()


def test_stale_is_quarantine():
    gate, conn = _gate()
    old = _now() - 600
    r = gate.route(PAYLOAD, _sig("g1-e", old), "g1-e", old)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    conn.close()


def test_future_is_quarantine():
    gate, conn = _gate()
    fut = _now() + 600
    r = gate.route(PAYLOAD, _sig("g1-f", fut), "g1-f", fut)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    conn.close()


def test_empty_nonce_is_quarantine():
    gate, conn = _gate()
    now = _now()
    r = gate.route(PAYLOAD, _sig("", now), "", now)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    conn.close()


def test_no_ledger_conn_still_routes():
    gate = gate1_ingress.Gate1()
    now = _now()
    r = gate.route(PAYLOAD, _sig("g1-g", now), "g1-g", now)
    assert r["tier"] == "STABLE" and r["status_code"] == 200
    assert r["ledger_seq"] is None and r["ledger_hash"] is None


def test_chain_valid_after_accepted_entries():
    gate, conn = _gate()
    now = _now()
    gate.route(PAYLOAD, _sig("g1-h1", now), "g1-h1", now)
    gate.route(PAYLOAD, _sig("g1-h2", now - 30), "g1-h2", now - 30)
    gate.route(PAYLOAD, "00" * 32, "g1-h3", now)
    cur = conn.execute("SELECT COUNT(*) FROM state_ledger")
    assert cur.fetchone()[0] == 2
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


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
