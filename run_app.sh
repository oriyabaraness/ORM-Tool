#!/usr/bin/env bash
# Launch the Bank of Israel Publications Explorer.
# Usage: ./run_app.sh   (creates/uses .venv, opens http://localhost:8501)
set -e
cd "$(dirname "$0")"
exec .venv/bin/python -m streamlit run app.py \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
