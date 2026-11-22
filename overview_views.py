"""Risk Overview — premium operational risk intelligence landing page.

Visual hierarchy answers three questions: current exposure, what changed,
what needs management attention. Metrics come only from orm.overview.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import controls_views
from orm import demo_mode, overview as ov, risk
from ui_theme import e as _e, empty_state, pill

PAGES: dict = {}

SEVERITY_KIND = {
    "Critical": "gap", "High": "gap", "P1": "gap", "P2": "gap", "Red": "gap",
    "Amber": "partial", "Moderate": "partial", "Medium": "partial",
    "Low": "found",
}

CSS = """
<style>
.ov-shell {max-width: 1180px; margin: 0 auto;}
.ov-head {display: flex; justify-content: space-between; align-items: flex-end;
  gap: 16px; padding-bottom: 14px; margin-bottom: 4px;
  border-bottom: 1px solid var(--line);}
.ov-head h1 {font-size: 26px; font-weight: 500; letter-spacing: -0.035em;
  margin: 0; color: var(--ink); line-height: 1.15;}
.ov-head .sub {font-size: 13.5px; color: var(--ink-2); margin-top: 4px;}
.ov-head-meta {text-align: right; font-size: 12px; color: var(--ink-3);
  line-height: 1.55; font-variant-numeric: tabular-nums;}
.ov-head-meta .demo {display: inline-block; margin-top: 4px; font-size: 11px;
  font-weight: 600; letter-spacing: 0.02em; color: #5c4300;
  background: var(--partial-bg); border: 1px solid #e0c56a;
  border-radius: 999px; padding: 1px 8px;}
.ov-kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin: 16px 0 20px;}
.ov-kpi {border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px;
  background: var(--surface); min-height: 88px; cursor: default;}
.ov-kpi .label {font-size: 12px; color: var(--ink-3); font-weight: 500;
  letter-spacing: -0.01em;}
.ov-kpi .value {font-size: 28px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums; letter-spacing: -0.03em;
  margin-top: 6px; line-height: 1;}
.ov-kpi .hint {font-size: 11px; color: var(--ink-3); margin-top: 8px;}
.ov-kpi.warn .value {color: var(--gap);}
.ov-kpi-nav {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin: -12px 0 18px;}
.ov-sec {margin: 8px 0 22px;}
.ov-sec-h {font-size: 13px; font-weight: 600; color: var(--ink);
  letter-spacing: -0.02em; padding-bottom: 8px; margin: 0 0 12px;
  border-bottom: 1px solid var(--line); display: flex; align-items: baseline;
  gap: 10px;}
.ov-sec-h .meta {margin-left: auto; font-weight: 500; color: var(--ink-3);
  font-size: 12px; font-variant-numeric: tabular-nums;}
.ov-panel {border: 1px solid var(--line); border-radius: 8px;
  background: var(--surface); padding: 14px 16px;}
.ov-dist {display: grid; gap: 8px;}
.ov-dist-row {display: grid; grid-template-columns: 72px 1fr 28px;
  gap: 8px; align-items: center; font-size: 12.5px; color: var(--ink-2);}
.ov-dist-row b {color: var(--ink); font-weight: 500; font-variant-numeric: tabular-nums;
  text-align: right;}
.ov-bar {height: 6px; background: var(--subtle); border-radius: 999px; overflow: hidden;}
.ov-bar > span {display: block; height: 100%; border-radius: 999px; background: var(--ink-2);}
.ov-bar.critical > span {background: var(--gap);}
.ov-bar.high > span {background: #c45c4a;}
.ov-bar.moderate > span {background: var(--partial);}
.ov-bar.low > span {background: var(--found);}
.ov-attn {width: 100%; border-collapse: collapse; font-size: 13px;}
.ov-attn th {text-align: left; font-size: 11px; font-weight: 600; color: var(--ink-3);
  border-bottom: 1px solid var(--line); padding: 0 8px 8px; letter-spacing: 0.01em;}
.ov-attn td {padding: 9px 8px; border-bottom: 1px solid var(--line); color: var(--ink-2);
  vertical-align: top;}
.ov-attn tr:last-child td {border-bottom: none;}
.ov-attn .issue {color: var(--ink); font-weight: 500;}
.ov-attn .sub {display: block; font-size: 11.5px; color: var(--ink-3); font-weight: 400;
  margin-top: 2px;}
.ov-ri {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px;}
.ov-ri-item {border: 1px solid var(--line); border-radius: 8px; padding: 12px;
  background: var(--surface);}
.ov-ri-item .n {font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums;
  color: var(--ink);}
.ov-ri-item .l {font-size: 11.5px; color: var(--ink-3); margin-top: 4px; line-height: 1.35;}
.ov-activity {font-size: 13px; color: var(--ink-2);}
.ov-activity li {margin: 0 0 6px; padding-left: 0;}
.ov-foot {font-size: 12px; color: var(--ink-3); margin-top: 8px;}
@media (max-width: 960px) {
  .ov-kpis, .ov-kpi-nav, .ov-ri {grid-template-columns: repeat(2, minmax(0, 1fr));}
  .ov-head {flex-direction: column; align-items: flex-start;}
  .ov-head-meta {text-align: left;}
}
@media (max-width: 560px) {
  .ov-kpis, .ov-kpi-nav, .ov-ri {grid-template-columns: 1fr;}
}
</style>
"""


def page_overview() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        if demo_mode.is_enabled(st.session_state):
            demo_mode.ensure_seeded(index_conn=index)

        _tour_chrome()

        with risk.session() as conn:
            from orm import demo_data
            demo_data.seed(conn, index)

            # Read filter state before widgets so the title sits above controls
            period = st.session_state.get("ov_period", "monthly")
            entity_pick = st.session_state.get("ov_entity", "All entities")
            entity = "" if entity_pick == "All entities" else entity_pick
            snap = ov.snapshot(conn, index, period=period,
                              legal_entity=entity or None)

            st.markdown('<div class="ov-shell">', unsafe_allow_html=True)
            _header(snap, period=period, entity=entity)
            new_period, new_entity = _header_filters(conn)
            if (new_period, new_entity) != (period, entity):
                st.rerun()

            if snap["empty"]:
                st.markdown(empty_state(
                    "No risk assessments have been created.",
                    "Enable Demo Mode — Synthetic Data in the sidebar, or open "
                    "the Risk Register after seeding. Upload a regulatory document "
                    "under Sources when working with your own corpus."),
                    unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                return

            _kpi_strip(snap)
            _exposure_section(snap)
            _attention_section(snap)
            _regulatory_section(snap)
            _activity_section(snap)

            st.markdown(
                f'<p class="ov-foot">{_e(snap["notice"])}</p></div>',
                unsafe_allow_html=True)
            _demo_controls_inline()
    finally:
        ctx.__exit__(None, None, None)


def _header_filters(conn) -> tuple[str, str]:
    try:
        ents = [r[0] for r in conn.execute(
            "SELECT DISTINCT legal_entity FROM risk "
            "WHERE status != 'retired' AND legal_entity IS NOT NULL "
            "AND legal_entity != '' ORDER BY 1").fetchall()]
    except Exception:
        ents = []
    c1, c2, _ = st.columns([1.2, 1.6, 2])
    with c1:
        period = st.selectbox(
            "Reporting period",
            ["monthly", "weekly", "quarterly"],
            format_func=lambda x: x.title(),
            key="ov_period",
            help="Context label for this Overview view.")
    with c2:
        choices = ["All entities"] + ents
        pick = st.selectbox(
            "Legal entity", choices, key="ov_entity",
            help="Filter open risks by legal entity when recorded.")
    entity = "" if pick == "All entities" else pick
    return period, entity


def _header(snap: dict, *, period: str = "", entity: str = "") -> None:
    badge = ""
    if demo_mode.is_enabled(st.session_state):
        badge = '<div class="demo">Demo Mode — Synthetic Data</div>'
    elif snap.get("synthetic"):
        badge = '<div class="demo">Synthetic dataset</div>'
    ent_label = entity or "All entities"
    st.markdown(
        f'<div class="ov-head">'
        f'<div><h1>Risk Overview</h1>'
        f'<div class="sub">Operational risk intelligence and monitoring</div></div>'
        f'<div class="ov-head-meta">'
        f'As of {_e(snap.get("as_of") or "—")}<br>'
        f'Updated {_e((snap.get("updated_at") or "")[:19].replace("T", " "))}<br>'
        f'{_e(ent_label)} · {_e((period or snap.get("period") or "").title())} view'
        f'{badge}</div></div>',
        unsafe_allow_html=True)


def _kpi_strip(snap: dict) -> None:
    m = snap["metrics"]
    items = [
        ("material_residual_risks", "Material residual risks",
         m["material_residual_risks"], "risks",
         "High / Critical residual band", True),
        ("kri_threshold_breaches", "KRI threshold breaches",
         m["kri_threshold_breaches"], "kri",
         "Red or Amber latest status", True),
        ("critical_control_gaps", "Critical control gaps",
         m["critical_control_gaps"], "controls",
         "Key controls not rated effective", False),
        ("overdue_risk_actions", "Overdue risk actions",
         m["overdue_risk_actions"], "incidents",
         "Open remediation past due date", True),
    ]
    # Single CSS grid so cards reflow on narrow viewports (Streamlit columns do not)
    cards = []
    for key, label, value, _page, hint, warn_on in items:
        warn = " warn" if (warn_on and value) else ""
        display = "—" if value is None else str(value)
        cards.append(
            f'<div class="ov-kpi{warn}" role="group" aria-label="{_e(label)}">'
            f'<div class="label">{_e(label)}</div>'
            f'<div class="value">{_e(display)}</div>'
            f'<div class="hint">{_e(hint)}</div></div>')
    st.markdown(f'<div class="ov-kpis">{"".join(cards)}</div>',
                unsafe_allow_html=True)
    cols = st.columns(4, gap="small")
    for col, (key, label, _value, page, _hint, _w) in zip(cols, items):
        with col:
            if st.button("Open", key=f"ov_kpi_{key}", width="stretch",
                         help=f"Open {label}"):
                if PAGES.get(page):
                    st.switch_page(PAGES[page])


def _exposure_section(snap: dict) -> None:
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Risk exposure'
        '<span class="meta">Current assessments — not a fabricated time series</span>'
        '</div></div>',
        unsafe_allow_html=True)
    left, right = st.columns([1.85, 1], gap="large")
    with left:
        st.markdown('<div class="ov-panel">', unsafe_allow_html=True)
        st.markdown("**Inherent vs residual distribution**")
        st.caption(
            "Counts of open risks by rating band. Time trends appear only when "
            "historical snapshots exist — none are invented here.")
        exp = snap["exposure"]
        if exp is None or exp.empty or int(exp[["Inherent", "Residual"]].sum().sum()) == 0:
            st.markdown(empty_state(
                "No risk assessments to chart.",
                "Open the Risk Register to record inherent and residual ratings."),
                unsafe_allow_html=True)
        else:
            long = exp.melt(id_vars="band", value_vars=["Inherent", "Residual"],
                            var_name="rating", value_name="count")
            order = ["Low", "Moderate", "High", "Critical"]
            chart = alt.Chart(long).mark_bar(cornerRadiusTopLeft=2,
                                             cornerRadiusTopRight=2).encode(
                x=alt.X("band:N", sort=order, title=None,
                         axis=alt.Axis(labelAngle=0, labelColor="#5c6b7a",
                                       tickColor="#e6ebf0", domainColor="#e6ebf0")),
                y=alt.Y("count:Q", title=None,
                        axis=alt.Axis(grid=True, gridColor="#eef2f6",
                                      tickColor="#e6ebf0", domainColor="#e6ebf0",
                                      labelColor="#5c6b7a")),
                color=alt.Color("rating:N",
                                scale=alt.Scale(
                                    domain=["Inherent", "Residual"],
                                    range=["#7a8b9a", "#0a2540"]),
                                legend=alt.Legend(title=None, orient="top")),
                xOffset="rating:N",
                tooltip=["band", "rating", "count"],
            ).properties(height=260).configure_view(strokeWidth=0)
            st.altair_chart(chart, use_container_width=True)
            st.caption("Bands: Low · Moderate · High · Critical. Medium maps to Moderate.")
        # Optional genuine KRI sparkline context
        if snap.get("has_kri_history"):
            trends = snap["kri_trends"]
            label = snap.get("kri_trend_label") or "KRI"
            st.markdown(f"**KRI series · {_e(label)}** (observed)")
            plot = trends.copy()
            idx = "period" if "period" in plot.columns else (
                "observed_at" if "observed_at" in plot.columns else None)
            if idx and "value" in plot.columns:
                st.line_chart(plot.set_index(idx)["value"], height=160)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="ov-panel">', unsafe_allow_html=True)
        st.markdown("**Risk distribution**")
        st.caption("Residual band · click to open register")
        dist = snap.get("residual_distribution") or {}
        total = sum(dist.values()) or 1
        for band in ("Critical", "High", "Moderate", "Low"):
            n = int(dist.get(band, 0))
            pct = min(100, round(100 * n / total))
            st.markdown(
                f'<div class="ov-dist-row"><span>{_e(band)}</span>'
                f'<div class="ov-bar {band.lower()}" aria-hidden="true">'
                f'<span style="width:{pct}%"></span></div>'
                f'<b>{n}</b></div>',
                unsafe_allow_html=True)
            if st.button(f"View {band}", key=f"ov_band_{band}", width="stretch"):
                st.session_state["ov_filter_band"] = band
                if PAGES.get("risks"):
                    st.switch_page(PAGES["risks"])
        st.markdown("</div>", unsafe_allow_html=True)


def _attention_section(snap: dict) -> None:
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Requires attention'
        '<span class="meta">Sorted by severity, then date</span></div></div>',
        unsafe_allow_html=True)
    attn = snap.get("attention")
    if attn is None or attn.empty:
        st.markdown(empty_state(
            "Nothing currently requires management attention.",
            "Appetite exceptions, KRI breaches, control gaps, overdue actions "
            "and high-severity incidents will appear here."),
            unsafe_allow_html=True)
        return

    st.markdown('<div class="ov-panel">', unsafe_allow_html=True)
    # Compact HTML table for polish + streamlit select for navigation
    head = ("<table class='ov-attn' role='table'><thead><tr>"
            "<th>Risk or issue</th><th>Category</th><th>Severity</th>"
            "<th>Owner</th><th>Due / observed</th><th>Status</th>"
            "</tr></thead><tbody>")
    body = []
    for _, r in attn.head(12).iterrows():
        sev = pill(str(r["severity"]), SEVERITY_KIND.get(str(r["severity"]), "na"))
        body.append(
            f"<tr><td class='issue'>{_e(r['issue'])}</td>"
            f"<td>{_e(r['category'])}</td><td>{sev}</td>"
            f"<td>{_e(r['owner'])}</td>"
            f"<td style='font-variant-numeric:tabular-nums'>"
            f"{_e(str(r['when'])[:16].replace('T', ' '))}</td>"
            f"<td>{_e(r['status'])}</td></tr>")
    st.markdown(head + "".join(body) + "</tbody></table>", unsafe_allow_html=True)

    options = {
        f"{r['record_id']} · {r['category']}": (r["page"], r["record_id"])
        for _, r in attn.head(12).iterrows()
    }
    pick = st.selectbox(
        "Open record",
        ["—"] + list(options),
        key="ov_attn_pick",
        help="Jump to the module that owns this item.")
    if pick != "—" and st.button("Go to record", key="ov_attn_go"):
        page, _rid = options[pick]
        if page == "risks" and _rid:
            st.session_state["rk_selected"] = _rid
        if PAGES.get(page):
            st.switch_page(PAGES[page])
    st.markdown("</div>", unsafe_allow_html=True)


def _regulatory_section(snap: dict) -> None:
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Regulatory intelligence'
        '<span class="meta">Secondary · ClauseWiz core differentiation</span>'
        '</div></div>',
        unsafe_allow_html=True)
    changes = snap.get("changes")
    apps = snap.get("applicability_pending")
    chg_acts = snap.get("change_actions")
    n_changes = 0 if changes is None or changes.empty else len(changes)
    n_apps = 0 if apps is None or apps.empty else len(apps)
    n_reviewed = 0
    if apps is not None and not apps.empty and "status" in apps.columns:
        n_reviewed = int((~apps["status"].isin(["not_yet_assessed"])).sum())
    n_impact = 0 if chg_acts is None or chg_acts.empty else len(chg_acts)

    st.markdown(
        '<div class="ov-ri">'
        f'<div class="ov-ri-item"><div class="n">{n_changes if n_changes else "—"}</div>'
        f'<div class="l">Regulatory changes awaiting review</div></div>'
        f'<div class="ov-ri-item"><div class="n">{n_apps if n_apps else "—"}</div>'
        f'<div class="l">Obligations requiring applicability assessment</div></div>'
        f'<div class="ov-ri-item"><div class="n">—</div>'
        f'<div class="l">Unmapped obligations</div></div>'
        f'<div class="ov-ri-item"><div class="n">'
        f'{n_reviewed if n_reviewed else (n_impact if n_impact else "—")}</div>'
        f'<div class="l">Recently assessed applicability / open impact actions</div></div>'
        '</div>',
        unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Open Regulatory Intelligence", key="ov_ri_go"):
            if PAGES.get("regulatory"):
                st.switch_page(PAGES["regulatory"])
    with c2:
        if st.button("Open Change Impact", key="ov_ci_go"):
            if PAGES.get("change_impact"):
                st.switch_page(PAGES["change_impact"])
    with c3:
        if st.button("Open Changes", key="ov_ch_go"):
            if PAGES.get("changes"):
                st.switch_page(PAGES["changes"])


def _activity_section(snap: dict) -> None:
    items = snap.get("recent_activity") or []
    if not items:
        return
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Recent activity'
        '<span class="meta">From audit log and recorded events only</span>'
        '</div></div>',
        unsafe_allow_html=True)
    st.markdown('<div class="ov-panel ov-activity"><ul>', unsafe_allow_html=True)
    lines = []
    for it in items[:8]:
        when = str(it.get("when") or "")[:16].replace("T", " ")
        lines.append(
            f"<li><b>{_e(it.get('kind') or '')}</b> · {_e(it.get('title') or '')} "
            f"<span style='color:var(--ink-3)'>— {_e(when)} · "
            f"{_e(it.get('detail') or '')}</span></li>")
    st.markdown("".join(lines) + "</ul></div>", unsafe_allow_html=True)


# --- tour / demo (unchanged behaviour) -------------------------------------------

def _tour_chrome() -> None:
    step = demo_mode.current_step(st.session_state)
    if not step:
        return
    st.markdown(
        f'<div class="tour-chrome" role="region" aria-label="Guided demo">'
        f'<div class="step">Guided demo · Step {step["step"]} of '
        f'{len(demo_mode.TOUR_STEPS)}</div>'
        f'<h3>{_e(step["title"])}</h3>'
        f'<p>{_e(step["explain"])}</p>'
        f'<div class="focus">Focus: {_e(step["focus"])}</div>'
        f'</div>',
        unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        if st.button("Previous", key="tour_prev", disabled=step["step"] <= 1):
            demo_mode.prev_step(st.session_state)
            st.rerun()
    with c2:
        if st.button("Next", type="primary", key="tour_next"):
            nxt = demo_mode.next_step(st.session_state)
            if nxt and PAGES:
                st.switch_page(PAGES[nxt["page_key"]])
            else:
                st.rerun()
    with c3:
        if st.button("Open step page", key="tour_open") and PAGES:
            st.switch_page(PAGES[step["page_key"]])
    with c4:
        if st.button("Exit tour", key="tour_exit"):
            demo_mode.exit_tour(st.session_state)
            st.rerun()


def _demo_controls_inline() -> None:
    with st.expander("Interview demo controls"):
        st.caption(
            "Demo Mode loads an isolated synthetic SQLite file "
            f"(`{demo_mode.DEMO_DB_PATH}`). Reset never deletes live risk data.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Start Guided Demo", type="primary", key="ov_start_tour"):
                demo_mode.start_tour(st.session_state)
                step = demo_mode.current_step(st.session_state)
                if step and PAGES:
                    st.switch_page(PAGES[step["page_key"]])
                else:
                    st.rerun()
        with c2:
            if st.button("Reset demo data", key="ov_reset_demo"):
                demo_mode.enable(st.session_state)
                demo_mode.reset(st.session_state)
                st.success("Demo database reset and re-seeded.")
                st.rerun()
        with c3:
            if demo_mode.is_enabled(st.session_state):
                if st.button("Leave Demo Mode", key="ov_leave_demo"):
                    demo_mode.disable(st.session_state)
                    st.rerun()


def render_sidebar_demo_controls(pages: dict) -> None:
    """Called from app.py sidebar — Demo Mode toggle + guided demo."""
    st.markdown("---")
    enabled = demo_mode.is_enabled(st.session_state)
    on = st.toggle(
        "Demo Mode — Synthetic Data",
        value=enabled,
        key="demo_mode_toggle",
        help="Uses an isolated demo database. Never writes to your live risk store.")
    if on and not enabled:
        demo_mode.enable(st.session_state)
        st.rerun()
    elif not on and enabled:
        demo_mode.disable(st.session_state)
        st.rerun()

    if demo_mode.is_enabled(st.session_state):
        st.caption("Synthetic · not Revolut · isolated DB")
        if st.button("Start Guided Demo", key="sb_start_tour", width="stretch"):
            demo_mode.start_tour(st.session_state)
            step = demo_mode.current_step(st.session_state)
            if step and pages:
                st.switch_page(pages[step["page_key"]])
            else:
                st.rerun()
        if st.button("Reset demo safely", key="sb_reset_demo", width="stretch"):
            demo_mode.reset(st.session_state)
            st.rerun()

    step = demo_mode.current_step(st.session_state)
    if step:
        st.info(
            f"Tour {step['step']}/{len(demo_mode.TOUR_STEPS)}: {step['title']}")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Tour Next", key="sb_tour_next"):
                nxt = demo_mode.next_step(st.session_state)
                if nxt and pages:
                    st.switch_page(pages[nxt["page_key"]])
                else:
                    st.rerun()
        with b2:
            if st.button("Exit tour", key="sb_tour_exit"):
                demo_mode.exit_tour(st.session_state)
                st.rerun()
