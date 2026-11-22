"""Incident and Operational Loss Management screens.

All numbers and narrative come from orm.incident_mgmt. Synthetic demo content
is labelled. Regulatory reporting rows are assessments — never automatic
notification decisions.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import demo_data, incident_mgmt as im, risk
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

SEV_KIND = {"P1": "gap", "P2": "gap", "P3": "partial", "P4": "found"}
WF_KIND = {
    "detected": "na", "triaged": "partial", "investigating": "partial",
    "contained": "partial", "recovering": "partial", "resolved": "found",
    "post_incident_review": "partial", "closed": "found",
}
CERT_KIND = {"confirmed": "found", "estimate": "partial", "hypothesis": "na"}

CSS = """
<style>
.inc-cards {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin: 8px 0 14px;}
.inc-card {border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
  background: var(--surface);}
.inc-card .n {font-size: 22px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums;}
.inc-card .l {font-size: 12px; color: var(--ink-3); margin-top: 2px;}
.inc-kv {display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px;
  font-size: 13px; color: var(--ink-2);}
.inc-kv b {color: var(--ink); font-weight: 500;}
.inc-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 8px 0;
  white-space: pre-wrap; font-size: 13px; color: var(--ink-2);}
.inc-tl {font-size: 13px; color: var(--ink-2); margin: 4px 0;}
.inc-tl b {color: var(--ink); font-variant-numeric: tabular-nums;}
@media (max-width: 900px) {
  .inc-cards {grid-template-columns: repeat(2, minmax(0, 1fr));}
}
@media (max-width: 640px) {
  .inc-cards {grid-template-columns: 1fr;}
}
</style>
"""


def page_incidents() -> None:
    page_header("Incidents & Loss",
                "Operational incident lifecycle, loss events, root cause, "
                "remediation and regulatory reporting assessment.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            im.seed(conn, index)
            risk_views._banner(conn)
            st.markdown(notice(f"<b>Synthetic demonstration.</b> {_e(im.NOTICE)}", "warn"),
                        unsafe_allow_html=True)
            dash = im.dashboard(conn)
            _summary_cards(dash)
            tabs = st.tabs([
                "Dashboard",
                "Incident register",
                "Incident detail",
                "Remediation",
                "Loss events",
                "Concepts",
            ])
            with tabs[0]:
                _panel_dashboard(dash)
            with tabs[1]:
                _panel_register(conn, dash)
            with tabs[2]:
                _panel_detail(conn, index)
            with tabs[3]:
                _panel_remediation(conn)
            with tabs[4]:
                _panel_losses(conn)
            with tabs[5]:
                _panel_concepts()
    finally:
        ctx.__exit__(None, None, None)


def _summary_cards(dash: dict) -> None:
    reg = dash["register"]
    open_n = 0 if reg.empty else int((~reg["workflow_status"].isin(["closed"])).sum())
    overdue_n = 0 if dash["overdue_actions"].empty else len(dash["overdue_actions"])
    det = dash["avg_detection_min"]
    loss = dash["total_net_loss"]
    st.markdown(
        '<div class="inc-cards">'
        f'<div class="inc-card"><div class="n">{open_n}</div>'
        f'<div class="l">Open incidents</div></div>'
        f'<div class="inc-card"><div class="n">'
        f'{f"{det:.0f} min" if det is not None else "—"}</div>'
        f'<div class="l">Avg time to detection</div></div>'
        f'<div class="inc-card"><div class="n">{overdue_n}</div>'
        f'<div class="l">Overdue remediation actions</div></div>'
        f'<div class="inc-card"><div class="n">{loss:,.0f}</div>'
        f'<div class="l">Total net loss (all currencies mixed)</div></div>'
        "</div>", unsafe_allow_html=True)


def _panel_dashboard(dash: dict) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(pane_head("Open incidents by severity"), unsafe_allow_html=True)
        sev = dash["open_by_severity"] or {}
        if not sev:
            st.caption("No open incidents.")
        else:
            st.dataframe(
                pd.DataFrame([{"Severity": k, "Count": v} for k, v in sorted(sev.items())]),
                hide_index=True, use_container_width=True)
        st.markdown(pane_head("Open by Basel event type"), unsafe_allow_html=True)
        et = dash["open_by_event_type"] or {}
        if not et:
            st.caption("No open incidents.")
        else:
            st.dataframe(
                pd.DataFrame([{"Event type": k, "Count": v} for k, v in et.items()]),
                hide_index=True, use_container_width=True)
    with c2:
        st.markdown(pane_head("Root cause themes"), unsafe_allow_html=True)
        themes = dash["root_cause_themes"]
        if themes.empty:
            st.caption("No RCA themes recorded yet.")
        else:
            st.dataframe(themes.rename(columns={"theme": "Theme", "n": "Count"}),
                         hide_index=True, use_container_width=True)
        st.markdown(pane_head("Repeated control failures"), unsafe_allow_html=True)
        rep = dash["repeated_control_failures"]
        if rep.empty:
            st.caption("No repeated failed-control links across incidents.")
        else:
            st.dataframe(rep.rename(columns={"control_id": "Control", "n": "Incidents"}),
                         hide_index=True, use_container_width=True)
        st.markdown(pane_head("Timings (open set)"), unsafe_allow_html=True)
        det = dash["avg_detection_min"]
        rest = dash["avg_restoration_min"]
        st.markdown(
            f'<div class="inc-kv"><b>Avg detection delay</b>'
            f'<span>{f"{det:.1f} min" if det is not None else "—"}</span>'
            f'<b>Avg disruption duration</b>'
            f'<span>{f"{rest:.1f} min" if rest is not None else "—"}</span></div>',
            unsafe_allow_html=True)
        st.markdown(pane_head("Overdue actions"), unsafe_allow_html=True)
        od = dash["overdue_actions"]
        if od.empty:
            st.caption("None overdue.")
        else:
            show = od[["id", "title", "owner", "due_at", "source_id"]].head(12)
            st.dataframe(show, hide_index=True, use_container_width=True)


def _panel_register(conn, dash: dict) -> None:
    reg = dash["register"]
    st.markdown(pane_head("Incident register",
                          count=f"{len(reg)}" if not reg.empty else "0"),
                unsafe_allow_html=True)
    if reg.empty:
        st.markdown(notice("No incidents in the register."), unsafe_allow_html=True)
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        sev = st.selectbox("Severity", ["All"] + sorted(reg["severity"].dropna().unique()),
                           key="inc_reg_sev")
    with c2:
        wf = st.selectbox(
            "Workflow status",
            ["All"] + [im.WORKFLOW_LABEL[s] for s in im.WORKFLOW],
            key="inc_reg_wf")
    with c3:
        syn_only = st.checkbox("Synthetic only", value=False, key="inc_reg_syn")
    filtered = reg.copy()
    if sev != "All":
        filtered = filtered[filtered["severity"] == sev]
    if wf != "All":
        key = next(k for k, v in im.WORKFLOW_LABEL.items() if v == wf)
        filtered = filtered[filtered["workflow_status"] == key]
    if syn_only:
        filtered = filtered[filtered["is_synthetic"] == 1]
    cols = ["id", "title", "severity", "workflow_label", "occurred_at", "detected_at",
            "owner", "jurisdiction", "net_loss", "detection_delay_min",
            "disruption_duration_min", "is_synthetic"]
    show = filtered[[c for c in cols if c in filtered.columns]].rename(columns={
        "id": "ID", "title": "Title", "severity": "Severity",
        "workflow_label": "Status", "occurred_at": "Event start",
        "detected_at": "Detected", "owner": "Owner",
        "jurisdiction": "Jurisdiction", "net_loss": "Net loss",
        "detection_delay_min": "Detect (min)",
        "disruption_duration_min": "Disruption (min)",
        "is_synthetic": "Synthetic",
    })
    st.dataframe(show, hide_index=True, use_container_width=True)
    st.download_button(
        "Export register CSV",
        data=im.export_csv(filtered),
        file_name="incident_register.csv",
        mime="text/csv",
        key="inc_export")


def _panel_detail(conn, index) -> None:
    reg = im.register(conn)
    if reg.empty:
        st.caption("No incidents to open.")
        return
    labels = {r["id"]: f"{r['id']} — {r['title'][:60]}" for _, r in reg.iterrows()}
    default = "INC-DEMO-CLOUD" if "INC-DEMO-CLOUD" in labels else list(labels)[0]
    pick = st.selectbox(
        "Incident", list(labels),
        index=list(labels).index(default) if default in labels else 0,
        format_func=lambda i: labels[i], key="inc_detail_pick")
    d = im.detail(conn, pick, index_conn=index)
    inc = d["incident"]
    if d["notice"]:
        st.markdown(notice(_e(d["notice"]), "warn"), unsafe_allow_html=True)
    wf = im.current_status(inc)
    st.markdown(
        pill(im.WORKFLOW_LABEL.get(wf, wf), WF_KIND.get(wf, "na"))
        + " "
        + pill(inc.get("severity") or "—", SEV_KIND.get(inc.get("severity"), "na")),
        unsafe_allow_html=True)
    st.markdown(f"### {_e(inc.get('title') or '')}")
    st.markdown(f'<div class="inc-quote">{_e(inc.get("description") or "")}</div>',
                unsafe_allow_html=True)

    # Timeline + calculated timings
    st.markdown(pane_head("Timeline (timezone-aware)"), unsafe_allow_html=True)
    t = d["timing"]
    rows = [
        ("Event start", inc.get("occurred_at")),
        ("Detection", inc.get("detected_at")),
        ("Escalation / triage", inc.get("escalated_at")),
        ("Recovery started", inc.get("recovery_started_at")),
        ("Service restored", inc.get("restored_at")),
        ("Resolved", inc.get("resolved_at")),
        ("Closed", inc.get("closed_at")),
    ]
    html = '<div class="inc-kv">'
    for lab, val in rows:
        html += f"<b>{_e(lab)}</b><span>{_e(val or '—')}</span>"
    html += (
        f"<b>Detection delay</b><span>{_fmt_min(t['detection_delay_min'])}</span>"
        f"<b>Time to escalation</b><span>{_fmt_min(t['time_to_escalation_min'])}</span>"
        f"<b>Disruption duration</b><span>{_fmt_min(t['disruption_duration_min'])}</span>"
        f"<b>Recovery duration</b><span>{_fmt_min(t['recovery_duration_min'])}</span>"
        "</div>")
    st.markdown(html, unsafe_allow_html=True)
    if pick == "INC-DEMO-CLOUD":
        st.caption(
            "Synthetic cloud-outage walkthrough: 09:00 disruption → 09:03 KRI rise → "
            "09:05 detection → 09:08 triage → 09:15 dependency hypothesis → "
            "09:25 recovery start → 10:15 partial restoration → 10:40 normal service.")

    st.markdown(pane_head("Classification & impact"), unsafe_allow_html=True)
    st.markdown(
        f'<div class="inc-kv">'
        f'<b>Discovery source</b><span>{_e(inc.get("discovery_source") or "—")}</span>'
        f'<b>Affected service</b><span>{_e(inc.get("service_id") or "—")}</span>'
        f'<b>Business process</b><span>{_e(inc.get("business_process") or "—")}</span>'
        f'<b>Legal entity</b><span>{_e(inc.get("legal_entity") or "—")}</span>'
        f'<b>Jurisdiction</b><span>{_e(inc.get("jurisdiction") or "—")}</span>'
        f'<b>Owner</b><span>{_e(inc.get("owner") or "—")}</span>'
        f'<b>Customers affected</b><span>{_e(str(inc.get("customers_affected") or "—"))}</span>'
        f'<b>Failed transactions</b><span>{_e(str(inc.get("failed_transactions") or "—"))}</span>'
        f'</div>', unsafe_allow_html=True)
    st.markdown(
        f"**Severity rationale** (illustrative framework)<br>"
        f'<div class="inc-quote">{_e(inc.get("severity_rationale") or "—")}</div>',
        unsafe_allow_html=True)
    st.caption(d["severity_note"])
    for lab, key in (
        ("Customer impact", "customer_impact"),
        ("Financial impact", "financial_impact_note"),
        ("Regulatory impact", "regulatory_impact"),
        ("Third-party involvement", "third_party_involvement"),
    ):
        st.markdown(f"**{lab}**<div class='inc-quote'>{_e(inc.get(key) or '—')}</div>",
                    unsafe_allow_html=True)

    # Links
    st.markdown(pane_head("Linked risks, controls, KRIs"), unsafe_allow_html=True)
    if not d["links"]:
        st.caption("No links recorded.")
    else:
        st.dataframe(pd.DataFrame(d["links"])[["kind", "target_id"]].rename(
            columns={"kind": "Link kind", "target_id": "ID"}),
            hide_index=True, use_container_width=True)

    # Workflow transitions
    st.markdown(pane_head("State transitions"), unsafe_allow_html=True)
    tr = d["transitions"]
    if tr.empty:
        st.caption("No transitions logged.")
    else:
        show = tr.copy()
        show["from"] = show["from_status"].map(
            lambda s: im.WORKFLOW_LABEL.get(s, s or "—"))
        show["to"] = show["to_status"].map(lambda s: im.WORKFLOW_LABEL.get(s, s))
        st.dataframe(show[["at", "from", "to", "actor", "note"]].rename(columns={
            "at": "When", "from": "From", "to": "To", "actor": "Actor", "note": "Note"}),
            hide_index=True, use_container_width=True)

    cur = im.current_status(inc)
    allowed = im.ALLOWED.get(cur, ())
    with st.expander("Advance / reopen workflow"):
        if not allowed:
            st.caption("No further transitions from this state.")
        else:
            to = st.selectbox(
                "Next status", list(allowed),
                format_func=lambda s: im.WORKFLOW_LABEL[s], key=f"inc_tr_to_{pick}")
            actor = st.text_input("Actor (required)", key=f"inc_tr_actor_{pick}")
            note = st.text_input("Note", key=f"inc_tr_note_{pick}")
            if st.button("Record transition", key=f"inc_tr_go_{pick}"):
                try:
                    im.transition(conn, pick, to, actor=actor, note=note)
                    st.success(f"Moved to {im.WORKFLOW_LABEL[to]}.")
                    st.rerun()
                except (ValueError, LookupError) as err:
                    st.error(str(err))

    # RCA
    st.markdown(pane_head("Root cause investigation"), unsafe_allow_html=True)
    rca = d["rca"]
    if not rca:
        st.caption("No structured RCA yet.")
    else:
        for lab, key in (
            ("What happened?", "what_happened"),
            ("Immediate technical trigger", "technical_trigger"),
            ("Underlying process / control weakness", "process_weakness"),
            ("Why not detected earlier?", "detection_gap"),
            ("Controls that failed", "controls_failed"),
            ("Controls that worked", "controls_worked"),
            ("Supporting evidence", "evidence"),
            ("Unconfirmed", "unconfirmed"),
        ):
            val = rca.get(key) or "—"
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    val = "\n".join(f"• {x}" for x in parsed)
            except (TypeError, json.JSONDecodeError):
                pass
            st.markdown(f"**{lab}**<div class='inc-quote'>{_e(val)}</div>",
                        unsafe_allow_html=True)
        st.markdown("**Five Whys**")
        try:
            whys = json.loads(rca.get("five_whys_json") or "[]")
        except json.JSONDecodeError:
            whys = []
        if not whys:
            st.caption("No Five Whys recorded.")
        else:
            for i, w in enumerate(whys, 1):
                cert = (w.get("certainty") or "hypothesis").lower()
                st.markdown(
                    f"{pill(cert, CERT_KIND.get(cert, 'na'))} "
                    f"**{i}. {_e(w.get('why') or '')}**<br>"
                    f'<div class="inc-quote">{_e(w.get("answer") or "")}</div>',
                    unsafe_allow_html=True)
        st.caption("Hypotheses and estimates are labelled — not confirmed findings.")

    # Regulatory reporting assessment
    st.markdown(pane_head("Regulatory Reporting Assessment"), unsafe_allow_html=True)
    st.markdown(notice(
        "This section lists <b>potentially</b> relevant obligations for review. "
        "It does <b>not</b> conclude that a regulatory notification is mandatory. "
        "Applicability, thresholds and timing must be verified by the decision owner.",
        "warn"), unsafe_allow_html=True)
    rep = d["reporting"]
    if rep.empty:
        st.caption("No reporting assessment rows.")
    else:
        for _, r in rep.iterrows():
            cite = r.get("live_citation") or r.get("citation") or "—"
            st.markdown(
                f'<div class="inc-kv">'
                f'<b>Obligation / source</b><span>{_e(cite)}</span>'
                f'<b>Jurisdiction</b><span>{_e(r.get("jurisdiction") or "—")}</span>'
                f'<b>Trigger criteria</b><span>{_e(r.get("trigger_criteria") or "—")}</span>'
                f'<b>Required review</b><span>{_e(r.get("review_required") or "—")}</span>'
                f'<b>Evidence</b><span>{_e(r.get("evidence") or "—")}</span>'
                f'<b>Decision owner</b><span>{_e(r.get("decision_owner") or "—")}</span>'
                f'<b>Reporting status</b><span>{_e(r.get("reporting_status") or "—")}</span>'
                f'<b>Decision note</b><span>{_e(r.get("decision_note") or "—")}</span>'
                f'</div>', unsafe_allow_html=True)

    # Remediation on this incident
    st.markdown(pane_head("Corrective actions"), unsafe_allow_html=True)
    acts = d["actions"]
    if acts.empty:
        st.caption("No remediation actions linked.")
    else:
        cols = [c for c in (
            "id", "title", "owner", "due_at", "priority", "status",
            "control_deficiency", "related_risk_id", "evidence_required",
            "closure_reviewer", "validation_outcome", "overdue") if c in acts.columns]
        st.dataframe(acts[cols], hide_index=True, use_container_width=True)

    if inc.get("lessons_learned"):
        st.markdown(pane_head("Lessons learned"), unsafe_allow_html=True)
        st.markdown(f'<div class="inc-quote">{_e(inc["lessons_learned"])}</div>',
                    unsafe_allow_html=True)


def _panel_remediation(conn) -> None:
    acts = risk.actions(conn)
    if acts.empty:
        st.caption("No actions.")
        return
    inc_acts = acts[acts["source_kind"] == "incident"] if not acts.empty else acts
    st.markdown(pane_head("Incident remediation actions",
                          count=str(len(inc_acts))), unsafe_allow_html=True)
    st.caption(
        "Owner completion does not equal independent validation. "
        "Validation outcome stays pending until a named reviewer confirms.")
    if not inc_acts.empty:
        st.dataframe(inc_acts[[
            c for c in ("id", "source_id", "title", "owner", "due_at", "priority",
                        "status", "control_deficiency", "related_risk_id",
                        "evidence_required", "validation_outcome",
                        "closure_reviewer", "overdue") if c in inc_acts.columns
        ]], hide_index=True, use_container_width=True)

    ids = list(inc_acts["id"]) if not inc_acts.empty else []
    if not ids:
        return
    pick = st.selectbox("Action", ids, key="inc_act_pick")
    row = inc_acts[inc_acts["id"] == pick].iloc[0]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Owner marks complete**")
        owner = st.text_input("Owner name", value=row.get("owner") or "",
                              key="inc_act_owner")
        ev = st.text_input("Evidence attached", key="inc_act_ev")
        if st.button("Mark owner-complete", key="inc_act_done"):
            try:
                im.mark_owner_complete(conn, pick, owner=owner, evidence=ev)
                st.success("Marked done by owner — validation still pending.")
                st.rerun()
            except ValueError as err:
                st.error(str(err))
    with c2:
        st.markdown("**Independent validation**")
        reviewer = st.text_input("Closure reviewer", key="inc_act_rev")
        outcome = st.selectbox("Outcome", ["validated", "rejected", "pending"],
                               key="inc_act_out")
        ev2 = st.text_input("Reviewer evidence note", key="inc_act_ev2")
        if st.button("Record validation", key="inc_act_val"):
            try:
                im.validate_action_closure(
                    conn, pick, outcome=outcome, reviewer=reviewer, evidence=ev2)
                st.success(f"Validation recorded: {outcome}.")
                st.rerun()
            except ValueError as err:
                st.error(str(err))


def _panel_losses(conn) -> None:
    losses = risk._df(conn, """
        SELECT l.*, i.title AS incident_title FROM incident_loss l
        LEFT JOIN incident i ON i.id = l.incident_id
        ORDER BY l.recognition_date DESC, l.id""")
    st.markdown(pane_head("Loss events (separate from incidents)"),
                unsafe_allow_html=True)
    st.caption(
        "An incident may have zero financial loss. Financial loss is not the only "
        "measure of operational impact. Certainty labels: confirmed / estimate / hypothesis.")
    if losses.empty:
        st.caption("No loss events recorded.")
        return
    view = losses.copy()
    view["net"] = view["gross_loss"].fillna(0) - view["recovered"].fillna(0)
    st.dataframe(view[[
        "id", "incident_id", "incident_title", "gross_loss", "recovered", "net",
        "currency", "loss_category", "recognition_date", "certainty",
        "evidence_ref", "is_synthetic",
    ]].rename(columns={
        "id": "Loss ID", "incident_id": "Incident", "incident_title": "Title",
        "gross_loss": "Gross", "recovered": "Recoveries", "net": "Net",
        "currency": "CCY", "loss_category": "Category",
        "recognition_date": "Recognised", "certainty": "Certainty",
        "evidence_ref": "Evidence", "is_synthetic": "Synthetic",
    }), hide_index=True, use_container_width=True)


def _panel_concepts() -> None:
    st.markdown("""
**Incident vs loss.** An incident is an operational event. A loss event is a
financial recognition that may (or may not) attach to an incident.

**Workflow.** Detected → Triaged → Investigating → Contained → Recovering →
Resolved → Post-Incident Review → Closed. Closed incidents can be reopened to
Investigating. Every transition stores actor + timestamp.

**Severity.** Configurable illustrative scale (P1–P4). Ratings must state a
rationale covering customer impact, failed transactions, duration, financial
impact, critical-service availability, data integrity, regulatory consequences
and recovery progress. This is **not** any bank's official severity framework.

**Certainty.** Fields distinguish confirmed facts, estimates and hypotheses.
AI or analyst hypotheses are never shown as confirmed findings.

**Remediation.** Owner completion ≠ independent validation. Closure requires a
named reviewer and a validation outcome.

**Regulatory reporting.** The assessment lists potentially relevant obligations
for Compliance review. The system never auto-concludes that a notification is
mandatory.
""")
    st.caption(im.SEVERITY_FRAMEWORK_NOTE)


def _fmt_min(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:.0f} min"
