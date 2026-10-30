import time
import hmac
import hashlib
from sumeravera_core import verify_ingress_packet, SHARED_SECRET

def run_benchmark(iterations=1000):
    print(f"[*] Benchmarking {iterations} zero-trust ingress validations...")
    payload = b'{"benchmark": true, "metric": "latency"}'
    start_time = time.perf_counter()

    for i in range(iterations):
        ts = time.time()
        nonce = f"bench_nonce_{i}_{int(ts * 1000)}"
        msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
        sig = hmac.new(SHARED_SECRET, msg, hashlib.sha256).hexdigest()
        assert verify_ingress_packet(payload, sig, nonce, ts)

    total_time = time.perf_counter() - start_time
    avg_latency = (total_time / iterations) * 1000

    print(f"[+] Completed {iterations} checks in {total_time:.4f}s")
    print(f"[+] Average validation latency: {avg_latency:.3f} ms per packet")

if __name__ == "__main__":
    run_benchmark(500)
