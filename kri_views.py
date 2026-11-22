"""KRI and Risk Appetite dashboard.

Observations and thresholds come from orm.kri_appetite — never hard-coded in
the UI. Synthetic demo values are labelled. No external alerts are sent.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import demo_data, kri_appetite as ka, risk
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}
RAG_KIND = risk_views.RAG_KIND

CSS = """
<style>
.kri-cards {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin: 8px 0 14px;}
.kri-card {border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
  background: var(--surface);}
.kri-card .n {font-size: 22px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums;}
.kri-card .l {font-size: 12px; color: var(--ink-3); margin-top: 2px;}
.kri-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 8px 0;
  white-space: pre-wrap; font-size: 13px; color: var(--ink-2);}
@media (max-width: 900px) {
  .kri-cards {grid-template-columns: repeat(2, minmax(0, 1fr));}
}
@media (max-width: 640px) {
  .kri-cards {grid-template-columns: 1fr;}
}
</style>
"""


def page_kri() -> None:
    page_header("KRI & Appetite", "Monitor key risk indicators, appetite and "
                "tolerances, and escalate breaches with an auditable trail.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            ka.seed(conn)
            risk_views._banner(conn)
            st.markdown(notice(f"<b>Synthetic demonstration.</b> {_e(ka.NOTICE)}", "warn"),
                        unsafe_allow_html=True)
            dash = ka.dashboard(conn)
            _cards(dash["cards"])
            tabs = st.tabs([
                "Dashboard",
                "Indicator detail",
                "Escalation queue",
                "Appetite & concepts",
                "Upload observations",
            ])
            with tabs[0]:
                _panel_dashboard(conn, dash)
            with tabs[1]:
                _panel_detail(conn, dash)
            with tabs[2]:
                _panel_escalations(conn)
            with tabs[3]:
                _panel_appetite(dash)
            with tabs[4]:
                _panel_upload(conn)
    finally:
        ctx.__exit__(None, None, None)


def _cards(cards: dict) -> None:
    st.markdown(
        '<div class="kri-cards">'
        f'<div class="kri-card"><div class="n">{cards["active_breaches"]}</div>'
        f'<div class="l">Active Red breaches</div></div>'
        f'<div class="kri-card"><div class="n">{cards["warning_indicators"]}</div>'
        f'<div class="l">Warning (Amber) indicators</div></div>'
        f'<div class="kri-card"><div class="n">{cards["risks_exceeding_appetite"]}</div>'
        f'<div class="l">Risks exceeding appetite</div></div>'
        f'<div class="kri-card"><div class="n">{cards["overdue_actions"]}</div>'
        f'<div class="l">Overdue remediation actions</div></div>'
        "</div>", unsafe_allow_html=True)


def _panel_dashboard(conn, dash: dict) -> None:
    lib = dash["library"]
    if lib.empty:
        st.markdown(notice("No KRIs in the catalogue yet."), unsafe_allow_html=True)
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        procs = ["All"] + sorted({p for p in lib["business_process"].dropna() if p})
        proc = st.selectbox("Business process", procs, key="kri_f_proc")
    with c2:
        ents = ["All"] + sorted({e for e in lib["legal_entity"].dropna() if e})
        ent = st.selectbox("Legal entity", ents, key="kri_f_ent")
    with c3:
        owners = ["All"] + sorted({o for o in lib["metric_owner"].fillna(lib["owner"]).dropna() if o})
        owner = st.selectbox("Metric owner", owners, key="kri_f_own")
    with c4:
        sev = st.selectbox("Severity", ["All", "Red", "Amber", "Green", "No data"],
                           key="kri_f_sev")
    filtered = ka.filter_library(
        lib,
        business_process="" if proc == "All" else proc,
        legal_entity="" if ent == "All" else ent,
        owner="" if owner == "All" else owner,
        severity="" if sev == "All" else sev)
    st.markdown(pane_head("KRI status", count=f"{len(filtered)}"), unsafe_allow_html=True)
    show = filtered[[
        "id", "name", "rag", "value", "unit", "green_limit", "amber_limit",
        "leading_lagging", "business_process", "metric_owner", "linked_risks",
    ]].rename(columns={
        "id": "KRI ID", "name": "Name", "rag": "Status", "value": "Latest",
        "unit": "Unit", "green_limit": "Green", "amber_limit": "Amber",
        "leading_lagging": "Type", "business_process": "Process",
        "metric_owner": "Owner", "linked_risks": "Linked risks",
    })
    st.dataframe(show, hide_index=True, width="stretch")

    # Trend chart for payment failure (interview centrepiece) when present.
    if "KRI-PAY-FAIL" in lib["id"].values:
        st.markdown(pane_head("Interview demo — Payment Transaction Failure Rate"),
                    unsafe_allow_html=True)
        hist = risk.kri_readings(conn, "KRI-PAY-FAIL")
        if not hist.empty:
            chart = hist[["period", "value"]].rename(
                columns={"period": "Period", "value": "Failure rate %"})
            st.line_chart(chart.set_index("Period"))
            st.caption("Illustrative thresholds: green ≤ 0.5% · amber ≤ 1.0% · red > 1.0%. "
                       "Series is synthetic and internally consistent (e.g. 300/100,000 = 0.3% "
                       "→ 1,800/100,000 = 1.8%).")
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else None
            tr = ka.trend(latest["value"], None if prev is None else prev["value"],
                          "higher_is_worse")
            st.markdown(
                f"Latest **{latest['value']:g}%** ({latest['rag']}) · previous "
                f"**{(prev['value'] if prev is not None else float('nan')):g}%** · "
                f"trend **{tr}**.")


def _panel_detail(conn, dash: dict) -> None:
    lib = dash["library"]
    if lib.empty:
        return
    ids = lib["id"].tolist()
    default = ids.index("KRI-PAY-FAIL") if "KRI-PAY-FAIL" in ids else 0
    labels = dict(zip(lib["id"], lib["id"] + " · " + lib["name"]))
    kri_id = st.selectbox("Open a KRI", ids, index=default, key="kri_detail",
                          format_func=labels.get)
    row = lib[lib["id"] == kri_id].iloc[0]
    st.markdown(pane_head(f"{row['id']} · {row['name']}"), unsafe_allow_html=True)
    st.markdown(pill(row["rag"], RAG_KIND.get(row["rag"], "na")), unsafe_allow_html=True)
    st.markdown(
        '<div class="rk-kv">' + "".join(
            f"<span>{_e(k)}</span><b>{_e(v)}</b>" for k, v in [
                ("Description", row.get("description") or row.get("definition") or ""),
                ("Formula", row.get("formula") or row.get("definition") or ""),
                ("Classification", row.get("classification") or ""),
                ("Direction", "Higher is worse" if row["direction"] == "higher_is_worse"
                 else "Lower is worse"),
                ("Green / Amber (illustrative)",
                 f"{row['green_limit']:g} / {row['amber_limit']:g} {row['unit']}"),
                ("Baseline (illustrative)", f"{row['baseline']:g}" if pd.notna(row.get("baseline")) else "—"),
                ("Business process", row.get("business_process") or "—"),
                ("Legal entity", row.get("legal_entity") or "—"),
                ("Metric owner", row.get("metric_owner") or row.get("owner") or "—"),
                ("Risk owner", row.get("risk_owner") or "—"),
                ("Data source", row.get("data_source") or "—"),
                ("Frequency", row.get("collection_frequency") or row.get("frequency") or "—"),
                ("Measurement period", row.get("measurement_period") or "—"),
                ("Reporting audience", row.get("reporting_audience") or "—"),
                ("Escalation rules", row.get("escalation_rules") or "—"),
                ("Linked risks", row.get("linked_risks") or "—"),
                ("Last validated", row.get("last_validated_at") or "—"),
                ("Appetite link", row.get("appetite_statement_id") or "—"),
            ] if v not in (None, "")) + "</div>", unsafe_allow_html=True)
    excl = row.get("exclusions_json") or ""
    if excl:
        try:
            items = json.loads(excl)
            st.caption("Configurable exclusions: " + "; ".join(items))
        except Exception:
            pass

    hist = risk.kri_readings(conn, kri_id)
    obs = ka.observations(conn, kri_id)
    if not hist.empty:
        st.markdown(pane_head("Trend", count=f"{len(hist)} periods"),
                    unsafe_allow_html=True)
        st.line_chart(hist.set_index("period")[["value"]])
        latest, prev = hist.iloc[-1], (hist.iloc[-2] if len(hist) > 1 else None)
        st.markdown(
            f"Current **{latest['value']:g}** · previous "
            f"**{prev['value']:g}** · {ka.trend(latest['value'], prev['value'] if prev is not None else None, row['direction'])}"
            if prev is not None else f"Current **{latest['value']:g}**")
    if not obs.empty:
        st.markdown(pane_head("Observations (numerator / denominator)"),
                    unsafe_allow_html=True)
        st.dataframe(obs[[
            "period", "observed_at", "numerator", "denominator", "value", "source", "note"
        ]].tail(15), hide_index=True, width="stretch")

    # Linked risk register rows
    risk_ids = [x for x in str(row.get("linked_risks") or "").split(",") if x]
    reg = dash["register"]
    if risk_ids and not reg.empty:
        linked = reg[reg["id"].isin(risk_ids)]
        if not linked.empty:
            st.markdown(pane_head("Linked risks"), unsafe_allow_html=True)
            st.dataframe(linked[["id", "title", "residual_score", "appetite", "owner"]],
                         hide_index=True, width="stretch")


def _panel_escalations(conn) -> None:
    name = controls_views._reviewer_box("kri_esc_name")
    esc = ka.escalations(conn)
    if esc.empty:
        st.markdown(notice("No escalations recorded."), unsafe_allow_html=True)
        return
    open_ = esc[esc["ack_status"].isin(["open", "acknowledged", "actioned"])]
    st.markdown(pane_head("Escalation queue", count=f"{len(open_)} open-ish"),
                unsafe_allow_html=True)
    st.dataframe(esc[[
        "id", "kri_id", "period", "status_rag", "value", "triggered_at",
        "owner", "ack_status", "action_id",
    ]], hide_index=True, width="stretch")
    ids = esc["id"].tolist()
    pick = st.selectbox("Open escalation", ids, key="kri_esc_pick")
    row = esc[esc["id"] == pick].iloc[0]
    st.markdown(f"**Recommendation**")
    st.markdown(f'<div class="kri-quote">{_e(row["recommendation"] or "")}</div>',
                unsafe_allow_html=True)
    commentary = st.text_area(
        "Management commentary (editable draft — facts vs hypotheses)",
        value=row.get("commentary") or "", key=f"kri_com_{pick}", height=260)
    if st.button("Save commentary edits", key="kri_com_save", disabled=not name):
        risk.update(conn, "kri_escalation", pick, {"commentary": commentary},
                    actor=name)
        conn.commit()
        st.success("Commentary saved.")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Acknowledge", key="kri_ack", disabled=not name):
            ka.acknowledge_escalation(conn, pick, actor=name)
            conn.commit()
            st.rerun()
    with c2:
        if st.button("Create investigation action", key="kri_act", disabled=not name):
            ka.approve_escalation_action(conn, pick, actor=name)
            conn.commit()
            st.success("Remediation / investigation action created (no email sent).")
            st.rerun()
    with c3:
        st.caption("External notifications are never sent automatically.")


def _panel_appetite(dash: dict) -> None:
    st.markdown(pane_head("Risk appetite statements (synthetic)"),
                unsafe_allow_html=True)
    app = dash["appetite"]
    if app.empty:
        st.markdown(notice("No appetite statements loaded."), unsafe_allow_html=True)
    else:
        for _, r in app.iterrows():
            st.markdown(
                f'<div class="card"><b>{_e(r["id"])} · {_e(r["title"])}</b> '
                f'{pill(r["kind"], "partial")}'
                f'<div class="kri-quote">{_e(r["statement"])}</div>'
                f'<div class="rk-note">{_e(r["legal_entity"])} · '
                f'{_e(r["business_process"])} · approved by {_e(r["approved_by"])}</div>'
                f"</div>", unsafe_allow_html=True)
    st.markdown(pane_head("Concepts — not interchangeable"), unsafe_allow_html=True)
    for title, body in ka.concepts_glossary():
        st.markdown(f"**{title}.** {body}")


def _panel_upload(conn) -> None:
    st.caption("Ingest observations from CSV. Columns: kri_id, period, observed_at, "
               "numerator, denominator[, value, note, unit]. Deterministic formulas "
               "compute the rate when numerator/denominator are supplied.")
    name = controls_views._reviewer_box("kri_up_name")
    sample = (
        "kri_id,period,observed_at,numerator,denominator,note\n"
        "KRI-PAY-FAIL,2099-01-01,2099-01-01T12:00:00+00:00,500,100000,Illustrative upload\n"
    )
    st.download_button("Download CSV template", sample.encode("utf-8"),
                       file_name="kri_observations_template.csv", mime="text/csv",
                       key="kri_tmpl")
    up = st.file_uploader("CSV file", type=["csv"], key="kri_csv")
    if up and st.button("Ingest CSV", key="kri_ingest", disabled=not name):
        text = up.read().decode("utf-8")
        results = ka.ingest_csv(conn, text, actor=name, is_synthetic=0)
        conn.commit()
        st.success(f"Ingested {len(results)} observation(s).")
        for r in results[:5]:
            st.write(r)
