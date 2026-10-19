import os
import glob
import time
import socket
import json
import resource

SOCKET_PATH = "/tmp/sumeravera.sock"

def read_system_hw_metrics():
    metrics = {"timestamp": time.time()}
    bat_paths = glob.glob("/sys/class/power_supply/BAT*")
    if bat_paths:
        try:
            with open(os.path.join(bat_paths[0], "voltage_now"), "r") as f:
                metrics["bat_voltage_uv"] = int(f.read().strip())
            with open(os.path.join(bat_paths[0], "current_now"), "r") as f:
                metrics["bat_current_ua"] = int(f.read().strip())
        except Exception:
            pass

    temp_paths = glob.glob("/sys/class/thermal/thermal_zone*/temp")
    temps = []
    for p in temp_paths[:2]:
        try:
            with open(p, "r") as f:
                temps.append(int(f.read().strip()) / 1000.0)
        except Exception:
            pass
    metrics["cpu_temps_c"] = temps
    return metrics

def run_hardware_energy_audit(duration_sec=30):
    print(f"=== Running Live Hardware Ingress Test ({duration_sec}s Soak) ===")
    start_cpu = resource.getrusage(resource.RUSAGE_SELF)
    start_time = time.perf_counter()
    
    events_logged = 0
    discarded_noise = 0
    last_temp = None

    while (time.perf_counter() - start_time) < duration_sec:
        data = read_system_hw_metrics()
        current_temp = data.get("cpu_temps_c", [0])[0] if data.get("cpu_temps_c") else 0
        
        if last_temp is None or abs(current_temp - last_temp) >= 0.25:
            last_temp = current_temp
            payload = {
                "source": "bare_metal_hw_bus",
                "event_type": "thermal_state_shift",
                "data": data
            }
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(SOCKET_PATH)
                s.send(json.dumps(payload).encode("utf-8"))
                s.recv(4096)
                s.close()
                events_logged += 1
            except Exception:
                pass
        else:
            discarded_noise += 1
            
        time.sleep(0.05)

    elapsed_wall = time.perf_counter() - start_time
    end_cpu = resource.getrusage(resource.RUSAGE_SELF)
    total_cpu_time = (end_cpu.ru_utime - start_cpu.ru_utime) + (end_cpu.ru_stime - start_cpu.ru_stime)
    
    idle_ratio = (1.0 - (total_cpu_time / elapsed_wall)) * 100
    suppression_pct = (discarded_noise / (events_logged + discarded_noise)) * 100 if (events_logged + discarded_noise) > 0 else 0

    print("\n================ EMPIRICAL HARDWARE EFFICIENCY ================")
    print(f"Total Observation Window      : {elapsed_wall:.2f} seconds")
    print(f"Raw Physical Samples Checked   : {events_logged + discarded_noise} (20 Hz loop)")
    print(f"Unnecessary Writes Suppressed  : {discarded_noise} samples ({suppression_pct:.1f}% reduction)")
    print(f"Verified State Events Committed: {events_logged}")
    print(f"Total CPU Processing Time      : {total_cpu_time:.4f} seconds")
    print(f"CPU Rest / Idle Ratio          : {idle_ratio:.2f}%")
    print("==============================================================")

if __name__ == "__main__":
    run_hardware_energy_audit(30)
