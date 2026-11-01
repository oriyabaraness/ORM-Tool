"""Source connectors: one per regulator, all emitting the same document dict.

A connector reads whatever its crawler produced (the existing CSV indexes in
this repo) and normalizes it to:

    id, jurisdiction, regulator, ref, title, subject, url, pdf_url,
    published, lastmod, source

Adding a jurisdiction means adding a connector here and registering it in
CONNECTORS -- nothing downstream changes.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Iterable

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOI_PROPER_CONDUCT = os.path.join(HERE, "boi_proper_conduct_directives.csv")
CBJ_REGULATIONS = os.path.join(HERE, "jordan_cbj_regulations.csv")


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _slug(text: str, n: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-")


def _iso_date(value: str) -> str:
    """BOI publishes dd/mm/yyyy; normalize to yyyy-mm-dd when possible."""
    value = _clean(value)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return value[:10]


def boi_proper_conduct(path: str = BOI_PROPER_CONDUCT) -> Iterable[dict]:
    """Bank of Israel Proper Conduct of Banking Business Directives."""
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str)
    df = df[df.get("status", "ok").fillna("ok").str.lower() == "ok"]
    seen: set[str] = set()
    docs = []
    for _, row in df.iterrows():
        number = _clean(row.get("directive_number"))
        title = _clean(row.get("page_title")) or _clean(row.get("title"))
        pdf_url = _clean(row.get("file_url"))
        key = number or pdf_url or title
        if not title or key in seen:
            continue
        seen.add(key)
        docs.append({
            "id": f"IL-BOI-PC-{number or _slug(title)}",
            "jurisdiction": "IL",
            "regulator": "Bank of Israel",
            "ref": f"Directive {number}" if number else "",
            "title": title,
            "subject": _clean(row.get("subject")) or _clean(row.get("area")),
            "url": _clean(row.get("url")),
            "pdf_url": pdf_url or None,
            "published": _iso_date(row.get("publication_date")),
            "lastmod": _clean(row.get("lastmod"))[:10],
            "source": "boi_proper_conduct_directives.csv",
        })
    return docs


_CBJ_NUMBER = re.compile(r"No\.?\s*\(?\s*(\d+\s*[/-]\s*\d{4}|\d+)\s*\)?", re.I)
_CBJ_PAREN_NUMBER = re.compile(r"\((\d+\s*-\s*\d{4})\)")


def _cbj_ref(title: str) -> str:
    m = _CBJ_NUMBER.search(title) or _CBJ_PAREN_NUMBER.search(title)
    return f"No. {m.group(1).replace(' ', '')}" if m else ""


def _is_pdf_url(url: str) -> bool:
    low = url.lower()
    return low.endswith(".pdf") or "root_storage" in low


def cbj_regulations(path: str = CBJ_REGULATIONS) -> Iterable[dict]:
    """Central Bank of Jordan instructions / regulations index."""
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str)
    docs = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        title = re.sub(r"\s+PDF$", "", _clean(row.get("title")))
        if not title:
            continue
        doc_id = f"JO-CBJ-{_slug(title)}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        url = _clean(row.get("url"))
        docs.append({
            "id": doc_id,
            "jurisdiction": "JO",
            "regulator": "Central Bank of Jordan",
            "ref": _cbj_ref(title),
            "title": title,
            "subject": _clean(row.get("category")),
            "url": _clean(row.get("source_url")) or url,
            "pdf_url": url if _is_pdf_url(url) else None,
            "published": "",
            "lastmod": _clean(row.get("last_seen"))[:10],
            "source": "jordan_cbj_regulations.csv",
        })
    return docs


CONNECTORS: dict[str, tuple[str, Callable[[], Iterable[dict]]]] = {
    "boi_proper_conduct": ("IL", boi_proper_conduct),
    "cbj_regulations": ("JO", cbj_regulations),
}


def all_documents(jurisdictions: set[str] | None = None) -> list[dict]:
    docs: list[dict] = []
    for _name, (code, fn) in CONNECTORS.items():
        if jurisdictions and code not in jurisdictions:
            continue
        docs.extend(fn())
    return docs
