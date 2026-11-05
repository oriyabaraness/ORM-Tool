"""Build a local Central Bank of Jordan regulations index.

The CBJ regulations page is a classic ASP.NET listing that can be slow to
stream from some networks. This script first attempts to parse the live page;
if the request stalls, it writes a small official-index seed so the regional
comparison map still has a stable Jordan corpus.

Run with:
    python jordan_cbj_index.py
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import time
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup


HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "jordan_cbj_regulations.csv")
SOURCE_URL = "https://www.cbj.gov.jo/EN/List/Instructions_"
REGULATOR = "Central Bank of Jordan"
COUNTRY = "Jordan"

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

SEEDED_ROWS = (
    {
        "title": "Climate Risk Management Regulations No. (2) of 2025",
        "size": "",
    },
    {
        "title": (
            "Financial Consumer Protection Instructions for the Banking "
            "Sector (14-2024)"
        ),
        "size": "792KB",
    },
    {
        "title": (
            "Instructions for Controls on Advertising of Products, Services, "
            "and Prizes Offered by Financial and Banking Services Providers "
            "No. (1/2025)"
        ),
        "size": "671KB",
    },
    {
        "title": (
            "Instructions for Classifying Credit Exposures and Calculating "
            "Impairment Provisions Against Them No. (8/2024) dated 30-6-2024"
        ),
        "size": "725KB",
    },
    {
        "title": "Guideline for Licensing Money Exchange Companies",
        "size": "356KB",
    },
    {
        "title": (
            "Tools for providing liquidity to Islamic banks from the Central "
            "Bank"
        ),
        "size": "",
    },
    {
        "title": (
            "Instructions for Dealing in Major Foreign Currencies and "
            "Precious Metals on Margin Basis for the Benefit of Customers "
            "No. (16/2018)"
        ),
        "size": "467KB",
    },
    {
        "title": (
            "Instructions to Islamic Banks on Legal Liquidity No. (40/2008)"
        ),
        "size": "391KB",
    },
    {
        "title": (
            "Instructions for the Minimum Capital of Licensed Banks "
            "No. (52/2010)"
        ),
        "size": "179KB",
    },
    {
        "title": (
            "Instructions of Corporate Governance for Microfinance Companies "
            "No. (10/2020) dated 6/12/2020"
        ),
        "size": "847KB",
    },
    {
        "title": (
            "Instructions for Granting Credit Facilities In Foreign Currency "
            "No. (2/2021)"
        ),
        "size": "1004KB",
    },
    {
        "title": (
            "Instructions for Banks' Owning of Stocks and Capital Shares in "
            "Companies No. (5/2021)"
        ),
        "size": "681KB",
    },
    {
        "title": (
            "Instructions For Implementing The International Financial "
            "Reporting Standard 9 No. (13/2018)"
        ),
        "size": "663KB",
    },
    {
        "title": (
            "Instructions of Financial Consumer Protection for Electronic "
            "Payment and Transfer of Funds Companies No. (3/2021) dated "
            "3/3/2021"
        ),
        "size": "722KB",
    },
    {
        "title": (
            "Regulatory Capital Instructions According to the Basel III "
            "Standard No. (67/2016) PDF"
        ),
        "size": "2001KB",
    },
    {
        "title": "Instructions of Liquidity Coverage Ratio (LCR) No. (5/2020) PDF",
        "size": "1341KB",
    },
    {
        "title": (
            "Instructions on Financial Consumer Protection for Customers of "
            "Licensed Money Exchange Companies No. (1/2021)"
        ),
        "size": "505KB",
    },
    {
        "title": (
            "Instructions of Financial Consumer Protection for Microfinance "
            "Sector No. (15/2018) dated 27/6/2018"
        ),
        "size": "2544KB",
    },
    {
        "title": (
            "The Instructions of Financial Consumer Protection for Customers "
            "with Disabilities No. (18-2018)"
        ),
        "size": "550KB",
    },
    {"title": "Domestic Systemically Important Banks (D-SIBs)", "size": "481KB"},
    {
        "title": "The Instructions of Basic Bank Account No. (1/2019)",
        "size": "326KB",
    },
    {
        "title": (
            "The Instructions of the Internal Procedures for Handling "
            "Consumers' Complaints of Financial and Banking Services "
            "Providers No. (1/2017)"
        ),
        "size": "572KB",
    },
    {"title": "FinTech Regulatory Sandbox", "size": "458KB"},
    {
        "title": (
            "Instructions on Licensing and Existence of Microfinance "
            "Companies No. (62/2016) dated 10/4/2016"
        ),
        "size": "650KB",
    },
    {
        "title": (
            "Instructions for Classification and Treating Lease-to-own Homes "
            "for Licensed Islamic Banks No. (60/2014)"
        ),
        "size": "105KB",
    },
    {"title": "Foreign Currency Instructions", "size": "44KB"},
    {
        "title": (
            "Instructions for Licensing Limited Liability Money Exchange "
            "Companies"
        ),
        "size": "46KB",
        "url": (
            "https://www.cbj.gov.jo/ebv4.0/root_storage/en/eb_list_page/"
            "c6dcdebe-07c4-4e13-9e76-41b92c639911.pdf"
        ),
    },
    {
        "title": "Guidelines to Fill the Suspicious Activity Report",
        "size": "29KB",
    },
    {"title": "Instructions of Anti Money Laundering", "size": "25KB"},
    {
        "title": "Procedures for Establishing Money Exchange Company",
        "size": "23KB",
    },
    {"title": "Terms of Money Exchange Companies Branching", "size": "19KB"},
    {
        "title": "Bonded Services Instructions No. (7/2001) dated 16/4/2001",
        "size": "3KB",
    },
    {
        "title": (
            "Instructions for Managing and Marketing Portfolios and "
            "Investment Funds in Foreign Currencies on Behalf of Clients "
            "No. (34/2007)"
        ),
        "size": "12KB",
    },
    {
        "title": (
            "Instructions Managing Banks' Assets-Liabilities in Foreign "
            "Currencies No. (32/2006)"
        ),
        "size": "24KB",
    },
    {
        "title": (
            "Instructions for the Returned Checks' Unit No. (55/2011) dated "
            "24/10/2011"
        ),
        "size": "314KB",
    },
    {"title": "Instructions for Compliance No. (33/2006)", "size": "15KB"},
    {
        "title": "Instructions of Internal Control Systems No. (35/2007)",
        "size": "44KB",
    },
    {
        "title": (
            "Instructions for Conducting Banks' Activities via Electronic "
            "Means No. (8/2001)"
        ),
        "size": "9KB",
    },
    {
        "title": (
            "Money Penalties over the Banks' Investments in Securities "
            "Instructions No. (21/2005)"
        ),
        "size": "6KB",
    },
    {
        "title": (
            "Money Penalties on the Violations of Credit Concentrations "
            "Instructions No. (23/2005)"
        ),
        "size": "12KB",
    },
    {
        "title": (
            "Instructions for Licensed Banks' Branching Inside Jordan "
            "No. (36/2007)"
        ),
        "size": "13KB",
    },
    {
        "title": "Cybersecurity Framework for Jordan Financial Sector",
        "size": "",
        "url": "https://www.cbj.gov.jo/EBV4.0/Root_Storage/EN/CSF4JFSv1-0.pdf",
    },
    {
        "title": "Instructions of Cyber Risks Resilience",
        "size": "",
        "url": (
            "https://www.cbj.gov.jo/ebv4.0/root_storage/en/eb_list_page/"
            "aa462da7-8104-4442-bd6c-0b6e9a7418f6.pdf"
        ),
    },
    {
        "title": "Instructions on Business Controls for Credit Information Companies",
        "size": "",
        "url": (
            "https://www.cbj.gov.jo/ebv4.0/root_storage/en/eb_list_page/"
            "c55acdb5-a661-413a-be83-cf15724a5ce3.pdf"
        ),
    },
    {
        "title": "Cloud Computing Guideline",
        "size": "",
        "url": (
            "https://www.cbj.gov.jo/ebv4.0/root_storage/en/eb_list_page/"
            "3064d03e-5de3-4606-bd2e-d2850f94e211.pdf"
        ),
    },
    {
        "title": (
            "Credit Information Companies Bylaw No. (36) of the Year 2011"
        ),
        "size": "",
        "url": (
            "https://www.cbj.gov.jo/ebv4.0/root_storage/en/eb_list_page/"
            "credit_information_companies_bylaw_no._%2836%29_of_the_year_2011.pdf"
        ),
    },
)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def make_row(title, size="", url="", status="fetched_official_index"):
    url = clean_text(url) or SOURCE_URL
    title = clean_text(title)
    file_type = "PDF" if ".pdf" in url.lower() or "pdf" in title.lower() else ""
    return {
        "country": COUNTRY,
        "regulator": REGULATOR,
        "title": title,
        "category": "Central bank regulation",
        "size": clean_text(size),
        "url": url,
        "source_url": SOURCE_URL,
        "file_type": file_type,
        "last_seen": dt.date.today().isoformat(),
        "connection_status": status,
    }


def fetch_official_index():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    chunks = []
    deadline = time.monotonic() + 90
    total = 0
    try:
        with requests.get(
            SOURCE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
            timeout=(15, 30),
            verify=False,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_content(32768):
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
                if total > 6_000_000 or time.monotonic() > deadline:
                    break
    except requests.RequestException as exc:
        print(f"CBJ live fetch incomplete: {exc}")
    return b"".join(chunks).decode("utf-8", errors="ignore")


def is_title_line(line):
    line = clean_text(line)
    if not line or len(line) < 6:
        return False
    rejects = {
        "type",
        "type image",
        "image: type image",
        "size",
        "view & download",
        "file name",
    }
    return line.lower() not in rejects


FILE_TYPES = {".pdf": "PDF", ".docx": "DOCX", ".doc": "DOC",
              ".xlsx": "XLSX", ".xls": "XLS"}


def file_type_for(url):
    path = url.lower().split("?", 1)[0]
    for ext, label in FILE_TYPES.items():
        if path.endswith(ext):
            return label
    return ""


def entry_for_link(anchor):
    # Climb from a download link to the smallest block holding exactly one
    # title label. The page renders each file twice (a paged table and a full
    # card list), and this pairs a link with its own title in either layout.
    node = anchor.parent
    while node is not None and node.name != "body":
        labels = node.find_all("label")
        if len(labels) == 1:
            return node, labels[0]
        if len(labels) > 1:
            return None, None
        node = node.parent
    return None, None


def extract_rows_from_items(soup):
    rows = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"]
        if "root_storage" not in href.lower() and not file_type_for(href):
            continue
        entry, label = entry_for_link(anchor)
        title = clean_text(label.get_text(" ", strip=True)) if label else ""
        if not title:
            continue
        size = next((clean_text(s.get_text()) for s in entry.find_all("span")
                     if re.fullmatch(r"[\d.,]+\s*[KMG]B",
                                     clean_text(s.get_text()), re.I)), "")
        url = urljoin(SOURCE_URL, href)
        row = make_row(title, size, url)
        row["file_type"] = file_type_for(url)
        rows.append(row)
    return rows


def extract_rows_from_html(html):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = extract_rows_from_items(soup)
    if rows:
        return rows
    # Older page layout without list-item ids. Titles and links are collected
    # separately here, so only trust them when the counts line up exactly.
    lines = [
        clean_text(line)
        for line in soup.get_text("\n", strip=True).splitlines()
        if clean_text(line)
    ]
    pdf_links = []
    for anchor in soup.select("a[href]"):
        href = urljoin(SOURCE_URL, anchor.get("href", ""))
        if ".pdf" in href.lower() or "root_storage" in href.lower():
            pdf_links.append(href)

    rows = []
    pending_size = ""
    for index, line in enumerate(lines):
        lower = line.lower()
        if lower == "size" and index + 1 < len(lines):
            pending_size = lines[index + 1]
            continue
        if lower != "file name":
            continue
        for candidate in lines[index + 1:index + 6]:
            if is_title_line(candidate):
                rows.append(make_row(candidate, pending_size))
                pending_size = ""
                break

    if len(rows) == len(pdf_links):
        for row, href in zip(rows, pdf_links):
            row["url"] = href
            row["file_type"] = file_type_for(href)
    return rows


def dedupe_rows(rows):
    seen = set()
    unique = []
    for row in rows:
        key = (row["title"].lower(), row["url"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def seeded_rows():
    return [
        make_row(
            item["title"],
            item.get("size", ""),
            item.get("url", SOURCE_URL),
            status="seeded_official_index",
        )
        for item in SEEDED_ROWS
    ]


def write_csv(rows):
    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_existing_rows():
    if not os.path.exists(OUTPUT):
        return []
    with open(OUTPUT, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _norm_title(title):
    return re.sub(r"\W+", " ", re.sub(r"\s+PDF$", "", title)).strip().lower()


def _instruction_numbers(title):
    numbers = set(re.findall(r"(\d+)\s*[/-]\s*(\d{4})", title))
    numbers |= set(re.findall(r"No\.?\s*\(?(\d+)\)?\s*of(?: the year)?\s*(\d{4})",
                              title, re.I))
    return numbers


def _same_instruction(old, new):
    a, b = _norm_title(old), _norm_title(new)
    if len(a.split()) >= 3 and len(b.split()) >= 3 and (
            a.startswith(b) or b.startswith(a)):
        return True
    words = lambda t: set(re.findall(r"[a-z]{4,}", t))
    return bool(_instruction_numbers(old) & _instruction_numbers(new)) and \
        len(words(a) & words(b)) >= 2


def merge_rows(fetched, existing):
    # The live page often stalls part way, so a fetch rarely has every entry,
    # and its titles drift (dates appended, wording tweaked). Fetched rows win;
    # earlier rows are kept only when no fetched row is the same instruction.
    kept = [row for row in existing
            if not any(_same_instruction(row["title"], f["title"])
                       for f in fetched)]
    return fetched + kept


def main():
    html = fetch_official_index()
    fetched = extract_rows_from_html(html)
    existing = read_existing_rows() or seeded_rows()
    rows = dedupe_rows(merge_rows(fetched, existing))
    write_csv(rows)
    print(f"Wrote {len(rows)} Jordan CBJ regulation rows to {OUTPUT} "
          f"({len(fetched)} from the live page)")


if __name__ == "__main__":
    main()
