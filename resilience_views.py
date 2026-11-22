"""Operational Resilience and Scenario Analysis screens.

All calculations come from orm.resilience. Synthetic demo content is labelled.
Impact tolerances are never invented. Scenario figures are assumptions, not
calibrated forecasts.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import demo_data, resilience as rs, risk
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

TOL_KIND = {"pass": "found", "fail": "gap", "indeterminate": "na"}
CRIT_KIND = {"critical": "gap", "important": "partial", "standard": "na"}

CSS = """
<style>
.res-cards {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin: 8px 0 14px;}
.res-card {border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
  background: var(--surface);}
.res-card .n {font-size: 22px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums;}
.res-card .l {font-size: 12px; color: var(--ink-3); margin-top: 2px;}
.res-kv {display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px;
  font-size: 13px; color: var(--ink-2);}
.res-kv b {color: var(--ink); font-weight: 500;}
.res-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 8px 0;
  white-space: pre-wrap; font-size: 13px; color: var(--ink-2);}
.res-opt {border: 1px solid var(--line); border-radius: 8px; padding: 12px;
  margin: 8px 0; background: var(--surface);}
@media (max-width: 900px) {
  .res-cards {grid-template-columns: repeat(2, minmax(0, 1fr));}
}
@media (max-width: 640px) {
  .res-cards {grid-template-columns: 1fr;}
}
</style>
"""


def page_resilience() -> None:
    page_header("Operational Resilience",
                "Important business services, dependency mapping, BIA and "
                "severe-but-plausible scenario analysis.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            rs.seed(conn, index)
            risk_views._banner(conn)
            st.markdown(notice(f"<b>Synthetic demonstration.</b> {_e(rs.NOTICE)}", "warn"),
                        unsafe_allow_html=True)
            dash = rs.dashboard(conn)
            _cards(dash)
            tabs = st.tabs([
                "Services",
                "Dependencies",
                "Business impact analysis",
                "Scenarios",
                "Results & comparison",
                "Management summary",
                "Concepts",
            ])
            with tabs[0]:
                _panel_services(conn, dash)
            with tabs[1]:
                _panel_dependencies(conn, dash)
            with tabs[2]:
                _panel_bia(conn, dash)
            with tabs[3]:
                _panel_scenarios(conn, dash)
            with tabs[4]:
                _panel_results(conn)
            with tabs[5]:
                _panel_summary(conn)
            with tabs[6]:
                _panel_concepts()
    finally:
        ctx.__exit__(None, None, None)


def _cards(dash: dict) -> None:
    st.markdown(
        '<div class="res-cards">'
        f'<div class="res-card"><div class="n">{dash["service_count"]}</div>'
        f'<div class="l">Services in inventory</div></div>'
        f'<div class="res-card"><div class="n">{dash["ibs_count"]}</div>'
        f'<div class="l">Designated IBS (explicit)</div></div>'
        f'<div class="res-card"><div class="n">{dash["scenario_count"]}</div>'
        f'<div class="l">Scenarios / templates</div></div>'
        f'<div class="res-card"><div class="n">{dash["flag_count"]}</div>'
        f'<div class="l">Concentration hypotheses</div></div>'
        "</div>", unsafe_allow_html=True)


def _panel_services(conn, dash: dict) -> None:
    svcs = dash["services"]
    st.markdown(pane_head("Service inventory",
                          count=str(dash["service_count"])), unsafe_allow_html=True)
    st.caption(
        "Important business service (IBS) designation is explicit. "
        "Criticality alone does not auto-designate an IBS.")
    if svcs.empty:
        st.markdown(notice("No services yet."), unsafe_allow_html=True)
        return
    show = svcs.copy()
    cols = [c for c in (
        "id", "name", "criticality", "is_ibs", "legal_entity", "jurisdiction",
        "owner", "impact_tolerance_hours", "rto_hours", "rpo_hours",
        "last_resilience_assessment", "is_synthetic",
    ) if c in show.columns]
    st.dataframe(show[cols].rename(columns={
        "id": "Service ID", "name": "Name", "criticality": "Criticality",
        "is_ibs": "IBS?", "legal_entity": "Legal entity",
        "jurisdiction": "Jurisdiction", "owner": "Owner",
        "impact_tolerance_hours": "Svc tolerance (h)",
        "rto_hours": "RTO (h)", "rpo_hours": "RPO (h)",
        "last_resilience_assessment": "Last assessment",
        "is_synthetic": "Synthetic",
    }), hide_index=True, use_container_width=True)

    pick = st.selectbox(
        "Open service", list(show["id"]),
        index=list(show["id"]).index("SVC-001") if "SVC-001" in list(show["id"]) else 0,
        key="res_svc_pick")
    detail = rs.service_detail(conn, pick)
    row = detail["service"]
    st.markdown(
        pill(row.get("criticality") or "—", CRIT_KIND.get(row.get("criticality"), "na"))
        + " "
        + pill("IBS designated" if int(row.get("is_important_business_service") or 0)
               else "Not designated IBS",
               "found" if int(row.get("is_important_business_service") or 0) else "na"),
        unsafe_allow_html=True)
    st.markdown(f"### {_e(row.get('name') or '')}")
    st.markdown(f'<div class="res-quote">{_e(row.get("description") or "")}</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"**IBS designation rationale**<div class='res-quote'>"
        f"{_e(row.get('ibs_designation_rationale') or '—')}</div>",
        unsafe_allow_html=True)
    for lab, key in (
        ("Customer impact", "customer_impact"),
        ("Alternate arrangements", "alternate_arrangements"),
        ("Recovery objectives", "recovery_objectives"),
    ):
        if row.get(key):
            st.markdown(f"**{lab}**<div class='res-quote'>{_e(row.get(key))}</div>",
                        unsafe_allow_html=True)
    if not detail["risks"].empty:
        st.markdown("**Linked risks**")
        st.dataframe(detail["risks"], hide_index=True, use_container_width=True)


def _panel_dependencies(conn, dash: dict) -> None:
    st.markdown(pane_head("Dependency mapping"), unsafe_allow_html=True)
    st.caption(
        "Business Service → Process → Application → Infrastructure → "
        "Third Party → Recovery Capability. Flags are hypotheses requiring validation.")
    svcs = dash["services"]
    pick = st.selectbox(
        "Service for graph", ["All"] + list(svcs["id"]) if not svcs.empty else ["All"],
        key="res_dep_svc")
    sid = None if pick == "All" else pick
    mermaid = rs.dependency_graph_mermaid(conn, sid)
    try:
        st.mermaid(mermaid)
    except Exception:
        st.code(mermaid, language="mermaid")

    deps = risk._df(conn, "SELECT * FROM service_dependency ORDER BY service_id, layer")
    if not deps.empty:
        st.dataframe(deps[[
            "service_id", "layer", "name", "shared_key", "has_alternative",
            "last_tested_at", "is_spof", "note",
        ]].rename(columns={
            "service_id": "Service", "layer": "Layer", "name": "Dependency",
            "shared_key": "Shared key", "has_alternative": "Has alternative",
            "last_tested_at": "Last tested", "is_spof": "SPOF flag", "note": "Note",
        }), hide_index=True, use_container_width=True)

    st.markdown(pane_head("Concentration / resilience hypotheses"),
                unsafe_allow_html=True)
    flags = dash["flags"]
    if flags.empty:
        st.caption("No hypothesis flags.")
    else:
        st.dataframe(flags.rename(columns={
            "kind": "Flag kind", "certainty": "Certainty",
            "shared_key": "Shared key", "services": "Services",
            "detail": "Detail", "requires_validation": "Needs validation",
        }), hide_index=True, use_container_width=True)


def _panel_bia(conn, dash: dict) -> None:
    st.markdown(pane_head("Business impact analysis"), unsafe_allow_html=True)
    st.caption(
        "RTO, RPO and impact tolerance are conceptually separate. "
        "If no approved tolerance exists, the system shows "
        "“Impact tolerance not defined.”")
    svcs = dash["services"]
    if svcs.empty:
        return
    pick = st.selectbox(
        "Service", list(svcs["id"]),
        index=list(svcs["id"]).index("SVC-001") if "SVC-001" in list(svcs["id"]) else 0,
        key="res_bia_svc")
    d = rs.service_detail(conn, pick)
    bia = d["bia"]
    if not bia:
        st.markdown(notice("No BIA recorded for this service."), unsafe_allow_html=True)
        return
    tol = bia.get("impact_tolerance_hours")
    if tol is None or (isinstance(tol, float) and pd.isna(tol)):
        st.markdown(notice("<b>Impact tolerance not defined.</b>", "warn"),
                    unsafe_allow_html=True)
    else:
        st.markdown(
            pill(f"Illustrative impact tolerance: {tol} h", "partial"),
            unsafe_allow_html=True)
    st.markdown(
        f'<div class="res-kv">'
        f'<b>Criticality</b><span>{_e(bia.get("criticality") or "—")}</span>'
        f'<b>Max tolerable disruption (h)</b>'
        f'<span>{_e(str(bia.get("max_tolerable_disruption_hours") or "—"))}</span>'
        f'<b>RTO (h)</b><span>{_e(str(bia.get("rto_hours") or "—"))}</span>'
        f'<b>RPO (h)</b><span>{_e(str(bia.get("rpo_hours") or "—"))}</span>'
        f'<b>Impact tolerance (h)</b>'
        f'<span>{_e("not defined" if tol is None or (isinstance(tol, float) and pd.isna(tol)) else str(tol))}</span>'
        f'</div>', unsafe_allow_html=True)
    for lab, key in (
        ("Financial impact", "financial_impact"),
        ("Customer impact", "customer_impact"),
        ("Operational impact", "operational_impact"),
        ("Reputational impact", "reputational_impact"),
        ("Legal / regulatory considerations", "legal_regulatory"),
        ("Impact tolerance basis", "impact_tolerance_basis"),
        ("Supporting evidence", "evidence"),
        ("Assumptions", "assumptions_note"),
    ):
        st.markdown(f"**{lab}**<div class='res-quote'>{_e(bia.get(key) or '—')}</div>",
                    unsafe_allow_html=True)


def _panel_scenarios(conn, dash: dict) -> None:
    st.markdown(pane_head("Severe-but-plausible scenarios"), unsafe_allow_html=True)
    scns = dash["scenarios"]
    if scns.empty:
        st.caption("No scenarios.")
        return
    st.dataframe(scns[[
        c for c in ("id", "code", "name", "scenario_type", "duration_minutes",
                    "linked_risk_id", "is_template", "confidence", "is_synthetic")
        if c in scns.columns
    ]].rename(columns={
        "id": "ID", "code": "Code", "name": "Name", "scenario_type": "Type",
        "duration_minutes": "Duration (min)", "linked_risk_id": "Risk",
        "is_template": "Template?", "confidence": "Confidence",
        "is_synthetic": "Synthetic",
    }), hide_index=True, use_container_width=True)

    with st.expander("Add user-defined scenario"):
        name = st.text_input("Name", key="res_custom_name")
        dur = st.number_input("Duration (minutes)", min_value=1.0, value=60.0,
                              key="res_custom_dur")
        tx = st.number_input("Avg transactions / hour (assumption)",
                             min_value=0.0, value=1000.0, key="res_custom_tx")
        rate = st.number_input("Failure rate % (assumption)", min_value=0.0,
                               max_value=100.0, value=80.0, key="res_custom_rate")
        svc = st.selectbox(
            "Affected service",
            list(dash["services"]["id"]) if not dash["services"].empty else [],
            key="res_custom_svc")
        if st.button("Create scenario", key="res_custom_go") and name and svc:
            row = rs.create_custom_scenario(
                conn, name=name, duration_minutes=dur, avg_tx_per_hour=tx,
                failure_rate_pct=rate, service_ids=[svc], actor="ui-user")
            st.success(f"Created {row['id']}")
            st.rerun()


def _panel_results(conn) -> None:
    scns = rs.scenarios(conn)
    runnable = scns[scns["is_template"] == 0] if not scns.empty else scns
    if runnable.empty:
        st.caption("No parameterised scenarios yet.")
        return
    ids = list(runnable["id"])
    default = "SCN-DEMO-CLOUD" if "SCN-DEMO-CLOUD" in ids else ids[0]
    pick = st.selectbox(
        "Scenario", ids, index=ids.index(default),
        format_func=lambda i: f"{i} — {runnable.set_index('id').loc[i, 'name']}",
        key="res_res_pick")
    d = rs.scenario_detail(conn, pick)
    scn = d["scenario"]
    if d["notice"]:
        st.markdown(notice(_e(d["notice"]), "warn"), unsafe_allow_html=True)
    st.markdown(f"### {_e(scn.get('name') or '')}")
    st.caption(d["method_note"])

    st.markdown(pane_head("Scenario parameters (assumptions)"), unsafe_allow_html=True)
    st.markdown(
        f'<div class="res-kv">'
        f'<b>Start</b><span>{_e(scn.get("disruption_start") or "—")}</span>'
        f'<b>Duration (min)</b><span>{_e(str(scn.get("duration_minutes")))}</span>'
        f'<b>Avg tx / hour</b><span>{_e(str(scn.get("avg_tx_per_hour")))} '
        f'<i>(assumption)</i></span>'
        f'<b>Failure rate %</b><span>{_e(str(scn.get("failure_rate_pct")))} '
        f'<i>(assumption)</i></span>'
        f'<b>Est. customers</b><span>{_e(str(scn.get("estimated_customers")))} '
        f'<i>(estimate)</i></span>'
        f'<b>Linked risk</b><span>{_e(scn.get("linked_risk_id") or "—")}</span>'
        f'<b>Confidence</b><span>{_e(scn.get("confidence") or "—")}</span>'
        f'</div>', unsafe_allow_html=True)
    for lab, key in (
        ("Starting conditions", "starting_conditions"),
        ("Recovery strategy", "recovery_strategy"),
        ("Recovery assumptions", "recovery_assumptions"),
        ("Control effectiveness assumptions", "control_effectiveness_assumptions"),
        ("Evidence sources", "evidence_sources"),
    ):
        st.markdown(f"**{lab}**<div class='res-quote'>{_e(scn.get(key) or '—')}</div>",
                    unsafe_allow_html=True)

    base = d["base_calc"]
    st.markdown(pane_head("Deterministic calculation (baseline)"),
                unsafe_allow_html=True)
    st.caption("All inputs below are assumptions unless marked observed.")
    st.code(
        f"outage_hours = duration_minutes / 60 "
        f"= {scn.get('duration_minutes')} / 60 = {base['outage_hours']}\n"
        f"attempted = avg_tx_per_hour × outage_hours "
        f"= {scn.get('avg_tx_per_hour')} × {base['outage_hours']} "
        f"= {base['attempted_transactions']}\n"
        f"failed = attempted × (failure_rate_pct / 100) "
        f"= {base['attempted_transactions']} × ({scn.get('failure_rate_pct')} / 100) "
        f"= {base['failed_transactions']}",
        language="text")
    tol = base["tolerance"]
    st.markdown(
        pill(tol["label"], TOL_KIND.get(tol["status"], "na"))
        + (f" · margin {tol['margin_hours']} h" if tol["margin_hours"] is not None else ""),
        unsafe_allow_html=True)
    if tol["missing_evidence"]:
        st.markdown(notice(
            "Missing evidence: " + "; ".join(_e(x) for x in tol["missing_evidence"]),
            "warn"), unsafe_allow_html=True)
    if tol["decision_required"]:
        st.caption("Management decision required.")

    st.markdown(pane_head("Arrangement comparison"), unsafe_allow_html=True)
    st.caption(
        "Compare no / weak mitigation vs tested capability. "
        "Resilience is about tested recovery, not design alone.")
    for c in d["comparisons"]:
        o = c["option"]
        calc = c["calc"]
        t = calc["tolerance"]
        st.markdown(
            f'<div class="res-opt"><b>{_e(o["label"])}</b><br>'
            f'{_e(o.get("arrangement_description") or "")}<br><br>'
            f'{pill(t["label"], TOL_KIND.get(t["status"], "na"))} '
            f'· duration {o.get("assumed_duration_minutes")} min '
            f'· failed tx {calc.get("failed_transactions")} '
            f'· customers {calc.get("estimated_customers")} '
            f'· control tested: {"yes" if int(o.get("control_tested") or 0) else "no"}'
            f'</div>',
            unsafe_allow_html=True)
        if c["assumption_deltas"]:
            st.markdown(
                "Assumptions that change:<br>" +
                "<br>".join(f"• {_e(x)}" for x in c["assumption_deltas"]),
                unsafe_allow_html=True)

    st.download_button(
        "Export scenario CSV",
        data=rs.export_scenario_csv(d),
        file_name=f"{pick}_scenario.csv",
        mime="text/csv",
        key="res_export_csv")


def _panel_summary(conn) -> None:
    scns = rs.scenarios(conn)
    runnable = scns[scns["is_template"] == 0] if not scns.empty else scns
    if runnable.empty:
        st.caption("No scenario summaries.")
        return
    ids = list(runnable["id"])
    default = "SCN-DEMO-CLOUD" if "SCN-DEMO-CLOUD" in ids else ids[0]
    pick = st.selectbox("Scenario for summary", ids, index=ids.index(default),
                        key="res_sum_pick")
    summary = rs.management_summary(conn, pick)
    st.markdown(notice(_e(summary["disclaimer"]), "warn"), unsafe_allow_html=True)
    st.markdown(f"### {_e(summary.get('title') or '')}")
    st.markdown(f'<div class="res-quote">{_e(summary.get("headline") or "")}</div>',
                unsafe_allow_html=True)

    base = summary["base"]
    st.markdown(pane_head("Results"), unsafe_allow_html=True)
    st.markdown(
        f'<div class="res-kv">'
        f'<b>Disruption duration</b>'
        f'<span>{_e(str(summary.get("duration_minutes")))} min '
        f'({base.get("outage_hours")} h)</span>'
        f'<b>Estimated affected customers</b>'
        f'<span>{_e(str(base.get("estimated_customers")))} <i>(estimate)</i></span>'
        f'<b>Estimated failed transactions</b>'
        f'<span>{_e(str(base.get("failed_transactions")))} <i>(assumption-based)</i></span>'
        f'<b>RTO achieved (baseline)</b>'
        f'<span>{_e("yes" if base.get("rto_achieved") else ("no" if base.get("rto_achieved") is False else "—"))}</span>'
        f'<b>Impact tolerance status</b>'
        f'<span>{_e(base["tolerance"]["label"])}</span>'
        f'<b>Linked risk</b><span>{_e(summary.get("linked_risk_id") or "—")}</span>'
        f'<b>Linked controls</b>'
        f'<span>{_e(", ".join(summary.get("linked_controls") or []) or "—")}</span>'
        f'</div>', unsafe_allow_html=True)

    st.markdown(pane_head("Main vulnerabilities"), unsafe_allow_html=True)
    if not summary.get("vulnerabilities"):
        st.caption("None listed.")
    else:
        for v in summary["vulnerabilities"]:
            st.markdown(f"- {_e(v)}")

    st.markdown(pane_head("Recommended resilience improvements"),
                unsafe_allow_html=True)
    acts = summary.get("actions")
    if acts is None or getattr(acts, "empty", True):
        st.caption("No actions recorded.")
    else:
        st.dataframe(acts[[
            c for c in ("id", "title", "owner", "due_at", "status",
                        "related_risk_id", "related_control_id", "rationale")
            if c in acts.columns
        ]], hide_index=True, use_container_width=True)

    text = rs.export_summary_text(summary)
    st.download_button(
        "Download management summary (.md)",
        data=text.encode("utf-8"),
        file_name=f"{pick}_management_summary.md",
        mime="text/markdown",
        key="res_export_md")
    with st.expander("Preview summary text"):
        st.markdown(text)


def _panel_concepts() -> None:
    st.markdown("""
**Important business service (IBS).** Explicit designation with rationale.
Criticality ≠ automatic IBS.

**RTO vs RPO vs impact tolerance.** Recovery objectives (how fast / how much
data loss you plan for) are not the same as the maximum disruption the firm
can tolerate for an IBS. This tool keeps them separate.

**Scenario analysis.** Deterministic arithmetic from stated assumptions.
Not Monte Carlo, not a calibrated loss model, not a forecast.

**Concentration flags.** Shared providers, missing alternatives, untested
recovery and SPOF markers are **hypotheses for validation**.

**Tested capability.** Comparing single-region vs multi-region (tested) vs
multi-region with an unresolved control deficiency shows that resilience
depends on proven recovery, not architecture diagrams alone.
""")
    st.caption(rs.METHOD_NOTE)
    st.markdown("**Formulas**")
    for k, v in rs.FORMULAS.items():
        st.code(f"{k}: {v}")
