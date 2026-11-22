"""
Clausewiz -- regulatory risk comparison and operational risk workspace.

Run with:  streamlit run app.py   (from inside the .venv)

This file wires screens and Demo Mode. Design rules: DESIGN.md.
Logic lives in the orm/ package.
"""
import os
import sys
import threading

import streamlit as st

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if not sys.path or os.path.abspath(sys.path[0] or ".") != _APP_DIR:
    sys.path.insert(0, _APP_DIR)

_FRESH = ("orm", "orm_compare", "ui_theme", "controls_views", "risk_views",
          "regulatory_views", "rcsa_views", "kri_views", "incident_views",
          "resilience_views", "exec_report_views", "overview_views",
          "change_impact_views", "interview_views")
with sys.__dict__.setdefault("_clausewiz_import_lock", threading.RLock()):
    for _name in list(sys.modules):
        if _name in _FRESH or _name.startswith("orm."):
            del sys.modules[_name]
    from ui_theme import APP_NAME, apply_theme  # noqa: E402
    import change_impact_views  # noqa: E402
    import controls_views  # noqa: E402
    import exec_report_views  # noqa: E402
    import incident_views  # noqa: E402
    import interview_views  # noqa: E402
    import kri_views  # noqa: E402
    import orm_compare  # noqa: E402
    import overview_views  # noqa: E402
    import rcsa_views  # noqa: E402
    import reference_views  # noqa: E402
    import regulatory_views  # noqa: E402
    import resilience_views  # noqa: E402
    import risk_views  # noqa: E402
    from orm import demo_mode  # noqa: E402

st.set_page_config(page_title=APP_NAME,
                   page_icon=":material/account_balance:", layout="wide",
                   initial_sidebar_state="expanded")

if not hasattr(orm_compare, "page_compare"):
    st.error("Loaded an outdated orm_compare from "
             f"{getattr(orm_compare, '__file__', None) or orm_compare.__path__}. "
             f"Expected {os.path.join(_APP_DIR, 'orm_compare.py')}.")
    st.stop()

# Demo Mode isolates ORM_RISK_DB before any page opens a risk session.
demo_mode.apply_env(st.session_state)

apply_theme()

# Wrap destination pages so interview arrival chrome can appear.
_w = interview_views.wrap_page
PAGES = {
    # Default landing is "/" (Streamlit serves default=True at root; a custom
    # url_path would 404). Sidebar title remains "Demonstration".
    "interview": st.Page(interview_views.page_interview_home,
                         title="Demonstration",
                         icon=":material/account_tree:",
                         default=True),
    "overview": st.Page(_w("overview", overview_views.page_overview),
                        title="Overview",
                        icon=":material/dashboard:", url_path="overview"),
    "home": st.Page(orm_compare.page_home, title="Home",
                    icon=":material/home:", url_path="home"),
    "compare": st.Page(orm_compare.page_compare, title="Compare",
                       icon=":material/compare_arrows:", url_path="compare"),
    "coverage": st.Page(orm_compare.page_coverage, title="Coverage",
                        icon=":material/grid_view:", url_path="coverage"),
    "gaps": st.Page(orm_compare.page_gaps, title="Gaps",
                    icon=":material/rule:", url_path="gaps"),
    "deadlines": st.Page(orm_compare.page_deadlines, title="Deadlines",
                         icon=":material/schedule:", url_path="deadlines"),
    "changes": st.Page(orm_compare.page_changes, title="Changes",
                       icon=":material/update:", url_path="changes"),
    "obligations": st.Page(controls_views.page_obligations, title="Obligations",
                           icon=":material/checklist:", url_path="obligations"),
    "controls": st.Page(_w("controls", controls_views.page_controls),
                        title="Controls",
                        icon=":material/verified_user:", url_path="controls"),
    "audit": st.Page(controls_views.page_audit, title="Audit readiness",
                     icon=":material/fact_check:", url_path="audit"),
    "risks": st.Page(_w("risks", risk_views.page_risks), title="Risk register",
                     icon=":material/report:", url_path="risks"),
    "rcsa": st.Page(_w("rcsa", rcsa_views.page_rcsa), title="RCSA",
                    icon=":material/grid_on:", url_path="rcsa"),
    "kri": st.Page(_w("kri", kri_views.page_kri), title="KRI Monitoring",
                   icon=":material/monitoring:", url_path="kri"),
    "incidents": st.Page(_w("incidents", incident_views.page_incidents),
                         title="Incident Management",
                         icon=":material/emergency:", url_path="incidents"),
    "resilience": st.Page(_w("resilience", resilience_views.page_resilience),
                          title="Operational Resilience",
                          icon=":material/hub:", url_path="resilience"),
    "risk_report": st.Page(risk_views.page_report, title="Risk report",
                           icon=":material/summarize:", url_path="risk-report"),
    "executive": st.Page(_w("executive", exec_report_views.page_executive_report),
                         title="Executive report",
                         icon=":material/clinical_notes:",
                         url_path="executive-report"),
    "regulatory": st.Page(
        _w("regulatory", regulatory_views.page_regulatory_intelligence),
        title="Regulatory Intelligence",
        icon=":material/policy:", url_path="regulatory"),
    "change_impact": st.Page(change_impact_views.page_change_impact,
                             title="Regulatory Change Impact",
                             icon=":material/difference:",
                             url_path="change-impact"),
    "sources": st.Page(reference_views.page_sources, title="Sources",
                       icon=":material/description:", url_path="sources"),
}

# Share page map for switch_page / guided tour
orm_compare.PAGES = PAGES
controls_views.PAGES = PAGES
risk_views.PAGES = PAGES
rcsa_views.PAGES = PAGES
kri_views.PAGES = PAGES
incident_views.PAGES = PAGES
resilience_views.PAGES = PAGES
exec_report_views.PAGES = PAGES
regulatory_views.PAGES = PAGES
overview_views.PAGES = PAGES
change_impact_views.PAGES = PAGES
interview_views.PAGES = PAGES

# Sidebar IA: Demonstration front page, then lifecycle (DESIGN.md).
nav = st.navigation({
    "Demonstration": [PAGES["interview"]],
    "Overview": [PAGES["overview"]],
    "Regulatory Intelligence": [
        PAGES["regulatory"], PAGES["change_impact"], PAGES["obligations"],
        PAGES["sources"],
    ],
    "Compare": [
        PAGES["home"], PAGES["compare"], PAGES["coverage"], PAGES["gaps"],
        PAGES["deadlines"], PAGES["changes"],
    ],
    "Risk Register": [PAGES["risks"]],
    "Controls & RCSA": [PAGES["controls"], PAGES["rcsa"], PAGES["audit"]],
    "KRI Monitoring": [PAGES["kri"]],
    "Incident Management": [PAGES["incidents"]],
    "Operational Resilience": [PAGES["resilience"]],
    "Management Reporting": [PAGES["executive"], PAGES["risk_report"]],
}, position="sidebar")

overview_views.render_sidebar_demo_controls(PAGES)

st.sidebar.markdown(
    '<div class="app-rail-foot">Israel · Jordan · Turkey<br>'
    'Obligation → risk → control → KRI → incident → report.<br>'
    'Every claim cites its source.</div>',
    unsafe_allow_html=True)

# Persistent demo banner on every page when Demo Mode is on
if demo_mode.is_enabled(st.session_state):
    from ui_theme import demo_banner_html
    st.markdown(demo_banner_html(demo_mode.DEMO_BANNER), unsafe_allow_html=True)

nav.run()
