"""
Lightweight Blockchain for ML-DSA Microgrid System
Uses Proof-of-Authority (PoA) consensus — no mining, just chain integrity.
"""

import hashlib
import json
import time
from typing import List, Dict, Any, Optional


class Block:
    """A single block in the chain."""

    def __init__(self, index: int, transactions: List[Dict], previous_hash: str,
                 forger: str = "FogAuthority"):
        self.index         = index
        self.timestamp     = time.time()
        self.transactions  = transactions
        self.previous_hash = previous_hash
        self.forger        = forger          # PoA: who created this block
        self.nonce         = 0
        self.hash          = self._compute_hash()

    def _compute_hash(self) -> str:
        """SHA-256 hash of the block contents."""
        content = json.dumps({
            "index":         self.index,
            "timestamp":     self.timestamp,
            "transactions":  self.transactions,
            "previous_hash": self.previous_hash,
            "forger":        self.forger,
            "nonce":         self.nonce,
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index":         self.index,
            "timestamp":     self.timestamp,
            "transactions":  self.transactions,
            "previous_hash": self.previous_hash,
            "forger":        self.forger,
            "nonce":         self.nonce,
            "hash":          self.hash,
            "tx_count":      len(self.transactions),
        }

    def __repr__(self) -> str:
        return (f"Block(index={self.index}, "
                f"txs={len(self.transactions)}, "
                f"hash={self.hash[:12]}...)")


class Blockchain:
    """
    Lightweight append-only blockchain.
    Consensus: Proof of Authority — fog nodes are trusted forgers.
    Integrity: each block stores previous block's hash (tamper detection).
    """

    MAX_TX_PER_BLOCK = 5   # Transactions batched per block

    def __init__(self):
        self.chain:    List[Block] = []
        self.pending:  List[Dict]  = []   # Verified transactions waiting for a block
        self._create_genesis()

    # ── Genesis ────────────────────────────────────────────────

    def _create_genesis(self):
        """Create block 0 (genesis) — hardcoded previous hash."""
        genesis = Block(
            index         = 0,
            transactions  = [{"type": "genesis", "message": "Microgrid Blockchain Initialized"}],
            previous_hash = "0" * 64,
            forger        = "Genesis",
        )
        self.chain.append(genesis)
        print(f"[Blockchain] Genesis block created. Hash: {genesis.hash[:16]}...")

    # ── Pending Pool ────────────────────────────────────────────

    def add_pending(self, transaction: Dict) -> bool:
        """Add a fog-verified transaction to the pending pool."""
        if self._is_duplicate(transaction):
            print(f"[Blockchain] Duplicate transaction rejected: {transaction.get('tx_id','?')}")
            return False
        self.pending.append(transaction)
        return True

    def _is_duplicate(self, tx: Dict) -> bool:
        tx_id = tx.get("tx_id")
        if not tx_id:
            return False
        for block in self.chain:
            for t in block.transactions:
                if t.get("tx_id") == tx_id:
                    return True
        return any(t.get("tx_id") == tx_id for t in self.pending)

    # ── Block Creation ──────────────────────────────────────────

    def mine_block(self, forger: str = "FogAuthority") -> Optional[Block]:
        """
        Create a new block from pending transactions (PoA — no heavy work).
        Returns the new block, or None if nothing to mine.
        """
        if not self.pending:
            return None

        # Take up to MAX_TX_PER_BLOCK transactions
        batch          = self.pending[:self.MAX_TX_PER_BLOCK]
        self.pending   = self.pending[self.MAX_TX_PER_BLOCK:]
        last           = self.chain[-1]

        new_block = Block(
            index         = last.index + 1,
            transactions  = batch,
            previous_hash = last.hash,
            forger        = forger,
        )
        self.chain.append(new_block)
        print(f"[Blockchain] Block {new_block.index} mined by {forger} | "
              f"{len(batch)} txs | hash={new_block.hash[:16]}...")
        return new_block

    def mine_all(self, forger: str = "FogAuthority") -> List[Block]:
        """Mine blocks until the pending pool is empty."""
        mined = []
        while self.pending:
            b = self.mine_block(forger)
            if b:
                mined.append(b)
        return mined

    # ── Validation ──────────────────────────────────────────────

    def is_valid(self) -> bool:
        """
        Validate the entire chain:
        1. Each block's stored hash matches recomputed hash.
        2. Each block's previous_hash matches the prior block's hash.
        """
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]

            # Check stored hash is correct
            recomputed = curr._compute_hash()
            if curr.hash != recomputed:
                print(f"[Blockchain] TAMPER DETECTED — Block {i} hash mismatch!")
                return False

            # Check linkage
            if curr.previous_hash != prev.hash:
                print(f"[Blockchain] TAMPER DETECTED — Block {i} broken chain link!")
                return False

        return True

    # ── Query ───────────────────────────────────────────────────

    def get_chain(self) -> List[Dict]:
        return [b.to_dict() for b in self.chain]

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def get_block(self, index: int) -> Optional[Block]:
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None

    def pending_count(self) -> int:
        return len(self.pending)

    def block_count(self) -> int:
        return len(self.chain)

    def all_transactions(self) -> List[Dict]:
        txs = []
        for block in self.chain[1:]:   # skip genesis
            txs.extend(block.transactions)
        return txs

    def summary(self) -> Dict[str, Any]:
        return {
            "blocks":        len(self.chain),
            "total_txs":     len(self.all_transactions()),
            "pending":       len(self.pending),
            "chain_valid":   self.is_valid(),
            "latest_hash":   self.chain[-1].hash[:16] + "...",
        }

    def __repr__(self) -> str:
        return f"Blockchain(blocks={len(self.chain)}, pending={len(self.pending)})"
