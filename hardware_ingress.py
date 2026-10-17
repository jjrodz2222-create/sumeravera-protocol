import socket
import json
import time
import os
import glob

SOCKET_PATH = "/tmp/sumeravera.sock"

def get_cpu_temp():
    """Extract real thermal sensor reading from Linux sysfs."""
    thermal_zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")
    if thermal_zones:
        try:
            with open(thermal_zones[0], "r") as f:
                return round(int(f.read().strip()) / 1000.0, 2)
        except Exception:
            pass
    return None

def get_memory_metrics():
    """Parse actual physical memory allocation from procfs."""
    mem_total, mem_free = 0, 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_free = int(line.split()[1])
        used_pct = round(((mem_total - mem_free) / mem_total) * 100, 2) if mem_total else 0.0
        return {"total_kb": mem_total, "used_pct": used_pct}
    except Exception:
        return {"total_kb": 0, "used_pct": 0.0}

def get_system_load():
    """Read actual kernel load averages."""
    try:
        load1, load5, load15 = os.getloadavg()
        return {"1m": round(load1, 2), "5m": round(load5, 2)}
    except Exception:
        return {"1m": 0.0, "5m": 0.0}

def send_to_socket(payload):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.send(json.dumps(payload).encode("utf-8"))
        raw = client.recv(4096).decode("utf-8")
        client.close()
        return json.loads(raw)
    except Exception as e:
        return {"status": "SOCKET_ERROR", "error": str(e)}

def run_hardware_ingress(cadence_seconds=5, samples=10):
    print(f"=== SumerAvera Live Hardware Ingress Stream ({samples} Samples) ===")
    for seq in range(1, samples + 1):
        payload = {
            "source": "chromebook_bare_metal",
            "event_type": "hardware_telemetry",
            "data": {
                "sample_id": seq,
                "cpu_temp_c": get_cpu_temp(),
                "memory": get_memory_metrics(),
                "load": get_system_load()
            }
        }
        res = send_to_socket(payload)
        status = res.get("status", "ERR")
        h = res.get("hash", "no-hash")[:16]
        print(f"Sample {seq:02d} | Temp: {payload['data']['cpu_temp_c']}°C | Mem: {payload['data']['memory']['used_pct']}% | Status: [{status}] Hash: {h}...")
        time.sleep(cadence_seconds)

if __name__ == "__main__":
    run_hardware_ingress(cadence_seconds=3, samples=5)
