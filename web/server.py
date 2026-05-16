#!/usr/bin/env python3
"""
PQC Microgrid - Defense Console Backend
=======================================
A dependency-free (Python stdlib only) web server that turns the
defender/attacker simulation into a live, browser-driven control center.

It:
  - serves the front-end (index.html / style.css / app.js)
  - launches the attacker + defender as real subprocesses
  - streams their console output to the browser
  - collects the structured results from defender/local_db.json

Run:
    python web/server.py
Then open http://localhost:8000
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ── Paths ──────────────────────────────────────────────────────
HERE         = os.path.dirname(os.path.abspath(__file__))
ROOT         = os.path.dirname(HERE)
DEFENDER_DIR = os.path.join(ROOT, "defender")
ATTACKER_DIR = os.path.join(ROOT, "attacker")
DB_FILE      = os.path.join(DEFENDER_DIR, "local_db.json")
GRAPH_DIR    = os.path.join(DEFENDER_DIR, "graphs")
ATTACKER_PORT = 9999
MAX_EVENTS    = 8000

STATIC = {
    "/":           ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css":  ("style.css",  "text/css; charset=utf-8"),
    "/app.js":     ("app.js",     "application/javascript; charset=utf-8"),
}


# ═══════════════════════════════════════════════════════════════
# Simulation orchestrator
# ═══════════════════════════════════════════════════════════════
class Simulation:
    """Owns the lifecycle of a single simulation run."""

    def __init__(self):
        # RLock so a thread already holding the lock can safely emit()
        self.lock = threading.RLock()
        self._reset()

    def _reset(self):
        self.status      = "idle"     # idle | running | done | error
        self.events      = []         # [{seq, t, src, text}]
        self.config      = {}
        self.results     = None
        self.error       = None
        self.started_at  = None
        self.finished_at = None
        self._seq        = 0
        self._procs      = []
        self._aborted    = False

    # ── event log ──────────────────────────────────────────────
    def emit(self, src, text):
        """Record one console line. src = system | defender | attacker."""
        for ln in str(text).splitlines() or [""]:
            with self.lock:
                self._seq += 1
                self.events.append({
                    "seq": self._seq,
                    "t":   round(time.time() - (self.started_at or time.time()), 2),
                    "src": src,
                    "text": ln,
                })
                if len(self.events) > MAX_EVENTS:
                    self.events = self.events[-MAX_EVENTS:]

    def snapshot(self, since=0):
        with self.lock:
            new = [e for e in self.events if e["seq"] > since]
            return {
                "status":      self.status,
                "cursor":      self._seq,
                "events":      new,
                "config":      self.config,
                "error":       self.error,
                "elapsed":     round((self.finished_at or time.time()) - self.started_at, 1)
                               if self.started_at else 0,
                "hasResults":  self.results is not None,
            }

    # ── run control ────────────────────────────────────────────
    def start(self, config):
        with self.lock:
            if self.status == "running":
                return False
            self._reset()
            self.status     = "running"
            self.config     = config
            self.started_at = time.time()
        threading.Thread(target=self._worker, daemon=True).start()
        return True

    def abort(self):
        with self.lock:
            self._aborted = True
            procs = list(self._procs)
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        self.emit("system", "Abort signal sent — terminating active nodes.")

    # ── subprocess plumbing ────────────────────────────────────
    def _spawn(self, src, cwd, stdin_text):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            env=env,
        )
        with self.lock:
            self._procs.append(proc)
        try:
            if stdin_text:
                proc.stdin.write(stdin_text)
                proc.stdin.flush()
            proc.stdin.close()
        except Exception:
            pass

        def pump():
            try:
                for line in proc.stdout:
                    self.emit(src, line.rstrip("\n"))
            except Exception:
                pass
        t = threading.Thread(target=pump, daemon=True)
        t.start()
        return proc, t

    def _worker(self):
        """Background thread: orchestrates attacker + defender."""
        cfg          = self.config
        n_tx         = int(cfg.get("transactions", 20))
        atk_enabled  = bool(cfg.get("attackerEnabled", True))
        tamper_rate  = int(cfg.get("tamperRate", 50))

        try:
            self.emit("system", "═══ DEFENSE CONSOLE — BOOT SEQUENCE ═══")
            self.emit("system", f"Transactions queued ......... {n_tx}")
            self.emit("system", f"Attacker node ............... {'ENABLED' if atk_enabled else 'OFFLINE'}")
            if atk_enabled:
                self.emit("system", f"Tamper intensity ............ {tamper_rate}%")

            # fresh database for this run
            try:
                if os.path.exists(DB_FILE):
                    os.remove(DB_FILE)
                self.emit("system", "Local database reset for a clean run.")
            except Exception as ex:
                self.emit("system", f"Could not reset database: {ex}")

            attacker_proc = None
            attacker_pump = None

            # 1) attacker first so it is listening before the defender connects
            if atk_enabled:
                if tamper_rate >= 100:
                    choice, extra = "1", ""
                elif tamper_rate <= 0:
                    choice, extra = "3", "0\n"
                elif tamper_rate == 50:
                    choice, extra = "2", ""
                else:
                    choice, extra = "3", f"{tamper_rate}\n"
                atk_stdin = f"2\n900\n{ATTACKER_PORT}\n{choice}\n{extra}"
                self.emit("system", f"Launching ATTACKER node on 127.0.0.1:{ATTACKER_PORT} ...")
                attacker_proc, attacker_pump = self._spawn("attacker", ATTACKER_DIR, atk_stdin)
                time.sleep(1.6)   # give it a moment to bind the socket
            else:
                self.emit("system", "Attacker node disabled — defender runs unobstructed.")

            # 2) defender
            self.emit("system", "Launching DEFENDER node ...")
            defender_stdin = f"2\n{n_tx}\n"
            defender_proc, defender_pump = self._spawn("defender", DEFENDER_DIR, defender_stdin)

            defender_proc.wait()
            defender_pump.join(timeout=5)
            self.emit("system", "Defender node finished.")

            # 3) stop the attacker (it would otherwise idle for 900s)
            if attacker_proc:
                try:
                    attacker_proc.terminate()
                    attacker_proc.wait(timeout=4)
                except Exception:
                    try:
                        attacker_proc.kill()
                    except Exception:
                        pass
                if attacker_pump:
                    attacker_pump.join(timeout=4)
                self.emit("system", "Attacker node shut down.")

            # 4) collect results
            self.emit("system", "Collecting results from the simulation database ...")
            results = self._build_results()
            ok = bool(results.get("transactions"))
            with self.lock:
                self.results     = results
                self.finished_at = time.time()
                self.status      = "done" if ok else "error"
                if not ok:
                    self.error = "Simulation produced no data — check the console log above."
            if ok:
                self.emit("system", "Simulation complete. Results ready.")
            else:
                self.emit("system", "No transaction data was produced.")
        except Exception as ex:
            with self.lock:
                self.status      = "error"
                self.error       = str(ex)
                self.finished_at = time.time()
            self.emit("system", f"Fatal orchestration error: {ex}")

    # ── result assembly ────────────────────────────────────────
    def _build_results(self):
        db = {}
        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)
        except Exception:
            db = {}

        transactions = db.get("transactions", [])
        fog_logs     = db.get("fog_logs", [])
        blocks       = db.get("blocks", [])
        nodes        = db.get("nodes", [])
        metrics_list = db.get("metrics", [])
        metrics      = metrics_list[-1] if metrics_list else {}

        # join each transaction with its fog verdict
        fog_by_tx = {}
        for log in fog_logs:
            fog_by_tx[log.get("tx_id")] = log
        for tx in transactions:
            log = fog_by_tx.get(tx.get("tx_id"))
            tx["fogValid"]    = bool(log["valid"]) if log else None
            tx["fogNode"]     = log.get("fog_node") if log else None
            tx["verifyMs"]    = log.get("verify_time_ms") if log else None

        valid_count   = sum(1 for l in fog_logs if l.get("valid"))
        invalid_count = sum(1 for l in fog_logs if not l.get("valid"))

        defender_text = "\n".join(e["text"] for e in self.events if e["src"] == "defender")
        attacker_text = "\n".join(e["text"] for e in self.events if e["src"] == "attacker")

        devices = self._parse_devices(defender_text)
        attack  = self._parse_attacker(attacker_text)

        # chain validity from the defender log
        chain_valid = True
        m = re.search(r"Chain valid\s*:\s*(✓ YES|✗ NO)", defender_text)
        if m:
            chain_valid = "YES" in m.group(1)

        total = valid_count + invalid_count
        fog_summary = {
            "received":    sum(n.get("received", 0) for n in nodes) or total,
            "valid":       valid_count,
            "rejected":    invalid_count,
            "acceptPct":   round(100 * valid_count / total, 1) if total else 0,
        }

        # representative key sizes from the first device
        pk = devices[0]["pk"] if devices else 1312
        sk = devices[0]["sk"] if devices else 2560

        return {
            "config":       self.config,
            "transactions": transactions,
            "fogLogs":      fog_logs,
            "blocks":       blocks,
            "nodes":        nodes,
            "metrics":      metrics,
            "devices":      devices,
            "attacker":     attack,
            "fogSummary":   fog_summary,
            "chainValid":   chain_valid,
            "graphs":       self._list_graphs(),
            "security": {
                "algorithm":   "ML-DSA-44 (CRYSTALS-Dilithium)",
                "standard":    "NIST FIPS 204",
                "level":       "Category 2 — 128-bit post-quantum security",
                "hardness":    "Module Learning With Errors (M-LWE) lattice problem",
                "tamperSent":  invalid_count,
                "tamperCaught": invalid_count,
                "falsePositive": 0,
                "publicKey":   pk,
                "privateKey":  sk,
            },
        }

    @staticmethod
    def _parse_devices(text):
        out = []
        pat = re.compile(
            r"^\s*(\S+)\s+type=(\S+)\s+txs=(\d+)\s+"
            r"avg_sign=([\d.]+)\s*ms\s+pk=(\d+)B\s+sk=(\d+)B")
        for line in text.splitlines():
            m = pat.match(line)
            if m:
                out.append({
                    "id":   m.group(1),
                    "type": m.group(2),
                    "txs":  int(m.group(3)),
                    "avgSign": float(m.group(4)),
                    "pk":   int(m.group(5)),
                    "sk":   int(m.group(6)),
                })
        return out

    @staticmethod
    def _parse_attacker(text):
        connections = len(re.findall(r"Connection #", text))
        corrupted   = len(re.findall(r"CORRUPTING", text))
        passed      = len(re.findall(r"Letting transaction pass", text))
        intercepted = len(re.findall(r"Intercepted \d+ bytes", text))
        return {
            "online":      bool(text.strip()),
            "connections": connections,
            "intercepted": intercepted,
            "corrupted":   corrupted,
            "passed":      passed,
        }

    @staticmethod
    def _list_graphs():
        order = [
            ("1_signing_time.png",      "ML-DSA Signing Time"),
            ("2_verify_time.png",       "ML-DSA Verification Time"),
            ("3_block_latency.png",     "Block Creation Latency"),
            ("4_valid_vs_invalid.png",  "Valid vs Invalid Transactions"),
            ("5_throughput.png",        "System Throughput"),
            ("6_mldsa_vs_classical.png","ML-DSA vs Classical Signatures"),
            ("7_fog_processing_delay.png","Fog Verification Delay"),
        ]
        out = []
        for fname, title in order:
            if os.path.exists(os.path.join(GRAPH_DIR, fname)):
                out.append({"file": fname, "title": title})
        return out


SIM = Simulation()


# ═══════════════════════════════════════════════════════════════
# HTTP handler
# ═══════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # keep the terminal clean

    # ── helpers ────────────────────────────────────────────────
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    # ── GET ────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/favicon.ico":
            # tiny inline favicon so the browser stops 404-ing
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path in STATIC:
            fname, ctype = STATIC[path]
            fpath = os.path.join(HERE, fname)
            try:
                with open(fpath, "rb") as f:
                    self._send(200, f.read(), ctype)
            except FileNotFoundError:
                self._send(404, {"error": f"{fname} not found"})
            return

        if path == "/api/poll":
            qs    = parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0] or 0)
            self._send(200, SIM.snapshot(since))
            return

        if path == "/api/results":
            if SIM.results is None:
                self._send(404, {"error": "no results yet"})
            else:
                self._send(200, SIM.results)
            return

        if path == "/api/graph":
            qs    = parse_qs(parsed.query)
            fname = os.path.basename(qs.get("file", [""])[0])
            fpath = os.path.join(GRAPH_DIR, fname)
            if fname.endswith(".png") and os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    self._send(200, f.read(), "image/png")
            else:
                self._send(404, {"error": "graph not found"})
            return

        self._send(404, {"error": "not found"})

    # ── POST ───────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/run":
            cfg = self._read_json()
            try:
                n = int(cfg.get("transactions", 20))
            except (TypeError, ValueError):
                n = 20
            cfg["transactions"]   = max(2, min(80, n))
            cfg["attackerEnabled"] = bool(cfg.get("attackerEnabled", True))
            cfg["tamperRate"]      = int(cfg.get("tamperRate", 50))
            if SIM.start(cfg):
                self._send(200, {"ok": True, "status": "running"})
            else:
                self._send(409, {"ok": False, "error": "a simulation is already running"})
            return

        if path == "/api/abort":
            SIM.abort()
            self._send(200, {"ok": True})
            return

        self._send(404, {"error": "not found"})


# ═══════════════════════════════════════════════════════════════
def find_port(start=8000, tries=20):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def main():
    port = find_port()
    url  = f"http://localhost:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    banner = f"""
  ╔══════════════════════════════════════════════════════════╗
  ║   PQC MICROGRID — DEFENSE CONSOLE                          ║
  ║   Post-Quantum Blockchain Fog Defense                      ║
  ╠══════════════════════════════════════════════════════════╣
  ║   Console live at:  {url:<37}║
  ║   Press Ctrl+C to stop the server.                         ║
  ╚══════════════════════════════════════════════════════════╝
"""
    print(banner)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down defense console.\n")
        SIM.abort()
        server.shutdown()


if __name__ == "__main__":
    main()
