#!/usr/bin/env python3
"""Tests for the HTTP-path lockdown: tightened POST /verify window
(65s past / 5s future, matching the edge guardian) and identity
screening (excluded-provider watchlist) on both ingress paths.

Run from the repo root:  python3 tests/test_watchlist.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only. The watchlist under test is
tests/data/watchlist_sample.txt -- SYNTHETIC test NPIs, not real
exclusions. The core verify path writes to the nonce store
(nonce_cache.db, gitignored); every test uses a fresh uuid nonce so
tests never collide with each other or with earlier runs.
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)
os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"
# The default watchlist must stay off for these tests unless a test
# sets it up explicitly: point it at a path that does not exist.
os.environ["SUMERAVERA_WATCHLIST_PATH"] = os.path.join(
    tempfile.gettempdir(), "sumeravera-no-such-watchlist.txt"
)

import gate1_ingress
import local_ledger
import watchlist
from watchlist import Watchlist, extract_provider_npi
from sumeravera_core import verify_ingress_packet

KEY = b"K" * 32
SAMPLE = os.path.join(ROOT, "tests", "data", "watchlist_sample.txt")
EXCLUDED_NPI = "1111111111"  # first entry of the synthetic sample list
LEGIT_NPI = "1000000099"  # not in the sample list


def _sig(nonce, ts, payload):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def _now():
    return time.time()


def _nonce(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def _claim(npi, claim_id="c1"):
    return json.dumps(
        {
            "claim_id": claim_id,
            "provider_npi": npi,
            "provider_name": "Test Clinic",
            "amount_usd": 100.0,
        },
        sort_keys=True,
    ).encode("utf-8")


def _gate(wl):
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    return gate1_ingress.Gate1(ledger_conn=conn, watchlist=wl), conn


def test_extract_provider_npi():
    assert extract_provider_npi(_claim("1234567890")) == "1234567890"
    assert extract_provider_npi(b'{"provider_npi": 1234567890}') == "1234567890"
    assert extract_provider_npi(b'{"provider_npi": "  1234567890  "}') == "1234567890"
    assert extract_provider_npi(b"not json") is None
    assert extract_provider_npi(b'{"amount_usd": 1}') is None
    assert extract_provider_npi(b'["a", "b"]') is None
    assert extract_provider_npi(b'{"provider_npi": null}') is None
    assert extract_provider_npi(b"") is None


def test_sample_list_loads():
    wl = Watchlist(SAMPLE)
    assert wl.enabled is True
    assert wl.is_excluded(EXCLUDED_NPI) is True
    assert wl.is_excluded(LEGIT_NPI) is False
    assert wl.is_excluded(None) is False
    assert wl.is_excluded("") is False


def test_missing_file_is_disabled_not_an_error():
    wl = Watchlist("/nonexistent/dir/no-such-watchlist.txt")
    assert wl.enabled is False
    assert wl.is_excluded(EXCLUDED_NPI) is False


def test_empty_file_is_disabled():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        path = fh.name
    try:
        wl = Watchlist(path)
        assert wl.enabled is False
        assert wl.is_excluded(EXCLUDED_NPI) is False
    finally:
        os.unlink(path)


def test_core_rejects_100s_old_packet():
    # The lockdown: POST /verify's window is now 65s past / 5s future.
    now = _now()
    old = now - 100
    nonce = _nonce("wl-old")
    payload = _claim(LEGIT_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, old, payload), nonce, old,
        watchlist=Watchlist.disabled(),
    ) is False


def test_core_rejects_future_packet():
    now = _now()
    fut = now + 10
    nonce = _nonce("wl-fut")
    payload = _claim(LEGIT_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, fut, payload), nonce, fut,
        watchlist=Watchlist.disabled(),
    ) is False


def test_core_accepts_fresh_packet_within_window():
    now = _now()
    nonce = _nonce("wl-fresh")
    payload = _claim(LEGIT_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, now, payload), nonce, now,
        watchlist=Watchlist.disabled(),
    ) is True


def test_core_rejects_excluded_npi():
    wl = Watchlist(SAMPLE)
    now = _now()
    nonce = _nonce("wl-excl")
    payload = _claim(EXCLUDED_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, now, payload), nonce, now, watchlist=wl
    ) is False


def test_core_accepts_legitimate_npi_with_list_loaded():
    wl = Watchlist(SAMPLE)
    now = _now()
    nonce = _nonce("wl-legit")
    payload = _claim(LEGIT_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, now, payload), nonce, now, watchlist=wl
    ) is True


def test_core_identity_rejection_does_not_consume_nonce():
    wl = Watchlist(SAMPLE)
    now = _now()
    nonce = _nonce("wl-nonce")
    payload = _claim(EXCLUDED_NPI)
    sig = _sig(nonce, now, payload)
    assert verify_ingress_packet(payload, sig, nonce, now, watchlist=wl) is False
    # Same packet, screening off: the nonce was never consumed, so it
    # verifies now (as if the provider had left the list).
    assert verify_ingress_packet(
        payload, sig, nonce, now, watchlist=Watchlist.disabled()
    ) is True


def test_core_non_json_payload_unaffected_by_list():
    wl = Watchlist(SAMPLE)
    now = _now()
    nonce = _nonce("wl-raw")
    payload = b'{"gate": 1}'
    assert verify_ingress_packet(
        payload, _sig(nonce, now, payload), nonce, now, watchlist=wl
    ) is True


def test_gate1_rejects_excluded_npi_without_ledger_entry():
    gate, conn = _gate(Watchlist(SAMPLE))
    now = _now()
    nonce = _nonce("wl-g1x")
    payload = _claim(EXCLUDED_NPI)
    r = gate.route(payload, _sig(nonce, now, payload), nonce, now)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    assert r["action"] == "ISOLATED" and r["reason"] == "identity_excluded"
    assert r["ledger_seq"] is None and r["ledger_hash"] is None
    cur = conn.execute("SELECT COUNT(*) FROM state_ledger")
    assert cur.fetchone()[0] == 0
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


def test_gate1_accepts_legitimate_npi_with_list_loaded():
    gate, conn = _gate(Watchlist(SAMPLE))
    now = _now()
    nonce = _nonce("wl-g1l")
    payload = _claim(LEGIT_NPI)
    r = gate.route(payload, _sig(nonce, now, payload), nonce, now)
    assert r["tier"] == "STABLE" and r["status_code"] == 200
    assert r["ledger_seq"] == 1
    conn.close()


def test_no_list_screening_off_both_paths():
    disabled = Watchlist.disabled()
    now = _now()
    nonce = _nonce("wl-off")
    payload = _claim(EXCLUDED_NPI)
    assert verify_ingress_packet(
        payload, _sig(nonce, now, payload), nonce, now, watchlist=disabled
    ) is True
    gate, conn = _gate(disabled)
    nonce2 = _nonce("wl-off2")
    r = gate.route(payload, _sig(nonce2, now, payload), nonce2, now)
    assert r["tier"] == "STABLE" and r["status_code"] == 200
    conn.close()


def test_default_watchlist_off_without_file():
    watchlist._reset_default_watchlist()
    try:
        wl = watchlist.get_default_watchlist()
        assert wl.enabled is False
        assert wl.is_excluded(EXCLUDED_NPI) is False
    finally:
        watchlist._reset_default_watchlist()


def test_default_watchlist_loads_from_env_path():
    os.environ["SUMERAVERA_WATCHLIST_PATH"] = SAMPLE
    watchlist._reset_default_watchlist()
    try:
        wl = watchlist.get_default_watchlist()
        assert wl.enabled is True
        assert wl.is_excluded(EXCLUDED_NPI) is True
    finally:
        os.environ["SUMERAVERA_WATCHLIST_PATH"] = os.path.join(
            tempfile.gettempdir(), "sumeravera-no-such-watchlist.txt"
        )
        watchlist._reset_default_watchlist()


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
