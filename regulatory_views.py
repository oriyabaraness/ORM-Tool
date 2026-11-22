"""Regulatory Intelligence workspace.

Source library → obligations → cross-jurisdiction comparison → applicability →
risk/control mapping. Logic lives in orm.regulatory_intel; this file only
renders. Look and wording follow DESIGN.md.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import controls_views
from orm import demo_data, regulatory_intel as ri, risk, state, taxonomy
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

APP_KIND = {
    "not_yet_assessed": "na",
    "potentially_applicable": "partial",
    "confirmed_applicable": "found",
    "confirmed_not_applicable": "gap",
    "requires_interpretation": "partial",
}
REL_KIND = {
    "Substantially aligned": "found",
    "Partially aligned": "partial",
    "Different scope": "partial",
    "Potentially conflicting": "gap",
    "No comparable requirement found": "gap",
    "Unable to determine": "na",
}
VAL_KIND = {
    "Validated": "found", "Approved": "found",
    "Suggested — needs review": "partial", "Unreviewed": "partial",
    "Rejected": "gap",
}

CSS = """
<style>
.ri-quote {font-family: var(--serif); font-size: 14.5px; line-height: 1.55;
  border-left: 3px solid var(--line); padding: 6px 0 6px 12px; margin: 6px 0;
  color: var(--ink); white-space: pre-wrap;}
.ri-interp {font-size: 13px; color: var(--ink-2); background: var(--subtle);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin: 6px 0;}
.ri-interp .tag {font-size: 11px; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: .04em; margin-bottom: 4px;}
.ri-kv {display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px;
  font-size: 13px; color: var(--ink-2); margin: 6px 0 10px;}
.ri-kv b {color: var(--ink); font-weight: 500;}
.ri-scroll {overflow-x: auto; max-width: 100%; -webkit-overflow-scrolling: touch;}
.ri-scroll .ws-table {min-width: 640px;}
.ri-pair {display: grid; grid-template-columns: 1fr 1fr; gap: 12px;}
@media (max-width: 640px) {
  .ri-pair {grid-template-columns: 1fr;}
}
</style>
"""


def _open_index():
    return controls_views._open()


def _banner() -> None:
    st.markdown(notice(
        "<b>Regulatory Intelligence.</b> Exact regulatory quotations are shown "
        "in the serif panels. Machine interpretations and risk suggestions are "
        "labelled separately and need a named reviewer before they are treated "
        "as validated. Semantic similarity is not legal equivalence.", "warn"),
        unsafe_allow_html=True)


def _kv(items: list[tuple[str, str]]) -> str:
    return '<div class="ri-kv">' + "".join(
        f"<span>{_e(k)}</span><b>{_e(v)}</b>" for k, v in items if v not in (None, "")
    ) + "</div>"


def _quote(text: str, citation: str = "", link: str = "",
           status: str = "") -> str:
    badge = pill(status, "found" if status.startswith("Verified") else
                 ("gap" if status == ri.UNVERIFIED_CITATION else "na")) if status else ""
    cite = f'<div class="cite">{_e(citation)}'
    if link:
        cite += f' · <a href="{_e(link)}" target="_blank" rel="noopener">Open source</a>'
    cite += f" {badge}</div>" if badge else "</div>"
    return f'{cite}<div class="ri-quote">{_e(text)}</div>'


def _interp(text: str) -> str:
    return (f'<div class="ri-interp"><div class="tag">Machine interpretation</div>'
            f'{_e(text)}<div class="tag" style="margin-top:6px">{_e(ri.INTERPRETATION_NOTE)}'
            f"</div></div>")


def _table(df: pd.DataFrame, cols: list[str]) -> str:
    use = [c for c in cols if c in df.columns]
    if not use or df.empty:
        return notice("No rows to show.")
    view = df[use].copy()
    html = view.to_html(index=False, classes="ws-table", border=0, escape=True)
    return f'<div class="ri-scroll">{html}</div>'


def page_regulatory_intelligence() -> None:
    page_header("Regulatory Intelligence",
                "From regulatory requirements to operational risk decisions")
    st.markdown(CSS, unsafe_allow_html=True)
    _banner()
    ctx, index = _open_index()
    try:
        with risk.session() as rconn:
            demo_data.seed(rconn, index)
            tabs = st.tabs([
                "A · Source library",
                "B · Obligations explorer",
                "C · Cross-jurisdiction comparison",
                "D · Applicability review",
                "E · Risk and control mapping",
            ])
            with tabs[0]:
                _panel_sources(index)
            with tabs[1]:
                _panel_obligations(index)
            with tabs[2]:
                _panel_compare(index)
            with tabs[3]:
                _panel_applicability(index, rconn)
            with tabs[4]:
                _panel_mapping(index, rconn)
    finally:
        ctx.__exit__(None, None, None)


# --- A ---------------------------------------------------------------------------

def _panel_sources(index) -> None:
    st.markdown(pane_head("Bank of Israel demo registry"), unsafe_allow_html=True)
    st.caption("Titles, URLs and publication dates come from the live index of "
               "official Bank of Israel pages. Version, effective date and "
               "supersession are marked Unverified when the index does not hold them.")
    demo = ri.demo_registry(index)
    st.markdown(_table(demo, [
        "document_id", "directive_number", "official_title", "publication_date",
        "effective_date", "document_version", "extraction_status", "obligations",
        "registry_status", "last_verification_date", "original_reference",
    ]), unsafe_allow_html=True)
    st.download_button("Export demo registry CSV",
                       ri.to_csv(demo, [
                           "document_id", "regulator", "jurisdiction", "official_title",
                           "directive_number", "publication_date", "effective_date",
                           "document_version", "source_url", "pdf_url",
                           "extraction_status", "file_checksum", "document_language",
                           "supersession_status", "last_verification_date",
                           "registry_status", "original_reference", "obligations"]),
                       file_name="regulatory_source_registry.csv", mime="text/csv",
                       key="ri_demo_csv")

    st.markdown(pane_head("Full source library"), unsafe_allow_html=True)
    jur = st.selectbox("Jurisdiction", ["All", "IL", "JO", "TR"], key="ri_src_jur")
    lib = ri.source_library(index)
    if jur != "All" and not lib.empty:
        lib = lib[lib["jurisdiction"] == jur]
    st.markdown(_table(lib, [
        "document_id", "jurisdiction", "regulator", "directive_number",
        "official_title", "publication_date", "extraction_status", "obligations",
        "verification_status", "original_reference",
    ]), unsafe_allow_html=True)
    st.markdown(notice(_e(ri.import_guidance())), unsafe_allow_html=True)
    if not lib.empty:
        st.download_button("Export source library CSV",
                           ri.to_csv(lib, [
                               "document_id", "regulator", "jurisdiction",
                               "official_title", "directive_number",
                               "publication_date", "effective_date",
                               "document_version", "source_url", "pdf_url",
                               "file_checksum", "upload_timestamp",
                               "extraction_status", "document_language",
                               "supersession_status", "last_verification_date",
                               "verification_status", "original_reference",
                               "obligations"]),
                           file_name="source_library.csv", mime="text/csv",
                           key="ri_lib_csv")


# --- B ---------------------------------------------------------------------------

def _panel_obligations(index) -> None:
    st.markdown(pane_head("Obligations explorer"), unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        demo_only = st.checkbox("Demo BOI set only", value=True, key="ri_obl_demo")
    with c2:
        cats = [("All", "")] + [(c.name, c.id) for c in taxonomy.CATEGORIES if c.orm_core]
        cat_label = st.selectbox("Risk category", [x[0] for x in cats], key="ri_obl_cat")
        cat_id = dict(cats)[cat_label] or None
    with c3:
        search = st.text_input("Search", placeholder="e.g. notify, cloud, continuity",
                               key="ri_obl_q")
    with c4:
        controls_views._reviewer_box("ri_obl_reviewer")

    with state.session() as s:
        reviews = state.reviews(s)
        df = ri.obligations_explorer(
            index, reviews, category_id=cat_id, search=search, demo_only=demo_only)
        if df.empty:
            st.markdown(notice("No obligations match these filters."),
                        unsafe_allow_html=True)
            return
        st.markdown(_status([
            ("obligations", str(len(df))),
            ("verified citations", str(int(df["citation_verified"].sum()))),
            ("need verification", str(int((~df["citation_verified"]).sum()))),
            ("unreviewed", str(int((df["status"] == "Unreviewed").sum()))),
        ]), unsafe_allow_html=True)
        st.markdown(_table(df, [
            "citation", "requirement_category", "modality", "validation_status",
            "citation_status", "business_process", "control_objective",
        ]), unsafe_allow_html=True)
        st.download_button(
            "Export obligations CSV",
            ri.to_csv(df, [
                "okey", "document_id", "citation", "clause_ref", "exact_source_text",
                "page_number", "source_language", "plain_language",
                "requirement_category", "business_process", "control_objective",
                "suggested_evidence", "validation_status", "citation_status",
                "modality", "link"]),
            file_name="obligations_explorer.csv", mime="text/csv", key="ri_obl_csv")

        labels = {
            r["okey"]: f"{r['citation']} — {str(r['plain_language'])[:80]}"
            for _, r in df.iterrows()}
        okey = st.selectbox("Open an obligation", list(labels),
                            format_func=labels.get, key="ri_obl_pick")
        row = df[df["okey"] == okey].iloc[0]
        st.markdown(_quote(row["exact_source_text"], row["citation"],
                           row.get("link") or "", row["citation_status"]),
                    unsafe_allow_html=True)
        st.markdown(_interp(row["plain_language"]), unsafe_allow_html=True)
        st.markdown(_kv([
            ("Requirement category", row["requirement_category"]),
            ("Business process", row["business_process"]),
            ("Control objective", row["control_objective"] or "—"),
            ("Suggested evidence", row["suggested_evidence"] or "—"),
            ("Validation", row["validation_status"]),
            ("Page", row["page_number"]),
            ("Language", row["source_language"]),
            ("Reviewer notes", row.get("note") or "—"),
        ]), unsafe_allow_html=True)

        edit = st.text_area("Edit plain-language explanation (saved as a review)",
                            value=row["plain_language"], key="ri_obl_edit")
        note = st.text_input("Reviewer notes", value=row.get("note") or "",
                             key="ri_obl_note")
        a1, a2, a3 = st.columns(3)
        name = controls_views._reviewer()
        with a1:
            if st.button("Validate obligation", key="ri_obl_ok", disabled=not name):
                state.save_review(s, okey, status=1, reviewer=name,
                                  action_edit=edit, note=note,
                                  control_id=row.get("control_id") or "")
                st.success("Marked validated.")
                st.rerun()
        with a2:
            if st.button("Reject extraction", key="ri_obl_no", disabled=not name):
                state.save_review(s, okey, status=-1, reviewer=name,
                                  action_edit=edit, note=note)
                st.success("Marked rejected.")
                st.rerun()
        with a3:
            st.caption("Enter your name above to record a decision.")


def _status(items: list[tuple[str, str]]) -> str:
    return '<div class="ws-status">' + "".join(
        f"<span><b>{_e(v)}</b> {_e(k)}</span>" for k, v in items) + "</div>"


# --- C ---------------------------------------------------------------------------

def _panel_compare(index) -> None:
    st.markdown(pane_head("Cross-jurisdiction comparison"), unsafe_allow_html=True)
    st.caption(ri.COMPARISON_DISCLAIMER)
    demo = ri.demo_registry(index)
    docs = ri.source_library(index)
    options = []
    if not demo.empty:
        options.extend(demo["document_id"].tolist())
    if not docs.empty:
        for d in docs["document_id"].tolist():
            if d not in options:
                options.append(d)
    labels = {}
    for _, r in (pd.concat([demo, docs]).drop_duplicates("document_id")
                 if not docs.empty else demo).iterrows():
        labels[r["document_id"]] = (
            f"{r.get('directive_number') or r['document_id']} · "
            f"{r.get('official_title') or r.get('title') or ''}")
    home = st.selectbox("Home document", options, format_func=labels.get,
                        key="ri_cmp_home")
    others = st.multiselect(
        "Compare with", [d for d in options if d != home],
        default=[d for d in options if d != home][:2],
        format_func=labels.get, key="ri_cmp_others")
    cats = [("All ORM categories", "")] + [
        (c.name, c.id) for c in taxonomy.CATEGORIES if c.orm_core]
    cat_label = st.selectbox("Limit to category", [x[0] for x in cats],
                             key="ri_cmp_cat")
    cat_id = dict(cats)[cat_label] or None
    if not others:
        st.markdown(notice("Select at least one other document."),
                    unsafe_allow_html=True)
        return
    cmp = ri.compare_documents(index, [home, *others], category_id=cat_id)
    if cmp.empty:
        st.markdown(notice("No obligations to compare for this selection."),
                    unsafe_allow_html=True)
        return
    st.markdown(_status([
        ("pairs", str(len(cmp))),
        ("substantially aligned",
         str(int((cmp["relation"] == "substantially_aligned").sum()))),
        ("no comparable / unable",
         str(int(cmp["relation"].isin(["no_comparable", "unable"]).sum()))),
    ]), unsafe_allow_html=True)
    st.markdown(_table(cmp, [
        "home_citation", "relation_label", "other_citation", "score",
        "validation_status",
    ]), unsafe_allow_html=True)
    st.download_button(
        "Export comparison CSV",
        ri.to_csv(cmp, [
            "home_okey", "home_citation", "home_quote", "home_interpretation",
            "home_citation_status", "other_document_id", "other_okey",
            "other_citation", "other_quote", "other_interpretation",
            "other_citation_status", "relation_label", "score",
            "similarity_note", "difference_note", "operational_implication",
            "validation_status", "disclaimer"]),
        file_name="ri_comparison.csv", mime="text/csv", key="ri_cmp_csv")

    idx = st.number_input("Open pair #", min_value=0, max_value=max(len(cmp) - 1, 0),
                          value=0, key="ri_cmp_i")
    row = cmp.iloc[int(idx)]
    st.markdown(pill(row["relation_label"], REL_KIND.get(row["relation_label"], "na")),
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="ri-pair">'
        f'<div>{_quote(row["home_quote"], row["home_citation"], row.get("home_link") or "", row["home_citation_status"])}'
        f'{_interp(row["home_interpretation"])}</div>'
        f'<div>{_quote(row["other_quote"] or "(no comparable quotation)", row["other_citation"], row.get("other_link") or "", row["other_citation_status"])}'
        f'{_interp(row["other_interpretation"]) if row["other_interpretation"] else ""}</div>'
        f"</div>",
        unsafe_allow_html=True)
    st.markdown(_kv([
        ("Similarities", row["similarity_note"]),
        ("Differences", row["difference_note"]),
        ("Operational implications", row["operational_implication"]),
        ("Validation", row["validation_status"]),
    ]), unsafe_allow_html=True)


# --- D ---------------------------------------------------------------------------

def _panel_applicability(index, rconn) -> None:
    st.markdown(pane_head("Applicability review"), unsafe_allow_html=True)
    st.caption("AI can suggest questions only. It does not declare binding legal "
               "obligations. Unverified applicability stays clearly marked.")
    demo = ri.demo_registry(index)
    docs = {r["document_id"]: r for _, r in demo.iterrows()}
    lib = ri.source_library(index)
    for _, r in lib.iterrows():
        docs.setdefault(r["document_id"], r)
    doc_id = st.selectbox(
        "Document", list(docs),
        format_func=lambda i: f"{docs[i].get('directive_number') or i} · "
                              f"{docs[i].get('official_title') or docs[i].get('title') or ''}",
        key="ri_app_doc")
    meta = docs[doc_id]
    existing = ri.applicability_for_document(rconn, doc_id)
    if existing:
        latest = existing[0]
        st.markdown(
            pill(risk.APPLICABILITY_LABEL.get(latest["status"], latest["status"]),
                 APP_KIND.get(latest["status"], "na")),
            unsafe_allow_html=True)
        st.markdown(_kv([
            ("Legal entity", latest["legal_entity"] or "—"),
            ("Licence / perimeter", latest["license_perimeter"] or "—"),
            ("Product / service", latest["product_service"] or "—"),
            ("Jurisdiction", latest["jurisdiction"] or "—"),
            ("Reasoning", latest["reasoning"] or "—"),
            ("Reviewer", latest["reviewer"] or "—"),
            ("Review date", latest["review_date"] or "—"),
            ("Supporting reference", latest["supporting_reference"] or "—"),
        ]), unsafe_allow_html=True)
    else:
        st.markdown(pill("Not yet assessed", "na"), unsafe_allow_html=True)

    st.markdown(pane_head("Questions to determine applicability"),
                unsafe_allow_html=True)
    for q in ri.applicability_questions(doc_id, meta.get("official_title") or ""):
        st.markdown(f"- {_e(q)}")

    name = controls_views._reviewer_box("ri_app_reviewer")
    status = st.selectbox(
        "Applicability status", list(risk.APPLICABILITY_STATUSES),
        format_func=lambda s: risk.APPLICABILITY_LABEL[s], key="ri_app_status")
    entity = st.text_input("Legal entity",
                           value="Demo Digital Bank Ltd (fictional)", key="ri_app_ent")
    license_ = st.text_input("Licence / regulatory perimeter",
                             placeholder="e.g. banking corporation / payment institution",
                             key="ri_app_lic")
    product = st.text_input("Relevant product / service",
                            value="Card payments", key="ri_app_prod")
    jur = st.text_input("Jurisdiction", value=meta.get("jurisdiction") or "IL",
                        key="ri_app_jur")
    reasoning = st.text_area("Reasoning", key="ri_app_why")
    support = st.text_input("Supporting reference (citation or memo id)",
                            key="ri_app_ref")
    if st.button("Save applicability decision", key="ri_app_save",
                 disabled=not name):
        ri.save_applicability(rconn, {
            "document_id": doc_id, "status": status, "legal_entity": entity,
            "license_perimeter": license_, "product_service": product,
            "jurisdiction": jur, "reasoning": reasoning,
            "supporting_reference": support,
            "is_synthetic": 1 if "fictional" in entity.lower() or "demo" in entity.lower() else 0,
        }, actor=name)
        st.success("Applicability decision saved.")
        st.rerun()

    all_rows = ri.list_applicability(rconn)
    if not all_rows.empty:
        st.markdown(pane_head("All applicability decisions"),
                    unsafe_allow_html=True)
        show = all_rows.copy()
        show["status_label"] = show["status"].map(risk.APPLICABILITY_LABEL)
        st.markdown(_table(show, [
            "document_id", "status_label", "legal_entity", "product_service",
            "jurisdiction", "reviewer", "review_date",
        ]), unsafe_allow_html=True)
        st.download_button(
            "Export applicability CSV",
            ri.to_csv(show, [
                "id", "document_id", "status", "status_label", "legal_entity",
                "license_perimeter", "product_service", "jurisdiction",
                "reasoning", "reviewer", "review_date", "supporting_reference",
                "validation_status", "is_synthetic"]),
            file_name="applicability.csv", mime="text/csv", key="ri_app_csv")


# --- E ---------------------------------------------------------------------------

def _panel_mapping(index, rconn) -> None:
    st.markdown(pane_head("Risk and control mapping"), unsafe_allow_html=True)
    st.caption("Generate editable suggestions from an obligation, then link to a "
               "risk only after a named reviewer confirms. Suggestions stay "
               "labelled until validated.")
    with state.session() as s:
        reviews = state.reviews(s)
    df = ri.obligations_explorer(index, reviews, demo_only=True)
    if df.empty:
        st.markdown(notice("No demo obligations available in this index."),
                    unsafe_allow_html=True)
        return
    labels = {r["okey"]: f"{r['citation']} — {str(r['plain_language'])[:80]}"
              for _, r in df.iterrows()}
    okey = st.selectbox("Obligation", list(labels), format_func=labels.get,
                        key="ri_map_okey")
    sug = ri.risk_mapping_suggestions(index, okey)
    if not sug.get("found"):
        st.markdown(notice("Obligation not found."), unsafe_allow_html=True)
        return
    st.markdown(_quote(sug["exact_source_text"], sug["citation"], sug.get("link") or "",
                       sug["citation_status"]), unsafe_allow_html=True)
    st.markdown(_interp(sug["interpretation"]), unsafe_allow_html=True)
    st.markdown(pill("Suggested — needs human validation", "partial"),
                unsafe_allow_html=True)

    name = controls_views._reviewer_box("ri_map_reviewer")
    risk_event = st.text_area("1. Risk event", value=sug["risk_event"], key="ri_map_ev")
    risk_cat = st.text_input("2. Risk category", value=sug["risk_category"],
                             key="ri_map_cat")
    causes = st.text_area("3. Causes", value=sug["causes"], key="ri_map_causes")
    consequences = st.text_area("4. Potential consequences",
                                value=sug["consequences"], key="ri_map_cons")
    processes = st.text_input("5. Affected business processes",
                              value=sug["business_processes"], key="ri_map_proc")
    control_obj = st.text_input("6. Control objectives",
                                value=sug["control_objectives"], key="ri_map_ctl")
    kris = st.text_area("7. Potential KRIs", value=sug["potential_kris"],
                        key="ri_map_kri")
    evidence = st.text_area("8. Potential control evidence",
                            value=sug["potential_evidence"], key="ri_map_evd")
    owners = st.text_input("9. Accountable stakeholders",
                           value=sug["accountable_stakeholders"], key="ri_map_own")
    st.caption(sug["disclaimer"])

    reg = risk.register(rconn)
    risk_ids = reg["id"].tolist() if not reg.empty else []
    if not risk_ids:
        st.markdown(notice(
            "No risks in the register yet. Open Risk register to seed the "
            "synthetic demo, then return here to link."), unsafe_allow_html=True)
        return
    risk_labels = dict(zip(reg["id"], reg["id"] + " · " + reg["title"]))
    risk_id = st.selectbox("Link to existing risk (after review)", risk_ids,
                           format_func=risk_labels.get, key="ri_map_risk")
    rationale = st.text_area(
        "Link rationale",
        value=(f"RI mapping: {risk_event[:120]} | process={processes} | "
               f"control={control_obj}"),
        key="ri_map_rationale")
    if st.button("Validate and link to risk", key="ri_map_link", disabled=not name):
        # Persist the edited suggestion text in the rationale / review note.
        with state.session() as s:
            state.save_review(
                s, okey, status=1, reviewer=name,
                action_edit=sug["interpretation"],
                note=(f"Mapped to {risk_id}. Category={risk_cat}. Causes={causes[:180]}. "
                      f"Consequences={consequences[:180]}. KRIs={kris[:120]}. "
                      f"Owners={owners}"),
                control_id=sug.get("suggested_control_id") or "")
        linked = ri.link_suggestion_to_risk(
            rconn, index, risk_id=risk_id, okey=okey,
            rationale=rationale, actor=name)
        st.success(f"Linked {okey} → {risk_id} "
                   f"({linked.get('validation_status', 'saved')}).")
