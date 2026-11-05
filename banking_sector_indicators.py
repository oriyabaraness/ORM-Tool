"""
Fetch annual banking-sector indicators for Israel and Jordan.

The app uses these as higher-signal alternatives to broad macro stress proxies
when comparing regulatory directive update activity with banking conditions.
"""
from __future__ import annotations

import csv
import datetime as dt
import os

import requests


HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "banking_sector_indicators.csv")
WORLD_BANK_API = "https://api.worldbank.org/v2/country/{countries}/indicator/{code}"

COUNTRIES = {
    "ISR": "Israel",
    "JOR": "Jordan",
}

INDICATORS = (
    {
        "code": "FB.BNK.CAPA.ZS",
        "name": "Bank capital to assets ratio (%)",
        "group": "Capital adequacy",
        "metric_type": "resilience",
        "stress_direction": "lower_is_stress",
    },
    {
        "code": "FB.AST.NPER.ZS",
        "name": "Bank nonperforming loans to total gross loans (%)",
        "group": "Credit risk",
        "metric_type": "stress",
        "stress_direction": "higher_is_stress",
    },
    {
        "code": "GFDD.SI.04",
        "name": "Bank credit to bank deposits (%)",
        "group": "Loan-to-deposit activity",
        "metric_type": "activity",
        "stress_direction": "higher_is_pressure",
    },
    {
        "code": "GFDD.SI.06",
        "name": "Liquid assets to deposits and short term funding (%)",
        "group": "Liquidity coverage",
        "metric_type": "resilience",
        "stress_direction": "lower_is_stress",
    },
    {
        "code": "FD.RES.LIQU.AS.ZS",
        "name": "Bank liquid reserves to bank assets ratio (%)",
        "group": "Liquidity reserves",
        "metric_type": "resilience",
        "stress_direction": "lower_is_stress",
    },
    {
        "code": "FD.AST.PRVT.GD.ZS",
        "name": "Domestic credit to private sector by banks (% of GDP)",
        "group": "Credit growth/activity",
        "metric_type": "activity",
        "stress_direction": "higher_is_activity",
    },
    {
        "code": "FR.INR.LNDP",
        "name": "Interest rate spread (lending rate minus deposit rate, %)",
        "group": "Funding stress",
        "metric_type": "stress",
        "stress_direction": "higher_is_stress",
    },
)

FIELDNAMES = (
    "country",
    "country_code",
    "indicator_code",
    "indicator_name",
    "indicator_group",
    "metric_type",
    "stress_direction",
    "year",
    "value",
    "source_url",
    "source_last_updated",
    "fetched_at",
)


def fetch_indicator(indicator):
    params = {
        "format": "json",
        "per_page": 20000,
    }
    url = WORLD_BANK_API.format(
        countries=";".join(COUNTRIES),
        code=indicator["code"],
    )
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) < 2:
        return []

    metadata = payload[0] or {}
    source_last_updated = str(metadata.get("lastupdated", "") or "")
    fetched_at = dt.date.today().isoformat()
    source_url = f"https://data.worldbank.org/indicator/{indicator['code']}"
    rows = []
    for item in payload[1] or []:
        value = item.get("value")
        if value is None:
            continue
        country_code = str(item.get("countryiso3code", "") or "")
        if country_code not in COUNTRIES:
            continue
        try:
            year = int(item.get("date", ""))
        except ValueError:
            continue
        rows.append({
            "country": COUNTRIES[country_code],
            "country_code": country_code,
            "indicator_code": indicator["code"],
            "indicator_name": indicator["name"],
            "indicator_group": indicator["group"],
            "metric_type": indicator["metric_type"],
            "stress_direction": indicator["stress_direction"],
            "year": year,
            "value": float(value),
            "source_url": source_url,
            "source_last_updated": source_last_updated,
            "fetched_at": fetched_at,
        })
    return rows


def refresh():
    rows = []
    for indicator in INDICATORS:
        rows.extend(fetch_indicator(indicator))

    rows.sort(key=lambda row: (
        row["country"],
        row["indicator_group"],
        row["indicator_name"],
        row["year"],
    ))
    with open(OUTPUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    written = refresh()
    print(f"Wrote {len(written):,} banking-sector indicator rows to {OUTPUT}")
