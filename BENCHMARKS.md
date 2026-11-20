# SumerAvera Edge Protocol - Measured Benchmarks

All numbers below are measured by `benchmark.py` (run it to reproduce:
`SUMERAVERA_SECRET_KEY=<32+ byte key> python3 benchmark.py`), except the
formal-verification line, which comes from the TLC run log
(`passing_run_log.txt`, 2026-10-17). Nothing in this file is a projection.

## Environment (this run)
- **Measured:** 2026-11-20
- **Execution Target:** Linux x86_64 virtual machine (4 CPUs)
- **Engine:** Python 3.12 / SQLite WAL mode
- **Cryptographic Primitives:** HMAC-SHA256 frame validation, SHA-256
  chained hashing, zero-trust schema validation

## Measured Operational Metrics (2026-11-20 run, 2,000 iterations)
| Metric | Measured Value | Unit / Scale |
| :--- | :--- | :--- |
| **Mean Core Ingress Latency** | 0.094 | ms / verified packet |
| **Core Ingress Throughput** | 10,593.2 | verifications / second (single-threaded) |
| **Mean Edge Guardian Latency** | 0.009 | ms / verified frame |
| **Edge Guardian Throughput** | 115,313.0 | verifications / second (single-threaded) |
| **Ledger Append Throughput** | 28,147.1 | writes / second (1,000 entries) |
| **Storage Density** | 372.7 | bytes / recorded state |
| **Working Disk Footprint** | 364.00 | KB (1,000 total transactions) |
| **Malformed-Packet Rejection** | 200 / 200 | rejected (100.00%: bad signature, replay, stale) |
| **Formal Safety Invariants** | 261 distinct states | 0 violations (TLC verified, 2026-10-17) |

The core repository reproduced these figures within ~5% on the same
machine (core ingress 0.090 ms, 11,076.5 verifications/sec; ledger
27,983.3 writes/sec, 376.8 bytes/state).

## Notes
- The 2026-10-17 figures previously listed here (0.743 ms mean latency,
  1,345.4 writes/sec, 353.7 bytes/state, 380.00 KB for 1,100 transactions)
  were superseded by the 2026-11-20 run above. The old throughput figure
  was the reciprocal of the old latency, not an independently measured
  write rate; this run measures ingress validation and ledger writes
  separately.
- The 2026-10-17 "Live 30s Soak" hardware-sensor sections (20 Hz sampling,
  99.8% noise suppression, CPU idle ratios) came from a physical sensor
  session and cannot be reproduced by `benchmark.py`; they are omitted
  until re-measured on hardware. The malformed-packet rejection rate in
  the table above is the measured replacement for the old blanket
  "100% interception" claim.
- **Sovereign Execution:** Fully decoupled from cloud infrastructure and
  recurring network costs.
