#!/usr/bin/env python3
"""Tests for edge_guardian.py -- fail-closed ingress checks.

Run from the repo root:  python3 tests/test_edge_guardian.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only; nothing here touches the network
or the real secret. Module constants NONCE_TTL / MAX_NONCE_CACHE_SIZE are
shrunk inside individual tests and restored afterwards.
"""
import hashlib
import hmac
import math
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)
os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"

import edge_guardian as eg  # noqa: E402

KEY = b"K" * 32
PAYLOAD = b"hello"


def _sig_new(nonce, ts_str, payload=PAYLOAD):
    mac = hmac.new(KEY, digestmod=hashlib.sha256)
    mac.update(nonce.encode("utf-8"))
    mac.update(b":")
    mac.update(ts_str.encode("utf-8"))
    mac.update(b":")
    mac.update(payload)
    return mac.hexdigest()


def _sig_old(payload=PAYLOAD):
    return hmac.new(KEY, payload, hashlib.sha256).hexdigest()


def _now():
    return int(time.time())


def test_valid_int_timestamp():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n1", str(now)), "n1", now) is True


def test_valid_str_timestamp():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n2", str(now)), "n2", str(now)) is True


def test_float_timestamp_canonicalized_to_int_seconds():
    # Sender signs integer seconds; verifier receives a float. Must verify.
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n3", str(now)), "n3", float(now)) is True
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n4", str(now)), "n4", now + 0.7) is True


def test_stale_timestamp_rejected():
    g = eg.EdgeTelemetryGuardian()
    old = _now() - 600
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n5", str(old)), "n5", old) is False


def test_future_timestamp_rejected():
    g = eg.EdgeTelemetryGuardian()
    fut = _now() + 600
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n6", str(fut)), "n6", fut) is False


def test_future_timestamp_beyond_5s_rejected():
    # Asymmetric skew: more than 5s in the future is rejected.
    g = eg.EdgeTelemetryGuardian()
    fut = _now() + 10
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n6b", str(fut)), "n6b", fut) is False


def test_future_timestamp_within_5s_accepted():
    # A small future skew (clock drift) is still tolerated.
    g = eg.EdgeTelemetryGuardian()
    fut = _now() + 3
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n6c", str(fut)), "n6c", fut) is True


def test_old_payload_only_signature_rejected():
    g = eg.EdgeTelemetryGuardian()
    assert g.verify_edge_ingress(PAYLOAD, _sig_old(), "n7", _now()) is False


def test_inf_nan_timestamps_fail_closed():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    for bad in (math.inf, float("inf"), "inf", math.nan, float("nan"), "nan", "-inf"):
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("n8", str(now)), "n8", bad) is False


def test_bool_timestamps_rejected():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n9", str(now)), "n9", True) is False
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n9", str(now)), "n9", False) is False


def test_garbage_timestamp_rejected():
    g = eg.EdgeTelemetryGuardian()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n10", str(_now())), "n10", "not-a-time") is False


def test_bad_signature_does_not_consume_nonce():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, "00" * 32, "n11", now) is False
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n11", str(now)), "n11", now) is True


def test_replay_rejected():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n1", str(now)), "n1", now) is True
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("n1", str(now)), "n1", now) is False


def test_empty_nonce_rejected():
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("", str(now)), "", now) is False


def test_colon_nonce_rejected():
    # A correctly signed frame whose nonce contains ':' must still be
    # rejected: the ':' would make nonce:timestamp:payload ambiguous.
    g = eg.EdgeTelemetryGuardian()
    now = _now()
    assert g.verify_edge_ingress(PAYLOAD, _sig_new("a:b", str(now)), "a:b", now) is False
    assert "a:b" not in g.nonce_cache


def test_expired_nonce_pruned_after_ttl():
    old_ttl = eg.NONCE_TTL
    try:
        eg.NONCE_TTL = 0.05
        g = eg.EdgeTelemetryGuardian()
        now = _now()
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("n12", str(now)), "n12", now) is True
        time.sleep(0.1)
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("n12", str(now)), "n12", now) is True
    finally:
        eg.NONCE_TTL = old_ttl


def test_cap_saturation_fail_closed():
    # Old behavior evicted the oldest live nonce; hardened behavior rejects
    # new ingress instead of opening a replay window.
    old_cap = eg.MAX_NONCE_CACHE_SIZE
    try:
        eg.MAX_NONCE_CACHE_SIZE = 2
        g = eg.EdgeTelemetryGuardian()
        now = _now()
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("a", str(now)), "a", now) is True
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("b", str(now)), "b", now) is True
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("c", str(now)), "c", now) is False
        assert len(g.nonce_cache) == 2 and "a" in g.nonce_cache and "b" in g.nonce_cache
    finally:
        eg.MAX_NONCE_CACHE_SIZE = old_cap


def test_cap_saturation_allows_after_prune():
    # After pruning, expired entries free space, so new ingress is accepted.
    old_cap = eg.MAX_NONCE_CACHE_SIZE
    old_ttl = eg.NONCE_TTL
    try:
        eg.MAX_NONCE_CACHE_SIZE = 2
        eg.NONCE_TTL = 0.05
        g = eg.EdgeTelemetryGuardian()
        now = _now()
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("a", str(now)), "a", now) is True
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("b", str(now)), "b", now) is True
        time.sleep(0.1)
        assert g.verify_edge_ingress(PAYLOAD, _sig_new("c", str(now)), "c", now) is True
    finally:
        eg.MAX_NONCE_CACHE_SIZE = old_cap
        eg.NONCE_TTL = old_ttl


def _run_import_with_env(env_overrides):
    env = dict(os.environ)
    env.pop("SUMERAVERA_SECRET_KEY", None)
    env.pop("SUMER_SECRET_ZERO_DRIFT", None)
    env.pop("SUMER_ALLOW_LEGACY_SIG", None)
    env.update(env_overrides)
    code = "import sys; sys.path.insert(0, %r); import edge_guardian" % ROOT
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True)


def test_import_refuses_without_key():
    r = _run_import_with_env({})
    assert r.returncode != 0 and "RuntimeError" in r.stderr


def test_import_refuses_short_key():
    r = _run_import_with_env({"SUMERAVERA_SECRET_KEY": "short-key-123456"})
    assert r.returncode != 0 and "RuntimeError" in r.stderr


def test_import_accepts_long_key():
    r = _run_import_with_env({"SUMERAVERA_SECRET_KEY": "K" * 64})
    assert r.returncode == 0, r.stderr


def test_legacy_toggle_accepts_old_signature():
    env = dict(os.environ)
    env["SUMERAVERA_SECRET_KEY"] = "K" * 32
    env["SUMER_ALLOW_LEGACY_SIG"] = "1"
    code = (
        "import sys, hmac, hashlib, time; sys.path.insert(0, %r); "
        "import edge_guardian as eg; "
        "p = b'hello'; now = int(time.time()); "
        "old = hmac.new(b'K'*32, p, hashlib.sha256).hexdigest(); "
        "g = eg.EdgeTelemetryGuardian(); "
        "assert g.verify_edge_ingress(p, old, 'L1', now) is True"
        % ROOT
    )
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


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
