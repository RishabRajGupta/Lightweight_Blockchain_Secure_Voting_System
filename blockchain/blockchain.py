"""Private lightweight blockchain manager backed by SQLite."""

from __future__ import annotations

import json
import time

from blockchain.block import Block
from blockchain.validation import verify_block


class LightweightVotingBlockchain:
    def __init__(self, db):
        self.db = db
        self.pending_transactions: list[dict] = []
        self._ensure_genesis_block()

    def _ensure_genesis_block(self) -> None:
        if self.db.get_last_block() is not None:
            return
        genesis = Block(index=0, transactions=[], previous_hash="0", nonce=0).as_dict()
        self.db.insert_block(genesis, verification_time_ms=0)

    def add_pending_transaction(self, transaction: dict) -> None:
        self.pending_transactions.append(transaction)
        self.db.insert_transaction(transaction, status="pending")

    def create_block_from_pending(self) -> tuple[bool, str, dict | None]:
        if not self.pending_transactions:
            return False, "No validated transactions are waiting in the pool.", None

        previous_block = self.db.get_last_block()
        start = time.perf_counter()
        block = Block(
            index=previous_block["index"] + 1,
            transactions=list(self.pending_transactions),
            previous_hash=previous_block["current_hash"],
            nonce=len(self.pending_transactions),
        ).as_dict()
        creation_time_ms = (time.perf_counter() - start) * 1000

        verify_start = time.perf_counter()
        valid, message = verify_block(block, previous_block)
        verification_time_ms = (time.perf_counter() - verify_start) * 1000
        if not valid:
            return False, message, None

        self.db.insert_block(block, creation_time_ms, verification_time_ms)
        for transaction in self.pending_transactions:
            self.db.mark_transaction_confirmed(transaction["transaction_id"], block["index"])
        self.pending_transactions.clear()
        return True, "Block created and appended to blockchain.", block

    def get_chain(self) -> list[dict]:
        return self.db.get_all_blocks()

    def calculate_results(self) -> dict:
        results: dict[str, int] = {}
        for block in self.get_chain():
            for transaction in block["transactions"]:
                candidate = transaction["candidate"]
                results[candidate] = results.get(candidate, 0) + 1
        return results

    def storage_metrics(self) -> dict:
        blocks = self.get_chain()
        serialized = json.dumps(blocks, sort_keys=True)
        vote_count = sum(len(block["transactions"]) for block in blocks)
        chain_bytes = len(serialized.encode("utf-8"))
        return {
            "blocks": len(blocks),
            "confirmed_votes": vote_count,
            "chain_storage_bytes": chain_bytes,
            "avg_bytes_per_vote": round(chain_bytes / vote_count, 2) if vote_count else 0,
        }
