"""Vote transaction helpers for the lightweight voting blockchain."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def hash_transaction_payload(voter_hash: str, candidate: str, timestamp: str) -> str:
    payload = {
        "voter_hash": voter_hash,
        "candidate": candidate,
        "timestamp": timestamp,
    }
    return sha256_text(canonical_json(payload))


def create_vote_transaction(voter_id: str, candidate: str) -> dict:
    """Create a privacy-preserving vote transaction.

    The transaction stores only a hash of the voter identity. The original
    voter_id stays in the database for authentication and duplicate checks.
    """

    timestamp = utc_now()
    voter_hash = sha256_text(voter_id)
    transaction_hash = hash_transaction_payload(voter_hash, candidate, timestamp)
    return {
        "transaction_id": str(uuid.uuid4()),
        "voter_hash": voter_hash,
        "candidate": candidate,
        "timestamp": timestamp,
        "transaction_hash": transaction_hash,
    }


def is_transaction_format_valid(transaction: dict) -> bool:
    required = {"transaction_id", "voter_hash", "candidate", "timestamp", "transaction_hash"}
    return required.issubset(transaction) and all(transaction.get(key) for key in required)


def is_transaction_hash_valid(transaction: dict) -> bool:
    expected_hash = hash_transaction_payload(
        transaction["voter_hash"],
        transaction["candidate"],
        transaction["timestamp"],
    )
    return expected_hash == transaction["transaction_hash"]
