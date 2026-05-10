"""
Analytics Layer — Metrics Collection and Graph Generation
Tracks performance across all system layers and generates comparison plots.
"""

import time
import os
import json
from typing import List, Dict, Optional

try:
    import matplotlib
    matplotlib.use("Agg")       # non-interactive backend (no display needed)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False
    print("[Analytics] matplotlib not installed — graphs will be skipped.")


GRAPH_DIR = "graphs"


class MetricsCollector:
    """
    Collects timing and performance data throughout the simulation.
    Stores data for graph generation and reporting.
    """

    def __init__(self):
        self.sign_times_ms:    List[float] = []   # ML-DSA signing times
        self.verify_times_ms:  List[float] = []   # ML-DSA verify times
        self.block_times_ms:   List[float] = []   # Block creation times
        self.fog_times_ms:     List[float] = []   # Fog node processing times
        self.valid_count:      int = 0
        self.invalid_count:    int = 0
        self.keygen_times_ms:  List[float] = []

        self._sign_start:   Optional[float] = None
        self._verify_start: Optional[float] = None
        self._block_start:  Optional[float] = None

        os.makedirs(GRAPH_DIR, exist_ok=True)

    # ── Recording ─────────────────────────────────────────────

    def record_sign(self, ms: float):
        self.sign_times_ms.append(ms)

    def record_verify(self, ms: float, valid: bool):
        self.verify_times_ms.append(ms)
        if valid:
            self.valid_count += 1
        else:
            self.invalid_count += 1

    def record_block(self, ms: float):
        self.block_times_ms.append(ms)

    def record_fog(self, ms: float):
        self.fog_times_ms.append(ms)

    def record_keygen(self, ms: float):
        self.keygen_times_ms.append(ms)

    def ingest_sign_times(self, times: List[float]):
        self.sign_times_ms.extend(times)

    def ingest_fog_logs(self, logs: List[Dict]):
        for log in logs:
            ms    = log.get("verify_time_ms", 0)
            valid = log.get("valid", False)
            self.verify_times_ms.append(ms)
            self.fog_times_ms.append(ms)
            if valid:
                self.valid_count += 1
            else:
                self.invalid_count += 1

    # ── Summary ────────────────────────────────────────────────

    def _avg(self, lst: List[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    def summary(self) -> Dict:
        total_tx   = self.valid_count + self.invalid_count
        total_time = sum(self.sign_times_ms) + sum(self.verify_times_ms)

        return {
            "total_transactions": total_tx,
            "valid":              self.valid_count,
            "invalid":            self.invalid_count,
            "avg_sign_ms":        round(self._avg(self.sign_times_ms), 3),
            "avg_verify_ms":      round(self._avg(self.verify_times_ms), 3),
            "avg_block_ms":       round(self._avg(self.block_times_ms), 3),
            "avg_fog_ms":         round(self._avg(self.fog_times_ms), 3),
            "throughput_tps":     round(total_tx / (total_time / 1000 + 0.001), 2),
            "blocks_created":     len(self.block_times_ms),
        }

    # ════════════════════════════════════════════════════════════
    # Graph Generation
    # ════════════════════════════════════════════════════════════

    def generate_all_graphs(self) -> List[str]:
        """Generate all performance graphs. Returns list of saved file paths."""
        if not MATPLOTLIB_OK:
            print("[Analytics] Skipping graphs (matplotlib not available).")
            return []

        generated = []
        generated += [self._graph_sign_times()]
        generated += [self._graph_verify_times()]
        generated += [self._graph_block_times()]
        generated += [self._graph_valid_invalid()]
        generated += [self._graph_throughput()]
        generated += [self._graph_rsa_vs_mldsa()]
        generated += [self._graph_fog_delay()]

        paths = [p for p in generated if p is not None]
        print(f"\n[Analytics] {len(paths)} graphs saved to '{GRAPH_DIR}/'")
        return paths

    # ── Individual Graphs ─────────────────────────────────────

    def _style(self, ax, title: str, xlabel: str, ylabel: str):
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    def _graph_sign_times(self) -> Optional[str]:
        if not self.sign_times_ms:
            return None
        path = os.path.join(GRAPH_DIR, "1_signing_time.png")
        fig, ax = plt.subplots(figsize=(8, 4))
        x = list(range(1, len(self.sign_times_ms) + 1))
        ax.plot(x, self.sign_times_ms, color="#4C72B0", marker="o",
                linewidth=1.8, markersize=5, label="Sign time (ms)")
        avg = self._avg(self.sign_times_ms)
        ax.axhline(avg, color="red", linestyle="--", alpha=0.6, label=f"Avg: {avg:.1f} ms")
        self._style(ax, "ML-DSA Signing Time vs Transaction Number",
                    "Transaction #", "Time (ms)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_verify_times(self) -> Optional[str]:
        if not self.verify_times_ms:
            return None
        path = os.path.join(GRAPH_DIR, "2_verify_time.png")
        fig, ax = plt.subplots(figsize=(8, 4))
        x = list(range(1, len(self.verify_times_ms) + 1))
        ax.plot(x, self.verify_times_ms, color="#DD8452", marker="s",
                linewidth=1.8, markersize=5, label="Verify time (ms)")
        avg = self._avg(self.verify_times_ms)
        ax.axhline(avg, color="blue", linestyle="--", alpha=0.6, label=f"Avg: {avg:.1f} ms")
        self._style(ax, "ML-DSA Verification Time vs Transaction Number",
                    "Transaction #", "Time (ms)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_block_times(self) -> Optional[str]:
        if not self.block_times_ms:
            return None
        path = os.path.join(GRAPH_DIR, "3_block_latency.png")
        fig, ax = plt.subplots(figsize=(8, 4))
        x = list(range(1, len(self.block_times_ms) + 1))
        ax.bar(x, self.block_times_ms, color="#55A868", edgecolor="white", linewidth=0.8)
        avg = self._avg(self.block_times_ms)
        ax.axhline(avg, color="red", linestyle="--", alpha=0.7, label=f"Avg: {avg:.1f} ms")
        self._style(ax, "Blockchain Block Creation Latency",
                    "Block #", "Time (ms)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_valid_invalid(self) -> Optional[str]:
        path = os.path.join(GRAPH_DIR, "4_valid_vs_invalid.png")
        fig, ax = plt.subplots(figsize=(5, 5))
        labels  = ["Valid ✓", "Invalid ✗"]
        values  = [max(self.valid_count, 0), max(self.invalid_count, 0)]
        colors  = ["#55A868", "#C44E52"]
        explode = [0, 0.08]

        if sum(values) == 0:
            return None

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors, explode=explode,
            autopct="%1.1f%%", startangle=140,
            textprops={"fontsize": 11}
        )
        ax.set_title("Valid vs Invalid Transactions\n(Tamper Detection by Fog Nodes)",
                     fontsize=12, fontweight='bold')
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_throughput(self) -> Optional[str]:
        path = os.path.join(GRAPH_DIR, "5_throughput.png")
        fig, ax = plt.subplots(figsize=(7, 4))

        # Compute cumulative throughput over time
        if not self.verify_times_ms:
            return None

        cumulative_time = 0
        tps_list = []
        for i, ms in enumerate(self.verify_times_ms, 1):
            cumulative_time += ms / 1000  # to seconds
            tps = i / max(cumulative_time, 0.001)
            tps_list.append(tps)

        ax.plot(range(1, len(tps_list) + 1), tps_list, color="#8172B2",
                linewidth=2, marker="D", markersize=4)
        self._style(ax, "System Throughput (Transactions per Second)",
                    "Transaction #", "TPS")
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_rsa_vs_mldsa(self) -> Optional[str]:
        """
        Comparison bar chart: ML-DSA vs RSA-2048 vs ECDSA-256.
        RSA / ECDSA values are approximate benchmarks from literature.
        ML-DSA values are from our actual run.
        """
        path = os.path.join(GRAPH_DIR, "6_mldsa_vs_classical.png")
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))

        # --- Signing times (ms) ---
        algs        = ["RSA-2048", "ECDSA-256", "ML-DSA-44\n(ours)"]
        sign_vals   = [0.5, 0.08, self._avg(self.sign_times_ms) or 1.5]
        verify_vals = [0.1, 0.25, self._avg(self.verify_times_ms) or 1.2]
        colors      = ["#4C72B0", "#DD8452", "#55A868"]

        for ax, vals, title in zip(axes,
                                   [sign_vals, verify_vals],
                                   ["Signing Time (ms)", "Verification Time (ms)"]):
            bars = ax.bar(algs, vals, color=colors, width=0.5, edgecolor="white")
            ax.bar_label(bars, fmt="%.2f", fontsize=9, padding=2)
            self._style(ax, title, "Algorithm", "Time (ms)")

        axes[0].set_title("Signing Time Comparison", fontsize=12, fontweight='bold')
        axes[1].set_title("Verification Time Comparison", fontsize=12, fontweight='bold')

        fig.suptitle("ML-DSA-44 vs Classical Signatures (Post-Quantum vs Pre-Quantum)",
                     fontsize=11, y=1.02)
        plt.tight_layout()
        plt.savefig(path, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def _graph_fog_delay(self) -> Optional[str]:
        if not self.fog_times_ms:
            return None
        path = os.path.join(GRAPH_DIR, "7_fog_processing_delay.png")
        fig, ax = plt.subplots(figsize=(8, 4))

        # Split by validity using same order as logs
        valid_times   = []
        invalid_times = []
        for i, ms in enumerate(self.fog_times_ms):
            if i < self.valid_count:
                valid_times.append(ms)
            else:
                invalid_times.append(ms)

        x = list(range(1, len(self.fog_times_ms) + 1))
        ax.plot(x, self.fog_times_ms, color="#4C72B0",
                linewidth=1.5, marker="o", markersize=4, label="Fog delay (ms)")
        avg = self._avg(self.fog_times_ms)
        ax.axhline(avg, color="red", linestyle="--", alpha=0.6, label=f"Avg: {avg:.1f} ms")

        self._style(ax, "Fog Node Verification Delay per Transaction",
                    "Transaction #", "Delay (ms)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        print(f"[Analytics] Graph saved: {path}")
        return path

    def print_report(self):
        """Print a formatted summary to console."""
        s = self.summary()
        line = "─" * 50
        print(f"\n{line}")
        print("  PERFORMANCE REPORT")
        print(line)
        print(f"  Total Transactions : {s['total_transactions']}")
        print(f"  Valid              : {s['valid']}  ✓")
        print(f"  Invalid / Tampered : {s['invalid']}  ✗")
        print(f"  Blocks Created     : {s['blocks_created']}")
        print(line)
        print(f"  Avg Sign Time      : {s['avg_sign_ms']} ms")
        print(f"  Avg Verify Time    : {s['avg_verify_ms']} ms")
        print(f"  Avg Block Latency  : {s['avg_block_ms']} ms")
        print(f"  Avg Fog Delay      : {s['avg_fog_ms']} ms")
        print(f"  Throughput         : {s['throughput_tps']} TPS")
        print(line)
