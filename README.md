# DigiParaMara / SumerAvera Protocol

Deterministic edge-first state invariance protocol and zero-trust ingress verification.

## Architectural Scope
DigiParaMara implements an edge-computing protocol designed for low-power edge nodes. It eliminates heavy consensus handshakes in favor of:
- Constant-time HMAC-SHA256 zero-trust ingress verification.
- Sliding-window timestamp drift enforcement.
- Persistent SQLite-backed nonce caches for full restart replay protection.
- Formally verified state invariance specifications (SumerAvera.tla).

## Local Verification
Run the verification suite:
python3 direct_test.py
./run_audit_suite.sh python3 audit_verify_standalone.py proof_re
