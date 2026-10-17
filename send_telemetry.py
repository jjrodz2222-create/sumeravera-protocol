import socket
import json
import time

SOCKET_PATH = "/tmp/sumeravera.sock"

def send_packet(payload):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)
    client.send(json.dumps(payload).encode("utf-8"))
    raw_response = client.recv(4096).decode("utf-8")
    client.close()
    return json.loads(raw_response)

print("--- [1/2] Sending Valid Vehicle/Equipment Telemetry ---")
valid_payload = {
    "source": "tow_telematics_unit_01",
    "event_type": "circuit_telemetry",
    "data": {
        "line_voltage": 12.6,
        "circuit_load_amps": 4.2,
        "operating_temp_c": 42.5
    }
}
resp1 = send_packet(valid_payload)
print(f"Server Response: {resp1}")

print("\n--- [2/2] Sending Malformed External Packet (Attack/Noise) ---")
malformed_payload = {
    "untrusted_source": "rogue_sensor",
    "arbitrary_injection": True
}
resp2 = send_packet(malformed_payload)
print(f"Server Response: {resp2}")
