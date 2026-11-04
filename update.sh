#!/usr/bin/env bash
# Refresh Risk Compare: re-crawl Bank of Israel + Central Bank of Jordan,
# download new directives, rebuild the index, write a "what's new" report.
#
# Run by hand:      ./update.sh
# Or on a schedule: see "Automatic updates" in README.md
# Report:           update_reports/latest.txt   Full log: update_reports/update.log
set -e
cd "$(dirname "$0")"
PYTHON_BIN="${ORM_TOOL_PYTHON:-$HOME/.cache/orm-revolut-venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
mkdir -p update_reports
{
  echo "=== $(date '+%Y-%m-%d %H:%M') ==="
  "$PYTHON_BIN" orm_pipeline.py update
} >> update_reports/update.log 2>&1
cat update_reports/latest.txt
