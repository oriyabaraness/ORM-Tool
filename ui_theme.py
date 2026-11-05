"""Shared look for every screen: the DESIGN.md tokens as CSS, plus a few
small building blocks (page header, notice, status pill, citation line).

Every screen calls apply_theme() once (app.py does it before navigation), and
uses these helpers instead of writing its own colors or fonts.
"""
from __future__ import annotations

import html

import streamlit as st

# One place for the product name (DESIGN.md: "renaming later is one change").
APP_NAME = "Banking ORM Tool"

# Country accents: thin rules and small dots only, never fills.
COUNTRY_ACCENT = {"IL": "#006d7e", "JO": "#9b2f4a", "TR": "#8a6a1f",
                  "Israel": "#006d7e", "Jordan": "#9b2f4a",
                  "Turkey": "#8a6a1f"}

THEME_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap");
:root {
  --ink: #14171f; --ink-2: #4a5160; --ink-3: #7b8292;
  --line: #e3e5ea; --surface: #ffffff; --canvas: #f6f7f9; --subtle: #f0f2f5;
  --primary: #17345b; --primary-hover: #102845; --focus: #3b6fd8;
  --found: #2f7a4a; --found-bg: #e8f3ec;
  --partial: #9a6a00; --partial-bg: #fbf2dc;
  --gap: #b3261e; --gap-bg: #fbe9e7;
  --na: #7b8292; --na-bg: #f0f2f5;
  --highlight: #fff1b8;
  --il: #006d7e; --jo: #9b2f4a;
  --ui: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --serif: "Source Serif 4", Georgia, "Times New Roman", serif;
}

/* ---- app chrome ---------------------------------------------------- */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: var(--canvas); color: var(--ink);
}
[data-testid="stAppViewContainer"] *:not([class*="material"]):not(code):not(pre) {
  font-family: var(--ui);
}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stMainBlockContainer"], .block-container {
  padding-top: 1.6rem; padding-bottom: 3rem; max-width: 100%;
}
p, li, label, .stMarkdown {font-size: 14px; line-height: 1.45;}
h1, h2, h3 {color: var(--ink); letter-spacing: -0.01em;}
h2 {font-size: 17px !important; font-weight: 600 !important; margin: 18px 0 6px !important;}
h3 {font-size: 15px !important; font-weight: 600 !important;}
a {color: var(--primary);}
code {font-size: 12.5px; background: var(--subtle); color: var(--ink); padding: 1px 4px;
  border-radius: 4px;}
*:focus-visible {outline: 2px solid var(--focus) !important; outline-offset: 1px;}
.tabular, [data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}

/* left rail */
[data-testid="stSidebar"] {background: var(--surface); border-right: 1px solid var(--line);}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top: 6px;}
[data-testid="stSidebarNav"] [data-testid="stNavSectionHeader"],
[data-testid="stSidebarNav"] header {
  font-size: 11px !important; text-transform: uppercase; letter-spacing: .06em;
  color: var(--ink-3) !important; font-weight: 600 !important;
}
[data-testid="stSidebarNavLink"] {border-radius: 6px; padding: 5px 10px;}
[data-testid="stSidebarNavLink"] span {font-size: 14px; color: var(--ink-2);}
[data-testid="stSidebarNavLink"]:hover {background: var(--subtle);}
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: var(--subtle); box-shadow: inset 3px 0 0 var(--primary);
}
[data-testid="stSidebarNavLink"][aria-current="page"] span {color: var(--primary); font-weight: 600;}
.app-brand {font-weight: 600; font-size: 15px; color: var(--ink); padding: 2px 10px 0;}
.app-brand small {display: block; font-weight: 400; font-size: 12px; color: var(--ink-3);}
.app-rail-foot {font-size: 12px; color: var(--ink-3); padding: 0 10px; line-height: 1.5;}

/* widgets */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label {
  font-size: 12px !important; font-weight: 500; color: var(--ink-2);
}
div[data-baseweb="select"] > div, div[data-baseweb="input"], .stTextInput input,
.stTextArea textarea {
  border-radius: 6px !important; border-color: var(--line) !important;
  background: var(--surface) !important; font-size: 14px;
}
.stButton button, .stDownloadButton button, [data-testid="stPopover"] button {
  border-radius: 4px; font-size: 13px; font-weight: 500; box-shadow: none;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink);
}
.stButton button:hover, .stDownloadButton button:hover {border-color: var(--ink-3); color: var(--ink);}
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background: var(--primary) !important; border-color: var(--primary) !important;
  color: #fff !important;
}
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  background: var(--primary-hover) !important;
}
[data-baseweb="tab-list"] {gap: 20px; border-bottom: 1px solid var(--line);}
[data-baseweb="tab"] {padding: 6px 0 !important; font-size: 13px; color: var(--ink-2);}
[data-baseweb="tab"][aria-selected="true"] {color: var(--primary); font-weight: 600;}
[data-baseweb="tab-highlight"] {background: var(--primary) !important; height: 2px;}
[data-baseweb="tab-border"] {display: none;}
[data-testid="stMetric"] {background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 10px 12px;}
[data-testid="stMetricLabel"] p {font-size: 12px !important; color: var(--ink-3);}
[data-testid="stMetricValue"] {font-size: 22px !important; color: var(--ink);}
[data-testid="stExpander"] details {border: 1px solid var(--line); border-radius: 6px;
  background: var(--surface);}
[data-testid="stDataFrame"], [data-testid="stTable"] {border: 1px solid var(--line);
  border-radius: 6px; background: var(--surface);}
[data-testid="stAlert"] {border-radius: 6px;}
hr {border-color: var(--line) !important;}

/* ---- building blocks ----------------------------------------------- */
.page-head {display: flex; justify-content: space-between; align-items: flex-end;
  gap: 16px; border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 14px;}
.page-title {font-size: 20px; line-height: 1.3; font-weight: 600; color: var(--ink); margin: 0;}
.page-sub {font-size: 13px; color: var(--ink-2); margin-top: 2px; max-width: 820px;}
.pane-head {font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
  font-weight: 600; color: var(--ink-2); padding: 0 0 6px; margin: 4px 0 8px;
  border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 8px;}
.pane-head .dot {width: 8px; height: 8px; border-radius: 50%; display: inline-block;}
.pane-head .count {margin-left: auto; text-transform: none; letter-spacing: 0;
  font-weight: 500; color: var(--ink-3); font-variant-numeric: tabular-nums;}
.notice {background: var(--subtle); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 12px; font-size: 13px; color: var(--ink-2); margin: 6px 0 10px;}
.notice.warn {background: var(--partial-bg); border-color: #f0dfb1; color: #5c4300;}
.notice.gap {background: var(--gap-bg); border-color: #f3cfca; color: #7d1c15;}
.notice b {color: var(--ink);}
.pill {display: inline-block; font-size: 11.5px; font-weight: 500; line-height: 18px;
  padding: 0 8px; border-radius: 999px; white-space: nowrap;}
.pill.found, .pill.strong {color: var(--found); background: var(--found-bg);}
.pill.partial {color: var(--partial); background: var(--partial-bg);}
.pill.not-found, .pill.gap {color: var(--gap); background: var(--gap-bg);}
.pill.not-assessed, .pill.weak, .pill.na {color: var(--na); background: var(--na-bg);}
.tag {display: inline-block; font-size: 12px; padding: 0 7px; line-height: 20px;
  border-radius: 999px; border: 1px solid var(--line); background: var(--surface);
  color: var(--ink-2); margin: 6px 4px 0 0;}
.cite {font-size: 12.5px; color: var(--ink-3); font-weight: 500;
  font-variant-numeric: tabular-nums; margin-bottom: 6px;}
.cite b {color: var(--ink); font-weight: 600;}
.cite a {margin-left: 6px; text-decoration: none; white-space: nowrap;}
.law {font-family: var(--serif) !important; font-size: 15.5px; line-height: 1.65;
  color: var(--ink);}
.law * {font-family: var(--serif) !important;}
mark {background: var(--highlight); color: inherit; padding: 0 1px; border-radius: 2px;}
.card {background: var(--surface); border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 14px; margin: 0 0 10px;}

/* ---- older Sources / Market context pieces, restyled to the tokens ---- */
.boi-section-title {font-size: 17px; font-weight: 600; color: var(--ink); margin: 18px 0 8px;}
.boi-kicker {font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--ink-3); font-weight: 600;}
.boi-catalog-shelf {display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px; margin: 6px 0 14px;}
.boi-catalog-type {background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 10px 12px; position: relative; overflow: hidden;}
.boi-catalog-rule {position: absolute; left: 0; top: 0; bottom: 0; width: 3px;}
.boi-catalog-title {font-weight: 600; font-size: 13px; color: var(--ink);}
.boi-catalog-copy {font-size: 12px; color: var(--ink-2); margin: 2px 0 6px; line-height: 1.4;}
.boi-catalog-meta {font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums;}
.boi-compare-panel {background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 12px 14px; margin: 8px 0 14px;}
.boi-compare-head {display: flex; justify-content: space-between; gap: 12px; align-items: baseline;}
.boi-compare-title {font-weight: 600; font-size: 14px; color: var(--ink);}
.boi-compare-count {font-size: 12px; color: var(--ink-3);}
.boi-compare-grid {display: grid; grid-template-columns: 1fr auto 1fr; gap: 12px;
  align-items: start; margin-top: 10px;}
.boi-compare-venn {display: flex; align-items: center; justify-content: center; gap: 0;}
.boi-compare-circle {width: 54px; height: 54px; border-radius: 50%; border: 2px solid var(--line);
  display: flex; align-items: center; justify-content: center; font-size: 12px;
  font-weight: 600; color: var(--ink-2); background: var(--surface);}
.boi-compare-overlap {font-size: 12px; color: var(--ink-2);}
.boi-compare-chip {display: inline-block; font-size: 12px; padding: 0 7px; line-height: 20px;
  border-radius: 999px; border: 1px solid var(--line); margin: 3px 4px 0 0; color: var(--ink-2);}
.boi-definition-links {display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 10px;}
.boi-definition-link {font-size: 12px; color: var(--primary); text-decoration: none;
  border: 1px solid var(--line); border-radius: 999px; padding: 0 8px; line-height: 20px;}
.boi-definition-popover {font-size: 13px; color: var(--ink-2);}

@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"], .block-container {padding-left: 16px; padding-right: 16px;}
  .page-head {flex-direction: column; align-items: flex-start;}
  .boi-compare-grid {grid-template-columns: 1fr;}
}
</style>
"""


def e(value) -> str:
    """HTML-escape anything (None -> '')."""
    return html.escape("" if value is None else str(value))


def apply_theme() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    sub = f'<div class="page-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="page-head"><div><h1 class="page-title">{e(title)}</h1>'
                f'{sub}</div></div>', unsafe_allow_html=True)


def pane_head(label: str, *, country: str | None = None, count: str = "") -> str:
    dot = (f'<span class="dot" style="background:{COUNTRY_ACCENT[country]}"></span>'
           if country in COUNTRY_ACCENT else "")
    right = f'<span class="count">{e(count)}</span>' if count else ""
    return f'<div class="pane-head">{dot}{e(label)}{right}</div>'


def notice(body_html: str, kind: str = "") -> str:
    """One-sentence honest-state message. kind: '', 'warn' or 'gap'."""
    return f'<div class="notice {kind}">{body_html}</div>'


def pill(label: str, kind: str) -> str:
    return f'<span class="pill {e(kind)}">{e(label)}</span>'


def citation(regulator: str, doc_ref: str, clause_ref: str, title: str,
             link: str | None = None) -> str:
    """`Regulator · Document ref §clause · Title  Open in source ↗`"""
    ref = " ".join(x for x in (doc_ref, clause_ref) if x)
    parts = [e(regulator)] if regulator else []
    if ref:
        parts.append(f"<b>{e(ref)}</b>")
    if title and title != doc_ref:
        parts.append(e(title))
    open_link = (f'<a href="{e(link)}" target="_blank">Open in source ↗</a>'
                 if link else "")
    return f'<div class="cite">{" · ".join(parts)}{open_link}</div>'
