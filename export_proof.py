import sqlite3
import json
import sys
from verify_inclusion import generate_audit_path, get_connection

def export_proof_package(seq_id: int, output_file: str = "proof_receipt.json"):
    conn = get_connection("ledger.db")
    cur = conn.cursor()
    cur.execute("SELECT epoch_id, start_seq, end_seq, merkle_root, sealed_at FROM epoch_receipts WHERE ? BETWEEN start_seq AND end_seq;", (seq_id,))
    epoch = cur.fetchone()
    if not epoch:
        print(f"[FAIL] Sequence #{seq_id} is not within any sealed epoch.")
        conn.close()
        return
    epoch_id, start_seq, end_seq, sealed_root, sealed_at = epoch
    cur.execute("SELECT sequence_id, entry_hash, payload FROM state_ledger WHERE sequence_id BETWEEN ? AND ? ORDER BY sequence_id ASC;", (start_seq, end_seq))
    rows = cur.fetchall()
    conn.close()
    hashes = [r[1] for r in rows]
    target_idx = seq_id - start_seq
    target_row = rows[target_idx]
    proof = generate_audit_path(hashes, target_idx)
    try:
        payload_data = json.loads(target_row[2])
    except Exception:
        payload_data = str(target_row[2])
    receipt_pkg = {
        "protocol": "SumerAvera-v2.5",
        "target_record": {
            "sequence_id": target_row[0],
            "entry_hash": target_row[1],
            "payload": payload_data
        },
        "epoch_seal": {
            "epoch_id": epoch_id,
            "range": [start_seq, end_seq],
            "merkle_root": sealed_root,
            "sealed_at": sealed_at
        },
        "proof_path": proof
    }
    with open(output_file, "w") as f:
        json.dump(receipt_pkg, f, indent=2)
    print(f"[EXPORTED] Standalone proof written to {output_file} for Seq #{seq_id}")

if __name__ == "__main__":
    seq = int(sys.argv[1]) if len(sys.argv) > 1 else 142
    export_proof_package(seq)
