import json
import hashlib
import sys

def verify_standalone_receipt(receipt_file: str = "proof_receipt.json") -> bool:
    with open(receipt_file, "r") as f:
        receipt = json.load(f)
    target = receipt["target_record"]
    epoch = receipt["epoch_seal"]
    proof = receipt["proof_path"]
    raw_payload_str = json.dumps(target["payload"], separators=(",", ":")) if isinstance(target["payload"], dict) else str(target["payload"])
    current_hash = target["entry_hash"]
    for sibling_hash, direction in proof:
        combined = (sibling_hash + current_hash) if direction == "L" else (current_hash + sibling_hash)
        current_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    expected_root = epoch["merkle_root"]
    is_valid = (current_hash == expected_root)
    print("================ EXTERNAL AUDIT VERIFICATION ================")
    print(f"Target Sequence ID : {target['sequence_id']}")
    print(f"Target Entry Hash  : {target['entry_hash'][:24]}...")
    print(f"Sealed Epoch ID    : #{epoch['epoch_id']} (Range: {epoch['range'][0]}..{epoch['range'][1]})")
    print(f"Computed Root      : {current_hash}")
    print(f"Expected Root      : {expected_root}")
    print(f"Cryptographic Math : {len(proof)} hashing layers resolved")
    verdict = "[VERIFIED VALID] PROOF MATHEMATICALLY SOUND" if is_valid else "[TAMPER DETECTED] PROOF INVALID"
    print(f"Verdict            : {verdict}")
    print("=============================================================")
    return is_valid

if __name__ == "__main__":
    fpath = sys.argv[1] if len(sys.argv) > 1 else "proof_receipt.json"
    success = verify_standalone_receipt(fpath)
    sys.exit(0 if success else 1)
