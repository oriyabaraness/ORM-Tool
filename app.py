"""
ORM Tool -- a Streamlit UI over the crawl/extract pipeline.

  Design direction: see DESIGN.md (regulatory risk comparison workspace).
Run with:  streamlit run app.py   (from inside the .venv)

Text extraction reuses boi_pdf_text.extract_one, and results are cached per URL.
"""
import gzip
import html
import io
import os
import re
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

from banking_sector_indicators import (
    OUTPUT as BANKING_SECTOR_INDICATORS,
    refresh as refresh_banking_sector_indicators,
)
from boi_pdf_viewer import build_pdf_viewer_model, download_pdf, render_pdf_viewer
from boi_pdf_text import extract_one, slug_for
from israel_boi_fx_reserves import (
    INDEX_OUTPUT as ISRAEL_BOI_FX_RESERVES_INDEX,
    OUTPUT as ISRAEL_BOI_FX_RESERVES_DATA,
    SOURCE_URL as ISRAEL_BOI_FX_RESERVES_SOURCE,
    refresh as refresh_israel_boi_fx_reserves,
)
from jordan_cbj_financial_stability import (
    OUTPUT as JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS,
    SOURCE_URL as JORDAN_CBJ_FINANCIAL_STABILITY_SOURCE,
    refresh as refresh_jordan_financial_stability_reports,
)
from jordan_cbj_foreign_exchange_reserves import (
    OUTPUT as JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES,
    SOURCE_URL as JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES_SOURCE,
    refresh as refresh_jordan_foreign_exchange_reserves,
)
from jordan_cbj_fx_rates import (
    OUTPUT as JORDAN_CBJ_FX_RATES,
    SOURCE_URL as JORDAN_CBJ_FX_RATES_SOURCE,
    refresh as refresh_jordan_fx_rates,
)
from overnight_rate_analysis import (
    FX_OUTPUT as OVERNIGHT_FX_CONTEXT,
    RATE_OUTPUT as OVERNIGHT_RATE_COMPARISON,
    refresh as refresh_overnight_rate_analysis,
)
from orm_compare import render_risk_compare_section

HERE = os.path.dirname(os.path.abspath(__file__))
LINKS = os.path.join(HERE, "boi_pdf_links.csv")
BANKING_SUPERVISION = os.path.join(HERE, "boi_banking_supervision_index.csv")
PUBLICATIONS_INDEX = os.path.join(HERE, "boi_publications_index.csv")
PROPER_CONDUCT_DIRECTIVES = os.path.join(
    HERE, "boi_proper_conduct_directives.csv")
JORDAN_CBJ_REGULATIONS = os.path.join(HERE, "jordan_cbj_regulations.csv")
MANIFEST = os.path.join(HERE, "boi_pdf_text_manifest.csv")
LOCAL_MANIFEST = os.path.join(HERE, "boi_pdf_text_manifest.local.csv")
TEXT_DIR = os.path.join(HERE, "boi_texts")
INDEX_LOG = os.path.join(HERE, "boi_pdf_text_index.log")
INDEX_PID = os.path.join(HERE, "boi_pdf_text_index.pid")

st.set_page_config(page_title="ORM Tool",
                   page_icon="🏦", layout="wide")


@st.cache_data(show_spinner=False)
def load_catalog(mtime):  # mtime busts the cache when the file changes
    df = pd.read_csv(LINKS)
    for c in ("doc_title", "source_title", "section", "lastmod", "doc_type"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df.drop_duplicates(subset=["doc_url"])


@st.cache_data(show_spinner=False)
def load_banking_supervision(mtime):
    if not os.path.exists(BANKING_SUPERVISION):
        return pd.DataFrame()
    df = pd.read_csv(BANKING_SUPERVISION, dtype=str)
    for c in ("url", "title", "section", "lang", "lastmod"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df.drop_duplicates(subset=["url"])


@st.cache_data(show_spinner=False)
def load_publications_index(mtime):
    if not os.path.exists(PUBLICATIONS_INDEX):
        return pd.DataFrame()
    df = pd.read_csv(PUBLICATIONS_INDEX, dtype=str).fillna("")
    return df.drop_duplicates(subset=["url"])


@st.cache_data(show_spinner=False)
def load_proper_conduct_metadata(mtime):
    if not os.path.exists(PROPER_CONDUCT_DIRECTIVES):
        return pd.DataFrame()
    df = pd.read_csv(PROPER_CONDUCT_DIRECTIVES, dtype=str).fillna("")
    return df.drop_duplicates(subset=["url"])


@st.cache_data(show_spinner=False)
def load_jordan_cbj_regulations(mtime):
    if not os.path.exists(JORDAN_CBJ_REGULATIONS):
        return pd.DataFrame()
    df = pd.read_csv(JORDAN_CBJ_REGULATIONS, dtype=str).fillna("")
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["title", "url"])


@st.cache_data(show_spinner=False)
def load_jordan_financial_stability_reports(mtime):
    if not os.path.exists(JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS):
        return pd.DataFrame()
    df = pd.read_csv(
        JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS, dtype=str).fillna("")
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["title", "url"])


@st.cache_data(show_spinner=False)
def load_jordan_foreign_exchange_reserves(mtime):
    if not os.path.exists(JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES):
        return pd.DataFrame()
    df = pd.read_csv(
        JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES, dtype=str).fillna("")
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["title", "url"])


@st.cache_data(show_spinner=False)
def load_jordan_fx_rates(mtime):
    if not os.path.exists(JORDAN_CBJ_FX_RATES):
        return pd.DataFrame()
    df = pd.read_csv(JORDAN_CBJ_FX_RATES, dtype=str).fillna("")
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["title", "url"])


@st.cache_data(show_spinner=False)
def load_israel_boi_fx_reserves(mtime):
    if not os.path.exists(ISRAEL_BOI_FX_RESERVES_INDEX):
        return pd.DataFrame()
    df = pd.read_csv(ISRAEL_BOI_FX_RESERVES_INDEX, dtype=str).fillna("")
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["title", "url"])


@st.cache_data(show_spinner=False)
def load_israel_boi_fx_reserves_data(mtime):
    if not os.path.exists(ISRAEL_BOI_FX_RESERVES_DATA):
        return pd.DataFrame()
    df = pd.read_csv(ISRAEL_BOI_FX_RESERVES_DATA, dtype=str).fillna("")
    expected = (
        "date", "total_foreign_exchange_reserves_usd_million",
        "release_date", "source_page_url", "source_pdf_url")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["date"])


@st.cache_data(show_spinner=False)
def load_overnight_rate_comparison(mtime):
    if not os.path.exists(OVERNIGHT_RATE_COMPARISON):
        return pd.DataFrame()
    df = pd.read_csv(OVERNIGHT_RATE_COMPARISON, dtype=str).fillna("")
    expected = (
        "country", "date", "series", "series_type", "rate_percent",
        "source_url", "source_updated", "notes")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["country", "date", "series"])


@st.cache_data(show_spinner=False)
def load_overnight_fx_context(mtime):
    if not os.path.exists(OVERNIGHT_FX_CONTEXT):
        return pd.DataFrame()
    df = pd.read_csv(OVERNIGHT_FX_CONTEXT, dtype=str).fillna("")
    expected = (
        "country", "date", "currency_pair", "rate", "unit",
        "source_url", "notes")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["country", "currency_pair", "date"])


@st.cache_data(show_spinner=False)
def load_banking_sector_indicators(mtime):
    if not os.path.exists(BANKING_SECTOR_INDICATORS):
        return pd.DataFrame()
    df = pd.read_csv(BANKING_SECTOR_INDICATORS, dtype=str).fillna("")
    expected = (
        "country", "country_code", "indicator_code", "indicator_name",
        "indicator_group", "metric_type", "stress_direction", "year",
        "value", "source_url", "source_last_updated", "fetched_at")
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.drop_duplicates(subset=["country", "indicator_code", "year"])


def ensure_jordan_financial_stability_reports(max_age_hours=24):
    age_seconds = time.time() - file_mtime(JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS)
    if os.path.exists(JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS):
        if age_seconds < max_age_hours * 3600:
            return None
    try:
        rows = refresh_jordan_financial_stability_reports()
        load_jordan_financial_stability_reports.clear()
        return f"Updated {len(rows):,} Jordan Financial Stability Report rows."
    except Exception as exc:
        return f"Jordan Financial Stability Report refresh failed: {exc}"


def ensure_jordan_foreign_exchange_reserves(max_age_hours=24):
    age_seconds = (
        time.time() - file_mtime(JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES))
    if os.path.exists(JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES):
        if age_seconds < max_age_hours * 3600:
            return None
    try:
        rows = refresh_jordan_foreign_exchange_reserves()
        load_jordan_foreign_exchange_reserves.clear()
        return f"Updated {len(rows):,} Jordan foreign reserves rows."
    except Exception as exc:
        return f"Jordan foreign reserves refresh failed: {exc}"


def ensure_jordan_fx_rates(max_age_hours=24):
    age_seconds = time.time() - file_mtime(JORDAN_CBJ_FX_RATES)
    if os.path.exists(JORDAN_CBJ_FX_RATES):
        if age_seconds < max_age_hours * 3600:
            return None
    try:
        rows = refresh_jordan_fx_rates()
        load_jordan_fx_rates.clear()
        return f"Updated {len(rows):,} Jordan FX rates rows."
    except Exception as exc:
        return f"Jordan FX rates refresh failed: {exc}"


def ensure_israel_boi_fx_reserves(max_age_hours=24):
    age_seconds = time.time() - file_mtime(ISRAEL_BOI_FX_RESERVES_INDEX)
    if os.path.exists(ISRAEL_BOI_FX_RESERVES_INDEX):
        if age_seconds < max_age_hours * 3600:
            return None
    try:
        rows = refresh_israel_boi_fx_reserves()
        load_israel_boi_fx_reserves.clear()
        load_israel_boi_fx_reserves_data.clear()
        if "load_tabular_source" in globals():
            load_tabular_source.clear()
        return f"Updated {len(rows):,} Israel foreign reserves rows."
    except Exception as exc:
        return f"Israel foreign reserves refresh failed: {exc}"


def ensure_overnight_rate_analysis(max_age_hours=24):
    paths = (OVERNIGHT_RATE_COMPARISON, OVERNIGHT_FX_CONTEXT)
    if all(os.path.exists(path) for path in paths):
        newest_stale_age = max(time.time() - file_mtime(path) for path in paths)
        if newest_stale_age < max_age_hours * 3600:
            return None
    try:
        rate_rows, fx_rows = refresh_overnight_rate_analysis()
        load_overnight_rate_comparison.clear()
        load_overnight_fx_context.clear()
        return (
            f"Updated {len(rate_rows):,} overnight-rate rows and "
            f"{len(fx_rows):,} FX context rows.")
    except Exception as exc:
        return f"Overnight-rate refresh failed: {exc}"


def ensure_banking_sector_indicators(max_age_hours=24 * 7):
    age_seconds = time.time() - file_mtime(BANKING_SECTOR_INDICATORS)
    if os.path.exists(BANKING_SECTOR_INDICATORS):
        if age_seconds < max_age_hours * 3600:
            return None
    try:
        rows = refresh_banking_sector_indicators()
        load_banking_sector_indicators.clear()
        return f"Updated {len(rows):,} banking-sector indicator rows."
    except Exception as exc:
        return f"Banking-sector indicator refresh failed: {exc}"


def combine_jordan_docs(*frames):
    expected = (
        "country", "regulator", "title", "category", "size", "url",
        "source_url", "file_type", "last_seen", "connection_status")
    ready = []
    for frame in frames:
        if frame is None or frame.empty:
            continue
        copy = frame.copy()
        for column in expected:
            if column not in copy.columns:
                copy[column] = ""
            copy[column] = copy[column].fillna("").astype(str)
        ready.append(copy[list(expected)])
    if not ready:
        return pd.DataFrame(columns=expected)
    return pd.concat(ready, ignore_index=True).drop_duplicates(
        subset=["title", "url"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_text_manifest(signature):
    frames = []
    for path in (MANIFEST, LOCAL_MANIFEST):
        if os.path.exists(path):
            frames.append(pd.read_csv(path))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    for c in ("doc_url", "doc_title", "source_title", "section", "lastmod",
              "txt_path", "status"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df


@st.cache_data(show_spinner=False)
def load_search_docs(signature):
    manifest = load_text_manifest(
        (file_mtime(MANIFEST), file_mtime(LOCAL_MANIFEST)))
    if manifest.empty:
        return pd.DataFrame()

    rows = []
    ok = manifest[manifest["status"].astype(str).str.lower() == "ok"]
    for _, row in ok.drop_duplicates(subset=["doc_url"]).iterrows():
        txt_path = str(row.get("txt_path", ""))
        full_path = os.path.join(HERE, txt_path)
        if not txt_path or not os.path.exists(full_path):
            continue
        try:
            with gzip.open(full_path, "rt", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue

        rows.append({
            "source_title": row.get("source_title", ""),
            "doc_title": row.get("doc_title", ""),
            "section": row.get("section", ""),
            "lastmod": row.get("lastmod", ""),
            "pages": row.get("pages", ""),
            "chars": row.get("chars", len(text)),
            "doc_url": row.get("doc_url", ""),
            "txt_path": txt_path,
            "_text": text,
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Extracting text…")
def get_text(url):
    """Download + extract a single PDF. Cached per URL. Returns (pages, text)."""
    return extract_one(url)


@st.cache_data(show_spinner="Preparing reader...")
def get_reader_model(url, title):
    pdf_bytes = download_pdf(url)
    model = build_pdf_viewer_model(
        pdf_bytes, title=title, source_url=url, render_scale=1.75)
    return model, pdf_bytes


def file_mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


SECTION_LABELS = {
    "communication-and-publications": "Communications and Publications",
    "economic-roles": "Economic Roles",
    "proper-conduct": "Proper Conduct Directives",
}


REGIONAL_BANKING_MARKETS = (
    {
        "country": "Israel",
        "code": "IL",
        "latitude": 31.78,
        "longitude": 35.22,
        "regulator": "Bank of Israel",
        "role": "Indexed BOI corpus",
    },
    {
        "country": "Jordan",
        "code": "JO",
        "latitude": 31.95,
        "longitude": 35.93,
        "regulator": "Central Bank of Jordan",
        "role": "Comparison target",
    },
    {
        "country": "Egypt",
        "code": "EG",
        "latitude": 30.04,
        "longitude": 31.24,
        "regulator": "Central Bank of Egypt",
        "role": "Comparison target",
    },
    {
        "country": "Saudi Arabia",
        "code": "SA",
        "latitude": 24.71,
        "longitude": 46.67,
        "regulator": "Saudi Central Bank",
        "role": "Comparison target",
    },
    {
        "country": "United Arab Emirates",
        "code": "AE",
        "latitude": 24.45,
        "longitude": 54.38,
        "regulator": "Central Bank of the UAE",
        "role": "Comparison target",
    },
    {
        "country": "Qatar",
        "code": "QA",
        "latitude": 25.29,
        "longitude": 51.53,
        "regulator": "Qatar Central Bank",
        "role": "Comparison target",
    },
    {
        "country": "Bahrain",
        "code": "BH",
        "latitude": 26.22,
        "longitude": 50.58,
        "regulator": "Central Bank of Bahrain",
        "role": "Comparison target",
    },
    {
        "country": "Kuwait",
        "code": "KW",
        "latitude": 29.38,
        "longitude": 47.98,
        "regulator": "Central Bank of Kuwait",
        "role": "Comparison target",
    },
    {
        "country": "Oman",
        "code": "OM",
        "latitude": 23.59,
        "longitude": 58.41,
        "regulator": "Central Bank of Oman",
        "role": "Comparison target",
    },
    {
        "country": "Turkey",
        "code": "TR",
        "latitude": 39.93,
        "longitude": 32.86,
        "regulator": "Central Bank of the Republic of Turkey",
        "role": "Comparison target",
    },
    {
        "country": "Lebanon",
        "code": "LB",
        "latitude": 33.89,
        "longitude": 35.50,
        "regulator": "Banque du Liban",
        "role": "Comparison target",
    },
    {
        "country": "Iraq",
        "code": "IQ",
        "latitude": 33.31,
        "longitude": 44.36,
        "regulator": "Central Bank of Iraq",
        "role": "Comparison target",
    },
    {
        "country": "Palestinian Territories",
        "code": "PS",
        "latitude": 31.90,
        "longitude": 35.20,
        "regulator": "Palestine Monetary Authority",
        "role": "Comparison target",
    },
    {
        "country": "Cyprus",
        "code": "CY",
        "latitude": 35.17,
        "longitude": 33.36,
        "regulator": "Central Bank of Cyprus",
        "role": "Comparison target",
    },
)


PUBLICATION_TYPE_RULES = (
    (r"\bproper conduct directive\b|proper conduct of banking business",
     "Proper Conduct Directives"),
    (r"\bbanking system annual survey\b|israel'?s banking system",
     "Banking System Surveys"),
    (r"\bannual report\b", "Annual Reports"),
    (r"\bmonetary policy report\b|\bmonetary policy committee\b|"
     r"\binterest rate decision\b|\bpress briefing on monetary policy\b",
     "Monetary Policy"),
    (r"\bstaff forecast\b|\binflation forecast\b|\bforecast\b",
     "Forecasts and Inflation Assessments"),
    (r"\bfinancial stability\b", "Financial Stability"),
    (r"\bexchange rates?\b|\beffective exchange rates?\b|\bfx rates?\b",
     "FX Rates"),
    (r"\bforeign exchange reserves?\b|\breserves? in\b",
     "Foreign Exchange Reserves"),
    (r"\bpayment and settlement\b|\bpayment systems?\b|\bmeans of payment\b",
     "Payment and Settlement Systems"),
    (r"\bdiscussion paper\b|\bworking paper\b|\bresearch department\b|"
     r"\bselected research\b|\bstud(y|ies)\b",
     "Research and Working Papers"),
    (r"\bpress release\b|\bremarks by\b|\baddress by\b|\bspeech\b|"
     r"\bgovernor\b",
     "Speeches and Press Releases"),
    (r"\bstatistical appendix\b|\bcomplementary data\b",
     "Statistical Data"),
)

PUBLICATION_TYPE_ORDER = (
    "Annual Reports",
    "Banking System Surveys",
    "Proper Conduct Directives",
    "Words and Lectures Greetings and Deputies",
    "Financial Consumer Protection Report",
    "Monthly Statement of Assets and Liabilities",
    "Journal of Applied Economic Studies",
    "Research and Working Papers",
    "The Central Bank of Jordan - 50 Years of Achievements",
    "Archived Of Monthly Statistical Bulletin",
    "External Trade Developments",
    "Monthly Economic and Monetary Developments",
    "Financial Stability Report",
    "Annual Report",
    "Special Issues",
    "Insurance Publications",
    "Foreign Investment Survey",
    "Regulations and Instructions",
    "Monetary Policy",
    "Forecasts and Inflation Assessments",
    "Financial Stability",
    "FX Rates",
    "Foreign Exchange Reserves",
    "Payment and Settlement Systems",
    "Research and Working Papers",
    "Statistical Data",
    "Speeches and Press Releases",
    "Communications and Publications",
    "Economic Roles",
    "Other Publications",
)

PUBLICATION_TYPE_DESCRIPTIONS = {
    "Annual Reports": (
        "Yearly Bank of Israel reports, chapters, tables, and supporting "
        "materials for long-range economic review."),
    "Banking System Surveys": (
        "Banking supervision surveys, system reviews, data tables, and "
        "supporting materials on Israel's banking sector."),
    "Proper Conduct Directives": (
        "Supervisory directives and circular-linked source PDFs for banking "
        "corporations."),
    "Words and Lectures Greetings and Deputies": (
        "Official speeches, lectures, remarks, greetings, and deputy governor "
        "public communications."),
    "Financial Consumer Protection Report": (
        "Financial consumer protection publications and reporting from the "
        "Central Bank of Jordan."),
    "Monthly Statement of Assets and Liabilities": (
        "Monthly balance-sheet style statements and assets/liabilities "
        "publication pages."),
    "Journal of Applied Economic Studies": (
        "Applied economic studies and journal publications from the Jordan "
        "central-bank library."),
    "The Central Bank of Jordan - 50 Years of Achievements": (
        "Commemorative publications covering the CBJ's institutional history "
        "and achievements."),
    "Archived Of Monthly Statistical Bulletin": (
        "Archived monthly statistical bulletin publications and historical "
        "statistical releases."),
    "External Trade Developments": (
        "External trade development reports and related macroeconomic "
        "publication pages."),
    "Monthly Economic and Monetary Developments": (
        "Monthly economic and monetary development reports from the Jordan "
        "publication library."),
    "Financial Stability Report": (
        "Jordan financial stability report publications and related source "
        "records."),
    "Annual Report": (
        "Central Bank of Jordan annual reports and report landing pages."),
    "Special Issues": (
        "Special issue publications and topical central-bank releases."),
    "Insurance Publications": (
        "Insurance-sector publications from the Central Bank of Jordan."),
    "Foreign Investment Survey": (
        "Foreign investment survey publications and source pages."),
    "Regulations and Instructions": (
        "Connected regional regulatory instructions and official country source "
        "records."),
    "Monetary Policy": (
        "Interest-rate decisions, monetary policy reports, committee materials, "
        "and policy briefings."),
    "Forecasts and Inflation Assessments": (
        "Research Department forecasts, inflation assessments, and related "
        "macroeconomic outlook documents."),
    "Financial Stability": (
        "Financial Stability Reports and publications on systemic risk, markets, "
        "and resilience."),
    "FX Rates": (
        "Representative exchange-rate tables, effective exchange-rate pages, "
        "and central-bank currency-rate data sources."),
    "Foreign Exchange Reserves": (
        "Foreign exchange reserve updates, reserve investment reports, and "
        "market reference publications."),
    "Payment and Settlement Systems": (
        "Payment systems, settlement infrastructure, means of payment, and "
        "oversight publications."),
    "Research and Working Papers": (
        "Discussion papers, research articles, selected studies, and working "
        "paper series."),
    "Statistical Data": (
        "Statistical appendices, data files, bulletins, and complementary "
        "published datasets."),
    "Speeches and Press Releases": (
        "Press releases, remarks, speeches, and official public communications."),
    "Communications and Publications": (
        "General publication pages and communication materials from the Bank of "
        "Israel site."),
    "Economic Roles": (
        "Economic-role pages, regulatory resources, market data, and policy "
        "reference materials."),
}

CATALOG_ACCENTS = (
    "#006d7e",
    "#6fa6bd",
    "#c0ad5c",
    "#5f986c",
    "#9b2f4a",
    "#5d3f85",
    "#008f88",
    "#8fa87a",
    "#ac5d73",
    "#7e89ad",
    "#c38551",
    "#596f7a",
)

COUNTRY_ORDER = (
    "Israel",
    "Jordan",
    "Egypt",
    "Saudi Arabia",
    "United Arab Emirates",
    "Qatar",
    "Bahrain",
    "Kuwait",
    "Oman",
    "Turkey",
    "Lebanon",
    "Iraq",
    "Palestinian Territories",
    "Cyprus",
)

JORDAN_PUBLICATION_SECTIONS = (
    (
        "Words and Lectures Greetings and Deputies",
        "https://www.cbj.gov.jo/EN/List/Words_and_Lectures_Greetings_and_Deputies",
    ),
    (
        "Financial Consumer Protection Report",
        "https://www.cbj.gov.jo/EN/List/Financial_Consumer_Protection_Report",
    ),
    (
        "Monthly Statement of Assets and Liabilities",
        "https://www.cbj.gov.jo/EN/List/Monthly_Statement_of_Assets_and_Liabilities",
    ),
    (
        "Journal of Applied Economic Studies",
        "https://www.cbj.gov.jo/EN/List/Journal_of_Applied_Economic_Studies",
    ),
    (
        "Research and Working Papers",
        "https://www.cbj.gov.jo/EN/List/Research_and_working_papers",
    ),
    (
        "The Central Bank of Jordan - 50 Years of Achievements",
        "https://www.cbj.gov.jo/EN/List/The_Central_Bank_of_Jordan_50_Years_of_Achievements",
    ),
    (
        "Archived Of Monthly Statistical Bulletin",
        "https://www.cbj.gov.jo/EN/List/Annual_Statistical_Bulletin",
    ),
    (
        "External Trade Developments",
        "https://www.cbj.gov.jo/EN/List/External_Trade_Developments",
    ),
    (
        "Monthly Economic and Monetary Developments",
        "https://www.cbj.gov.jo/EN/List/Monthly_Economic_and_Monetary_Developments",
    ),
    (
        "Financial Stability Report",
        "https://www.cbj.gov.jo/EN/List/Financial_Stability_Report",
    ),
    (
        "Annual Report",
        "https://www.cbj.gov.jo/EN/List/Annual_Report",
    ),
    (
        "Special Issues",
        "https://www.cbj.gov.jo/EN/List/Special_Issues",
    ),
    (
        "Insurance Publications",
        "https://www.cbj.gov.jo/EN/List/Insurance_publications",
    ),
    (
        "Foreign Investment Survey",
        "https://www.cbj.gov.jo/EN/List/Foreign_Investment_Survey",
    ),
)

LEGAL_COMPARISON_RULES = (
    (
        "Capital adequacy",
        ("capital", "basel", "tier 1", "leverage", "risk weighted"),
    ),
    (
        "Liquidity risk",
        ("liquidity", "lcr", "liquid assets", "funding", "cash flow"),
    ),
    (
        "Credit risk",
        ("credit risk", "credit exposure", "impairment", "provision", "default"),
    ),
    (
        "Consumer protection",
        ("consumer protection", "customer", "complaint", "disclosure", "fees"),
    ),
    (
        "Housing and lending",
        ("housing", "mortgage", "loan", "lending", "credit facilities"),
    ),
    (
        "Governance and audit",
        ("governance", "board", "director", "audit", "auditor", "internal control"),
    ),
    (
        "Reporting and disclosure",
        ("report", "reporting", "annual report", "statement", "disclosure"),
    ),
    (
        "Financial stability",
        ("financial stability", "systemic", "resilience", "stress", "crisis"),
    ),
    (
        "Monetary policy",
        ("monetary", "interest rate", "inflation", "policy rate", "forecast"),
    ),
    (
        "Foreign exchange",
        ("foreign exchange", "currency", "exchange rate", "reserves", "fx"),
    ),
    (
        "Payments and cards",
        ("payment", "settlement", "card", "transfer", "electronic payment"),
    ),
    (
        "Cyber and operational resilience",
        ("cyber", "technology", "operational", "incident", "business continuity"),
    ),
    (
        "AML/CFT",
        ("anti money laundering", "terrorist financing", "aml", "suspicious"),
    ),
    (
        "Insurance supervision",
        ("insurance", "insurer", "policyholder", "premium"),
    ),
)

FX_COMPARISON_RULES = (
    (
        "Exchange-rate table",
        ("exchange rate", "exchange rates", "representative exchange", "fx rate"),
    ),
    (
        "Major currencies",
        ("major foreign currencies", "currency", "usd", "eur", "dollar", "euro"),
    ),
    (
        "Central-bank source",
        ("central bank", "bank of israel", "central bank of jordan", "cbj"),
    ),
    (
        "Official data file",
        ("xlsx", "data", "table", "statistical", "download"),
    ),
    (
        "Foreign reserves context",
        ("foreign exchange reserves", "reserves", "reserve assets"),
    ),
    (
        "Market reference",
        ("financial markets", "foreign exchange market", "effective exchange"),
    ),
)


def section_label(section):
    section = str(section or "").strip()
    if not section:
        return "Other Publications"
    return SECTION_LABELS.get(section, section.replace("-", " ").title())


def classify_publication_type(row):
    section = str(row.get("section", "") or "").strip()
    text = " ".join(
        str(row.get(col, "") or "")
        for col in ("source_title", "doc_title", "section", "doc_url")
    ).lower()

    for pattern, label in PUBLICATION_TYPE_RULES:
        if re.search(pattern, text):
            return label
    return section_label(section)


def with_publication_type(df):
    result = df.copy()
    if result.empty:
        result["publication_type"] = pd.Series(dtype=str)
        return result
    inferred = result.apply(classify_publication_type, axis=1)
    if "publication_type" not in result.columns:
        result["publication_type"] = inferred
    else:
        existing = result["publication_type"].fillna("").astype(str).str.strip()
        result["publication_type"] = existing.where(existing.str.len() > 0, inferred)
    return result


def country_rank(label):
    try:
        return COUNTRY_ORDER.index(str(label or ""))
    except ValueError:
        return len(COUNTRY_ORDER)


def ordered_countries(labels):
    cleaned = [str(label) for label in labels if str(label or "").strip()]
    return sorted(cleaned, key=lambda label: (country_rank(label), label))


def publication_type_rank(label):
    try:
        return PUBLICATION_TYPE_ORDER.index(str(label or ""))
    except ValueError:
        return len(PUBLICATION_TYPE_ORDER)


def ordered_publication_types(labels):
    cleaned = [str(label) for label in labels if str(label or "").strip()]
    return sorted(cleaned, key=lambda label: (publication_type_rank(label), label))


def order_catalog_by_publication_type(df):
    if df.empty:
        return df.copy()
    result = df.copy()
    if "publication_type" not in result.columns:
        result = with_publication_type(result)
    if "country" not in result.columns:
        result["country"] = ""
    result["_publication_type_rank"] = result["publication_type"].apply(
        publication_type_rank)
    result["_country_rank"] = result["country"].apply(country_rank)
    result["_title_sort"] = result["source_title"].fillna("").str.lower()
    result = result.sort_values(
        [
            "_country_rank", "country", "_publication_type_rank",
            "publication_type", "lastmod", "_title_sort",
        ],
        ascending=[True, True, True, True, False, True],
        kind="mergesort")
    return result.drop(
        columns=["_publication_type_rank", "_country_rank", "_title_sort"])


def order_fx_comparison_options(df):
    if df.empty:
        return df.copy()
    result = df.copy()
    if "publication_type" not in result.columns:
        result = with_publication_type(result)
    for column in ("country", "doc_type", "source_title", "lastmod"):
        if column not in result.columns:
            result[column] = ""
        result[column] = result[column].fillna("").astype(str)
    result["_tabular_rank"] = result["doc_type"].str.lower().isin(
        ("csv", "tsv", "xlsx", "xls")).map({True: 0, False: 1})
    result["_country_rank"] = result["country"].apply(country_rank)
    result["_publication_type_rank"] = result["publication_type"].apply(
        publication_type_rank)
    result["_title_sort"] = result["source_title"].str.lower()
    result = result.sort_values(
        [
            "_tabular_rank", "_country_rank", "country",
            "_publication_type_rank", "publication_type", "lastmod",
            "_title_sort",
        ],
        ascending=[True, True, True, True, True, False, True],
        kind="mergesort")
    return result.drop(
        columns=[
            "_tabular_rank", "_country_rank", "_publication_type_rank",
            "_title_sort",
        ])


def build_jordan_publication_section_rows():
    rows = []
    for title, url in JORDAN_PUBLICATION_SECTIONS:
        rows.append({
            "source_page": url,
            "source_title": title,
            "section": "jordan-publications",
            "lastmod": "",
            "doc_title": "Publication section",
            "doc_url": url,
            "doc_type": "web",
            "country": "Jordan",
            "regulator": "Central Bank of Jordan",
            "publication_type": title,
            "size": "",
            "connection_status": "official_publication_section",
        })
    return pd.DataFrame(rows)


def build_country_catalog(catalog, jordan_docs=None):
    boi = catalog.copy()
    boi["country"] = "Israel"
    boi["regulator"] = "Bank of Israel"
    boi["size"] = ""
    boi["connection_status"] = "local_boi_index"
    boi = with_publication_type(boi)
    frames = [boi]

    if jordan_docs is not None and not jordan_docs.empty:
        frames.append(build_jordan_publication_section_rows())
        jordan = jordan_docs.copy()
        for col in (
                "country", "regulator", "title", "category", "size", "url",
                "source_url", "file_type", "last_seen", "connection_status"):
            if col not in jordan.columns:
                jordan[col] = ""
            jordan[col] = jordan[col].fillna("").astype(str)

        publication_type = jordan["category"].replace({
            "Central bank regulation": "Regulations and Instructions",
            "central bank regulation": "Regulations and Instructions",
        })
        publication_type = publication_type.where(
            publication_type.str.len() > 0, "Regulations and Instructions")
        doc_type = jordan["file_type"].str.lower().where(
            jordan["file_type"].str.len() > 0, "web")

        jordan_rows = pd.DataFrame({
            "source_page": jordan["source_url"].where(
                jordan["source_url"].str.len() > 0, jordan["url"]),
            "source_title": jordan["title"],
            "section": "jordan-cbj",
            "lastmod": jordan["last_seen"],
            "doc_title": jordan["category"].where(
                jordan["category"].str.len() > 0,
                "Central bank regulation"),
            "doc_url": jordan["url"],
            "doc_type": doc_type,
            "country": jordan["country"].where(
                jordan["country"].str.len() > 0, "Jordan"),
            "regulator": jordan["regulator"].where(
                jordan["regulator"].str.len() > 0, "Central Bank of Jordan"),
            "publication_type": publication_type,
            "size": jordan["size"],
            "connection_status": jordan["connection_status"],
        })
        frames.append(jordan_rows)

    combined = pd.concat(frames, ignore_index=True)
    for col in (
            "source_page", "source_title", "section", "lastmod", "doc_title",
            "doc_url", "doc_type", "country", "regulator",
            "publication_type", "size", "connection_status"):
        if col not in combined.columns:
            combined[col] = ""
        combined[col] = combined[col].fillna("").astype(str)
    return combined


def build_directive_comparison_catalog(directives, jordan_docs=None):
    frames = []

    if directives is not None and not directives.empty:
        israel = directives.copy()
        for col in (
                "url", "directive_number", "title_display", "subject_display",
                "lastmod", "file_url", "circular_number"):
            if col not in israel.columns:
                israel[col] = ""
            israel[col] = israel[col].fillna("").astype(str)

        directive_title = (
            "Proper Conduct Directive "
            + israel["directive_number"]
            + " - "
            + israel["title_display"])
        directive_rows = pd.DataFrame({
            "source_page": israel["url"],
            "source_title": directive_title.str.replace(
                r"\s+-\s*$", "", regex=True),
            "section": "proper-conduct",
            "lastmod": israel["lastmod"],
            "doc_title": israel["subject_display"].where(
                israel["subject_display"].str.len() > 0, "Directive PDF"),
            "doc_url": israel["file_url"],
            "doc_type": "pdf",
            "country": "Israel",
            "regulator": "Bank of Israel",
            "publication_type": "Proper Conduct Directives",
            "size": "",
            "connection_status": "proper_conduct_directive",
            "directive_number": israel["directive_number"],
            "circular_number": israel["circular_number"],
        })
        directive_rows = directive_rows[
            directive_rows["doc_url"].astype(str).str.len() > 0]
        frames.append(directive_rows)

    if jordan_docs is not None and not jordan_docs.empty:
        jordan = jordan_docs.copy()
        for col in (
                "country", "regulator", "title", "category", "size", "url",
                "source_url", "file_type", "last_seen",
                "connection_status"):
            if col not in jordan.columns:
                jordan[col] = ""
            jordan[col] = jordan[col].fillna("").astype(str)
        regulatory_mask = jordan["category"].str.contains(
            r"\b(regulation|regulations|instruction|instructions)\b",
            case=False,
            regex=True,
            na=False)
        jordan = jordan[regulatory_mask].copy()

        file_type = jordan["file_type"].str.lower()
        inferred_pdf = jordan["url"].str.lower().str.endswith(".pdf")
        doc_type = file_type.where(file_type.str.len() > 0, "web")
        doc_type = doc_type.where(~inferred_pdf, "pdf")
        jordan_rows = pd.DataFrame({
            "source_page": jordan["source_url"].where(
                jordan["source_url"].str.len() > 0, jordan["url"]),
            "source_title": jordan["title"],
            "section": "jordan-cbj",
            "lastmod": jordan["last_seen"],
            "doc_title": jordan["category"].where(
                jordan["category"].str.len() > 0,
                "Central bank regulation"),
            "doc_url": jordan["url"],
            "doc_type": doc_type,
            "country": jordan["country"].where(
                jordan["country"].str.len() > 0, "Jordan"),
            "regulator": jordan["regulator"].where(
                jordan["regulator"].str.len() > 0, "Central Bank of Jordan"),
            "publication_type": "Regulations and Instructions",
            "size": jordan["size"],
            "connection_status": jordan["connection_status"].where(
                jordan["connection_status"].str.len() > 0,
                "central_bank_regulation"),
            "directive_number": "",
            "circular_number": "",
        })
        jordan_rows = jordan_rows[
            jordan_rows["source_title"].astype(str).str.len() > 0]
        frames.append(jordan_rows)

    columns = (
        "source_page", "source_title", "section", "lastmod", "doc_title",
        "doc_url", "doc_type", "country", "regulator", "publication_type",
        "size", "connection_status", "directive_number", "circular_number")
    if not frames:
        return pd.DataFrame(columns=columns)

    combined = pd.concat(frames, ignore_index=True)
    for col in columns:
        if col not in combined.columns:
            combined[col] = ""
        combined[col] = combined[col].fillna("").astype(str)
    return combined.drop_duplicates(
        subset=["country", "source_title", "doc_url"]).reset_index(drop=True)


def fx_publication_type(row):
    text = " ".join(
        str(row.get(col, "") or "")
        for col in ("source_title", "doc_title", "publication_type", "doc_url")
    ).lower()
    if "foreign exchange reserves" in text or "reserves" in text:
        return "Foreign Exchange Reserves"
    if re.search(r"\bexchange rates?\b|\beffective exchange rates?\b|\bfx\b", text):
        return "FX Rates"
    return "FX Rates"


def build_fx_comparison_catalog(catalog, jordan_docs=None, israel_fx_docs=None):
    frames = []
    columns = (
        "source_page", "source_title", "section", "lastmod", "doc_title",
        "doc_url", "doc_type", "country", "regulator", "publication_type",
        "size", "connection_status", "directive_number", "circular_number")

    if israel_fx_docs is not None and not israel_fx_docs.empty:
        israel_data = israel_fx_docs.copy()
        for col in (
                "country", "regulator", "title", "category", "size", "url",
                "source_url", "file_type", "last_seen",
                "connection_status"):
            if col not in israel_data.columns:
                israel_data[col] = ""
            israel_data[col] = israel_data[col].fillna("").astype(str)
        file_type = israel_data["file_type"].str.lower()
        doc_type = file_type.where(file_type.str.len() > 0, "csv")
        israel_data_rows = pd.DataFrame({
            "source_page": israel_data["source_url"].where(
                israel_data["source_url"].str.len() > 0, israel_data["url"]),
            "source_title": israel_data["title"],
            "section": "israel-boi-data",
            "lastmod": israel_data["last_seen"],
            "doc_title": israel_data["category"].where(
                israel_data["category"].str.len() > 0, "FX data source"),
            "doc_url": israel_data["url"],
            "doc_type": doc_type,
            "country": israel_data["country"].where(
                israel_data["country"].str.len() > 0, "Israel"),
            "regulator": israel_data["regulator"].where(
                israel_data["regulator"].str.len() > 0, "Bank of Israel"),
            "publication_type": israel_data["category"].where(
                israel_data["category"].str.len() > 0,
                "Foreign Exchange Reserves"),
            "size": israel_data["size"],
            "connection_status": israel_data["connection_status"],
            "directive_number": "",
            "circular_number": "",
        })
        frames.append(israel_data_rows)

    publications = load_publications_index(file_mtime(PUBLICATIONS_INDEX))
    if publications is not None and not publications.empty:
        israel = publications.copy()
        for col in ("section", "title", "url", "lastmod"):
            if col not in israel.columns:
                israel[col] = ""
            israel[col] = israel[col].fillna("").astype(str)
        haystack = (
            israel["title"] + " " + israel["url"] + " " + israel["section"]
        ).str.lower()
        fx_mask = haystack.str.contains(
            r"\b(?:exchange rates?|effective exchange rates?|foreign exchange reserves?)\b",
            regex=True,
            na=False)
        israel = israel[fx_mask].copy()
        if not israel.empty:
            israel_rows = pd.DataFrame({
                "source_page": israel["url"],
                "source_title": israel["title"],
                "section": israel["section"],
                "lastmod": israel["lastmod"],
                "doc_title": "FX data source",
                "doc_url": israel["url"],
                "doc_type": "web",
                "country": "Israel",
                "regulator": "Bank of Israel",
                "publication_type": "",
                "size": "",
                "connection_status": "boi_publication_index",
                "directive_number": "",
                "circular_number": "",
            })
            israel_rows["publication_type"] = israel_rows.apply(
                fx_publication_type, axis=1)
            frames.append(israel_rows)

    if catalog is not None and not catalog.empty:
        israel_pdf = catalog.copy()
        for col in (
                "source_page", "source_title", "section", "lastmod",
                "doc_title", "doc_url", "doc_type"):
            if col not in israel_pdf.columns:
                israel_pdf[col] = ""
            israel_pdf[col] = israel_pdf[col].fillna("").astype(str)
        haystack = (
            israel_pdf["source_title"] + " " + israel_pdf["doc_title"] + " "
            + israel_pdf["doc_url"] + " " + israel_pdf["section"]
        ).str.lower()
        fx_mask = haystack.str.contains(
            r"\b(?:exchange rates?|effective exchange rates?|foreign exchange reserves?)\b",
            regex=True,
            na=False)
        israel_pdf = israel_pdf[fx_mask].copy()
        if not israel_pdf.empty:
            pdf_rows = pd.DataFrame({
                "source_page": israel_pdf["source_page"],
                "source_title": israel_pdf["source_title"],
                "section": israel_pdf["section"],
                "lastmod": israel_pdf["lastmod"],
                "doc_title": israel_pdf["doc_title"],
                "doc_url": israel_pdf["doc_url"],
                "doc_type": israel_pdf["doc_type"].where(
                    israel_pdf["doc_type"].str.len() > 0, "pdf"),
                "country": "Israel",
                "regulator": "Bank of Israel",
                "publication_type": "",
                "size": "",
                "connection_status": "local_boi_index",
                "directive_number": "",
                "circular_number": "",
            })
            pdf_rows["publication_type"] = pdf_rows.apply(
                fx_publication_type, axis=1)
            frames.append(pdf_rows)

    if jordan_docs is not None and not jordan_docs.empty:
        jordan = jordan_docs.copy()
        for col in (
                "country", "regulator", "title", "category", "size", "url",
                "source_url", "file_type", "last_seen",
                "connection_status"):
            if col not in jordan.columns:
                jordan[col] = ""
            jordan[col] = jordan[col].fillna("").astype(str)
        haystack = (
            jordan["title"] + " " + jordan["category"] + " "
            + jordan["url"] + " " + jordan["file_type"]
        ).str.lower()
        fx_mask = haystack.str.contains(
            r"\b(?:fx rates?|exchange rates?|foreign exchange reserves?)\b",
            regex=True,
            na=False)
        jordan = jordan[fx_mask].copy()
        if not jordan.empty:
            file_type = jordan["file_type"].str.lower()
            doc_type = file_type.where(file_type.str.len() > 0, "web")
            jordan_rows = pd.DataFrame({
                "source_page": jordan["source_url"].where(
                    jordan["source_url"].str.len() > 0, jordan["url"]),
                "source_title": jordan["title"],
                "section": "jordan-cbj",
                "lastmod": jordan["last_seen"],
                "doc_title": jordan["category"].where(
                    jordan["category"].str.len() > 0, "FX data source"),
                "doc_url": jordan["url"],
                "doc_type": doc_type,
                "country": jordan["country"].where(
                    jordan["country"].str.len() > 0, "Jordan"),
                "regulator": jordan["regulator"].where(
                    jordan["regulator"].str.len() > 0,
                    "Central Bank of Jordan"),
                "publication_type": jordan["category"].where(
                    jordan["category"].str.len() > 0, "FX Rates"),
                "size": jordan["size"],
                "connection_status": jordan["connection_status"],
                "directive_number": "",
                "circular_number": "",
            })
            frames.append(jordan_rows)

    if not frames:
        return pd.DataFrame(columns=columns)

    combined = pd.concat(frames, ignore_index=True)
    for col in columns:
        if col not in combined.columns:
            combined[col] = ""
        combined[col] = combined[col].fillna("").astype(str)
    combined = combined[combined["doc_url"].str.len() > 0].copy()
    return combined.drop_duplicates(
        subset=["country", "source_title", "doc_url"]).reset_index(drop=True)


def publication_row_title(row):
    title = str(row.get("source_title", "") or "").strip()
    if title:
        return title
    doc_title = str(row.get("doc_title", "") or "").strip()
    if doc_title:
        return doc_title
    return str(row.get("doc_url", "") or "Untitled publication").rsplit("/", 1)[-1]


def format_publication_option(row):
    title = publication_row_title(row)
    publication = str(row.get("publication_type", "") or "").strip()
    doc_type = str(row.get("doc_type", "") or "").strip().upper()
    date = str(row.get("lastmod", "") or "").strip()[:10]
    parts = [title]
    if publication and publication.lower() not in title.lower():
        parts.append(publication)
    if doc_type:
        parts.append(doc_type)
    if date:
        parts.append(date)
    return " · ".join(parts)


def legal_text_for_row(row, reader_docs):
    parts = [
        row.get("country", ""),
        row.get("regulator", ""),
        row.get("publication_type", ""),
        row.get("source_title", ""),
        row.get("doc_title", ""),
        row.get("section", ""),
        row.get("connection_status", ""),
    ]
    doc_url = str(row.get("doc_url", "") or "")
    if doc_url and reader_docs is not None and not reader_docs.empty:
        matches = reader_docs[reader_docs["doc_url"] == doc_url]
        if not matches.empty:
            # Keep comparison quick while still using enough of the text for
            # theme detection.
            parts.append(str(matches.iloc[0].get("_text", ""))[:120000])
    return " ".join(str(part or "") for part in parts)


def legal_notes_for_row(row, reader_docs):
    text = legal_text_for_row(row, reader_docs).lower()
    notes = []
    for label, terms in LEGAL_COMPARISON_RULES:
        if any(term in text for term in terms):
            notes.append(label)

    publication_type = str(row.get("publication_type", "") or "")
    doc_title = str(row.get("doc_title", "") or "")
    if "Regulations and Instructions" in publication_type:
        notes.append("Regulatory instructions")
    if "Publication section" in doc_title:
        notes.append("Publication gateway")

    unique = []
    for note in notes:
        if note not in unique:
            unique.append(note)
    return unique or ["General central-bank legal context"]


def fx_notes_for_row(row):
    text = " ".join(
        str(row.get(col, "") or "")
        for col in (
            "country", "regulator", "publication_type", "source_title",
            "doc_title", "doc_type", "section", "connection_status", "doc_url")
    ).lower()
    notes = []
    for label, terms in FX_COMPARISON_RULES:
        if any(term in text for term in terms):
            notes.append(label)

    if str(row.get("doc_type", "") or "").lower() in ("xlsx", "xls", "csv"):
        notes.append("Machine-readable rate data")
    if str(row.get("publication_type", "") or "") == "FX Rates":
        notes.append("FX rates")
    if "Foreign Exchange Reserves" in str(row.get("publication_type", "") or ""):
        notes.append("Reserve data")

    unique = []
    for note in notes:
        if note not in unique:
            unique.append(note)
    return unique or ["General FX market context"]


def build_note_comparison(
        primary_row, secondary_row, primary_notes, secondary_notes, *,
        kicker, title, shared_label):
    shared = [note for note in primary_notes if note in secondary_notes]
    primary_only = [note for note in primary_notes if note not in secondary_notes]
    secondary_only = [note for note in secondary_notes if note not in primary_notes]
    if not shared and (
            "General central-bank legal context" in primary_notes
            or "General central-bank legal context" in secondary_notes):
        shared = ["General central-bank legal context"]
        primary_only = [
            note for note in primary_only
            if note != "General central-bank legal context"]
        secondary_only = [
            note for note in secondary_only
            if note != "General central-bank legal context"]
    if not shared and (
            "General FX market context" in primary_notes
            or "General FX market context" in secondary_notes):
        shared = ["General FX market context"]
        primary_only = [
            note for note in primary_only
            if note != "General FX market context"]
        secondary_only = [
            note for note in secondary_only
            if note != "General FX market context"]

    def meta(row):
        return {
            "country": str(row.get("country", "") or ""),
            "regulator": str(row.get("regulator", "") or ""),
            "title": publication_row_title(row),
            "publicationType": str(row.get("publication_type", "") or ""),
            "url": str(row.get("doc_url", "") or ""),
            "sourceUrl": str(row.get("source_page", "") or ""),
            "docType": str(row.get("doc_type", "") or ""),
        }

    return {
        "enabled": True,
        "kicker": kicker,
        "title": title,
        "sharedLabel": shared_label,
        "primary": meta(primary_row),
        "secondary": meta(secondary_row),
        "sharedNotes": shared,
        "primaryOnly": primary_only,
        "secondaryOnly": secondary_only,
    }


def build_legal_comparison(primary_row, secondary_row, reader_docs):
    return build_note_comparison(
        primary_row,
        secondary_row,
        legal_notes_for_row(primary_row, reader_docs),
        legal_notes_for_row(secondary_row, reader_docs),
        kicker="Two-country legal comparison",
        title="Legal notes overlap",
        shared_label="shared notes")


def build_fx_comparison(primary_row, secondary_row):
    return build_note_comparison(
        primary_row,
        secondary_row,
        fx_notes_for_row(primary_row),
        fx_notes_for_row(secondary_row),
        kicker="Two-country FX comparison",
        title="FX rates overlap",
        shared_label="shared data notes")


def tabular_extension_for_row(row):
    doc_type = str(row.get("doc_type", "") or "").strip().lower()
    if doc_type in ("csv", "tsv", "xlsx", "xls"):
        return doc_type
    path = urlparse(str(row.get("doc_url", "") or "")).path.lower()
    extension = os.path.splitext(path)[1].lstrip(".")
    return extension if extension in ("csv", "tsv", "xlsx", "xls") else ""


def is_http_url(url):
    return str(url or "").lower().startswith(("http://", "https://"))


def source_link_for_row(row):
    doc_url = str(row.get("doc_url", "") or "")
    source_page = str(row.get("source_page", "") or "")
    if is_http_url(doc_url):
        return doc_url
    if is_http_url(source_page):
        return source_page
    return doc_url


def clean_tabular_frame(frame):
    frame = frame.copy()
    frame = frame.dropna(how="all")
    frame = frame.dropna(axis=1, how="all")
    frame.columns = [str(column) for column in frame.columns]
    return frame.fillna("")


def fetch_tabular_bytes(url, source_page=""):
    parsed = urlparse(str(url or ""))
    if parsed.scheme == "file":
        with open(parsed.path, "rb") as fh:
            return fh.read()
    if not parsed.scheme and os.path.exists(str(url or "")):
        with open(str(url), "rb") as fh:
            return fh.read()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": (
            "text/csv,application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet,application/vnd.ms-excel,*/*"),
    }
    if source_page:
        headers["Referer"] = source_page
    last_error = None
    with requests.Session() as session:
        if source_page:
            try:
                session.get(source_page, headers=headers, timeout=30)
            except requests.RequestException:
                pass
        for _ in range(3):
            try:
                response = session.get(url, headers=headers, timeout=75)
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1)
    raise last_error


@st.cache_data(show_spinner=False)
def load_tabular_source(url, extension, source_page=""):
    content = fetch_tabular_bytes(url, source_page)
    payload = io.BytesIO(content)
    if extension == "csv":
        return {"CSV": clean_tabular_frame(pd.read_csv(payload))}
    if extension == "tsv":
        return {"TSV": clean_tabular_frame(pd.read_csv(payload, sep="\t"))}
    if extension in ("xlsx", "xls"):
        sheets = pd.read_excel(payload, sheet_name=None, engine="openpyxl")
        return {
            str(sheet): clean_tabular_frame(frame)
            for sheet, frame in sheets.items()
        }
    raise ValueError(f"Unsupported data source type: {extension or 'web'}")


def render_data_reader(row, label, key_prefix):
    title = publication_row_title(row)
    url = str(row.get("doc_url", "") or "")
    source_page = str(row.get("source_page", "") or "")
    extension = tabular_extension_for_row(row)
    st.markdown(f"**{label}**")
    st.caption(title)
    link_url = source_link_for_row(row)
    if link_url:
        st.link_button(f"Open {label} source", link_url, width="stretch")

    if not extension:
        st.info("This source is a web page, not a CSV/XLSX data file.")
        return

    try:
        sheets = load_tabular_source(url, extension, source_page)
    except Exception as exc:
        st.error(f"Could not load this data source: {exc}")
        return

    sheet_names = list(sheets)
    sheet = sheet_names[0]
    if len(sheet_names) > 1:
        sheet = st.selectbox(
            "Sheet",
            sheet_names,
            key=f"{key_prefix}_sheet")
    data = sheets[sheet]
    st.caption(
        f"{extension.upper()} · {len(data):,} rows · {len(data.columns):,} columns")
    st.dataframe(data, hide_index=True, width="stretch", height=420)
    st.download_button(
        "Download visible table (CSV)",
        data.to_csv(index=False).encode("utf-8"),
        slug_for(title or label) + ".csv",
        "text/csv",
        key=f"{key_prefix}_download")


def render_side_by_side_data_readers(primary_row, secondary_row):
    st.markdown("**Side-by-side data readers**")
    st.caption(
        "CSV and Excel sources open directly here for quick comparison. "
        "Web-only sources remain available through their official link.")
    left, right = st.columns(2)
    with left:
        render_data_reader(primary_row, "Country A", "country_a_data_reader")
    with right:
        render_data_reader(secondary_row, "Country B", "country_b_data_reader")


def latest_rate_row(rates, country, series_type):
    subset = rates[
        (rates["country"] == country)
        & (rates["series_type"] == series_type)].copy()
    if subset.empty:
        return None
    subset = subset.dropna(subset=["date_dt", "rate_percent"])
    if subset.empty:
        return None
    return subset.sort_values("date_dt").iloc[-1]


def rate_series_stats(rates, country, series_type, start_date=None):
    subset = rates[
        (rates["country"] == country)
        & (rates["series_type"] == series_type)].copy()
    if start_date is not None:
        subset = subset[subset["date_dt"] >= start_date]
    subset = subset.dropna(subset=["date_dt", "rate_percent"])
    if subset.empty:
        return {}
    subset = subset.sort_values("date_dt")
    first = subset.iloc[0]
    latest = subset.iloc[-1]
    peak = subset.loc[subset["rate_percent"].idxmax()]
    return {
        "first": first,
        "latest": latest,
        "peak": peak,
        "change": latest["rate_percent"] - first["rate_percent"],
        "peak_change": latest["rate_percent"] - peak["rate_percent"],
    }


def format_rate_metric(row):
    if row is None:
        return "Not available"
    return f"{float(row['rate_percent']):.2f}%"


def format_rate_date(row):
    if row is None:
        return ""
    date = row.get("date_dt")
    if pd.isna(date):
        return ""
    return pd.to_datetime(date).date().isoformat()


def format_pp(value):
    if pd.isna(value):
        return ""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f} pp"


def render_overnight_rate_analysis(rate_rows, fx_rows):
    st.markdown("**Overnight-rate trend analysis**")
    st.caption(
        "Compares Israel's BOI policy-rate anchor with Jordan's overnight "
        "policy corridor and published monthly overnight interbank rate. "
        "FX rates provide currency context for the rate comparison.")
    if rate_rows is None or rate_rows.empty:
        st.info(
            "No overnight-rate snapshot found yet. Run "
            "`python overnight_rate_analysis.py` to create the comparison data.")
        return

    rates = rate_rows.copy()
    rates["date_dt"] = pd.to_datetime(rates["date"], errors="coerce")
    rates["rate_percent"] = pd.to_numeric(
        rates["rate_percent"], errors="coerce")
    rates = rates.dropna(subset=["date_dt", "rate_percent"])
    if rates.empty:
        st.info("The overnight-rate snapshot does not contain chartable rows.")
        return

    window = st.segmented_control(
        "Trend window",
        ["Since 2023", "Since 2024", "All available"],
        default="Since 2023",
        key="overnight_trend_window",
        width="content")
    start_date = None
    if window == "Since 2023":
        start_date = pd.Timestamp("2023-01-01")
    elif window == "Since 2024":
        start_date = pd.Timestamp("2024-01-01")
    chart_rates = rates.copy()
    if start_date is not None:
        chart_rates = chart_rates[chart_rates["date_dt"] >= start_date]

    chart_rates = chart_rates[
        (
            (chart_rates["country"] == "Israel")
            & (chart_rates["series_type"] == "policy_anchor"))
        | (
            (chart_rates["country"] == "Jordan")
            & chart_rates["series_type"].isin(
                ["overnight_midpoint", "market_actual"]))
    ].copy()
    label_lookup = {
        ("Israel", "policy_anchor"): "Israel BOI policy anchor",
        ("Jordan", "overnight_midpoint"): "Jordan overnight corridor midpoint",
        ("Jordan", "market_actual"): "Jordan monthly overnight interbank",
    }
    chart_rates["series_label"] = chart_rates.apply(
        lambda row: label_lookup.get(
            (row["country"], row["series_type"]),
            f"{row['country']} {row['series']}"),
        axis=1)
    if not chart_rates.empty:
        chart_data = chart_rates.pivot_table(
            index="date_dt",
            columns="series_label",
            values="rate_percent",
            aggfunc="last").sort_index()
        st.line_chart(chart_data, height=340)

    israel_latest = latest_rate_row(rates, "Israel", "policy_anchor")
    jordan_mid_latest = latest_rate_row(rates, "Jordan", "overnight_midpoint")
    jordan_actual_latest = latest_rate_row(rates, "Jordan", "market_actual")
    spread = None
    if israel_latest is not None and jordan_mid_latest is not None:
        spread = (
            float(jordan_mid_latest["rate_percent"])
            - float(israel_latest["rate_percent"]))

    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric(
        "Israel BOI anchor",
        format_rate_metric(israel_latest),
        format_rate_date(israel_latest))
    metric_b.metric(
        "Jordan overnight midpoint",
        format_rate_metric(jordan_mid_latest),
        format_rate_date(jordan_mid_latest))
    metric_c.metric(
        "Jordan vs Israel spread",
        "Not available" if spread is None else format_pp(spread),
        "policy corridor midpoint")
    metric_d.metric(
        "Jordan market overnight",
        format_rate_metric(jordan_actual_latest),
        format_rate_date(jordan_actual_latest))

    trend_start = pd.Timestamp("2023-01-01")
    israel_stats = rate_series_stats(
        rates, "Israel", "policy_anchor", trend_start)
    jordan_stats = rate_series_stats(
        rates, "Jordan", "overnight_midpoint", trend_start)
    trend_lines = []
    if israel_stats:
        trend_lines.append(
            "Israel's BOI anchor is "
            f"{float(israel_stats['latest']['rate_percent']):.2f}% as of "
            f"{format_rate_date(israel_stats['latest'])}, "
            f"{format_pp(israel_stats['change'])} from the first 2023 reading "
            "in this dataset.")
    if jordan_stats:
        trend_lines.append(
            "Jordan's overnight corridor midpoint is "
            f"{float(jordan_stats['latest']['rate_percent']):.2f}% as of "
            f"{format_rate_date(jordan_stats['latest'])}, "
            f"{format_pp(jordan_stats['peak_change'])} from its 2023 peak "
            f"of {float(jordan_stats['peak']['rate_percent']):.2f}%.")
    if spread is not None:
        trend_lines.append(
            "The current Jordan midpoint sits "
            f"{format_pp(spread)} above Israel's BOI anchor, so Jordan remains "
            "the higher overnight-rate environment in this comparison.")

    fx_context = pd.DataFrame()
    if fx_rows is not None and not fx_rows.empty:
        fx_context = fx_rows.copy()
        fx_context["rate"] = pd.to_numeric(fx_context["rate"], errors="coerce")
        fx_context["date_dt"] = pd.to_datetime(
            fx_context["date"], errors="coerce")
    if not fx_context.empty:
        fx_display = fx_context[
            ["country", "date", "currency_pair", "rate", "unit", "source_url"]
        ].copy()
        st.markdown("**FX context**")
        st.dataframe(
            fx_display,
            hide_index=True,
            width="stretch",
            height=min(180, 72 + 42 * max(1, len(fx_display))))
        israel_fx = fx_context[fx_context["country"] == "Israel"]
        jordan_fx = fx_context[fx_context["country"] == "Jordan"]
        if not israel_fx.empty and not jordan_fx.empty:
            ils = float(israel_fx.iloc[-1]["rate"])
            jod = float(jordan_fx.iloc[-1]["rate"])
            trend_lines.append(
                "FX backdrop: USD/ILS is "
                f"{ils:.4f}, while USD/JOD is about {jod:.3f}. "
                "Jordan's tightly anchored dinar makes its rate setting more "
                "visibly constrained by dollar-linked conditions, while "
                "Israel's floating shekel leaves more adjustment to the FX "
                "channel.")

    if trend_lines:
        st.info(" ".join(trend_lines))

    with st.expander("Overnight-rate source rows", expanded=False):
        visible = rates[
            ["country", "date", "series", "series_type", "rate_percent",
             "source_url"]
        ].sort_values(["country", "date"], ascending=[True, False])
        st.dataframe(visible, hide_index=True, width="stretch", height=360)
        st.download_button(
            "Download overnight-rate comparison (CSV)",
            visible.to_csv(index=False).encode("utf-8"),
            "overnight_rate_comparison.csv",
            "text/csv",
            key="download_overnight_rate_comparison")


def render_comparison_preview(comparison):
    if not comparison:
        return

    def chips(items):
        if not items:
            return '<span class="boi-compare-chip muted">None flagged</span>'
        return "".join(
            f'<span class="boi-compare-chip">{html.escape(item)}</span>'
            for item in items[:5])

    primary = comparison["primary"]
    secondary = comparison["secondary"]
    kicker = html.escape(comparison.get("kicker", "Two-country comparison"))
    title = html.escape(comparison.get("title", "Notes overlap"))
    shared_label = html.escape(comparison.get("sharedLabel", "shared notes"))
    st.markdown(
        f"""
        <div class="boi-compare-panel">
          <div class="boi-compare-head">
            <div>
              <div class="boi-kicker">{kicker}</div>
              <div class="boi-compare-title">{title}</div>
            </div>
            <div class="boi-compare-count">
              {len(comparison['sharedNotes'])} {shared_label}
            </div>
          </div>
          <div class="boi-compare-venn">
            <div class="boi-compare-circle left">
              <strong>{html.escape(primary['country'])}</strong>
              <span>{len(comparison['primaryOnly'])} unique</span>
            </div>
            <div class="boi-compare-circle right">
              <strong>{html.escape(secondary['country'])}</strong>
              <span>{len(comparison['secondaryOnly'])} unique</span>
            </div>
            <div class="boi-compare-overlap">
              <strong>{len(comparison['sharedNotes'])}</strong>
              <span>shared</span>
            </div>
          </div>
          <div class="boi-compare-grid">
            <div>
              <b>{html.escape(primary['title'])}</b>
              <div>{chips(comparison['primaryOnly'])}</div>
            </div>
            <div>
              <b>Shared</b>
              <div>{chips(comparison['sharedNotes'])}</div>
            </div>
            <div>
              <b>{html.escape(secondary['title'])}</b>
              <div>{chips(comparison['secondaryOnly'])}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True)


def render_catalog_type_shelf(view):
    if view.empty or "publication_type" not in view.columns:
        return

    grouped = (
        view.assign(publication_type=view["publication_type"].fillna(""))
        .groupby("publication_type", dropna=False)
        .agg(
            document_count=("source_title", "count"),
            latest=("lastmod", "max"),
        )
        .reset_index())
    grouped = grouped[grouped["publication_type"].astype(str).str.len() > 0]
    if grouped.empty:
        return

    grouped = grouped.sort_values(
        by=["publication_type"],
        key=lambda col: col.map(
            lambda label: f"{publication_type_rank(label):03d}-{label}"))

    items = []
    for index, (_, row) in enumerate(grouped.iterrows()):
        label = str(row["publication_type"])
        accent = CATALOG_ACCENTS[index % len(CATALOG_ACCENTS)]
        latest = str(row["latest"] or "")[:10] or "n/a"
        count = int(row["document_count"] or 0)
        description = PUBLICATION_TYPE_DESCRIPTIONS.get(
            label,
            "Bank of Israel source documents grouped by shared publication "
            "context.")
        items.append(
            f'<div class="boi-catalog-type">'
            f'<div class="boi-catalog-rule" style="background:{accent};"></div>'
            f'<div class="boi-catalog-title">{html.escape(label)}</div>'
            f'<div class="boi-catalog-copy">{html.escape(description)}</div>'
            f'<div class="boi-catalog-meta">'
            f'{count:,} documents · latest {html.escape(latest)}'
            f'</div></div>')

    st.markdown(
        '<div class="boi-catalog-shelf">' + "\n".join(items) + "</div>",
        unsafe_allow_html=True)


def directive_update_stats(directives):
    if directives is None or directives.empty or "lastmod" not in directives.columns:
        return {
            "rate_label": "n/a",
            "recent_label": "No directive dates",
            "latest_label": "n/a",
        }

    dates = pd.to_datetime(directives["lastmod"], errors="coerce", utc=True)
    dates = dates.dropna()
    if dates.empty:
        return {
            "rate_label": "n/a",
            "recent_label": "No directive dates",
            "latest_label": "n/a",
        }

    today = pd.Timestamp.now(tz="UTC").normalize()
    year_start = today - pd.DateOffset(months=12)
    quarter_start = today - pd.DateOffset(days=90)
    last_year_count = int((dates >= year_start).sum())
    last_quarter_count = int((dates >= quarter_start).sum())
    monthly_rate = last_year_count / 12
    latest = dates.max().date().isoformat()
    return {
        "rate_label": f"{monthly_rate:.1f}/mo",
        "recent_label": f"{last_quarter_count:,} in last 90 days",
        "latest_label": latest,
    }


def z_score(series):
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return values * 0
    return (values - values.mean()) / std


def build_directive_financial_stress_frame(directives, rate_rows, israel_reserves):
    pieces = []

    directive_dates = pd.Series(dtype="datetime64[ns, UTC]")
    if directives is not None and not directives.empty and "lastmod" in directives:
        directive_dates = pd.to_datetime(
            directives["lastmod"], errors="coerce", utc=True).dropna()
    if not directive_dates.empty:
        updates = (
            directive_dates.dt.tz_convert(None).dt.to_period("M")
            .value_counts()
            .rename_axis("month_period")
            .reset_index(name="directive_updates"))
        updates["month"] = updates["month_period"].dt.to_timestamp()
        pieces.append(updates[["month", "directive_updates"]])

    if rate_rows is not None and not rate_rows.empty:
        rates = rate_rows.copy()
        for column in ("country", "series_type", "date", "rate_percent"):
            if column not in rates.columns:
                rates[column] = ""
        rates = rates[
            (rates["country"].astype(str) == "Israel")
            & (rates["series_type"].astype(str) == "policy_anchor")].copy()
        rates["date_dt"] = pd.to_datetime(rates["date"], errors="coerce")
        rates["policy_rate"] = pd.to_numeric(
            rates["rate_percent"], errors="coerce")
        rates = rates.dropna(subset=["date_dt", "policy_rate"])
        if not rates.empty:
            rates["month"] = rates["date_dt"].dt.to_period("M").dt.to_timestamp()
            rates = (
                rates.sort_values("date_dt")
                .groupby("month", as_index=False)
                .agg(policy_rate=("policy_rate", "last")))
            pieces.append(rates)

    if israel_reserves is not None and not israel_reserves.empty:
        reserves = israel_reserves.copy()
        for column in ("date", "total_foreign_exchange_reserves_usd_million"):
            if column not in reserves.columns:
                reserves[column] = ""
        reserves["month"] = pd.to_datetime(
            reserves["date"], format="%B %Y", errors="coerce"
        ).dt.to_period("M").dt.to_timestamp()
        reserves["reserve_total_usd_million"] = pd.to_numeric(
            reserves["total_foreign_exchange_reserves_usd_million"],
            errors="coerce")
        reserves = reserves.dropna(subset=["month", "reserve_total_usd_million"])
        if not reserves.empty:
            reserves = (
                reserves.sort_values("month")
                .groupby("month", as_index=False)
                .agg(reserve_total_usd_million=(
                    "reserve_total_usd_million", "last")))
            reserves["reserve_mom_pct"] = (
                reserves["reserve_total_usd_million"].pct_change() * 100)
            pieces.append(reserves)

    if not pieces:
        return pd.DataFrame()

    min_month = min(piece["month"].min() for piece in pieces if not piece.empty)
    max_month = max(piece["month"].max() for piece in pieces if not piece.empty)
    frame = pd.DataFrame({
        "month": pd.date_range(min_month, max_month, freq="MS")
    })
    for piece in pieces:
        frame = frame.merge(piece, on="month", how="left")

    frame["directive_updates"] = frame["directive_updates"].fillna(0).astype(int)
    if "policy_rate" in frame.columns:
        frame["policy_rate"] = frame["policy_rate"].ffill()
        frame["policy_rate_pressure"] = frame["policy_rate"]
        frame["policy_rate_change_abs"] = frame["policy_rate"].diff().abs()
    else:
        frame["policy_rate"] = np.nan
        frame["policy_rate_pressure"] = np.nan
        frame["policy_rate_change_abs"] = np.nan
    if "reserve_total_usd_million" not in frame.columns:
        frame["reserve_total_usd_million"] = np.nan
    if "reserve_mom_pct" not in frame.columns:
        frame["reserve_mom_pct"] = np.nan
    frame["reserve_drawdown_pct"] = -frame["reserve_mom_pct"]

    frame["financial_stress_index"] = (
        z_score(frame["reserve_drawdown_pct"])
        + z_score(frame["policy_rate_pressure"])
        + z_score(frame["policy_rate_change_abs"]))
    return frame


def fit_simple_ols(data, x_col, y_col):
    sample = data[["month", x_col, y_col]].copy()
    sample[x_col] = pd.to_numeric(sample[x_col], errors="coerce")
    sample[y_col] = pd.to_numeric(sample[y_col], errors="coerce")
    sample = sample.dropna(subset=[x_col, y_col])
    if len(sample) < 3 or sample[x_col].nunique() < 2:
        return None, sample

    x = sample[x_col].to_numpy(dtype=float)
    y = sample[y_col].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    fitted = intercept + slope * x
    residuals = y - fitted
    ss_res = float(np.square(residuals).sum())
    ss_tot = float(np.square(y - y.mean()).sum())
    r_squared = 1 - ss_res / ss_tot if ss_tot else 0.0
    corr = float(pd.Series(x).corr(pd.Series(y)))
    sxx = float(np.square(x - x.mean()).sum())
    t_stat = np.nan
    if len(sample) > 2 and sxx:
        mse = ss_res / (len(sample) - 2)
        se = np.sqrt(mse / sxx) if mse >= 0 else np.nan
        if se and not pd.isna(se):
            t_stat = float(slope / se)
    sample["fitted"] = fitted
    line_points = pd.DataFrame({
        x_col: [float(x.min()), float(x.max())],
        y_col: [
            float(intercept + slope * x.min()),
            float(intercept + slope * x.max()),
        ],
    })
    return {
        "intercept": float(intercept),
        "slope": float(slope),
        "r_squared": float(r_squared),
        "correlation": corr,
        "t_stat": t_stat,
        "n": int(len(sample)),
        "line_points": line_points,
    }, sample


def render_directive_financial_stress_regression(
        directives, overnight_rates, israel_reserves, selected_country):
    st.subheader("Directive Updates vs Financial Stress")
    if selected_country != "Israel":
        st.info(
            "Regression is available for Israel first. To run this for "
            f"{selected_country}, connect a directive-update history and a "
            "country-level financial stress/activity proxy for that "
            "jurisdiction.")
        return

    frame = build_directive_financial_stress_frame(
        directives, overnight_rates, israel_reserves)
    if frame.empty:
        st.info(
            "No usable monthly directive/stress data is available for "
            "regression.")
        return

    st.caption(
        "First-pass OLS using monthly observations. The dependent variable is "
        "a financial-stress proxy; the explanatory variable is directive update "
        "count shifted by the selected lag. This is correlation analysis, not "
        "a causal claim.")

    proxy_options = {
        "Combined financial stress proxy": (
            "financial_stress_index",
            "Higher values combine reserve drawdowns, higher BOI policy-rate "
            "pressure, and policy-rate shock magnitude."),
        "FX reserve drawdown stress": (
            "reserve_drawdown_pct",
            "Higher values mean foreign reserves fell more month over month."),
        "Policy-rate pressure": (
            "policy_rate_pressure",
            "Higher values mean a tighter BOI policy-rate level."),
        "Policy-rate shock magnitude": (
            "policy_rate_change_abs",
            "Higher values mean a larger month-over-month policy-rate move."),
    }
    lag_options = {
        "Same month": 0,
        "1-month lag": 1,
        "3-month lag": 3,
        "6-month lag": 6,
        "12-month lag": 12,
    }
    window_options = {
        "Reserve-data window": pd.Timestamp("2025-06-01"),
        "Since 2024": pd.Timestamp("2024-01-01"),
        "All available": None,
    }

    control_1, control_2, control_3 = st.columns(3)
    with control_1:
        proxy_label = st.selectbox(
            "Financial stress proxy",
            list(proxy_options),
            key="stress_regression_proxy")
    with control_2:
        lag_label = st.selectbox(
            "Directive lag",
            list(lag_options),
            index=1,
            key="stress_regression_lag")
    with control_3:
        window_label = st.selectbox(
            "Sample window",
            list(window_options),
            key="stress_regression_window")

    y_col, proxy_note = proxy_options[proxy_label]
    lag_months = lag_options[lag_label]
    start_month = window_options[window_label]
    analysis = frame.copy()
    if start_month is not None:
        analysis = analysis[analysis["month"] >= start_month].copy()
    analysis["directive_updates_lagged"] = (
        analysis["directive_updates"].shift(lag_months))
    result, sample = fit_simple_ols(
        analysis, "directive_updates_lagged", y_col)

    if result is None:
        st.warning(
            "Not enough variation/observations to estimate this regression. "
            "Try a shorter lag or a wider sample window.")
        return

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Coefficient β", f"{result['slope']:.3f}")
    metric_2.metric("R²", f"{result['r_squared']:.2f}")
    metric_3.metric("Correlation", f"{result['correlation']:.2f}")
    metric_4.metric("Observations", f"{result['n']:,}")

    plot_data = sample.rename(columns={
        "directive_updates_lagged": "Lagged directive updates",
        y_col: "Financial stress proxy",
    })
    line_points = result["line_points"].rename(columns={
        "directive_updates_lagged": "Lagged directive updates",
        y_col: "Financial stress proxy",
    })
    scatter = alt.Chart(plot_data).mark_circle(size=80, opacity=0.74).encode(
        x=alt.X("Lagged directive updates:Q"),
        y=alt.Y("Financial stress proxy:Q"),
        tooltip=[
            alt.Tooltip("month:T", title="Month"),
            alt.Tooltip("Lagged directive updates:Q", format=".0f"),
            alt.Tooltip("Financial stress proxy:Q", format=".3f"),
        ],
    )
    trend = alt.Chart(line_points).mark_line(
        color="#17345b", strokeWidth=3).encode(
            x="Lagged directive updates:Q",
            y="Financial stress proxy:Q")
    st.altair_chart(scatter + trend, use_container_width=True)

    normalized = sample[["month", "directive_updates_lagged", y_col]].copy()
    normalized["Lagged directive updates"] = z_score(
        normalized["directive_updates_lagged"])
    normalized["Financial stress proxy"] = z_score(normalized[y_col])
    st.line_chart(
        normalized.set_index("month")[
            ["Lagged directive updates", "Financial stress proxy"]],
        height=260)

    direction = "higher" if result["slope"] > 0 else "lower"
    st.info(
        f"Interpretation: with {lag_label.lower()}, months with more directive "
        f"updates are associated with {direction} `{proxy_label}` values in "
        f"this sample. {proxy_note}")

    with st.expander("Regression dataset", expanded=False):
        display = analysis[[
            "month", "directive_updates", "directive_updates_lagged",
            "policy_rate", "reserve_total_usd_million", "reserve_mom_pct",
            "reserve_drawdown_pct", "policy_rate_pressure",
            "policy_rate_change_abs", "financial_stress_index",
        ]].dropna(subset=["directive_updates_lagged", y_col])
        st.dataframe(display, hide_index=True, width="stretch", height=320)
        st.download_button(
            "Download regression dataset (CSV)",
            display.to_csv(index=False).encode("utf-8"),
            "directive_financial_stress_regression.csv",
            "text/csv",
            key="download_directive_financial_stress_regression")


DIRECTIVE_TOPIC_PRIORITY = (
    "All banking directives",
    "Capital adequacy",
    "Liquidity risk",
    "Credit risk",
    "Housing and lending",
    "Governance and audit",
    "Reporting and disclosure",
    "Cyber and operational resilience",
    "Consumer protection",
    "Payments and cards",
    "Foreign exchange",
    "Financial stability",
)
CORRELATION_TOPIC_THRESHOLD = 0.5


def directive_topic_text(row):
    fields = (
        "directive_number", "title_display", "subject_display", "page_title",
        "title", "subject", "area", "circular_number")
    return " ".join(str(row.get(field, "") or "") for field in fields).lower()


def directive_topics_for_row(row):
    text = directive_topic_text(row)
    topics = []
    for label, terms in LEGAL_COMPARISON_RULES:
        if any(term in text for term in terms):
            topics.append(label)
    if not topics:
        topics.append("General supervision")
    return topics


def directive_topic_options(directives):
    discovered = []
    if directives is not None and not directives.empty:
        for _, row in directives.iterrows():
            for topic in directive_topics_for_row(row):
                if topic not in discovered:
                    discovered.append(topic)
    ordered = ["All banking directives"]
    for topic in DIRECTIVE_TOPIC_PRIORITY:
        if topic != "All banking directives" and topic in discovered:
            ordered.append(topic)
    for topic in sorted(discovered):
        if topic not in ordered:
            ordered.append(topic)
    return ordered


def annual_directive_updates(directives, topic, date_basis="publication_date"):
    if directives is None or directives.empty:
        return pd.DataFrame(columns=["year", "directive_updates"])
    data = directives.copy()
    preferred_column = (
        "publication_date" if date_basis == "publication_date" else "lastmod")
    if preferred_column not in data.columns:
        preferred_column = "lastmod" if "lastmod" in data.columns else ""
    if not preferred_column:
        return pd.DataFrame(columns=["year", "directive_updates"])

    if preferred_column == "publication_date":
        data["event_dt"] = pd.to_datetime(
            data[preferred_column], errors="coerce", dayfirst=True)
    else:
        data["event_dt"] = pd.to_datetime(
            data[preferred_column], errors="coerce", utc=True).dt.tz_convert(None)
    data = data.dropna(subset=["event_dt"])
    if data.empty:
        return pd.DataFrame(columns=["year", "directive_updates"])
    if topic != "All banking directives":
        topic_mask = data.apply(
            lambda row: topic in directive_topics_for_row(row),
            axis=1)
        data = data[topic_mask].copy()
    if data.empty:
        return pd.DataFrame(columns=["year", "directive_updates"])
    data["year"] = data["event_dt"].dt.year.astype(int)
    return (
        data.groupby("year")
        .size()
        .reset_index(name="directive_updates")
        .sort_values("year"))


def banking_indicator_snapshot(indicators, country):
    if indicators is None or indicators.empty:
        return pd.DataFrame()
    data = indicators[indicators["country"].astype(str) == country].copy()
    if data.empty:
        return data
    data["year_num"] = pd.to_numeric(data["year"], errors="coerce")
    data["value_num"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["year_num", "value_num"])
    if data.empty:
        return data
    latest_idx = data.sort_values("year_num").groupby(
        "indicator_code")["year_num"].idxmax()
    latest = data.loc[latest_idx].copy().sort_values("indicator_group")
    return latest[[
        "indicator_group", "indicator_name", "year", "value",
        "metric_type", "source_url"]]


def build_directive_banking_indicator_frame(
        directives, indicators, country, indicator_code, topic,
        date_basis="publication_date"):
    update_counts = annual_directive_updates(directives, topic, date_basis)
    if indicators is None or indicators.empty:
        return pd.DataFrame(), None

    indicator_rows = indicators[
        (indicators["country"].astype(str) == country)
        & (indicators["indicator_code"].astype(str) == indicator_code)
    ].copy()
    if indicator_rows.empty:
        return pd.DataFrame(), None

    indicator_rows["year"] = pd.to_numeric(
        indicator_rows["year"], errors="coerce")
    indicator_rows["indicator_value"] = pd.to_numeric(
        indicator_rows["value"], errors="coerce")
    indicator_rows = indicator_rows.dropna(subset=["year", "indicator_value"])
    if indicator_rows.empty:
        return pd.DataFrame(), None
    indicator_rows["year"] = indicator_rows["year"].astype(int)
    indicator_rows = (
        indicator_rows.sort_values("year")
        .groupby("year", as_index=False)
        .agg(
            indicator_value=("indicator_value", "last"),
            indicator_name=("indicator_name", "last"),
            indicator_group=("indicator_group", "last"),
            metric_type=("metric_type", "last"),
            stress_direction=("stress_direction", "last"),
            source_url=("source_url", "last"),
            source_last_updated=("source_last_updated", "last")))
    indicator_meta = indicator_rows.iloc[-1].to_dict()

    pieces = [indicator_rows[[
        "year", "indicator_value", "indicator_name", "indicator_group",
        "metric_type", "stress_direction", "source_url",
        "source_last_updated"]]]
    if not update_counts.empty:
        pieces.append(update_counts)

    min_year = min(piece["year"].min() for piece in pieces if not piece.empty)
    max_year = max(piece["year"].max() for piece in pieces if not piece.empty)
    frame = pd.DataFrame({"year": range(int(min_year), int(max_year) + 1)})
    for piece in pieces:
        frame = frame.merge(piece, on="year", how="left")
    frame["directive_updates"] = frame["directive_updates"].fillna(0).astype(int)
    frame = frame.sort_values("year")
    frame["indicator_change_pp"] = frame["indicator_value"].diff()
    frame["indicator_change_pct"] = frame["indicator_value"].pct_change() * 100

    stress_direction = str(
        indicator_meta.get("stress_direction", "") or "").lower()
    level_score = z_score(frame["indicator_value"])
    change_score = z_score(frame["indicator_change_pp"])
    if stress_direction.startswith("lower"):
        level_score = -level_score
        change_score = -change_score
    frame["stress_activity_score"] = level_score
    frame["stress_activity_change_score"] = change_score
    frame["month"] = pd.to_datetime(
        frame["year"].astype(str) + "-01-01", errors="coerce")
    return frame, indicator_meta


def format_correlation_strength(correlation):
    if pd.isna(correlation):
        return "unreadable"
    magnitude = abs(correlation)
    if magnitude < 0.30:
        return "weak"
    if magnitude < 0.50:
        return "modest"
    if magnitude < 0.70:
        return "moderate"
    return "strong"


def directive_topic_correlation_scan(
        directives, indicators, country, indicator_code, y_col, lag_years,
        start_year, date_basis):
    rows = []
    for candidate_topic in directive_topic_options(directives):
        frame, indicator_meta = build_directive_banking_indicator_frame(
            directives, indicators, country, indicator_code, candidate_topic,
            date_basis)
        if frame.empty or not indicator_meta:
            continue
        analysis = frame.copy()
        if start_year is not None:
            analysis = analysis[analysis["year"] >= start_year].copy()
        analysis["directive_updates_lagged"] = (
            analysis["directive_updates"].shift(lag_years))
        result, sample = fit_simple_ols(
            analysis, "directive_updates_lagged", y_col)
        if result is None or pd.isna(result["correlation"]):
            continue
        rows.append({
            "topic": candidate_topic,
            "correlation": result["correlation"],
            "abs_correlation": abs(result["correlation"]),
            "r_squared": result["r_squared"],
            "coefficient_beta": result["slope"],
            "observations": result["n"],
        })

    if not rows:
        return pd.DataFrame(columns=[
            "topic", "correlation", "abs_correlation", "r_squared",
            "coefficient_beta", "observations"])
    return (
        pd.DataFrame(rows)
        .sort_values(["abs_correlation", "topic"], ascending=[False, True])
        .reset_index(drop=True))


REGRESSION_COLUMN_DEFINITIONS = {
    "year": (
        "Calendar year for the annual observation used in the regression."),
    "directive_updates": (
        "Number of BOI Proper Conduct directive publications or updates in "
        "that year, after the selected directive-topic filter is applied."),
    "directive_updates_lagged": (
        "Directive update count shifted by the selected lag. This is the "
        "independent variable used in the regression."),
    "indicator_value": (
        "Raw value of the selected banking-sector indicator for that year."),
    "indicator_change_pp": (
        "Year-over-year change in the selected indicator, measured in "
        "percentage points."),
    "indicator_change_pct": (
        "Year-over-year percentage change in the selected indicator value."),
    "stress_activity_score": (
        "Standardized indicator level. For resilience indicators such as "
        "capital or liquidity, the sign is flipped so higher means more "
        "stress; for activity/pressure indicators, higher means more activity "
        "or pressure."),
    "stress_activity_change_score": (
        "Standardized annual change. The sign is oriented so higher means "
        "rising stress, pressure, or activity."),
    "source_url": (
        "World Bank source page for the selected banking-sector indicator."),
}

REGRESSION_COLUMN_LABELS = {
    "year": "Year",
    "directive_updates": "Directive updates",
    "directive_updates_lagged": "Lagged directive updates",
    "indicator_value": "Indicator value",
    "indicator_change_pp": "Indicator change, pp",
    "indicator_change_pct": "Indicator change, %",
    "stress_activity_score": "Stress/activity score",
    "stress_activity_change_score": "Stress/activity change score",
    "source_url": "Source",
}

ORM_REGRESSION_DEFAULT_VERSION = "orm-regression-defaults-2026-07-26-v3"
ORM_DEFAULT_RISK_PROXY_CODE = "FR.INR.LNDP"
ORM_RISK_PROXY_OPTIONS = (
    {
        "label": "Funding stress",
        "indicator_code": "FR.INR.LNDP",
        "description": (
            "Interest-rate spread between lending and deposit rates. Wider "
            "spreads usually indicate tighter funding conditions."),
    },
    {
        "label": "Credit risk",
        "indicator_code": "FB.AST.NPER.ZS",
        "description": (
            "Bank nonperforming loans as a share of gross loans. Higher values "
            "indicate more realized credit stress."),
    },
    {
        "label": "Liquidity buffer stress",
        "indicator_code": "GFDD.SI.06",
        "description": (
            "Liquid assets to deposits and short-term funding. The score is "
            "oriented so lower liquidity buffers read as higher stress."),
    },
    {
        "label": "Capital buffer stress",
        "indicator_code": "FB.BNK.CAPA.ZS",
        "description": (
            "Bank capital to assets. The score is oriented so lower capital "
            "buffers read as higher stress."),
    },
)


def regression_column_config():
    config = {}
    for column, definition in REGRESSION_COLUMN_DEFINITIONS.items():
        label = REGRESSION_COLUMN_LABELS.get(column, column)
        if column == "source_url":
            config[column] = st.column_config.LinkColumn(
                label,
                help=definition,
                display_text="Open source")
        elif column == "year":
            config[column] = st.column_config.NumberColumn(
                label,
                help=definition,
                format="%d")
        else:
            config[column] = st.column_config.NumberColumn(
                label,
                help=definition,
                format="%.3f")
    return config


def render_regression_definition_popovers(columns):
    st.markdown("**Definitions**")
    items = []
    for column in columns:
        definition = REGRESSION_COLUMN_DEFINITIONS.get(column)
        if not definition:
            continue
        label = REGRESSION_COLUMN_LABELS.get(column, column)
        items.append(
            '<span class="boi-definition-link" tabindex="0">'
            f'{html.escape(label)}'
            '<span class="boi-definition-popover">'
            f'{html.escape(definition)}'
            '</span></span>')
    if not items:
        return
    st.markdown(
        """
        <style>
        .boi-definition-links {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem 0.8rem;
            margin: 0.3rem 0 0.9rem;
        }
        .boi-definition-link {
            position: relative;
            color: var(--boi-navy);
            cursor: help;
            font-weight: 650;
            text-decoration: underline;
            text-underline-offset: 3px;
            white-space: nowrap;
        }
        .boi-definition-popover {
            position: absolute;
            left: 0;
            top: calc(100% + 8px);
            z-index: 999;
            width: min(320px, 78vw);
            padding: 0.72rem 0.8rem;
            border: 1px solid var(--boi-line);
            border-radius: 6px;
            background: var(--boi-paper);
            color: var(--boi-ink);
            box-shadow: 0 8px 24px rgba(23, 52, 91, 0.14);
            font-weight: 500;
            line-height: 1.35;
            white-space: normal;
            opacity: 0;
            pointer-events: none;
            transform: translateY(-4px);
            transition: opacity 0.12s ease, transform 0.12s ease;
        }
        .boi-definition-link:hover .boi-definition-popover,
        .boi-definition-link:focus .boi-definition-popover,
        .boi-definition-link:focus-within .boi-definition-popover {
            opacity: 1;
            pointer-events: auto;
            transform: translateY(0);
        }
        </style>
        """,
        unsafe_allow_html=True)
    st.markdown(
        '<div class="boi-definition-links">'
        + "\n".join(items)
        + "</div>",
        unsafe_allow_html=True)


def render_directive_banking_indicator_regression(
        directives, banking_indicators, selected_country):
    st.subheader("Directive Update Frequency vs Risk")
    st.caption(
        "Annual BOI Proper Conduct directive updates are compared with one "
        "risk proxy for the selected country. The method is fixed to a "
        "same-year annual correlation since 2012 using website update dates.")
    if banking_indicators is None or banking_indicators.empty:
        st.info(
            "No banking-sector indicator file is available yet. Run "
            "`python banking_sector_indicators.py` to fetch the World Bank "
            "indicator snapshot.")
        return

    countries = ordered_countries(
        banking_indicators["country"].dropna().astype(str).unique())
    if not countries:
        st.info("No country-level banking indicators are available.")
        return

    if selected_country not in countries:
        st.info(
            f"No banking-risk indicator series is connected for "
            f"{selected_country} yet. Choose Israel or Jordan in the "
            "publication country selector above to run the correlation view.")
        return

    indicator_country = selected_country
    available_codes = set(
        banking_indicators[
            banking_indicators["country"].astype(str) == indicator_country
        ]["indicator_code"].astype(str))
    risk_options = [
        option for option in ORM_RISK_PROXY_OPTIONS
        if option["indicator_code"] in available_codes
    ]
    if not risk_options:
        st.info(f"No risk proxy observations are available for {indicator_country}.")
        return

    default_risk_label = next(
        (
            option["label"] for option in risk_options
            if option["indicator_code"] == ORM_DEFAULT_RISK_PROXY_CODE
        ),
        risk_options[0]["label"],
    )
    risk_labels = [option["label"] for option in risk_options]
    if (
            st.session_state.get("orm_regression_default_version")
            != ORM_REGRESSION_DEFAULT_VERSION
            or st.session_state.get("banking_risk_proxy") not in risk_labels):
        st.session_state["banking_risk_proxy"] = default_risk_label
        st.session_state["orm_regression_default_version"] = (
            ORM_REGRESSION_DEFAULT_VERSION)

    risk_label = st.selectbox(
        "Risk proxy",
        risk_labels,
        key="banking_risk_proxy",
        help="The only setting left exposed: choose the risk lens to compare "
             "against directive update frequency.")
    risk_option = next(
        option for option in risk_options if option["label"] == risk_label)

    topic = "All banking directives"
    indicator_code = risk_option["indicator_code"]
    date_basis = "lastmod"
    y_col = "stress_activity_score"
    dependent_label = "Risk score"
    lag_years = 0
    start_year = 2012

    setting_1, setting_2, setting_3 = st.columns(3)
    setting_1.markdown(
        f"**Country**  \n{indicator_country}")
    setting_2.markdown(
        "**Directive frequency**  \nAll BOI Proper Conduct updates")
    setting_3.markdown(
        "**Method**  \nSame-year annual correlation since 2012")

    frame, indicator_meta = build_directive_banking_indicator_frame(
        directives, banking_indicators, indicator_country, indicator_code,
        topic, date_basis)
    if frame.empty or not indicator_meta:
        st.warning("No matching indicator observations were found.")
        return

    analysis = frame.copy()
    if start_year is not None:
        analysis = analysis[analysis["year"] >= start_year].copy()
    analysis["directive_updates_lagged"] = (
        analysis["directive_updates"].shift(lag_years))
    result, sample = fit_simple_ols(
        analysis, "directive_updates_lagged", y_col)

    latest = analysis.dropna(
        subset=["indicator_value", "directive_updates_lagged"]).tail(1)
    latest_value = "n/a"
    latest_year = "n/a"
    latest_updates = "n/a"
    if not latest.empty:
        latest_value = f"{float(latest.iloc[0]['indicator_value']):.2f}"
        latest_year = str(int(latest.iloc[0]["year"]))
        latest_updates = f"{int(latest.iloc[0]['directive_updates_lagged']):,}"

    if result is None:
        st.warning(
            "Not enough annual observations or update-frequency variation to "
            "estimate this correlation yet.")
    else:
        strength = format_correlation_strength(result["correlation"])
        metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
        metric_1.metric(
            "Avg annual updates",
            f"{sample['directive_updates_lagged'].mean():.1f}")
        metric_2.metric(
            "Correlation",
            f"{result['correlation']:.2f}",
            strength)
        metric_3.metric("R squared", f"{result['r_squared']:.2f}")
        metric_4.metric("Observations", f"{result['n']:,}")
        metric_5.metric(f"{latest_year} risk proxy", latest_value)
        st.caption(
            f"Latest paired year: {latest_year} with {latest_updates} "
            "directive updates.")

        y_axis_title = dependent_label
        plot_data = sample.rename(columns={
            "directive_updates_lagged": "Directive update frequency",
            y_col: y_axis_title,
        })
        line_points = result["line_points"].rename(columns={
            "directive_updates_lagged": "Directive update frequency",
            y_col: y_axis_title,
        })
        scatter = alt.Chart(plot_data).mark_circle(
            size=84, opacity=0.78).encode(
                x=alt.X("Directive update frequency:Q"),
                y=alt.Y(f"{y_axis_title}:Q"),
                tooltip=[
                    alt.Tooltip("month:T", title="Year", format="%Y"),
                    alt.Tooltip("Directive update frequency:Q", format=".0f"),
                    alt.Tooltip(f"{y_axis_title}:Q", format=".3f"),
                ])
        trend = alt.Chart(line_points).mark_line(
            color="#17345b", strokeWidth=3).encode(
                x="Directive update frequency:Q",
                y=f"{y_axis_title}:Q")
        st.altair_chart(scatter + trend, use_container_width=True)

        normalized = sample[["month", "directive_updates_lagged", y_col]].copy()
        normalized["Directive update frequency"] = z_score(
            normalized["directive_updates_lagged"])
        normalized[y_axis_title] = z_score(normalized[y_col])
        st.line_chart(
            normalized.set_index("month")[
                ["Directive update frequency", y_axis_title]],
            height=260)

        direction = "higher" if result["slope"] > 0 else "lower"
        st.info(
            f"Interpretation: this run has a {strength} correlation. "
            f"Years with more directive updates are associated with {direction} "
            f"{risk_label.lower()} risk scores for {indicator_country}. "
            f"{risk_option['description']} Treat this as a screening signal, "
            "not a causal claim.")

    with st.expander("Audit data", expanded=False):
        snapshot = banking_indicator_snapshot(
            banking_indicators, indicator_country)
        if not snapshot.empty:
            st.markdown("**Latest banking indicators**")
            st.dataframe(
                snapshot.rename(columns={
                    "indicator_group": "Group",
                    "indicator_name": "Indicator",
                    "year": "Latest year",
                    "value": "Latest value",
                    "metric_type": "Metric type",
                    "source_url": "Source",
                }),
                hide_index=True,
                width="stretch",
                height=min(360, 72 + 42 * len(snapshot)))
        display = analysis[[
            "year", "directive_updates", "directive_updates_lagged",
            "indicator_value", "indicator_change_pp",
            "indicator_change_pct", "stress_activity_score",
            "stress_activity_change_score",
            "source_url",
        ]].dropna(subset=["directive_updates_lagged", y_col])
        st.markdown("**Regression rows**")
        render_regression_definition_popovers(display.columns)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=320,
            column_config=regression_column_config())
        st.download_button(
            "Download banking-indicator regression dataset (CSV)",
            display.to_csv(index=False).encode("utf-8"),
            "directive_banking_indicator_regression.csv",
            "text/csv",
            key="download_directive_banking_indicator_regression")


def build_regional_map_data(reader_view, query, jordan_docs=None):
    rows = []
    israel_matches = len(reader_view) if reader_view is not None else 0
    israel_hits = 0
    if reader_view is not None and not reader_view.empty:
        if "full_text_matches" in reader_view.columns:
            israel_hits = int(reader_view["full_text_matches"].fillna(0).sum())
    jordan_matches = len(jordan_docs) if jordan_docs is not None else 0

    for market in REGIONAL_BANKING_MARKETS:
        row = dict(market)
        if market["country"] == "Israel":
            row["publication_matches"] = israel_matches
            row["text_hits"] = israel_hits
            row["coverage"] = (
                f"{israel_matches:,} matching BOI PDFs"
                if str(query or "").strip()
                else f"{israel_matches:,} BOI PDFs in catalog")
            row["status"] = "Active local corpus"
            row["radius"] = min(260000, 76000 + israel_matches * 120)
            row["fill_color"] = [255, 76, 76, 210]
            row["line_color"] = [132, 28, 35, 235]
        elif market["country"] == "Jordan" and jordan_matches:
            row["publication_matches"] = jordan_matches
            row["text_hits"] = 0
            row["coverage"] = f"{jordan_matches:,} CBJ records"
            row["status"] = "Connected external corpus"
            row["radius"] = min(220000, 76000 + jordan_matches * 1400)
            row["fill_color"] = [26, 132, 108, 210]
            row["line_color"] = [8, 86, 74, 235]
        else:
            row["publication_matches"] = 0
            row["text_hits"] = 0
            row["coverage"] = "External corpus not connected yet"
            row["status"] = "Regional comparison target"
            row["radius"] = 69000
            row["fill_color"] = [36, 78, 96, 155]
            row["line_color"] = [19, 48, 58, 210]
        rows.append(row)
    return pd.DataFrame(rows)


def render_regional_banking_map(reader_view, query, jordan_docs=None):
    map_data = build_regional_map_data(reader_view, query, jordan_docs)
    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            id="country-markers",
            get_position="[longitude, latitude]",
            get_radius="radius",
            get_fill_color="fill_color",
            get_line_color="line_color",
            line_width_min_pixels=1,
            stroked=True,
            filled=True,
            pickable=True,
            auto_highlight=True,
        ),
        pdk.Layer(
            "TextLayer",
            data=map_data,
            id="country-labels",
            get_position="[longitude, latitude]",
            get_text="code",
            get_size=12,
            get_color=[255, 255, 255, 245],
            get_text_anchor="'middle'",
            get_alignment_baseline="'center'",
        ),
    ]
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=31.1,
            longitude=40.9,
            zoom=3.25,
            pitch=0,
        ),
        layers=layers,
        tooltip={
            "html": (
                "<b>{country}</b><br/>"
                "{regulator}<br/>"
                "{status}<br/>"
                "{coverage}<br/>"
                "Text hits: {text_hits}"
            ),
            "style": {
                "backgroundColor": "#172026",
                "color": "#fffefa",
                "fontSize": "12px",
            },
        },
    )

    st.markdown("**Regional banking map**")
    st.caption(
        "Middle East comparison layer. Israel is linked to the current BOI "
        "search results; other jurisdictions are ready for external "
        "publication feeds.")
    map_state = st.pydeck_chart(
        deck,
        height=420,
        key="regional_banking_map",
        on_select="rerun",
        selection_mode="single-object")

    selected_country = None
    selection = getattr(map_state, "selection", {}) or {}
    objects = selection.get("objects", {}) if isinstance(selection, dict) else {}
    picked = objects.get("country-markers", []) if isinstance(objects, dict) else []
    if picked:
        selected_country = picked[0].get("country")

    return selected_country


def get_pdf_catalog(catalog, directives=None):
    doc_type = catalog["doc_type"].fillna("").astype(str).str.strip().str.lower()
    pdf_catalog = catalog[doc_type == "pdf"].copy()

    if directives is not None and not directives.empty:
        directive_rows = pd.DataFrame({
            "source_page": directives["url"].fillna(""),
            "source_title": (
                "Proper Conduct Directive "
                + directives["directive_number"].fillna("").astype(str)
                + " - "
                + directives["title_display"].fillna("").astype(str)),
            "section": "proper-conduct",
            "lastmod": directives["lastmod"].fillna(""),
            "doc_title": "Directive PDF",
            "doc_url": directives["file_url"].fillna(""),
            "doc_type": "pdf",
            "country": "Israel",
            "regulator": "Bank of Israel",
            "publication_type": "Proper Conduct Directives",
            "connection_status": "proper_conduct_directive",
        })
        directive_rows = directive_rows[
            directive_rows["doc_url"].astype(str).str.len() > 0]
        pdf_catalog = pd.concat([pdf_catalog, directive_rows], ignore_index=True)

    pdf_catalog = pdf_catalog.drop_duplicates(
        subset=["doc_url"]).reset_index(drop=True)
    return with_publication_type(pdf_catalog)


def read_index_pid():
    if not os.path.exists(INDEX_PID):
        return None
    try:
        with open(INDEX_PID, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def process_is_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def pdf_index_process():
    pid = read_index_pid()
    running = process_is_running(pid)
    if pid and not running:
        try:
            os.remove(INDEX_PID)
        except OSError:
            pass
    return pid if running else None


def start_pdf_text_index():
    running_pid = pdf_index_process()
    if running_pid:
        return running_pid

    os.makedirs(TEXT_DIR, exist_ok=True)
    with open(INDEX_LOG, "a", encoding="utf-8") as log:
        log.write(f"\n\n== started {time.strftime('%Y-%m-%d %H:%M:%S')} ==\n")
        log.flush()
        proc = subprocess.Popen(
            [sys.executable, "-u", "boi_pdf_text.py"],
            cwd=HERE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True)

    with open(INDEX_PID, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))
    return proc.pid


def stop_pdf_text_index():
    pid = pdf_index_process()
    if not pid:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    return True


def read_index_log_tail(chars=5000):
    if not os.path.exists(INDEX_LOG):
        return ""
    try:
        with open(INDEX_LOG, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - chars))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def search_corpus_signature():
    if not os.path.isdir(TEXT_DIR):
        return (file_mtime(MANIFEST), file_mtime(LOCAL_MANIFEST))
    files = []
    for name in sorted(os.listdir(TEXT_DIR)):
        if not name.endswith(".txt.gz"):
            continue
        path = os.path.join(TEXT_DIR, name)
        files.append((name, os.path.getmtime(path), os.path.getsize(path)))
    return (file_mtime(MANIFEST), file_mtime(LOCAL_MANIFEST), tuple(files))


def parse_terms(query):
    terms = []
    for quoted, bare in re.findall(r'"([^"]+)"|(\S+)', query):
        term = (quoted or bare).strip().strip(",;:").lower()
        if term and term not in terms:
            terms.append(term)
    return terms


def normalize_search_text(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def exact_search_phrase(query):
    phrase = query.strip()
    if len(phrase) >= 2 and phrase[0] == '"' and phrase[-1] == '"':
        phrase = phrase[1:-1]
    return normalize_search_text(phrase)


def search_terms_for_mode(query, match_mode):
    if match_mode == "Exact match":
        phrase = exact_search_phrase(query)
        return [phrase] if phrase else []
    return parse_terms(query)


def find_snippets(text, terms, width=240, limit=3):
    flat = re.sub(r"\s+", " ", text).strip()
    lowered = flat.lower()
    positions = []
    for term in terms:
        pos = lowered.find(term)
        while pos != -1:
            positions.append(pos)
            pos = lowered.find(term, pos + max(1, len(term)))
            if len(positions) >= limit * len(terms) * 3:
                break
    snippets = []
    last_end = -1
    for pos in sorted(positions):
        start = max(0, pos - width // 2)
        end = min(len(flat), pos + width // 2)
        if start <= last_end:
            continue
        snippets.append(
            ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")
        )
        last_end = end
        if len(snippets) == limit:
            break
    return "\n\n".join(snippets)


def search_full_text(docs, terms, match_mode, limit):
    rows = []
    exact_match = match_mode == "Exact match"
    for _, row in docs.iterrows():
        text = row["_text"]
        lowered = normalize_search_text(text) if exact_match else text.lower()
        counts = {term: lowered.count(term) for term in terms}
        matched = {term: count for term, count in counts.items() if count}
        if not matched:
            continue

        rows.append({
            "source_title": row["source_title"],
            "doc_title": row["doc_title"],
            "section": row["section"],
            "lastmod": row["lastmod"],
            "pages": row["pages"],
            "matches": sum(matched.values()),
            "matched_terms": ", ".join(matched),
            "snippet": find_snippets(text, terms),
            "doc_url": row["doc_url"],
            "txt_path": row["txt_path"],
            "_text": text,
        })

    results = pd.DataFrame(rows)
    if results.empty:
        return results
    return results.sort_values(
        ["matches", "lastmod", "source_title"],
        ascending=[False, False, True],
    ).head(limit)


def build_reader_results(pdf_catalog, docs, query, limit=200):
    view = pdf_catalog.copy()
    view["metadata_matches"] = 0
    view["full_text_matches"] = 0
    view["matched_terms"] = ""
    view["search_snippet"] = ""
    view["search_source"] = "Catalog"

    query = query.strip()
    if not query:
        return view

    terms = parse_terms(query)
    if not terms:
        return view.iloc[0:0].copy()

    hay = (view["source_title"] + " " + view["doc_title"] + " "
           + view["doc_url"]).str.lower()
    metadata_scores = hay.apply(
        lambda text: sum(text.count(term) for term in terms)
        + (1 if query.lower() in text else 0))

    full_text_results = pd.DataFrame()
    if not docs.empty:
        full_text_results = search_full_text(docs, terms, "Broad match", limit)

    metadata_urls = set(view.loc[metadata_scores > 0, "doc_url"])
    full_text_urls = set(full_text_results["doc_url"]) if not full_text_results.empty else set()
    matched_urls = metadata_urls | full_text_urls
    result = view[view["doc_url"].isin(matched_urls)].copy()
    if result.empty:
        return result

    result["metadata_matches"] = metadata_scores.loc[result.index].astype(int)
    if not full_text_results.empty:
        indexed = full_text_results.set_index("doc_url")
        result["full_text_matches"] = (
            result["doc_url"].map(indexed["matches"]).fillna(0).astype(int))
        result["matched_terms"] = result["doc_url"].map(indexed["matched_terms"]).fillna("")
        result["search_snippet"] = result["doc_url"].map(indexed["snippet"]).fillna("")
    result["search_source"] = result["full_text_matches"].apply(
        lambda hits: "Full text" if hits else "Catalog")
    return result.sort_values(
        ["full_text_matches", "metadata_matches", "lastmod", "source_title"],
        ascending=[False, False, False, True],
    ).head(limit)


def build_full_text_pdf_results(pdf_catalog, docs, query, match_mode, limit=500):
    query = query.strip()
    if not query:
        result = pdf_catalog.copy()
        result["full_text_matches"] = 0
        result["matched_terms"] = ""
        result["search_snippet"] = ""
        return result

    terms = search_terms_for_mode(query, match_mode)
    if not terms or docs.empty:
        return pd.DataFrame()

    results = search_full_text(docs, terms, match_mode, limit)
    if results.empty:
        return results

    metadata = pdf_catalog.drop_duplicates(subset=["doc_url"]).set_index("doc_url")

    def fill_from_catalog(col):
        if col not in metadata.columns:
            return
        mapped = results["doc_url"].map(metadata[col]).fillna("")
        if col in results.columns:
            current = results[col].fillna("").astype(str)
            results[col] = current.where(current.str.len() > 0, mapped)
        else:
            results[col] = mapped

    for col in (
            "source_title", "doc_title", "section", "publication_type",
            "lastmod", "doc_type"):
        fill_from_catalog(col)

    if "doc_type" not in results.columns:
        results["doc_type"] = "pdf"
    if "publication_type" not in results.columns:
        results["publication_type"] = results.apply(
            classify_publication_type, axis=1)
    else:
        missing_type = results["publication_type"].fillna("").astype(str) == ""
        if missing_type.any():
            results.loc[missing_type, "publication_type"] = results[
                missing_type].apply(classify_publication_type, axis=1)
    if "pages" in results.columns:
        results["pages"] = pd.to_numeric(results["pages"], errors="coerce")
    results["full_text_matches"] = results["matches"].fillna(0).astype(int)
    results["search_snippet"] = results["snippet"].fillna("")
    results["search_source"] = "Full text"
    return results.sort_values(
        ["full_text_matches", "lastmod", "source_title"],
        ascending=[False, False, True],
    ).head(limit)


def extract_directive_number(*parts):
    text = " ".join(str(part or "") for part in parts).lower()
    patterns = [
        r"\bdirective\s+(?:no|number)\s*\.?\s*(\d{3}[a-z]?)\b",
        r"\b(?:nbt|pc|enbt)[\s_-]*(\d{3}[a-z]?)\b",
        r"\b(\d{3}[a-z]?)\s*(?:nbt|en|et)\b",
        r"/(?:nbt|pc|enbt)?[_-]?(\d{3}[a-z]?)(?:[_-]?(?:en|et|nbt))?/?$",
        r"\b(\d{3}[a-z]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).upper()
    return ""


SUBJECT_TRANSLATIONS = {
    "Interest rate risk": "Interest Rate Risk",
    "איסור הלבנת הון": "Anti-Money Laundering",
    "אמצעי תשלום": "Means of Payment",
    "בנקים חדשים": "New Banks",
    "הלוואות וחובות": "Loans and Debts",
    "הלוואות לדיור": "Housing Loans",
    "הלימות ההון ומינוף": "Capital Adequacy and Leverage",
    "חלוקה (דיבידנד ורכישה)": "Distribution (Dividend and Buyback)",
    "חשבונות בנק": "Bank Accounts",
    "חשבונות ללא תנועה": "Dormant Accounts",
    "מיקור חוץ": "Outsourcing",
    "ממשל תאגידי": "Corporate Governance",
    "נזילות": "Liquidity",
    "ניהול ובקרה": "Management and Control",
    "ניהול סיכונים": "Risk Management",
    "ניירות ערך": "Securities",
    "סיכון אשראי": "Credit Risk",
    "סיכון תפעולי": "Operational Risk",
    "סיכוני טכנולוגיית המידע, אבטחת מידע והגנת סייבר": (
        "Information Technology Risk, Information Security and Cyber Defense"),
    "סיכוני שוק": "Market Risk",
    "סיכונים סביבתיים": "Environmental Risks",
    "עמלות": "Fees",
    "ערבויות": "Guarantees",
    "פעילויות שוק ההון": "Capital Market Activities",
    "פתיחת סניפים והצבת ATM": "Opening Branches and Placing ATMs",
    "רואה החשבון המבקר": "External Auditor",
    "ריבית": "Interest",
    "שיקים ללא כיסוי": "Checks Without Cover",
    "שליטה והחזקה": "Control and Holdings",
    "תאגידים בנקאיים ייחודיים ותאגידים אחרים": (
        "Special Banking Corporations and Other Entities"),
}


def translate_subject(subject):
    subject = str(subject or "").strip()
    if not subject:
        return ""
    return SUBJECT_TRANSLATIONS.get(subject, subject)


def prepare_proper_conduct_directives(df):
    required = (
        "title", "url", "lastmod", "publication_date", "directive_number",
        "circular_number", "area", "subject", "file_url", "page_title",
        "status")
    directives = df.copy()
    for col in required:
        if col not in directives.columns:
            directives[col] = ""
        directives[col] = directives[col].fillna("").astype(str)

    if "status" in directives.columns:
        status = directives["status"].str.lower()
        directives = directives[status.isin(("", "ok"))].copy()

    title = directives["page_title"].where(
        directives["page_title"].str.len() > 0, directives["title"])
    directives["title_display"] = title.str.replace(r"\s+", " ", regex=True)
    directives["subject_display"] = directives["subject"].apply(
        translate_subject)
    missing_numbers = directives["directive_number"].str.len() == 0
    directives.loc[missing_numbers, "directive_number"] = directives[
        missing_numbers].apply(
            lambda row: extract_directive_number(
                row["title"], row["page_title"], row["url"]),
            axis=1)

    sort_number = directives["directive_number"].str.extract(r"(\d+)")[0]
    directives["_sort_number"] = pd.to_numeric(
        sort_number, errors="coerce").fillna(9999).astype(int)
    directives["_sort_suffix"] = directives["directive_number"].str.extract(
        r"\d+([A-Za-z]+)")[0].fillna("")
    return directives.sort_values(
        ["_sort_number", "_sort_suffix", "title_display"],
        ascending=[True, True, True])


def load_proper_conduct_directives():
    directives = load_proper_conduct_metadata(
        file_mtime(PROPER_CONDUCT_DIRECTIVES))
    if directives.empty:
        publications = load_publications_index(file_mtime(PUBLICATIONS_INDEX))
        if publications.empty:
            return publications
        proper = publications["url"].str.contains(
            "/proper_conduct/", case=False, na=False)
        directives = publications[proper].copy()
        slugs = directives["url"].str.rstrip("/").str.split("/").str[-1]
        directives = directives[slugs != "proper_conduct"]
    return prepare_proper_conduct_directives(directives)


def apply_library_styles():
    st.markdown(
        """
        <style>
        :root {
            --boi-navy: #17345b;
            --boi-navy-hover: #102845;
            --boi-ink: #222222;
            --boi-muted: #666666;
            --boi-line: #ddddda;
            --boi-search: #ececea;
            --boi-paper: #ffffff;
            --boi-page: #f7f7f5;
            --boi-banner: #eef5ff;
            --boi-banner-border: #d6e5ff;
            --boi-teal: #006d7e;
            --boi-blue: #6fa6bd;
            --boi-gold: #c0ad5c;
            --boi-green: #5f986c;
            --boi-rose: #9b2f4a;
            --boi-purple: #5d3f85;
            --boi-serif: Georgia, "Times New Roman", serif;
            --boi-ui: ui-sans-serif, system-ui, -apple-system,
                BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif;
        }

        .stApp {
            background: var(--boi-page);
        }

        .block-container {
            max-width: 1280px;
            padding-top: 1rem;
            padding-bottom: 3.25rem;
            background: var(--boi-paper);
        }

        [data-testid="stSidebar"] {
            display: none;
        }

        h1, h2, h3, p, div, span, label, button, input {
            letter-spacing: 0;
            font-family: var(--boi-ui);
        }

        a {
            color: var(--boi-navy);
        }

        .boi-topbar {
            display: grid;
            grid-template-columns: minmax(0, 1fr) max-content;
            align-items: center;
            column-gap: clamp(0.8rem, 2vw, 1.5rem);
            border-bottom: 1px solid var(--boi-line);
            min-height: 68px;
            padding: 0.25rem 0;
            margin-bottom: 0;
            background: var(--boi-paper);
        }

        .boi-brand {
            color: var(--boi-ink);
            flex: 1 1 auto;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: clamp(1rem, 1.28vw, 1.22rem);
            font-weight: 700;
            line-height: 1.2;
        }

        .boi-nav {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            flex-wrap: nowrap;
            min-width: max-content;
            gap: clamp(0.72rem, 1.5vw, 1.6rem);
            color: var(--boi-muted);
            font-size: clamp(0.82rem, 0.95vw, 1rem);
            font-weight: 650;
            line-height: 1.45;
            white-space: nowrap;
        }

        .boi-nav span {
            flex: 0 0 auto;
        }

        .boi-nav span:first-child {
            color: var(--boi-navy);
            font-weight: 650;
        }

        .boi-library-head {
            display: grid;
            grid-template-columns: minmax(0, 760px) minmax(290px, 340px);
            justify-content: center;
            gap: clamp(2rem, 5vw, 5rem);
            align-items: start;
            padding: 4.8rem 0 2.3rem;
            margin-bottom: 0.5rem;
        }

        .boi-kicker {
            color: var(--boi-muted);
            font-size: 0.82rem;
            font-weight: 750;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .boi-page-title {
            color: var(--boi-muted);
            font-size: clamp(1.45rem, 2.1vw, 1.85rem);
            font-weight: 750;
            line-height: 1.2;
            margin: 0 0 1.7rem;
        }

        h1.boi-page-title {
            color: var(--boi-muted) !important;
            font-size: clamp(1.45rem, 2.1vw, 1.85rem) !important;
            line-height: 1.2 !important;
        }

        .boi-language-toggle {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            border: 1px solid var(--boi-line);
            border-radius: 999px;
            padding: 0.3rem 0.7rem;
            color: var(--boi-muted);
            font-size: 0.82rem;
            background: var(--boi-paper);
        }

        .boi-language-toggle strong {
            color: var(--boi-ink);
            font-weight: 650;
        }

        .boi-shelf {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            column-gap: 1.6rem;
            row-gap: 2rem;
            border-top: 0;
            margin-top: 1.2rem;
        }

        .boi-shelf-item {
            display: grid;
            grid-template-columns: 1fr;
            gap: 0.55rem;
            align-items: start;
            border-bottom: 0;
            padding: 0;
        }

        .boi-shelf-item::before {
            content: "";
            display: block;
            height: 4px;
            width: 100%;
            margin-bottom: 0.55rem;
            background: var(--boi-teal);
        }

        .boi-shelf-item:nth-child(2)::before {
            background: var(--boi-blue);
        }

        .boi-shelf-item:nth-child(3)::before {
            background: var(--boi-gold);
        }

        .boi-shelf-title {
            color: var(--boi-ink);
            font-family: var(--boi-serif);
            font-size: clamp(1.45rem, 2vw, 1.82rem);
            font-weight: 400;
            line-height: 1.15;
        }

        .boi-shelf-copy {
            color: var(--boi-muted);
            font-size: 0.98rem;
            line-height: 1.42;
        }

        .boi-shelf-count {
            color: var(--boi-muted);
            font-size: 0.86rem;
            font-weight: 650;
            white-space: nowrap;
        }

        .boi-catalog-shelf {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            column-gap: clamp(1.2rem, 3vw, 2rem);
            row-gap: 2.15rem;
            margin: 1.15rem 0 1.85rem;
        }

        .boi-catalog-type {
            min-width: 0;
            padding: 0;
        }

        .boi-catalog-rule {
            height: 4px;
            width: 100%;
            margin-bottom: 0.65rem;
        }

        .boi-catalog-title {
            color: #050505;
            font-family: var(--boi-serif);
            font-size: clamp(1.35rem, 2vw, 1.82rem);
            font-weight: 400;
            line-height: 1.15;
            margin-bottom: 0.65rem;
        }

        .boi-catalog-copy {
            color: var(--boi-muted);
            font-size: 0.98rem;
            font-weight: 520;
            line-height: 1.42;
            max-width: 38rem;
        }

        .boi-catalog-meta {
            color: var(--boi-muted);
            font-size: 0.84rem;
            font-weight: 700;
            margin-top: 0.75rem;
        }

        .boi-compare-panel {
            display: grid;
            gap: 1rem;
            margin: 0.9rem 0 1.4rem;
            padding: 1rem;
            border: 1px solid var(--boi-line);
            border-radius: 6px;
            background: #fbfbfa;
        }

        .boi-compare-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: start;
        }

        .boi-compare-title {
            color: var(--boi-ink);
            font-family: var(--boi-serif);
            font-size: clamp(1.25rem, 1.8vw, 1.55rem);
            line-height: 1.15;
        }

        .boi-compare-count {
            color: var(--boi-navy);
            font-size: 0.86rem;
            font-weight: 800;
            white-space: nowrap;
        }

        .boi-compare-venn {
            position: relative;
            height: 160px;
            max-width: 390px;
            margin: 0.2rem auto;
        }

        .boi-compare-circle {
            position: absolute;
            top: 8px;
            display: grid;
            place-items: center;
            align-content: center;
            width: 150px;
            height: 150px;
            border: 2px solid rgba(23, 52, 91, 0.45);
            border-radius: 50%;
            color: var(--boi-navy);
            background: rgba(0, 109, 126, 0.16);
            text-align: center;
        }

        .boi-compare-circle.right {
            right: 0;
            border-color: rgba(95, 152, 108, 0.65);
            color: #2b6843;
            background: rgba(95, 152, 108, 0.17);
        }

        .boi-compare-circle.left {
            left: 0;
        }

        .boi-compare-circle strong {
            font-size: 1rem;
        }

        .boi-compare-circle span,
        .boi-compare-overlap span {
            color: var(--boi-muted);
            font-size: 0.78rem;
            font-weight: 700;
        }

        .boi-compare-overlap {
            position: absolute;
            left: 50%;
            top: 50%;
            z-index: 2;
            display: grid;
            place-items: center;
            width: 92px;
            min-height: 62px;
            padding: 0.5rem;
            transform: translate(-50%, -50%);
            border: 1px solid var(--boi-line);
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.92);
            box-shadow: rgba(0, 0, 0, 0.08) 0 4px 18px;
            color: var(--boi-ink);
            text-align: center;
        }

        .boi-compare-overlap strong {
            font-size: 1.45rem;
            line-height: 1;
        }

        .boi-compare-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.8rem;
        }

        .boi-compare-grid > div {
            display: grid;
            gap: 0.55rem;
            min-width: 0;
        }

        .boi-compare-grid b {
            color: var(--boi-ink);
            font-size: 0.9rem;
            line-height: 1.25;
        }

        .boi-compare-chip {
            display: inline-block;
            margin: 0 0.35rem 0.35rem 0;
            padding: 0.25rem 0.5rem;
            border: 1px solid var(--boi-line);
            border-radius: 999px;
            color: var(--boi-navy);
            background: var(--boi-paper);
            font-size: 0.76rem;
            font-weight: 700;
        }

        .boi-compare-chip.muted {
            color: var(--boi-muted);
        }

        .boi-info-panel {
            border-top: 1px solid var(--boi-line);
            border-bottom: 0;
            padding: 1.25rem 0 0;
        }

        .boi-info-panel + .boi-info-panel {
            margin-top: 1.65rem;
        }

        .boi-panel-title {
            color: var(--boi-muted);
            font-size: clamp(1.25rem, 1.8vw, 1.55rem);
            font-weight: 750;
            margin-bottom: 0.9rem;
        }

        .boi-panel-copy, .boi-panel-list {
            color: var(--boi-muted);
            font-size: 0.96rem;
            line-height: 1.52;
        }

        .boi-panel-list {
            display: grid;
            gap: 0.55rem;
            margin-top: 0.75rem;
        }

        .boi-section-rule {
            border-top: 1px solid var(--boi-line);
            margin: 1.4rem 0 1.2rem;
        }

        .boi-section-title {
            color: var(--boi-ink);
            font-size: 1.45rem;
            font-weight: 750;
            margin: 0 0 0.6rem;
        }

        h2.boi-section-title {
            color: var(--boi-ink) !important;
            font-size: 1.45rem !important;
            line-height: 1.2 !important;
        }

        div[data-testid="stSegmentedControl"] {
            margin: 0.75rem 0 0.2rem;
        }

        div[data-testid="stButtonGroup"] {
            margin: 0.75rem 0 0.2rem;
        }

        div[data-testid="stButtonGroup"] button {
            border-color: var(--boi-line) !important;
            background: var(--boi-paper) !important;
            color: var(--boi-ink) !important;
        }

        div[data-testid="stButtonGroup"]
        button[data-testid="stBaseButton-segmented_controlActive"] {
            border-color: var(--boi-navy) !important;
            background: rgba(23, 52, 91, 0.08) !important;
            color: var(--boi-navy) !important;
        }

        div[data-testid="stButtonGroup"]
        button[data-testid="stBaseButton-segmented_controlActive"] p {
            color: var(--boi-navy) !important;
        }

        div[data-testid="stMetric"] {
            background: var(--boi-paper);
            border: 1px solid var(--boi-line);
            border-radius: 6px;
            padding: 0.75rem 0.9rem;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
            background: var(--boi-search);
            border-color: transparent;
            border-radius: 18px;
        }

        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stLinkButton"] a {
            border-radius: 4px;
            border-color: var(--boi-navy);
        }

        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"],
        div[data-testid="stLinkButton"] a {
            background: var(--boi-navy);
            color: white;
            box-shadow: rgba(0, 0, 0, 0.18) 0 2px 6px;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        div[data-testid="stLinkButton"] a:hover {
            border-color: var(--boi-navy-hover);
            color: var(--boi-navy-hover);
        }

        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover,
        div[data-testid="stLinkButton"] a:hover {
            background: var(--boi-navy-hover);
            color: white;
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border-color: var(--boi-line);
        }

        @media (max-width: 820px) {
            .boi-library-head {
                display: block;
                padding-top: 2.5rem;
            }

            .boi-shelf {
                grid-template-columns: 1fr;
            }

            .boi-catalog-shelf {
                grid-template-columns: 1fr;
            }

            .boi-compare-grid {
                grid-template-columns: 1fr;
            }

            .boi-nav {
                font-size: 0.74rem;
                gap: 0.42rem;
            }

            .boi-shelf-copy {
                margin-top: 0.35rem;
            }

            .boi-shelf-count {
                margin-top: 0.65rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True)


def render_library_shell(catalog, directives, jordan_docs=None):
    country_catalog = build_country_catalog(catalog, jordan_docs)
    pdf_count = len(get_pdf_catalog(catalog, directives))
    numbered = (
        int(directives["directive_number"].str.len().gt(0).sum())
        if not directives.empty else 0)
    latest = directives["lastmod"].max()[:10] if not directives.empty else "n/a"
    manifest = load_text_manifest(
        (file_mtime(MANIFEST), file_mtime(LOCAL_MANIFEST)))
    indexed_docs = 0
    if not manifest.empty:
        ok = manifest[manifest["status"].astype(str).str.lower() == "ok"]
        indexed_docs = len(ok.drop_duplicates(subset=["doc_url"]))

    st.markdown(
        f"""
        <div class="boi-topbar">
            <div class="boi-brand">ORM Tool</div>
            <div class="boi-nav">
                <span>Catalog</span>
                <span>Directives</span>
                <span>Reader</span>
                <span>Search</span>
            </div>
        </div>
        <div class="boi-library-head">
            <div>
                <div class="boi-kicker">Library</div>
                <h1 class="boi-page-title">Browse the Library</h1>
                <div class="boi-language-toggle">
                    <strong>English</strong><span>Hebrew source data</span>
                </div>
                <div class="boi-shelf">
                    <div class="boi-shelf-item">
                        <div class="boi-shelf-title">Catalog</div>
                        <div class="boi-shelf-copy">
                            Official Bank of Israel publication links,
                            regional source records, metadata, source pages,
                            and extractable documents.
                        </div>
                        <div class="boi-shelf-count">
                            {len(country_catalog):,} docs / {
                                country_catalog['country'].nunique():,} countries
                        </div>
                    </div>
                    <div class="boi-shelf-item">
                        <div class="boi-shelf-title">Reader</div>
                        <div class="boi-shelf-copy">
                            Searchable PDFs, including Proper Conduct directives,
                            with extracted text, highlighted matches, page
                            navigation, and downloadable sources.
                        </div>
                        <div class="boi-shelf-count">
                            {pdf_count:,} PDFs / {numbered:,} directives
                        </div>
                    </div>
                </div>
            </div>
            <div>
                <div class="boi-info-panel">
                    <div class="boi-panel-title">A Living BOI Library</div>
                    <div class="boi-panel-copy">
                        A compact index for Bank of Israel publications,
                        supervisory materials, and directive PDFs.
                    </div>
                </div>
                <div class="boi-info-panel">
                    <div class="boi-panel-title">Current Index</div>
                    <div class="boi-panel-list">
                        <div>{len(directives):,} proper conduct directives</div>
                        <div>{indexed_docs:,} full-text PDFs indexed</div>
                        <div>Latest directive update: {latest}</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True)

    sections = [
        "Catalog",
        "Reader",
        "Regional Map",
        "Risk Compare",
    ]
    _, selector_col, _ = st.columns([1, 2, 1])
    with selector_col:
        selected = st.segmented_control(
            "Library section",
            sections,
            default="Catalog",
            key="library_section",
            label_visibility="collapsed",
            width="stretch")
    st.markdown('<div class="boi-section-rule"></div>', unsafe_allow_html=True)
    return selected or "Catalog"


def render_section_heading(title):
    st.markdown(
        f'<h2 class="boi-section-title">{title}</h2>',
        unsafe_allow_html=True)


def render_catalog_section(catalog, jordan_docs=None):
    render_section_heading("Catalog")
    catalog = build_country_catalog(catalog, jordan_docs)
    query = st.text_input(
        "Search title / URL",
        "",
        placeholder="Israel, Jordan, annual report, inflation, monetary policy",
        key="catalog_query")

    filter_1, filter_2, filter_3, filter_4 = st.columns(4)
    countries = ordered_countries(catalog["country"].unique())
    publication_types = ordered_publication_types(
        catalog["publication_type"].unique())
    types = sorted(t for t in catalog["doc_type"].unique() if t)
    only_dated = catalog[catalog["lastmod"] != ""]
    years = (
        sorted({d[:4] for d in only_dated["lastmod"] if len(d) >= 4})
        if not only_dated.empty else [])
    with filter_1:
        pick_countries = st.multiselect("Country", countries, default=[])
    with filter_2:
        pick_publication_types = st.multiselect(
            "Publications", publication_types, default=[])
    with filter_3:
        pick_types = st.multiselect("File type", types, default=[])
    with filter_4:
        pick_years = st.multiselect("Year", years, default=[])

    view = catalog
    if query:
        q = query.lower()
        hay = (view["doc_title"] + " " + view["source_title"] + " "
               + view["doc_url"] + " " + view["country"] + " "
               + view["regulator"]).str.lower()
        view = view[hay.str.contains(q, regex=False)]
    if pick_countries:
        view = view[view["country"].isin(pick_countries)]
    if pick_publication_types:
        view = view[view["publication_type"].isin(pick_publication_types)]
    if pick_types:
        view = view[view["doc_type"].isin(pick_types)]
    if pick_years:
        view = view[view["lastmod"].str[:4].isin(pick_years)]

    view = order_catalog_by_publication_type(view)
    st.markdown(f"**{len(view):,}** documents match.")
    render_catalog_type_shelf(view)

    display = view[[
        "country", "source_title", "publication_type", "doc_type", "lastmod",
        "doc_url"
    ]].copy()
    display.insert(0, "select", False)
    edited = st.data_editor(
        display, hide_index=True, width="stretch", height=420,
        column_config={
            "select": st.column_config.CheckboxColumn("✓", width="small"),
            "country": st.column_config.TextColumn(
                "Country", width="small"),
            "source_title": "Publication",
            "publication_type": st.column_config.TextColumn(
                "Publications", width="medium"),
            "doc_type": st.column_config.TextColumn("Type", width="small"),
            "lastmod": st.column_config.TextColumn("Updated", width="medium"),
            "doc_url": st.column_config.LinkColumn(
                "Link text",
                display_text="Link text",
                width="medium"),
        },
        disabled=[
            "country", "source_title", "publication_type", "doc_type",
            "lastmod", "doc_url"
        ],
        key="catalog_editor")

    chosen_rows = edited[edited["select"]].copy()
    chosen = chosen_rows[
        chosen_rows["doc_type"].astype(str).str.lower() == "pdf"
    ]["doc_url"].tolist()
    c1, c2 = st.columns([1, 3])
    with c1:
        go = st.button(f"Extract PDF text ({len(chosen)})",
                       type="primary", disabled=not chosen)
    with c2:
        st.download_button("Download filtered catalog (CSV)",
                           view.to_csv(index=False).encode("utf-8"),
                           "boi_filtered_catalog.csv", "text/csv")
    if len(chosen_rows) > len(chosen):
        st.caption(
            "Text extraction is available for selected PDF rows. Country "
            "records that point to web indexes remain searchable as catalog "
            "metadata.")

    if go:
        prog = st.progress(0.0)
        for i, url in enumerate(chosen, 1):
            try:
                pages, text = get_text(url)
                title = (view.loc[view["doc_url"] == url, "source_title"].iloc[0]
                         or url.rsplit("/", 1)[-1])
                with st.expander(f"{title} - {pages} pages, "
                                 f"{len(text):,} chars", expanded=(i == 1)):
                    st.caption(url)
                    st.download_button("Save text (.txt)", text.encode("utf-8"),
                                       slug_for(url) + ".txt", "text/plain",
                                       key="dl_" + slug_for(url))
                    st.text_area("Text", text, height=320,
                                 key="ta_" + slug_for(url))
            except Exception as e:
                st.error(f"Failed to extract {url}: {e}")
            prog.progress(i / len(chosen))
        prog.empty()
        st.success(f"Extracted {len(chosen)} document(s).")


def render_country_publication_browser(country_view, country, key_prefix):
    st.subheader(f"{country} Publications")
    if country_view.empty:
        st.info(
            f"No connected publication records are available for {country} yet.")
        return

    render_catalog_type_shelf(country_view)
    query = st.text_input(
        f"Search {country} publications",
        placeholder="annual report, directives, exchange rates, stability",
        key=f"{key_prefix}_query")
    view = country_view.copy()
    if query.strip():
        q = query.strip().lower()
        haystack = view[[
            "source_title", "doc_title", "publication_type", "doc_type",
            "lastmod", "doc_url", "regulator",
        ]].astype(str).agg(" ".join, axis=1).str.lower()
        view = view[haystack.str.contains(q, regex=False, na=False)]

    view = order_catalog_by_publication_type(view)
    st.write(f"{len(view):,} {country} publication records match.")
    display = view[[
        "source_title", "publication_type", "doc_type", "lastmod", "doc_url"
    ]].copy()
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            "source_title": "Publication",
            "publication_type": "Publication type",
            "doc_type": st.column_config.TextColumn("Type", width="small"),
            "lastmod": st.column_config.TextColumn("Updated", width="medium"),
            "doc_url": st.column_config.LinkColumn(
                "Official link", display_text="Open", width="medium"),
        })
    st.download_button(
        f"Download {country} publications (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        f"{slug_for(country)}_publications.csv",
        "text/csv",
        key=f"{key_prefix}_download")


def render_regional_map_section(
        catalog, directives, jordan_docs=None, jordan_reports=None,
        jordan_reserves=None, jordan_fx_rates=None, overnight_rates=None,
        israel_reserve_rows=None, banking_indicators=None):
    render_section_heading("Regional Banking Map")
    pdf_catalog = get_pdf_catalog(catalog, directives)
    if jordan_docs is None:
        jordan_docs = load_jordan_cbj_regulations(
            file_mtime(JORDAN_CBJ_REGULATIONS))
    if jordan_reports is None:
        jordan_reports = load_jordan_financial_stability_reports(
            file_mtime(JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS))
    if jordan_reserves is None:
        jordan_reserves = load_jordan_foreign_exchange_reserves(
            file_mtime(JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES))
    if jordan_fx_rates is None:
        jordan_fx_rates = load_jordan_fx_rates(
            file_mtime(JORDAN_CBJ_FX_RATES))
    if banking_indicators is None:
        banking_indicators = load_banking_sector_indicators(
            file_mtime(BANKING_SECTOR_INDICATORS))
    jordan_corpus = combine_jordan_docs(
        jordan_docs, jordan_reports, jordan_reserves, jordan_fx_rates)
    connected_feeds = (
        int(not jordan_docs.empty)
        + int(not jordan_reports.empty)
        + int(not jordan_reserves.empty)
        + int(not jordan_fx_rates.empty))
    pending_feeds = max(
        0, len(REGIONAL_BANKING_MARKETS) - 1 - connected_feeds)
    directive_stats = directive_update_stats(directives)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Mapped markets", f"{len(REGIONAL_BANKING_MARKETS):,}")
    m2.metric("BOI PDFs", f"{len(pdf_catalog):,}")
    m3.metric("Jordan CBJ records", f"{len(jordan_corpus):,}")
    m4.metric("Other feeds", f"{pending_feeds:,} pending")
    m5.metric(
        "Directive update rate",
        directive_stats["rate_label"],
        directive_stats["recent_label"])

    st.caption(
        "This layer is separated from the Reader. It is the workspace for "
        "comparing Bank of Israel publications with regional banking "
        "regulators as additional country corpora are connected.")
    selected_from_map = render_regional_banking_map(
        pdf_catalog, "", jordan_corpus)

    map_data = build_regional_map_data(pdf_catalog, "", jordan_corpus)
    country_options = ordered_countries(
        market["country"] for market in REGIONAL_BANKING_MARKETS)
    if selected_from_map in country_options:
        st.session_state.regional_publication_country = selected_from_map
    elif "regional_publication_country" not in st.session_state:
        st.session_state.regional_publication_country = (
            "Jordan" if "Jordan" in country_options else country_options[0])

    selected_publication_country = st.selectbox(
        "Publication country",
        country_options,
        key="regional_publication_country",
        help="Choose which country's publications should be shown below.")
    selected_market = map_data[
        map_data["country"] == selected_publication_country]
    if not selected_market.empty:
        selected_market = selected_market.iloc[0]
        detail_1, detail_2, detail_3, detail_4 = st.columns(4)
        detail_1.markdown(
            f"**Regulator**  \n{selected_market['regulator']}")
        detail_2.markdown(
            f"**Corpus status**  \n{selected_market['status']}")
        detail_3.markdown(
            f"**Coverage**  \n{selected_market['coverage']}")
        if selected_publication_country == "Israel":
            detail_4.markdown(
                "**Directive update rate**  \n"
                f"{directive_stats['rate_label']} · latest "
                f"{directive_stats['latest_label']}")
        else:
            detail_4.markdown(
                "**Directive update rate**  \nNot connected")

    render_directive_banking_indicator_regression(
        directives, banking_indicators, selected_publication_country)

    country_catalog = build_country_catalog(catalog, jordan_corpus)
    selected_country_view = country_catalog[
        country_catalog["country"] == selected_publication_country].copy()

    if selected_publication_country == "Israel":
        render_country_publication_browser(
            selected_country_view, "Israel", "regional_israel_publications")
        return

    if selected_publication_country != "Jordan":
        st.subheader(f"{selected_publication_country} Publications")
        regulator = (
            str(selected_market.get("regulator", ""))
            if not selected_market.empty else "The selected regulator")
        st.info(
            f"{regulator} is mapped for regional comparison, but its "
            "publication feed is not connected yet.")
        return

    st.subheader("Jordan Publications")
    render_catalog_type_shelf(selected_country_view)
    st.caption(
        "Showing connected Central Bank of Jordan publication feeds. Use the "
        "source-specific sections below to search and refresh each feed.")

    st.subheader("Central Bank of Jordan Regulations")
    st.caption(
        "Source: official Central Bank of Jordan regulations listing. "
        "Run `python jordan_cbj_index.py` to refresh the local snapshot.")
    st.link_button(
        "Open CBJ regulations source",
        "https://www.cbj.gov.jo/EN/List/Instructions_")

    if jordan_docs.empty:
        st.info(
            "No Jordan CBJ snapshot found yet. Run `python jordan_cbj_index.py` "
            "from the project folder to create `jordan_cbj_regulations.csv`.")
    else:
        jordan_query = st.text_input(
            "Search Jordan regulations",
            placeholder="capital, consumer protection, Basel, cyber",
            key="jordan_cbj_query")
        jordan_view = jordan_docs.copy()
        if jordan_query.strip():
            needles = [
                term.lower()
                for term in re.split(r"[\s,]+", jordan_query.strip())
                if term.strip()
            ]
            haystack = jordan_view[[
                "title", "category", "regulator", "file_type",
                "connection_status"
            ]].astype(str).agg(" ".join, axis=1).str.lower()
            mask = pd.Series(True, index=jordan_view.index)
            for needle in needles:
                mask &= haystack.str.contains(re.escape(needle), na=False)
            jordan_view = jordan_view[mask]

        st.write(f"{len(jordan_view):,} Jordan records match.")
        display = jordan_view[[
            "title", "category", "size", "file_type", "last_seen", "url"
        ]].copy()
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=420,
            column_config={
                "title": "Publication",
                "category": "Publication type",
                "size": "Size",
                "file_type": "File type",
                "last_seen": "Indexed",
                "url": st.column_config.LinkColumn(
                    "Official link", display_text="Open", width="medium"),
            })
        st.download_button(
            "Download Jordan CBJ index (CSV)",
            jordan_view.to_csv(index=False).encode("utf-8"),
            "jordan_cbj_regulations.csv",
            "text/csv")

    st.subheader("Central Bank of Jordan Financial Stability Reports")
    st.caption(
        "Source: official Central Bank of Jordan Financial Stability Report "
        "listing. This feed refreshes from the live site and is also included "
        "in the Catalog as Jordan PDF records.")
    refresh_col, source_col = st.columns([1, 2])
    with refresh_col:
        if st.button("Refresh reports from CBJ site", width="stretch"):
            try:
                rows = refresh_jordan_financial_stability_reports()
                load_jordan_financial_stability_reports.clear()
                jordan_reports = pd.DataFrame(rows)
                st.success(f"Updated {len(rows):,} report rows from CBJ.")
            except Exception as exc:
                st.error(f"Could not refresh CBJ reports: {exc}")
    with source_col:
        st.link_button(
            "Open CBJ Financial Stability Report source",
            JORDAN_CBJ_FINANCIAL_STABILITY_SOURCE,
            width="stretch")

    if jordan_reports.empty:
        st.info(
            "No Jordan Financial Stability Report snapshot found yet. Use "
            "the refresh button or run "
            "`python jordan_cbj_financial_stability.py`.")
    else:
        report_query = st.text_input(
            "Search Jordan financial stability reports",
            placeholder="2024, stability, report",
            key="jordan_fsr_query")
        report_view = jordan_reports.copy()
        if report_query.strip():
            needles = [
                term.lower()
                for term in re.split(r"[\s,]+", report_query.strip())
                if term.strip()
            ]
            haystack = report_view[[
                "title", "category", "regulator", "file_type",
                "connection_status"
            ]].astype(str).agg(" ".join, axis=1).str.lower()
            mask = pd.Series(True, index=report_view.index)
            for needle in needles:
                mask &= haystack.str.contains(re.escape(needle), na=False)
            report_view = report_view[mask]

        st.write(
            f"{len(report_view):,} Jordan financial stability reports match.")
        report_display = report_view[[
            "title", "category", "size", "file_type", "last_seen", "url"
        ]].copy()
        st.dataframe(
            report_display,
            hide_index=True,
            width="stretch",
            height=360,
            column_config={
                "title": "Publication",
                "category": "Publication type",
                "size": "Size",
                "file_type": "File type",
                "last_seen": "Source updated",
                "url": st.column_config.LinkColumn(
                    "Official PDF", display_text="Open PDF", width="medium"),
            })
        st.download_button(
            "Download Jordan financial stability reports (CSV)",
            report_view.to_csv(index=False).encode("utf-8"),
            "jordan_cbj_financial_stability_reports.csv",
            "text/csv")

    st.subheader("Central Bank of Jordan Foreign Exchange Reserves")
    st.caption(
        "Source: official Central Bank of Jordan Annual Statistical Bulletin "
        "listing. The reserve table is connected as a live XLSX data record "
        "and included in the Catalog under Jordan.")
    reserve_refresh_col, reserve_source_col = st.columns([1, 2])
    with reserve_refresh_col:
        if st.button("Refresh reserves from CBJ site", width="stretch"):
            try:
                rows = refresh_jordan_foreign_exchange_reserves()
                load_jordan_foreign_exchange_reserves.clear()
                jordan_reserves = pd.DataFrame(rows)
                st.success(f"Updated {len(rows):,} reserve rows from CBJ.")
            except Exception as exc:
                st.error(f"Could not refresh CBJ reserves: {exc}")
    with reserve_source_col:
        st.link_button(
            "Open CBJ Annual Statistical Bulletin source",
            JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES_SOURCE,
            width="stretch")

    if jordan_reserves.empty:
        st.info(
            "No Jordan foreign reserves snapshot found yet. Use the refresh "
            "button or run `python jordan_cbj_foreign_exchange_reserves.py`.")
    else:
        reserves_query = st.text_input(
            "Search Jordan foreign reserves",
            placeholder="foreign reserves, central bank, xlsx",
            key="jordan_reserves_query")
        reserves_view = jordan_reserves.copy()
        if reserves_query.strip():
            needles = [
                term.lower()
                for term in re.split(r"[\s,]+", reserves_query.strip())
                if term.strip()
            ]
            haystack = reserves_view[[
                "title", "category", "regulator", "file_type",
                "connection_status"
            ]].astype(str).agg(" ".join, axis=1).str.lower()
            mask = pd.Series(True, index=reserves_view.index)
            for needle in needles:
                mask &= haystack.str.contains(re.escape(needle), na=False)
            reserves_view = reserves_view[mask]

        st.write(f"{len(reserves_view):,} Jordan foreign reserves records match.")
        reserves_display = reserves_view[[
            "title", "category", "size", "file_type", "last_seen", "url"
        ]].copy()
        st.dataframe(
            reserves_display,
            hide_index=True,
            width="stretch",
            height=220,
            column_config={
                "title": "Publication",
                "category": "Publication type",
                "size": "Size",
                "file_type": "File type",
                "last_seen": "Source updated",
                "url": st.column_config.LinkColumn(
                    "Official XLSX", display_text="Open XLSX", width="medium"),
            })
        st.download_button(
            "Download Jordan foreign reserves index (CSV)",
            reserves_view.to_csv(index=False).encode("utf-8"),
            "jordan_cbj_foreign_exchange_reserves.csv",
            "text/csv")

    st.subheader("Central Bank of Jordan FX Rates")
    st.caption(
        "Source: official Central Bank of Jordan Annual Statistical Bulletin "
        "listing. The exchange-rate table is connected as a live XLSX data "
        "record and included in the Compare countries FX mode.")
    fx_refresh_col, fx_source_col = st.columns([1, 2])
    with fx_refresh_col:
        if st.button("Refresh FX rates from CBJ site", width="stretch"):
            try:
                rows = refresh_jordan_fx_rates()
                load_jordan_fx_rates.clear()
                jordan_fx_rates = pd.DataFrame(rows)
                st.success(f"Updated {len(rows):,} FX rate rows from CBJ.")
            except Exception as exc:
                st.error(f"Could not refresh CBJ FX rates: {exc}")
    with fx_source_col:
        st.link_button(
            "Open CBJ Annual Statistical Bulletin source",
            JORDAN_CBJ_FX_RATES_SOURCE,
            width="stretch")

    if jordan_fx_rates.empty:
        st.info(
            "No Jordan FX rates snapshot found yet. Use the refresh button "
            "or run `python jordan_cbj_fx_rates.py`.")
        return

    fx_query = st.text_input(
        "Search Jordan FX rates",
        placeholder="exchange rates, foreign currencies, xlsx",
        key="jordan_fx_rates_query")
    fx_view = jordan_fx_rates.copy()
    if fx_query.strip():
        needles = [
            term.lower()
            for term in re.split(r"[\s,]+", fx_query.strip())
            if term.strip()
        ]
        haystack = fx_view[[
            "title", "category", "regulator", "file_type",
            "connection_status"
        ]].astype(str).agg(" ".join, axis=1).str.lower()
        mask = pd.Series(True, index=fx_view.index)
        for needle in needles:
            mask &= haystack.str.contains(re.escape(needle), na=False)
        fx_view = fx_view[mask]

    st.write(f"{len(fx_view):,} Jordan FX rate records match.")
    fx_display = fx_view[[
        "title", "category", "size", "file_type", "last_seen", "url"
    ]].copy()
    st.dataframe(
        fx_display,
        hide_index=True,
        width="stretch",
        height=220,
        column_config={
            "title": "Publication",
            "category": "Publication type",
            "size": "Size",
            "file_type": "File type",
            "last_seen": "Source updated",
            "url": st.column_config.LinkColumn(
                "Official XLSX", display_text="Open XLSX", width="medium"),
        })
    st.download_button(
        "Download Jordan FX rates index (CSV)",
        fx_view.to_csv(index=False).encode("utf-8"),
        "jordan_cbj_fx_rates.csv",
        "text/csv")


def render_reader_section(
        catalog, directives, jordan_docs=None, israel_fx_docs=None,
        overnight_rates=None, overnight_fx_context=None):
    render_section_heading("Search Inside All PDFs")
    pdf_catalog = get_pdf_catalog(catalog, directives)
    country_catalog = build_country_catalog(catalog, jordan_docs)
    directive_comparison_catalog = build_directive_comparison_catalog(
        directives, jordan_docs)
    fx_comparison_catalog = build_fx_comparison_catalog(
        catalog, jordan_docs, israel_fx_docs)
    reader_docs = load_search_docs(search_corpus_signature())
    indexed_urls = (
        set(reader_docs["doc_url"]) if not reader_docs.empty else set())
    remaining = max(0, len(pdf_catalog) - len(indexed_urls))
    running_pid = pdf_index_process()

    with st.expander("Index status", expanded=False):
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("PDF files", f"{len(pdf_catalog):,}")
        i2.metric("Full-text indexed", f"{len(indexed_urls):,}")
        i3.metric("Remaining", f"{remaining:,}")
        i4.metric("Indexer", "Running" if running_pid else "Idle")

        index_col, stop_col = st.columns([1, 1])
        with index_col:
            if st.button(
                    "Index remaining PDFs",
                    type="primary",
                    disabled=running_pid is not None or remaining == 0,
                    width="stretch"):
                pid = start_pdf_text_index()
                st.success(f"Full-text indexing started. PID {pid}.")
        with stop_col:
            if st.button(
                    "Stop indexing",
                    disabled=running_pid is None,
                    width="stretch"):
                if stop_pdf_text_index():
                    st.warning("Full-text indexing stop requested.")
                else:
                    st.info("No indexing process is running.")

        log_tail = read_index_log_tail()
        if log_tail:
            st.text("Index log")
            st.text(log_tail)

    reader_mode = st.segmented_control(
        "Reader mode",
        ["Single PDF", "Compare countries"],
        default="Single PDF",
        key="reader_mode",
        width="content")
    active_comparison = None
    active_secondary_row = None
    active_comparison_topic = ""
    comparison_primary_urls = set()
    if reader_mode != "Compare countries" and "reader_comparison" in st.session_state:
        del st.session_state.reader_comparison
    if reader_mode == "Compare countries":
        comparison_topic = st.segmented_control(
            "Comparison topic",
            ["Directives / regulations", "FX rates / reserves"],
            default="Directives / regulations",
            key="comparison_topic",
            width="content")
        active_comparison_topic = comparison_topic or "Directives / regulations"
        compare_fx = active_comparison_topic == "FX rates / reserves"
        comparison_catalog = (
            fx_comparison_catalog if compare_fx else directive_comparison_catalog)

        st.markdown(
            "**Two-country FX rates comparison**"
            if compare_fx else "**Two-country legal comparison**")
        if compare_fx:
            st.caption(
                "Compare exchange-rate and foreign-reserve data sources across "
                "connected central banks, including BOI exchange-rate pages and "
                "CBJ XLSX data files.")
        else:
            st.caption(
                "Compare directive and regulatory publications: Bank of Israel "
                "Proper Conduct directives and connected regional instructions.")
        countries = ordered_countries(
            comparison_catalog["country"].unique())
        if not countries:
            st.info(
                "No FX sources are available for comparison."
                if compare_fx
                else "No directive publications are available for comparison.")
            countries = ["Israel", "Jordan"]
        default_a = countries.index("Israel") if "Israel" in countries else 0
        default_b = (
            countries.index("Jordan")
            if "Jordan" in countries
            else min(1, len(countries) - 1))
        country_a_col, country_b_col = st.columns(2)
        with country_a_col:
            compare_country_a = st.selectbox(
                "Country A",
                countries,
                index=default_a,
                key="compare_country_a")
        with country_b_col:
            compare_country_b = st.selectbox(
                "Country B",
                countries,
                index=default_b,
                key="compare_country_b")

        primary_options = comparison_catalog[
            comparison_catalog["country"] == compare_country_a].copy()
        secondary_options = comparison_catalog[
            comparison_catalog["country"] == compare_country_b].copy()
        if not compare_fx:
            primary_options = primary_options[
                primary_options["doc_type"].str.lower() == "pdf"].copy()
        if compare_fx:
            primary_options = order_fx_comparison_options(primary_options)
            secondary_options = order_fx_comparison_options(secondary_options)
        else:
            primary_options = order_catalog_by_publication_type(primary_options)
            secondary_options = order_catalog_by_publication_type(secondary_options)
        comparison_primary_urls = set(
            primary_options[
                primary_options["doc_type"].str.lower() == "pdf"]["doc_url"])

        if primary_options.empty or secondary_options.empty:
            st.info(
                "Comparison needs FX data sources for both countries."
                if compare_fx
                else "Comparison needs a directive PDF for Country A and at "
                "least one directive or regulatory publication for Country B.")
        else:
            pub_a_col, pub_b_col = st.columns(2)
            with pub_a_col:
                primary_index = st.selectbox(
                    "Country A FX source"
                    if compare_fx else "Country A directive PDF",
                    primary_options.index.tolist(),
                    format_func=lambda idx: format_publication_option(
                        primary_options.loc[idx]),
                    key=("compare_primary_fx"
                         if compare_fx else "compare_primary_publication"))
            with pub_b_col:
                secondary_index = st.selectbox(
                    "Country B FX source"
                    if compare_fx else "Country B directive / regulation",
                    secondary_options.index.tolist(),
                    format_func=lambda idx: format_publication_option(
                        secondary_options.loc[idx]),
                    key=("compare_secondary_fx"
                         if compare_fx else "compare_secondary_publication"))

            primary_row = primary_options.loc[primary_index]
            secondary_row = secondary_options.loc[secondary_index]
            active_secondary_row = secondary_row
            active_comparison = (
                build_fx_comparison(primary_row, secondary_row)
                if compare_fx
                else build_legal_comparison(primary_row, secondary_row, reader_docs))
            render_comparison_preview(active_comparison)
            primary_url = str(primary_row.get("doc_url", "") or "")
            secondary_url = str(secondary_row.get("doc_url", "") or "")
            primary_is_pdf = str(
                primary_row.get("doc_type", "") or "").lower() == "pdf"
            link_a, link_b = st.columns(2)
            with link_a:
                primary_link = source_link_for_row(primary_row)
                if primary_link:
                    st.link_button(
                        "Open Country A source",
                        primary_link,
                        width="stretch")
            with link_b:
                secondary_link = source_link_for_row(secondary_row)
                if secondary_link:
                    st.link_button(
                        "Open Country B source",
                        secondary_link,
                        width="stretch")

            if compare_fx:
                render_side_by_side_data_readers(primary_row, secondary_row)
                render_overnight_rate_analysis(
                    overnight_rates, overnight_fx_context)

            if st.session_state.get("reader_url") == primary_url:
                st.session_state.reader_comparison = active_comparison
            if primary_is_pdf:
                if st.button(
                        "Open comparison reader",
                        type="primary",
                        key="open_comparison_reader"):
                    st.session_state.reader_url = primary_url
                    st.session_state.reader_title = publication_row_title(primary_row)
                    st.session_state.reader_initial_query = ""
                    st.session_state.reader_comparison = active_comparison
            elif compare_fx:
                st.info(
                    "The selected Country A FX source is not a PDF, so it "
                    "opens in the data reader or via its official link rather "
                    "than the PDF reader.")

    reader_query = st.text_input(
        "Search inside indexed PDF text",
        "",
        placeholder='stock, inflation, "monetary policy"',
        key="reader_query")
    match_mode = st.segmented_control(
        "Match type",
        ["Exact match", "Broad match"],
        default="Broad match",
        key="reader_match_type",
        width="content")
    reader_view = build_full_text_pdf_results(
        pdf_catalog, reader_docs, reader_query, match_mode or "Broad match")
    if reader_mode == "Compare countries" and comparison_primary_urls:
        reader_view = reader_view[
            reader_view["doc_url"].isin(comparison_primary_urls)].copy()
    if not reader_view.empty and "publication_type" in reader_view.columns:
        reader_publication_types = sorted(
            s for s in reader_view["publication_type"].unique() if s)
        pick_reader_publication_types = st.multiselect(
            "Publication type",
            reader_publication_types,
            default=[],
            key="reader_publication_type_filter")
        if pick_reader_publication_types:
            reader_view = reader_view[
                reader_view["publication_type"].isin(
                    pick_reader_publication_types)]

    if reader_query.strip():
        total_hits = (
            int(reader_view["full_text_matches"].sum())
            if "full_text_matches" in reader_view.columns else 0)
        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric("Matching PDFs", f"{len(reader_view):,}")
        metric_2.metric("Full-text hits", f"{total_hits:,}")
        metric_3.metric("Indexed PDFs searched", f"{len(reader_docs):,}")
        st.caption(
            f"Search is looking inside the text of {len(reader_docs):,} "
            f"indexed PDFs. Index the remaining {remaining:,} PDFs to "
            f"cover the full {len(pdf_catalog):,}-PDF catalog.")
        if not reader_view.empty:
            preview = reader_view[[
                "source_title", "publication_type", "pages", "lastmod",
                "full_text_matches", "matched_terms", "search_snippet",
                "doc_url"
            ]].copy()
            table_state = st.dataframe(
                preview,
                hide_index=True,
                width="stretch",
                height=420,
                key="reader_results_table",
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "source_title": "Publication",
                    "publication_type": st.column_config.TextColumn(
                        "Publication type", width="medium"),
                    "pages": st.column_config.NumberColumn(
                        "Pages", width="small"),
                    "lastmod": st.column_config.TextColumn(
                        "Updated", width="medium"),
                    "full_text_matches": st.column_config.NumberColumn(
                        "Text hits", width="small"),
                    "matched_terms": "Terms",
                    "search_snippet": "Snippet",
                    "doc_url": st.column_config.LinkColumn(
                        "Link text",
                        display_text="Link text",
                        width="medium"),
                })
            selected_rows = table_state.selection.rows
            if selected_rows and selected_rows[0] < len(preview):
                clicked_url = preview.iloc[selected_rows[0]]["doc_url"]
                clicked_matches = reader_view[
                    reader_view["doc_url"] == clicked_url]
                if not clicked_matches.empty:
                    clicked_row = clicked_matches.iloc[0]
                    clicked_title = (
                        clicked_row.get("source_title", "")
                        or clicked_row.get("doc_title", "")
                        or clicked_url.rsplit("/", 1)[-1])
                    st.session_state.reader_url = clicked_url
                    st.session_state.reader_title = clicked_title
                    st.session_state.reader_initial_query = reader_query.strip()
            st.download_button(
                "Download search results (CSV)",
                preview.to_csv(index=False).encode("utf-8"),
                "boi_publication_search_results.csv",
                "text/csv")

    def reader_label(index):
        row = reader_view.loc[index]
        title = row["source_title"] or row["doc_title"] or row["doc_url"].rsplit("/", 1)[-1]
        date = str(row.get("lastmod", ""))[:10]
        hits = int(row.get("full_text_matches", 0) or 0)
        hit_label = f" ({hits:,} text hits)" if hits else ""
        return f"{title}{hit_label} - {date}" if date else f"{title}{hit_label}"

    if reader_view.empty:
        st.info("No PDF text matches.")
        return

    pick_col, action_col = st.columns([4, 1])
    with pick_col:
        selected_pdf = st.selectbox(
            "Open a matching PDF",
            reader_view.index.tolist(),
            format_func=reader_label,
            key="reader_selected_pdf")
    selected_row = reader_view.loc[selected_pdf]
    selected_title = selected_row["source_title"] or selected_row["doc_title"]
    selected_url = selected_row["doc_url"]

    with action_col:
        open_reader = st.button("Open reader", type="primary", width="stretch")

    if open_reader:
        st.session_state.reader_url = selected_url
        st.session_state.reader_title = selected_title
        st.session_state.reader_initial_query = reader_query.strip()
        if active_comparison:
            selected_primary = selected_row.copy()
            selected_primary["country"] = selected_primary.get("country", "Israel")
            selected_primary["regulator"] = selected_primary.get(
                "regulator", "Bank of Israel")
            st.session_state.reader_comparison = (
                build_fx_comparison(selected_primary, active_secondary_row)
                if active_comparison_topic == "FX rates / reserves"
                else build_legal_comparison(
                    selected_primary,
                    active_secondary_row,
                    reader_docs))
        elif "reader_comparison" in st.session_state:
            del st.session_state.reader_comparison

    if "reader_url" in st.session_state:
        model, pdf_bytes = get_reader_model(
            st.session_state.reader_url,
            st.session_state.reader_title)

        m1, m2, m3 = st.columns(3)
        m1.metric("Pages", f"{model['pageCount']:,}")
        m2.metric("PDF size", f"{len(pdf_bytes) / 1024 / 1024:.1f} MB")
        words = sum(len(page["words"]) for page in model["pages"])
        m3.metric("Indexed words", f"{words:,}")

        st.download_button(
            "Download PDF",
            pdf_bytes,
            slug_for(st.session_state.reader_url) + ".pdf",
            "application/pdf")
        viewer_model = dict(model)
        viewer_model["initialQuery"] = st.session_state.get(
            "reader_initial_query", "")
        if st.session_state.get("reader_comparison"):
            viewer_model["comparison"] = st.session_state.reader_comparison
        render_pdf_viewer(viewer_model)


apply_library_styles()

if not os.path.exists(LINKS):
    st.warning(
        "No catalog yet. Run **`python3 boi_pdf_extractor.py`** first to build "
        "`boi_pdf_links.csv`, then reload this page.")
    st.stop()

catalog = load_catalog(file_mtime(LINKS))
directives = load_proper_conduct_directives()
ensure_jordan_financial_stability_reports()
ensure_jordan_foreign_exchange_reserves()
ensure_jordan_fx_rates()
ensure_israel_boi_fx_reserves()
ensure_overnight_rate_analysis()
ensure_banking_sector_indicators()
jordan_regulations = load_jordan_cbj_regulations(
    file_mtime(JORDAN_CBJ_REGULATIONS))
jordan_reports = load_jordan_financial_stability_reports(
    file_mtime(JORDAN_CBJ_FINANCIAL_STABILITY_REPORTS))
jordan_reserves = load_jordan_foreign_exchange_reserves(
    file_mtime(JORDAN_CBJ_FOREIGN_EXCHANGE_RESERVES))
jordan_fx_rates = load_jordan_fx_rates(file_mtime(JORDAN_CBJ_FX_RATES))
israel_fx_reserves = load_israel_boi_fx_reserves(
    file_mtime(ISRAEL_BOI_FX_RESERVES_INDEX))
israel_fx_reserve_rows = load_israel_boi_fx_reserves_data(
    file_mtime(ISRAEL_BOI_FX_RESERVES_DATA))
overnight_rates = load_overnight_rate_comparison(
    file_mtime(OVERNIGHT_RATE_COMPARISON))
overnight_fx_context = load_overnight_fx_context(
    file_mtime(OVERNIGHT_FX_CONTEXT))
banking_indicators = load_banking_sector_indicators(
    file_mtime(BANKING_SECTOR_INDICATORS))
jordan_docs = combine_jordan_docs(
    jordan_regulations, jordan_reports, jordan_reserves, jordan_fx_rates)
section = render_library_shell(catalog, directives, jordan_docs)

if section == "Catalog":
    render_catalog_section(catalog, jordan_docs)
elif section == "Reader":
    render_reader_section(
        catalog, directives, jordan_docs, israel_fx_reserves,
        overnight_rates, overnight_fx_context)
elif section == "Risk Compare":
    render_risk_compare_section()
else:
    render_regional_map_section(
        catalog, directives, jordan_regulations, jordan_reports,
        jordan_reserves, jordan_fx_rates, overnight_rates,
        israel_fx_reserve_rows, banking_indicators)
