"""Build a Bank of Israel foreign exchange reserves data snapshot.

Run with:
    python israel_boi_fx_reserves.py
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import tempfile

import fitz
import requests


HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "israel_boi_fx_reserves.csv")
INDEX_OUTPUT = os.path.join(HERE, "israel_boi_fx_reserves_index.csv")
SOURCE_URL = (
    "https://www.boi.org.il/en/communication-and-publications/press-releases/"
    "foreign-exchange-reserves-at-the-bank-of-israel-june-2026/"
)
SOURCE_PDF_URL = (
    "https://www.boi.org.il/media/vywlht3x/"
    "foreign-exchange-reserves-at-the-bank-of-israel-june-2026.pdf"
)
REGULATOR = "Bank of Israel"
COUNTRY = "Israel"
CATEGORY = "Foreign Exchange Reserves"
TITLE = "Israel Foreign Exchange Reserves"

CSV_FIELDS = (
    "date",
    "reserves_excluding_imf_usd_million",
    "reserves_excluding_imf_note",
    "reserves_at_imf_usd_million",
    "reserves_at_imf_note",
    "total_foreign_exchange_reserves_usd_million",
    "total_foreign_exchange_reserves_note",
    "release_date",
    "source_page_url",
    "source_pdf_url",
)

INDEX_FIELDS = (
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

MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)


def fetch_pdf():
    response = requests.get(
        SOURCE_PDF_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=45,
    )
    response.raise_for_status()
    return response.content


def extract_pdf_text(pdf_bytes):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf_bytes)
        path = fh.name
    try:
        with fitz.open(path) as doc:
            return "\n".join(page.get_text("text") for page in doc)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def clean_line(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_release_date(text):
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},\s+\d{4}\b",
        text,
    )
    if not match:
        return dt.date.today().isoformat()
    return dt.datetime.strptime(match.group(0), "%B %d, %Y").date().isoformat()


def parse_value(value):
    match = re.match(r"^([\d,]+)([A-Za-z]*)$", clean_line(value))
    if not match:
        return None
    number, note = match.groups()
    return int(number.replace(",", "")), note


def extract_rows_from_text(text):
    release_date = parse_release_date(text)
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    date_re = re.compile(rf"^({'|'.join(MONTHS)})\s+(\d{{4}})$")
    rows = []
    for index, line in enumerate(lines):
        if not date_re.match(line):
            continue

        values = []
        offset = index + 1
        while offset < len(lines) and len(values) < 3:
            parsed = parse_value(lines[offset])
            if parsed:
                values.append(parsed)
            elif date_re.match(lines[offset]):
                break
            offset += 1

        if len(values) != 3:
            continue

        excluding_imf, at_imf, total = values
        rows.append({
            "date": line,
            "reserves_excluding_imf_usd_million": excluding_imf[0],
            "reserves_excluding_imf_note": excluding_imf[1],
            "reserves_at_imf_usd_million": at_imf[0],
            "reserves_at_imf_note": at_imf[1],
            "total_foreign_exchange_reserves_usd_million": total[0],
            "total_foreign_exchange_reserves_note": total[1],
            "release_date": release_date,
            "source_page_url": SOURCE_URL,
            "source_pdf_url": SOURCE_PDF_URL,
        })
    return rows


def write_data_csv(rows):
    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_index_csv(rows):
    last_seen = rows[0]["release_date"] if rows else dt.date.today().isoformat()
    data_url = "file://" + OUTPUT
    index_row = {
        "country": COUNTRY,
        "regulator": REGULATOR,
        "title": TITLE,
        "category": CATEGORY,
        "size": f"{len(rows):,} rows",
        "url": data_url,
        "source_url": SOURCE_URL,
        "file_type": "CSV",
        "last_seen": last_seen,
        "connection_status": "fetched_live_boi_foreign_exchange_reserves",
    }
    with open(INDEX_OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=INDEX_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(index_row)


def refresh():
    rows = extract_rows_from_text(extract_pdf_text(fetch_pdf()))
    if not rows:
        raise RuntimeError("No Bank of Israel foreign reserves rows found.")
    write_data_csv(rows)
    write_index_csv(rows)
    return rows


def main():
    rows = refresh()
    print(f"Wrote {len(rows)} Israel FX reserve rows to {OUTPUT}")


if __name__ == "__main__":
    main()
