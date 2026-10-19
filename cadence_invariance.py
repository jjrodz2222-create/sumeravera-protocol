import time, hashlib, json

class CadenceIntentTracker:
    def __init__(self, pause_threshold_sec=1.5):
        self.pause_threshold = pause_threshold_sec
        self.last_event_ts = time.time()
        self.cadence_log = []

    def log_input_segment(self, segment_text, custom_pause_duration=None):
        current_ts = time.time()
        pause_duration = custom_pause_duration if custom_pause_duration is not None else (current_ts - self.last_event_ts)
        self.last_event_ts = current_ts
        is_pause = pause_duration >= self.pause_threshold
        cadence_type = 'REFLECTIVE_PAUSE' if is_pause else 'STREAMING_FLOW'
        entry = {
            'text': segment_text,
            'pause_duration_ms': round(pause_duration * 1000, 2),
            'cadence_type': cadence_type,
            'intent_preserved': True
        }
        entry_blob = f"{segment_text}|{entry['pause_duration_ms']}|{cadence_type}".encode('utf-8')
        entry['temporal_hash'] = hashlib.sha256(entry_blob).hexdigest()
        self.cadence_log.append(entry)
        return entry

    def export_cadence_receipt(self, output_path='cadence_receipt.json'):
        payload = {
            'protocol': 'SumerAvera Core',
            'module': 'Temporal-Cadence-Preservation',
            'log_count': len(self.cadence_log),
            'events': self.cadence_log
        }
        with open(output_path, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f'[CADENCE] Preserved {len(self.cadence_log)} states to {output_path}')
        return payload

if __name__ == '__main__':
    tracker = CadenceIntentTracker(pause_threshold_sec=1.5)
    tracker.log_input_segment('Context initialization', custom_pause_duration=0.3)
    tracker.log_input_segment('Structural intent hold', custom_pause_duration=2.4)
    tracker.log_input_segment('Execution invariant', custom_pause_duration=0.5)
    tracker.export_cadence_receipt()
