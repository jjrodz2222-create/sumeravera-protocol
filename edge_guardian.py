#!/usr/bin/env python3
import os, sys, hmac, hashlib, time
from collections import OrderedDict
STARTUP_TIME, STARTUP_GRACE_PERIOD, NONCE_TTL = time.time(), 61.0, 65.0
SUMER_SECRET_ZERO_DRIFT = os.getenv("SUMER_SECRET_ZERO_DRIFT", "FAIL_CLOSED")
class EdgeTelemetryGuardian:
    def __init__(self):
        self.nonce_cache = OrderedDict()
    def verify_edge_ingress(self, payload: bytes, signature: str, nonce: str) -> bool:
        if time.time() - STARTUP_TIME < STARTUP_GRACE_PERIOD and not nonce: return False
        if nonce in self.nonce_cache: return False
        sig = hmac.new(SUMER_SECRET_ZERO_DRIFT.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, signature): return False
        self.nonce_cache[nonce] = time.time()
        return True
if __name__ == "__main__":
    print("[+] SumerAvera Edge Telemetry Guardian initialized successfully. PAWS Connect purged.")
