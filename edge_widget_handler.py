#!/usr/bin/env python3
import os, sys, time, hashlib, hmac
from collections import OrderedDict
STARTUP_TIME, STARTUP_GRACE_PERIOD, NONCE_TTL = time.time(), 61.0, 65.0
SUMER_SECRET_ZERO_DRIFT = os.getenv("SUMER_SECRET_ZERO_DRIFT", "FAIL_CLOSED")
class ProtocolEdgeWidgetHandler:
    def __init__(self):
        self.nonce_cache = OrderedDict()
    def render_edge_telemetry_payload(self, state_metric: str, signature: str, nonce: str) -> bool:
        if time.time() - STARTUP_TIME < STARTUP_GRACE_PERIOD and not nonce: return False
        if nonce in self.nonce_cache: return False
        sig = hmac.new(SUMER_SECRET_ZERO_DRIFT.encode(), state_metric.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, signature): return False
        self.nonce_cache[nonce] = time.time()
        return True
if __name__ == "__main__":
    print("[+] Protocol-Aligned Edge Widget Handler initialized successfully.")
