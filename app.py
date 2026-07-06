"""
Bank of Israel Publications Explorer -- a Streamlit UI over the crawl/extract
pipeline.

  Catalog tab : search & filter the document catalog (boi_pdf_links.csv), pick
                publications, extract their text on the spot, read it, and
                download the text or the source PDF.
  Overview tab: counts and a peek at the page index (boi_publications_index.csv).

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
INDEX = os.path.join(HERE, "boi_publications_index.csv")
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
def load_index(mtime):
    return pd.read_csv(INDEX)


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
        term = (quoted or bare).strip().lower()
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


st.title("🏦 Bank of Israel Publications Explorer")

if not os.path.exists(LINKS):
    st.warning(
        "No catalog yet. Run **`python3 boi_pdf_extractor.py`** first to build "
        "`boi_pdf_links.csv`, then reload this page.")
    st.stop()

catalog = load_catalog(file_mtime(LINKS))
tab_catalog, tab_search, tab_reader, tab_overview = st.tabs(
    ["📚 Catalog", "🔎 Full Text", "Reader", "📊 Overview"])

# --------------------------------------------------------------------------- #
# Catalog tab
# --------------------------------------------------------------------------- #
with tab_catalog:
    with st.sidebar:
        st.header("Filters")
        query = st.text_input("Search title / URL", "",
                              placeholder="e.g. annual report, inflation")
        sections = sorted(s for s in catalog["section"].unique() if s)
        pick_sections = st.multiselect("Section", sections, default=[])
        types = sorted(t for t in catalog["doc_type"].unique() if t)
        pick_types = st.multiselect("File type", types, default=[])
        only_dated = catalog[catalog["lastmod"] != ""]
        if not only_dated.empty:
            years = sorted({d[:4] for d in only_dated["lastmod"] if len(d) >= 4})
            pick_years = st.multiselect("Year (lastmod)", years, default=[])
        else:
            pick_years = []
        st.caption(f"Catalog: {len(catalog):,} documents")

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

    st.markdown(f"**{len(view):,}** documents match. Tick the ones you want, "
                "then extract their text below.")

    display = view[["source_title", "doc_title", "doc_type", "lastmod",
                    "doc_url"]].copy()
    display.insert(0, "select", False)
    edited = st.data_editor(
        display, hide_index=True, width="stretch", height=380,
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
        go = st.button(f"📄 Extract text ({len(chosen)})",
                       type="primary", disabled=not chosen)
    with c2:
        st.download_button("⬇️ Download filtered catalog (CSV)",
                           view.to_csv(index=False).encode("utf-8"),
                           "boi_filtered_catalog.csv", "text/csv")

    if go:
        prog = st.progress(0.0)
        for i, url in enumerate(chosen, 1):
            try:
                pages, text = get_text(url)
                title = (view.loc[view["doc_url"] == url, "source_title"].iloc[0]
                         or url.rsplit("/", 1)[-1])
                with st.expander(f"📄 {title} — {pages} pages, "
                                 f"{len(text):,} chars", expanded=(i == 1)):
                    st.caption(url)
                    st.download_button("⬇️ Save text (.txt)", text.encode("utf-8"),
                                       slug_for(url) + ".txt", "text/plain",
                                       key="dl_" + slug_for(url))
                    st.text_area("Text", text, height=320,
                                 key="ta_" + slug_for(url))
            except Exception as e:
                st.error(f"Failed to extract {url}: {e}")
            prog.progress(i / len(chosen))
        prog.empty()
        st.success(f"Extracted {len(chosen)} document(s).")

# --------------------------------------------------------------------------- #
# Full-text tab
# --------------------------------------------------------------------------- #
with tab_search:
    docs = load_search_docs(search_corpus_signature())
    s1, s2, s3 = st.columns(3)
    s1.metric("Searchable documents", f"{len(docs):,}")
    text_file_count = len(docs["txt_path"].unique()) if not docs.empty else 0
    indexed_chars = int(docs["_text"].str.len().sum()) if not docs.empty else 0
    s2.metric("Text files", f"{text_file_count:,}")
    s3.metric("Indexed characters", f"{indexed_chars:,}")

    qcol, mode_col, limit_col = st.columns([3, 1, 1])
    with qcol:
        full_query = st.text_input(
            "Search full text",
            "",
            placeholder='inflation expectations or "monetary policy"',
            key="full_text_query")
    with mode_col:
        match_mode = st.segmented_control(
            "Match",
            ["All terms", "Any term"],
            default="All terms",
            key="full_text_match")
    with limit_col:
        result_limit = st.number_input(
            "Results",
            min_value=5,
            max_value=100,
            value=25,
            step=5,
            key="full_text_limit")

    terms = parse_terms(full_query)
    if not docs.empty and terms:
        results = search_full_text(docs, terms, match_mode, int(result_limit))
        st.markdown(f"**{len(results):,}** documents match.")
        if not results.empty:
            table = results[["source_title", "doc_title", "section", "lastmod",
                             "pages", "matches", "matched_terms", "doc_url"]]
            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
                column_config={
                    "source_title": "Publication",
                    "doc_title": "Link text",
                    "section": "Section",
                    "lastmod": st.column_config.TextColumn("Updated", width="medium"),
                    "pages": st.column_config.NumberColumn("Pages", width="small"),
                    "matches": st.column_config.NumberColumn("Hits", width="small"),
                    "matched_terms": "Terms",
                    "doc_url": st.column_config.LinkColumn("URL"),
                })
            st.download_button(
                "⬇️ Download search results (CSV)",
                results.drop(columns=["_text"]).to_csv(index=False).encode("utf-8"),
                "boi_full_text_search_results.csv",
                "text/csv")

            for i, row in results.iterrows():
                title = row["source_title"] or row["doc_title"] or row["doc_url"]
                with st.expander(
                        f"🔎 {title} — {row['matches']:,} hits",
                        expanded=(i == results.index[0])):
                    st.caption(row["doc_url"])
                    st.text_area("Snippets", row["snippet"], height=160,
                                 key=f"snippet_{i}")
                    st.download_button(
                        "⬇️ Download full text (.txt)",
                        row["_text"].encode("utf-8"),
                        slug_for(row["doc_url"]) + ".txt",
                        "text/plain",
                        key=f"full_text_download_{i}")
        else:
            st.info("No extracted document text matched that query.")
    elif docs.empty:
        st.warning("No extracted text files were found.")

# --------------------------------------------------------------------------- #
# Reader tab
# --------------------------------------------------------------------------- #
with tab_reader:
    pdf_catalog = catalog[catalog["doc_type"].str.lower() == "pdf"].copy()
    pdf_catalog = pdf_catalog.drop_duplicates(subset=["doc_url"]).reset_index(drop=True)

    reader_query = st.text_input(
        "Find PDF",
        "",
        placeholder="annual report, inflation, monetary policy",
        key="reader_query")
    reader_view = pdf_catalog
    if reader_query:
        q = reader_query.lower()
        hay = (reader_view["source_title"] + " " + reader_view["doc_title"] + " "
               + reader_view["doc_url"]).str.lower()
        reader_view = reader_view[hay.str.contains(q, regex=False)]

    def reader_label(index):
        row = reader_view.loc[index]
        title = row["source_title"] or row["doc_title"] or row["doc_url"].rsplit("/", 1)[-1]
        date = str(row.get("lastmod", ""))[:10]
        return f"{title} - {date}" if date else title

    if reader_view.empty:
        st.info("No PDFs match.")
    else:
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
            render_pdf_viewer(model)

# --------------------------------------------------------------------------- #
# Overview tab
# --------------------------------------------------------------------------- #
with tab_overview:
    a, b, c = st.columns(3)
    a.metric("Documents in catalog", f"{len(catalog):,}")
    b.metric("PDFs", f"{(catalog['doc_type'] == 'pdf').sum():,}")
    c.metric("Sections", catalog["section"].nunique())

    st.subheader("Documents by section")
    st.bar_chart(catalog["section"].value_counts())

    st.subheader("Documents by file type")
    st.bar_chart(catalog["doc_type"].value_counts())

    if os.path.exists(INDEX):
        idx = load_index(file_mtime(INDEX))
        st.subheader("Page index (sitemap-derived)")
        st.caption(f"{len(idx):,} publication pages known from the sitemap.")
        st.dataframe(idx.head(200), hide_index=True, width="stretch")
