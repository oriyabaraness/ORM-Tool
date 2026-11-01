"""Risk Compare: the Israel vs Jordan regulatory risk comparison view.

Rendered as a section of the Streamlit library (app.py). All data comes from
orm.queries over orm.db, which is built by orm_pipeline.py.
"""
from __future__ import annotations

import html
import os
import re

import streamlit as st

from orm import classify, db, pipeline, queries, taxonomy

J = queries.JURISDICTIONS
NAMES = queries.JURISDICTION_NAMES

LEVEL_LABEL = {
    "text": "Provisions indexed",
    "metadata": "Mapped from titles",
    "none": "No coverage found",
}

CSS = """
<style>
.orm-intro {color: var(--color-text-muted, #666); font-size: 15px; max-width: 760px;
    margin: -4px 0 18px 0; line-height: 1.45;}
.orm-status {display: flex; gap: 32px; flex-wrap: wrap; margin: 0 0 20px 0;
    font-size: 14px; color: #444;}
.orm-status b {color: #17345b;}
.orm-matrix {width: 100%; border-collapse: collapse; font-size: 14px; margin: 4px 0 8px 0;}
.orm-matrix th {text-align: left; font-weight: 600; color: #666; font-size: 13px;
    border-bottom: 1px solid #ddddda; padding: 8px 10px;}
.orm-matrix td {border-bottom: 1px solid #ececea; padding: 10px; vertical-align: top;}
.orm-matrix td.cat {font-family: Georgia, "Times New Roman", serif; font-size: 17px;
    color: #222; width: 30%;}
.orm-matrix td.cat small {display: block; font-family: system-ui, sans-serif;
    font-size: 12px; color: #888; margin-top: 2px;}
.orm-cell {display: flex; gap: 8px; align-items: flex-start;}
.orm-dot {width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex: none;}
.orm-dot.text {background: #17345b;}
.orm-dot.metadata {background: #fff; border: 2px solid #6fa6bd;}
.orm-dot.none {background: #ddddda;}
.orm-cell .n {color: #222;}
.orm-cell .sub {color: #888; font-size: 12px;}
.orm-legend {font-size: 12px; color: #666; display: flex; gap: 18px; margin-bottom: 24px;}
.orm-legend span {display: inline-flex; gap: 6px; align-items: center;}
.orm-col-head {font-family: Georgia, serif; font-size: 22px; color: #222;
    border-top: 4px solid #006d7e; padding-top: 8px; margin-bottom: 6px;}
.orm-col-head.JO {border-top-color: #9b2f4a;}
.orm-doc {font-size: 14px; padding: 6px 0; border-bottom: 1px solid #ececea;}
.orm-doc .ref {color: #17345b; font-weight: 600; margin-right: 6px;}
.orm-doc .meta {color: #888; font-size: 12px;}
.orm-prov {background: #fafafa; border: 1px solid #ececea; border-radius: 6px;
    padding: 10px 12px; margin: 10px 0; font-size: 14px; line-height: 1.5;}
.orm-prov .head {font-size: 12px; color: #666; margin-bottom: 4px;}
.orm-prov .head b {color: #17345b;}
.orm-prov mark {background: #fff3bf; padding: 0 1px;}
.orm-chip {display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 10px;
    background: #eef5ff; border: 1px solid #d6e5ff; color: #17345b; margin: 6px 4px 0 0;}
.orm-note {background: #eef5ff; border: 1px solid #d6e5ff; border-radius: 8px;
    padding: 10px 14px; font-size: 14px; color: #333; margin: 8px 0;}
.orm-gap {width: 100%; border-collapse: collapse; font-size: 14px;}
.orm-gap th {text-align: left; color: #666; font-weight: 600; font-size: 13px;
    border-bottom: 1px solid #ddddda; padding: 8px;}
.orm-gap td {border-bottom: 1px solid #ececea; padding: 8px; vertical-align: top;}
.orm-pill {font-size: 12px; padding: 1px 8px; border-radius: 10px; white-space: nowrap;}
.orm-pill.found {background: #e6f2ea; color: #2f6b3d;}
.orm-pill.not-found {background: #f8e6ea; color: #9b2f4a;}
.orm-pill.not-assessed {background: #ececea; color: #666;}
.orm-ev {color: #666; font-size: 12px; margin-top: 4px;}
</style>
"""


# --- data -------------------------------------------------------------------

def _db_path() -> str:
    return db.DEFAULT_DB


def ensure_index(path: str) -> None:
    """Build the index from metadata + cached text if it doesn't exist yet."""
    needs_build = not os.path.exists(path)
    if not needs_build:
        with db.session(path) as conn:
            db.init(conn)
            needs_build = conn.execute("SELECT COUNT(*) FROM document").fetchone()[0] == 0
    if needs_build:
        with st.spinner("Building the comparison index…"):
            pipeline.build(path, fetch=False)


# --- rendering helpers --------------------------------------------------------

def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _highlight(text: str, terms: list[str], limit: int = 900) -> str:
    text = text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"
    out = _e(text)
    for t in sorted({t for t in terms if len(t) > 2}, key=len, reverse=True):
        out = re.sub(f"({re.escape(html.escape(t))})", r"<mark>\1</mark>", out,
                     flags=re.I)
    return out


def _cell(row, j: str) -> str:
    level = row[f"{j}_level"]
    docs, text_docs, provs = row[f"{j}_docs"], row[f"{j}_docs_text"], row[f"{j}_provisions"]
    if level == "none":
        main, sub = "—", ""
    elif level == "metadata":
        main = f"{docs} document{'s' if docs != 1 else ''}"
        sub = "no text extracted yet"
    else:
        main = f"{provs} provision{'s' if provs != 1 else ''}"
        sub = f"{text_docs} of {docs} docs with text"
    latest = row[f"{j}_latest"]
    if latest and level != "none":
        sub = f"{sub} · latest {latest[:10]}" if sub else f"latest {latest[:10]}"
    return (f'<div class="orm-cell"><span class="orm-dot {level}" '
            f'title="{LEVEL_LABEL[level]}"></span><div><div class="n">{_e(main)}</div>'
            f'<div class="sub">{_e(sub)}</div></div></div>')


def render_matrix(matrix) -> None:
    head = "".join(f"<th>{NAMES[j]}</th>" for j in J)
    body = []
    for _, row in matrix.iterrows():
        tag = "ORM core" if row["orm_core"] else "Prudential / other"
        cells = "".join(f"<td>{_cell(row, j)}</td>" for j in J)
        body.append(f'<tr><td class="cat">{_e(row["name"])}<small>{tag}</small></td>{cells}</tr>')
    st.markdown(
        f'<table class="orm-matrix"><thead><tr><th>Risk category</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
        '<div class="orm-legend">'
        '<span><span class="orm-dot text"></span>Provisions indexed</span>'
        '<span><span class="orm-dot metadata"></span>Mapped from titles only</span>'
        '<span><span class="orm-dot none"></span>No coverage found</span></div>',
        unsafe_allow_html=True)


def render_jurisdiction_column(conn, category_id: str, j: str, query: str) -> None:
    st.markdown(f'<div class="orm-col-head {j}">{NAMES[j]}</div>', unsafe_allow_html=True)
    docs = queries.category_documents(conn, category_id, j)
    if docs.empty:
        st.markdown('<div class="orm-note">No documents in this category.</div>',
                    unsafe_allow_html=True)
        return

    items = []
    for _, d in docs.iterrows():
        link = d["pdf_url"] or d["url"]
        title = (f'<a href="{_e(link)}" target="_blank">{_e(d["title"])}</a>'
                 if link else _e(d["title"]))
        status = "text indexed" if d["text_status"] == "ok" else "metadata only"
        date = f" · {d['date'][:10]}" if d["date"] else ""
        items.append(
            f'<div class="orm-doc"><span class="ref">{_e(d["ref"])}</span>{title}'
            f'<div class="meta">{status}{date} · matched by {_e(d["evidence"])}</div></div>')
    with st.expander(f"{len(docs)} document{'s' if len(docs) != 1 else ''}",
                     expanded=False):
        st.markdown("".join(items), unsafe_allow_html=True)

    provs = queries.category_provisions(conn, category_id, j, query=query)
    if provs.empty:
        has_text = (docs["text_status"] == "ok").any()
        msg = ("No provisions match this search." if query.strip() and has_text else
               "No extracted text for these documents yet, so only the titles "
               "are mapped. Run <code>python orm_pipeline.py build --fetch</code> "
               "to pull the PDFs.")
        st.markdown(f'<div class="orm-note">{msg}</div>', unsafe_allow_html=True)
        return

    terms = query.split()
    cards = []
    for _, p in provs.iterrows():
        ev_terms = classify.matched_keywords(category_id, p["text"])
        chips = "".join(f'<span class="orm-chip">⏱ {_e(v)}</span>' for v in p["deadlines"])
        chips += "".join(f'<span class="orm-chip">↻ {_e(v)}</span>' for v in p["frequencies"])
        reviewed = " · ✓ reviewed" if p["reviewed"] == 1 else ""
        cards.append(
            f'<div class="orm-prov"><div class="head"><b>{_e(p["doc_ref"] or p["doc_title"])}</b>'
            f' {_e(p["ref"])}{reviewed}</div>{_highlight(p["text"], terms + ev_terms)}'
            f'<div>{chips}</div></div>')
    st.markdown("".join(cards), unsafe_allow_html=True)


def render_gap_table(conn, category_id: str) -> None:
    cat = taxonomy.BY_ID[category_id]
    if not cat.expectations:
        st.markdown('<div class="orm-note">No baseline expectations are defined for '
                    'this category yet. Gap analysis covers the ORM core categories.</div>',
                    unsafe_allow_html=True)
        return
    table = queries.expectation_table(conn, category_id)
    head = "".join(f"<th>{NAMES[j]}</th>" for j in J)
    rows = []
    for _, r in table.iterrows():
        cells = []
        for j in J:
            status = r[f"{j}_status"]
            ev = ""
            if status == "found":
                ev = (f'<div class="orm-ev"><b>{_e(r[f"{j}_source"])}</b> — '
                      f'{_e(r[f"{j}_evidence"][:220])}</div>')
            cells.append(f'<td><span class="orm-pill {status.replace(" ", "-")}">'
                         f'{status}</span>{ev}</td>')
        rows.append(f'<tr><td>{_e(r["expectation"])}</td>{"".join(cells)}</tr>')
    st.markdown(
        f'<table class="orm-gap"><thead><tr><th>Baseline expectation</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>', unsafe_allow_html=True)
    st.caption("Keyword-detected against the full text of each jurisdiction. "
               "“Not assessed” means no text is indexed yet for that country in "
               "this category. Treat every result as a lead for review, not a finding.")


def render_deadlines(conn, category_id: str) -> None:
    df = queries.deadlines(conn, category_id)
    if df.empty:
        st.markdown('<div class="orm-note">No deadlines extracted for this category '
                    'yet.</div>', unsafe_allow_html=True)
        return
    df = df.assign(country=df["jurisdiction"].map(NAMES),
                   source=df["doc_ref"].fillna("") + " " + df["ref"].fillna(""),
                   context=df["text"].str.slice(0, 220) + "…")
    st.dataframe(
        df[["country", "value_text", "hours", "source", "doc_title", "context"]],
        hide_index=True, width="stretch",
        column_config={"value_text": "Deadline as written",
                       "hours": st.column_config.NumberColumn("≈ hours", format="%.0f"),
                       "doc_title": "Document"})


# --- section ------------------------------------------------------------------

def render_risk_compare_section(path: str | None = None) -> None:
    path = path or _db_path()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<h2 class="boi-section-title">Risk Compare</h2>', unsafe_allow_html=True)
    st.markdown(
        '<div class="orm-intro">Israel and Jordan banking regulation, mapped to one '
        'risk taxonomy. Pick a category to read both countries’ provisions side by '
        'side and see which baseline expectations each one covers.</div>',
        unsafe_allow_html=True)
    ensure_index(path)

    with db.session(path) as conn:
        status = queries.index_status(conn).set_index("jurisdiction")
        parts = []
        for j in J:
            if j in status.index:
                s = status.loc[j]
                parts.append(f"<span><b>{NAMES[j]}</b> · {int(s['documents'])} documents · "
                             f"{int(s['with_text'] or 0)} with text · "
                             f"{int(s['provisions'])} provisions</span>")
        st.markdown(f'<div class="orm-status">{"".join(parts)}</div>',
                    unsafe_allow_html=True)

        c1, c2 = st.columns([3, 1])
        with c1:
            orm_only = st.toggle("ORM core categories only", value=True,
                                 key="orm_core_only")
        with c2:
            if st.button("Rebuild index", width="stretch",
                         help="Re-reads the source indexes and any cached text, "
                              "then re-tags everything. Does not download PDFs."):
                with st.spinner("Rebuilding…"):
                    pipeline.build(path, fetch=False)
                st.rerun()

        matrix = queries.coverage_matrix(conn, orm_only=orm_only)
        render_matrix(matrix)
        st.download_button(
            "Download matrix (CSV)", matrix.to_csv(index=False).encode("utf-8"),
            "risk_coverage_matrix.csv", "text/csv")

        st.markdown('<div class="boi-section-rule"></div>', unsafe_allow_html=True)
        options = matrix["category_id"].tolist()
        category_id = st.selectbox(
            "Category", options,
            format_func=lambda cid: taxonomy.BY_ID[cid].name, key="orm_category")
        st.caption(taxonomy.BY_ID[category_id].description)

        side, gap, dl = st.tabs(["Side by side", "Gap analysis", "Deadlines"])
        with side:
            query = st.text_input("Search within this category", "",
                                  placeholder="e.g. notify, outsourcing, 24 hours",
                                  key="orm_query")
            cols = st.columns(2, gap="large")
            for col, j in zip(cols, J):
                with col:
                    render_jurisdiction_column(conn, category_id, j, query)
        with gap:
            render_gap_table(conn, category_id)
        with dl:
            render_deadlines(conn, category_id)
