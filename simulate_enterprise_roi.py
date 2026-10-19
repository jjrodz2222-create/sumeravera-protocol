import time
import random

def run_sim(total_tx=10000):
    start = time.perf_counter()
    clean = 0
    quarantined = 0
    suppressed = 0
    prevented_usd = 0.0
    for i in range(total_tx):
        r = random.random()
        if r < 0.034:
            quarantined += 1
            prevented_usd += random.uniform(450.0, 3200.0)
        elif r < 0.88:
            suppressed += 1
        else:
            clean += 1
    elapsed = time.perf_counter() - start
    cloud_cost = total_tx * 0.0085
    edge_cost = clean * 0.0001
    savings_bw = cloud_cost - edge_cost
    total_saved = prevented_usd + savings_bw
    print("=== FINANCIAL VALUATION METRICS ===")
    print(f"Total Processed Ingress Events : {total_tx:,}")
    print(f"Synthetic Fraud Intercepted    : {quarantined:,} events")
    print(f"Direct Fraud Loss Prevented    : ${prevented_usd:,.2f} USD")
    print(f"Telemetry Noise Suppressed     : {suppressed:,} records ({suppressed/total_tx*100:.1f}%)")
    print(f"Cloud Ingestion Cost Saved     : ${savings_bw:,.2f} USD")
    print(f"Engine Processing Speed        : {total_tx/elapsed:,.1f} tx/sec")
    print(f"Net Operational Capital Saved  : ${total_saved:,.2f} USD")
    print("===================================")

if __name__ == "__main__":
    run_sim(10000)
