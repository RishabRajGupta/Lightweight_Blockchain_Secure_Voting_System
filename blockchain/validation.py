"""Lightweight transaction and block validation routines."""

from __future__ import annotations

from blockchain.block import calculate_block_hash
from blockchain.merkle import build_merkle_root
from blockchain.transaction import (
    is_transaction_format_valid,
    is_transaction_hash_valid,
    is_transaction_signature_valid,
    sha256_text,
)


def validate_vote_transaction(db, voter_id: str, transaction: dict) -> tuple[bool, str]:
    """Validate a vote transaction before it enters the pending pool."""

    voter = db.get_voter(voter_id)
    if voter is None:
        return False, "Voter does not exist."

    if voter["has_voted"]:
        return False, "Duplicate vote rejected. This voter has already voted."

    if transaction.get("voter_hash") != sha256_text(voter_id):
        return False, "Voter hash does not match the authenticated voter."

    if transaction.get("public_key") != voter.get("public_key"):
        return False, "Transaction public key does not match the registered voter key."

    if not db.candidate_exists(transaction.get("candidate", "")):
        return False, "Selected candidate is not registered."

    if not is_transaction_format_valid(transaction):
        return False, "Transaction format is invalid."

    if not is_transaction_hash_valid(transaction):
        return False, "Transaction hash integrity check failed."

    if not is_transaction_signature_valid(transaction):
        return False, "Transaction signature verification failed."

    return True, "Transaction validated successfully."


def verify_block(block: dict, previous_block: dict | None) -> tuple[bool, str]:
    """Verify a block with hash checks rather than heavyweight consensus."""

    expected_previous_hash = "0" if previous_block is None else previous_block["current_hash"]
    if block["previous_hash"] != expected_previous_hash:
        return False, "Previous hash mismatch."

    for transaction in block["transactions"]:
        if not is_transaction_format_valid(transaction):
            return False, "A transaction has invalid structure."
        if not is_transaction_hash_valid(transaction):
            return False, "A transaction failed integrity verification."
        if not is_transaction_signature_valid(transaction):
            return False, "A transaction has an invalid digital signature."

    expected_merkle_root = build_merkle_root([tx["transaction_hash"] for tx in block["transactions"]])
    if block["merkle_root"] != expected_merkle_root:
        return False, "Merkle root mismatch."

    if calculate_block_hash(block) != block["current_hash"]:
        return False, "Block hash integrity check failed."

    return True, "Block verified successfully."


def validate_chain(chain: list[dict]) -> tuple[bool, list[str]]:
    """Verify the full blockchain from genesis to latest block."""

    errors = []
    previous_block = None
    for expected_index, block in enumerate(chain):
        if block.get("index") != expected_index:
            errors.append(f"Block ordering error at position {expected_index}.")

        valid, message = verify_block(block, previous_block)
        if not valid:
            errors.append(f"Block {block.get('index')}: {message}")

        previous_block = block

    return len(errors) == 0, errors
