#!/bin/bash
# ════════════════════════════════════════════════════════════════
#  PQC Microgrid — Defense Console launcher
#  Double-click this file in Finder, or run it from a terminal.
# ════════════════════════════════════════════════════════════════

# move to the project root (the folder that contains web/, defender/, attacker/)
cd "$(dirname "$0")/.." || exit 1

echo "──────────────────────────────────────────────"
echo "  Starting PQC Microgrid — Defense Console"
echo "──────────────────────────────────────────────"

# prefer the bundled virtual-env (it has matplotlib); fall back to python3
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
  echo "  Interpreter : .venv/bin/python  (matplotlib ready)"
else
  PY="python3"
  echo "  Interpreter : python3  (system)"
  echo "  Tip: charts need matplotlib -> pip install -r requirements.txt"
fi

echo
exec "$PY" web/server.py
