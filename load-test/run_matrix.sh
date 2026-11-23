#!/bin/bash
# Run the full load-test matrix: modes x threads {1,2,4,8,16,32} x 2 reps.
# Each run is a fresh process in a fresh temp dir (deleted afterwards).
# Appends one JSON line per run to results.jsonl.
set -u
# Paths are resolved from this script's location, so the matrix runs from a
# checkout anywhere. PY is overridable (SVP_PYTHON) for a venv python.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="${SVP_PYTHON:-python3}"
LT="$SCRIPT_DIR/loadtest.py"
TREE="$ROOT"
OUT="$SCRIPT_DIR/results.jsonl"
: > "$OUT"
for mode in gate1-shared gate1-perthread core-nonce ledger-only; do
  for threads in 1 2 4 8 16 32; do
    for rep in 1 2; do
      workdir=$(mktemp -d /tmp/svp-load-XXXXXX)
      echo "=== $mode threads=$threads rep=$rep ==="
      if ! timeout 240 "$PY" "$LT" --mode "$mode" --threads "$threads" \
          --iters 500 --workdir "$workdir" --tree "$TREE" >> "$OUT"; then
        echo "{\"mode\":\"$mode\",\"threads\":$threads,\"rep\":$rep,\"run\":\"timeout_or_crash\"}" >> "$OUT"
      fi
      rm -rf "$workdir"
    done
  done
done
echo "DONE. Results in $OUT"
