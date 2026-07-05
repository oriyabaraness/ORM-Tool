#!/usr/bin/env bash
# Reclaim disk after the pipeline has finished.
#
#   ./cleanup_storage.sh            # gzip at-rest CSVs (safe anytime the crawl is stopped)
#   ./cleanup_storage.sh --browser  # ALSO remove the Playwright Chromium cache (~550MB)
#
# The Chromium cache is only needed by boi_pdf_extractor.py (the link crawl).
# Text extraction (boi_pdf_text.py) uses plain requests, so once the crawl is
# done you can drop it and reinstall later with:  playwright install chromium
set -e
cd "$(dirname "$0")"

if pgrep -f "boi_pdf_extractor.py" >/dev/null; then
  echo "!! boi_pdf_extractor.py is still running -- CSVs are in use. Aborting."
  echo "   Re-run this once the crawl has finished."
  exit 1
fi

echo "Compressing at-rest CSVs (keeping originals as .gz)…"
for f in boi_publications_index.csv boi_pdf_links.csv boi_pdf_progress.csv \
         boi_pdf_text_manifest.csv; do
  [ -f "$f" ] && gzip -kf "$f" && echo "  $f -> $f.gz"
done

if [ "$1" = "--browser" ]; then
  echo "Removing Playwright Chromium cache…"
  rm -rf "$HOME/Library/Caches/ms-playwright" && \
    echo "  reclaimed. Reinstall later with: playwright install chromium"
fi

echo "Done. Current footprint:"
du -sh .venv boi_texts *.csv *.gz 2>/dev/null | sort -h
