"""Overview dashboard — operational risk snapshot for interview-ready navigation.

Metrics come from orm.overview only. Demo Mode and the guided tour are driven
by orm.demo_mode. No fabricated live feeds.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import demo_mode, overview as ov, risk
from ui_theme import (
    demo_banner_html, e as _e, empty_state, notice, page_header, pane_head, pill,
)

PAGES: dict = {}

BAND_KIND = {"Low": "found", "Moderate": "partial", "Medium": "partial",
             "High": "gap", "Critical": "gap"}


def page_overview() -> None:
    page_header(
        "Overview",
        "Operational risk snapshot across appetite, controls, KRIs, incidents "
        "and remediation — calculated from application records.")
    ctx, index = controls_views._open()
    try:
        # Ensure demo dataset exists when Demo Mode is on
        if demo_mode.is_enabled(st.session_state):
            demo_mode.ensure_seeded(index_conn=index)
            st.markdown(demo_banner_html(demo_mode.DEMO_BANNER),
                        unsafe_allow_html=True)

        _tour_chrome()

        with risk.session() as conn:
            # Seed lightly when empty so Overview is useful in interview without
            # forcing Demo Mode — still labelled synthetic when applicable.
            from orm import demo_data
            demo_data.seed(conn, index)
            snap = ov.snapshot(conn, index)
            risk_views._banner(conn)

            if snap["empty"]:
                st.markdown(empty_state(
                    "No risk assessments have been created.",
                    "Enable <b>Demo Mode — Synthetic Data</b> in the sidebar, "
                    "or open Risk Register after seeding. "
                    "Upload a regulatory document under Sources / Regulatory "
                    "Intelligence when working with your own corpus."),
                    unsafe_allow_html=True)
                return

            _snapshot_cards(snap)
            left, right = st.columns([1.1, 1.4], gap="large")
            with left:
                st.markdown(pane_head("B. Risk heat map (residual)"),
                            unsafe_allow_html=True)
                st.markdown(risk_views._heat(snap["register"]),
                            unsafe_allow_html=True)
            with right:
                st.markdown(pane_head("A. Material risks & appetite exceptions"),
                            unsafe_allow_html=True)
                _material_tables(snap)

            c1, c2 = st.columns(2, gap="large")
            with c1:
                _kri_trends(snap)
            with c2:
                _priority_actions(snap)

            c3, c4 = st.columns(2, gap="large")
            with c3:
                _regulatory_changes(snap)
            with c4:
                _recent_events(snap)

            st.caption(snap["notice"])
            _demo_controls_inline()
    finally:
        ctx.__exit__(None, None, None)


def _snapshot_cards(snap: dict) -> None:
    m = snap["metrics"]

    def card(n, label, alert=False):
        cls = "ov-card alert" if alert and n else "ov-card"
        return (f'<div class="{cls}"><div class="n">{n}</div>'
                f'<div class="l">{label}</div></div>')

    st.markdown(
        '<div class="ov-cards" role="group" aria-label="Operational risk snapshot">'
        + card(m["material_risks"], "Material risks (High / Critical)", True)
        + card(m["appetite_exceptions"], "Risk appetite exceptions", True)
        + card(m["control_weaknesses"], "Open control weaknesses", True)
        + card(m["kri_breaches"], "KRI breaches (Red / Amber)", True)
        + card(m["high_severity_incidents"], "High-severity incidents (P1/P2)", True)
        + card(m["overdue_actions"], "Overdue actions", True)
        + "</div>",
        unsafe_allow_html=True)


def _material_tables(snap: dict) -> None:
    mat = snap["material"]
    out = snap["outside"]
    if (mat is None or mat.empty) and (out is None or out.empty):
        st.markdown(empty_state(
            "No material risks or appetite exceptions in the register.",
            "Open Risk Register to assess residual exposure."),
            unsafe_allow_html=True)
        return
    if mat is not None and not mat.empty:
        st.caption("Material by residual band")
        show = mat[["id", "title", "residual_score", "residual_band", "owner"]].head(8)
        st.dataframe(show, hide_index=True, use_container_width=True)
    if out is not None and not out.empty:
        st.caption("Outside appetite")
        st.dataframe(
            out[["id", "title", "residual_score", "appetite", "owner"]].head(8),
            hide_index=True, use_container_width=True)


def _kri_trends(snap: dict) -> None:
    st.markdown(pane_head("C. KRI trends"), unsafe_allow_html=True)
    trends = snap["kri_trends"]
    breaches = snap["kri_breaches"]
    if trends is None or trends.empty:
        st.markdown(empty_state(
            "No KRI observations for this reporting period.",
            "Open KRI Monitoring or enable Demo Mode for synthetic series."),
            unsafe_allow_html=True)
    else:
        cols = [c for c in ("period", "observed_at", "value", "numerator",
                            "denominator", "rag") if c in trends.columns]
        st.dataframe(trends[cols].tail(14), hide_index=True, use_container_width=True)
        # Accessible text summary — not color alone
        if "value" in trends.columns and len(trends) >= 2:
            first, last = trends.iloc[0]["value"], trends.iloc[-1]["value"]
            st.caption(
                f"Series move: {first} → {last} "
                f"({'up' if last > first else 'down' if last < first else 'flat'}).")
    if breaches is not None and not breaches.empty:
        st.caption("Current breaches")
        use = [c for c in ("id", "name", "rag", "value", "unit") if c in breaches.columns]
        st.dataframe(breaches[use].head(6), hide_index=True, use_container_width=True)


def _priority_actions(snap: dict) -> None:
    st.markdown(pane_head("D. Priority management actions"), unsafe_allow_html=True)
    acts = snap["priority_actions"]
    if acts is None or acts.empty:
        st.markdown(empty_state(
            "No overdue remediation actions.",
            "Open Incidents or Risk Register when actions are raised."),
            unsafe_allow_html=True)
        return
    use = [c for c in ("id", "title", "owner", "due_at", "source_id", "status")
           if c in acts.columns]
    st.dataframe(acts[use], hide_index=True, use_container_width=True)


def _regulatory_changes(snap: dict) -> None:
    st.markdown(pane_head("E. Regulatory changes requiring review"),
                unsafe_allow_html=True)
    ch = snap["changes"]
    if ch is None or ch.empty:
        st.markdown(empty_state(
            "No indexed document changes in the look-back window.",
            "Open Changes under Compare, or refresh the regulation index."),
            unsafe_allow_html=True)
        return
    use = [c for c in ("jurisdiction", "doc_ref", "doc_title", "changed",
                       "categories", "text_status") if c in ch.columns]
    st.dataframe(ch[use].head(10), hide_index=True, use_container_width=True)


def _recent_events(snap: dict) -> None:
    st.markdown(pane_head("F. Recent risk events"), unsafe_allow_html=True)
    events = snap.get("recent_events") or []
    if not events:
        st.markdown(empty_state(
            "No recent risk events recorded.",
            "Incidents and new risk records will appear here."),
            unsafe_allow_html=True)
        return
    st.dataframe(pd.DataFrame(events), hide_index=True, use_container_width=True)


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

    # Persistent tour chrome when navigating other pages
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
