#!/usr/bin/env python3
"""Tests for the ledger wiring in sumeravera_core.py.

Run from the repo root:  python3 tests/test_ledger_wiring.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only. Runs inside a temporary directory
so the nonce store (nonce_cache.db) never lands in the repository.
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Isolate on-disk state BEFORE importing sumeravera_core: it opens
# nonce_cache.db in the current directory at import time.
_TMP = tempfile.mkdtemp(prefix="svp_ledger_test_")
os.chdir(_TMP)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)

import local_ledger
from sumeravera_core import (
    get_ledger_connection,
    verify_ingress_packet,
    _record_verified_ingress,
)

KEY = b"K" * 32
PAYLOAD = b'{"action": "state_update"}'


def _sig(nonce, ts, payload=PAYLOAD):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def _now():
    return time.time()


def _mem_ledger():
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    return conn


def _row_count(conn):
    return conn.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0]


def test_verified_packet_appends_ledger_entry():
    conn = _mem_ledger()
    now = _now()
    nonce = f"lw-a-{int(now * 1000)}"
    assert verify_ingress_packet(
        PAYLOAD, _sig(nonce, now), nonce, now, ledger_conn=conn
    ) is True
    assert _row_count(conn) == 1
    row = conn.execute(
        "SELECT payload FROM state_ledger WHERE sequence_id = 1"
    ).fetchone()[0]
    assert json.loads(row)["nonce"] == nonce
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


def test_verified_packet_without_ledger_still_verifies():
    now = _now()
    nonce = f"lw-b-{int(now * 1000)}"
    assert verify_ingress_packet(PAYLOAD, _sig(nonce, now), nonce, now) is True


def test_rejected_packet_appends_nothing():
    conn = _mem_ledger()
    now = _now()
    assert verify_ingress_packet(
        PAYLOAD, "00" * 32, f"lw-c-{int(now * 1000)}", now, ledger_conn=conn
    ) is False
    assert _row_count(conn) == 0
    conn.close()


def test_replay_appends_nothing():
    conn = _mem_ledger()
    now = _now()
    nonce = f"lw-d-{int(now * 1000)}"
    assert verify_ingress_packet(
        PAYLOAD, _sig(nonce, now), nonce, now, ledger_conn=conn
    ) is True
    assert verify_ingress_packet(
        PAYLOAD, _sig(nonce, now), nonce, now, ledger_conn=conn
    ) is False
    assert _row_count(conn) == 1
    conn.close()


def test_chain_detects_tampering_after_wiring():
    conn = _mem_ledger()
    now = _now()
    for i in range(2):
        nonce = f"lw-e-{i}-{int(now * 1000)}"
        assert verify_ingress_packet(
            PAYLOAD, _sig(nonce, now), nonce, now, ledger_conn=conn
        ) is True
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.execute(
        "UPDATE state_ledger SET payload = ? WHERE sequence_id = 1",
        ('{"event": "tampered"}',),
    )
    conn.commit()
    assert local_ledger.verify_chain_integrity(conn) is False
    conn.close()


def test_ledger_connection_helper_records_entries():
    conn = get_ledger_connection()
    seq, entry_hash = _record_verified_ingress(
        conn, "lw-f-helper", _now(), None
    )
    assert seq == 1 and entry_hash
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
