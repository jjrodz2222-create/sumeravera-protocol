import socket
import json
import time

SOCKET_PATH = "/tmp/sumeravera.sock"

print("--- Streaming 10 Live Telemetry Packets ---")
for i in range(1, 11):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCKET_PATH)
    payload = {
        "source": "tow_telematics_bench",
        "event_type": "diagnostic_pulse",
        "data": {
            "seq": i,
            "battery_v": round(12.4 + (i * 0.05), 2),
            "load_a": 3.8
        }
    }
    s.send(json.dumps(payload).encode("utf-8"))
    raw_res = s.recv(4096).decode("utf-8")
    res = json.loads(raw_res)
    h = res.get("hash", "")
    print(f"Packet {i:02d}/10 Committed -> Hash: {h[:16]}...")
    s.close()
    time.sleep(0.15)
