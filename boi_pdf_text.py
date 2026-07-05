"""
Download Bank of Israel publication PDFs and extract their text.

Input : boi_pdf_links.csv  (produced by boi_pdf_extractor.py) -- the catalog of
        document links. You select which documents to process with the filters
        below; by default ALL .pdf rows are processed.

Output: boi_texts/<slug>.txt.gz   one gzip-compressed text file per PDF
                                 (read with: python3 -c "import gzip,sys;
                                  print(gzip.open(sys.argv[1],'rt').read())" FILE)
        boi_pdf_text_manifest.csv  one row per document (url, title, pages,
                                   chars, txt_path, status)

The /media/*.pdf files download directly (no Radware challenge), so this uses
plain requests. Resumable: PDFs already extracted (status ok in the manifest,
with the .txt still present) are skipped.

Usage:
  python3 boi_pdf_text.py                         # every PDF in the catalog
  python3 boi_pdf_text.py --filter "annual report"
  python3 boi_pdf_text.py --section economic-roles
  python3 boi_pdf_text.py --since 2023-01-01
  python3 boi_pdf_text.py --urls my_urls.txt      # one URL per line
  python3 boi_pdf_text.py --limit 20              # cap (handy for testing)
"""
import argparse
import csv
import gzip
import os
import re
import time
from urllib.parse import urlparse

import fitz  # pymupdf
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
LINKS = os.path.join(HERE, "boi_pdf_links.csv")
TEXT_DIR = os.path.join(HERE, "boi_texts")
MANIFEST = os.path.join(HERE, "boi_pdf_text_manifest.csv")

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")}
DELAY = 0.5  # polite pause between downloads


def slug_for(url):
    """Stable, filesystem-safe filename from a PDF URL."""
    p = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (p.path or "").strip("/")).strip("-")
    return (base or "doc")[:120]


def load_manifest_done():
    """URLs already extracted successfully and whose .txt still exists."""
    if not os.path.exists(MANIFEST):
        return set()
    try:
        m = pd.read_csv(MANIFEST)
    except Exception:
        return set()
    done = set()
    for _, r in m.iterrows():
        if str(r.get("status")) == "ok":
            tp = str(r.get("txt_path", ""))
            if tp and os.path.exists(os.path.join(HERE, tp)):
                done.add(r["doc_url"])
    return done


def select(args):
    df = pd.read_csv(LINKS)
    df = df[df["doc_type"].str.lower() == "pdf"].copy()

    if args.urls:
        with open(args.urls, encoding="utf-8") as f:
            wanted = {ln.strip() for ln in f if ln.strip()}
        df = df[df["doc_url"].isin(wanted)]
    if args.filter:
        f = args.filter.lower()
        hay = (df["doc_title"].fillna("") + " " + df["source_title"].fillna("")
               + " " + df["doc_url"]).str.lower()
        df = df[hay.str.contains(re.escape(f))]
    if args.section:
        df = df[df["section"].fillna("").str.contains(args.section, case=False)]
    if args.since:
        df = df[df["lastmod"].fillna("") >= args.since]

    df = df.drop_duplicates(subset=["doc_url"])
    if args.limit:
        df = df.head(args.limit)
    return df


def extract_one(url):
    """Return (n_pages, text). Raises on failure."""
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    if not r.content[:5] == b"%PDF-":
        raise ValueError("not a PDF response")
    doc = fitz.open(stream=r.content, filetype="pdf")
    parts = [page.get_text("text") for page in doc]
    n = doc.page_count
    doc.close()
    return n, "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", help="substring match on title/url")
    ap.add_argument("--section", help="filter by section")
    ap.add_argument("--since", help="lastmod >= this ISO date, e.g. 2023-01-01")
    ap.add_argument("--urls", help="file with one PDF URL per line")
    ap.add_argument("--limit", type=int, help="cap number of PDFs")
    args = ap.parse_args()

    if not os.path.exists(LINKS):
        raise SystemExit(f"Missing {LINKS} -- run boi_pdf_extractor.py first.")

    os.makedirs(TEXT_DIR, exist_ok=True)
    targets = select(args)
    done = load_manifest_done()
    todo = targets[~targets["doc_url"].isin(done)]
    print(f"Selected: {len(targets)} | already extracted: {len(done)} | "
          f"to process: {len(todo)}", flush=True)

    new_manifest = not os.path.exists(MANIFEST)
    mf = open(MANIFEST, "a", newline="", encoding="utf-8")
    mw = csv.writer(mf)
    if new_manifest:
        mw.writerow(["doc_url", "doc_title", "source_title", "section",
                     "lastmod", "pages", "chars", "txt_path", "status"])

    total = len(todo)
    for i, (_, row) in enumerate(todo.iterrows(), 1):
        url = row["doc_url"]
        txt_name = slug_for(url) + ".txt.gz"
        txt_rel = os.path.join("boi_texts", txt_name)
        try:
            pages, text = extract_one(url)
            # gzip-compressed on disk (~3-6x smaller than raw .txt)
            with gzip.open(os.path.join(TEXT_DIR, txt_name), "wt",
                           encoding="utf-8") as fh:
                fh.write(text)
            mw.writerow([url, row.get("doc_title", ""), row.get("source_title", ""),
                         row.get("section", ""), row.get("lastmod", ""),
                         pages, len(text), txt_rel, "ok"])
            print(f"[{i}/{total}] ok  {pages}p {len(text):>7}c  {txt_name}", flush=True)
        except Exception as e:
            mw.writerow([url, row.get("doc_title", ""), row.get("source_title", ""),
                         row.get("section", ""), row.get("lastmod", ""),
                         "", "", "", f"error: {e}"])
            print(f"[{i}/{total}] ERR {url[:70]} :: {e}", flush=True)
        mf.flush()
        time.sleep(DELAY)

    mf.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
