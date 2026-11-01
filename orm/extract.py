"""Get each document's text and split it into provisions.

Text sources, in order of preference:
  1. a manual drop-in at orm_texts/manual/<document_id>.pdf or .txt
     (for regulators whose site blocks scripted downloads -- e.g. save a
     CBJ PDF from the browser and drop it in)
  2. the cached extraction at orm_texts/<slug>.txt.gz
  3. text the BOI explorer already extracted (boi_texts/)
  4. a fresh download of pdf_url
"""
from __future__ import annotations

import gzip
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_DIR = os.path.join(HERE, "orm_texts")
MANUAL_DIR = os.path.join(TEXT_DIR, "manual")
BOI_TEXT_DIR = os.path.join(HERE, "boi_texts")

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")}


def slug_for(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (p.path or "").strip("/")).strip("-")
    return (base or "doc")[:120]


def pdf_bytes_to_text(data: bytes) -> tuple[int, str]:
    if not data[:5] == b"%PDF-":
        raise ValueError("not a PDF response")
    import fitz  # pymupdf; imported lazily so the app runs without it
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return doc.page_count, "\n".join(p.get_text("text") for p in doc)
    finally:
        doc.close()


def _read_gz(path: str) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return f.read()


def _write_gz(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def manual_path(document_id: str) -> str | None:
    for ext in (".pdf", ".txt"):
        path = os.path.join(MANUAL_DIR, document_id + ext)
        if os.path.exists(path):
            return path
    return None


def get_text(document_id: str, pdf_url: str | None, *, fetch: bool = True,
             timeout: int = 60) -> tuple[str, int | None, str, str]:
    """Return (text, pages, text_path, origin). Raises if unavailable."""
    manual = manual_path(document_id)
    if manual:
        if manual.endswith(".txt"):
            with open(manual, encoding="utf-8") as f:
                return f.read(), None, os.path.relpath(manual, HERE), "manual"
        with open(manual, "rb") as f:
            pages, text = pdf_bytes_to_text(f.read())
        return text, pages, os.path.relpath(manual, HERE), "manual"

    if not pdf_url:
        raise LookupError("no PDF link in the source index")

    slug = slug_for(pdf_url)
    cached = os.path.join(TEXT_DIR, slug + ".txt.gz")
    if os.path.exists(cached):
        return _read_gz(cached), None, os.path.relpath(cached, HERE), "cache"
    boi_cached = os.path.join(BOI_TEXT_DIR, slug + ".txt.gz")
    if os.path.exists(boi_cached):
        return _read_gz(boi_cached), None, os.path.relpath(boi_cached, HERE), "cache"

    if not fetch:
        raise LookupError("text not cached (run with fetching enabled)")
    r = requests.get(pdf_url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    pages, text = pdf_bytes_to_text(r.content)
    _write_gz(cached, text)
    time.sleep(0.5)  # be polite to regulator sites
    return text, pages, os.path.relpath(cached, HERE), "download"


# --- provision splitting ---------------------------------------------------

_HEADING = re.compile(
    r"^\s*(?:"
    r"(?P<num>\d{1,3}(?:\.\d{1,3}){0,3})\.?\s+(?=[A-Za-z֐-ۿ(\"'])"
    r"|(?P<art>(?:Article|Section|Chapter|Part)\s*\(?\s*[\dIVXLC]+\s*\)?)"
    r")")
_PAGE_FURNITURE = re.compile(
    r"^\s*(page \d+( of \d+)?|\d{1,3}|-\s*\d+\s*-|\d+\s*/\s*\d+)\s*$", re.I)


def normalize(text: str) -> str:
    text = text.replace("­", "").replace("\r", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # de-hyphenate
    return text


def split_provisions(text: str, min_chars: int = 160,
                     max_chars: int = 3000) -> list[tuple[str, str]]:
    """Split regulation text into (ref, text) provisions.

    A new provision starts at a numbered paragraph ("12.", "4.2.1") or an
    Article/Section/Chapter heading. Short fragments are merged forward so a
    provision is always a readable unit; very long blocks are cut at sentence
    boundaries.
    """
    chunks: list[list] = []          # [ref, [lines]]
    current_ref, current_lines = "", []

    def flush():
        body = " ".join(" ".join(current_lines).split())
        if body:
            chunks.append([current_ref, body])

    for raw in normalize(text).split("\n"):
        line = raw.strip()
        if not line or _PAGE_FURNITURE.match(line):
            continue
        m = _HEADING.match(line)
        if m and len(" ".join(current_lines)) >= min_chars:
            flush()
            current_ref = (m.group("num") or m.group("art") or "").strip()
            current_lines = [line]
        else:
            if m and not current_ref:   # short preamble absorbs the first heading
                current_ref = (m.group("num") or m.group("art") or "").strip()
            current_lines.append(line)
    flush()

    out: list[tuple[str, str]] = []
    for ref, body in chunks:
        label = _label(ref)
        if len(body) <= max_chars:
            out.append((label, body))
            continue
        part, n = "", 1
        for sentence in re.split(r"(?<=[.;:])\s+", body):
            if part and len(part) + len(sentence) > max_chars:
                out.append((f"{label} (part {n})" if label else f"part {n}", part))
                part, n = "", n + 1
            part = f"{part} {sentence}".strip()
        if part:
            out.append((f"{label} (part {n})" if label else f"part {n}", part))
    return out


def _label(ref: str) -> str:
    if not ref:
        return ""
    if ref[0].isdigit():
        return f"§{ref}"
    return re.sub(r"\s+", " ", ref.replace("(", "").replace(")", "")).strip()
