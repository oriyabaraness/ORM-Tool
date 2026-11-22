"""Risk Overview — operational risk intelligence landing page.

Rendering must not depend on CSS from other pages. The residual heat map uses
inline-styled HTML so Streamlit cannot collapse it into raw L1/I5 text.
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

# Inline colours — do not rely on theme class CSS for the matrix cells
HEAT_BG = {
    "Low": "#e6f2ea",
    "Moderate": "#f7f0d8",
    "Medium": "#f7f0d8",
    "High": "#f3e0c8",
    "Critical": "#f3d6d2",
}
HEAT_FG = {
    "Low": "#1f6b3a",
    "Moderate": "#7a5b00",
    "Medium": "#7a5b00",
    "High": "#9a4d00",
    "Critical": "#8b2e24",
}

CSS = """
<style>
.ov-shell {max-width: 1200px; margin: 0 auto;}
.ov-head {display: flex; justify-content: space-between; align-items: flex-end;
  gap: 16px; padding-bottom: 12px; margin-bottom: 2px;
  border-bottom: 1px solid var(--line);}
.ov-head h1 {font-size: 24px; font-weight: 500; letter-spacing: -0.03em;
  margin: 0; color: var(--ink); line-height: 1.15;}
.ov-head .sub {font-size: 13px; color: var(--ink-2); margin-top: 3px;}
.ov-head-meta {text-align: right; font-size: 12px; color: var(--ink-3);
  line-height: 1.5; font-variant-numeric: tabular-nums;}
.ov-head-meta .demo {display: inline-block; margin-top: 4px; font-size: 11px;
  font-weight: 600; color: #5c4300; background: var(--partial-bg);
  border: 1px solid #e0c56a; border-radius: 999px; padding: 1px 8px;}
.ov-kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px; margin: 12px 0 8px;}
.ov-kpi {border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px 8px;
  background: var(--surface);}
.ov-kpi .label {font-size: 11.5px; color: var(--ink-3); font-weight: 500;}
.ov-kpi .value {font-size: 22px; font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums; letter-spacing: -0.03em;
  margin-top: 4px; line-height: 1;}
.ov-kpi .hint {font-size: 11px; color: var(--ink-3); margin-top: 5px;}
.ov-kpi.warn .value {color: var(--gap);}
.ov-sec {margin: 4px 0 14px;}
.ov-sec-h {font-size: 13px; font-weight: 600; color: var(--ink);
  letter-spacing: -0.02em; padding-bottom: 7px; margin: 0 0 10px;
  border-bottom: 1px solid var(--line); display: flex; align-items: baseline;
  gap: 10px;}
.ov-sec-h .meta {margin-left: auto; font-weight: 500; color: var(--ink-3);
  font-size: 12px;}
.ov-heat-wrap {overflow-x: auto; max-width: 100%;}
.ov-heat {width: 100%; max-width: 560px; border-collapse: separate; border-spacing: 4px;
  table-layout: fixed; font-variant-numeric: tabular-nums;}
.ov-heat th {font-size: 11px; font-weight: 500; color: #6b7785; text-align: center;
  padding: 2px 0;}
.ov-heat th.corner {width: 28px;}
.ov-heat td.cell {height: 58px; text-align: center; vertical-align: middle;
  border-radius: 4px; border: 1px solid transparent; font-size: 15px; font-weight: 600;}
.ov-heat-cap {font-size: 11.5px; color: var(--ink-3); margin-top: 8px; line-height: 1.4;}
.ov-mat {width: 100%; border-collapse: collapse; font-size: 12.5px;}
.ov-mat th {text-align: left; font-size: 11px; font-weight: 600; color: var(--ink-3);
  border-bottom: 1px solid var(--line); padding: 0 6px 6px;}
.ov-mat td {padding: 7px 6px; border-bottom: 1px solid var(--line); color: var(--ink-2);
  vertical-align: top;}
.ov-mat .risk {color: var(--ink); font-weight: 500;}
.ov-mat .ref {display: block; font-size: 11px; color: var(--ink-3); font-weight: 400;
  margin-top: 1px;}
.ov-attn {width: 100%; border-collapse: collapse; font-size: 12.5px; table-layout: fixed;}
.ov-attn th {text-align: left; font-size: 11px; font-weight: 600; color: var(--ink-3);
  border-bottom: 1px solid var(--line); padding: 0 8px 7px;}
.ov-attn td {padding: 8px; border-bottom: 1px solid var(--line); color: var(--ink-2);
  vertical-align: top;}
.ov-attn .issue {color: var(--ink); font-weight: 500;}
.ov-attn .ref {display: block; font-size: 11px; color: var(--ink-3); font-weight: 400;}
.ov-attn th:nth-child(1), .ov-attn td:nth-child(1) {width: 28%;}
.ov-attn th:nth-child(2), .ov-attn td:nth-child(2) {width: 16%;}
.ov-attn th:nth-child(3), .ov-attn td:nth-child(3) {width: 10%;}
.ov-attn th:nth-child(4), .ov-attn td:nth-child(4) {width: 18%;}
.ov-attn th:nth-child(5), .ov-attn td:nth-child(5) {width: 14%;}
.ov-attn th:nth-child(6), .ov-attn td:nth-child(6) {width: 14%;}
.ov-ri {display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;}
.ov-ri-item {border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px;
  background: var(--surface);}
.ov-ri-item .n {font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums;}
.ov-ri-item .l {font-size: 11.5px; color: var(--ink-3); margin-top: 3px; line-height: 1.35;}
.ov-dist-row {display: grid; grid-template-columns: 72px 1fr 28px; gap: 8px;
  align-items: center; font-size: 12.5px; color: var(--ink-2); margin-bottom: 7px;}
.ov-dist-row b {color: var(--ink); font-weight: 500; text-align: right;
  font-variant-numeric: tabular-nums;}
.ov-bar {height: 6px; background: #eef2f6; border-radius: 999px; overflow: hidden;}
.ov-bar > span {display: block; height: 100%; border-radius: 999px;}
.ov-bar.critical > span {background: #c45c4a;}
.ov-bar.high > span {background: #d4893a;}
.ov-bar.moderate > span {background: #c9a227;}
.ov-bar.low > span {background: #3d8b5e;}
.ov-foot {font-size: 12px; color: var(--ink-3); margin-top: 10px;}
@media (max-width: 960px) {
  .ov-kpis {grid-template-columns: repeat(2, minmax(0, 1fr));}
  .ov-head {flex-direction: column; align-items: flex-start;}
  .ov-head-meta {text-align: left;}
}
@media (max-width: 560px) {
  .ov-kpis, .ov-ri {grid-template-columns: 1fr;}
  .ov-heat td.cell {height: 44px; font-size: 13px;}
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
            from orm import demo_data, incident_mgmt, kri_appetite
            demo_data.seed(conn, index)
            # Idempotent — ensures observation series exist when KRI seed is present
            try:
                kri_appetite.seed(conn)
            except Exception:
                pass
            try:
                incident_mgmt.seed(conn, index)
            except Exception:
                pass

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
                    "the Risk Register after seeding."),
                    unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                return

            _kpi_strip(snap)
            _heat_and_distribution(snap)
            _attention_section(snap)
            _kri_and_regulatory(snap)

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
            key="ov_period")
    with c2:
        pick = st.selectbox(
            "Legal entity", ["All entities"] + ents, key="ov_entity")
    return period, ("" if pick == "All entities" else pick)


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
        f'<div class="sub">Operational risk exposure, monitoring, and priorities.</div>'
        f'</div><div class="ov-head-meta">'
        f'As of {_e(snap.get("as_of") or "—")}<br>'
        f'Updated {_e((snap.get("updated_at") or "")[:19].replace("T", " "))}<br>'
        f'{_e(ent_label)} · {_e((period or "").title())} view{badge}</div></div>',
        unsafe_allow_html=True)


def _kpi_strip(snap: dict) -> None:
    m = snap["metrics"]
    items = [
        ("material_residual_risks", "Material residual risks",
         m["material_residual_risks"], "risks",
         "High / Critical residual", True),
        ("kri_threshold_breaches", "KRI breaches",
         m["kri_threshold_breaches"], "kri",
         "Latest Red or Amber", True),
        ("critical_control_gaps", "Control weaknesses",
         m["critical_control_gaps"], "controls",
         "Key controls not effective", False),
        ("overdue_risk_actions", "Overdue actions",
         m["overdue_risk_actions"], "incidents",
         "Remediation past due", True),
    ]
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
    # Compact text navigation (avoid page_link material icons — they read as prototype)
    cols = st.columns(4, gap="small")
    short = ["Risks", "KRIs", "Controls", "Actions"]
    for col, (key, label, _v, page, _h, _w), s in zip(cols, items, short):
        with col:
            if st.button(s, key=f"ov_kpi_{key}", width="stretch", help=label):
                if PAGES.get(page):
                    st.switch_page(PAGES[page])


def _residual_heat_html(snap: dict) -> str:
    """5×5 residual matrix with INLINE styles (Streamlit-safe). Counts only."""
    cells = snap.get("heat_cells") or {}
    # Empty cells keep a faint band tint so the matrix reads as a real grid
    empty_bg = {
        "Low": "#f3f8f4", "Moderate": "#faf7ec", "Medium": "#faf7ec",
        "High": "#faf3ea", "Critical": "#faf0ee",
    }
    rows = [
        '<div class="ov-heat-wrap" role="img" aria-label="Residual risk heat map, '
        'likelihood across, impact up">'
        '<table class="ov-heat"><thead><tr><th class="corner"></th>'
    ]
    for like in range(1, 6):
        rows.append(f"<th>L{like}</th>")
    rows.append("</tr></thead><tbody>")
    for impact in range(5, 0, -1):
        rows.append(f"<tr><th scope='row'>I{impact}</th>")
        for like in range(1, 6):
            entries = cells.get((impact, like), [])
            n = len(entries)
            band = risk.band(like * impact)
            if band == "Medium":
                band = "Moderate"
            if n:
                titles = "; ".join(
                    f"{e['id']} {e['title']}" for e in entries[:6])
                tip = _e(f"Likelihood {like} × Impact {impact} · {band} · {titles}")
                bg = HEAT_BG.get(band, "#f7f9fb")
                fg = HEAT_FG.get(band, "#6b7785")
                body = str(n)
                style = (f"background-color:{bg};color:{fg};"
                         f"border:1px solid {fg}44;")
            else:
                tip = _e(f"Likelihood {like} × Impact {impact} · {band} · empty")
                bg = empty_bg.get(band, "#f7f9fb")
                body = ""
                style = f"background-color:{bg};border:1px solid #e8edf2;"
            rows.append(
                f'<td class="cell" style="{style}" bgcolor="{bg}" '
                f'title="{tip}">{body}</td>')
        rows.append("</tr>")
    rows.append(
        "</tbody></table>"
        '<div class="ov-heat-cap">Likelihood → · Impact ↑ · Cell = risk count · '
        "Colour = residual score band (Low / Moderate / High / Critical). "
        "Hover a cell for references.</div></div>")
    return "".join(rows)


def _heat_and_distribution(snap: dict) -> None:
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Residual risk exposure'
        '<span class="meta">5×5 matrix · counts, not raw IDs</span></div></div>',
        unsafe_allow_html=True)
    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        st.markdown("**Residual risk heat map**")
        st.markdown(_residual_heat_html(snap), unsafe_allow_html=True)

        cells = snap.get("heat_cells") or {}
        occupied = sorted(
            ((i, l, entries) for (i, l), entries in cells.items() if entries),
            key=lambda t: (-(t[0] * t[1]), -t[0], -t[1]))
        if occupied:
            labels = {
                f"I{i}×L{l} · {len(e)} risk(s) · {risk.band(i * l)}": (i, l, e)
                for i, l, e in occupied
            }
            pick = st.selectbox(
                "Open risks in cell",
                ["—"] + list(labels),
                key="ov_heat_cell",
                help="Jump to Risk Register filtered to this matrix cell.")
            if pick != "—" and st.button("Open cell in register",
                                        key="ov_heat_go"):
                _i, _l, entries = labels[pick]
                st.session_state["ov_filter_ids"] = [x["id"] for x in entries]
                st.session_state["ov_filter_band"] = None
                if PAGES.get("risks"):
                    st.switch_page(PAGES["risks"])

    with right:
        st.markdown("**Risk distribution**")
        dist = snap.get("residual_distribution") or {}
        total = sum(dist.values()) or 1
        dist_html = []
        for band in ("Critical", "High", "Moderate", "Low"):
            n = int(dist.get(band, 0))
            pct = min(100, round(100 * n / total))
            dist_html.append(
                f'<div class="ov-dist-row"><span>{_e(band)}</span>'
                f'<div class="ov-bar {band.lower()}"><span style="width:{pct}%">'
                f'</span></div><b>{n}</b></div>')
        st.markdown("".join(dist_html), unsafe_allow_html=True)
        short_band = {"Critical": "Critical", "High": "High",
                      "Moderate": "Moderate", "Low": "Low"}
        bcols = st.columns(4)
        for band, col in zip(("Critical", "High", "Moderate", "Low"), bcols):
            n = int(dist.get(band, 0))
            with col:
                label = short_band[band]
                if n and st.button(label, key=f"ov_band_{band}",
                                   help=f"Filter register to {band} ({n})",
                                   width="stretch"):
                    st.session_state["ov_filter_band"] = band
                    st.session_state.pop("ov_filter_ids", None)
                    if PAGES.get("risks"):
                        st.switch_page(PAGES["risks"])

        st.markdown("**Material residual risks**")
        mat = snap.get("material")
        if mat is None or mat.empty:
            st.markdown(empty_state(
                "No High or Critical residual risks.",
                "Material items appear when residual band is High or Critical."),
                unsafe_allow_html=True)
        else:
            body = []
            for _, r in mat.head(6).iterrows():
                title = str(r.get("title") or "")
                if len(title) > 56:
                    title = title[:53] + "…"
                owner = r.get("owner")
                try:
                    if owner is None or pd.isna(owner):
                        owner = "—"
                except (TypeError, ValueError):
                    owner = owner or "—"
                sev = pill(str(r.get("residual_band") or ""),
                           SEVERITY_KIND.get(str(r.get("residual_band")), "na"))
                body.append(
                    f"<tr><td class='risk'>{_e(title)}"
                    f"<span class='ref'>{_e(r['id'])}</span></td>"
                    f"<td>{sev}</td>"
                    f"<td>{_e(str(owner))}</td></tr>")
            st.markdown(
                "<table class='ov-mat'><thead><tr>"
                "<th>Risk / Issue</th><th>Severity</th><th>Accountable Owner</th>"
                "</tr></thead><tbody>"
                + "".join(body) + "</tbody></table>",
                unsafe_allow_html=True)


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
            "and high-severity incidents appear here."),
            unsafe_allow_html=True)
        return

    head = ("<table class='ov-attn' role='table'><thead><tr>"
            "<th>Issue</th><th>Type</th><th>Severity</th>"
            "<th>Accountable Owner</th><th>Status</th>"
            "<th>Due / observed</th></tr></thead><tbody>")
    body = []
    options = {}
    for _, r in attn.head(12).iterrows():
        issue = str(r["issue"] or "")
        if " — " in issue:
            ref, title = issue.split(" — ", 1)
        else:
            ref, title = str(r.get("record_id") or ""), issue
        if len(title) > 72:
            title = title[:69] + "…"
        sev = pill(str(r["severity"]), SEVERITY_KIND.get(str(r["severity"]), "na"))
        body.append(
            f"<tr><td class='issue'>{_e(title)}"
            f"<span class='ref'>{_e(ref)}</span></td>"
            f"<td>{_e(r['category'])}</td><td>{sev}</td>"
            f"<td>{_e(r['owner'])}</td>"
            f"<td>{_e(r['status'])}</td>"
            f"<td style='font-variant-numeric:tabular-nums'>"
            f"{_e(str(r['when'])[:16].replace('T', ' '))}</td></tr>")
        options[f"{r['record_id']} · {r['category']}"] = (r["page"], r["record_id"])

    st.markdown(head + "".join(body) + "</tbody></table>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    with c1:
        pick = st.selectbox(
            "Open selected record",
            ["—"] + list(options),
            key="ov_attn_pick")
    with c2:
        go = st.button("Open", key="ov_attn_go", width="stretch")
    if pick != "—" and go:
        page, rid = options[pick]
        if page == "risks" and rid:
            st.session_state["rk_selected"] = rid
        if PAGES.get(page):
            st.switch_page(PAGES[page])


def _kri_and_regulatory(snap: dict) -> None:
    st.markdown(
        '<div class="ov-sec"><div class="ov-sec-h">Monitoring &amp; regulatory'
        '<span class="meta">Same store as the KPI strip</span></div></div>',
        unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        st.markdown("**KRI trends**")
        note = snap.get("kri_note") or ""
        if note:
            st.caption(note)
        breaches = snap.get("kri_breaches")
        if breaches is not None and not breaches.empty:
            rows = []
            for _, k in breaches.head(6).iterrows():
                kid = k.get("id") or k.get("kri_id")
                name = k.get("name") or kid
                if len(str(name)) > 48:
                    name = str(name)[:45] + "…"
                rag = pill(str(k.get("rag") or ""),
                           SEVERITY_KIND.get(str(k.get("rag") or ""), "na"))
                rows.append(
                    f"<tr><td class='risk'>{_e(name)}"
                    f"<span class='ref'>{_e(kid)}</span></td>"
                    f"<td>{rag}</td></tr>")
            st.markdown(
                "<table class='ov-mat'><thead><tr>"
                "<th>Indicator</th><th>Latest status</th>"
                "</tr></thead><tbody>"
                + "".join(rows) + "</tbody></table>",
                unsafe_allow_html=True)
        if snap.get("has_kri_history"):
            trends = snap["kri_trends"]
            label = snap.get("kri_trend_label") or "KRI"
            st.markdown(f"**Observation series · {_e(label)}**")
            plot = trends.copy()
            idx = "period" if "period" in plot.columns else (
                "observed_at" if "observed_at" in plot.columns else None)
            if idx and "value" in plot.columns:
                chart = alt.Chart(plot).mark_line(
                    point=True, color="#0a2540").encode(
                    x=alt.X(f"{idx}:N", title=None,
                            axis=alt.Axis(labelAngle=-30, labelColor="#5c6b7a")),
                    y=alt.Y("value:Q", title=None,
                            axis=alt.Axis(grid=True, gridColor="#eef2f6",
                                          labelColor="#5c6b7a")),
                    tooltip=[idx, "value"],
                ).properties(height=180).configure_view(strokeWidth=0)
                st.altair_chart(chart, width="stretch")
        elif breaches is None or breaches.empty:
            st.markdown(empty_state(
                "No KRI breaches or observation history.",
                "Open KRI Monitoring or enable Demo Mode for a seeded series."),
                unsafe_allow_html=True)
        if st.button("Open KRI Monitoring", key="ov_kri_go"):
            if PAGES.get("kri"):
                st.switch_page(PAGES["kri"])

    with right:
        st.markdown("**Regulatory intelligence**")
        changes = snap.get("changes")
        apps = snap.get("applicability_pending")
        chg_acts = snap.get("change_actions")
        n_changes = 0 if changes is None or changes.empty else len(changes)
        n_apps = 0 if apps is None or apps.empty else len(apps)
        n_impact = 0 if chg_acts is None or chg_acts.empty else len(chg_acts)
        st.markdown(
            '<div class="ov-ri">'
            f'<div class="ov-ri-item"><div class="n">'
            f'{n_changes if n_changes else "—"}</div>'
            f'<div class="l">Regulatory changes awaiting review</div></div>'
            f'<div class="ov-ri-item"><div class="n">'
            f'{n_apps if n_apps else "—"}</div>'
            f'<div class="l">Obligations needing applicability assessment</div></div>'
            f'<div class="ov-ri-item"><div class="n">'
            f'{n_impact if n_impact else "—"}</div>'
            f'<div class="l">Change-impact actions open</div></div>'
            f'<div class="ov-ri-item"><div class="n">—</div>'
            f'<div class="l">Unmapped obligations (count not tracked)</div></div>'
            '</div>',
            unsafe_allow_html=True)
        if changes is not None and not changes.empty:
            st.caption("Recent indexed changes")
            recent = []
            for _, c in changes.head(4).iterrows():
                title = str(c.get("doc_title") or c.get("doc_ref") or "Document")
                if len(title) > 56:
                    title = title[:53] + "…"
                juris = c.get("jurisdiction") or ""
                recent.append(f"· {_e(juris)} — {_e(title)}")
            st.markdown("<br>".join(recent), unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Regulatory Intelligence", key="ov_ri_go"):
                if PAGES.get("regulatory"):
                    st.switch_page(PAGES["regulatory"])
        with b2:
            if st.button("Change Impact", key="ov_ci_go"):
                if PAGES.get("change_impact"):
                    st.switch_page(PAGES["change_impact"])


# --- tour / demo ------------------------------------------------------------------

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
