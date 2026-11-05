"""Build a local Central Bank of the Republic of Turkiye (CBRT) regulations index.

The CBRT publishes its English legal texts as PDFs spread over a few
"Legal Framework" pages. This script visits each page, collects every PDF
link, and writes them to turkey_cbrt_regulations.csv (same columns as the
Jordan CBJ index, so the app can show both side by side).

If the live site cannot be reached, it falls back to a seed list of the
official documents so the regional comparison map still has a Turkey corpus.

Note: in Turkey, most prudential banking rules (capital, liquidity, credit
risk) are issued by the BRSA / BDDK, not the central bank. The CBRT covers
monetary policy, payment systems, reserve requirements and FX operations.

Run with:
    python turkey_cbrt_index.py
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "turkey_cbrt_regulations.csv")
REGULATOR = "Central Bank of the Republic of Turkiye"
COUNTRY = "Turkey"
BASE = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/"
    "About+the+Bank/Legal+Framework/"
)
SOURCE_URL = BASE

# Each Legal Framework page and the category its PDFs belong to.
SOURCE_PAGES = (
    (BASE, "Central bank law and framework"),
    (BASE + "Payment+Systems+Regulations/", "Payment systems regulation"),
    (BASE + "Regulations+on+Operational+Transactions/",
     "Operational transactions regulation"),
    (BASE + "Articles+of+Association+of+the+Central+Bank+of+the+Republic+"
     "of+Turkiye/", "Central bank law and framework"),
)

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

_WCM = "https://www.tcmb.gov.tr/wps/wcm/connect/"

SEEDED_ROWS = (
    {
        "title": "The Law on the Central Bank of the Republic of Turkiye",
        "category": "Central bank law and framework",
        "url": _WCM + "d6ac47f4-379f-43da-bf2b-7ad855dca0ff/"
        "The_Law_on_the_Central_Bank_of_the_Republic_of_Turkiye_2026.pdf"
        "?MOD=AJPERES",
    },
    {
        "title": (
            "Law on Payment and Securities Settlement Systems, Payment "
            "Services and Electronic Money Institutions (Law No. 6493)"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "de4fb4cc-19c4-47fe-a9cb-9ef0397a8923/"
        "Payment+Systems+Law.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Regulation on Operations of Payment and Securities Settlement "
            "Systems"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "993847e8-75ab-4d7b-b74b-3a7247b192af/"
        "2.+REGULATION+ON+OPERATIONS.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Regulation on Oversight of Payment and Securities Settlement "
            "Systems"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "13b1a775-787d-44d7-8b3b-7b87f4b99e7d/"
        "3.+REGULATION+ON+OVERSIGHT.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Regulation on the Generation and the Use of TR QR Code in "
            "Payment Services"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "a3dd886f-ac9b-4e1e-b225-58821ccea36e/"
        "Regulation+on+the+Generation+and+the+Use+Of+TR+QR+Code+in+"
        "Payment+Services+with+annex.pdf?MOD=AJPERES",
    },
    {
        "title": "Regulation on the Disuse of Crypto Assets in Payments",
        "category": "Payment systems regulation",
        "url": _WCM + "c241af16-e730-45b5-bb0d-31d3af28884e/"
        "Regulation+on+the+Disuse+of+Crypto+Assets+in+Payments.pdf"
        "?MOD=AJPERES",
    },
    {
        "title": (
            "Communique on Information Systems Used in Payment and "
            "Securities Settlement Systems"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "18d691c5-9cd1-4320-9dde-68ddabe2b09f/"
        "4.Communique+on+Information+Systems.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Communique on the International Bank Account Number "
            "(No: 2008/6)"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "864e0313-07a4-4c06-ab3b-938574089c2c/"
        "COMMUNIQUE_2021_5.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "General Application Principles of Collateral, Guarantee and "
            "Credit Mechanism for Payment and Securities Settlement Systems"
        ),
        "category": "Payment systems regulation",
        "url": _WCM + "9ebf09b6-03c3-47af-8eb8-13e8b7a345fe/"
        "General+Application+Principles+of+Collateral+Mechanism-"
        "23.05.2017.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Technical Details Regarding the New Operational Framework of "
            "the Monetary Policy and the Transition Period"
        ),
        "category": "Operational transactions regulation",
        "url": _WCM + "b50b6e81-a9a6-44ae-9cf1-8ded2db8a080/"
        "Technical+Details+Regarding+the+New+Operational+Framework.pdf"
        "?MOD=AJPERES",
    },
    {
        "title": "Technical Details Regarding Turkish Lira Liquidity Management",
        "category": "Operational transactions regulation",
        "url": _WCM + "79881935-3ea5-4236-b770-9d9a7b746d0c/"
        "Technicaldetails.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Communique on Deposit and Participation Scheme for Non-Resident "
            "Turkish Citizens (YUVAM) Accounts (No: 2022/7)"
        ),
        "category": "Operational transactions regulation",
        "url": _WCM + "8e0ffd6c-93f9-46d3-a2bf-4e572f9434ae/"
        "Yuvam_Tebli%C4%9F_ENG.pdf?MOD=AJPERES",
    },
    {
        "title": (
            "Implementation Instructions for the Communique on Deposit and "
            "Participation Scheme for Non-Resident Turkish Citizens (YUVAM) "
            "Accounts"
        ),
        "category": "Operational transactions regulation",
        "url": _WCM + "06511818-45b6-409b-bdef-6762a602dbe4/"
        "YUVAM_Uygulama_Talimat%C4%B1_ENG.pdf?MOD=AJPERES",
    },
)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def doc_key(url):
    """Identify a CBRT document by the ID in its path, ignoring CACHEID."""
    path = urlsplit(url).path
    match = re.search(r"/connect/([0-9a-f-]{36})/", path)
    return match.group(1) if match else path.lower()


def make_row(title, url, category, status="fetched_official_index"):
    return {
        "country": COUNTRY,
        "regulator": REGULATOR,
        "title": clean_text(title),
        "category": category,
        "size": "",
        "url": clean_text(url),
        "source_url": SOURCE_URL,
        "file_type": "PDF",
        "last_seen": dt.date.today().isoformat(),
        "connection_status": status,
    }


def fetch_page(url):
    try:
        response = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(10, 20))
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"CBRT page not reachable ({url}): {exc}")
        return ""


def title_from_url(url):
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    name = re.sub(r"\.pdf$", "", name, flags=re.I).replace("+", " ")
    return clean_text(name.replace("_", " "))


def extract_rows_from_html(html, page_url, category):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    for anchor in soup.select("a[href]"):
        href = urljoin(page_url, anchor.get("href", ""))
        if ".pdf" not in href.lower():
            continue
        title = clean_text(anchor.get_text(" ")) or clean_text(
            anchor.get("title", "")) or title_from_url(href)
        rows.append(make_row(title, href, category))
    return rows


def dedupe_rows(rows):
    """Keep one row per document; prefer the longer (more descriptive) title."""
    best = {}
    order = []
    for row in rows:
        key = doc_key(row["url"])
        if key not in best:
            best[key] = row
            order.append(key)
        elif len(row["title"]) > len(best[key]["title"]):
            best[key]["title"] = row["title"]
    return [best[key] for key in order]


def seeded_rows():
    return [
        make_row(item["title"], item["url"], item["category"],
                 status="seeded_official_index")
        for item in SEEDED_ROWS
    ]


def write_csv(rows):
    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    for page_url, category in SOURCE_PAGES:
        rows.extend(
            extract_rows_from_html(fetch_page(page_url), page_url, category))
    rows = dedupe_rows(rows)
    if len(rows) < 5:
        print("Live CBRT pages gave too few results; using the seed list.")
        rows = seeded_rows()
    write_csv(rows)
    print(f"Wrote {len(rows)} Turkey CBRT regulation rows to {OUTPUT}")


if __name__ == "__main__":
    main()
