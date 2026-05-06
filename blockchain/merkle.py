"""Merkle tree utilities for efficient transaction verification."""

from __future__ import annotations

from blockchain.transaction import sha256_text


EMPTY_MERKLE_ROOT = sha256_text("empty-block")


def merkle_parent(left: str, right: str) -> str:
    return sha256_text(left + right)


def build_merkle_root(transaction_hashes: list[str]) -> str:
    """Build a deterministic Merkle root from transaction hashes."""

    if not transaction_hashes:
        return EMPTY_MERKLE_ROOT

    level = list(transaction_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [merkle_parent(level[index], level[index + 1]) for index in range(0, len(level), 2)]
    return level[0]


def build_merkle_proof(transaction_hashes: list[str], target_hash: str) -> list[dict]:
    """Return a compact inclusion proof for a transaction hash."""

    if target_hash not in transaction_hashes:
        return []

    proof = []
    index = transaction_hashes.index(target_hash)
    level = list(transaction_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling_index = index + 1 if index % 2 == 0 else index - 1
        proof.append(
            {
                "hash": level[sibling_index],
                "position": "right" if index % 2 == 0 else "left",
            }
        )
        index //= 2
        level = [merkle_parent(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return proof


def verify_merkle_proof(target_hash: str, proof: list[dict], merkle_root: str) -> bool:
    computed = target_hash
    for step in proof:
        if step["position"] == "left":
            computed = merkle_parent(step["hash"], computed)
        else:
            computed = merkle_parent(computed, step["hash"])
    return computed == merkle_root
