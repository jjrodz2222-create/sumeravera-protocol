import hmac
import hashlib
import time
import secrets
import json
import sys

class SVPHandshakePeer:
    def __init__(self, node_id: str, shared_secret: bytes, allowed_drift: int = 5):
        """
        Initializes an SVP Peer node for secure inter-intelligence handshakes.
        
        :param node_id: Unique identification string for this peer instance.
        :param shared_secret: Pre-shared key (PSK) used for HMAC-SHA256 verification.
        :param allowed_drift: Maximum acceptable temporal drift in seconds.
        """
        self.node_id = node_id
        self.shared_secret = shared_secret
        self.allowed_drift = allowed_drift
        self.seen_nonces = set()  # In production, use an expiring TTL cache

    def generate_challenge_packet(self) -> dict:
        """
        Generates Gate 1 & Gate 3 compliant handshake initialization packet.
        """
        timestamp = int(time.time())
        nonce = secrets.token_hex(16)
        
        payload = {
            "packet_id": f"svp-handshake-{secrets.token_hex(4)}",
            "protocol": "SumerAvera Protocol (SVP)",
            "version": "2.5",
            "sender_id": self.node_id,
            "timestamp": timestamp,
            "nonce": nonce
        }
        
        # Serialize with strict UTF-8 normalizer constraints (Gate 2 compliance)
        serialized_payload = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        # Generate Gate 1 Cryptographic Ingress Seal
        signature = hmac.new(self.shared_secret, serialized_payload, hashlib.sha256).hexdigest()
        payload["cryptographic_seal"] = signature
        
        return payload

    def verify_peer_handshake(self, incoming_packet: dict) -> bool:
        """
        Executes structural, temporal, and cryptographic validation on incoming peer packets.
        """
        try:
            # 0. Extract seal for isolation
            received_seal = incoming_packet.get("cryptographic_seal", "")
            if not received_seal:
                return False
                
            # Clone packet and remove seal to reconstruct raw verification payload
            verification_target = incoming_packet.copy()
            if "cryptographic_seal" in verification_target:
                del verification_target["cryptographic_seal"]
                
            # Gate 2: Strict Byte-level Serialization Alignment
            serialized_target = json.dumps(verification_target, sort_keys=True).encode('utf-8')
            
            # Gate 1: Constant-Time Cryptographic Validation
            expected_seal = hmac.new(self.shared_secret, serialized_target, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_seal, received_seal):
                return False  # Signature mismatch or timing attack vector mitigated
                
            # Gate 3: Idempotency & Temporal Drift Guarding
            timestamp = int(incoming_packet.get("timestamp", 0))
            current_time = int(time.time())
            if abs(current_time - timestamp) > self.allowed_drift:
                return False  # Replay window violation / Temporal drift outside limits
                
            nonce = incoming_packet.get("nonce", "")
            if nonce in self.seen_nonces:
                return False  # Idempotency failure: Replay detected
                
            # Track verified nonce to prevent duplicate processing
            self.seen_nonces.add(nonce)
            return True
            
        except (ValueError, KeyError, TypeError):
            return False  # Malformed payload structure rejected immediately

# Example Invariant Peer Synchronization Test Execution
if __name__ == "__main__":
    SHARED_INTELLIGENCE_KEY = b"svp_secure_immutable_anchor_psk_2026"
    
    node_alpha = SVPHandshakePeer(node_id="SVP-ALPHA-NODE", shared_secret=SHARED_INTELLIGENCE_KEY)
    node_beta = SVPHandshakePeer(node_id="SVP-BETA-NODE", shared_secret=SHARED_INTELLIGENCE_KEY)
    
    print("[P2P HANDSHAKE TEST]: Initializing peer verification sequence...")
    
    # 1. Alpha constructs and seals the telemetry initiation signal
    handshake_signal = node_alpha.generate_challenge_packet()
    print(f"Alpha Ingress Packet Generated:\n{json.dumps(handshake_signal, indent=2)}\n")
    
    # 2. Beta intercepting, normalizing, and verifying the state mapping
    verification_success = node_beta.verify_peer_handshake(handshake_signal)
    print(f"Beta Verification Results -> Handshake Validated: {verification_success}")
    
    # 3. Test Replay Immunity (Idempotency Check)
    replay_attempt = node_beta.verify_peer_handshake(handshake_signal)
    print(f"Beta Secondary Verification (Replay Attack) -> Handshake Validated: {replay_attempt}")

    if verification_success and not replay_attempt:
        print("\n[SUCCESS]: Peer handshake protocol operating with zero drift.")
        sys.exit(0)
    else:
        print("\n[FAILURE]: Handshake test anomaly detected.")
        sys.exit(1)
