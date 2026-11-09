import time
import hmac
import hashlib
import json
from sumeravera_inquest import SovereignInquestEngine

def run_empirical_audit():
    print("[SVP Audit] Starting Empirical Zero-Trust Verification Harness...")
    secret = b"sumeravera-root-anchor-2026"
    engine = SovereignInquestEngine(secret, ttl_seconds=65)
    
    iterations = 10000
    start_time = time.time()
    
    allowed = 0
    inquired = 0
    dropped = 0
    
    for i in range(iterations):
        nonce = f"nonce_stress_{i}"
        ts = time.time()
        
        bio_var = 0.02 if i % 2 == 0 else (0.08 if i % 3 == 0 else 0.25)
        
        payload = {
            "event": "stress_test_packet",
            "seq": i,
            "telemetry": {
                "hw_attested": True,
                "lat": 29.8833,
                "lon": -97.9414,
                "biometric_variance": bio_var
            }
        }
        
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        sig = hmac.new(secret, f"{ts}:{nonce}:{canonical}".encode('utf-8'), hashlib.sha256).hexdigest()
        
        decision = engine.verify_gate1_ingress(payload, sig, ts, nonce)
        if decision == "ALLOW":
            allowed += 1
        elif decision == "INQUIRE":
            inquired += 1
        elif decision == "DROP":
            dropped += 1

    duration = time.time() - start_time
    throughput = iterations / duration

    print(f"\n--- Empirical Audit Results ---")
    print(f"Total Packets Evaluated : {iterations}")
    print(f"Execution Time          : {duration:.4f} seconds")
    print(f"Throughput              : {throughput:.2f} verifications/sec")
    print(f"ALLOW State Count       : {allowed}")
    print(f"INQUIRE State Count     : {inquired} (Uncertainty challenge loops triggered)")
    print(f"DROP State Count        : {dropped} (Drift / Rejections)")

    print("\n[SVP Audit] Running Adversarial Replay & TTL Test...")
    test_nonce = "replay_attack_nonce_999"
    test_ts = time.time()
    test_payload = {"event": "replay"}
    canonical_rep = json.dumps(test_payload, sort_keys=True, separators=(',', ':'))
    test_sig = hmac.new(secret, f"{test_ts}:{test_nonce}:{canonical_rep}".encode('utf-8'), hashlib.sha256).hexdigest()
    
    first_pass = engine.verify_gate1_ingress(test_payload, test_sig, test_ts, test_nonce)
    second_pass = engine.verify_gate1_ingress(test_payload, test_sig, test_ts, test_nonce)
    
    print(f"First Pass (Expected ALLOW/INQUIRE): {first_pass}")
    print(f"Second Pass Replay (Expected DROP)   : {second_pass}")
    assert second_pass == "DROP", "Security Failure: Replay attack was not intercepted!"
    print("[SVP Audit] Replay protection verified successfully.")

if __name__ == "__main__":
    run_empirical_audit()
