"""RCSA workspace: register, heat map, gaps, and obligation → risk workflow.

Logic in orm.risk / orm.rcsa; this file only renders. Prototype methodology —
not any bank's approved framework. Follows DESIGN.md.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import controls_views
import risk_views
from orm import audit, demo_data, rcsa, risk, state, taxonomy
from ui_theme import e as _e, notice, page_header, pane_head, pill

PAGES: dict = {}

BAND_KIND = risk_views.BAND_KIND
APPETITE_KIND = risk_views.APPETITE_KIND
RAG_KIND = risk_views.RAG_KIND
RATING_KIND = risk_views.RATING_KIND

CSS = """
<style>
.rcsa-scale {display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px; margin: 8px 0 14px; font-size: 12.5px; color: var(--ink-2);}
.rcsa-scale div {border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;
  background: var(--surface);}
.rcsa-scale b {color: var(--ink); display: block; margin-bottom: 4px;}
.rcsa-heat {display: grid; grid-template-columns: 36px repeat(5, minmax(48px, 1fr));
  gap: 3px; max-width: 460px; font-size: 12px; font-variant-numeric: tabular-nums;}
.rcsa-heat .ax {color: var(--ink-3); display: flex; align-items: center; justify-content: center;}
.rcsa-cell {border-radius: 6px; min-height: 44px; padding: 4px; display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  color: var(--ink-2); border: 1px solid var(--line); cursor: default;}
.rcsa-cell b {font-size: 15px; color: var(--ink);}
.rcsa-cell.low {background: var(--found-bg);}
.rcsa-cell.moderate {background: var(--partial-bg);}
.rcsa-cell.high {background: var(--gap-bg);}
.rcsa-cell.critical {background: #f7d4d0;}
.rcsa-scroll {overflow-x: auto; max-width: 100%;}
</style>
"""


def page_rcsa() -> None:
    page_header("RCSA", "Risk and Control Self-Assessment — identify, rate, control "
                "and monitor operational risks across business processes.")
    st.markdown(CSS, unsafe_allow_html=True)
    ctx, index = controls_views._open()
    try:
        with risk.session() as conn:
            demo_data.seed(conn, index)
            risk_views._banner(conn)
            st.markdown(notice(
                "<b>Prototype methodology.</b> " + _e(risk.METHOD_NOTE), "warn"),
                unsafe_allow_html=True)
            tabs = st.tabs([
                "Register & heat map",
                "Risk detail",
                "Control gaps",
                "Create from obligation",
                "Scales & taxonomy",
            ])
            with tabs[0]:
                _panel_register(conn)
            with tabs[1]:
                _panel_detail(conn, index)
            with tabs[2]:
                _panel_gaps(conn)
            with tabs[3]:
                _panel_create(conn, index)
            with tabs[4]:
                _panel_scales()
            risk_views._render_demo_tools(conn, index)
    finally:
        ctx.__exit__(None, None, None)


def _scale_card() -> str:
    like = " · ".join(f"{k} {v}" for k, v in risk.LIKELIHOOD_LABELS.items())
    impact = " · ".join(f"{k} {v}" for k, v in risk.IMPACT_LABELS.items())
    bands = " · ".join(f"≤{t} {lab}" for t, lab in risk.BANDS)
    dims = ", ".join(risk.IMPACT_DIMENSIONS)
    return (
        '<div class="rcsa-scale">'
        f"<div><b>Likelihood</b>{_e(like)}</div>"
        f"<div><b>Impact</b>{_e(impact)}</div>"
        f"<div><b>Bands (configurable)</b>{_e(bands)}</div>"
        f"<div><b>Impact dimensions</b>{_e(dims)} — demo aggregates with "
        f"<b>max</b></div></div>"
    )


def _heat_html(reg: pd.DataFrame, view: str) -> str:
    heat = rcsa.heat_map(reg, view=view)
    cells = ['<div class="rcsa-heat"><div class="ax"></div>']
    for i in range(1, 6):
        cells.append(f'<div class="ax">I{i}</div>')
    for like in range(5, 0, -1):
        cells.append(f'<div class="ax">L{like}</div>')
        for imp in range(1, 6):
            n = int(heat.loc[imp, like])
            score = like * imp
            cls = risk.band(score).lower()
            cells.append(
                f'<div class="rcsa-cell {cls}" title="L{like}×I{imp}={score}">'
                f'<b>{n}</b><span>{score}</span></div>')
    cells.append("</div>")
    cells.append(
        f'<div class="rk-heat-cap">X = impact · Y = likelihood · view = {_e(view)} · '
        "cell shows count and score</div>")
    return "".join(cells)


def _panel_register(conn) -> None:
    st.markdown(_scale_card(), unsafe_allow_html=True)
    reg = risk.register(conn)
    if reg.empty:
        st.markdown(notice("No risks in the register yet."), unsafe_allow_html=True)
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        units = ["All"] + sorted({u for u in reg["business_unit"] if u})
        unit = st.selectbox("Business unit", units, key="rcsa_unit")
    with c2:
        cats = ["All"] + sorted(reg["category_id"].unique().tolist())
        cat = st.selectbox("Risk category", cats, key="rcsa_cat",
                           format_func=lambda c: taxonomy.BY_ID[c].name
                           if c in taxonomy.BY_ID else c)
    with c3:
        events = ["All"] + sorted({e for e in reg["event_type"] if e})
        event = st.selectbox("Event type", events, key="rcsa_evt")
    with c4:
        view = st.selectbox("Heat map view", ["residual", "inherent"], key="rcsa_view")
    filtered = rcsa.filter_register(
        reg,
        business_unit="" if unit == "All" else unit,
        category_id="" if cat == "All" else cat,
        event_type="" if event == "All" else event)
    st.markdown(risk_views._status_line([
        ("risks shown", str(len(filtered))),
        ("outside appetite", str(int((filtered["appetite"] == "Outside appetite").sum()))),
        ("residual not approved", str(int((~filtered["residual_assessed"]).sum()))),
        ("no controls", str(int((filtered["controls"] == 0).sum()))),
    ]), unsafe_allow_html=True)
    left, right = st.columns([1, 2.1])
    with left:
        st.markdown(pane_head(f"{view.capitalize()} heat map"), unsafe_allow_html=True)
        st.markdown(_heat_html(filtered, view), unsafe_allow_html=True)
    with right:
        st.markdown(pane_head("Risk register", count=f"{len(filtered)}"),
                    unsafe_allow_html=True)
        show = filtered[[
            "id", "title", "business_unit", "event_type", "owner",
            "inherent_score", "inherent_band", "residual_score", "residual_band",
            "residual_status", "appetite", "controls", "obligations",
        ]].rename(columns={
            "id": "Risk ID", "title": "Title", "business_unit": "Unit",
            "event_type": "Event type", "owner": "Owner",
            "inherent_score": "Inherent", "inherent_band": "Inh. band",
            "residual_score": "Residual", "residual_band": "Res. band",
            "residual_status": "Residual status", "appetite": "Appetite",
            "controls": "Controls", "obligations": "Obligations",
        })
        st.dataframe(show, hide_index=True, width="stretch")
    if "DEMO-RISK-001" in filtered["id"].values:
        st.caption("DEMO-RISK-001 is synthetic centrepiece data for the interview walkthrough.")


def _panel_detail(conn, index) -> None:
    reg = risk.register(conn)
    if reg.empty:
        st.markdown(notice("No risks to open."), unsafe_allow_html=True)
        return
    ids = reg["id"].tolist()
    default = ids.index("DEMO-RISK-001") if "DEMO-RISK-001" in ids else 0
    labels = dict(zip(reg["id"], reg["id"] + " · " + reg["title"]))
    risk_id = st.selectbox("Open a risk", ids, index=default, key="rcsa_detail",
                           format_func=labels.get)
    chain = risk.risk_chain(conn, risk_id, index)
    r, s = chain["risk"], chain["summary"]
    st.markdown(pane_head(f"{r['id']} · {r['title']}"), unsafe_allow_html=True)
    cross = ", ".join(rcsa.parse_cross_cutting(r.get("cross_cutting"))) or "—"
    st.markdown(
        '<div class="rk-kv">' + "".join(
            f"<span>{_e(k)}</span><b>{_e(v)}</b>" for k, v in [
                ("Business process", r.get("business_process") or s.get("business_process") or "—"),
                ("Business unit", r.get("business_unit") or "—"),
                ("Legal entity", r.get("legal_entity") or "—"),
                ("Jurisdiction", r.get("jurisdiction") or "—"),
                ("Event type", r.get("event_type") or "—"),
                ("Cross-cutting", cross),
                ("Owner", r.get("owner") or "—"),
                ("Status", r.get("status") or "—"),
            ]) + "</div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="rk-scores">'
        f'<span>Inherent <b>{s["inherent_score"]}</b> '
        f'{pill(s["inherent_band"], BAND_KIND[s["inherent_band"]])} '
        f'L{s["inherent_likelihood"]} ({risk.LIKELIHOOD_LABELS[s["inherent_likelihood"]]}) '
        f'× I{s["inherent_impact"]} ({risk.IMPACT_LABELS[s["inherent_impact"]]})</span>'
        f'<span>Residual <b>{s["residual_score"]}</b> '
        f'{pill(s["residual_band"], BAND_KIND[s["residual_band"]])} '
        f'L{s["residual_likelihood"]} × I{s["residual_impact"]} · '
        f'{pill("Approved" if s["residual_assessed"] else "Not approved", "found" if s["residual_assessed"] else "partial")}</span>'
        f'<span>{pill(s["appetite"], APPETITE_KIND[s["appetite"]])}</span>'
        "</div>", unsafe_allow_html=True)

    overview, assessment, controls_t, kris_t, incs_t, regs_t, rem_t, hist_t = st.tabs([
        "Overview", "Assessment", "Controls", "KRIs", "Incidents",
        "Regulatory Links", "Remediation", "Audit History",
    ])
    with overview:
        st.markdown(f"**Risk event.** {_e(r.get('description') or '')}")
        st.markdown(f"**Causes.** {_e(r.get('cause') or '')}")
        st.markdown(f"**Potential consequences.** {_e(r.get('effect') or '')}")
        dims = [(d, r.get(f"impact_{d}")) for d in risk.IMPACT_DIMENSIONS]
        st.markdown("**Impact dimensions** (demo aggregates with max):")
        st.markdown(", ".join(
            f"{d}={v}" for d, v in dims if v not in (None, "", float("nan"))
            and not (isinstance(v, float) and pd.isna(v))) or "Not set")
    with assessment:
        _assessment_tab(conn, r, s)
    with controls_t:
        risk_views._render_controls(chain["controls"])
        st.caption("Design effectiveness ≠ operating effectiveness. Documentation alone "
                   "is not proof of operating effectiveness.")
    with kris_t:
        risk_views._render_kris(conn, chain["kris"])
    with incs_t:
        risk_views._render_incidents(chain["incidents"], chain["incident_links"], index)
    with regs_t:
        risk_views._render_obligations(conn, risk_id, chain["obligations"])
    with rem_t:
        risk_views._render_actions(chain["actions"])
    with hist_t:
        log = risk.history(conn, object_id=risk_id, limit=80)
        if not log:
            st.markdown(notice("No audit entries for this risk yet."),
                        unsafe_allow_html=True)
        else:
            st.dataframe(pd.DataFrame([{
                "When (UTC)": x["ts"], "Who": x["actor"],
                "What": f"{x['action']} {x['table_name']}",
            } for x in log]), hide_index=True, width="stretch")


def _assessment_tab(conn, r: dict, s: dict) -> None:
    name = controls_views._reviewer_box("rcsa_assess_name")
    st.caption("Residual risk must be set explicitly. The suggestion below is optional "
               "and never applied without confirmation.")
    sug = rcsa.suggest_residual(conn, r["id"])
    st.markdown(
        f"Suggested residual (from control ratings, illustrative only): "
        f"L{sug['suggested_likelihood']} × I{sug['suggested_impact']} = "
        f"**{sug['suggested_score']}**. {_e(sug['note'])}")
    c1, c2 = st.columns(2)
    with c1:
        like = st.selectbox(
            "Residual likelihood", list(range(1, 6)),
            index=max(0, int(s["residual_likelihood"]) - 1),
            format_func=lambda n: f"{n} · {risk.LIKELIHOOD_LABELS[n]}",
            key=f"rcsa_rl_{r['id']}")
    with c2:
        imp = st.selectbox(
            "Residual impact", list(range(1, 6)),
            index=max(0, int(s["residual_impact"]) - 1),
            format_func=lambda n: f"{n} · {risk.IMPACT_LABELS[n]}",
            key=f"rcsa_ri_{r['id']}")
    why = st.text_area("Explanation of the residual assessment",
                       value=r.get("residual_rationale") or "",
                       key=f"rcsa_why_{r['id']}")
    evidence = st.text_area("Supporting evidence",
                            value=r.get("residual_evidence") or "",
                            key=f"rcsa_ev_{r['id']}")
    if st.button("Approve residual assessment", key=f"rcsa_approve_{r['id']}",
                 disabled=not name):
        try:
            risk.approve_residual(conn, r["id"], int(like), int(imp),
                                  rationale=why, evidence=evidence, actor=name)
            conn.commit()
            st.success(f"Residual approved: L{like} × I{imp} = {like * imp}.")
            st.rerun()
        except ValueError as exc:
            st.warning(str(exc))


def _panel_gaps(conn) -> None:
    gaps = rcsa.control_gaps(conn)
    st.caption("These are workflow indicators for review — not automatic conclusions "
               "of regulatory noncompliance.")
    if gaps.empty:
        st.markdown(notice("No gap indicators on the current register."),
                    unsafe_allow_html=True)
        return
    st.markdown(risk_views._status_line([
        ("indicators", str(len(gaps))),
        ("high", str(int((gaps["severity"] == "high").sum()))),
        ("medium", str(int((gaps["severity"] == "medium").sum()))),
    ]), unsafe_allow_html=True)
    st.dataframe(gaps[["severity", "gap_kind", "risk_id", "title", "detail", "disclaimer"]],
                 hide_index=True, width="stretch")


def _panel_create(conn, index) -> None:
    st.caption("Acceptance path: start from a regulatory obligation, create a risk, "
               "then assess inherent exposure and attach controls on the detail tabs.")
    name = controls_views._reviewer_box("rcsa_create_name")
    with state.session() as s:
        reviews = state.reviews(s)
    obl = audit.obligation_table(index, reviews, jurisdiction="IL")
    if obl.empty:
        st.markdown(notice("No obligations in the index."), unsafe_allow_html=True)
        return
    demo_ids = [o for o in obl["document_id"].unique()
                if str(o).startswith("IL-BOI-PC-")]
    doc = st.selectbox("Source document", demo_ids or obl["document_id"].unique().tolist(),
                       key="rcsa_create_doc")
    rows = obl[obl["document_id"] == doc]
    labels = {r["okey"]: f"{r['citation']} — {str(r['action'])[:90]}"
              for _, r in rows.iterrows()}
    okey = st.selectbox("Obligation", list(labels), format_func=labels.get,
                        key="rcsa_create_okey")
    picked = rows[rows["okey"] == okey].iloc[0]
    st.markdown(
        f'<div class="law rk-quote">{_e(picked["sentence"])}</div>',
        unsafe_allow_html=True)
    title = st.text_input("Risk title",
                          value=f"Risk linked to: {str(picked['action'])[:80]}",
                          key="rcsa_create_title")
    description = st.text_area("Risk event description", value=picked["action"],
                               key="rcsa_create_desc")
    event = st.selectbox("Event type (Basel)", risk.EVENT_TYPES, index=5,
                         key="rcsa_create_event")
    cat = st.selectbox("ORM category", [c.id for c in taxonomy.CATEGORIES if c.orm_core],
                       format_func=lambda i: taxonomy.BY_ID[i].name, key="rcsa_create_cat")
    cross = st.multiselect("Cross-cutting classifications", list(risk.CROSS_CUTTING),
                           default=["Payments operations"], key="rcsa_create_xc")
    c1, c2 = st.columns(2)
    with c1:
        like = st.selectbox("Inherent likelihood", list(range(1, 6)), index=2,
                            format_func=lambda n: f"{n} · {risk.LIKELIHOOD_LABELS[n]}",
                            key="rcsa_create_l")
    with c2:
        st.caption("Set dimensional impacts; inherent impact = max (demo rule).")
    dims = {}
    dcols = st.columns(5)
    for col, dim in zip(dcols, risk.IMPACT_DIMENSIONS):
        with col:
            dims[dim] = st.selectbox(dim.capitalize()[:6], list(range(1, 6)), index=2,
                                     key=f"rcsa_dim_{dim}")
    owner = st.text_input("Risk owner", value="Head of Operational Risk",
                          key="rcsa_create_owner")
    process = st.text_input("Business process", value="Card payment authorisation",
                            key="rcsa_create_proc")
    unit = st.text_input("Business unit", value="Payments", key="rcsa_create_unit")
    entity = st.text_input("Legal entity", value=demo_data.ENTITY, key="rcsa_create_ent")
    causes = st.text_area("Causes", value="To be refined by the risk owner.",
                          key="rcsa_create_cause")
    consequences = st.text_area("Potential consequences",
                                value="To be refined by the risk owner.",
                                key="rcsa_create_effect")
    if st.button("Create risk from obligation", key="rcsa_create_go", disabled=not name):
        try:
            row = rcsa.create_risk_from_obligation(
                conn, index, okey=okey, title=title, description=description,
                event_type=event, category_id=cat, causes=causes,
                consequences=consequences, inherent_likelihood=int(like),
                inherent_impact=max(dims.values()), owner=owner, actor=name,
                business_process=process, business_unit=unit, legal_entity=entity,
                jurisdiction=picked["jurisdiction"], cross_cutting=cross,
                impact_dimensions=dims,
                is_synthetic=1 if "fictional" in entity.lower() or "demo" in entity.lower() else 0)
            conn.commit()
            st.success(f"Created {row['id']}. Open it under Risk detail to attach "
                       "controls and approve residual risk.")
            st.session_state["rcsa_detail"] = row["id"]
        except (LookupError, ValueError) as exc:
            st.warning(str(exc))


def _panel_scales() -> None:
    st.markdown(pane_head("Configurable taxonomy"), unsafe_allow_html=True)
    st.markdown("**Event types (exclusive primary category)**")
    st.markdown("\n".join(f"- {e['name']}" for e in rcsa.EVENT_TAXONOMY))
    st.markdown("**Cross-cutting classifications (non-exclusive)**")
    st.markdown("\n".join(f"- {e['name']}" for e in rcsa.CROSS_CUTTING_TAXONOMY))
    st.markdown(_scale_card(), unsafe_allow_html=True)
    st.caption(risk.METHOD_NOTE)
