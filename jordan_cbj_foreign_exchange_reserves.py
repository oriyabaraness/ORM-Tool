"""Build a live Central Bank of Jordan foreign reserves index.

Run with:
    python jordan_cbj_foreign_exchange_reserves.py
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "jordan_cbj_foreign_exchange_reserves.csv")
SOURCE_URL = "https://www.cbj.gov.jo/En/List/Annual_Statistical_Bulletin"
REGULATOR = "Central Bank of Jordan"
COUNTRY = "Jordan"
CATEGORY = "Foreign Exchange Reserves"

CSV_FIELDS = (
    "country",
    "regulator",
    "title",
    "category",
    "size",
    "url",
    "source_url",
    "file_type",
    "last_seen",
    "connection_status",
)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_html():
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=45,
    )
    response.raise_for_status()
    return response.text


def page_last_update(soup):
    text = soup.get_text("\n", strip=True)
    match = re.search(r"Last update\s+(\d{4})/(\d{2})/(\d{2})", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    return dt.date.today().isoformat()


def file_type_for_url(url):
    path = urlparse(url).path.lower()
    extension = os.path.splitext(path)[1].lstrip(".")
    return extension.upper() if extension else "WEB"


def row_for_download(anchor, source_date):
    container = anchor
    for parent in anchor.parents:
        if parent.find("label") and parent.select_one(".file-size"):
            container = parent
            break

    label = container.find("label")
    size = container.select_one(".file-size")
    title = clean_text(label.get_text(" ", strip=True) if label else "")
    if "foreign reserves" not in title.lower():
        return None

    href = urljoin(SOURCE_URL, anchor.get("href", ""))
    return {
        "country": COUNTRY,
        "regulator": REGULATOR,
        "title": title,
        "category": CATEGORY,
        "size": clean_text(size.get_text(" ", strip=True) if size else ""),
        "url": href,
        "source_url": SOURCE_URL,
        "file_type": file_type_for_url(href),
        "last_seen": source_date,
        "connection_status": "fetched_live_cbj_foreign_exchange_reserves",
    }


def extract_rows_from_html(html):
    soup = BeautifulSoup(html or "", "html.parser")
    source_date = page_last_update(soup)
    rows = []
    for anchor in soup.select("a.DownloadLink[href]"):
        row = row_for_download(anchor, source_date)
        if row:
            rows.append(row)
    return dedupe_rows(rows)


def dedupe_rows(rows):
    seen = set()
    unique = []
    for row in rows:
        key = row["url"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def write_csv(rows):
    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh():
    rows = extract_rows_from_html(fetch_html())
    if not rows:
        raise RuntimeError("No foreign reserves downloads found.")
    write_csv(rows)
    return rows


def main():
    rows = refresh()
    print(f"Wrote {len(rows)} Jordan foreign reserves rows to {OUTPUT}")


if __name__ == "__main__":
    main()
