# How to Run the Defense Console

A step-by-step guide to launching the web front-end for the
Post-Quantum Blockchain Fog Microgrid project.

---

## What you need

- **macOS / Linux / Windows** with **Python 3.8+** (the project was built on 3.12).
- That's it. The web console uses **only the Python standard library** — no
  `pip install` is required just to run it.
- Charts (the Analytics panel) need **matplotlib**. The bundled virtual-env
  `.venv/` already has it, so if you use the launcher below, charts just work.

---

## The easy way (recommended)

### macOS — double-click

1. Open the `CyberProject/web/` folder in Finder.
2. Double-click **`start.command`**.
3. A terminal window opens, the server starts, and your browser opens
   automatically at <http://localhost:8000>.

> First time only: if macOS says *"cannot be opened because it is from an
> unidentified developer"*, right-click `start.command` → **Open** → **Open**.

### Any system — one command

Open a terminal **in the `CyberProject/` folder** and run:

```bash
# macOS / Linux — uses the bundled venv that already has matplotlib
.venv/bin/python web/server.py
```

```bat
:: Windows
.venv\Scripts\python web\server.py
```

No virtual-env? Plain Python works too (charts need matplotlib):

```bash
python3 web/server.py
```

Then open <http://localhost:8000> in your browser if it didn't open by itself.

---

## Using the console

1. **Configuration panel** — set:
   - **Energy Transactions** — how many signed transactions to simulate.
   - **Attacker Node** — `ENGAGED` (a malicious node intercepts traffic) or
     `OFFLINE`.
   - **Tamper Intensity** — `0% / 50% / 100%` of intercepted transactions whose
     signature the attacker corrupts.
2. Click **`> RUN SIMULATION`**.
3. Watch **Live Telemetry** — the real defender and attacker nodes stream their
   console output here in real time.
4. When the run finishes, the rest of the page fills in: metrics, smart
   devices, fog nodes, the blockchain, the transaction ledger, the analytics
   charts (click any chart to enlarge), and the security verdict.

A run with the default 20 transactions takes only a few seconds.

---

## Stopping it

- Press **Ctrl + C** in the terminal window to stop the server.
- Closing the terminal/`start.command` window also stops it.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser didn't open | Open <http://localhost:8000> manually. |
| `Address already in use` | An old server is still running — the server auto-picks the next free port (8001, 8002 …); check the terminal banner for the real URL. |
| Analytics panel is empty | matplotlib isn't installed for the Python you used. Run with `.venv/bin/python`, or `pip install -r requirements.txt`. |
| "a simulation is already running" | Wait for the current run to finish, or click **ABORT**. |
| Page looks unstyled | Hard-refresh the browser (Cmd/Ctrl + Shift + R). |

---

## How it works (short version)

`web/server.py` is a small standard-library HTTP server. When you click
**RUN**, it launches the real `attacker/main.py` and `defender/main.py` as
separate processes, streams their output to the browser, and reads the
structured results from `defender/local_db.json`. The browser side
(`index.html`, `style.css`, `app.js`) polls the server and renders everything.

Each run starts from a clean `defender/local_db.json` so the dashboard always
shows the current run only.
