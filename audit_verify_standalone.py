#!/usr/bin/env python3
"""Standalone invariant audit for the SumerAvera protocol repos.

Unlike the earlier version of this script, every check below exercises the
real modules (edge_guardian, sumeravera_core, local_ledger, gate1_ingress)
instead of recomputing a signature and comparing it with itself. Nothing
here asserts an arithmetic tautology.

Checks:
  1. Bad signature rejected by the edge guardian.
  2. Replay rejected by the edge guardian (same nonce twice).
  3. Stale timestamp rejected by the edge guardian (> 65s old).
  4. sumeravera_core.verify_ingress_packet: valid packet accepted, replay
     rejected, stale timestamp rejected, bad signature rejected, and a bad
     signature does not consume the nonce (retry with the good signature
     still verifies).
  5. Ledger: three appended entries verify; tampering with one entry is
     detected by verify_chain_integrity.
  6. Gate 1: fresh valid packet -> STABLE (200) with a ledger entry;
     drifted valid packet -> REBALANCING (202); bad signature ->
     QUARANTINE (403) with no ledger entry.

Fail-closed: SUMERAVERA_SECRET_KEY must be set in the environment and be
>= 32 bytes, or the audit exits non-zero before any check runs. The audit
runs inside a temporary directory so the nonce store (nonce_cache.db) and
any ledger files it creates never land in the repository.

Usage: python3 audit_verify_standalone.py [scope-label]
The scope label (default "proof_re") is only printed; it selects nothing.
"""

import hashlib
import hmac
import os
import sys
import tempfile
import time

MIN_SECRET_BYTES = 32

_failures = []


def _check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if not condition:
        _failures.append(name)
    return condition


def _sign(secret, nonce, ts, payload):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def audit_zero_trust_invariants(target_dir="proof_re"):
    print(f"[*] Auditing target verification directory/scope: {target_dir}")

    key = os.environ.get("SUMERAVERA_SECRET_KEY", "")
    if len(key.encode("utf-8")) < MIN_SECRET_BYTES:
        print(
            "[FAIL] SUMERAVERA_SECRET_KEY must be set and >= 32 bytes. "
            "The audit refuses to run without a provisioned key.",
            file=sys.stderr,
        )
        return 1
    secret = key.encode("utf-8")

    # All on-disk state (nonce store, ledger files) lives in a temp dir.
    tmp = tempfile.mkdtemp(prefix="svp_audit_")
    os.chdir(tmp)

    # Imports happen after the key check: both modules fail closed at
    # import time without a provisioned key.
    import edge_guardian as eg
    import gate1_ingress
    import local_ledger
    from sumeravera_core import verify_ingress_packet

    payload = b'{"state": "InvariantLocked", "action": "audit_probe"}'
    now = time.time()

    # 1-3. Edge guardian: bad signature, replay, stale timestamp.
    g = eg.EdgeTelemetryGuardian()
    _check(
        "Edge guardian rejects a bad signature",
        g.verify_edge_ingress(payload, "00" * 32, "audit-bad", now) is False,
    )
    _check(
        "Edge guardian accepts a valid frame, then rejects its replay",
        g.verify_edge_ingress(
            payload, _sign(secret, "audit-replay", now, payload), "audit-replay", now
        )
        is True
        and g.verify_edge_ingress(
            payload, _sign(secret, "audit-replay", now, payload), "audit-replay", now
        )
        is False,
    )
    old = now - 600
    _check(
        "Edge guardian rejects a stale (> 65s) timestamp",
        g.verify_edge_ingress(
            payload, _sign(secret, "audit-stale", old, payload), "audit-stale", old
        )
        is False,
    )

    # 4. Core verify path: valid, replay, stale, bad signature, and a bad
    # signature must not consume the nonce.
    n1 = f"audit-core-{int(now * 1000)}"
    _check(
        "Core verifies a valid packet",
        verify_ingress_packet(payload, _sign(secret, n1, now, payload), n1, now)
        is True,
    )
    _check(
        "Core rejects a replay of the same packet",
        verify_ingress_packet(payload, _sign(secret, n1, now, payload), n1, now)
        is False,
    )
    n2 = f"audit-core-stale-{int(now)}"
    old_ts = now - 301
    _check(
        "Core rejects a stale (> 300s) packet",
        verify_ingress_packet(
            payload, _sign(secret, n2, old_ts, payload), n2, old_ts
        )
        is False,
    )
    n3 = f"audit-core-bad-{int(now * 1000)}"
    _check(
        "Core rejects a bad signature and does not consume the nonce",
        verify_ingress_packet(payload, "00" * 32, n3, now) is False
        and verify_ingress_packet(
            payload, _sign(secret, n3, now, payload), n3, now
        )
        is True,
    )

    # 5. Ledger: appends verify; tampering is detected.
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    for i in range(3):
        local_ledger.append_state_entry(conn, {"event": "audit", "i": i})
    _check(
        "Ledger chain verifies after three appends",
        local_ledger.verify_chain_integrity(conn) is True,
    )
    conn.execute(
        "UPDATE state_ledger SET payload = ? WHERE sequence_id = 2",
        ('{"event": "tampered"}',),
    )
    conn.commit()
    _check(
        "Ledger detects a tampered entry",
        local_ledger.verify_chain_integrity(conn) is False,
    )
    conn.close()

    # 6. Gate 1 tiers, with a ledger.
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    gate = gate1_ingress.Gate1(ledger_conn=conn)
    fresh = gate.route(
        payload, _sign(secret, "audit-g1-fresh", now, payload), "audit-g1-fresh", now
    )
    _check(
        "Gate 1 routes a fresh valid packet to STABLE (200) with a ledger entry",
        fresh["tier"] == "STABLE"
        and fresh["status_code"] == 200
        and fresh["ledger_seq"] == 1,
    )
    drifted_ts = now - 30
    drifted = gate.route(
        payload,
        _sign(secret, "audit-g1-old", drifted_ts, payload),
        "audit-g1-old",
        drifted_ts,
    )
    _check(
        "Gate 1 routes a drifted valid packet to REBALANCING (202)",
        drifted["tier"] == "REBALANCING" and drifted["status_code"] == 202,
    )
    bad = gate.route(payload, "00" * 32, "audit-g1-bad", now)
    _check(
        "Gate 1 routes a bad signature to QUARANTINE (403) with no ledger entry",
        bad["tier"] == "QUARANTINE"
        and bad["status_code"] == 403
        and bad["ledger_seq"] is None,
    )
    _check(
        "Gate 1 ledger chain verifies (2 accepted entries)",
        local_ledger.verify_chain_integrity(conn) is True,
    )
    conn.close()

    if _failures:
        print(
            f"[FAIL] {len(_failures)} invariant check(s) failed: "
            f"{', '.join(_failures)}"
        )
        return 1
    print(
        "[SUCCESS] All protocol zero-trust invariants verified against "
        "the real modules."
    )
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "proof_re"
    sys.exit(audit_zero_trust_invariants(target))
