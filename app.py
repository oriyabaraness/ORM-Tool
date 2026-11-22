"""
Clausewiz -- regulatory risk comparison and controls workspace (Streamlit).

Run with:  streamlit run app.py   (from inside the .venv)

This file only wires screens together:
  - orm_compare.py      Home, Compare, Coverage, Gaps, Deadlines, Changes
  - controls_views.py   Obligations, Controls, Audit readiness
  - risk_views.py       Risk register, Risk report
  - reference_views.py  Sources (catalog + PDF reader), Market context
Design rules: DESIGN.md. Logic lives in the orm/ package.
"""
import os
import sys
import threading

import streamlit as st

# Always load this project's own modules from this folder, even if another
# copy of the project (or a stale module with the same name) is on Python's
# path -- otherwise an older orm_compare / orm could be picked up instead.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if not sys.path or os.path.abspath(sys.path[0] or ".") != _APP_DIR:
    sys.path.insert(0, _APP_DIR)
# Re-import them fresh on every run, so a long-running app server never keeps
# an old version in memory after the code is updated (e.g. after git pull).
# Two sessions running at once share sys.modules: without the lock, one can
# delete orm.match while the other is half-way through importing it. The lock
# lives on `sys` because this file is re-executed on every run.
_FRESH = ("orm", "orm_compare", "ui_theme", "controls_views", "risk_views",
          "regulatory_views", "rcsa_views")
with sys.__dict__.setdefault("_clausewiz_import_lock", threading.RLock()):
    for _name in list(sys.modules):
        if _name in _FRESH or _name.startswith("orm."):
            del sys.modules[_name]
    from ui_theme import APP_NAME, apply_theme  # noqa: E402
    import controls_views  # noqa: E402
    import orm_compare  # noqa: E402
    import rcsa_views  # noqa: E402
    import reference_views  # noqa: E402
    import regulatory_views  # noqa: E402
    import risk_views  # noqa: E402

st.set_page_config(page_title=APP_NAME,
                   page_icon=":material/account_balance:", layout="wide",
                   initial_sidebar_state="expanded")

if not hasattr(orm_compare, "page_compare"):
    st.error("Loaded an outdated orm_compare from "
             f"{getattr(orm_compare, '__file__', None) or orm_compare.__path__}. "
             f"Expected {os.path.join(_APP_DIR, 'orm_compare.py')}.")
    st.stop()

apply_theme()

PAGES = {
    "home": st.Page(orm_compare.page_home, title="Home",
                    icon=":material/home:", url_path="home", default=True),
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
    "controls": st.Page(controls_views.page_controls, title="Controls",
                        icon=":material/verified_user:", url_path="controls"),
    "audit": st.Page(controls_views.page_audit, title="Audit readiness",
                     icon=":material/fact_check:", url_path="audit"),
    "risks": st.Page(risk_views.page_risks, title="Risk register",
                     icon=":material/report:", url_path="risks"),
    "rcsa": st.Page(rcsa_views.page_rcsa, title="RCSA",
                    icon=":material/grid_on:", url_path="rcsa"),
    "risk_report": st.Page(risk_views.page_report, title="Risk report",
                           icon=":material/summarize:", url_path="risk-report"),
    "regulatory": st.Page(regulatory_views.page_regulatory_intelligence,
                          title="Regulatory Intelligence",
                          icon=":material/policy:", url_path="regulatory"),
    "sources": st.Page(reference_views.page_sources, title="Sources",
                       icon=":material/description:", url_path="sources"),
    # Market context (reference_views.page_market: regional map, FX reserves,
    # rates) is switched off: macro data is not part of the controls workflow.
    # To bring it back, add an st.Page for it here and list it under Reference.
}
orm_compare.PAGES = PAGES
controls_views.PAGES = PAGES
risk_views.PAGES = PAGES
rcsa_views.PAGES = PAGES
regulatory_views.PAGES = PAGES

nav = st.navigation({
    "Compare": [PAGES["home"], PAGES["compare"], PAGES["coverage"], PAGES["gaps"],
                PAGES["deadlines"], PAGES["changes"]],
    "Controls": [PAGES["obligations"], PAGES["controls"], PAGES["audit"]],
    "Risk": [PAGES["risks"], PAGES["rcsa"], PAGES["risk_report"], PAGES["regulatory"]],
    "Reference": [PAGES["sources"]],
}, position="sidebar")
st.sidebar.markdown(
    '<div class="app-rail-foot">Israel · Jordan · Turkey<br>'
    'Regulation → obligation → risk → control → evidence. Every item cites its clause.</div>',
    unsafe_allow_html=True)
nav.run()
