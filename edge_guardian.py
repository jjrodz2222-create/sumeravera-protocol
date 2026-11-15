#!/usr/bin/env python3
"""SumerAvera Edge Telemetry Guardian -- fail-closed ingress check.

FINAL REVISION (ready for repo integration).
Changes vs. public HEAD 0caf4dbb:
  1. No fallback secret: SUMERAVERA_SECRET_KEY (or legacy SUMER_SECRET_ZERO_DRIFT)
     must be set and >= 32 bytes. Refuses to start (RuntimeError) otherwise.
  2. Monotonic TTL enforcement: NONCE_TTL (65.0s) is enforced via time.monotonic()
     so NTP clock steps cannot stretch windows or prematurely evict nonces.
  3. Bounded O(1) cache: MAX_NONCE_CACHE_SIZE = 1_000_000 with FIFO eviction
     via OrderedDict.
  4. Dead grace-period logic removed: empty/missing nonces are rejected
     unconditionally across the entire process lifecycle.
  5. BREAKING SIGNATURE CHANGE: HMAC-SHA256 authenticates canonicalized
     `nonce:timestamp:payload` using integer Unix seconds (`int(timestamp)`),
     converging with sumeravera_core.py. Senders must sign integer Unix seconds.
     Set SUMER_ALLOW_LEGACY_SIG=1 temporarily during live emitter migration.
"""
import os
import hmac
import hashlib
import math
import time
from collections import OrderedDict

NONCE_TTL = 65.0
MAX_CLOCK_SKEW = 65.0
MAX_NONCE_CACHE_SIZE = 1_000_000
MIN_SECRET_BYTES = 32

_RAW_SECRET = os.getenv("SUMERAVERA_SECRET_KEY") or os.getenv("SUMER_SECRET_ZERO_DRIFT") or ""
_SECRET_BYTES = _RAW_SECRET.encode("utf-8")

if len(_SECRET_BYTES) < MIN_SECRET_BYTES:
    raise RuntimeError(
        f"Secret key must be at least {MIN_SECRET_BYTES} bytes "
        f"(got {len(_SECRET_BYTES)}). Refusing to start."
    )

_ALLOW_LEGACY_SIG = os.getenv("SUMER_ALLOW_LEGACY_SIG", "0") == "1"


class EdgeTelemetryGuardian:
    def __init__(self) -> None:
        self.nonce_cache: OrderedDict[str, float] = OrderedDict()

    def _prune_expired(self, now_mono: float) -> None:
        """Drop nonces older than NONCE_TTL (oldest first)."""
        cutoff = now_mono - NONCE_TTL
        while self.nonce_cache:
            _, ts = next(iter(self.nonce_cache.items()))
            if ts > cutoff:
                break
            self.nonce_cache.popitem(last=False)

    def _verify_mac(self, payload: bytes, signature: str, nonce: str, ts_str: str) -> bool:
        """Verify HMAC-SHA256 over nonce:timestamp:payload (with optional legacy fallback)."""
        mac = hmac.new(_SECRET_BYTES, digestmod=hashlib.sha256)
        mac.update(nonce.encode("utf-8"))
        mac.update(b":")
        mac.update(ts_str.encode("utf-8"))
        mac.update(b":")
        mac.update(payload)
        if hmac.compare_digest(mac.hexdigest(), signature):
            return True

        if _ALLOW_LEGACY_SIG:
            legacy_mac = hmac.new(_SECRET_BYTES, payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(legacy_mac, signature)

        return False

    def verify_edge_ingress(
        self,
        payload: bytes,
        signature: str,
        nonce: str,
        timestamp: str | int | float,
    ) -> bool:
        if (
            not isinstance(payload, (bytes, bytearray))
            or not isinstance(signature, str)
            or not isinstance(nonce, str)
            or not nonce
            or isinstance(timestamp, bool)
        ):
            return False

        # Canonicalize sender timestamp to integer Unix seconds (converging with core)
        try:
            ts_val = float(timestamp)
        except (TypeError, ValueError):
            return False

        if not math.isfinite(ts_val):
            return False

        ts_int = int(ts_val)
        ts_str = str(ts_int)

        if abs(time.time() - ts_int) > MAX_CLOCK_SKEW:
            return False

        # 1. Verify signature FIRST -- before reading or mutating nonce state.
        if not self._verify_mac(payload, signature, nonce, ts_str):
            return False

        # 2. Only a signature-verified packet reaches the replay check.
        now_mono = time.monotonic()
        self._prune_expired(now_mono)
        if nonce in self.nonce_cache:
            return False

        # 3. Record the nonce, enforcing the 1M O(1) FIFO bound.
        if len(self.nonce_cache) >= MAX_NONCE_CACHE_SIZE:
            self.nonce_cache.popitem(last=False)
        self.nonce_cache[nonce] = now_mono
        return True


if __name__ == "__main__":
    print("[+] SumerAvera Edge Telemetry Guardian initialized successfully. PAWS Connect purged.")
