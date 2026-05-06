"""Block representation and hash functions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from blockchain.merkle import build_merkle_root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def calculate_block_hash(block_data: dict) -> str:
    """Calculate SHA-256 over stable block fields.

    This is intentionally lightweight: no mining loop and no adjustable
    difficulty target. The nonce is deterministic metadata rather than PoW.
    """

    payload = {
        "index": block_data["index"],
        "timestamp": block_data["timestamp"],
        "transactions": block_data["transactions"],
        "merkle_root": block_data["merkle_root"],
        "validator_votes": block_data.get("validator_votes", {}),
        "node_status": block_data.get("node_status", {}),
        "previous_hash": block_data["previous_hash"],
        "nonce": block_data["nonce"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Block:
    def __init__(
        self,
        index: int,
        transactions: list[dict],
        previous_hash: str,
        nonce: int = 0,
        validator_votes: dict | None = None,
        node_status: dict | None = None,
    ):
        self.index = index
        self.timestamp = utc_now()
        self.transactions = transactions
        self.merkle_root = build_merkle_root([tx["transaction_hash"] for tx in transactions])
        self.validator_votes = validator_votes or {}
        self.node_status = node_status or {}
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.current_hash = self.compute_hash()

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "merkle_root": self.merkle_root,
            "validator_votes": self.validator_votes,
            "node_status": self.node_status,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "current_hash": self.current_hash,
        }

    def compute_hash(self) -> str:
        return calculate_block_hash(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "transactions": self.transactions,
                "merkle_root": self.merkle_root,
                "validator_votes": self.validator_votes,
                "node_status": self.node_status,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            }
        )
