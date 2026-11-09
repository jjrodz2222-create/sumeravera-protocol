import os
from dotenv import load_dotenv

# Load environment variables from the local .env file
load_dotenv()

SECRET_KEY = os.getenv("SUMERAVERA_SECRET_KEY")

if not SECRET_KEY or len(SECRET_KEY) < 32:
  raise RuntimeError(
      "CRITICAL: SumerAvera Protocol halted. Valid SUMERAVERA_SECRET_KEY"
      " environment variable not found."
  )

# --- Rest of your protocol initialization and Gate 1 logic follows below ---import hmac
import hashlib
import sys
import os

def verify_ingress_payload(secret_key: bytes, payload: bytes, provided_signature: str) -> bool:
    if not provided_signature:
        return False
    try:
        computed_signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed_signature, provided_signature)
    except Exception:
        return False

if __name__ == "__main__":
    secret_env = os.environ.get("SVP_INGRESS_SECRET")
    if not secret_env:
        print("[GATE 1 INGRESS FATAL]: SVP_INGRESS_SECRET is not set. Failing closed.", file=sys.stderr)
        sys.exit(1)
        
    SECRET = secret_env.encode('utf-8')
    raw_payload = sys.stdin.buffer.read()
    incoming_sig = os.environ.get("SVP_PAYLOAD_SIGNATURE", "")
    
    if verify_ingress_payload(SECRET, raw_payload, incoming_sig):
        print("[GATE 1 INGRESS]: Payload verification successful. Invariance maintained.")
        sys.exit(0)
    else:
        print("[GATE 1 INGRESS ALERT]: Malformed or unauthorized payload signature intercepted.")
        sys.exit(1)
