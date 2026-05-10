"""
Smart Microgrid Device Simulation Layer
Simulates 5 types of smart grid devices that generate signed energy transactions.
"""

import time
import uuid
import random
from typing import Dict, List, Tuple
from app.pqc.ml_dsa import MLDSA


# Energy transaction types per device class
DEVICE_PROFILES = {
    "SmartMeter":  {"role": "consumer",  "energy_range": (1,  10),  "unit": "kWh"},
    "SolarPanel":  {"role": "generator", "energy_range": (5,  50),  "unit": "kWh"},
    "Battery":     {"role": "storage",   "energy_range": (2,  30),  "unit": "kWh"},
    "EVCharger":   {"role": "consumer",  "energy_range": (7,  22),  "unit": "kWh"},
    "Consumer":    {"role": "consumer",  "energy_range": (0.5, 8),  "unit": "kWh"},
}


class SmartDevice:
    """
    A simulated smart microgrid device.
    Each device:
      - Has a unique ID and ML-DSA keypair (generated at startup).
      - Can create energy transactions (random amounts).
      - Signs transactions with its private key.
    """

    def __init__(self, device_type: str, device_id: str):
        if device_type not in DEVICE_PROFILES:
            raise ValueError(f"Unknown device type: {device_type}")

        self.device_type  = device_type
        self.device_id    = device_id
        self.profile      = DEVICE_PROFILES[device_type]
        self.tx_count     = 0
        self.sign_times:  List[float] = []

        # Generate ML-DSA keypair at device startup
        print(f"[Device {self.device_id}] Generating ML-DSA keypair...", end=" ", flush=True)
        t0 = time.perf_counter()
        self.public_key, self.private_key = MLDSA.generate_keypair()
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"Done ({elapsed:.0f} ms) | pk={len(self.public_key)}B sk={len(self.private_key)}B")

    def _build_payload(self, receiver: str, energy: float) -> str:
        """Build the canonical string that will be signed."""
        return (f"sender={self.device_id}|"
                f"receiver={receiver}|"
                f"energy={energy}{self.profile['unit']}|"
                f"role={self.profile['role']}")

    def create_transaction(self, receiver: str,
                           energy: float = None,
                           tamper: bool = False) -> Tuple[Dict, float]:
        """
        Create a signed energy transaction.

        Args:
            receiver : destination device ID
            energy   : kWh amount (random if None)
            tamper   : if True, corrupt the signature to simulate an attack

        Returns:
            (transaction_dict, sign_time_ms)
        """
        if energy is None:
            lo, hi = self.profile["energy_range"]
            energy = round(random.uniform(lo, hi), 3)

        payload   = self._build_payload(receiver, energy)
        tx_id     = str(uuid.uuid4())
        timestamp = time.time()

        # Sign the payload
        t0 = time.perf_counter()
        sig = MLDSA.sign(self.private_key, payload.encode('utf-8'))
        sign_ms = (time.perf_counter() - t0) * 1000
        self.sign_times.append(sign_ms)

        # Optionally tamper: flip a byte in the signature to simulate attack
        if tamper:
            sig_list = bytearray(sig)
            idx = random.randint(32, min(64, len(sig_list) - 1))
            sig_list[idx] ^= 0xFF
            sig = bytes(sig_list)

        tx = {
            "tx_id":      tx_id,
            "sender":     self.device_id,
            "receiver":   receiver,
            "energy":     energy,
            "unit":       self.profile["unit"],
            "role":       self.profile["role"],
            "payload":    payload,
            "public_key": self.public_key.hex(),
            "signature":  sig.hex(),
            "timestamp":  timestamp,
            "tampered":   tamper,
        }

        self.tx_count += 1
        status = "TAMPERED" if tamper else "signed"
        print(f"[Device {self.device_id}] TX {status}: {energy}{self.profile['unit']} "
              f"→ {receiver} ({sign_ms:.1f} ms)")
        return tx, sign_ms

    def avg_sign_time(self) -> float:
        if not self.sign_times:
            return 0.0
        return sum(self.sign_times) / len(self.sign_times)

    def info(self) -> Dict:
        return {
            "device_id":    self.device_id,
            "device_type":  self.device_type,
            "role":         self.profile["role"],
            "tx_count":     self.tx_count,
            "avg_sign_ms":  round(self.avg_sign_time(), 3),
            "pk_size_bytes": len(self.public_key),
            "sk_size_bytes": len(self.private_key),
        }

    def __repr__(self) -> str:
        return f"SmartDevice({self.device_id} [{self.device_type}])"


class MicrogridSimulator:
    """
    Manages the fleet of 5 smart microgrid devices.
    Orchestrates transaction generation for the simulation.
    """

    DEVICE_CONFIG = [
        ("SmartMeter", "SmartMeter_01"),
        ("SolarPanel",  "SolarPanel_01"),
        ("Battery",     "Battery_01"),
        ("EVCharger",   "EVCharger_01"),
        ("Consumer",    "Consumer_01"),
    ]

    def __init__(self):
        print("\n[Microgrid] Initializing 5 smart devices with ML-DSA keypairs...")
        print("-" * 60)
        self.devices: Dict[str, SmartDevice] = {}
        for dtype, did in self.DEVICE_CONFIG:
            self.devices[did] = SmartDevice(dtype, did)
        print("-" * 60)
        print(f"[Microgrid] All {len(self.devices)} devices ready.\n")

    def device_ids(self) -> List[str]:
        return list(self.devices.keys())

    def generate_transactions(self, count: int = 10,
                               tamper_count: int = 2) -> Tuple[List[Dict], List[float]]:
        """
        Generate `count` random energy transactions.
        `tamper_count` of them will have corrupted signatures (attack simulation).

        Returns: (transactions, sign_times_ms)
        """
        ids     = self.device_ids()
        txs     = []
        times   = []
        tamper_indices = set(random.sample(range(count), min(tamper_count, count)))

        print(f"\n[Microgrid] Generating {count} transactions "
              f"({tamper_count} tampered)...")
        print("-" * 60)

        for i in range(count):
            sender_id   = random.choice(ids)
            receiver_id = random.choice([d for d in ids if d != sender_id])
            tamper      = (i in tamper_indices)

            sender = self.devices[sender_id]
            tx, sign_ms = sender.create_transaction(receiver_id, tamper=tamper)
            txs.append(tx)
            times.append(sign_ms)

        print("-" * 60)
        print(f"[Microgrid] Generated {len(txs)} transactions "
              f"({tamper_count} intentionally tampered).\n")
        return txs, times

    def device_summary(self) -> List[Dict]:
        return [d.info() for d in self.devices.values()]
