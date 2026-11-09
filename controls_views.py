"""The controls workspace: Obligations, Controls and Audit readiness.

Regulation -> obligation -> control -> evidence. Obligations and control
suggestions come from the index (orm.obligations, rebuilt on every deploy);
what people decide -- reviews, the bank's own controls -- is kept in the
state store (orm.state) with a full change log. Logic lives in orm/; this
file only renders. Look and wording follow DESIGN.md.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import streamlit as st

import orm_compare
from orm import audit, controls as control_lib, obligations, state, taxonomy
from ui_theme import e as _e, notice, page_header

PAGES: dict = {}
NAMES = audit.NAMES
NEEDS_NEW = "— needs a new control —"
CORE = [c.id for c in taxonomy.CATEGORIES if c.orm_core]


# --- shared ----------------------------------------------------------------------

def _open():
    """Index connection (built if missing), with obligations ready."""
    ctx = orm_compare._open(None)
    conn = ctx.__enter__()
    obligations.init(conn)
    has_obl = conn.execute("SELECT COUNT(*) FROM obligation").fetchone()[0]
    has_text = conn.execute("SELECT COUNT(*) FROM provision").fetchone()[0]
    if not has_obl and has_text:
        with st.spinner("Reading obligations from the indexed regulations…"):
            obligations.build_all(conn)
            conn.commit()
    return ctx, conn


def _reviewer() -> str:
    return st.session_state.get("reviewer_name", "").strip()


def _reviewer_box(key: str) -> str:
    name = st.text_input("Your name (recorded with every change)",
                         value=st.session_state.get("reviewer_name", ""), key=key,
                         placeholder="e.g. Oriya Baraness")
    st.session_state["reviewer_name"] = name
    return name.strip()


def _control_label(cid: str) -> str:
    c = control_lib.BY_ID.get(cid)
    return f"{c.id} · {c.name}" if c else NEEDS_NEW


def _storage_note() -> None:
    st.caption("Reviews, uploaded controls and the change log are stored on the "
               "server in orm_state.db. Until it is moved to permanent storage "
               "(action plan task 5.2), a redeploy can reset them: export the audit "
               "pack to keep a copy.")


def _scope(conn, page: str) -> dict:
    return orm_compare.scope_bar(conn, page, compare=False)


# --- Obligations -------------------------------------------------------------------

def page_obligations() -> None:
    page_header("Obligations", "Every duty the regulation imposes, as a checklist "
                "item: who must do what, by when, and the evidence to keep. Approve, "
                "correct or reject each one.")
    ctx, conn = _open()
    try:
        scope = _scope(conn, "obligations")
        with state.session() as s:
            reviews = state.reviews(s)
        df = audit.obligation_table(conn, reviews, jurisdiction=scope["country"],
                                    category_id=scope["category"])
        if df.empty:
            st.markdown(notice(f"No obligations found for {NAMES[scope['country']]} in "
                               "this category. Either its text isn't indexed, or no "
                               "sentence uses shall, must or should."),
                        unsafe_allow_html=True)
            return
        docs = (df.drop_duplicates("document_id")
                .assign(label=lambda d: d["doc_ref"].fillna("") + " · " + d["doc_title"])
                [["document_id", "label"]])
        c1, c2, c3 = st.columns([3, 2, 2], vertical_alignment="bottom")
        with c1:
            doc = st.selectbox("Document", ["all"] + docs["document_id"].tolist(),
                               format_func=lambda d: "All documents" if d == "all" else
                               docs.set_index("document_id").at[d, "label"].strip(" ·"),
                               key="obl_doc")
        with c2:
            shown = st.multiselect("Status", ["Unreviewed", "Approved", "Rejected"],
                                   default=["Unreviewed", "Approved"], key="obl_status")
        with c3:
            query = st.text_input("Search", "", key="obl_query",
                                  placeholder="e.g. notify, test, board")
        view = df
        if doc != "all":
            view = view[view["document_id"] == doc]
        if shown:
            view = view[view["status"].isin(shown)]
        if query.strip():
            q = query.strip().lower()
            view = view[view["action"].str.lower().str.contains(q, regex=False)
                        | view["sentence"].str.lower().str.contains(q, regex=False)]

        counts = df["status"].value_counts()
        mapped = int((df["control_id"].fillna("") != "").sum())
        st.markdown(
            f'<div class="ws-status"><span><b>{len(df):,}</b> obligations</span>'
            f'<span>{int(counts.get("Approved", 0)):,} approved</span>'
            f'<span>{int(counts.get("Unreviewed", 0)):,} unreviewed</span>'
            f'<span>{int(counts.get("Rejected", 0)):,} rejected</span>'
            f'<span>{mapped:,} with a control</span></div>', unsafe_allow_html=True)

        if view.empty:
            st.markdown(notice("No obligations match these filters."),
                        unsafe_allow_html=True)
            return
        options = [_control_label(c.id) for c in control_lib.for_category(scope["category"])]
        options += [_control_label(c.id) for c in control_lib.LIBRARY
                    if c.category_id != scope["category"]]
        options.append(NEEDS_NEW)
        table = pd.DataFrame({
            "status": view["status"].to_numpy(),
            "control": view["control_id"].fillna("").map(_control_label).to_numpy(),
            "actor": view["actor"].fillna("").to_numpy(),
            "action": view["action"].to_numpy(),
            "deadline": view["deadline_text"].fillna("").to_numpy(),
            "frequency": view["frequency"].fillna("").to_numpy(),
            "evidence": view["evidence"].fillna("").to_numpy(),
            "source": view["citation"].to_numpy(),
            "link": view["link"].fillna("").to_numpy(),
            "suggested": view["control_source"].map(
                {"reviewer": "Reviewer", "suggested": "Suggested", "": ""}).to_numpy(),
        }, index=pd.Index(view["okey"].to_numpy(), name="okey"))
        edited = st.data_editor(
            table, key=f"obl_editor_{scope['country']}_{scope['category']}_{doc}",
            hide_index=True, width="stretch", height=560,
            disabled=["actor", "deadline", "frequency", "evidence", "source", "link",
                      "suggested"],
            column_config={
                "status": st.column_config.SelectboxColumn(
                    "Status", options=["Unreviewed", "Approved", "Rejected"],
                    required=True, width="small"),
                "control": st.column_config.SelectboxColumn(
                    "Control", options=options, required=True, width="medium"),
                "actor": st.column_config.TextColumn("Who", width="small"),
                "action": st.column_config.TextColumn("Must do (edit to correct)",
                                                      width="large"),
                "deadline": "Deadline", "frequency": "Frequency",
                "evidence": st.column_config.TextColumn("Evidence to keep", width="medium"),
                "source": st.column_config.TextColumn("Source", width="medium"),
                "link": st.column_config.LinkColumn("Open", display_text="source ↗",
                                                    width="small"),
                "suggested": st.column_config.TextColumn("Control set by", width="small"),
            })
        changed = _changes(table, edited, view)
        c1, c2, c3 = st.columns([2.2, 1.4, 1.6], vertical_alignment="bottom")
        with c1:
            name = _reviewer_box("obl_reviewer")
        with c2:
            save = st.button(f"Save {len(changed)} change(s)" if changed else "Save changes",
                             type="primary", disabled=not changed, width="stretch")
        with c3:
            st.download_button(
                "Export (CSV)", audit.pack_frame(view.assign(
                    bank_control="", bank_owner="", coverage="")).to_csv(index=False)
                .encode("utf-8"), f"obligations_{scope['country']}_{scope['category']}.csv",
                "text/csv", width="stretch")
        if save:
            if not name:
                st.error("Enter your name first: every decision is recorded with who made it.")
            else:
                with state.session() as s:
                    for okey, change in changed.items():
                        state.save_review(s, okey, reviewer=name, **change)
                st.success(f"Saved {len(changed)} change(s).")
                st.rerun()
        st.caption("Obligations are read from sentences using shall, must or should; "
                   "controls are suggested from the starter library. Both are leads "
                   "until a reviewer approves them. Rejected obligations are left out "
                   "of coverage and the audit pack.")
        _storage_note()
    finally:
        ctx.__exit__(None, None, None)


def _changes(before: pd.DataFrame, after: pd.DataFrame, view: pd.DataFrame) -> dict:
    """Rows the reviewer changed -> arguments for state.save_review."""
    label_to_id = {_control_label(c.id): c.id for c in control_lib.LIBRARY}
    label_to_id[NEEDS_NEW] = ""
    original = view.set_index("okey")["original_action"]
    out = {}
    for okey in after.index:
        a, b = after.loc[okey], before.loc[okey]
        if (a["status"], a["control"], a["action"]) == (b["status"], b["control"], b["action"]):
            continue
        status = state.STATUS_CODE.get(a["status"], 0)
        if status == 0 and (a["control"] != b["control"] or a["action"] != b["action"]):
            status = 1   # editing a row is a review of it
        out[okey] = {
            "status": status,
            "control_id": label_to_id.get(a["control"], ""),
            "action_edit": a["action"] if a["action"] != original.get(okey) else "",
        }
    return out


# --- Controls ----------------------------------------------------------------------

def page_controls() -> None:
    page_header("Controls", "The control library, which obligations each control "
                "answers, and the chain from regulation to evidence for any directive.")
    ctx, conn = _open()
    try:
        with state.session() as s:
            reviews = state.reviews(s)
        library, chain = st.tabs(["Control library", "Regulation → control → evidence"])
        with library:
            _render_library(conn, reviews)
        with chain:
            _render_chain(conn, reviews)
    finally:
        ctx.__exit__(None, None, None)


def _render_library(conn, reviews) -> None:
    cat = st.selectbox("Risk category", CORE, key="ctl_category",
                       format_func=lambda c: taxonomy.BY_ID[c].name)
    df = audit.obligation_table(conn, reviews, category_id=cat)
    live = df[df["status"] != "Rejected"] if not df.empty else df
    rows = []
    for c in control_lib.for_category(cat):
        row = {"control": f"{c.id} · {c.name}", "what it does": c.description,
               "frequency": c.frequency, "evidence": c.evidence}
        for j in NAMES:
            n = int(((live["control_id"] == c.id) & (live["jurisdiction"] == j)).sum()) \
                if not live.empty else 0
            row[NAMES[j]] = n
        rows.append(row)
    gap = {"control": NEEDS_NEW, "what it does": "Obligations no library control answers. "
           "Each needs a bank control written for it.", "frequency": "", "evidence": ""}
    for j in NAMES:
        gap[NAMES[j]] = int(((live["control_id"].fillna("") == "") &
                             (live["jurisdiction"] == j)).sum()) if not live.empty else 0
    rows.append(gap)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={NAMES[j]: st.column_config.NumberColumn(
                     f"{NAMES[j]} obligations", width="small") for j in NAMES})
    st.caption("Counts are obligations mapped to each control: a reviewer's choice "
               "where there is one, otherwise the suggestion. The library is a "
               "starting point written for this tool; upload your own controls under "
               "Audit readiness to see how your control set covers the rules.")


def _render_chain(conn, reviews) -> None:
    c1, c2 = st.columns([1.2, 4], vertical_alignment="bottom")
    with c1:
        country = st.selectbox("Country", list(NAMES), format_func=NAMES.get,
                               key="chain_country")
    df = audit.obligation_table(conn, reviews, jurisdiction=country)
    if df.empty:
        st.markdown(notice(f"No obligations indexed for {NAMES[country]} yet."),
                    unsafe_allow_html=True)
        return
    docs = (df.groupby(["document_id", "doc_ref", "doc_title"], dropna=False)
            .size().reset_index(name="n"))
    docs["label"] = docs.apply(lambda r: f"{r['doc_ref'] or ''} · {r['doc_title']} "
                               f"({r['n']} obligations)".strip(" ·"), axis=1)
    default = next((i for i, d in enumerate(docs["document_id"])
                    if d.endswith("-310")), 0)
    with c2:
        doc = st.selectbox("Directive", docs["document_id"].tolist(), index=default,
                           format_func=docs.set_index("document_id")["label"].get,
                           key=f"chain_doc_{country}")
    view = df[(df["document_id"] == doc) & (df["status"] != "Rejected")]
    approved = int((view["status"] == "Approved").sum())
    no_ctl = int((view["control_id"].fillna("") == "").sum())
    st.markdown(
        f'<div class="ws-status"><span><b>{len(view)}</b> obligations</span>'
        f'<span>{approved} approved</span>'
        f'<span>{len(view) - no_ctl} mapped to a control</span>'
        f'<span>{no_ctl} need a new control</span></div>', unsafe_allow_html=True)
    blocks = []
    for _, r in view.iterrows():
        ctl = control_lib.BY_ID.get(r["control_id"] or "")
        ctl_html = (f'<b>{_e(ctl.id)} · {_e(ctl.name)}</b><br>'
                    f'<span class="muted">{_e(ctl.frequency)}</span>'
                    if ctl else '<span class="pill gap">needs a new control</span>')
        state_pill = ('<span class="pill found">approved</span>'
                      if r["status"] == "Approved" else
                      '<span class="pill na">suggested</span>' if ctl else "")
        who = f"<b>{_e(r['actor'])}</b>: " if r["actor"] else ""
        timing = " · ".join(x for x in (r["deadline_text"], r["frequency"]) if x)
        blocks.append(
            f'<tr><td class="cat">{_e(r["clause_ref"] or "")}</td>'
            f'<td>{who}{_e(r["action"])}'
            f'{"<br><span class=muted>" + _e(timing) + "</span>" if timing else ""}</td>'
            f'<td>{ctl_html} {state_pill}</td><td>{_e(r["evidence"])}</td></tr>')
    st.markdown(
        '<table class="ws-table"><thead><tr><th>Clause</th><th>Obligation</th>'
        '<th>Control</th><th>Evidence to keep</th></tr></thead><tbody>'
        + "".join(blocks) + "</tbody></table>", unsafe_allow_html=True)
    st.caption("Change a mapping or approve an obligation on the Obligations screen.")


# --- Audit readiness ------------------------------------------------------------------

TEMPLATE = pd.DataFrame([
    {"ref": "C-001", "name": "Annual business continuity test",
     "description": "BCP and disaster recovery plans are tested every year; results "
                    "and remediation actions are reported to the risk committee.",
     "owner": "Head of Operational Resilience", "frequency": "Annual",
     "category": "Operational risk & resilience"},
    {"ref": "C-002", "name": "Regulatory incident notification",
     "description": "Significant operational incidents are reported to the "
                    "supervisor within the required deadline.",
     "owner": "Chief Risk Officer", "frequency": "Per incident",
     "category": "Incident & event reporting"},
])


def page_audit() -> None:
    page_header("Audit readiness", "Load your bank's controls, see which obligations "
                "they cover, and export an audit pack with every citation and review.")
    ctx, conn = _open()
    try:
        yours, cov_tab, pack_tab, history = st.tabs(
            ["Your controls", "Coverage", "Audit pack", "History"])
        with yours:
            _render_upload()
        with state.session() as s:
            reviews = state.reviews(s)
            bank = state.bank_controls(s)
            log = state.log_entries(s)
        with cov_tab:
            _render_coverage(conn, reviews, bank)
        with pack_tab:
            _render_pack(conn, reviews, bank, log)
        with history:
            _render_history(conn, log)
    finally:
        ctx.__exit__(None, None, None)


def _render_upload() -> None:
    with state.session() as s:
        current = state.bank_controls(s)
    st.markdown("Upload your control list as Excel or CSV. Columns used: **name** "
                "(or **description**), and if you have them **ref**, **owner**, "
                "**frequency** and **category** (one of the risk categories).")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download a template (CSV)",
                           TEMPLATE.to_csv(index=False).encode("utf-8"),
                           "clausewiz_controls_template.csv", "text/csv",
                           width="stretch")
    up = st.file_uploader("Control list", type=["xlsx", "xls", "csv"],
                          key="bank_upload")
    if up is not None:
        try:
            df = (pd.read_csv(up) if up.name.lower().endswith(".csv")
                  else pd.read_excel(up))
        except Exception as exc:  # bad file: say so, don't crash
            st.error(f"Could not read that file: {exc}")
            return
        rows, problems = state.normalize_controls(df)
        for p in problems[:10]:
            st.warning(p)
        if rows:
            st.markdown(f"**{len(rows)}** controls read from {up.name}:")
            st.dataframe(pd.DataFrame(rows).assign(
                category=lambda d: d["category_id"].map(
                    lambda c: taxonomy.BY_ID[c].name if c in taxonomy.BY_ID else "any")),
                hide_index=True, width="stretch",
                column_order=["ref", "name", "description", "owner", "frequency",
                              "category"])
            name = _reviewer_box("upload_reviewer")
            replace = (f"Replace the {len(current)} saved controls"
                       if current else "Save these controls")
            if st.button(replace, type="primary", disabled=not name):
                with state.session() as s:
                    state.replace_bank_controls(s, rows, name)
                st.success(f"Saved {len(rows)} controls.")
                st.rerun()
    if current:
        st.markdown(f"**Saved controls:** {len(current)} "
                    f"(uploaded {current[0]['uploaded_at'][:16].replace('T', ' ')} UTC"
                    f"{' by ' + current[0]['uploaded_by'] if current[0]['uploaded_by'] else ''})")
        st.dataframe(pd.DataFrame(current)[["ref", "name", "owner", "frequency",
                                            "category_id"]],
                     hide_index=True, width="stretch")
    else:
        st.markdown(notice("No controls saved yet. Coverage and the audit pack work "
                           "without them, but show every obligation as not covered."),
                    unsafe_allow_html=True)
    _storage_note()


def _scope_picker(key: str) -> tuple[str, list[str]]:
    c1, c2 = st.columns([1.2, 4], vertical_alignment="bottom")
    with c1:
        country = st.selectbox("Country", list(NAMES), format_func=NAMES.get,
                               key=f"{key}_country",
                               index=list(NAMES).index(
                                   st.session_state.get("audit_country", "IL")))
    with c2:
        cats = st.multiselect("Risk categories", CORE,
                              default=st.session_state.get("audit_cats", CORE),
                              format_func=lambda c: taxonomy.BY_ID[c].name,
                              key=f"{key}_cats") or CORE
    st.session_state["audit_country"], st.session_state["audit_cats"] = country, cats
    return country, cats


def _coverage_frame(conn, reviews, bank, country, cats, approved_only=False):
    df = audit.obligation_table(conn, reviews, jurisdiction=country)
    if df.empty:
        return df
    df = df[df["category_id"].isin(cats) & (df["status"] != "Rejected")]
    if approved_only:
        df = df[df["status"] == "Approved"]
    return audit.coverage(df, bank)


def _render_coverage(conn, reviews, bank) -> None:
    country, cats = _scope_picker("cov")
    cov = _coverage_frame(conn, reviews, bank, country, cats)
    if cov.empty:
        st.markdown(notice(f"No obligations for {NAMES[country]} in these categories."),
                    unsafe_allow_html=True)
        return
    if not bank:
        st.markdown(notice("Upload your controls under <b>Your controls</b> to see "
                           "coverage. Until then every obligation shows as not covered.",
                           "warn"), unsafe_allow_html=True)
    levels = cov["coverage"].value_counts()
    st.markdown(
        f'<div class="ws-status"><span><b>{len(cov):,}</b> obligations</span>'
        f'<span>{int(levels.get("covered", 0)):,} covered</span>'
        f'<span>{int(levels.get("partial", 0)):,} partly covered</span>'
        f'<span>{len(cov) - int(levels.get("covered", 0)) - int(levels.get("partial", 0)):,}'
        f' not covered</span></div>', unsafe_allow_html=True)
    st.dataframe(audit.coverage_summary(cov), hide_index=True, width="stretch")
    pick = st.segmented_control("Show", ["not covered", "partial", "covered"],
                                default="not covered", key="cov_show")
    show = cov[cov["coverage"].isin([pick] if pick else ["not covered"])] \
        if bank else cov
    st.dataframe(
        show[["category_id", "citation", "actor", "action", "control_name",
              "bank_control", "bank_owner", "coverage_score", "status", "link"]]
        .assign(category_id=lambda d: d["category_id"].map(
            lambda c: taxonomy.BY_ID[c].name)),
        hide_index=True, width="stretch", height=480,
        column_config={"category_id": "Category", "citation": "Source", "actor": "Who",
                       "action": st.column_config.TextColumn("Obligation", width="large"),
                       "control_name": "Library control",
                       "bank_control": "Your closest control", "bank_owner": "Owner",
                       "coverage_score": st.column_config.ProgressColumn(
                           "Match", min_value=0.0, max_value=0.6, format="%.2f"),
                       "status": "Review", "link": st.column_config.LinkColumn(
                           "Open", display_text="source ↗")})
    st.caption("Coverage compares the wording of your controls with each obligation. "
               "It points a reviewer at likely matches and likely gaps; it does not "
               "test whether a control works. Rejected obligations are left out.")


def _render_pack(conn, reviews, bank, log) -> None:
    country, cats = _scope_picker("pack")
    approved_only = st.toggle("Approved obligations only", value=False,
                              key="pack_approved")
    cov = _coverage_frame(conn, reviews, bank, country, cats, approved_only)
    if cov.empty:
        st.markdown(notice("Nothing in this scope yet" + (
            ": no obligations have been approved." if approved_only else ".")),
            unsafe_allow_html=True)
        return
    scope = (f"{NAMES[country]} · "
             + (", ".join(taxonomy.BY_ID[c].name for c in cats)
                if len(cats) < len(CORE) else "all ORM core categories")
             + (" · approved only" if approved_only else ""))
    approved = int((cov["status"] == "Approved").sum())
    st.markdown(f"**{len(cov):,}** obligations in the pack, **{approved:,}** approved by "
                f"a reviewer. Each row carries its source citation and link, the mapped "
                f"control, your closest control and owner, the evidence to keep, and who "
                f"reviewed it when.")
    stamp = dt.date.today().isoformat()
    base = f"clausewiz_audit_pack_{country}_{stamp}"
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download Excel pack",
                           audit.audit_pack_excel(cov, scope=scope, log=log),
                           f"{base}.xlsx",
                           "application/vnd.openxmlformats-officedocument."
                           "spreadsheetml.sheet", type="primary", width="stretch")
    with c2:
        st.download_button("Download PDF pack", audit.audit_pack_pdf(cov, scope=scope),
                           f"{base}.pdf", "application/pdf", width="stretch")
    st.caption(audit.NOTICE)


def _render_history(conn, log) -> None:
    st.markdown("**What was in place on a given date.** Pick a date to see the "
                "obligations approved and the controls chosen as of that day.")
    when = st.date_input("As of", value=dt.date.today(), key="hist_date")
    with state.session() as s:
        past = state.reviews_as_of(s, when.isoformat())
    approved = {k: v for k, v in past.items() if v["status"] == 1}
    if approved:
        df = audit.obligation_table(conn, approved)
        df = df[df["okey"].isin(approved)]
        st.markdown(f"**{len(df):,}** obligations approved as of {when.isoformat()}.")
        st.dataframe(df[["jurisdiction", "citation", "action", "control_name",
                         "reviewer", "reviewed_at"]]
                     .assign(jurisdiction=lambda d: d["jurisdiction"].map(NAMES)),
                     hide_index=True, width="stretch",
                     column_config={"jurisdiction": "Country", "citation": "Source",
                                    "action": "Obligation", "control_name": "Control",
                                    "reviewer": "Approved by",
                                    "reviewed_at": "When (UTC)"})
    else:
        st.markdown(notice(f"No obligations had been approved as of {when.isoformat()}."),
                    unsafe_allow_html=True)

    st.markdown("**Change log**, newest first.")
    if log:
        rows = []
        for r in log:
            d = json.loads(r["detail"] or "{}")
            what = (f"{state.STATUS_LABEL.get(d.get('status'), '')}"
                    f"{' · control ' + d['control_id'] if d.get('control_id') else ''}"
                    f"{' · wording edited' if d.get('action_edit') else ''}"
                    if r["action"] == "review" else f"{d.get('count', '')} controls")
            rows.append({"when": r["ts"][:19].replace("T", " "), "who": r["actor"],
                         "change": r["action"].replace("_", " "), "detail": what})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"when": "When (UTC)", "who": "Who",
                                    "change": "Change", "detail": "Detail"})
    else:
        st.markdown(notice("No changes recorded yet."), unsafe_allow_html=True)
    _storage_note()
