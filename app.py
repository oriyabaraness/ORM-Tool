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
import os

import pandas as pd
import streamlit as st

from boi_pdf_text import extract_one, slug_for

HERE = os.path.dirname(os.path.abspath(__file__))
LINKS = os.path.join(HERE, "boi_pdf_links.csv")
INDEX = os.path.join(HERE, "boi_publications_index.csv")

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


@st.cache_data(show_spinner="Extracting text…")
def get_text(url):
    """Download + extract a single PDF. Cached per URL. Returns (pages, text)."""
    return extract_one(url)


def file_mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


st.title("🏦 Bank of Israel Publications Explorer")

if not os.path.exists(LINKS):
    st.warning(
        "No catalog yet. Run **`python3 boi_pdf_extractor.py`** first to build "
        "`boi_pdf_links.csv`, then reload this page.")
    st.stop()

catalog = load_catalog(file_mtime(LINKS))
tab_catalog, tab_overview = st.tabs(["📚 Catalog", "📊 Overview"])

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
        display, hide_index=True, use_container_width=True, height=380,
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
        st.dataframe(idx.head(200), hide_index=True, use_container_width=True)
