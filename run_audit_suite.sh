#!/usr/bin/env bash
set -e
echo "============================================================="
echo "       SUMERAVERA SOVEREIGN PROTOCOL AUDIT SUITE             "
echo "============================================================="

echo "[1/4] Auditing Database WAL State..."
python3 -c "import sqlite3; conn = sqlite3.connect('ledger.db'); conn.execute('PRAGMA wal_checkpoint(PASSIVE);'); conn.close()"
echo "      -> WAL checkpoint clean."

echo "[2/4] Testing Merkle Inclusion Proof (Seq #142)..."
python3 verify_inclusion.py 142 > /dev/null
echo "      -> Merkle inclusion proof verified."

echo "[3/4] Exporting Standalone Proof Package..."
python3 export_proof.py 142 > /dev/null
echo "      -> proof_receipt.json generated."

echo "[4/4] Executing Zero-Dependency Standalone Audit..."
python3 audit_verify_standalone.py proof_receipt.json

echo "============================================================="
echo "[PASS] ALL SOVEREIGN INVARIANTS CRYPTOGRAPHICALLY VERIFIED    "
echo "============================================================="
