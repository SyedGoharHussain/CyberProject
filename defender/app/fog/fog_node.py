"""
Fog Computing Layer — Transaction Verification Nodes
Fog nodes sit between smart devices and the blockchain.
They verify ML-DSA signatures and reject tampered transactions.
"""

import time
import uuid
from typing import Dict, List, Optional, Tuple
from app.pqc.ml_dsa import MLDSA


class FogNode:
    """
    A single fog node.
    - Receives transactions from smart devices.
    - Verifies ML-DSA signatures.
    - Forwards valid transactions to the blockchain pending pool.
    - Logs all decisions.
    """

    def __init__(self, node_id: str, location: str = "Zone-A"):
        self.node_id   = node_id
        self.location  = location
        self.queue:    List[Dict] = []
        self.logs:     List[Dict] = []
        self.stats = {
            "received":  0,
            "valid":     0,
            "rejected":  0,
            "total_verify_time_ms": 0.0,
        }
        print(f"[FogNode {self.node_id}] Online at {self.location}")

    # ── Receive ────────────────────────────────────────────────

    def receive(self, transaction: Dict) -> str:
        """Accept a transaction into the local queue."""
        self.queue.append(transaction)
        self.stats["received"] += 1
        return f"[{self.node_id}] Transaction {transaction.get('tx_id','?')} queued."

    # ── Verify ─────────────────────────────────────────────────

    def verify_transaction(self, tx: Dict) -> Tuple[bool, float]:
        """
        Verify the ML-DSA signature on a single transaction.
        Returns (is_valid, verification_time_ms).
        """
        start = time.perf_counter()
        try:
            pub_key_hex = tx.get("public_key")
            signature   = tx.get("signature")
            payload     = tx.get("payload")

            if not all([pub_key_hex, signature, payload]):
                return False, 0.0

            pk  = bytes.fromhex(pub_key_hex)
            sig = bytes.fromhex(signature)
            msg = str(payload).encode('utf-8')

            valid = MLDSA.verify(pk, msg, sig)
        except Exception as e:
            print(f"[FogNode {self.node_id}] Verification error: {e}")
            valid = False

        elapsed_ms = (time.perf_counter() - start) * 1000
        return valid, elapsed_ms

    def process_queue(self) -> List[Dict]:
        """
        Process all queued transactions.
        Returns list of verified (valid) transactions ready for blockchain.
        """
        verified = []
        while self.queue:
            tx = self.queue.pop(0)
            tx_id = tx.get("tx_id", "unknown")

            valid, t_ms = self.verify_transaction(tx)
            self.stats["total_verify_time_ms"] += t_ms

            log_entry = {
                "fog_node":       self.node_id,
                "tx_id":          tx_id,
                "valid":          valid,
                "verify_time_ms": round(t_ms, 3),
                "timestamp":      time.time(),
            }
            self.logs.append(log_entry)

            if valid:
                self.stats["valid"] += 1
                tx["fog_verified_by"]  = self.node_id
                tx["fog_verify_time"]  = round(t_ms, 3)
                verified.append(tx)
                print(f"[FogNode {self.node_id}] ✓ VALID   tx={tx_id[:12]}  ({t_ms:.1f} ms)")
            else:
                self.stats["rejected"] += 1
                print(f"[FogNode {self.node_id}] ✗ INVALID tx={tx_id[:12]}  ({t_ms:.1f} ms)")

        return verified

    # ── Stats ──────────────────────────────────────────────────

    def average_verify_time(self) -> float:
        total = self.stats["valid"] + self.stats["rejected"]
        if total == 0:
            return 0.0
        return self.stats["total_verify_time_ms"] / total

    def get_stats(self) -> Dict:
        return {
            "node_id":              self.node_id,
            "location":            self.location,
            "received":            self.stats["received"],
            "valid":               self.stats["valid"],
            "rejected":            self.stats["rejected"],
            "avg_verify_time_ms":  round(self.average_verify_time(), 3),
            "queue_length":        len(self.queue),
        }

    def __repr__(self) -> str:
        s = self.stats
        return (f"FogNode({self.node_id} | "
                f"valid={s['valid']} rejected={s['rejected']})")


class FogNetwork:
    """
    Manages 3 fog nodes with round-robin load balancing.
    In a real deployment, nodes would be geographically distributed.
    Here they are simulated on the same machine.
    """

    def __init__(self):
        self.nodes: List[FogNode] = [
            FogNode("FOG-1", "Zone-North"),
            FogNode("FOG-2", "Zone-Central"),
            FogNode("FOG-3", "Zone-South"),
        ]
        self._rr_index = 0
        print(f"[FogNetwork] {len(self.nodes)} fog nodes initialized.")

    def route(self, transaction: Dict) -> FogNode:
        """Round-robin routing to balance load across nodes."""
        node = self.nodes[self._rr_index % len(self.nodes)]
        self._rr_index += 1
        return node

    def submit(self, transaction: Dict) -> str:
        """Route a transaction to the next fog node."""
        node = self.route(transaction)
        return node.receive(transaction)

    def submit_batch(self, transactions: List[Dict]):
        """Submit a batch of transactions across all nodes."""
        for tx in transactions:
            self.submit(tx)

    def process_all(self) -> List[Dict]:
        """Process all queues across all fog nodes. Returns verified transactions."""
        all_verified = []
        for node in self.nodes:
            verified = node.process_queue()
            all_verified.extend(verified)
        return all_verified

    def get_all_stats(self) -> List[Dict]:
        return [n.get_stats() for n in self.nodes]

    def get_all_logs(self) -> List[Dict]:
        logs = []
        for n in self.nodes:
            logs.extend(n.logs)
        return sorted(logs, key=lambda x: x["timestamp"])

    def network_summary(self) -> Dict:
        total_received = sum(n.stats["received"]  for n in self.nodes)
        total_valid    = sum(n.stats["valid"]      for n in self.nodes)
        total_rejected = sum(n.stats["rejected"]   for n in self.nodes)
        all_times      = [n.stats["total_verify_time_ms"] for n in self.nodes]
        total_time     = sum(all_times)
        total_count    = total_valid + total_rejected

        return {
            "nodes":            len(self.nodes),
            "total_received":   total_received,
            "total_valid":      total_valid,
            "total_rejected":   total_rejected,
            "accept_rate_pct":  round(100 * total_valid / max(total_count, 1), 1),
            "avg_verify_ms":    round(total_time / max(total_count, 1), 3),
        }
