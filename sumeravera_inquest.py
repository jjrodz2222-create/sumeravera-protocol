#!/usr/bin/env python3
"""
SumerAvera Protocol (DigiParaMara) - Sovereign Inquest & Ingress Engine
Core architectural module for zero-trust invariant state verification,
uncertainty delta detection, and inquiring edge validation.
"""

import hmac
import hashlib
import time
import json
from collections import OrderedDict

class SovereignInquestEngine:
    def __init__(self, shared_secret: bytes, ttl_seconds: int = 65):
        self.shared_secret = shared_secret
        self.ttl_seconds = ttl_seconds
        # 65s TTL Nonce Cache for replay protection
        self.nonce_cache = OrderedDict()
        
        # Baseline Invariants (Hardware, Spatial, Biometric/Acoustic vectors)
        self.baseline_state = {
            "hardware_attestation_valid": True,
            "spatial_perimeter_active": True,
            "biometric_variance_threshold": 0.15,
            "baseline_lat": 29.8833, # San Marcos, TX baseline anchor
            "baseline_lon": -97.9414
        }

    def _clean_nonce_cache(self):
        current_time = time.time()
        expired_nonces = [
            nonce for nonce, timestamp in self.nonce_cache.items()
            if current_time - timestamp > self.ttl_seconds
        ]
        for nonce in expired_nonces:
            del self.nonce_cache[nonce]

    def verify_gate1_ingress(self, payload: dict, signature: str, timestamp: float, nonce: str) -> str:
        """
        Gate 1 Ingress Validation:
        Returns: 'ALLOW', 'INQUIRE' (uncertainty trigger), or 'DROP' (malicious/drift)
        """
        current_time = time.time()
        
        # 1. Nonce & Timestamp TTL Check (Replay Protection)
        if abs(current_time - timestamp) > self.ttl_seconds:
            return "DROP"
        
        self._clean_nonce_cache()
        if nonce in self.nonce_cache:
            return "DROP" # Replay detected
        
        self.nonce_cache[nonce] = current_time
        
        # 2. Constant-Time HMAC-SHA256 Verification
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        computed_sig = hmac.new(
            self.shared_secret,
            f"{timestamp}:{nonce}:{canonical_payload}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_sig, signature):
            return "DROP" # Cryptographic failure / spoof attempt

        # 3. Continuous Invariant Delta Evaluation
        delta_score = self._evaluate_invariants(payload.get("telemetry", {}))
        
        if delta_score == 0.0:
            return "ALLOW"
        elif 0.0 < delta_score <= self.baseline_state["biometric_variance_threshold"]:
            # Uncertainty detected: trigger the inquiry loop instead of blind failure
            return "INQUIRE"
        else:
            # Severe invariant violation (hard drift)
            return "DROP"

    def _evaluate_invariants(self, telemetry: dict) -> float:
        """
        Calculates environmental, spatial, and biometric variance.
        Returns a delta score between 0.0 (exact match) and 1.0 (complete divergence).
        """
        score = 0.0
        
        # Check Hardware Attestation Flag
        if not telemetry.get("hw_attested", True):
            return 1.0 # Immediate critical failure
            
        # Check Spatial Drift (GPS distance approximation)
        lat = telemetry.get("lat", self.baseline_state["baseline_lat"])
        lon = telemetry.get("lon", self.baseline_state["baseline_lon"])
        lat_delta = abs(lat - self.baseline_state["baseline_lat"])
        lon_delta = abs(lon - self.baseline_state["baseline_lon"])
        
        if lat_delta > 0.05 or lon_delta > 0.05: # Noticeable spatial shift
            score += 0.10
            
        # Check Biometric / Acoustic Cadence Variance
        bio_variance = telemetry.get("biometric_variance", 0.0)
        score += bio_variance
        
        return min(score, 1.0)

if __name__ == "__main__":
    secret = b"sumeravera-root-anchor-2026"
    engine = SovereignInquestEngine(secret)
    
    test_payload = {
        "event": "identity_attestation",
        "telemetry": {
            "hw_attested": True,
            "lat": 29.8835,
            "lon": -97.9412,
            "biometric_variance": 0.08 # Mild variance triggering the inquiry threshold
        }
    }
    
    ts = time.time()
    nonce_str = "nonce_2222_alpha"
    canonical = json.dumps(test_payload, sort_keys=True, separators=(',', ':'))
    sig = hmac.new(secret, f"{ts}:{nonce_str}:{canonical}".encode('utf-8'), hashlib.sha256).hexdigest()
    
    decision = engine.verify_gate1_ingress(test_payload, sig, ts, nonce_str)
    print(f"[SVP Gate 1 Ingress State] Result: {decision}")
