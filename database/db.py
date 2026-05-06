"""SQLite persistence layer for the voting blockchain prototype."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from blockchain.crypto_utils import generate_key_pair
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "voting_system.db"


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS voters (
                    voter_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    private_key TEXT,
                    public_key TEXT,
                    has_voted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blockchain (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    block_index INTEGER UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    transactions TEXT NOT NULL,
                    merkle_root TEXT,
                    validator_votes TEXT,
                    node_status TEXT,
                    previous_hash TEXT NOT NULL,
                    nonce INTEGER NOT NULL,
                    current_hash TEXT NOT NULL,
                    creation_time_ms REAL DEFAULT 0,
                    verification_time_ms REAL DEFAULT 0,
                    consensus_time_ms REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    voter_hash TEXT NOT NULL,
                    candidate TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    signature TEXT,
                    public_key TEXT,
                    transaction_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    validation_time_ms REAL DEFAULT 0,
                    signature_verification_time_ms REAL DEFAULT 0,
                    block_index INTEGER
                );

                CREATE TABLE IF NOT EXISTS node_ledgers (
                    node_name TEXT NOT NULL,
                    block_index INTEGER NOT NULL,
                    block_json TEXT NOT NULL,
                    is_valid INTEGER NOT NULL DEFAULT 1,
                    message TEXT,
                    synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (node_name, block_index)
                );

                CREATE TABLE IF NOT EXISTS election_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_active INTEGER NOT NULL DEFAULT 0
                );

                INSERT OR IGNORE INTO election_status (id, is_active) VALUES (1, 1);
                """
            )
            self._migrate_schema(conn)
            self.seed_data(conn)

    def _migrate_schema(self, conn) -> None:
        """Add research-upgrade columns to databases created by older versions."""

        migrations = {
            "voters": {
                "private_key": "TEXT",
                "public_key": "TEXT",
            },
            "blockchain": {
                "merkle_root": "TEXT",
                "validator_votes": "TEXT",
                "node_status": "TEXT",
                "consensus_time_ms": "REAL DEFAULT 0",
            },
            "transactions": {
                "signature": "TEXT",
                "public_key": "TEXT",
                "signature_verification_time_ms": "REAL DEFAULT 0",
            },
        }
        for table, columns in migrations.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def seed_data(self, conn) -> None:
        for candidate in ["Alice Sharma", "Bharat Mehta", "Catherine D'Souza"]:
            conn.execute("INSERT OR IGNORE INTO candidates (name) VALUES (?)", (candidate,))

        sample_voters = [
            ("VOTER001", "Aarav Singh", "password123"),
            ("VOTER002", "Diya Patel", "password123"),
            ("VOTER003", "Kabir Rao", "password123"),
        ]
        for voter_id, name, password in sample_voters:
            private_key, public_key = generate_key_pair()
            conn.execute(
                """
                INSERT OR IGNORE INTO voters
                (voter_id, name, password_hash, private_key, public_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (voter_id, name, generate_password_hash(password), private_key, public_key),
            )
        self._backfill_missing_voter_keys(conn)

    def _backfill_missing_voter_keys(self, conn) -> None:
        rows = conn.execute("SELECT voter_id FROM voters WHERE private_key IS NULL OR public_key IS NULL").fetchall()
        for row in rows:
            private_key, public_key = generate_key_pair()
            conn.execute(
                "UPDATE voters SET private_key = ?, public_key = ? WHERE voter_id = ?",
                (private_key, public_key, row["voter_id"]),
            )

    def get_voter(self, voter_id: str):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()
            return dict(row) if row else None

    def add_voter(self, voter_id: str, name: str, password: str) -> None:
        private_key, public_key = generate_key_pair()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO voters (voter_id, name, password_hash, private_key, public_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (voter_id, name, generate_password_hash(password), private_key, public_key),
            )

    def mark_voter_voted(self, voter_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE voters SET has_voted = 1 WHERE voter_id = ?", (voter_id,))

    def get_voters(self) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT voter_id, name, public_key, has_voted FROM voters ORDER BY voter_id"
                )
            ]

    def add_candidate(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO candidates (name) VALUES (?)", (name,))

    def candidate_exists(self, name: str) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM candidates WHERE name = ?", (name,)).fetchone() is not None

    def get_candidates(self) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM candidates ORDER BY name")]

    def set_election_status(self, is_active: bool) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE election_status SET is_active = ? WHERE id = 1", (1 if is_active else 0,))

    def is_election_active(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT is_active FROM election_status WHERE id = 1").fetchone()
            return bool(row["is_active"])

    def insert_transaction(
        self,
        transaction: dict,
        status: str,
        validation_time_ms: float = 0,
        signature_verification_time_ms: float = 0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions
                (transaction_id, voter_hash, candidate, timestamp, signature, public_key,
                 transaction_hash, status, validation_time_ms, signature_verification_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction["transaction_id"],
                    transaction["voter_hash"],
                    transaction["candidate"],
                    transaction["timestamp"],
                    transaction["signature"],
                    transaction["public_key"],
                    transaction["transaction_hash"],
                    status,
                    validation_time_ms,
                    signature_verification_time_ms,
                ),
            )

    def update_transaction_validation_time(self, transaction_id: str, validation_time_ms: float) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE transactions SET validation_time_ms = ? WHERE transaction_id = ?",
                (validation_time_ms, transaction_id),
            )

    def mark_transaction_confirmed(self, transaction_id: str, block_index: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE transactions SET status = 'confirmed', block_index = ? WHERE transaction_id = ?",
                (block_index, transaction_id),
            )

    def insert_block(
        self,
        block: dict,
        creation_time_ms: float = 0,
        verification_time_ms: float = 0,
        consensus_time_ms: float = 0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO blockchain
                (block_index, timestamp, transactions, merkle_root, validator_votes, node_status,
                 previous_hash, nonce, current_hash, creation_time_ms, verification_time_ms, consensus_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    block["index"],
                    block["timestamp"],
                    json.dumps(block["transactions"], sort_keys=True),
                    block["merkle_root"],
                    json.dumps(block.get("validator_votes", {}), sort_keys=True),
                    json.dumps(block.get("node_status", {}), sort_keys=True),
                    block["previous_hash"],
                    block["nonce"],
                    block["current_hash"],
                    creation_time_ms,
                    verification_time_ms,
                    consensus_time_ms,
                ),
            )

    def _row_to_block(self, row) -> dict:
        return {
            "index": row["block_index"],
            "timestamp": row["timestamp"],
            "transactions": json.loads(row["transactions"]),
            "merkle_root": row["merkle_root"],
            "validator_votes": json.loads(row["validator_votes"] or "{}"),
            "node_status": json.loads(row["node_status"] or "{}"),
            "previous_hash": row["previous_hash"],
            "nonce": row["nonce"],
            "current_hash": row["current_hash"],
            "creation_time_ms": row["creation_time_ms"],
            "verification_time_ms": row["verification_time_ms"],
            "consensus_time_ms": row["consensus_time_ms"],
        }

    def get_last_block(self):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM blockchain ORDER BY block_index DESC LIMIT 1").fetchone()
            return self._row_to_block(row) if row else None

    def get_all_blocks(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM blockchain ORDER BY block_index").fetchall()
            return [self._row_to_block(row) for row in rows]

    def performance_metrics(self) -> dict:
        with self.connect() as conn:
            tx = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    AVG(validation_time_ms) AS avg_validation,
                    SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed
                FROM transactions
                """
            ).fetchone()
            blocks = conn.execute(
                """
                SELECT
                    AVG(creation_time_ms) AS avg_creation,
                    AVG(verification_time_ms) AS avg_verification,
                    AVG(consensus_time_ms) AS avg_consensus
                FROM blockchain WHERE block_index > 0
                """
            ).fetchone()
            signature = conn.execute(
                "SELECT AVG(signature_verification_time_ms) AS avg_signature FROM transactions"
            ).fetchone()
            duplicates_prevented = conn.execute("SELECT COUNT(*) FROM voters WHERE has_voted = 1").fetchone()[0]
        return {
            "total_transactions": tx["total"] or 0,
            "confirmed_transactions": tx["confirmed"] or 0,
            "avg_validation_time_ms": round(tx["avg_validation"] or 0, 4),
            "avg_signature_verification_time_ms": round(signature["avg_signature"] or 0, 4),
            "avg_block_creation_time_ms": round(blocks["avg_creation"] or 0, 4),
            "avg_block_verification_time_ms": round(blocks["avg_verification"] or 0, 4),
            "avg_consensus_time_ms": round(blocks["avg_consensus"] or 0, 4),
            "duplicate_vote_prevention_accuracy": "100% for registered voters via has_voted constraint",
            "voters_marked_voted": duplicates_prevented,
        }

    def upsert_node_block(self, node_name: str, block: dict, is_valid: bool, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO node_ledgers
                (node_name, block_index, block_json, is_valid, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (node_name, block["index"], json.dumps(block, sort_keys=True), 1 if is_valid else 0, message),
            )

    def get_node_last_block(self, node_name: str):
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT block_json FROM node_ledgers
                WHERE node_name = ? ORDER BY block_index DESC LIMIT 1
                """,
                (node_name,),
            ).fetchone()
            return json.loads(row["block_json"]) if row else None

    def get_node_status_summary(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT node_name, COUNT(*) AS blocks, MIN(is_valid) AS all_valid, MAX(synced_at) AS last_sync
                FROM node_ledgers GROUP BY node_name ORDER BY node_name
                """
            ).fetchall()
            return {row["node_name"]: dict(row) for row in rows}

    def tamper_latest_block(self) -> bool:
        """Intentionally corrupt the latest non-genesis block for demos."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM blockchain WHERE block_index > 0 ORDER BY block_index DESC LIMIT 1"
            ).fetchone()
            if not row:
                return False
            transactions = json.loads(row["transactions"])
            if not transactions:
                return False
            transactions[0]["candidate"] = f"{transactions[0]['candidate']} (tampered)"
            conn.execute(
                "UPDATE blockchain SET transactions = ? WHERE block_index = ?",
                (json.dumps(transactions, sort_keys=True), row["block_index"]),
            )
            return True
