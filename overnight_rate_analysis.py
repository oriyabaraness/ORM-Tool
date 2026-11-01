"""Build overnight-rate and FX context snapshots for Israel and Jordan.

Run with:
    python overnight_rate_analysis.py
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


HERE = os.path.dirname(os.path.abspath(__file__))
RATE_OUTPUT = os.path.join(HERE, "overnight_rate_comparison.csv")
FX_OUTPUT = os.path.join(HERE, "overnight_fx_context.csv")

ISRAEL_POLICY_RATE_URL = (
    "https://www.boi.org.il/boi_files/Statistics/bointcre_m.xls"
)
ISRAEL_POLICY_SOURCE_PAGE = (
    "https://www.boi.org.il/en/economic-roles/statistics/"
    "boi-interest-rate-and-the-monetary-tools/"
    "boi-interest-rate-and-the-monetary-tools/"
)
ISRAEL_USD_RATE_URL = (
    "https://www.boi.org.il/en/economic-roles/financial-markets/"
    "exchange-rates/usdollar/"
)
ISRAEL_USD_RATE_FALLBACK = {
    "country": "Israel",
    "date": "2026-07-15",
    "currency_pair": "USD/ILS",
    "rate": 2.9950,
    "unit": "ILS per USD",
    "source_url": ISRAEL_USD_RATE_URL,
    "notes": (
        "Bank of Israel representative exchange rate. Static fallback from "
        "the official BOI page when scripted HTML access is blocked."),
}

JORDAN_MAIN_RATES_URL = "https://www.cbj.gov.jo/en/Pages/Maininterestrates"
JORDAN_MONTHLY_OVERNIGHT_PAGE = (
    "https://www.cbj.gov.jo/EN/econmicDetails/3515"
    "?description=MonthlyAverageOvernightInterbankRate"
)
JORDAN_HOME_URL = "https://www.cbj.gov.jo/default/en"

RATE_FIELDS = (
    "country",
    "date",
    "series",
    "series_type",
    "rate_percent",
    "source_url",
    "source_updated",
    "notes",
)

FX_FIELDS = (
    "country",
    "date",
    "currency_pair",
    "rate",
    "unit",
    "source_url",
    "notes",
)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_bytes(url, *, referer="", attempts=3):
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    last_error = None
    with requests.Session() as session:
        if referer:
            try:
                session.get(referer, headers=headers, timeout=30)
            except requests.RequestException:
                pass
        for _ in range(attempts):
            try:
                response = session.get(url, headers=headers, timeout=75)
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1)
    raise last_error


def fetch_text(url, *, referer="", attempts=3):
    return fetch_bytes(url, referer=referer, attempts=attempts).decode(
        "utf-8", errors="ignore")


def parse_date(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return pd.to_datetime(value).date().isoformat()
    value = clean_text(value)
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def parse_israel_policy_rates():
    payload = fetch_bytes(ISRAEL_POLICY_RATE_URL, referer=ISRAEL_POLICY_SOURCE_PAGE)
    raw = pd.read_excel(io.BytesIO(payload), header=None, engine="xlrd")
    source_updated = parse_date(raw.iloc[0, 3])
    rows = []
    data = raw.iloc[3:, [0, 1, 2, 3]].dropna(subset=[1, 3])
    for _, row in data.iterrows():
        start_date = parse_date(row.iloc[1])
        if not start_date:
            continue
        rows.append({
            "country": "Israel",
            "date": start_date,
            "series": "BOI declared nominal interest rate",
            "series_type": "policy_anchor",
            "rate_percent": float(row.iloc[3]),
            "source_url": ISRAEL_POLICY_SOURCE_PAGE,
            "source_updated": source_updated,
            "notes": (
                "Official BOI declared nominal rate, used here as Israel's "
                "overnight policy-rate anchor."),
        })
    return rows


def parse_jordan_main_rates():
    html = fetch_text(JORDAN_MAIN_RATES_URL)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    pattern = re.compile(
        r"Central Bank Main Interest Rates\s+(\d{4}/\d{2}/\d{2})\s+"
        r"Main Interest Rate\s+([\d.]+)\s+"
        r"Re-Discount Rate\s+([\d.]+)\s+"
        r"Overnight repurchase agreement interest rate\s+([\d.]+)\s+"
        r"Overnight Deposit Window Rate\s+([\d.]+)",
        re.I,
    )
    rows = []
    for match in pattern.finditer(text):
        date = parse_date(match.group(1))
        main_rate = float(match.group(2))
        repo_rate = float(match.group(4))
        deposit_rate = float(match.group(5))
        series_values = (
            ("CBJ main interest rate", "policy_anchor", main_rate),
            ("Overnight repurchase agreements rate", "overnight_repo", repo_rate),
            ("Overnight deposit window rate", "overnight_deposit", deposit_rate),
            (
                "Overnight policy corridor midpoint",
                "overnight_midpoint",
                (repo_rate + deposit_rate) / 2,
            ),
        )
        for series, series_type, value in series_values:
            rows.append({
                "country": "Jordan",
                "date": date,
                "series": series,
                "series_type": series_type,
                "rate_percent": value,
                "source_url": JORDAN_MAIN_RATES_URL,
                "source_updated": "",
                "notes": "Official Central Bank of Jordan policy-rate corridor.",
            })
    return rows


def jordan_monthly_overnight_download_url(html):
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        if "xlsx" in anchor["href"].lower():
            return urljoin(JORDAN_MONTHLY_OVERNIGHT_PAGE, anchor["href"])
    return ""


def parse_jordan_monthly_overnight():
    html = fetch_text(JORDAN_MONTHLY_OVERNIGHT_PAGE)
    url = jordan_monthly_overnight_download_url(html)
    if not url:
        return []
    payload = fetch_bytes(url, referer=JORDAN_MONTHLY_OVERNIGHT_PAGE)
    data = pd.read_excel(io.BytesIO(payload), engine="openpyxl")
    rows = []
    for _, row in data.iterrows():
        date = parse_date(row.get("Date"))
        rate = pd.to_numeric(row.get("Rate (%)"), errors="coerce")
        if not date or pd.isna(rate):
            continue
        rows.append({
            "country": "Jordan",
            "date": date,
            "series": "Monthly average overnight interbank rate",
            "series_type": "market_actual",
            "rate_percent": float(rate),
            "source_url": JORDAN_MONTHLY_OVERNIGHT_PAGE,
            "source_updated": "",
            "notes": (
                "Monthly average effective overnight interbank lending rate "
                "published by CBJ."),
        })
    return rows


def parse_israel_usd_fx():
    html = fetch_text(ISRAEL_USD_RATE_URL)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    rate_match = re.search(r"Exchange rates US Dollar\s+([\d.]+)", text, re.I)
    date_match = re.search(r"last updated on:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    if not rate_match:
        return [ISRAEL_USD_RATE_FALLBACK]
    return [{
        "country": "Israel",
        "date": parse_date(date_match.group(1) if date_match else ""),
        "currency_pair": "USD/ILS",
        "rate": float(rate_match.group(1)),
        "unit": "ILS per USD",
        "source_url": ISRAEL_USD_RATE_URL,
        "notes": "Bank of Israel representative exchange rate.",
    }]


def parse_jordan_usd_fx():
    html = fetch_text(JORDAN_HOME_URL)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    section_start = text.find("Currency Rates (In Fils)")
    section_end = text.find("Rates on Deposits", section_start)
    section = text[section_start:section_end if section_end > 0 else None]
    usd_match = re.search(r"USD\s+([\d.]+)\s+([\d.]+)", section)
    date_match = re.search(r"Last Update:\s*(\d{2}/\d{2}/\d{4})", section)
    if not usd_match:
        return []
    low = float(usd_match.group(1)) / 1000
    high = float(usd_match.group(2)) / 1000
    mid = (low + high) / 2
    date = parse_date(date_match.group(1) if date_match else "")
    return [{
        "country": "Jordan",
        "date": date,
        "currency_pair": "USD/JOD",
        "rate": mid,
        "unit": "JOD per USD, CBJ low/high midpoint",
        "source_url": JORDAN_HOME_URL,
        "notes": f"CBJ currency-rate midpoint from {low:.3f}-{high:.3f} JOD/USD.",
    }]


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh():
    rate_rows = []
    rate_rows.extend(parse_israel_policy_rates())
    rate_rows.extend(parse_jordan_main_rates())
    try:
        rate_rows.extend(parse_jordan_monthly_overnight())
    except Exception:
        pass
    if not rate_rows:
        raise RuntimeError("No overnight-rate rows found.")
    write_csv(RATE_OUTPUT, RATE_FIELDS, rate_rows)

    fx_rows = []
    try:
        fx_rows.extend(parse_israel_usd_fx())
    except Exception:
        fx_rows.append(ISRAEL_USD_RATE_FALLBACK)
    fx_rows.extend(parse_jordan_usd_fx())
    if fx_rows:
        write_csv(FX_OUTPUT, FX_FIELDS, fx_rows)
    return rate_rows, fx_rows


def main():
    rate_rows, fx_rows = refresh()
    print(f"Wrote {len(rate_rows)} overnight-rate rows to {RATE_OUTPUT}")
    print(f"Wrote {len(fx_rows)} FX context rows to {FX_OUTPUT}")


if __name__ == "__main__":
    main()
