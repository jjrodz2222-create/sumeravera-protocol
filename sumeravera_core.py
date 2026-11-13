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
# Fail closed: the service refuses to start without a provisioned key.
# There is no fallback secret. Set SUMERAVERA_SECRET_KEY in the environment
# of the machine that runs this process; never commit a key value.
PRIMARY_KEY = os.environ.get("SUMERAVERA_SECRET_KEY")
if not PRIMARY_KEY:
    raise RuntimeError(
        "CRITICAL: SUMERAVERA_SECRET_KEY environment variable is not set. "
        "SumerAvera Core refuses to start without a provisioned key."
    )

SHARED_SECRET = PRIMARY_KEY.encode("utf-8")
NONCE_EXPIRY_SECONDS = 300

# 2. Device Identity Keyring
# A node key exists in the keyring only when its env var is set explicitly.
# A device that presents an unknown device_id is rejected; a node never
# silently falls back to the primary key.
DEVICE_KEYRING = {
    device_id: os.environ[env_var].encode("utf-8")
    for device_id, env_var in (
        ("node_alpha_01", "KEY_NODE_ALPHA"),
        ("node_beta_02", "KEY_NODE_BETA"),
    )
    if os.environ.get(env_var)
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

    # Key Resolution: an unknown device_id is rejected outright; a node never
    # falls back to the shared secret.
    if device_id is not None and device_id not in DEVICE_KEYRING:
        return False
    secret = DEVICE_KEYRING.get(device_id, SHARED_SECRET) if device_id else SHARED_SECRET

    # HMAC-SHA256 Constant-Time Verification.
    # The signature is verified BEFORE the nonce is recorded: a packet with a
    # bad signature must never consume a nonce or leave a mark in the store.
    message = f"{nonce}:{int(timestamp)}:".encode("utf-8") + payload
    expected_sig = hmac.new(secret, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        return False

    # Replay Check: only a signature-verified packet registers its nonce.
    return register_nonce(nonce, timestamp)

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
