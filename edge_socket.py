import socket
import os
import json
from protocol_lockdown import get_connection, initialize_lockdown_storage, process_ingress_secure

SOCKET_PATH = "/tmp/sumeravera.sock"

if os.path.exists(SOCKET_PATH):
    os.remove(SOCKET_PATH)

conn = get_connection("ledger.db")
initialize_lockdown_storage(conn)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCKET_PATH)
server.listen(5)
print(f"SumerAvera Socket Listening on {SOCKET_PATH}...")

try:
    while True:
        client, _ = server.accept()
        raw = client.recv(65536).decode("utf-8")
        if raw:
            try:
                payload = json.loads(raw)
                status, tx_hash = process_ingress_secure(conn, payload)
                response = json.dumps({"status": status, "hash": tx_hash})
            except Exception as e:
                response = json.dumps({"status": "ERROR", "message": str(e)})
            client.send(response.encode("utf-8"))
        client.close()
except KeyboardInterrupt:
    print("\nShutting down socket.")
finally:
    conn.close()
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
