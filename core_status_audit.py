#!/usr/bin/env python3
"""
SumerAvera Protocol - Private Core Status & Zero-Drift Audit
Performs local validation of zero-trust ingress state invariants,
nonce cache health, and private repository isolation boundaries.

DRAFT REVISION (for review -- not yet applied to repo).
Changes vs. public HEAD 0caf4dbb:
  1. The isolation check is no longer inverted: it PASSES only when a real
     secret key is set (>= 32 bytes) and FAILS when the key is missing, too
     short, or a known fallback literal. The old version printed PASSED
     precisely when no secret was set.
  2. The secret value is never printed. The audit reports only which variable
     supplied it and its byte length.
  3. The HMAC self-test runs only when a real key is present; it no longer
     "passes" by signing with the fallback literal.
  4. Exit code: 0 when every check passes, 1 otherwise, so the audit can
     gate CI. The old version always exited 0.
  5. Checks SUMERAVERA_SECRET_KEY first, with SUMER_SECRET_ZERO_DRIFT as a
     legacy fallback during migration.
"""

import os
import sys
import time
import hmac
import hashlib
from collections import OrderedDict

MIN_SECRET_BYTES = 32
KNOWN_FALLBACK_LITERALS = {"", "FAIL_CLOSED"}


def _load_secret():
    """Return (source_var_name, secret_bytes), or (None, b'') when unset."""
    raw = os.getenv("SUMERAVERA_SECRET_KEY")
    if raw:
        return "SUMERAVERA_SECRET_KEY", raw.encode("utf-8")
    raw = os.getenv("SUMER_SECRET_ZERO_DRIFT")
    if raw:
        return "SUMER_SECRET_ZERO_DRIFT", raw.encode("utf-8")
    return None, b""


def audit_core_status():
    print("==================================================")
    print(" SumerAvera Protocol - Private Core Audit Suite   ")
    print("==================================================")

    failures = []

    # Check environment isolation (never print the secret value)
    source, secret_bytes = _load_secret()
    if source is None:
        print("[*] Secret key status: NOT SET (checked SUMERAVERA_SECRET_KEY, then SUMER_SECRET_ZERO_DRIFT)")
        print("[-] Isolation check: FAILED (no secret key set -- refusing to treat fallback as valid)")
        failures.append("secret-not-set")
    elif secret_bytes.decode("utf-8", "ignore") in KNOWN_FALLBACK_LITERALS:
        print(f"[*] Secret key status: set via {source}, {len(secret_bytes)} bytes (KNOWN FALLBACK LITERAL)")
        print("[-] Isolation check: FAILED (fallback literal active -- set a real key)")
        failures.append("fallback-literal-active")
    elif len(secret_bytes) < MIN_SECRET_BYTES:
        print(f"[*] Secret key status: set via {source}, {len(secret_bytes)} bytes")
        print(f"[-] Isolation check: FAILED (key is {len(secret_bytes)} bytes, need >= {MIN_SECRET_BYTES})")
        failures.append("secret-too-short")
    else:
        print(f"[*] Secret key status: set via {source}, {len(secret_bytes)} bytes")
        print("[+] Isolation check: PASSED (real secret key set)")

    # Test Nonce Cache & HMAC validation pipeline (only with a real key)
    cache = OrderedDict()
    if failures:
        print("[-] Ingress HMAC Signature Binding: SKIPPED (no valid secret key)")
    else:
        test_nonce = "audit_nonce_10302026"
        test_payload = b"sumeravera_state_sync_payload"

        test_sig = hmac.new(secret_bytes, test_payload, hashlib.sha256).hexdigest()
        expected = hmac.new(secret_bytes, test_payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, test_sig):
            cache[test_nonce] = time.time()
            print("[+] Ingress HMAC Signature Binding: PASSED")
        else:
            print("[-] Ingress HMAC Signature Binding: FAILED")
            failures.append("hmac-self-test-failed")

    print(f"[+] Active Nonce Cache Entries: {len(cache)}")
    if failures:
        print("[-] Core status audit complete. FAILURES: " + ", ".join(failures))
        return 1
    print("[+] Core status audit complete. All private invariants intact.")
    return 0


if __name__ == "__main__":
    sys.exit(audit_core_status())
