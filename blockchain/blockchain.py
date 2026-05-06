"""Private lightweight blockchain manager backed by SQLite."""

from __future__ import annotations

import json
import time

from blockchain.block import Block, calculate_block_hash
from blockchain.validation import validate_chain, verify_block
from nodes.network import SimulatedValidatorNetwork


class LightweightVotingBlockchain:
    def __init__(self, db):
        self.db = db
        self.pending_transactions: list[dict] = []
        self.validator_network = SimulatedValidatorNetwork(db)
        self._ensure_genesis_block()
        self.validator_network.initialize_ledgers(self.get_chain())

    def _ensure_genesis_block(self) -> None:
        if self.db.get_last_block() is not None:
            return
        genesis = Block(
            index=0,
            transactions=[],
            previous_hash="0",
            nonce=0,
            validator_votes={"node_a": "genesis", "node_b": "genesis", "node_c": "genesis"},
            node_status={
                "node_a": {"valid": True, "message": "Genesis synchronized"},
                "node_b": {"valid": True, "message": "Genesis synchronized"},
                "node_c": {"valid": True, "message": "Genesis synchronized"},
            },
        ).as_dict()
        self.db.insert_block(genesis, verification_time_ms=0)

    def add_pending_transaction(
        self,
        transaction: dict,
        validation_time_ms: float = 0,
        signature_verification_time_ms: float = 0,
    ) -> None:
        self.pending_transactions.append(transaction)
        self.db.insert_transaction(
            transaction,
            status="pending",
            validation_time_ms=validation_time_ms,
            signature_verification_time_ms=signature_verification_time_ms,
        )

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

        consensus_accepted, consensus_report, consensus_time_ms = self.validator_network.request_consensus(
            block,
            previous_block,
        )
        block["validator_votes"] = consensus_report["validator_votes"]
        block["node_status"] = consensus_report["node_status"]
        block["current_hash"] = calculate_block_hash(block)

        verify_start = time.perf_counter()
        valid, message = verify_block(block, previous_block)
        verification_time_ms += (time.perf_counter() - verify_start) * 1000
        if not consensus_accepted:
            return False, "Consensus failed. Majority validator approval was not reached.", None
        if not valid:
            return False, message, None

        self.db.insert_block(block, creation_time_ms, verification_time_ms, consensus_time_ms)
        self.validator_network.synchronize_accepted_block(block)
        for transaction in self.pending_transactions:
            self.db.mark_transaction_confirmed(transaction["transaction_id"], block["index"])
        self.pending_transactions.clear()
        return True, "Block created, approved by validator majority, and appended to blockchain.", block

    def reset_runtime_ledger(self, is_active: bool = False) -> None:
        self.pending_transactions.clear()
        self.db.clear_election_runtime(is_active=is_active)
        self._ensure_genesis_block()
        self.validator_network.initialize_ledgers(self.get_chain())

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

    def chain_health(self) -> dict:
        is_valid, errors = validate_chain(self.get_chain())
        return {
            "is_valid": is_valid,
            "status": "VALID" if is_valid else "TAMPER DETECTED",
            "errors": errors,
            "nodes": self.db.get_node_status_summary(),
        }

    def consensus_comparison_metrics(self) -> dict:
        """Estimate lightweight consensus against a tiny simulated PoW baseline."""

        latest_block = self.db.get_last_block()
        if latest_block is None:
            return {"pow_baseline_time_ms": 0, "validator_speedup": "N/A"}

        consensus_time = latest_block.get("consensus_time_ms") or 0.0001
        # Deterministic simulated baseline for UI metrics. This avoids running
        # a mining loop during page rendering while still illustrating overhead.
        transaction_count = max(1, sum(len(block["transactions"]) for block in self.get_chain()))
        pow_time_ms = (consensus_time * 80) + (transaction_count * 4.5)
        nonce = transaction_count * 1200
        return {
            "pow_baseline_time_ms": round(pow_time_ms, 4),
            "pow_baseline_nonce_attempts": nonce,
            "validator_speedup": round(pow_time_ms / consensus_time, 2) if consensus_time else "N/A",
        }
