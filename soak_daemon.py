import socket
import json
import time
import random

SOCKET_PATH = "/tmp/sumeravera.sock"

def send(payload):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.send(json.dumps(payload).encode("utf-8"))
        client.recv(4096)
        client.close()
    except Exception:
        pass

print("SumerAvera Soak Ingestion Simulator active (1 event every 5 seconds)...")

event_count = 0
while True:
    time.sleep(5)
    event_count += 1
    if random.random() > 0.10:
        packet = {
            "source": "sim_telematics_unit_01",
            "event_type": "telemetry_pulse",
            "data": {
                "voltage": round(12.4 + random.uniform(-0.3, 0.4), 2),
                "pulse_seq": event_count
            }
        }
    else:
        packet = {
            "unverified_source": "noise_burst",
            "raw_value": random.randint(100, 999)
        }
    send(packet)
