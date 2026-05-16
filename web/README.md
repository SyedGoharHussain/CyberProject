# Defense Console — Web Front-End

A live, browser-driven control center for the Post-Quantum Blockchain Fog
Microgrid simulation. Built with the Python standard library only — **no new
dependencies**.

## What it does

- Configure a run from the browser: transaction count, attacker on/off, tamper
  intensity (0% / 50% / 100%).
- Launches the real `defender/main.py` and `attacker/main.py` as subprocesses.
- Streams both nodes' console output live into a hacker-style terminal pane.
- Renders the structured results: metrics, smart devices, fog nodes, the
  blockchain ledger, the transaction ledger, the analytics charts, and a
  post-quantum security verdict.

## Running it

From the project root (`CyberProject/`):

```bash
# use the interpreter that has matplotlib installed (the bundled venv does)
.venv/bin/python web/server.py
```

Then open <http://localhost:8000> — the browser also opens automatically.

> Charts require `matplotlib` (see `requirements.txt`). Run the server with the
> same Python that has it installed, or the run still works but the Analytics
> panel stays empty.

## How it works

| File         | Role                                                           |
|--------------|----------------------------------------------------------------|
| `server.py`  | HTTP server + simulation orchestrator + JSON API               |
| `index.html` | Page structure                                                 |
| `style.css`  | Dark terminal theme                                            |
| `app.js`     | Polling, live console, result rendering                        |

Each run resets `defender/local_db.json` so the dashboard always reflects the
current run only.
