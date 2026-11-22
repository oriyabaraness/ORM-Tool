"""Interview demonstration front page — job responsibilities → live modules.

Navigational product entry for a Revolut ORM interview. Not a job application
page. Exact responsibility wording from the public LinkedIn posting.
"""
from __future__ import annotations

import streamlit as st

from orm import demo_mode, interview_demo as ix
from ui_theme import APP_NAME, e as _e

PAGES: dict = {}

CSS = """
<style>
.ix-shell {max-width: 920px; margin: 0 auto; padding: 8px 0 40px;}
.ix-brand {font-size: 13px; font-weight: 600; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 18px;}
.ix-brand b {color: var(--ink); font-weight: 600; letter-spacing: 0.02em;
  text-transform: none; font-size: 18px;}
.ix-demo-tag {display: inline-block; margin-left: 10px; font-size: 11px;
  font-weight: 500; letter-spacing: 0.02em; color: #5c4300;
  background: var(--partial-bg); border: 1px solid #e0c56a;
  border-radius: 999px; padding: 2px 9px; vertical-align: middle;
  text-transform: none;}
.ix-h1 {font-size: 34px; font-weight: 500; letter-spacing: -0.04em;
  color: var(--ink); margin: 0 0 10px; line-height: 1.15;}
.ix-sub {font-size: 15.5px; color: var(--ink-2); line-height: 1.55;
  max-width: 560px; margin: 0 0 22px;}
.ix-actions {display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  margin-bottom: 28px;}
.ix-sec {font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--ink-3); margin: 28px 0 12px;
  padding-bottom: 8px; border-bottom: 1px solid var(--line);}
.ix-list {border: 1px solid var(--line); border-radius: 8px;
  background: var(--surface); overflow: hidden;}
.ix-row {display: grid; grid-template-columns: 36px 1fr auto 18px;
  gap: 12px; align-items: start; padding: 14px 16px;
  border-bottom: 1px solid var(--line); text-decoration: none; color: inherit;}
.ix-row:last-child {border-bottom: none;}
.ix-row:hover {background: #f8fafc;}
.ix-num {font-size: 12px; font-weight: 600; color: var(--ink-3);
  font-variant-numeric: tabular-nums; padding-top: 2px;}
.ix-text {font-size: 14px; color: var(--ink); line-height: 1.45; font-weight: 500;}
.ix-cap {display: block; font-size: 11.5px; color: var(--ink-3); font-weight: 450;
  margin-top: 4px; line-height: 1.35;}
.ix-dest {font-size: 11.5px; color: var(--ink-3); white-space: nowrap;
  padding-top: 2px; text-align: right;}
.ix-arrow {color: var(--ink-3); font-size: 14px; padding-top: 1px;}
.ix-flow {display: flex; flex-wrap: wrap; align-items: center; gap: 6px 4px;
  margin-top: 8px; font-size: 12.5px; color: var(--ink-2);}
.ix-flow span {border: 1px solid var(--line); background: var(--surface);
  border-radius: 6px; padding: 6px 10px; color: var(--ink); font-weight: 500;}
.ix-flow .sep {border: none; background: transparent; padding: 0 2px;
  color: var(--ink-3); font-weight: 400;}
.ix-foot {font-size: 12px; color: var(--ink-3); margin-top: 28px; line-height: 1.5;
  max-width: 720px;}
.ix-arrive {border: 1px solid var(--line); border-radius: 8px; background: #f8fafc;
  padding: 10px 14px; margin: 0 0 14px; font-size: 13px; color: var(--ink-2);
  display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;
  flex-wrap: wrap;}
.ix-arrive b {color: var(--ink); font-weight: 600;}
.ix-arrive .focus {display: block; margin-top: 3px; color: var(--ink-3); font-size: 12.5px;}
@media (max-width: 720px) {
  .ix-h1 {font-size: 26px;}
  .ix-row {grid-template-columns: 28px 1fr; gap: 8px;}
  .ix-dest, .ix-arrow {display: none;}
}
</style>
"""

PRESENTATION_CSS = """
<style>
/* Presentation Mode — quieter chrome, keep branding & provenance */
[data-testid="stSidebar"] .app-rail-foot {display: none !important;}
div[data-testid="stSidebarNav"] + div {opacity: 0.92;}
.ix-present-badge {display: inline-block; font-size: 11px; font-weight: 600;
  color: var(--ink-2); border: 1px solid var(--line); border-radius: 999px;
  padding: 2px 8px; margin-left: 8px;}
</style>
"""


def page_interview_home() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    _apply_presentation_chrome()
    _sync_query_params()

    st.markdown('<div class="ix-shell">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ix-brand"><b>{_e(APP_NAME)}</b>'
        f'<span class="ix-demo-tag">Interactive Product Demonstration</span></div>'
        f'<h1 class="ix-h1">Operational Risk, Connected.</h1>'
        f'<p class="ix-sub">From regulatory intelligence to risk assessment, '
        f'control effectiveness, operational resilience, and management decisions.</p>',
        unsafe_allow_html=True)

    a1, a2, a3, _ = st.columns([1.3, 1.3, 1.4, 2])
    with a1:
        if st.button("Start Guided Demo", type="primary", key="ix_start_guide",
                     width="stretch"):
            _start_guided()
    with a2:
        if st.button("Open Risk Overview", key="ix_open_ov", width="stretch"):
            if PAGES.get("overview"):
                st.switch_page(PAGES["overview"])
    with a3:
        present = st.toggle(
            "Presentation Mode",
            value=bool(st.session_state.get("presentation_mode")),
            key="ix_presentation_toggle",
            help="Focus the demo: quieter chrome, keep branding and synthetic labels.")
        st.session_state["presentation_mode"] = present

    if present:
        st.caption("Presentation Mode on · synthetic data remains labelled · "
                   "not affiliated with Revolut")

    st.markdown(
        '<div class="ix-sec">Explore the Operational Risk Lifecycle</div>',
        unsafe_allow_html=True)
    st.caption(
        "Each item is taken verbatim from the Operational Risk Manager role "
        "description and opens the ClauseWiz module that demonstrates it.")

    # Render list visually + interactive buttons for reliable Streamlit navigation
    for i, r in enumerate(ix.RESPONSIBILITIES, start=1):
        c_num, c_body, c_go = st.columns([0.35, 5.2, 1.1], gap="small")
        with c_num:
            st.markdown(
                f'<div class="ix-num">{i:02d}</div>', unsafe_allow_html=True)
        with c_body:
            st.markdown(
                f'<div class="ix-text">{_e(r["text"])}'
                f'<span class="ix-cap">{_e(r["capability"])}</span></div>',
                unsafe_allow_html=True)
        with c_go:
            if st.button("Open →", key=f"ix_go_{r['id']}", width="stretch",
                         help=r["capability"]):
                _open_responsibility(r["id"])

    st.markdown(
        '<div class="ix-sec">End-to-end workflow</div>'
        '<div class="ix-flow">'
        + "".join(
            (f'<span>{_e(step)}</span>' if j == 0 else
             f'<span class="sep">→</span><span>{_e(step)}</span>')
            for j, step in enumerate(ix.WORKFLOW))
        + "</div>",
        unsafe_allow_html=True)

    st.markdown(
        f'<p class="ix-foot">{_e(ix.DISCLAIMER)}</p></div>',
        unsafe_allow_html=True)

    with st.expander("About this demonstration"):
        st.markdown(
            "- **Risk Overview** remains available in the sidebar.\n"
            "- Enable **Demo Mode — Synthetic Data** for the payment-disruption story.\n"
            "- Guided Demo walks regulatory → risk → RCSA → KRI → incident → report.\n"
            "- Destinations use live application routes; no fabricated modules.")


def render_arrival_chrome(expected_page: str | None = None) -> None:
    """Banner on destination pages when arriving from the interview front page."""
    arr = st.session_state.get("interview_arrival")
    if not arr:
        return
    if expected_page and arr.get("page_key") != expected_page:
        return
    _apply_presentation_chrome()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="ix-arrive" role="status">'
        f'<div><b>Demonstrating · {_e(arr.get("resp_id") or "Guide")}</b>'
        f'<span class="focus">{_e(arr.get("focus") or "")}</span></div></div>',
        unsafe_allow_html=True)
    b1, b2, _ = st.columns([1.4, 1.2, 3])
    with b1:
        if st.button("← Back to Demonstration", key="ix_back_demo"):
            st.session_state.pop("interview_arrival", None)
            st.session_state.pop("interview_qp_handled", None)
            try:
                if "resp" in st.query_params:
                    del st.query_params["resp"]
            except Exception:
                pass
            if PAGES.get("interview"):
                st.switch_page(PAGES["interview"])
    with b2:
        step = demo_mode.current_step(st.session_state)
        if step and st.button("Tour Next →", key="ix_arrive_next"):
            nxt = demo_mode.next_step(st.session_state)
            if nxt:
                _arrive_from_guide(nxt)
                if PAGES.get(nxt["page_key"]):
                    st.switch_page(PAGES[nxt["page_key"]])


def _apply_presentation_chrome() -> None:
    if st.session_state.get("presentation_mode"):
        st.markdown(PRESENTATION_CSS, unsafe_allow_html=True)


def _sync_query_params() -> None:
    """Deep-link: ?resp=R01 opens that responsibility destination."""
    try:
        params = st.query_params
    except Exception:
        return
    resp = params.get("resp") if params is not None else None
    if isinstance(resp, list):
        resp = resp[0] if resp else None
    if resp and ix.by_id(str(resp)):
        # Only auto-navigate once per param set
        if st.session_state.get("interview_qp_handled") != resp:
            st.session_state["interview_qp_handled"] = resp
            _open_responsibility(str(resp))


def _open_responsibility(resp_id: str) -> None:
    r = ix.by_id(resp_id)
    if not r:
        st.error(f"Unknown responsibility {resp_id}")
        return
    page = r["page_key"]
    if not PAGES.get(page):
        st.error(f"Destination page '{page}' is not registered.")
        return
    st.session_state["interview_arrival"] = {
        "resp_id": r["id"],
        "page_key": page,
        "focus": r["focus"],
        "text": r["text"],
        "capability": r["capability"],
    }
    if r.get("prefer_risk_id"):
        st.session_state["rk_selected"] = r["prefer_risk_id"]
        st.session_state["ov_filter_ids"] = None
    if r.get("prefer_kri_id"):
        st.session_state["kri_selected"] = r["prefer_kri_id"]
    if r.get("prefer_incident_id"):
        st.session_state["inc_selected"] = r["prefer_incident_id"]
    try:
        st.query_params["resp"] = resp_id
    except Exception:
        pass
    st.switch_page(PAGES[page])


def _start_guided() -> None:
    demo_mode.enable(st.session_state)
    demo_mode.ensure_seeded()
    # Align tour with six-step interview guide
    st.session_state["demo_tour_active"] = True
    st.session_state["demo_tour_step"] = 1
    st.session_state["presentation_mode"] = True
    step = demo_mode.current_step(st.session_state)
    if step:
        _arrive_from_guide(step)
        if PAGES.get(step["page_key"]):
            st.switch_page(PAGES[step["page_key"]])


def _arrive_from_guide(step: dict) -> None:
    st.session_state["interview_arrival"] = {
        "resp_id": f"Guide {step.get('step')}",
        "page_key": step["page_key"],
        "focus": step.get("focus") or step.get("explain") or "",
        "text": step.get("title") or "",
        "capability": "Guided demonstration",
    }
    if step.get("prefer_risk_id"):
        st.session_state["rk_selected"] = step["prefer_risk_id"]
    if step.get("prefer_kri_id"):
        st.session_state["kri_selected"] = step["prefer_kri_id"]
    if step.get("prefer_incident_id"):
        st.session_state["inc_selected"] = step["prefer_incident_id"]


def wrap_page(page_key: str, fn):
    """Wrap a Streamlit page so interview arrival chrome appears when relevant."""
    def _wrapped():
        if page_key in ix.destination_pages():
            render_arrival_chrome(page_key)
        elif st.session_state.get("presentation_mode"):
            _apply_presentation_chrome()
        fn()
    _wrapped.__name__ = getattr(fn, "__name__", page_key)
    _wrapped.__doc__ = getattr(fn, "__doc__", None)
    return _wrapped
