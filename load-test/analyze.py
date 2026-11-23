#!/usr/bin/env python3
"""Summarize load-test results.jsonl into a readable table."""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "results.jsonl"
rows = []
with open(path) as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

# Group by (mode, threads), keep reps together
groups = defaultdict(list)
for r in rows:
    groups[(r.get("mode"), r.get("threads"))].append(r)

MODES = ["gate1-shared", "gate1-perthread", "core-nonce", "ledger-only"]
print(f"{'mode':<16} {'thr':>3} {'rep':>3} {'succ/att':>10} {'thrpt/s':>9} "
      f"{'p50':>7} {'p95':>7} {'p99':>7} {'errs':>5} {'chain':>6} {'rows':>6}")
print("-" * 110)
for mode in MODES:
    for thr in [1, 2, 4, 8, 16, 32]:
        for r in groups.get((mode, thr), []):
            lat = r.get("latency") or {}
            errs = r.get("errors") or {}
            nerr = sum(v["count"] for v in errs.values())
            errnames = ",".join(f"{k}:{v['count']}" for k, v in errs.items()) or "-"
            chain = r.get("chain_valid")
            chain_s = "Y" if chain is True else ("N" if chain is False else "-")
            lrows = r.get("ledger_rows", r.get("nonce_rows", "-"))
            print(f"{mode:<16} {thr:>3} {r.get('rep','?'):>3} "
                  f"{r.get('success','?')}/{r.get('attempts','?'):>10} "
                  f"{str(r.get('throughput_per_s')):>9} "
                  f"{(lat.get('p50_ms') or 0):>7.3f} {(lat.get('p95_ms') or 0):>7.3f} "
                  f"{(lat.get('p99_ms') or 0):>7.3f} {nerr:>5} {chain_s:>6} {str(lrows):>6}")
            if errnames != "-":
                print(f"{'':<16} {'':>3} {'':>3} errors: {errnames}")
                for k, v in errs.items():
                    print(f"{'':<16} {'':>3} {'':>3}   {k}: {v['example'][:160]}")
            if "run" in r:
                print(f"{'':<16} {'':>3} {'':>3} RUN FAILED: {r['run']}")
            wal = r.get("ledger_files_before_close") or r.get("nonce_files")
            if wal:
                print(f"{'':<16} {'':>3} {'':>3} files before close: {wal}  "
                      f"after close: {r.get('ledger_files_after_close', '-')}")
print()
print("Rows parsed:", len(rows))
