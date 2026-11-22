"""Regulatory Change Impact Analyzer screens.

Compares two document versions, maps changed clauses to risks/controls, and
proposes review actions. Never asserts noncompliance from a text diff alone.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import change_impact as ci, demo_data, risk
from ui_theme import e as _e, empty_state, notice, page_header, pane_head, pill

PAGES: dict = {}

KIND_PILL = {
    "added": "gap",
    "removed": "partial",
    "modified": "partial",
    "unchanged": "found",
    "uncertain": "na",
}

CSS = """
<style>
.ci-cards {display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px; margin: 8px 0 14px;}
.ci-card {border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
  background: var(--surface);}
.ci-card .n {font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums;}
.ci-card .l {font-size: 11px; color: var(--ink-3); margin-top: 2px;}
.ci-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 6px 0;
  white-space: pre-wrap; font-size: 13px; color: var(--ink-2);}
.ci-law {font-family: var(--serif); font-size: 14.5px; line-height: 1.55;}
@media (max-width: 900px) {
  .ci-cards {grid-template-columns: repeat(3, minmax(0, 1fr));}
}
</style>
"""


def page_change_impact() -> None:
    page_header(
        "Regulatory Change Impact",
        "Compare two verified versions of a document, map changed obligations "
        "to risks and controls, and generate auditable review actions.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            ci.seed(conn, index)
            risk_views._banner(conn)
            st.markdown(notice(f"<b>Important.</b> {_e(ci.NOTICE)}", "warn"),
                        unsafe_allow_html=True)

            fams = ci.families(conn)
            if fams.empty:
                st.markdown(empty_state(
                    "No document families available for version comparison.",
                    "Enable Demo Mode or import paired document versions."),
                    unsafe_allow_html=True)
                return

            default_i = 0
            if "DEMO-CLOUD-RES" in list(fams["id"]):
                default_i = list(fams["id"]).index("DEMO-CLOUD-RES")
            family_id = st.selectbox(
                "Document family", list(fams["id"]), index=default_i,
                format_func=lambda i: f"{i} — {fams.set_index('id').loc[i, 'title']}",
                key="ci_family")
            fam_row = fams[fams["id"] == family_id].iloc[0]
            st.caption(_e(fam_row.get("publisher_note") or ""))

            vers = ci.versions(conn, family_id)
            if len(vers) < 2:
                st.markdown(empty_state(
                    "At least two versions are required.",
                    "Seed the fictional demo or import a second verified version."),
                    unsafe_allow_html=True)
                return
            ids = list(vers["id"])
            labels = {
                r["id"]: f"{r['version_label']} ({r.get('published_at') or 'undated'})"
                for _, r in vers.iterrows()}
            c1, c2 = st.columns(2)
            with c1:
                va = st.selectbox(
                    "Version A (baseline)", ids,
                    index=ids.index("DEMO-CLOUD-RES-A") if "DEMO-CLOUD-RES-A" in ids else 0,
                    format_func=lambda i: labels[i], key="ci_va")
            with c2:
                vb = st.selectbox(
                    "Version B (newer)", ids,
                    index=ids.index("DEMO-CLOUD-RES-B") if "DEMO-CLOUD-RES-B" in ids else min(1, len(ids)-1),
                    format_func=lambda i: labels[i], key="ci_vb")
            if va == vb:
                st.warning("Select two different versions.")
                return

            analysis = ci.analyze(conn, va, vb)
            _counts(analysis["counts"])

            tabs = st.tabs([
                "1. Version Comparison",
                "2. Changed Obligations",
                "3. Affected Risk and Control Mapping",
                "4. Proposed Remediation",
                "5. Management Summary",
            ])
            with tabs[0]:
                _panel_versions(analysis)
            with tabs[1]:
                _panel_changed(analysis)
            with tabs[2]:
                _panel_mapping(analysis)
            with tabs[3]:
                _panel_actions(conn, analysis)
            with tabs[4]:
                _panel_summary(analysis)
    finally:
        ctx.__exit__(None, None, None)


def _counts(counts: dict) -> None:
    st.markdown(
        '<div class="ci-cards" role="group" aria-label="Change counts">'
        + "".join(
            f'<div class="ci-card"><div class="n">{counts.get(k, 0)}</div>'
            f'<div class="l">{k.title()}</div></div>'
            for k in ("added", "removed", "modified", "unchanged", "uncertain"))
        + "</div>",
        unsafe_allow_html=True)


def _panel_versions(analysis: dict) -> None:
    st.markdown(pane_head("Version Comparison"), unsafe_allow_html=True)
    va, vb = analysis["version_a"], analysis["version_b"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{_e(va['version_label'])}** · {_e(va.get('published_at') or '')}")
        st.markdown(f'<div class="ci-quote">{_e(va.get("summary") or "")}</div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f"**{_e(vb['version_label'])}** · {_e(vb.get('published_at') or '')}")
        st.markdown(f'<div class="ci-quote">{_e(vb.get("summary") or "")}</div>',
                    unsafe_allow_html=True)
    st.caption(analysis["fictional_publisher"])

    rows = [{
        "Clause": d["clause_ref"],
        "Change": d["change_kind"],
        "Similarity": d["similarity"],
        "Certainty": d["certainty"],
        "Materiality": d["materiality"],
    } for d in analysis["diffs"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _panel_changed(analysis: dict) -> None:
    st.markdown(pane_head("Changed Obligations"), unsafe_allow_html=True)
    st.caption(
        "Source-backed textual difference plus plain-language interpretation. "
        "Interpretations are hypotheses for review.")
    changed = analysis["changed"]
    if not changed:
        st.markdown(empty_state("No clause differences detected between these versions."),
                    unsafe_allow_html=True)
        return
    for d in changed:
        st.markdown(
            f"{pill(d['change_kind'], KIND_PILL.get(d['change_kind'], 'na'))} "
            f"**{_e(d['clause_ref'])}** · similarity {d['similarity']}",
            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Version A**")
            st.markdown(f'<div class="ci-law ci-quote">{_e(d["text_a"] or "—")}</div>',
                        unsafe_allow_html=True)
        with c2:
            st.markdown("**Version B**")
            st.markdown(f'<div class="ci-law ci-quote">{_e(d["text_b"] or "—")}</div>',
                        unsafe_allow_html=True)
        if d.get("diff"):
            with st.expander(f"Unified diff · {d['clause_ref']}"):
                st.code(d["diff"], language="diff")
        st.markdown(
            f"**Interpretation** ({_e(d['certainty'])})"
            f'<div class="ci-quote">{_e(d["interpretation"])}</div>',
            unsafe_allow_html=True)


def _panel_mapping(analysis: dict) -> None:
    st.markdown(pane_head("Affected Risk and Control Mapping"),
                unsafe_allow_html=True)
    st.caption(
        "Potential links based on theme overlap with existing records. "
        "Requires human confirmation before reassessment.")
    m = analysis["mapping"]
    if m.get("themes"):
        st.write("Detected themes (heuristic):", ", ".join(m["themes"]))

    risks = m.get("risks") or []
    controls = m.get("controls") or []
    if not risks and not controls:
        st.markdown(empty_state(
            "No linked risks or controls were identified for these changes.",
            "Map obligations to risks in the Risk Register, then re-run."),
            unsafe_allow_html=True)
        return

    if risks:
        st.markdown("**Operational risks that may require reassessment**")
        st.dataframe(pd.DataFrame(risks), hide_index=True, use_container_width=True)
    if controls:
        st.markdown("**Control objectives potentially affected**")
        st.dataframe(pd.DataFrame(controls), hide_index=True, use_container_width=True)
        if any(c.get("testing_program_review") for c in controls):
            st.markdown(notice(
                "<b>Control testing program:</b> changed language may imply a need "
                "to review whether periodic evidence-supported recovery testing is "
                "covered. This is a review prompt, not a failed-test finding.",
                "warn"), unsafe_allow_html=True)


def _panel_actions(conn, analysis: dict) -> None:
    st.markdown(pane_head("Proposed Remediation"), unsafe_allow_html=True)
    st.caption(
        "Suggested actions with owner, priority and due date. "
        "Persisting them creates an auditable draft requiring human review.")
    acts = analysis["actions"]
    if not acts:
        st.markdown(empty_state("No remediation suggestions for this comparison."),
                    unsafe_allow_html=True)
        return
    st.dataframe(pd.DataFrame(acts)[[
        "id", "clause_ref", "change_kind", "title", "owner", "priority",
        "due_at", "related_risk_id", "related_control_id", "requires_human_review",
    ]], hide_index=True, use_container_width=True)

    if st.button("Generate auditable review actions", type="primary",
                 key="ci_persist"):
        saved = ci.persist_actions(conn, analysis, actor="ui-reviewer")
        st.success(
            f"Wrote {len(saved)} change-impact action(s) and linked remediation "
            "rows (draft / pending validation). Open Risk Register or Incidents "
            "actions to continue review.")
        # Offer navigation hints
        if PAGES.get("risks"):
            if st.button("Open Risk Register", key="ci_goto_risks"):
                st.switch_page(PAGES["risks"])


def _panel_summary(analysis: dict) -> None:
    st.markdown(pane_head("Management Summary"), unsafe_allow_html=True)
    s = analysis["summary"]
    st.markdown(f"### {_e(s['title'])}")
    st.markdown(f'<div class="ci-quote">{_e(s["headline"])}</div>',
                unsafe_allow_html=True)
    st.markdown(notice(_e(s["disclaimer"]), "warn"), unsafe_allow_html=True)
    st.write("Versions:", s["from_version"], "→", s["to_version"])
    st.write("Publisher note:", s["publisher_note"])

    if s["key_changes"]:
        st.markdown("**Key changes**")
        for c in s["key_changes"]:
            st.markdown(
                f"- {pill(c['kind'], KIND_PILL.get(c['kind'], 'na'))} "
                f"**{_e(c['ref'])}** — {_e(c['interpretation'])}",
                unsafe_allow_html=True)

    st.download_button(
        "Download management summary (.md)",
        data=ci.export_summary_text(s).encode("utf-8"),
        file_name=f"change_impact_{analysis['family']['id']}.md",
        mime="text/markdown",
        key="ci_export_md")
