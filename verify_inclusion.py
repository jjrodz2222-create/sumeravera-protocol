import sqlite3
import hashlib
import sys
from typing import List, Tuple

def get_connection(db_path: str = "ledger.db") -> sqlite3.Connection:
    return sqlite3.connect(db_path)

def build_merkle_tree(leaf_hashes: List[str]) -> List[List[str]]:
    if not leaf_hashes:
        return [["0" * 64]]
    levels = [leaf_hashes]
    current = leaf_hashes
    while len(current) > 1:
        nxt = []
        for i in range(0, len(current), 2):
            l = current[i]
            r = current[i + 1] if i + 1 < len(current) else l
            c = hashlib.sha256((l + r).encode("utf-8")).hexdigest()
            nxt.append(c)
        levels.append(nxt)
        current = nxt
    return levels

def generate_audit_path(leaf_hashes: List[str], target_idx: int) -> List[Tuple[str, str]]:
    tree = build_merkle_tree(leaf_hashes)
    proof = []
    idx = target_idx
    for level in tree[:-1]:
        is_right = (idx % 2 == 1)
        sib_idx = idx - 1 if is_right else idx + 1
        sib_hash = level[sib_idx] if sib_idx < len(level) else level[idx]
        proof.append((sib_hash, "L" if is_right else "R"))
        idx //= 2
    return proof

def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], expected_root: str) -> bool:
    cur = leaf_hash
    for sib_hash, direction in proof:
        comb = (sib_hash + cur) if direction == "L" else (cur + sib_hash)
        cur = hashlib.sha256(comb.encode("utf-8")).hexdigest()
    return cur == expected_root

def audit_entry(seq_id: int):
    conn = get_connection("ledger.db")
    c = conn.cursor()
    c.execute("SELECT epoch_id, start_seq, end_seq, merkle_root FROM epoch_receipts WHERE ? BETWEEN start_seq AND end_seq;", (seq_id,))
    epoch = c.fetchone()
    if not epoch:
        print(f"[FAIL] Sequence ID {seq_id} is not part of any sealed epoch.")
        conn.close()
        return
    epoch_id, start_seq, end_seq, sealed_root = epoch
    c.execute("SELECT sequence_id, entry_hash FROM state_ledger WHERE sequence_id BETWEEN ? AND ? ORDER BY sequence_id ASC;", (start_seq, end_seq))
    rows = c.fetchall()
    conn.close()
    hashes = [r[1] for r in rows]
    t_idx = seq_id - start_seq
    t_hash = hashes[t_idx]
    proof = generate_audit_path(hashes, t_idx)
    valid = verify_proof(t_hash, proof, sealed_root)
    print(f"=== MERKLE INCLUSION AUDIT: SEQ #{seq_id} ===")
    print(f"Target Hash     : {t_hash[:20]}...")
    print(f"Sealed In Epoch : #{epoch_id} (Range {start_seq}..{end_seq})")
    print(f"Audit Path Steps: {len(proof)} sibling hashes evaluated")
    print(f"Sealed Root     : {sealed_root[:20]}...")
    print(f"Audit Verdict   : {'[PASS] CRYPTOGRAPHICALLY VERIFIED' if valid else '[FAIL] PROOF INVALID'}")
    print("==============================================")

if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    audit_entry(target)
