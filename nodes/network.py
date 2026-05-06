"""Simulated multi-node validator network.

This is deliberately not peer-to-peer networking. It models three independent
validators that each keep a ledger copy and vote on candidate blocks. Majority
approval gives the research prototype a consensus layer without Proof of Work.
"""

from __future__ import annotations

import copy
import time

from blockchain.validation import verify_block


class SimulatedNode:
    def __init__(self, name: str):
        self.name = name

    def verify_candidate_block(self, block: dict, previous_block: dict | None) -> tuple[bool, str]:
        candidate = copy.deepcopy(block)
        candidate["validator_votes"] = {}
        candidate["node_status"] = {}
        return verify_block(candidate, previous_block)


class SimulatedValidatorNetwork:
    def __init__(self, db, node_names: list[str] | None = None):
        self.db = db
        self.nodes = [SimulatedNode(name) for name in (node_names or ["node_a", "node_b", "node_c"])]
        self.majority_threshold = (len(self.nodes) // 2) + 1

    def initialize_ledgers(self, chain: list[dict]) -> None:
        """Ensure each simulated node has a copy of the current chain."""

        for node in self.nodes:
            if self.db.get_node_last_block(node.name) is None:
                for block in chain:
                    self.db.upsert_node_block(node.name, block, is_valid=True, message="Synchronized")

    def request_consensus(self, block: dict, previous_block: dict | None) -> tuple[bool, dict, float]:
        start = time.perf_counter()
        validator_votes = {}
        node_status = {}

        for node in self.nodes:
            node_previous = self.db.get_node_last_block(node.name) or previous_block
            approved, message = node.verify_candidate_block(block, node_previous)
            validator_votes[node.name] = "approved" if approved else "rejected"
            node_status[node.name] = {"valid": approved, "message": message}

        approvals = sum(1 for vote in validator_votes.values() if vote == "approved")
        accepted = approvals >= self.majority_threshold
        consensus_time_ms = (time.perf_counter() - start) * 1000

        consensus_report = {
            "validator_votes": validator_votes,
            "node_status": node_status,
            "approvals": approvals,
            "required": self.majority_threshold,
            "accepted": accepted,
        }
        return accepted, consensus_report, consensus_time_ms

    def synchronize_accepted_block(self, block: dict) -> None:
        for node in self.nodes:
            status = block.get("node_status", {}).get(node.name, {})
            self.db.upsert_node_block(
                node.name,
                block,
                is_valid=bool(status.get("valid", True)),
                message=status.get("message", "Synchronized after consensus"),
            )
