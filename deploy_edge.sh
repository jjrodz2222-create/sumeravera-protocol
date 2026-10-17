#!/usr/bin/env bash
set -e

echo "=== SumerAvera Sovereign Edge Node Deployment ==="

# 1. Environment and dependency check
if ! command -v python3 &> /dev/null; then
    echo "[FAIL] Python3 standard runtime not found."
    exit 1
fi

# 2. Run local formal verification test harness
echo "--- Running Pre-Flight Invariant Audit ---"
python3 test_runner.py

# 3. Clean stale sockets
rm -f /tmp/sumeravera.sock

# 4. Launch socket server in background
echo "--- Launching Sovereign Socket Daemon ---"
nohup python3 edge_socket.py > edge_node.log 2>&1 &
NODE_PID=$!
echo "[PASS] Edge Daemon active with PID: $NODE_PID"

# 5. Send verification ping
sleep 1
python3 send_telemetry.py

echo "=== DEPLOYMENT COMPLETE: ZERO-TRUST DAEMON OPERATIONAL ==="
