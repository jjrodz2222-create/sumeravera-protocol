#!/usr/bin/env python3
"""SumerAvera Gate 1 -- minimal deterministic ingress gate.

Gate 1 is the first (and only) ingress gate in the protocol repos. It is
built from the repos' own primitives only:

  * edge_guardian.EdgeTelemetryGuardian -- HMAC-SHA256 verification over the
    canonical ``nonce:timestamp:payload`` frame, replay rejection, 65s past /
    5s future skew bounds, fail-closed without a provisioned secret.
  * local_ledger -- SQLite hash-chained state ledger (append_state_entry /
    verify_chain_integrity).

Three-tier routing (status codes mirror the console's historical tiers):

  * STABLE (200)      -- verified and fresh (timestamp within 5s of now).
                        Accepted as canonical; appended to the ledger.
  * REBALANCING (202) -- verified but drifted (5s < age <= 65s, the
                        guardian's past-skew bound). Accepted for
                        deterministic ordering; appended to the ledger.
  * QUARANTINE (403)  -- guardian rejected the frame (bad signature,
                        replay, stale/future timestamp, bad nonce).
                        Isolated: nothing is written to the state ledger,
                        so a rejected payload can never pollute it.

Deliberately NOT included: the AI Studio console app's SettlementEngine,
trust vault, and 5% extraction. Those belong to the console demo, not to
the protocol repos.

The gate fails closed: importing edge_guardian requires
SUMERAVERA_SECRET_KEY (or legacy SUMER_SECRET_ZERO_DRIFT) to be set and
>= 32 bytes, so this module refuses to load without a provisioned key.

Threading: a single Gate1 may be shared across worker threads when
constructed with ledger_db_path (one ledger connection per calling
thread); a ledger_conn is only safe from the thread that created it,
because a sqlite3 connection must never be shared across threads.
"""

import sqlite3
import threading
import time
from typing import Optional

from edge_guardian import EdgeTelemetryGuardian
from local_ledger import append_state_entry, get_connection, initialize_ledger

# A verified packet whose timestamp is this fresh is canonical.
STABLE_DRIFT_SECONDS = 5.0

# The guardian's past-skew bound. A verified packet older than this cannot
# exist (the guardian rejects it), so REBALANCING spans (5s, 65s].
MAX_DRIFT_SECONDS = 65.0


class Gate1:
    """Minimal Gate 1: verify, route, and (for accepted packets) record.

    Ledger recording takes one of two forms:

      * ``ledger_conn`` -- a caller-owned sqlite3 connection. The caller
        must only use it from the thread that created it (a sqlite3
        connection must never be shared across threads). Kept for
        single-threaded callers and tests.
      * ``ledger_db_path`` -- the gate opens one ledger connection per
        calling thread, lazily, so a single Gate1 can be shared across
        worker threads. This is the form a threaded server should use.
        Must be a file path, not ":memory:" (each thread would get its
        own separate in-memory database).

    Pass one or the other, not both. When neither is given, the gate
    verifies and routes but records nothing.
    """

    def __init__(
        self,
        guardian: Optional[EdgeTelemetryGuardian] = None,
        ledger_conn=None,
        ledger_db_path: Optional[str] = None,
    ) -> None:
        if ledger_conn is not None and ledger_db_path is not None:
            raise ValueError("pass ledger_conn or ledger_db_path, not both")
        self.guardian = guardian or EdgeTelemetryGuardian()
        self.ledger_conn = ledger_conn
        self.ledger_db_path = ledger_db_path
        self._ledger_local = threading.local()

    def _ledger_connection(self):
        """Return the connection route() should record on, or None."""
        if self.ledger_conn is not None:
            return self.ledger_conn
        if self.ledger_db_path is None:
            return None
        conn = getattr(self._ledger_local, "conn", None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                conn = None
        if conn is None:
            conn = get_connection(self.ledger_db_path)
            initialize_ledger(conn)
            self._ledger_local.conn = conn
        return conn

    def close(self) -> None:
        """Close the calling thread's ledger connection, if the gate opened
        one (ledger_db_path form). A no-op otherwise."""
        conn = getattr(self._ledger_local, "conn", None)
        if conn is not None:
            conn.close()
            del self._ledger_local.conn

    def route(
        self,
        payload: bytes,
        signature: str,
        nonce: str,
        timestamp,
    ) -> dict:
        """Verify one ingress frame and return its routing decision.

        Returns a dict with keys: tier, status_code, action, reason, nonce,
        drift_ms (None when quarantined), ledger_seq and ledger_hash
        (None when quarantined or when no ledger connection was given).
        """
        verified = self.guardian.verify_edge_ingress(
            payload, signature, nonce, timestamp
        )
        if not verified:
            return {
                "tier": "QUARANTINE",
                "status_code": 403,
                "action": "ISOLATED",
                "reason": "verification_failed",
                "nonce": nonce,
                "drift_ms": None,
                "ledger_seq": None,
                "ledger_hash": None,
            }

        # Verified: the timestamp is a finite number the guardian accepted.
        drift_s = time.time() - float(timestamp)
        if drift_s <= STABLE_DRIFT_SECONDS:
            tier, status_code, action = "STABLE", 200, "ACCEPTED_CANONICAL"
        else:
            tier, status_code, action = "REBALANCING", 202, "AUTO_STAGED"

        ledger_seq = None
        ledger_hash = None
        ledger_conn = self._ledger_connection()
        if ledger_conn is not None:
            ledger_seq, ledger_hash = append_state_entry(
                ledger_conn,
                {
                    "event": "gate1_ingress",
                    "tier": tier,
                    "nonce": nonce,
                    "drift_ms": round(drift_s * 1000, 3),
                },
            )

        return {
            "tier": tier,
            "status_code": status_code,
            "action": action,
            "reason": "verified",
            "nonce": nonce,
            "drift_ms": round(drift_s * 1000, 3),
            "ledger_seq": ledger_seq,
            "ledger_hash": ledger_hash,
        }


if __name__ == "__main__":
    # Smoke check: requires SUMERAVERA_SECRET_KEY in the environment.
    # Uses an in-memory ledger; writes nothing to disk.
    import hashlib
    import hmac
    import os
    import sqlite3
    import sys

    from local_ledger import get_connection, initialize_ledger, verify_chain_integrity

    key = os.environ.get("SUMERAVERA_SECRET_KEY") or os.environ.get(
        "SUMER_SECRET_ZERO_DRIFT", ""
    )
    if len(key.encode("utf-8")) < 32:
        print("[GATE1] SUMERAVERA_SECRET_KEY (>= 32 bytes) is required.", file=sys.stderr)
        sys.exit(1)

    secret = key.encode("utf-8")
    conn = get_connection(":memory:")
    initialize_ledger(conn)
    gate = Gate1(ledger_conn=conn)

    def _sign(nonce, ts, payload):
        msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()

    payload = b'{"gate": 1, "smoke": true}'
    now = time.time()
    fresh = gate.route(payload, _sign("g1-fresh", now, payload), "g1-fresh", now)
    print(f"fresh packet   -> {fresh['tier']} {fresh['status_code']} ledger_seq={fresh['ledger_seq']}")
    bad = gate.route(payload, "00" * 32, "g1-bad", now)
    print(f"bad signature  -> {bad['tier']} {bad['status_code']} ledger_seq={bad['ledger_seq']}")
    old = now - 30
    drifted = gate.route(payload, _sign("g1-old", old, payload), "g1-old", old)
    print(f"30s-old packet -> {drifted['tier']} {drifted['status_code']} ledger_seq={drifted['ledger_seq']}")
    print(f"ledger chain valid: {verify_chain_integrity(conn)}")
    conn.close()
