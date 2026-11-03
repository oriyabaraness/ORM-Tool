"""Risk Compare: the Israel vs Jordan regulatory risk comparison view.

Rendered as a section of the Streamlit library (app.py). All data comes from
orm.queries over orm.db, which is built by orm_pipeline.py.
"""
from __future__ import annotations

import html
import os
import re

import pandas as pd
import streamlit as st

from orm import classify, db, match, pipeline, queries, taxonomy

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
.orm-doc-group {font-size: 13px; color: #444; margin: 14px 0 6px 0; padding-top: 8px;
    border-top: 1px solid #ddddda;}
.orm-doc-group .ref {color: #17345b; font-weight: 600; margin-right: 6px;}
.orm-selected {background: #fff; border: 1px solid #ddddda; border-left: 4px solid #17345b;
    border-radius: 6px; padding: 14px 16px; font-family: Georgia, serif; font-size: 16px;
    line-height: 1.6; margin-bottom: 22px;}
.orm-selected .head, .orm-match .head {font-family: system-ui, sans-serif;
    font-size: 12px; color: #666; margin-bottom: 6px;}
.orm-selected .head b, .orm-match .head b {color: #17345b;}
.orm-selected mark, .orm-match mark {background: #fff3bf;}
.orm-match {background: #fafafa; border: 1px solid #ececea; border-radius: 6px;
    padding: 12px 14px; margin: 10px 0; font-size: 14px; line-height: 1.5;}
.orm-match .bar {height: 3px; background: #ececea; border-radius: 2px; margin-bottom: 8px;}
.orm-match .bar span {display: block; height: 3px; background: #9b2f4a; border-radius: 2px;}
.orm-match .strength {float: right; font-weight: 600; color: #9b2f4a;}
.orm-fulltext {max-height: 340px; overflow-y: auto; white-space: normal; padding-right: 6px;}
.orm-selected .orm-fulltext {max-height: 520px;}
.orm-read-meta {font-family: system-ui, sans-serif; font-size: 13px; color: #555; margin: 4px 0 12px;}
.orm-read {border-left: 3px solid #ececea; padding: 6px 0 6px 12px; margin-bottom: 8px;}
.orm-read.tagged {border-left-color: #9b2f4a; background: #fdf8f9;}
.orm-read .ref {font-family: system-ui, sans-serif; font-weight: 600; color: #17345b;
  font-size: 13px; margin-right: 6px;}
.orm-warn {background: #fff6e5; border: 1px solid #f3dca8; border-radius: 8px;
  padding: 10px 14px; font-family: system-ui, sans-serif; font-size: 14px; margin: 8px 0;}
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


def _highlight(text: str, terms: list[str], limit: int | None = None) -> str:
    """Escape + highlight. The whole text is kept unless a limit is given;
    callers wrap it in a scrollable .orm-fulltext box instead of cutting."""
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
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
            f' {_e(p["ref"])}{reviewed}</div><div class="orm-fulltext">{_highlight(p["text"], terms + ev_terms)}</div>'
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


# --- clause explorer ------------------------------------------------------------

def _short(text: str, n: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _source_link(row) -> str:
    link = row.get("pdf_url") or row.get("url")
    return (f' · <a href="{_e(link)}" target="_blank">open source ↗</a>'
            if link else "")


def render_clause_explorer(conn, country: str, category_id: str) -> None:
    """Pick a clause on the left; its equivalents in the other countries
    appear on the right."""
    others = [j for j in J if j != country]
    query = st.text_input("Filter clauses", "", key="orm_clause_query",
                          placeholder="e.g. notify, exit strategy, 24 hours")
    rows = queries.clauses(conn, country, category_id, query=query)

    if rows.empty:
        docs = queries.category_documents(conn, category_id, country)
        if query.strip():
            msg = "No clauses match this filter."
        elif docs.empty:
            msg = (f"{NAMES[country]} has no documents mapped to this category.")
        else:
            msg = (f"{NAMES[country]} has {len(docs)} document"
                   f"{'s' if len(docs) != 1 else ''} in this category, but their "
                   "text hasn't been extracted yet, so there are no clauses to "
                   "click. Run <code>python orm_pipeline.py build --fetch</code>.")
        st.markdown(f'<div class="orm-note">{msg}</div>', unsafe_allow_html=True)
        return

    ids = rows["provision_id"].tolist()
    key = f"orm_clause_{country}_{category_id}"
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]
    selected_id = st.session_state[key]

    left, right = st.columns([5, 6], gap="large")
    with left:
        st.markdown(f'<div class="orm-col-head {country}">{NAMES[country]} · '
                    f'{len(rows)} clause{"s" if len(rows) != 1 else ""}</div>',
                    unsafe_allow_html=True)
        with st.container(height=680, border=False):
            for doc_id, group in rows.groupby("document_id", sort=False):
                first = group.iloc[0]
                st.markdown(
                    f'<div class="orm-doc-group"><span class="ref">'
                    f'{_e(first["doc_ref"])}</span>{_e(first["doc_title"])}</div>',
                    unsafe_allow_html=True)
                for _, c in group.iterrows():
                    pid = int(c["provision_id"])
                    n = int(c["matches"])
                    label = (f'{c["ref"] or "¶"}  {_short(c["text"], 95)}'
                             f'  ·  {n} match{"es" if n != 1 else ""}')
                    label = re.sub(r"[*_`\[\]#<>$~|]", "", label)
                    if st.button(label, key=f"orm_btn_{pid}", width="stretch",
                                 type="primary" if pid == selected_id else "secondary"):
                        st.session_state[key] = pid
                        st.rerun()

    with right:
        clause = queries.clause(conn, selected_id)
        st.markdown(
            f'<div class="orm-selected"><div class="head"><b>'
            f'{_e(clause["doc_ref"] or clause["doc_title"])}</b> {_e(clause["ref"])}'
            f' · {_e(clause["doc_title"])}{_source_link(clause)}</div>'
            f'<div class="orm-fulltext">'
            f'{_highlight(clause["text"], classify.matched_keywords(category_id, clause["text"]))}'
            f'</div></div>', unsafe_allow_html=True)

        matches = queries.equivalents(conn, selected_id, category_id)
        for j in others:
            st.markdown(f'<div class="orm-col-head {j}">Equivalent in {NAMES[j]}</div>',
                        unsafe_allow_html=True)
            mj = matches[matches["jurisdiction"] == j]
            if mj.empty:
                if not queries.has_text_in_category(conn, j, category_id):
                    msg = (f"{NAMES[j]} has no extracted text in this category yet, "
                           "so it can't be compared.")
                else:
                    msg = (f"No comparable clause found in {NAMES[j]}. "
                           "This may be a gap worth reviewing.")
                st.markdown(f'<div class="orm-note">{msg}</div>', unsafe_allow_html=True)
                continue
            cards = []
            for _, m in mj.iterrows():
                strength = match.strength(m["score"])
                width = max(6, min(100, int(m["score"] * 160)))
                why = "".join(f'<span class="orm-chip">✓ {_e(x)}</span>'
                              for x in m["shared_expectation_labels"])
                terms = (f'<div class="orm-ev">Shared terms: {_e(m["shared_terms"])}</div>'
                         if m["shared_terms"] else "")
                cards.append(
                    f'<div class="orm-match"><div class="bar"><span style="width:{width}%">'
                    f'</span></div><div class="head"><b>{_e(m["doc_ref"] or m["doc_title"])}'
                    f'</b> {_e(m["ref"])} · {_e(m["doc_title"])}{_source_link(m)}'
                    f'<span class="strength">{strength}</span></div>'
                    f'<div class="orm-fulltext">{_highlight(m["text"], [])}</div>'
                    f'<div>{why}</div>{terms}</div>')
            st.markdown("".join(cards), unsafe_allow_html=True)
        st.caption("Matches are suggested by text similarity and shared baseline "
                   "expectations within the same risk category. Confirm before "
                   "relying on them.")


# --- full directive reader --------------------------------------------------

_STATUS_TEXT = {
    "pending": "not read yet",
    "no_text": "no text available",
    "error": "reading failed",
}


def render_full_directive(conn, country: str, category_id: str) -> None:
    """Read one directive from start to finish -- every provision, in order,
    with the clauses tagged for the current risk category marked."""
    docs = queries.documents(conn, country)
    if docs.empty:
        st.markdown(f'<div class="orm-note">No {NAMES[country]} documents in the '
                    'index.</div>', unsafe_allow_html=True)
        return

    unread = docs[docs["text_status"] != "ok"]
    if not unread.empty:
        reasons = "".join(
            f"<li>{_e(r['doc_ref'] or '')} {_e(r['doc_title'])} — "
            f"{_STATUS_TEXT.get(r['text_status'], r['text_status'])}"
            f"{': ' + _e(r['error']) if r['error'] else ''}</li>"
            for _, r in unread.head(60).iterrows())
        more = f"<li>… and {len(unread) - 60} more</li>" if len(unread) > 60 else ""
        st.markdown(
            f'<div class="orm-warn"><b>{len(unread)} of {len(docs)} {NAMES[country]} '
            'documents have no text in the index, so Risk Compare cannot read '
            'them.</b> Run <code>python orm_pipeline.py build --fetch</code>, or '
            'save the PDF from your browser into <code>orm_texts/manual/</code> '
            'named after the document id.<details><summary>Show which</summary>'
            f'<ul>{reasons}{more}</ul></details></div>', unsafe_allow_html=True)

    read = docs[docs["text_status"] == "ok"]
    if read.empty:
        return
    labels = {r["document_id"]: (f"{r['doc_ref'] + ' · ' if r['doc_ref'] else ''}"
                                 f"{r['doc_title']}  ({int(r['provisions'])} provisions)")
              for _, r in read.iterrows()}
    doc_id = st.selectbox("Directive", list(labels), format_func=labels.get,
                          key=f"orm_read_doc_{country}")
    doc = read[read["document_id"] == doc_id].iloc[0]
    provs = queries.document_provisions(conn, doc_id)

    chars = int(doc["chars"] or 0)
    kept = int(doc["provision_chars"] or 0)
    pages = f"{int(doc['pages'])} pages · " if pd.notna(doc["pages"]) and doc["pages"] else ""
    coverage = f" · {min(100, round(100 * kept / chars))}% of the text kept" if chars else ""
    tagged_here = provs["categories"].str.split(",").apply(
        lambda cs: category_id in cs).sum()
    link = doc["pdf_url"] or doc["url"]
    link_html = (f' · <a href="{_e(link)}" target="_blank">open source ↗</a>'
                 if link else "")
    st.markdown(
        f'<div class="orm-read-meta">{pages}{len(provs)} provisions'
        f'{coverage} · {int(doc["tagged"])} tagged with any risk category · '
        f'{tagged_here} with <b>{_e(taxonomy.BY_ID[category_id].name)}</b>'
        f'{link_html}</div>', unsafe_allow_html=True)

    only_tagged = st.toggle("Only clauses in this risk category", value=False,
                            key=f"orm_read_only_{country}")
    blocks = []
    for _, p in provs.iterrows():
        cats = [c for c in p["categories"].split(",") if c]
        in_cat = category_id in cats
        if only_tagged and not in_cat:
            continue
        chips = "".join(f'<span class="orm-chip">{_e(taxonomy.BY_ID[c].name)}</span>'
                        for c in cats if c in taxonomy.BY_ID)
        terms = classify.matched_keywords(category_id, p["text"]) if in_cat else []
        blocks.append(
            f'<div class="orm-read{" tagged" if in_cat else ""}">'
            f'<span class="ref">{_e(p["ref"] or "¶")}</span>'
            f'{_highlight(p["text"], terms)}<div>{chips}</div></div>')
    with st.container(height=760, border=False):
        st.markdown("".join(blocks) or '<div class="orm-note">No clauses.</div>',
                    unsafe_allow_html=True)


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

        c1, c2, c3, c4 = st.columns([2, 3, 2, 1.3], vertical_alignment="bottom")
        with c1:
            country = st.selectbox("Country", list(J), format_func=NAMES.get,
                                   key="orm_country")
        with c3:
            orm_only = st.toggle("ORM core categories only", value=True,
                                 key="orm_core_only")
        counts = queries.category_counts(conn, country)
        options = [c.id for c in taxonomy.CATEGORIES if c.orm_core or not orm_only]
        with c2:
            category_id = st.selectbox(
                "Risk management category", options, key="orm_category",
                format_func=lambda cid: (f"{taxonomy.BY_ID[cid].name}  ·  "
                                         f"{counts.get(cid, 0)} clauses"))
        with c4:
            if st.button("Rebuild index", width="stretch",
                         help="Re-reads the source indexes and any cached text, "
                              "then re-tags and re-matches everything. Does not "
                              "download PDFs."):
                with st.spinner("Rebuilding…"):
                    pipeline.build(path, fetch=False)
                st.rerun()
        st.caption(taxonomy.BY_ID[category_id].description)

        explorer, reader, side, gap, dl, overview = st.tabs(
            ["Clause explorer", "Full directive", "Side by side", "Gap analysis",
             "Deadlines", "Coverage matrix"])
        with explorer:
            render_clause_explorer(conn, country, category_id)
        with reader:
            render_full_directive(conn, country, category_id)
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
        with overview:
            matrix = queries.coverage_matrix(conn, orm_only=orm_only)
            render_matrix(matrix)
            st.download_button(
                "Download matrix (CSV)", matrix.to_csv(index=False).encode("utf-8"),
                "risk_coverage_matrix.csv", "text/csv")
