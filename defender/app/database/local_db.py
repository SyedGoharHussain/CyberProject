"""
Database Layer — Local JSON storage setup.
"""
import json
import os
import time
from typing import Dict, List, Any, Optional

LOCAL_DB_FILE = "local_db.json"

class LocalDB:
    """
    Simple JSON-file-backed storage.
    Mimics a document structure.
    """
    def __init__(self, path: str = LOCAL_DB_FILE):
        self.path = path
        self._data: Dict[str, List] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self._data = json.load(f)

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    def add(self, collection: str, document: Dict) -> str:
        doc_id = document.get("id", str(time.time_ns()))
        if collection not in self._data:
            self._data[collection] = []
        self._data[collection].append({"_id": doc_id, **document})
        self._save()
        return doc_id

    def get_all(self, collection: str) -> List[Dict]:
        return self._data.get(collection, [])

    def count(self, collection: str) -> int:
        return len(self._data.get(collection, []))

    def clear_collection(self, collection: str):
        self._data[collection] = []
        self._save()

class Database:
    """
    Unified database interface using LocalDB.
    """
    COLLECTIONS = {
        "transactions": "transactions",
        "blocks":       "blocks",
        "metrics":      "metrics",
        "nodes":        "nodes",
        "logs":         "fog_logs",
    }

    def __init__(self, use_firebase: bool = False):
        self._db = LocalDB()
        self.backend_name = "Local JSON"
        print("[Database] Using local JSON storage.")

    def save_transaction(self, tx: Dict) -> str:
        clean = {k: v for k, v in tx.items()
                 if k not in ("public_key", "signature")}
        clean["pk_fingerprint"] = tx.get("public_key", "")[:16] + "..."
        clean["sig_length"]     = len(tx.get("signature", "")) // 2
        return self._db.add(self.COLLECTIONS["transactions"], clean)

    def get_transactions(self) -> List[Dict]:
        return self._db.get_all(self.COLLECTIONS["transactions"])

    def transaction_count(self) -> int:
        return self._db.count(self.COLLECTIONS["transactions"])

    def save_block(self, block_dict: Dict) -> str:
        return self._db.add(self.COLLECTIONS["blocks"], block_dict)

    def get_blocks(self) -> List[Dict]:
        return self._db.get_all(self.COLLECTIONS["blocks"])

    def save_chain(self, chain: List[Dict]):
        for block in chain:
            self.save_block(block)

    def save_metrics(self, metrics: Dict) -> str:
        metrics["saved_at"] = time.time()
        return self._db.add(self.COLLECTIONS["metrics"], metrics)

    def get_metrics(self) -> List[Dict]:
        return self._db.get_all(self.COLLECTIONS["metrics"])

    def save_fog_logs(self, logs: List[Dict]):
        for log in logs:
            self._db.add(self.COLLECTIONS["logs"], log)

    def get_fog_logs(self) -> List[Dict]:
        return self._db.get_all(self.COLLECTIONS["logs"])

    def save_nodes(self, nodes: List[Dict]):
        for n in nodes:
            self._db.add(self.COLLECTIONS["nodes"], n)

    def get_nodes(self) -> List[Dict]:
        return self._db.get_all(self.COLLECTIONS["nodes"])

    def summary(self) -> Dict:
        return {
            "backend":      self.backend_name,
            "transactions": self.transaction_count(),
            "blocks":       self._db.count(self.COLLECTIONS["blocks"]),
            "metrics":      self._db.count(self.COLLECTIONS["metrics"]),
        }
