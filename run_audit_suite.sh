#!/bin/bash
set -e

echo "[+] Starting SumerAvera Protocol Audit Runner..."
if [ "$#" -lt 2 ]; then
    echo "Usage: ./run_audit_suite.sh <python_bin> <script_name> [args...]"
    exit 1
fi

PYTHON_BIN="$1"
SCRIPT_NAME="$2"
shift 2

echo "[+] Executing: $PYTHON_BIN $SCRIPT_NAME $@"
$PYTHON_BIN "$SCRIPT_NAME" "$@"
echo "[+] Audit sequence completed successfully."
