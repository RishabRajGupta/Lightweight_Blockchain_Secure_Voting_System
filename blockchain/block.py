"""Block representation and hash functions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


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
        "previous_hash": block_data["previous_hash"],
        "nonce": block_data["nonce"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Block:
    def __init__(self, index: int, transactions: list[dict], previous_hash: str, nonce: int = 0):
        self.index = index
        self.timestamp = utc_now()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.current_hash = self.compute_hash()

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
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
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            }
        )
