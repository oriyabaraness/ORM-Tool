#!/usr/bin/env bash
# Launch the Bank of Israel Publications Explorer.
# Usage: ./run_app.sh   (creates/uses .venv, opens http://localhost:8501)
set -e
cd "$(dirname "$0")"
PYTHON_BIN="${ORM_TOOL_PYTHON:-$HOME/.cache/orm-revolut-venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
exec "$PYTHON_BIN" -m streamlit run app.py \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
