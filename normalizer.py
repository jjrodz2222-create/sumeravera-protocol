import json
import sys

def normalize_and_validate_payload(raw_payload: bytes) -> dict:
    """
    Normalizes raw byte payloads and enforces strict structural schema validation.
    Returns the parsed dictionary if valid, or raises a ValueError if malformed.
    """
    # 1. Decode raw bytes to UTF-8 string safely
    try:
        payload_str = raw_payload.decode('utf-8').strip()
    except UnicodeDecodeError:
        raise ValueError("Normalization Error: Payload contains invalid UTF-8 byte sequences.")

    # 2. Parse JSON content
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        raise ValueError("Schema Validation Error: Payload is not valid JSON format.")

    if not isinstance(data, dict):
        raise ValueError("Schema Validation Error: Root payload structure must be a JSON object.")

    # 3. Enforce Required Schema Fields and Types
    required_fields = {
        "node_id": str,
        "timestamp": (int, float),
        "state_delta": dict,
        "nonce": str
    }

    for field, expected_type in required_fields.items():
        if field not in data:
            raise ValueError(f"Schema Validation Error: Missing required field '{field}'.")
        if not isinstance(data[field], expected_type):
            raise TypeError(f"Schema Validation Error: Field '{field}' must be of type {expected_type.__name__}.")

    # 4. Normalize string and nested values
    normalized_data = {
        "node_id": data["node_id"].strip().lower(),
        "timestamp": float(data["timestamp"]),
        "state_delta": data["state_delta"],
        "nonce": data["nonce"].strip()
    }

    return normalized_data

if __name__ == "__main__":
    # Test execution when run standalone
    sample_raw = sys.stdin.buffer.read()
    if not sample_raw:
        # Default test payload if none provided via stdin
        sample_raw = b'{"node_id": " NODE_ALPHA ", "timestamp": 1772481600, "state_delta": {"status": "active"}, "nonce": "abc-123"}'
    
    try:
        clean_payload = normalize_and_validate_payload(sample_raw)
        print("[GATE 2 NORMALIZER]: Payload normalized and validated successfully.")
        print(json.dumps(clean_payload, indent=2))
        sys.exit(0)
    except (ValueError, TypeError) as e:
        print(f"[GATE 2 NORMALIZER ALERT]: {e}", file=sys.stderr)
        sys.exit(1)
