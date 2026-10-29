import time
import hmac
import hashlib
from sumeravera_core import verify_ingress_packet, SHARED_SECRET

def run_tests():
    print("[*] Running SumerAvera Core Integration Tests...")

    payload = b'{"action": "state_update", "target": "edge_node_42"}'
    ts = time.time()
    nonce = f"test_nonce_{int(ts * 1000)}"

    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    sig = hmac.new(SHARED_SECRET, msg, hashlib.sha256).hexdigest()

    # Test 1: Valid Ingress
    assert verify_ingress_packet(payload, sig, nonce, ts), "Test 1 Failed: Valid packet rejected"
    print("  [PASS] Test 1: Legitimate ingress verified.")

    # Test 2: Replay Attack (Same nonce)
    assert not verify_ingress_packet(payload, sig, nonce, ts), "Test 2 Failed: Replay packet accepted"
    print("  [PASS] Test 2: Replay attack rejected.")

    # Test 3: Stale Drift Packet (> 300s old)
    old_ts = ts - 301
    old_nonce = f"old_nonce_{int(old_ts)}"
    old_msg = f"{old_nonce}:{int(old_ts)}:".encode("utf-8") + payload
    old_sig = hmac.new(SHARED_SECRET, old_msg, hashlib.sha256).hexdigest()
    assert not verify_ingress_packet(payload, old_sig, old_nonce, old_ts), "Test 3 Failed: Stale packet accepted"
    print("  [PASS] Test 3: Stale timestamp rejected.")

    print("[SUCCESS] All SumerAvera Core verification tests passed.")

if __name__ == "__main__":
    run_tests()
