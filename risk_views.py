"""The risk workspace: Risk register and Management report.

Regulation -> obligation -> risk -> control -> KRI -> incident -> action ->
report. Data and scoring live in orm.risk / orm.risk_report; the demo data is
synthetic (orm.demo_data) and every screen says so. This file only renders.
Look and wording follow DESIGN.md.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pandas as pd
import streamlit as st

import controls_views
from orm import demo_data, risk, risk_report
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

RAG_KIND = {"Green": "found", "Amber": "partial", "Red": "gap", "No data": "na"}
APPETITE_KIND = {"Outside appetite": "gap", "Within appetite": "found",
                 "No appetite set": "na"}
RATING_KIND = {"effective": "found", "partially_effective": "partial",
               "ineffective": "gap", "not_tested": "na"}
BAND_KIND = {"Low": "found", "Moderate": "partial", "Medium": "partial",
             "High": "gap", "Critical": "gap"}

CSS = """
<style>
.rk-heat {display: grid; grid-template-columns: 28px repeat(5, minmax(44px, 1fr));
  gap: 3px; max-width: 420px; font-size: 12px; font-variant-numeric: tabular-nums;}
.rk-heat .ax {color: var(--ink-3); display: flex; align-items: center; justify-content: center;}
.rk-cell {border-radius: 6px; min-height: 40px; padding: 4px; display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  color: var(--ink-2); border: 1px solid var(--line);}
.rk-cell b {font-size: 14px; color: var(--ink);}
.rk-cell.low {background: var(--found-bg);}
.rk-cell.medium {background: var(--partial-bg);}
.rk-cell.high {background: var(--gap-bg);}
.rk-cell.critical {background: #f7d4d0;}
.rk-heat-cap {font-size: 12px; color: var(--ink-3); margin-top: 6px;}
.rk-quote {border-left: 3px solid var(--line); padding-left: 10px; margin: 4px 0 2px;}
.rk-trend {font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums;}
.rk-kv {display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px;
  font-size: 13px; color: var(--ink-2);}
.rk-kv b {color: var(--ink); font-weight: 500;}
.rk-scores {display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 13px;
  color: var(--ink-2); margin: 10px 0 12px; font-variant-numeric: tabular-nums;}
.rk-scores b {color: var(--ink); font-weight: 600;}
.rk-note {font-size: 12.5px; color: var(--ink-3); margin-top: 4px;}
.rk-scroll {overflow-x: auto; max-width: 100%; -webkit-overflow-scrolling: touch;}
.rk-scroll .ws-table {min-width: 560px;}
@media (max-width: 640px) {
  .rk-heat {grid-template-columns: 22px repeat(5, minmax(0, 1fr));}
  .rk-cell {min-height: 34px;}
}
</style>
"""


# --- shared ----------------------------------------------------------------------

@contextmanager
def _stores():
    """(risk store, regulation index). Loads the synthetic demo the first time."""
    ctx, index = controls_views._open()
    try:
        st.markdown(CSS, unsafe_allow_html=True)
        with risk.session() as conn:
            demo_data.seed(conn, index)
            yield conn, index
    finally:
        ctx.__exit__(None, None, None)


def _banner(conn) -> None:
    if not risk.is_synthetic(conn):
        return
    bank = risk.get_meta(conn, "bank") or "a fictional bank"
    st.markdown(notice(
        f"<b>Synthetic demonstration data.</b> {_e(bank)}: its services, risks, "
        "controls, test results, KRIs, incidents and losses are invented. Only the "
        "regulation quotes come from the indexed Bank of Israel texts.", "warn"),
        unsafe_allow_html=True)
    missing = json.loads(risk.get_meta(conn, "missing_links") or "[]")
    if missing:
        st.markdown(notice(
            f"{len(missing)} regulation links were not found in this index and were "
            "left out rather than typed in: " + _e("; ".join(missing)) + "."),
            unsafe_allow_html=True)


def _status_line(items: list[tuple[str, str]]) -> str:
    return '<div class="ws-status">' + "".join(
        f"<span><b>{_e(v)}</b> {_e(k)}</span>" for k, v in items) + "</div>"


def _heat(reg: pd.DataFrame) -> str:
    cells = ['<div class="rk-heat"><div class="ax"></div>']
    cells += [f'<div class="ax">L{i}</div>' for i in range(1, 6)]
    for impact in range(5, 0, -1):
        cells.append(f'<div class="ax">I{impact}</div>')
        for like in range(1, 6):
            ids = reg[(reg["residual_impact"] == impact)
                      & (reg["residual_likelihood"] == like)]["id"].tolist() \
                if not reg.empty else []
            kind = risk.band(like * impact).lower()
            body = (f"<b>{len(ids)}</b><span>{_e(' '.join(i.replace('RSK-', '') for i in ids))}"
                    "</span>") if ids else ""
            cells.append(f'<div class="rk-cell {kind}" title="Likelihood {like} × impact '
                         f'{impact}: {risk.band(like * impact)}">{body}</div>')
    cells.append("</div>")
    cells.append('<div class="rk-heat-cap">Residual risk: likelihood (L) across, impact '
                 '(I) up. Numbers are risk IDs.</div>')
    return "".join(cells)


def _register_table(reg: pd.DataFrame) -> str:
    rows = []
    for _, r in reg.iterrows():
        override = ' <span class="sub">override</span>' if r["residual_overridden"] else ""
        rows.append(
            f'<tr><td class="cat">{_e(r["id"])} · {_e(r["title"])}'
            f'<small>{_e(r["category"])} · {_e(r["owner"])}</small></td>'
            f'<td class="n">{r["inherent_score"]} {pill(r["inherent_band"], BAND_KIND[r["inherent_band"]])}</td>'
            f'<td class="n">{r["residual_score"]} {pill(r["residual_band"], BAND_KIND[r["residual_band"]])}{override}</td>'
            f'<td>{pill(r["appetite"], APPETITE_KIND[r["appetite"]])}</td>'
            f'<td class="n">{r["kri_red"]} red · {r["kri_amber"]} amber</td>'
            f'<td class="n">{r["controls"]}<div class="sub">{r["weak_controls"]} not effective</div></td>'
            f'<td class="n">{r["open_actions"]}<div class="sub">{r["overdue_actions"]} overdue</div></td>'
            f'<td class="n">{r["obligations"]}</td></tr>')
    return _scroll('<table class="ws-table"><thead><tr><th>Risk</th><th>Inherent</th>'
                   '<th>Residual</th><th>Appetite</th><th>KRIs</th><th>Key controls</th>'
                   '<th>Open actions</th><th>Regulation links</th></tr></thead><tbody>'
                   + "".join(rows) + "</tbody></table>")


def _scroll(table_html: str) -> str:
    """Wide tables scroll sideways on a phone instead of overflowing the page."""
    return f'<div class="rk-scroll">{table_html}</div>'


def _fmt_minutes(m) -> str:
    if m is None or pd.isna(m):
        return "not recorded"
    m = int(m)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


# --- Risk register -----------------------------------------------------------------

def page_risks() -> None:
    page_header("Risk register", "Operational risks with inherent and residual scores, "
                "the regulation behind each one, and its controls, KRIs, incidents and "
                "actions.")
    with _stores() as (conn, index):
        _banner(conn)
        reg = risk.register(conn)
        if reg.empty:
            st.markdown(notice("No risks recorded yet."), unsafe_allow_html=True)
            return
        st.markdown(_status_line([
            ("open risks", str(len(reg))),
            ("outside appetite", str(int((reg["appetite"] == "Outside appetite").sum()))),
            ("KRIs red", str(int(reg["kri_red"].sum()))),
            ("open actions", str(int(reg["open_actions"].sum()))),
            ("overdue", str(int(reg["overdue_actions"].sum()))),
        ]), unsafe_allow_html=True)
        left, right = st.columns([1, 2.2])
        with left:
            st.markdown(pane_head("Residual heat map"), unsafe_allow_html=True)
            st.markdown(_heat(reg), unsafe_allow_html=True)
        with right:
            st.markdown(pane_head("Register", count=f"{len(reg)} risks"),
                        unsafe_allow_html=True)
            st.markdown(_register_table(reg), unsafe_allow_html=True)
        st.caption(risk.METHOD_NOTE)

        ids = reg["id"].tolist()
        labels = dict(zip(reg["id"], reg["id"] + " · " + reg["title"]))
        risk_id = st.selectbox("Open a risk", ids, key="rk_risk", format_func=labels.get)
        _render_chain(conn, index, risk_id)
        _render_demo_tools(conn, index)


def _render_chain(conn, index, risk_id: str) -> None:
    chain = risk.risk_chain(conn, risk_id, index)
    r, s = chain["risk"], chain["summary"]
    st.markdown(pane_head(f"{r['id']} · {r['title']}"), unsafe_allow_html=True)
    svc = chain["service"]
    facts = [("Owner", r["owner"]), ("Category", s.get("category", "")),
             ("Event type", r["event_type"]), ("Cause", r["cause"]), ("Effect", r["effect"]),
             ("Service", f"{svc['name']} · {svc['criticality']} · impact tolerance "
                         f"{svc['impact_tolerance_hours']:g} h · RTO {svc['rto_hours']:g} h"
              if svc else "Not linked to a business service"),
             ("Assessed", f"{r['assessed_at'] or 'not yet'} · next review "
                          f"{r['next_review_at'] or 'not set'}"),
             ("Record", f"{r['validation_status']} · {r['provenance']}")]
    st.markdown('<div class="rk-kv">' + "".join(
        f"<span>{_e(k)}</span><b>{_e(v)}</b>" for k, v in facts if v) + "</div>",
        unsafe_allow_html=True)
    limit = f" · limit {s['appetite_limit']}" if s["appetite_limit"] else ""
    st.markdown(
        '<div class="rk-scores">'
        f'<span>Inherent <b>{s["inherent_score"]}</b> '
        f'{pill(s["inherent_band"], BAND_KIND[s["inherent_band"]])} '
        f'L{s["inherent_likelihood"]} × I{s["inherent_impact"]}</span>'
        f'<span>Residual <b>{s["residual_score"]}</b> '
        f'{pill(s["residual_band"], BAND_KIND[s["residual_band"]])} '
        f'L{s["residual_likelihood"]} × I{s["residual_impact"]}'
        f'{" · assessor override" if s["residual_overridden"] else ""}</span>'
        f'<span>{pill(s["appetite"], APPETITE_KIND[s["appetite"]])}{_e(limit)}</span>'
        '</div>', unsafe_allow_html=True)
    controls_views._reviewer_box("rk_reviewer")

    regs, ctl, kris, incs, acts, assess = st.tabs(
        ["Regulation", "Controls", "KRIs", "Incidents", "Actions", "Assessment and history"])
    with regs:
        _render_obligations(conn, risk_id, chain["obligations"])
    with ctl:
        _render_controls(chain["controls"])
    with kris:
        _render_kris(conn, chain["kris"])
    with incs:
        _render_incidents(chain["incidents"], chain["incident_links"], index)
    with acts:
        _render_actions(chain["actions"])
    with assess:
        _render_assessment(conn, r, s)


def _render_obligations(conn, risk_id: str, obl: pd.DataFrame) -> None:
    if obl.empty:
        st.markdown(notice("No regulation linked to this risk yet."), unsafe_allow_html=True)
        return
    st.caption("Each link is a suggestion until a named person validates it. A difference "
               "or a link is not a compliance conclusion.")
    for _, o in obl.iterrows():
        status = {"validated": pill("Validated", "found"),
                  "rejected": pill("Rejected", "na")}.get(
            o["validation_status"], pill("Suggested: verify", "na"))
        source = "" if o["source_state"] == "current" else (
            pill("Source text changed: re-validate", "gap")
            if o["source_state"] == "source changed" else pill("Not checked", "na"))
        link = (f'<a href="{_e(o["link"])}" target="_blank">Open in source ↗</a>'
                if o["link"] else "")
        st.markdown(
            f'<div class="card"><div class="cite"><b>{_e(o["citation"])}</b>{link}</div>'
            f'<div class="law rk-quote">{_e(o["sentence"])}</div>'
            f'<div class="rk-note">Why it applies: {_e(o["rationale"] or "not stated")}</div>'
            f'<div style="margin-top:6px">{status} {source}</div></div>',
            unsafe_allow_html=True)
        if o["validation_status"] == "suggested":
            c1, c2, _ = st.columns([1, 1, 4])
            choice = None
            with c1:
                if st.button("Validate", key=f"rk_val_{risk_id}_{o['okey']}"):
                    choice = "validated"
            with c2:
                if st.button("Reject", key=f"rk_rej_{risk_id}_{o['okey']}"):
                    choice = "rejected"
            if choice:
                name = controls_views._reviewer()
                if not name:
                    st.warning("Enter your name above first; every decision is "
                               "recorded with it.")
                else:
                    risk.update(conn, "risk_obligation", (risk_id, o["okey"]),
                                {"validation_status": choice}, actor=name)
                    conn.commit()
                    st.rerun()


def _render_controls(ctl: pd.DataFrame) -> None:
    if ctl.empty:
        st.markdown(notice("No controls linked to this risk."), unsafe_allow_html=True)
        return
    rows = []
    for _, c in ctl.iterrows():
        rating = c["rating"]
        lib = f'<div class="sub">Library: {_e(c["library_id"])} · {_e(c["library_name"])}</div>' \
            if c["library_name"] else ""
        rows.append(
            f'<tr><td class="cat">{_e(c["id"])} · {_e(c["name"])}'
            f'<small>{_e(c["type"])} · {_e(c["nature"])} · {_e(c["frequency"])} · '
            f'{_e(c["owner"])}</small>{lib}</td>'
            f'<td>reduces {_e(c["reduces"])}</td>'
            f'<td>{pill(risk.RATING_LABEL.get(c["design_rating"], "Not tested"), RATING_KIND.get(c["design_rating"], "na"))}</td>'
            f'<td>{pill(risk.RATING_LABEL.get(c["operating_rating"], "Not tested"), RATING_KIND.get(c["operating_rating"], "na"))}</td>'
            f'<td>{pill(risk.RATING_LABEL[rating], RATING_KIND[rating])}</td>'
            f'<td>{_e(c["tested_at"] or "never")}<div class="ev">{_e(c["findings"] or "")}</div></td></tr>')
    st.markdown(_scroll('<table class="ws-table"><thead><tr><th>Control</th><th>Effect</th>'
                        '<th>Design</th><th>Operating</th><th>Overall</th><th>Last test</th>'
                        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table>"),
                unsafe_allow_html=True)


def _render_kris(conn, kris: pd.DataFrame) -> None:
    if kris.empty:
        st.markdown(notice("No KRIs set for this risk."), unsafe_allow_html=True)
        return
    for _, k in kris.iterrows():
        hist = risk.kri_readings(conn, k["id"])
        trend = " → ".join(f"{v:g}" for v in hist["value"]) if not hist.empty else "no readings"
        better = "lower is better" if k["direction"] == "higher_is_worse" else "higher is better"
        latest = "no reading" if pd.isna(k["value"]) else f"{k['value']:g} {k['unit']}"
        st.markdown(
            f'<div class="card"><b>{_e(k["id"])} · {_e(k["name"])}</b> '
            f'{pill(k["rag"], RAG_KIND[k["rag"]])}'
            f'<div class="rk-note">{_e(k["definition"])}</div>'
            f'<div class="rk-kv" style="margin-top:6px"><span>Latest</span><b>{_e(latest)}'
            f' ({_e(k["period"] or "")})</b><span>Limits</span><b>green {k["green_limit"]:g}'
            f' · amber {k["amber_limit"]:g} · {_e(better)}</b><span>Last 6 periods</span>'
            f'<b class="rk-trend">{_e(trend)}</b><span>Source</span>'
            f'<b>{_e(k["data_source"])} · {_e(k["owner"])}</b></div></div>',
            unsafe_allow_html=True)


def _render_incidents(inc: pd.DataFrame, links: dict, index) -> None:
    if inc.empty:
        st.markdown(notice("No incidents linked to this risk."), unsafe_allow_html=True)
        return
    for _, i in inc.iterrows():
        breached = i["tolerance_breached"]
        tol = ("" if breached is None or pd.isna(breached) else
               pill("Impact tolerance exceeded", "gap") if breached else
               pill("Within impact tolerance", "found"))
        timeline = [("Occurred", i["occurred_at"]), ("Detected", i["detected_at"]),
                    ("Escalated", i["escalated_at"]),
                    ("Regulator notified", i["regulator_notified_at"]),
                    ("Resolved", i["resolved_at"])]
        mine = links.get(i["id"], [])
        failed = [lnk["target_id"] for lnk in mine if lnk["kind"] == "failed_control"]
        notes = [lnk["target_id"] for lnk in mine if lnk["kind"] == "notification_obligation"]
        cite_html = ""
        for okey in notes:
            c = risk.obligation_citation(index, okey) if index is not None else None
            cite_html += (
                f'<div class="cite" style="margin-top:8px">Notification obligation · '
                f'<b>{_e(c["citation"])}</b></div><div class="law rk-quote">'
                f'{_e(c["sentence"])}</div>' if c else
                notice("The linked notification obligation is no longer in the index: "
                       "re-validate."))
        st.markdown(
            f'<div class="card"><b>{_e(i["id"])} · {_e(i["title"])}</b> '
            f'{pill(i["severity"] or "", "partial")} {tol}'
            f'<div class="rk-note">{_e(i["description"])}</div>'
            '<div class="rk-kv" style="margin-top:6px">'
            + "".join(f"<span>{_e(k)}</span><b>{_e((v or 'not recorded').replace('T', ' '))}</b>"
                      for k, v in timeline)
            + f'<span>Outage</span><b>{_e(i["outage_hours"])} h against a tolerance of '
              f'{_e(i["impact_tolerance_hours"])} h</b>'
            f'<span>Detection → regulator</span><b>{_e(_fmt_minutes(i["notify_minutes"]))}</b>'
            f'<span>Customers affected</span><b>{int(i["customers_affected"] or 0):,}</b>'
            f'<span>Loss</span><b>gross {i["gross_loss"] or 0:,.0f} · recovered '
            f'{i["recovered"] or 0:,.0f} · net {i["net_loss"]:,.0f} {_e(i["currency"])}</b>'
            f'<span>Root cause</span><b>{_e(i["root_cause"])}</b>'
            f'<span>Failed controls</span><b>{_e(", ".join(failed) or "none recorded")}</b>'
            f'<span>Status</span><b>{_e(i["status"])} · {_e(i["owner"])}</b></div>'
            f'{cite_html}</div>', unsafe_allow_html=True)
    st.caption("Times are shown as recorded. Whether a report met a regulatory deadline "
               "is for the compliance owner to confirm against the quoted obligation.")


def _render_actions(acts: pd.DataFrame) -> None:
    if acts.empty:
        st.markdown(notice("No remediation actions."), unsafe_allow_html=True)
        return
    rows = []
    for _, a in acts.iterrows():
        state = (pill("Done", "found") if a["status"] == "done" else
                 pill("Overdue", "gap") if a["overdue"] else
                 pill(a["status"].replace("_", " ").capitalize(), "na"))
        rows.append(f'<tr><td class="cat">{_e(a["id"])} · {_e(a["title"])}'
                    f'<small>from {_e(a["source_kind"].replace("_", " "))} '
                    f'{_e(a["source_id"])}</small></td><td>{_e(a["owner"])}</td>'
                    f'<td class="n">{_e(a["due_at"])}</td><td>{state}'
                    f'<div class="ev">{_e(a["closure_evidence"] or "")}</div></td></tr>')
    st.markdown(_scroll('<table class="ws-table"><thead><tr><th>Action</th><th>Owner</th>'
                        '<th>Due</th><th>Status</th></tr></thead><tbody>' + "".join(rows)
                        + "</tbody></table>"), unsafe_allow_html=True)


def _render_assessment(conn, r: dict, s: dict) -> None:
    name = controls_views._reviewer()
    st.caption(f"Computed residual: L{s['residual_likelihood']} × I{s['residual_impact']}. "
               "Override it only with a reason; the change is logged.")
    keep = "Use computed"
    opts = [keep, 1, 2, 3, 4, 5]
    c1, c2 = st.columns(2)

    def idx(v):
        return 0 if v is None or pd.isna(v) else int(v)
    with c1:
        like = st.selectbox("Residual likelihood", opts, index=idx(r["override_likelihood"]),
                            key=f"rk_ol_{r['id']}")
    with c2:
        imp = st.selectbox("Residual impact", opts, index=idx(r["override_impact"]),
                           key=f"rk_oi_{r['id']}")
    why = st.text_area("Reason for the override", value=r["override_rationale"] or "",
                       key=f"rk_why_{r['id']}")
    if st.button("Save assessment", key=f"rk_save_{r['id']}"):
        if not name:
            st.warning("Enter your name first; every change is recorded with it.")
        else:
            try:
                risk.set_residual_override(
                    conn, r["id"], None if like == keep else int(like),
                    None if imp == keep else int(imp), why, actor=name)
                conn.commit()
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
    log = risk.history(conn, object_id=r["id"], limit=50)
    st.markdown(pane_head("History", count=f"{len(log)} entries"), unsafe_allow_html=True)
    if log:
        st.dataframe(pd.DataFrame([{
            "When (UTC)": x["ts"], "Who": x["actor"], "What": f"{x['action']} {x['table_name']}",
            "Changed": ", ".join(k for k, v in json.loads(x["after_json"] or "{}").items()
                                 if json.loads(x["before_json"] or "{}").get(k) != v
                                 and k not in ("updated_at", "updated_by"))[:200],
        } for x in log]), hide_index=True, width="stretch")


def _render_demo_tools(conn, index) -> None:
    if not risk.is_synthetic(conn):
        return
    with st.expander("Demo data"):
        st.caption("Reloads the synthetic demo, undoing any edits made to it. Refuses "
                   "if the store holds anything that is not synthetic.")
        if st.button("Reset demo data", key="rk_reset"):
            try:
                demo_data.reset(conn, index, actor=controls_views._reviewer() or "anonymous")
                conn.commit()
                st.rerun()
            except PermissionError as exc:
                st.warning(str(exc))


# --- Management report ---------------------------------------------------------------

def page_report() -> None:
    page_header("Risk report", "One page for the risk committee: risks against appetite, "
                "KRI breaches, incidents and losses, control exceptions and overdue "
                "actions, with every regulatory reference cited.")
    with _stores() as (conn, index):
        _banner(conn)
        rep = risk_report.build(conn, index)
        if rep["register"].empty:
            st.markdown(notice("No risks recorded yet, so there is nothing to report."),
                        unsafe_allow_html=True)
            return
        st.markdown(pane_head("Summary", count=f"as of {rep['date']}"),
                    unsafe_allow_html=True)
        st.markdown("<ul>" + "".join(f"<li>{_e(x)}</li>" for x in risk_report.headline(rep))
                    + "</ul>", unsafe_allow_html=True)
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.download_button("Download Excel", risk_report.excel(rep),
                               file_name=f"risk_report_{rep['date']}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet", key="rk_xlsx")
        with c2:
            st.download_button("Download PDF", risk_report.pdf(rep),
                               file_name=f"risk_report_{rep['date']}.pdf",
                               mime="application/pdf", key="rk_pdf")
        left, right = st.columns([1, 2.2])
        with left:
            st.markdown(pane_head("Residual heat map"), unsafe_allow_html=True)
            st.markdown(_heat(rep["register"]), unsafe_allow_html=True)
        with right:
            st.markdown(pane_head("Risks by residual score"), unsafe_allow_html=True)
            st.markdown(_register_table(rep["register"]), unsafe_allow_html=True)
        sections = (
            ("KRI breaches (latest reading)", risk_report.kri_frame(rep["kris"]),
             "No KRI is amber or red."),
            (f"Incidents, last {risk_report.INCIDENT_WINDOW_DAYS} days",
             risk_report.incident_frame(rep["incidents"]), "No incidents in the period."),
            ("Open remediation actions", risk_report.action_frame(rep["actions"]),
             "No open actions."),
            ("Key controls not rated effective", risk_report.control_frame(rep["controls"]),
             "Every key control is rated effective."),
            ("Regulation links to validate", risk_report.link_frame(rep["links"]),
             "Every link is validated and its source text is current."),
        )
        for title, frame, empty in sections:
            st.markdown(pane_head(title, count=f"{len(frame)}"), unsafe_allow_html=True)
            if frame.empty:
                st.markdown(notice(empty), unsafe_allow_html=True)
            else:
                st.dataframe(frame, hide_index=True, width="stretch")
        st.caption(risk_report.NOTICE + " " + risk.METHOD_NOTE)
