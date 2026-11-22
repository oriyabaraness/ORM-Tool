"""Executive Operational Risk Reporting screens.

Renders orm.exec_report output only. Narratives distinguish FACTS / ANALYSIS /
RECOMMENDATIONS. Synthetic packs are watermarked. No compliance conclusions.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import demo_data, exec_report as er, risk
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

CSS = """
<style>
.ex-cards {display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px; margin: 8px 0 14px;}
.ex-card {border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
  background: var(--surface);}
.ex-card .n {font-size: 22px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums;}
.ex-card .l {font-size: 12px; color: var(--ink-3); margin-top: 2px;}
.ex-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 6px 0;
  font-size: 13px; color: var(--ink-2);}
.ex-sec {margin: 10px 0 16px;}
@media (max-width: 1100px) {
  .ex-cards {grid-template-columns: repeat(3, minmax(0, 1fr));}
}
@media (max-width: 640px) {
  .ex-cards {grid-template-columns: repeat(2, minmax(0, 1fr));}
}
</style>
"""

SECTION_TITLES = [
    ("A_executive_summary", "A. Executive summary"),
    ("B_material_developments", "B. Material developments"),
    ("C_risk_appetite_exceptions", "C. Risk appetite exceptions"),
    ("D_control_environment", "D. Control environment observations"),
    ("E_operational_incidents", "E. Operational incidents"),
    ("F_resilience_concerns", "F. Resilience concerns"),
    ("G_outstanding_decisions", "G. Outstanding management decisions"),
    ("H_next_period_priorities", "H. Next-period priorities"),
]


def page_executive_report() -> None:
    page_header(
        "Executive report",
        "Period-filtered operational risk pack for Head of ORM, country "
        "management and the Risk Committee — evidence-linked and editable.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            er.seed(conn, index)
            risk_views._banner(conn)

            period, as_of, c_start, c_end = _period_controls()
            try:
                rep = er.build(
                    conn, index, period=period, as_of=as_of,
                    custom_start=c_start, custom_end=c_end,
                    title=er.DEMO_TITLE if risk.is_synthetic(conn) else None)
            except ValueError as err:
                st.error(str(err))
                return

            if rep.get("watermark"):
                st.markdown(notice(f"<b>{_e(rep['watermark'])}</b>", "warn"),
                            unsafe_allow_html=True)
            st.caption(
                f"{rep['title']} · {rep['period']['label']} · "
                f"Generated {rep['generated_at']} · "
                f"{rep['document_status']} · {rep['review_status']}")

            _dashboard(rep)
            tabs = st.tabs([
                "Dashboard detail",
                "Risk movement",
                "Management narrative",
                "Committee actions",
                "Explainability",
                "Export",
            ])
            with tabs[0]:
                _panel_detail(rep)
            with tabs[1]:
                _panel_movement(rep)
            with tabs[2]:
                _panel_narrative(rep)
            with tabs[3]:
                _panel_actions(rep)
            with tabs[4]:
                _panel_explain(rep)
            with tabs[5]:
                _panel_export(rep)
            st.caption(rep["notice"] + " " + rep["method_note"])
    finally:
        ctx.__exit__(None, None, None)


def _period_controls():
    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
    with c1:
        period = st.selectbox(
            "Reporting period", ["monthly", "weekly", "quarterly", "custom"],
            format_func=lambda x: x.title(), key="ex_period")
    with c2:
        as_of = st.date_input("As of", value=dt.date.today(), key="ex_asof")
    c_start = c_end = None
    with c3:
        if period == "custom":
            c_start = st.date_input("From", value=as_of - dt.timedelta(days=30),
                                    key="ex_from")
        else:
            st.caption("—")
    with c4:
        if period == "custom":
            c_end = st.date_input("To", value=as_of, key="ex_to")
        else:
            st.caption("—")
    return period, as_of, c_start, c_end


def _dashboard(rep: dict) -> None:
    m = rep["metrics"]
    st.markdown(
        '<div class="ex-cards">'
        f'<div class="ex-card"><div class="n">{m["open_risks"]}</div>'
        f'<div class="l">1. Overall open risks</div></div>'
        f'<div class="ex-card"><div class="n">{m["outside_appetite"]}</div>'
        f'<div class="l">4. Outside appetite</div></div>'
        f'<div class="ex-card"><div class="n">{m["kri_red"]}</div>'
        f'<div class="l">5. KRI Red breaches</div></div>'
        f'<div class="ex-card"><div class="n">{m["critical_weak_controls"]}</div>'
        f'<div class="l">6. Critical control weaknesses</div></div>'
        f'<div class="ex-card"><div class="n">{m["material_incidents"]}</div>'
        f'<div class="l">7. Material incidents</div></div>'
        f'<div class="ex-card"><div class="n">{m["overdue_actions"]}</div>'
        f'<div class="l">8. Overdue actions</div></div>'
        f'<div class="ex-card"><div class="n">{m["concentration_flags"]}</div>'
        f'<div class="l">9. Concentration concerns</div></div>'
        f'<div class="ex-card"><div class="n">{m["emerging_risks"]}</div>'
        f'<div class="l">10. Emerging / highlighted</div></div>'
        f'<div class="ex-card"><div class="n">{m["residual_overrides"]}</div>'
        f'<div class="l">3. Documented residual overrides</div></div>'
        f'<div class="ex-card"><div class="n">{m["kri_amber"]}</div>'
        f'<div class="l">5b. KRI Amber</div></div>'
        "</div>", unsafe_allow_html=True)
    bands = m.get("by_residual_band") or {}
    if bands:
        st.markdown(pane_head("2. Risk distribution by residual severity"),
                    unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame([{"Band": k, "Count": v} for k, v in sorted(bands.items())]),
            hide_index=True, use_container_width=True)


def _panel_detail(rep: dict) -> None:
    sections = (
        ("Risks exceeding appetite", rep["outside_appetite"],
         ["id", "title", "residual_score", "residual_band", "appetite", "owner"]),
        ("KRI breaches", rep["kri_breaches"],
         ["id", "name", "rag", "value", "unit"]),
        ("Critical control weaknesses", rep["critical_controls"],
         ["id", "name", "rating", "operating_rating", "owner", "findings"]),
        ("Material operational incidents", rep["incidents"],
         ["id", "title", "severity", "occurred_at", "owner", "status"]),
        ("Overdue remediation", rep["overdue_actions"],
         ["id", "title", "owner", "due_at", "source_id", "status"]),
        ("Third-party concentration concerns", rep["concentration"], None),
        ("Emerging operational risks", rep["emerging"], None),
    )
    for title, frame, cols in sections:
        st.markdown(pane_head(title, count=str(0 if frame is None or frame.empty
                                               else len(frame))),
                    unsafe_allow_html=True)
        if frame is None or frame.empty:
            st.caption("None in this view — or evidence not recorded.")
            continue
        use = [c for c in (cols or list(frame.columns)) if c in frame.columns][:10]
        st.dataframe(frame[use] if use else frame, hide_index=True,
                     use_container_width=True)


def _panel_movement(rep: dict) -> None:
    st.markdown(pane_head("Risk movement (audit-traced)"), unsafe_allow_html=True)
    st.caption(
        "Prior → current from the risk audit log only. "
        "If a reason was not recorded, the report says evidence is missing.")
    moves = rep.get("movements") or []
    if not moves:
        st.markdown(notice("No documented residual movements in this period."),
                    unsafe_allow_html=True)
    for mv in moves:
        st.markdown(
            f"**{_e(mv['risk_id'])}** — {_e(mv.get('title') or '')}<br>"
            f'<div class="ex-quote">'
            f"Prior: {_e(str(mv['prior']))}<br>"
            f"Current: {_e(str(mv['current']))}<br>"
            f"Reason: {_e(mv['reason_for_change'])}<br>"
            f"Evidence: {_e(str(mv.get('new_evidence') or 'Missing'))}<br>"
            f"Control changes: {_e(str(mv.get('control_changes')))}<br>"
            f"Related incidents: {_e(', '.join(mv.get('related_incidents') or []) or 'none linked')}<br>"
            f"Owner: {_e(str(mv.get('owner') or ''))} · "
            f"Approval: {_e(str(mv.get('approval_status') or ''))} · "
            f"Actor: {_e(str(mv.get('actor') or ''))} @ {_e(str(mv.get('at') or ''))}"
            f"</div>",
            unsafe_allow_html=True)

    st.markdown(pane_head("Documented residual overrides (current register)"),
                unsafe_allow_html=True)
    ov = rep["residual_overrides"]
    if ov is None or ov.empty:
        st.caption("No residual overrides on the current register.")
    else:
        st.dataframe(ov, hide_index=True, use_container_width=True)


def _panel_narrative(rep: dict) -> None:
    st.markdown(pane_head("Draft management commentary"), unsafe_allow_html=True)
    st.caption(
        "Editable draft. FACTS = observed records. ANALYSIS = interpretation. "
        "RECOMMENDATIONS = suggested next steps. Not a compliance attestation.")
    sections = rep["narrative"]["sections"]
    for key, title in SECTION_TITLES:
        sec = sections[key]
        st.markdown(f"### {title}")
        for label, kind in (("FACTS", "found"), ("ANALYSIS", "partial"),
                            ("RECOMMENDATIONS", "na")):
            st.markdown(pill(label, kind), unsafe_allow_html=True)
            default = "\n".join(sec[label.lower()])
            st.text_area(
                f"{title} · {label}",
                value=default,
                key=f"ex_narr_{key}_{label}",
                height=100,
                label_visibility="collapsed")


def _panel_actions(rep: dict) -> None:
    st.markdown(pane_head("Risk committee actions"), unsafe_allow_html=True)
    acts = rep["committee_actions"]
    if acts is None or acts.empty:
        st.caption("No committee actions derived from open records.")
        return
    st.dataframe(acts, hide_index=True, use_container_width=True)


def _panel_explain(rep: dict) -> None:
    st.markdown(pane_head("Explainability — evidence links"), unsafe_allow_html=True)
    st.caption("Every metric row traces to an application record. Missing evidence is stated.")
    prov = rep.get("provenance") or []
    if not prov:
        st.caption("No provenance rows.")
        return
    st.dataframe(pd.DataFrame(prov), hide_index=True, use_container_width=True)
    if rep.get("resilience"):
        st.markdown("**Resilience scenario link**")
        r = rep["resilience"]
        st.markdown(
            f'<div class="ex-quote">{_e(r.get("headline") or "")}<br>'
            f"Risk: {_e(str(r.get('linked_risk_id') or ''))} · "
            f"Scenario: {_e(str(r.get('scenario_id') or ''))}</div>",
            unsafe_allow_html=True)


def _panel_export(rep: dict) -> None:
    st.markdown(pane_head("Export"), unsafe_allow_html=True)
    st.caption(
        "One-page executive pack. PDF preferred; HTML is print-ready. "
        "Synthetic watermark included when demo data is present.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "Download PDF",
            data=er.export_pdf(rep),
            file_name=f"executive_risk_report_{rep['period']['end_iso']}.pdf",
            mime="application/pdf",
            key="ex_pdf")
    with c2:
        st.download_button(
            "Download HTML (printable)",
            data=er.export_html(rep).encode("utf-8"),
            file_name=f"executive_risk_report_{rep['period']['end_iso']}.html",
            mime="text/html",
            key="ex_html")
    with c3:
        st.download_button(
            "Download Excel",
            data=er.export_excel(rep),
            file_name=f"executive_risk_report_{rep['period']['end_iso']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ex_xlsx")
    with st.expander("HTML preview (source)"):
        st.code(er.export_html(rep)[:4000] + "\n…", language="html")
