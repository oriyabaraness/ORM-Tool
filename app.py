"""
Bank of Israel Publications Explorer -- a Streamlit UI over the crawl/extract
pipeline.

  Library layout: browse the catalog, Proper Conduct directives, and the
                  PDF reader from a Sefaria-style index page.
Run with:  streamlit run app.py   (from inside the .venv)

Text extraction reuses boi_pdf_text.extract_one, and results are cached per URL.
"""
import gzip
import os
import re

import pandas as pd
import streamlit as st

from boi_pdf_viewer import build_pdf_viewer_model, download_pdf, render_pdf_viewer
from boi_pdf_text import extract_one, slug_for

HERE = os.path.dirname(os.path.abspath(__file__))
LINKS = os.path.join(HERE, "boi_pdf_links.csv")
BANKING_SUPERVISION = os.path.join(HERE, "boi_banking_supervision_index.csv")
PUBLICATIONS_INDEX = os.path.join(HERE, "boi_publications_index.csv")
PROPER_CONDUCT_DIRECTIVES = os.path.join(
    HERE, "boi_proper_conduct_directives.csv")
MANIFEST = os.path.join(HERE, "boi_pdf_text_manifest.csv")
TEXT_DIR = os.path.join(HERE, "boi_texts")

st.set_page_config(page_title="BOI Publications Explorer",
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
def load_text_manifest(mtime):
    if not os.path.exists(MANIFEST):
        return pd.DataFrame()
    df = pd.read_csv(MANIFEST)
    for c in ("doc_url", "doc_title", "source_title", "section", "lastmod",
              "txt_path", "status"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df


@st.cache_data(show_spinner=False)
def load_search_docs(signature):
    manifest = load_text_manifest(file_mtime(MANIFEST))
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
    model = build_pdf_viewer_model(pdf_bytes, title=title, source_url=url)
    return model, pdf_bytes


def file_mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


def search_corpus_signature():
    if not os.path.isdir(TEXT_DIR):
        return (file_mtime(MANIFEST),)
    files = []
    for name in sorted(os.listdir(TEXT_DIR)):
        if not name.endswith(".txt.gz"):
            continue
        path = os.path.join(TEXT_DIR, name)
        files.append((name, os.path.getmtime(path), os.path.getsize(path)))
    return (file_mtime(MANIFEST), tuple(files))


def parse_terms(query):
    terms = []
    for quoted, bare in re.findall(r'"([^"]+)"|(\S+)', query):
        term = (quoted or bare).strip().strip(",;:").lower()
        if term and term not in terms:
            terms.append(term)
    return terms


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
    require_all = match_mode == "All terms"
    for _, row in docs.iterrows():
        text = row["_text"]
        lowered = text.lower()
        counts = {term: lowered.count(term) for term in terms}
        matched = {term: count for term, count in counts.items() if count}
        if require_all and len(matched) != len(terms):
            continue
        if not require_all and not matched:
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
        full_text_results = search_full_text(docs, terms, "Any term", limit)

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


def filter_proper_conduct_directives(directives, query):
    query = query.strip()
    if not query:
        return directives

    search_cols = [
        "directive_number", "circular_number", "title_display",
        "title", "page_title", "publication_date", "subject",
        "subject_display", "area", "url", "file_url",
    ]
    hay = directives[search_cols].fillna("").agg(" ".join, axis=1).str.lower()
    mask = pd.Series(True, index=directives.index)
    for term in parse_terms(query):
        term = term.lower()
        if re.fullmatch(r"\d{3,4}[a-z]?", term):
            directive_numbers = directives["directive_number"].str.lower()
            circular_numbers = directives["circular_number"].str.lower()
            if re.fullmatch(r"\d{3,4}", term):
                mask &= (
                    directive_numbers.str.startswith(term)
                    | circular_numbers.eq(term))
            else:
                mask &= (
                    directive_numbers.eq(term)
                    | circular_numbers.eq(term))
        else:
            mask &= hay.str.contains(term, regex=False)
    return directives[mask]


def apply_library_styles():
    st.markdown(
        """
        <style>
        :root {
            --boi-ink: #202124;
            --boi-muted: #5f6368;
            --boi-line: #d8d2c6;
            --boi-accent: #a34f36;
            --boi-link: #1f5f73;
            --boi-bg-soft: #f7f4ef;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 2.1rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            display: none;
        }

        h1, h2, h3, p, div, span, label {
            letter-spacing: 0;
        }

        .boi-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.5rem;
            border-bottom: 1px solid var(--boi-line);
            padding-bottom: 0.9rem;
            margin-bottom: 1.85rem;
        }

        .boi-brand {
            color: var(--boi-ink);
            font-size: 1.18rem;
            font-weight: 650;
            line-height: 1.2;
        }

        .boi-nav {
            display: flex;
            align-items: center;
            gap: 1.1rem;
            color: var(--boi-muted);
            font-size: 0.96rem;
            white-space: nowrap;
        }

        .boi-nav span:first-child {
            color: var(--boi-accent);
            font-weight: 650;
        }

        .boi-library-head {
            display: grid;
            grid-template-columns: minmax(0, 1.8fr) minmax(280px, 0.9fr);
            gap: 3.6rem;
            align-items: start;
            margin-bottom: 1.25rem;
        }

        .boi-kicker {
            color: var(--boi-muted);
            font-size: 0.9rem;
            font-weight: 650;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .boi-page-title {
            color: var(--boi-ink);
            font-size: clamp(2.2rem, 5vw, 4.4rem);
            font-weight: 500;
            line-height: 1.03;
            margin: 0 0 1.35rem;
        }

        .boi-language-toggle {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            border: 1px solid var(--boi-line);
            border-radius: 999px;
            padding: 0.28rem 0.65rem;
            color: var(--boi-muted);
            font-size: 0.92rem;
        }

        .boi-language-toggle strong {
            color: var(--boi-ink);
            font-weight: 650;
        }

        .boi-shelf {
            border-top: 1px solid var(--boi-line);
            margin-top: 1.2rem;
        }

        .boi-shelf-item {
            display: grid;
            grid-template-columns: minmax(180px, 0.8fr) minmax(0, 1.35fr) auto;
            gap: 1.4rem;
            align-items: start;
            border-bottom: 1px solid var(--boi-line);
            padding: 1.15rem 0;
        }

        .boi-shelf-title {
            color: var(--boi-link);
            font-size: 1.45rem;
            font-weight: 500;
            line-height: 1.15;
        }

        .boi-shelf-copy {
            color: var(--boi-muted);
            font-size: 0.98rem;
            line-height: 1.52;
        }

        .boi-shelf-count {
            color: var(--boi-ink);
            font-size: 0.92rem;
            font-weight: 650;
            white-space: nowrap;
        }

        .boi-info-panel {
            border-top: 1px solid var(--boi-line);
            border-bottom: 1px solid var(--boi-line);
            padding: 1rem 0 1.15rem;
        }

        .boi-info-panel + .boi-info-panel {
            margin-top: 1.4rem;
        }

        .boi-panel-title {
            color: var(--boi-ink);
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 0.45rem;
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
            font-size: 1.75rem;
            font-weight: 550;
            margin: 0 0 0.6rem;
        }

        div[data-testid="stSegmentedControl"] {
            margin: 0.75rem 0 0.2rem;
        }

        div[data-testid="stMetric"] {
            background: var(--boi-bg-soft);
            border: 1px solid #e7e1d7;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
        }

        @media (max-width: 820px) {
            .boi-topbar,
            .boi-library-head,
            .boi-shelf-item {
                display: block;
            }

            .boi-nav {
                margin-top: 0.8rem;
                overflow-x: auto;
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


def render_library_shell(catalog, directives):
    pdf_count = (
        int(catalog["doc_type"].str.lower().eq("pdf").sum())
        if "doc_type" in catalog.columns else 0)
    numbered = (
        int(directives["directive_number"].str.len().gt(0).sum())
        if not directives.empty else 0)
    latest = directives["lastmod"].max()[:10] if not directives.empty else "n/a"
    manifest = load_text_manifest(file_mtime(MANIFEST))
    indexed_docs = 0
    if not manifest.empty:
        ok = manifest[manifest["status"].astype(str).str.lower() == "ok"]
        indexed_docs = len(ok.drop_duplicates(subset=["doc_url"]))

    st.markdown(
        f"""
        <div class="boi-topbar">
            <div class="boi-brand">Bank of Israel Publications Explorer</div>
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
                            metadata, source pages, and extractable documents.
                        </div>
                        <div class="boi-shelf-count">{len(catalog):,} docs</div>
                    </div>
                    <div class="boi-shelf-item">
                        <div class="boi-shelf-title">
                            Proper Conduct of Banking Business Directives
                        </div>
                        <div class="boi-shelf-copy">
                            Directive numbers, circular numbers, publication
                            dates, English subjects, PDF previews, and source pages.
                        </div>
                        <div class="boi-shelf-count">{numbered:,} numbered</div>
                    </div>
                    <div class="boi-shelf-item">
                        <div class="boi-shelf-title">Reader</div>
                        <div class="boi-shelf-copy">
                            Searchable PDFs with extracted text, highlighted
                            matches, page navigation, and downloadable sources.
                        </div>
                        <div class="boi-shelf-count">{pdf_count:,} PDFs</div>
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
        "Proper Conduct of Banking Business Directives",
        "Reader",
    ]
    selected = st.segmented_control(
        "Library section",
        sections,
        default="Proper Conduct of Banking Business Directives",
        key="library_section",
        label_visibility="collapsed",
        width="stretch")
    st.markdown('<div class="boi-section-rule"></div>', unsafe_allow_html=True)
    return selected or "Proper Conduct of Banking Business Directives"


def render_section_heading(title):
    st.markdown(
        f'<h2 class="boi-section-title">{title}</h2>',
        unsafe_allow_html=True)


def render_catalog_section(catalog):
    render_section_heading("Catalog")
    query = st.text_input(
        "Search title / URL",
        "",
        placeholder="annual report, inflation, monetary policy",
        key="catalog_query")

    filter_1, filter_2, filter_3 = st.columns(3)
    sections = sorted(s for s in catalog["section"].unique() if s)
    types = sorted(t for t in catalog["doc_type"].unique() if t)
    only_dated = catalog[catalog["lastmod"] != ""]
    years = (
        sorted({d[:4] for d in only_dated["lastmod"] if len(d) >= 4})
        if not only_dated.empty else [])
    with filter_1:
        pick_sections = st.multiselect("Section", sections, default=[])
    with filter_2:
        pick_types = st.multiselect("File type", types, default=[])
    with filter_3:
        pick_years = st.multiselect("Year", years, default=[])

    view = catalog
    if query:
        q = query.lower()
        hay = (view["doc_title"] + " " + view["source_title"] + " "
               + view["doc_url"]).str.lower()
        view = view[hay.str.contains(q, regex=False)]
    if pick_sections:
        view = view[view["section"].isin(pick_sections)]
    if pick_types:
        view = view[view["doc_type"].isin(pick_types)]
    if pick_years:
        view = view[view["lastmod"].str[:4].isin(pick_years)]

    st.markdown(f"**{len(view):,}** documents match.")

    display = view[["source_title", "doc_title", "doc_type", "lastmod",
                    "doc_url"]].copy()
    display.insert(0, "select", False)
    edited = st.data_editor(
        display, hide_index=True, width="stretch", height=420,
        column_config={
            "select": st.column_config.CheckboxColumn("✓", width="small"),
            "source_title": "Publication",
            "doc_title": "Link text",
            "doc_type": st.column_config.TextColumn("Type", width="small"),
            "lastmod": st.column_config.TextColumn("Updated", width="medium"),
            "doc_url": st.column_config.LinkColumn("URL"),
        },
        disabled=["source_title", "doc_title", "doc_type", "lastmod", "doc_url"],
        key="catalog_editor")

    chosen = edited[edited["select"]]["doc_url"].tolist()
    c1, c2 = st.columns([1, 3])
    with c1:
        go = st.button(f"Extract text ({len(chosen)})",
                       type="primary", disabled=not chosen)
    with c2:
        st.download_button("Download filtered catalog (CSV)",
                           view.to_csv(index=False).encode("utf-8"),
                           "boi_filtered_catalog.csv", "text/csv")

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


def render_proper_conduct_section(directives):
    render_section_heading("Proper Conduct of Banking Business Directives")

    d1, d2, d3 = st.columns(3)
    d1.metric("Directives", f"{len(directives):,}")
    numbered = (
        int(directives["directive_number"].str.len().gt(0).sum())
        if not directives.empty else 0)
    d2.metric("Numbered", f"{numbered:,}")
    latest = directives["lastmod"].max()[:10] if not directives.empty else ""
    d3.metric("Latest update", latest or "n/a")

    if directives.empty:
        st.info("No Proper Conduct of Banking Business Directives were found.")
        return

    directive_query = st.text_input(
        "Search directives",
        "",
        placeholder="201, 301A, 2607, board of directors, Credit Risk",
        key="proper_conduct_query")

    directive_view = directives
    if directive_query:
        directive_view = filter_proper_conduct_directives(
            directive_view, directive_query)

    st.markdown(f"**{len(directive_view):,}** directives match.")
    table = directive_view[[
        "directive_number", "circular_number", "publication_date",
        "title_display", "subject_display", "lastmod", "url"
    ]].copy()
    table["directive_link"] = (
        table["url"].str.rstrip("/")
        + "/#directive-"
        + table["directive_number"])
    table = table[[
        "directive_link", "circular_number", "publication_date",
        "title_display", "subject_display", "lastmod"
    ]]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            "directive_link": st.column_config.LinkColumn(
                "Directive #",
                width="small",
                display_text=r"#directive-([^#]+)$"),
            "circular_number": st.column_config.TextColumn(
                "Circular #", width="small"),
            "publication_date": st.column_config.TextColumn(
                "Published", width="small"),
            "title_display": "Title",
            "subject_display": "Subject",
            "lastmod": st.column_config.TextColumn("Updated", width="medium"),
        })
    export_cols = [
        "directive_number", "circular_number", "publication_date",
        "title_display", "subject_display", "subject", "area", "lastmod",
        "url", "file_url",
    ]
    st.download_button(
        "Download directives (CSV)",
        directive_view[export_cols].to_csv(index=False).encode("utf-8"),
        "proper_conduct_banking_business_directives.csv",
        "text/csv")

    if directive_view.empty:
        return

    def directive_preview_label(index):
        row = directive_view.loc[index]
        number = row["directive_number"]
        title = row["title_display"] or row["title"]
        return f"{number} - {title}" if number else title

    selected_directive = st.selectbox(
        "Preview directive",
        directive_view.index.tolist(),
        format_func=directive_preview_label,
        key="proper_conduct_preview_directive")
    selected = directive_view.loc[selected_directive]
    st.markdown(
        f"**{selected['directive_number']}** "
        f"{selected['title_display']}")

    page_col, pdf_col = st.columns(2)
    with page_col:
        st.link_button(
            "Open directive page",
            selected["url"],
            width="stretch")
    with pdf_col:
        st.link_button(
            "Open PDF",
            selected["file_url"],
            width="stretch")

    if selected["file_url"]:
        try:
            model, directive_pdf = get_reader_model(
                selected["file_url"],
                selected["title_display"])
            st.download_button(
                "Download PDF",
                directive_pdf,
                slug_for(selected["file_url"]) + ".pdf",
                "application/pdf")
            render_pdf_viewer(model, height=720)
        except Exception as e:
            st.error(f"Unable to load PDF preview: {e}")
    else:
        st.info("No PDF file is available for this directive.")


def render_reader_section(catalog):
    render_section_heading("Reader")
    pdf_catalog = catalog[catalog["doc_type"].str.lower() == "pdf"].copy()
    pdf_catalog = pdf_catalog.drop_duplicates(subset=["doc_url"]).reset_index(drop=True)
    reader_docs = load_search_docs(search_corpus_signature())

    reader_query = st.text_input(
        "Find PDF",
        "",
        placeholder='Search all PDFs: stock, inflation, "monetary policy"',
        key="reader_query")
    reader_view = build_reader_results(pdf_catalog, reader_docs, reader_query)

    if reader_query.strip():
        st.caption(
            f"{len(reader_view):,} PDFs match across catalog metadata and "
            f"{len(reader_docs):,} extracted full-text PDFs.")
        if not reader_view.empty:
            preview = reader_view[[
                "source_title", "doc_title", "lastmod", "full_text_matches",
                "matched_terms", "search_snippet", "doc_url"
            ]].head(12).copy()
            st.dataframe(
                preview,
                hide_index=True,
                width="stretch",
                height=230,
                column_config={
                    "source_title": "Publication",
                    "doc_title": "Link text",
                    "lastmod": st.column_config.TextColumn("Updated", width="medium"),
                    "full_text_matches": st.column_config.NumberColumn(
                        "Text hits", width="small"),
                    "matched_terms": "Terms",
                    "search_snippet": "Snippet",
                    "doc_url": st.column_config.LinkColumn("URL"),
                })

    def reader_label(index):
        row = reader_view.loc[index]
        title = row["source_title"] or row["doc_title"] or row["doc_url"].rsplit("/", 1)[-1]
        date = str(row.get("lastmod", ""))[:10]
        hits = int(row.get("full_text_matches", 0) or 0)
        hit_label = f" ({hits:,} text hits)" if hits else ""
        return f"{title}{hit_label} - {date}" if date else f"{title}{hit_label}"

    if reader_view.empty:
        st.info("No PDFs match.")
        return

    pick_col, action_col = st.columns([4, 1])
    with pick_col:
        selected_pdf = st.selectbox(
            "Publication",
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
        render_pdf_viewer(viewer_model)


apply_library_styles()

if not os.path.exists(LINKS):
    st.warning(
        "No catalog yet. Run **`python3 boi_pdf_extractor.py`** first to build "
        "`boi_pdf_links.csv`, then reload this page.")
    st.stop()

catalog = load_catalog(file_mtime(LINKS))
directives = load_proper_conduct_directives()
section = render_library_shell(catalog, directives)

if section == "Catalog":
    render_catalog_section(catalog)
elif section == "Reader":
    render_reader_section(catalog)
else:
    render_proper_conduct_section(directives)
