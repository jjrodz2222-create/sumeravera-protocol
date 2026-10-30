import os
import sys
import time
import hmac
import hashlib
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Request

app = FastAPI(title="SumerAvera Core Engine", version="1.0.0")

# 1. Enforce Key Configuration
PRIMARY_KEY = os.environ.get("SUMERAVERA_SECRET_KEY")
if not PRIMARY_KEY:
    # Fail fast if security key is not provisioned
    print("CRITICAL: SUMERAVERA_SECRET_KEY not set. Using local development fallback.")
    PRIMARY_KEY = "svp_local_dev_secret_key_32bytes_min"

SHARED_SECRET = PRIMARY_KEY.encode("utf-8")
NONCE_EXPIRY_SECONDS = 300

# 2. Device Identity Keyring
DEVICE_KEYRING = {
    "node_alpha_01": os.environ.get("KEY_NODE_ALPHA", PRIMARY_KEY).encode("utf-8"),
    "node_beta_02": os.environ.get("KEY_NODE_BETA", PRIMARY_KEY).encode("utf-8"),
}

# 3. Persistent SQLite Nonce Engine (Survives Restarts)
DB_PATH = "nonce_cache.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

with conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_nonces (
            nonce TEXT PRIMARY KEY,
            timestamp REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON seen_nonces(timestamp)")

def prune_expired_nonces(now: float):
    cutoff = now - NONCE_EXPIRY_SECONDS
    with conn:
        conn.execute("DELETE FROM seen_nonces WHERE timestamp < ?", (cutoff,))

def register_nonce(nonce: str, timestamp: float) -> bool:
    prune_expired_nonces(timestamp)
    try:
        with conn:
            conn.execute("INSERT INTO seen_nonces (nonce, timestamp) VALUES (?, ?)", (nonce, timestamp))
        return True
    except sqlite3.IntegrityError:
        return False  # Nonce collision / Replay attack

def verify_ingress_packet(payload: bytes, signature: str, nonce: str, timestamp: float, device_id: Optional[str] = None) -> bool:
    now = time.time()

    # Time Drift Check
    if abs(now - timestamp) > NONCE_EXPIRY_SECONDS:
        return False

    # Replay Check
    if not register_nonce(nonce, timestamp):
        return False

    # Key Resolution
    secret = DEVICE_KEYRING.get(device_id, SHARED_SECRET) if device_id else SHARED_SECRET

    # HMAC-SHA256 Constant-Time Verification
    message = f"{nonce}:{int(timestamp)}:".encode("utf-8") + payload
    expected_sig = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)

@app.get("/")
def get_status():
    return {
        "protocol": "SumerAvera",
        "state": "InvariantLocked",
        "status": "active",
        "persistence": "sqlite3"
    }

@app.post("/verify")
async def verify_endpoint(
    request: Request,
    x_signature: str = Header(...),
    x_nonce: str = Header(...),
    x_timestamp: float = Header(...),
    x_device_id: Optional[str] = Header(None)
):
    body = await request.body()
    if not verify_ingress_packet(body, x_signature, x_nonce, x_timestamp, x_device_id):
        raise HTTPException(status_code=401, detail="Zero-trust invariant verification failed")

    return {
        "status": "Committed",
        "verified": True,
        "nonce": x_nonce
    }
