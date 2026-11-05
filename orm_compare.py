"""The comparison workspace: Compare, Coverage, Gaps, Deadlines and Changes.

Each screen is a page function that app.py registers in the left rail. They
share one scope (country, countries to compare with, risk category) that is
remembered while you move between screens. All data comes from orm.queries
over orm.db, which is built by orm_pipeline.py. Look and wording follow
DESIGN.md.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import pandas as pd
import streamlit as st

from orm import classify, db, match, pipeline, queries, taxonomy
from ui_theme import (COUNTRY_ACCENT, citation, e as _e, notice, page_header,
                      pane_head, pill)

J = queries.JURISDICTIONS
NAMES = queries.JURISDICTION_NAMES
REGULATORS = {"IL": "Bank of Israel", "JO": "Central Bank of Jordan",
              "TR": "Central Bank of the Republic of Turkiye"}
HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(HERE, "update_reports")

# Filled in by app.py so screens can link to each other (Coverage -> Compare).
PAGES: dict = {}

LEVEL = {
    "text": ("Clauses indexed", "found"),
    "metadata": ("Titles only", "partial"),
    "none": ("No coverage", "na"),
}
STATUS = {
    "found": ("Found", "found"),
    "not found": ("Not found", "not-found"),
    "not assessed": ("Not assessed", "not-assessed"),
}
STRENGTH_KIND = {"Strong match": "strong", "Partial match": "partial",
                 "Weak match": "weak"}

CSS = """
<style>
.ws-status {display: flex; gap: 22px; flex-wrap: wrap; font-size: 12.5px;
  color: var(--ink-3); margin: -4px 0 12px; font-variant-numeric: tabular-nums;}
.ws-status b {color: var(--ink-2); font-weight: 600;}
.ws-status .dot {width: 7px; height: 7px; border-radius: 50%; display: inline-block;
  margin-right: 6px; vertical-align: 1px;}
.ws-cat-desc {font-size: 12.5px; color: var(--ink-3); margin: -2px 0 12px;}
.ws-doc-group {font-size: 12px; color: var(--ink-2); margin: 12px 0 4px; font-weight: 600;}
.ws-doc-group .ref {color: var(--primary); margin-right: 6px;}
.ws-selected {background: var(--surface); border: 1px solid var(--line);
  border-left: 3px solid var(--primary); border-radius: 6px; padding: 12px 14px;}
.ws-scroll {max-height: 520px; overflow-y: auto; padding-right: 6px;}
.ws-match {background: var(--surface); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 12px 12px; margin: 0 0 10px;}
.ws-match .top {display: flex; align-items: center; gap: 8px; margin-bottom: 6px;}
.ws-match .bar {flex: 1; height: 3px; background: var(--subtle); border-radius: 2px;}
.ws-match .bar span {display: block; height: 3px; background: var(--primary); border-radius: 2px;}
.ws-match .ws-scroll {max-height: 300px;}
.ws-why {font-size: 12px; color: var(--ink-3); margin-top: 6px;}
.ws-table {width: 100%; border-collapse: collapse; font-size: 13px; background: var(--surface);
  border: 1px solid var(--line); border-radius: 6px; overflow: hidden;}
.ws-table th {text-align: left; font-size: 12px; font-weight: 600; color: var(--ink-2);
  background: var(--canvas); border-bottom: 1px solid var(--line); padding: 8px 12px;
  position: sticky; top: 0;}
.ws-table td {border-bottom: 1px solid var(--line); padding: 9px 12px; vertical-align: top;}
.ws-table tr:last-child td {border-bottom: none;}
.ws-table tr:hover td {background: #fafbfc;}
.ws-table td.cat {font-weight: 500; color: var(--ink); width: 30%;}
.ws-table td.cat small {display: block; font-weight: 400; font-size: 12px; color: var(--ink-3);}
.ws-table .n {font-variant-numeric: tabular-nums; color: var(--ink);}
.ws-table .sub {font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums;}
.ws-table .ev {font-size: 12px; color: var(--ink-2); margin-top: 4px;}
.ws-legend {display: flex; gap: 14px; flex-wrap: wrap; margin: 8px 0 18px;
  font-size: 12px; color: var(--ink-3);}
.ws-prov {background: var(--surface); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 12px; margin: 0 0 10px;}
.ws-read-meta {font-size: 12.5px; color: var(--ink-3); margin: 2px 0 12px;
  font-variant-numeric: tabular-nums;}
.ws-read {border-left: 3px solid var(--line); padding: 6px 0 6px 12px; margin-bottom: 8px;}
.ws-read.tagged {border-left-color: var(--primary); background: #f7f9fc;}
.ws-read .ref {font-family: var(--ui) !important; font-weight: 600; color: var(--primary);
  font-size: 12.5px; margin-right: 6px;}
.ws-report {font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 12.5px; white-space: pre-wrap; background: var(--surface);
  border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; color: var(--ink-2);}
/* clause list buttons: left-aligned rows, selected = navy rule + tint */
div[class*="st-key-ws_clause_"] button {justify-content: flex-start; text-align: left;
  border: none !important; border-radius: 0 !important; background: transparent !important;
  border-bottom: 1px solid var(--line) !important; padding: 7px 10px !important;
  color: var(--ink) !important; font-weight: 400 !important; min-height: 0;}
div[class*="st-key-ws_clause_"] button p {font-size: 13px !important; text-align: left;}
div[class*="st-key-ws_clause_"] button:hover {background: var(--subtle) !important;}
div[class*="st-key-ws_clause_"] button[kind="primary"] {background: var(--subtle) !important;
  box-shadow: inset 3px 0 0 var(--primary);}
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


def _open(path: str | None):
    path = path or _db_path()
    st.markdown(CSS, unsafe_allow_html=True)
    ensure_index(path)
    return db.session(path)


# --- rendering helpers --------------------------------------------------------

def _highlight(text: str, terms: list[str], limit: int | None = None) -> str:
    """Escape + highlight. The whole text is kept unless a limit is given;
    callers wrap it in a scrollable box instead of cutting."""
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    out = _e(text)
    for t in sorted({t for t in terms if len(t) > 2}, key=len, reverse=True):
        out = re.sub(f"({re.escape(_e(t))})", r"<mark>\1</mark>", out, flags=re.I)
    return out


def _short(text: str, n: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _val(row, key: str) -> str:
    """A text field from a dict or pandas row; blank for None/NaN."""
    v = row.get(key) if hasattr(row, "get") else None
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def _link(row) -> str | None:
    return _val(row, "pdf_url") or _val(row, "url") or None


def _cite(row) -> str:
    regulator = _val(row, "regulator") or REGULATORS.get(_val(row, "jurisdiction"), "")
    return citation(regulator, _val(row, "doc_ref"), _val(row, "ref"),
                    _val(row, "doc_title"), _link(row))


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# --- shared scope -----------------------------------------------------------------

def _remembered(name: str, options: list, default):
    value = st.session_state.get(f"scope_{name}", default)
    return value if value in options else default


def scope_bar(conn, page: str, *, compare: bool = True, category: bool = True) -> dict:
    """Country · Compare with · Risk category, shared by every workspace page."""
    countries = list(J)
    widths = [1.3] + ([2] if compare else []) + ([3, 1.2] if category else [])
    cols = st.columns(widths, vertical_alignment="bottom")
    i = 0
    with cols[i]:
        current = _remembered("country", countries, countries[0])
        country = st.selectbox("Country", countries, index=countries.index(current),
                               format_func=NAMES.get, key=f"{page}_country")
    st.session_state["scope_country"] = country
    others = [j for j in countries if j != country]
    compare_with = others
    if compare:
        i += 1
        with cols[i]:
            saved = [j for j in st.session_state.get("scope_compare", others)
                     if j in others] or others
            compare_with = st.multiselect("Compare with", others, default=saved,
                                          format_func=NAMES.get,
                                          key=f"{page}_compare") or others
        st.session_state["scope_compare"] = compare_with
    category_id = None
    if category:
        with cols[-1]:
            orm_only = st.toggle("ORM core only",
                                 value=st.session_state.get("scope_core", True),
                                 key=f"{page}_core")
        st.session_state["scope_core"] = orm_only
        counts = queries.category_counts(conn, country)
        options = [c.id for c in taxonomy.CATEGORIES if c.orm_core or not orm_only]
        with cols[-2]:
            current = _remembered("category", options, options[0])
            category_id = st.selectbox(
                "Risk category", options, index=options.index(current),
                key=f"{page}_category",
                format_func=lambda cid: (f"{taxonomy.BY_ID[cid].name}  ·  "
                                         f"{counts.get(cid, 0)} clauses"))
        st.session_state["scope_category"] = category_id
        st.markdown(f'<div class="ws-cat-desc">{_e(taxonomy.BY_ID[category_id].description)}'
                    '</div>', unsafe_allow_html=True)
    return {"country": country, "compare": compare_with, "category": category_id}


def render_status(conn) -> None:
    status = queries.index_status(conn).set_index("jurisdiction")
    parts = []
    for j in J:
        if j in status.index:
            s = status.loc[j]
            parts.append(
                f'<span><span class="dot" style="background:{COUNTRY_ACCENT[j]}"></span>'
                f'<b>{NAMES[j]}</b> · {_plural(int(s["documents"]), "document")} · '
                f'{int(s["with_text"] or 0):,} with text · '
                f'{_plural(int(s["provisions"]), "clause")}</span>')
    st.markdown(f'<div class="ws-status">{"".join(parts)}</div>', unsafe_allow_html=True)


# --- Compare: clause explorer ---------------------------------------------------

def render_clause_explorer(conn, country: str, category_id: str,
                           others: list[str] | None = None) -> None:
    """Three panes: clause list · selected clause · equivalents per country."""
    others = others or [j for j in J if j != country]
    rows = queries.clauses(conn, country, category_id,
                           query=st.session_state.get("ws_clause_query", ""))
    other_has_text = {j: queries.has_text_in_category(conn, j, category_id)
                      for j in others}

    left, mid, right = st.columns([3, 3.6, 3.6], gap="medium")
    with left:
        st.markdown(pane_head(f"{NAMES[country]} clauses", country=country,
                              count=_plural(len(rows), "clause")),
                    unsafe_allow_html=True)
        st.text_input("Filter clauses", "", key="ws_clause_query",
                      placeholder="e.g. notify, exit strategy, 24 hours",
                      label_visibility="collapsed")
        if rows.empty:
            docs = queries.category_documents(conn, category_id, country)
            if st.session_state.get("ws_clause_query", "").strip():
                msg = "No clauses match this filter."
            elif docs.empty:
                msg = (f"{NAMES[country]} has no documents mapped to this category.")
            else:
                msg = (f"{NAMES[country]} has {_plural(len(docs), 'document')} in this "
                       "category, but their text isn't indexed yet. Run "
                       "<code>python orm_pipeline.py build --fetch</code>.")
            st.markdown(notice(msg), unsafe_allow_html=True)
            return

        ids = rows["provision_id"].tolist()
        key = f"ws_selected_{country}_{category_id}"
        if st.session_state.get(key) not in ids:
            st.session_state[key] = ids[0]
        selected_id = st.session_state[key]
        with st.container(height=640, border=False):
            for _doc_id, group in rows.groupby("document_id", sort=False):
                first = group.iloc[0]
                st.markdown(f'<div class="ws-doc-group"><span class="ref">'
                            f'{_e(first["doc_ref"])}</span>{_e(first["doc_title"])}</div>',
                            unsafe_allow_html=True)
                for _, c in group.iterrows():
                    pid = int(c["provision_id"])
                    n = int(c["matches"])
                    if n:
                        state = _plural(n, "equivalent")
                    elif any(other_has_text.values()):
                        state = "possible gap"
                    else:
                        state = "not assessed"
                    label = f'{c["ref"] or "¶"}   {_short(c["text"], 90)}   ·  {state}'
                    label = re.sub(r"[*_`\[\]#<>$~|]", "", label)
                    if st.button(label, key=f"ws_clause_{pid}", width="stretch",
                                 type="primary" if pid == selected_id else "secondary"):
                        st.session_state[key] = pid
                        st.rerun()

    clause = queries.clause(conn, selected_id)
    with mid:
        st.markdown(pane_head("Selected clause"), unsafe_allow_html=True)
        attrs = queries.provision_attributes(conn, [selected_id]).get(selected_id, {})
        tags = "".join(f'<span class="tag">⏱ {_e(v)}</span>'
                       for v in attrs.get("deadline", []))
        tags += "".join(f'<span class="tag">↻ {_e(v)}</span>'
                        for v in attrs.get("frequency", []))
        checks = queries.provision_expectations(conn, selected_id)
        checklist = ("".join(f'<span class="tag">✓ {_e(x)}</span>' for x in checks)
                     if checks else "")
        st.markdown(
            f'<div class="ws-selected">{_cite(clause)}'
            f'<div class="law ws-scroll">'
            f'{_highlight(clause["text"], classify.matched_keywords(category_id, clause["text"]))}'
            f'</div><div>{tags}{checklist}</div></div>', unsafe_allow_html=True)

    with right:
        matches = queries.equivalents(conn, selected_id, category_id)
        for j in others:
            mj = matches[matches["jurisdiction"] == j]
            st.markdown(pane_head(f"Equivalent in {NAMES[j]}", country=j,
                                  count=_plural(len(mj), "suggestion") if len(mj) else ""),
                        unsafe_allow_html=True)
            if mj.empty:
                if not other_has_text[j]:
                    msg = (f"<b>Not assessed.</b> {NAMES[j]} has no indexed text in "
                           "this category yet, so it can't be compared.")
                    st.markdown(notice(msg), unsafe_allow_html=True)
                else:
                    msg = (f"<b>No comparable clause found in {NAMES[j]}.</b> "
                           "This may be a gap worth reviewing.")
                    st.markdown(notice(msg, "gap"), unsafe_allow_html=True)
                continue
            cards = []
            for _, m in mj.iterrows():
                strength = match.strength(m["score"])
                width = max(6, min(100, int(m["score"] * 160)))
                why = "".join(f'<span class="tag">✓ {_e(x)}</span>'
                              for x in m["shared_expectation_labels"])
                terms = (f'<div class="ws-why">Shared terms: {_e(m["shared_terms"])}</div>'
                         if m["shared_terms"] else "")
                cards.append(
                    f'<div class="ws-match"><div class="top">'
                    f'{pill(strength, STRENGTH_KIND[strength])}'
                    f'<div class="bar"><span style="width:{width}%"></span></div></div>'
                    f'{_cite(m)}<div class="law ws-scroll">{_highlight(m["text"], [])}</div>'
                    f'<div>{why}</div>{terms}</div>')
            st.markdown("".join(cards), unsafe_allow_html=True)
        st.caption("Suggested matches, ranked by text similarity and shared checklist "
                   "items within the same risk category. Confirm before relying on them.")


# --- Compare: full directive ----------------------------------------------------

_STATUS_TEXT = {
    "pending": "not read yet",
    "no_text": "no text available",
    "error": "reading failed",
}


def render_full_directive(conn, country: str, category_id: str) -> None:
    """Read one directive from start to finish -- every clause, in order,
    with the clauses tagged for the current risk category marked."""
    docs = queries.documents(conn, country)
    if docs.empty:
        st.markdown(notice(f"No {NAMES[country]} documents in the index."),
                    unsafe_allow_html=True)
        return

    unread = docs[docs["text_status"] != "ok"]
    if not unread.empty:
        reasons = "".join(
            f"<li>{_e(r['doc_ref'] or '')} {_e(r['doc_title'])} — "
            f"{_STATUS_TEXT.get(r['text_status'], r['text_status'])}"
            f"{': ' + _e(r['error']) if r['error'] else ''}</li>"
            for _, r in unread.head(60).iterrows())
        more = f"<li>… and {len(unread) - 60} more</li>" if len(unread) > 60 else ""
        st.markdown(notice(
            f'<b>{len(unread)} of {len(docs)} {NAMES[country]} documents have no text '
            'in the index, so they can\'t be compared yet.</b> Run '
            '<code>python orm_pipeline.py build --fetch</code>, or save the PDF '
            'into <code>orm_texts/manual/</code> named after the document id.'
            f'<details><summary>Show which</summary><ul>{reasons}{more}</ul></details>',
            "warn"), unsafe_allow_html=True)

    read = docs[docs["text_status"] == "ok"]
    if read.empty:
        return
    labels = {r["document_id"]: (f"{r['doc_ref'] + ' · ' if r['doc_ref'] else ''}"
                                 f"{r['doc_title']}  ({int(r['provisions'])} clauses)")
              for _, r in read.iterrows()}
    c1, c2 = st.columns([4, 1.4], vertical_alignment="bottom")
    with c1:
        doc_id = st.selectbox("Document", list(labels), format_func=labels.get,
                              key=f"ws_read_doc_{country}")
    with c2:
        only_tagged = st.toggle("Only this category", value=False,
                                key=f"ws_read_only_{country}")
    doc = read[read["document_id"] == doc_id].iloc[0]
    provs = queries.document_provisions(conn, doc_id)

    chars = int(doc["chars"] or 0)
    kept = int(doc["provision_chars"] or 0)
    pages = f"{int(doc['pages'])} pages · " if pd.notna(doc["pages"]) and doc["pages"] else ""
    coverage = f" · {min(100, round(100 * kept / chars))}% of the text kept" if chars else ""
    tagged_here = provs["categories"].str.split(",").apply(
        lambda cs: category_id in cs).sum()
    link = _link(doc)
    link_html = (f' · <a href="{_e(link)}" target="_blank">Open in source ↗</a>'
                 if link else "")
    st.markdown(
        f'<div class="ws-read-meta">{pages}{len(provs)} clauses{coverage} · '
        f'{int(doc["tagged"])} tagged with any risk category · {tagged_here} with '
        f'<b>{_e(taxonomy.BY_ID[category_id].name)}</b>{link_html}</div>',
        unsafe_allow_html=True)

    blocks = []
    for _, p in provs.iterrows():
        cats = [c for c in p["categories"].split(",") if c]
        in_cat = category_id in cats
        if only_tagged and not in_cat:
            continue
        chips = "".join(f'<span class="tag">{_e(taxonomy.BY_ID[c].name)}</span>'
                        for c in cats if c in taxonomy.BY_ID)
        terms = classify.matched_keywords(category_id, p["text"]) if in_cat else []
        blocks.append(
            f'<div class="ws-read{" tagged" if in_cat else ""}">'
            f'<div class="law"><span class="ref">{_e(p["ref"] or "¶")}</span>'
            f'{_highlight(p["text"], terms)}</div><div>{chips}</div></div>')
    with st.container(height=720, border=False):
        st.markdown("".join(blocks) or notice("No clauses."), unsafe_allow_html=True)


# --- Compare: all clauses side by side ------------------------------------------

def render_jurisdiction_column(conn, category_id: str, j: str, query: str) -> None:
    docs = queries.category_documents(conn, category_id, j)
    st.markdown(pane_head(NAMES[j], country=j, count=_plural(len(docs), "document")),
                unsafe_allow_html=True)
    if docs.empty:
        st.markdown(notice(f"No {NAMES[j]} documents are mapped to this category."),
                    unsafe_allow_html=True)
        return

    items = []
    for _, d in docs.iterrows():
        status = (pill("Text indexed", "found") if d["text_status"] == "ok"
                  else pill("Title only", "na"))
        date = f" · {d['date'][:10]}" if d["date"] else ""
        link = _link(d)
        open_link = (f' <a href="{_e(link)}" target="_blank">Open in source ↗</a>'
                     if link else "")
        items.append(f'<tr><td><b>{_e(d["ref"])}</b> {_e(d["title"])}{open_link}'
                     f'<div class="sub">matched by {_e(d["evidence"])}{date}</div></td>'
                     f'<td>{status}</td></tr>')
    with st.expander(f"Documents in this category ({len(docs)})", expanded=False):
        st.markdown(f'<table class="ws-table"><tbody>{"".join(items)}</tbody></table>',
                    unsafe_allow_html=True)

    provs = queries.category_provisions(conn, category_id, j, query=query)
    if provs.empty:
        has_text = (docs["text_status"] == "ok").any()
        msg = ("No clauses match this search." if query.strip() and has_text else
               "<b>Not assessed.</b> These documents are mapped from their titles, but "
               "their text isn't indexed yet. Run "
               "<code>python orm_pipeline.py build --fetch</code>.")
        st.markdown(notice(msg), unsafe_allow_html=True)
        return

    terms = query.split()
    cards = []
    for _, p in provs.iterrows():
        ev_terms = classify.matched_keywords(category_id, p["text"])
        chips = "".join(f'<span class="tag">⏱ {_e(v)}</span>' for v in p["deadlines"])
        chips += "".join(f'<span class="tag">↻ {_e(v)}</span>' for v in p["frequencies"])
        if p["reviewed"] == 1:
            chips += pill("Confirmed", "found")
        cards.append(
            f'<div class="ws-prov">{_cite({**p, "jurisdiction": j})}'
            f'<div class="law ws-scroll">{_highlight(p["text"], terms + ev_terms)}</div>'
            f'<div>{chips}</div></div>')
    st.markdown("".join(cards), unsafe_allow_html=True)


# --- Coverage -------------------------------------------------------------------

def _cell(row, j: str) -> str:
    level = row[f"{j}_level"]
    docs, text_docs, provs = row[f"{j}_docs"], row[f"{j}_docs_text"], row[f"{j}_provisions"]
    label, kind = LEVEL[level]
    if level == "none":
        main, sub = "—", ""
    elif level == "metadata":
        main = _plural(docs, "document")
        sub = "no text indexed yet"
    else:
        main = _plural(provs, "clause")
        sub = (f"{text_docs} of {_plural(docs, 'document')} with text" if docs
               else "found inside documents filed under other topics")
    latest = row[f"{j}_latest"]
    if latest and level != "none":
        sub = f"{sub} · latest {latest[:10]}" if sub else f"latest {latest[:10]}"
    return (f'{pill(label, kind)}<div class="n" style="margin-top:4px">{_e(main)}</div>'
            f'<div class="sub">{_e(sub)}</div>')


def render_matrix(matrix, countries: list[str] | None = None) -> None:
    countries = countries or list(J)
    head = "".join(f'<th><span class="dot" style="display:inline-block;width:7px;'
                   f'height:7px;border-radius:50%;margin-right:6px;'
                   f'background:{COUNTRY_ACCENT[j]}"></span>{NAMES[j]}</th>'
                   for j in countries)
    body = []
    for _, row in matrix.iterrows():
        tag = "ORM core" if row["orm_core"] else "Prudential / other"
        cells = "".join(f"<td>{_cell(row, j)}</td>" for j in countries)
        body.append(f'<tr><td class="cat">{_e(row["name"])}<small>{tag}</small></td>'
                    f'{cells}</tr>')
    st.markdown(
        f'<table class="ws-table"><thead><tr><th>Risk category</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
        f'<div class="ws-legend"><span>{pill("Clauses indexed", "found")} text read and '
        f'tagged</span><span>{pill("Titles only", "partial")} mapped from document '
        f'titles, text not indexed yet</span><span>{pill("No coverage", "na")} no '
        'document mapped</span></div>', unsafe_allow_html=True)


# --- Gaps -----------------------------------------------------------------------

def render_gap_table(conn, category_id: str, countries: list[str] | None = None) -> None:
    countries = countries or list(J)
    cat = taxonomy.BY_ID[category_id]
    if not cat.expectations:
        st.markdown(notice("No baseline checklist is defined for this category yet. "
                           "Gap analysis covers the ORM core categories."),
                    unsafe_allow_html=True)
        return
    table = queries.expectation_table(conn, category_id)
    head = "".join(f"<th>{NAMES[j]}</th>" for j in countries)
    rows = []
    for _, r in table.iterrows():
        cells = []
        for j in countries:
            label, kind = STATUS[r[f"{j}_status"]]
            ev = ""
            if r[f"{j}_status"] == "found":
                ev = (f'<div class="ev"><b>{_e(REGULATORS.get(j, ""))} · '
                      f'{_e(r[f"{j}_source"])}</b> — {_e(_short(r[f"{j}_evidence"], 200))}'
                      '</div>')
            cells.append(f'<td>{pill(label, kind)}{ev}</td>')
        rows.append(f'<tr><td class="cat">{_e(r["expectation"])}</td>{"".join(cells)}</tr>')
    st.markdown(
        f'<table class="ws-table"><thead><tr><th>Baseline expectation</th>{head}</tr>'
        f'</thead><tbody>{"".join(rows)}</tbody></table>', unsafe_allow_html=True)
    st.caption("Detected from the full text of each country's documents. “Not assessed” "
               "means no text is indexed yet for that country in this category, which "
               "is not the same as a gap. Treat every result as a lead for review.")
    export = table.copy()
    export.insert(0, "category", cat.name)
    st.download_button("Export gaps (CSV)", export.to_csv(index=False).encode("utf-8"),
                       f"gaps_{category_id}.csv", "text/csv", key="ws_gaps_export")


# --- Deadlines ------------------------------------------------------------------

def render_deadlines(conn, category_id: str | None,
                     countries: list[str] | None = None) -> None:
    countries = countries or list(J)
    df = queries.deadlines(conn, category_id)
    df = df[df["jurisdiction"].isin(countries)]
    if df.empty:
        st.markdown(notice("No deadlines found in the indexed text for this scope."),
                    unsafe_allow_html=True)
        return
    df = df.assign(country=df["jurisdiction"].map(NAMES),
                   source=(df["doc_ref"].fillna("") + " " + df["ref"].fillna("")).str.strip(),
                   context=df["text"].map(lambda t: _short(t, 220)))
    out = df[["country", "value_text", "hours", "source", "doc_title", "context"]]
    st.dataframe(
        out, hide_index=True, width="stretch",
        column_config={"country": "Country",
                       "value_text": "Deadline as written",
                       "hours": st.column_config.NumberColumn("≈ hours", format="%.0f"),
                       "source": "Clause",
                       "doc_title": "Document",
                       "context": "Context"})
    st.download_button("Export deadlines (CSV)", out.to_csv(index=False).encode("utf-8"),
                       "deadlines.csv", "text/csv", key="ws_deadlines_export")


# --- Changes --------------------------------------------------------------------

def _latest_report() -> tuple[str, str] | None:
    path = os.path.join(REPORT_DIR, "latest.txt")
    if not os.path.exists(path):
        return None
    when = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    with open(path, encoding="utf-8") as f:
        return when, f.read()


def render_changes(conn, countries: list[str]) -> None:
    report = _latest_report()
    if report:
        when, text = report
        with st.expander(f"Latest automatic update · {when}", expanded=True):
            st.markdown(f'<div class="ws-report">{_e(text)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(notice("No automatic update has run on this computer yet. Run "
                           "<code>./update.sh</code> to collect new and amended "
                           "regulations; the summary will appear here."),
                    unsafe_allow_html=True)

    default_since = dt.date.today() - dt.timedelta(days=90)
    since = st.date_input("Published or updated since", value=default_since,
                          key="ws_changes_since")
    since = since or default_since
    df = queries.changes_since(conn, since.isoformat(), tuple(countries))
    if df.empty:
        st.markdown(notice(f"No documents in this scope were published or updated "
                           f"since {since.isoformat()}."), unsafe_allow_html=True)
        return
    df = df.assign(country=df["jurisdiction"].map(NAMES),
                   date=df["changed"].str.slice(0, 10),
                   text=df["text_status"].map(
                       lambda s: "Indexed" if s == "ok" else "Not indexed yet"),
                   link=df["pdf_url"].fillna("").where(df["pdf_url"].fillna("") != "",
                                                       df["url"].fillna("")))
    st.markdown(f"**{len(df):,}** documents changed since {since.isoformat()}.")
    st.dataframe(
        df[["date", "country", "doc_ref", "doc_title", "categories", "text", "link"]],
        hide_index=True, width="stretch",
        column_config={"date": "Date", "country": "Country", "doc_ref": "Ref",
                       "doc_title": "Document", "categories": "Risk categories",
                       "text": "Text",
                       "link": st.column_config.LinkColumn("Source",
                                                           display_text="Open ↗")})


# --- pages (registered in the left rail by app.py) --------------------------------

def page_compare(path: str | None = None) -> None:
    page_header("Compare", "Pick a clause; its equivalents in the other countries "
                "appear beside it, with citations.")
    with _open(path) as conn:
        render_status(conn)
        scope = scope_bar(conn, "compare")
        clauses, full, side = st.tabs(["Clauses", "Full document", "All clauses side by side"])
        with clauses:
            render_clause_explorer(conn, scope["country"], scope["category"],
                                   scope["compare"])
        with full:
            render_full_directive(conn, scope["country"], scope["category"])
        with side:
            query = st.text_input("Search clauses in this category", "",
                                  placeholder="e.g. notify, outsourcing, 24 hours",
                                  key="ws_side_query")
            shown = [scope["country"], *scope["compare"]]
            for col, j in zip(st.columns(len(shown), gap="medium"), shown):
                with col:
                    render_jurisdiction_column(conn, scope["category"], j, query)


def page_coverage(path: str | None = None) -> None:
    page_header("Coverage", "How much each country regulates each risk area, and how "
                "much of it is indexed.")
    with _open(path) as conn:
        render_status(conn)
        orm_only = st.toggle("ORM core only", value=st.session_state.get("scope_core", True),
                             key="coverage_core")
        st.session_state["scope_core"] = orm_only
        matrix = queries.coverage_matrix(conn, orm_only=orm_only)
        render_matrix(matrix)
        c1, c2, c3, c4 = st.columns([1.3, 3, 1.2, 1.4], vertical_alignment="bottom")
        with c1:
            country = st.selectbox("Country", list(J), format_func=NAMES.get,
                                   key="coverage_open_country")
        with c2:
            cat_ids = matrix["category_id"].tolist()
            cat = st.selectbox("Risk category", cat_ids, key="coverage_open_category",
                               format_func=lambda c: taxonomy.BY_ID[c].name)
        with c3:
            if st.button("Open in Compare", type="primary", width="stretch") and PAGES:
                st.session_state["scope_country"] = country
                st.session_state["scope_category"] = cat
                st.switch_page(PAGES["compare"])
        with c4:
            st.download_button("Export matrix (CSV)",
                               matrix.to_csv(index=False).encode("utf-8"),
                               "risk_coverage_matrix.csv", "text/csv", width="stretch")


def page_gaps(path: str | None = None) -> None:
    page_header("Gaps", "Baseline expectations for one risk category: found, not found, "
                "or not assessed in each country.")
    with _open(path) as conn:
        scope = scope_bar(conn, "gaps")
        render_gap_table(conn, scope["category"], [scope["country"], *scope["compare"]])


def page_deadlines(path: str | None = None) -> None:
    page_header("Deadlines", "Reporting deadlines found in the text, converted to hours "
                "so countries can be compared.")
    with _open(path) as conn:
        scope = scope_bar(conn, "deadlines")
        every = st.toggle("All risk categories", value=False, key="deadlines_all")
        render_deadlines(conn, None if every else scope["category"],
                         [scope["country"], *scope["compare"]])


def page_changes(path: str | None = None) -> None:
    page_header("Changes", "New and amended regulations, and the summary of the latest "
                "automatic update.")
    with _open(path) as conn:
        render_status(conn)
        render_changes(conn, list(J))


def render_risk_compare_section(path: str | None = None) -> None:
    """Every workspace screen on one page (used by tests and as a fallback)."""
    for page in (page_compare, page_coverage, page_gaps, page_deadlines, page_changes):
        page(path)
