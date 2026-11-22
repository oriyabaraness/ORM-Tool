"""Executive operational risk reporting.

Pulls from the risk register, controls, KRIs, incidents, remediation actions,
resilience scenarios and obligation links into a period-filtered management
pack. Narratives are structured FACTS / ANALYSIS / RECOMMENDATIONS built only
from recorded data — never invent compliance conclusions or false movement
reasons. Synthetic demo content is watermarked.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
from typing import Any

import pandas as pd

from . import risk

try:
    from . import incident_mgmt as im
except Exception:  # pragma: no cover
    im = None
try:
    from . import kri_appetite as ka
except Exception:  # pragma: no cover
    ka = None
try:
    from . import resilience as rs
except Exception:  # pragma: no cover
    rs = None

SEED_VERSION = "exec-1"
ACTOR = "Synthetic executive-report demo seed"
ENTITY = "Demo Digital Bank Ltd (fictional)"
DEMO_TITLE = "Operational Risk Overview — Hypothetical Digital Payments Entity"

SYNTHETIC_WATERMARK = (
    "SYNTHETIC DEMONSTRATION DATA. This is not an actual Revolut risk report "
    "and not any real bank's management information."
)
NOTICE = (
    "Regulatory text is quoted from the indexed sources. Links between risks "
    "and obligations remain suggestions until a named person validates them. "
    "This pack is not a compliance conclusion and does not assert that the "
    "organization is fully compliant."
)
METHOD_NOTE = (
    "Illustrative executive-reporting layout for this prototype. Metrics are "
    "derived from application records in orm_risk.db for the selected period."
)

PERIODS = ("weekly", "monthly", "quarterly", "custom")


# --- periods ----------------------------------------------------------------------

def period_bounds(kind: str, *, as_of: dt.date | None = None,
                  custom_start: dt.date | None = None,
                  custom_end: dt.date | None = None) -> dict:
    """Configurable reporting window. End date is inclusive."""
    as_of = as_of or dt.date.today()
    kind = (kind or "monthly").lower()
    if kind not in PERIODS:
        raise ValueError(f"Unknown period kind: {kind}")
    if kind == "custom":
        if not custom_start or not custom_end:
            raise ValueError("Custom period requires start and end dates.")
        if custom_end < custom_start:
            raise ValueError("Custom period end must be on or after start.")
        start, end = custom_start, custom_end
    elif kind == "weekly":
        end = as_of
        start = as_of - dt.timedelta(days=6)
    elif kind == "monthly":
        end = as_of
        start = as_of.replace(day=1)
    else:  # quarterly
        end = as_of
        q_month = ((as_of.month - 1) // 3) * 3 + 1
        start = as_of.replace(month=q_month, day=1)
    return {
        "kind": kind,
        "start": start,
        "end": end,
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "label": f"{start.isoformat()} → {end.isoformat()} ({kind})",
    }


def _in_period(ts: Any, start: dt.date, end: dt.date) -> bool:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return False
    text = str(ts).strip()
    if not text:
        return False
    try:
        if "T" in text:
            d = dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        else:
            d = dt.date.fromisoformat(text[:10])
    except ValueError:
        return False
    return start <= d <= end


# --- build ------------------------------------------------------------------------

def build(conn, index_conn=None, *, period: str = "monthly",
          as_of: dt.date | None = None,
          custom_start: dt.date | None = None,
          custom_end: dt.date | None = None,
          title: str | None = None) -> dict:
    """Assemble the executive pack from live application records."""
    as_of = as_of or dt.date.today()
    bounds = period_bounds(period, as_of=as_of,
                           custom_start=custom_start, custom_end=custom_end)
    start, end = bounds["start"], bounds["end"]
    iso = as_of.isoformat()

    reg = risk.register(conn, iso)
    ctl = risk.control_status(conn)
    acts = risk.actions(conn, iso)
    links = risk.check_obligation_links(conn, index_conn)
    incidents = risk.incidents(conn)
    if im is not None:
        try:
            incidents = im.register(conn)
        except Exception:
            pass

    # KRIs — prefer kri_appetite library when available
    kris = risk.kri_status(conn)
    kri_breaches = pd.DataFrame()
    if ka is not None:
        try:
            lib = ka.library(conn)
            kri_breaches = lib[lib["rag"].isin(["Red", "Amber"])] if not lib.empty else lib
        except Exception:
            kri_breaches = kris[kris["rag"].isin(["Red", "Amber"])] if not kris.empty else kris
    else:
        kri_breaches = kris[kris["rag"].isin(["Red", "Amber"])] if not kris.empty else kris

    # Period-filtered incidents
    if not incidents.empty:
        ts_col = "occurred_at" if "occurred_at" in incidents.columns else None
        if ts_col:
            period_inc = incidents[incidents[ts_col].map(
                lambda v: _in_period(v, start, end))]
        else:
            period_inc = incidents
    else:
        period_inc = incidents

    material_inc = period_inc
    if not period_inc.empty and "severity" in period_inc.columns:
        material_inc = period_inc[period_inc["severity"].isin(["P1", "P2"])]

    weak = ctl[ctl["rating"] != "effective"] if not ctl.empty else ctl
    # Critical / key weak controls
    if not weak.empty and "key_control" in weak.columns:
        critical_weak = weak[weak["key_control"].fillna(1).astype(int) == 1]
    else:
        critical_weak = weak

    overdue = acts[acts["overdue"]] if not acts.empty else acts
    outside = reg[reg["appetite"] == "Outside appetite"] if not reg.empty else reg

    # Severity / band distribution
    by_band = {}
    if not reg.empty:
        by_band = reg.groupby("residual_band").size().to_dict()

    # Residual score change vs suggested (documented overrides only)
    residual_changes = _residual_overrides(reg)

    # Audit-log movements in period (no invented reasons)
    movements = risk_movements(conn, start, end, reg)

    # Concentration hypotheses from resilience
    concentration = pd.DataFrame()
    resilience_demo = None
    if rs is not None:
        try:
            concentration = rs.concentration_flags(conn)
            if conn.execute(
                "SELECT 1 FROM resilience_scenario WHERE id='SCN-DEMO-CLOUD'"
            ).fetchone():
                resilience_demo = rs.management_summary(conn, "SCN-DEMO-CLOUD")
        except Exception:
            concentration = pd.DataFrame()

    # Emerging: risks created or assessed in period, or DEMO-RISK-001 story
    emerging = _emerging_risks(conn, reg, start, end)

    committee = committee_actions(conn, overdue, critical_weak, material_inc,
                                 outside, resilience_demo)

    metrics = {
        "open_risks": 0 if reg.empty else len(reg),
        "by_residual_band": by_band,
        "outside_appetite": 0 if outside.empty else len(outside),
        "kri_red": int((kri_breaches["rag"] == "Red").sum())
        if not kri_breaches.empty and "rag" in kri_breaches.columns else 0,
        "kri_amber": int((kri_breaches["rag"] == "Amber").sum())
        if not kri_breaches.empty and "rag" in kri_breaches.columns else 0,
        "critical_weak_controls": 0 if critical_weak.empty else len(critical_weak),
        "material_incidents": 0 if material_inc.empty else len(material_inc),
        "overdue_actions": 0 if overdue.empty else len(overdue),
        "concentration_flags": 0 if concentration.empty else len(concentration),
        "emerging_risks": 0 if emerging.empty else len(emerging),
        "residual_overrides": 0 if residual_changes.empty else len(residual_changes),
        "movements_in_period": len(movements),
    }

    provenance = _provenance_index(
        outside, kri_breaches, critical_weak, material_inc, overdue,
        concentration, emerging)

    narrative = draft_narrative(
        metrics=metrics, outside=outside, kri_breaches=kri_breaches,
        critical_weak=critical_weak, material_inc=material_inc,
        overdue=overdue, concentration=concentration, emerging=emerging,
        movements=movements, resilience_demo=resilience_demo,
        bounds=bounds, synthetic=risk.is_synthetic(conn))

    return {
        "title": title or (
            DEMO_TITLE if risk.is_synthetic(conn)
            else f"Operational Risk Overview — {risk.get_meta(conn, 'bank') or 'Entity'}"),
        "period": bounds,
        "generated_at": risk.now(),
        "document_status": "draft",
        "review_status": "draft — pending Head of Operational Risk review",
        "synthetic": risk.is_synthetic(conn),
        "bank": risk.get_meta(conn, "bank") or ENTITY,
        "metrics": metrics,
        "register": reg,
        "outside_appetite": outside,
        "kri_breaches": kri_breaches,
        "critical_controls": critical_weak,
        "incidents": material_inc,
        "overdue_actions": overdue,
        "concentration": concentration,
        "emerging": emerging,
        "residual_overrides": residual_changes,
        "movements": movements,
        "committee_actions": committee,
        "narrative": narrative,
        "resilience": resilience_demo,
        "provenance": provenance,
        "links_to_validate": links[
            (links["validation_status"] != "validated")
            | (links["source_state"] != "current")] if not links.empty else links,
        "watermark": SYNTHETIC_WATERMARK if risk.is_synthetic(conn) else "",
        "notice": NOTICE,
        "method_note": METHOD_NOTE,
    }


def _residual_overrides(reg: pd.DataFrame) -> pd.DataFrame:
    """Documented residual overrides only — no invented movement stories."""
    if reg.empty:
        return pd.DataFrame()
    rows = []
    for _, r in reg.iterrows():
        if not r.get("residual_overridden"):
            continue
        rows.append({
            "risk_id": r["id"],
            "title": r["title"],
            "prior_or_suggested": (
                f"{r.get('suggested_residual_score')} "
                f"(suggested from controls)"),
            "current": f"{r['residual_score']} {r['residual_band']}",
            "reason": r.get("override_rationale") or r.get("residual_rationale")
            or "Reason not recorded — evidence missing.",
            "owner": r.get("owner") or "",
            "approval_status": r.get("residual_status") or "",
            "evidence": r.get("residual_evidence") or "Evidence missing.",
        })
    return pd.DataFrame(rows)


def risk_movements(conn, start: dt.date, end: dt.date,
                   reg: pd.DataFrame) -> list[dict]:
    """Material movements from the audit log. Never invent explanations."""
    hist = risk.history(conn, table="risk", limit=500)
    by_id: dict[str, list] = {}
    for h in hist:
        if not _in_period(h.get("ts"), start, end):
            continue
        if h.get("action") != "update":
            continue
        by_id.setdefault(h["object_id"], []).append(h)

    reg_idx = reg.set_index("id") if not reg.empty else None
    out = []
    for rid, events in by_id.items():
        for h in events:
            before = json.loads(h["before_json"]) if h.get("before_json") else {}
            after = json.loads(h["after_json"]) if h.get("after_json") else {}
            watched = (
                "override_likelihood", "override_impact", "override_rationale",
                "residual_likelihood", "residual_impact", "residual_status",
                "inherent_likelihood", "inherent_impact",
            )
            changed = [k for k in watched
                       if before.get(k) != after.get(k)
                       and (k in before or k in after)]
            if not changed:
                continue
            reason = (after.get("override_rationale")
                      or after.get("residual_rationale")
                      or before.get("override_rationale"))
            if not reason:
                reason = ("No documented reason in the audit trail for this "
                          "change — evidence missing.")
            cur = reg_idx.loc[rid] if reg_idx is not None and rid in reg_idx.index else None
            # Related incidents / controls from current links only
            related_inc = []
            control_changes = []
            if cur is not None:
                try:
                    links = [dict(r) for r in conn.execute(
                        "SELECT incident_id FROM incident_link WHERE "
                        "kind='risk' AND target_id=?", (rid,))]
                    related_inc = [x["incident_id"] for x in links]
                except Exception:
                    related_inc = []
            out.append({
                "risk_id": rid,
                "title": (cur["title"] if cur is not None else rid),
                "prior": {k: before.get(k) for k in changed},
                "current": {k: after.get(k) for k in changed},
                "reason_for_change": reason,
                "new_evidence": after.get("residual_evidence")
                or after.get("override_rationale")
                or "Evidence missing.",
                "control_changes": control_changes or "Not recorded on this update.",
                "related_incidents": related_inc or [],
                "owner": (cur["owner"] if cur is not None else after.get("owner") or ""),
                "approval_status": after.get("residual_status")
                or (cur["residual_status"] if cur is not None else ""),
                "actor": h.get("actor") or "",
                "at": h.get("ts") or "",
                "fields_changed": changed,
            })
    return out


def _emerging_risks(conn, reg: pd.DataFrame, start: dt.date,
                    end: dt.date) -> pd.DataFrame:
    if reg.empty:
        return pd.DataFrame()
    rows = []
    for _, r in reg.iterrows():
        created = r.get("created_at") or r.get("assessed_at")
        in_window = _in_period(created, start, end)
        is_demo_story = r["id"] == "DEMO-RISK-001"
        if in_window or is_demo_story:
            rows.append({
                "risk_id": r["id"],
                "title": r["title"],
                "residual": f"{r['residual_score']} {r['residual_band']}",
                "appetite": r["appetite"],
                "owner": r.get("owner") or "",
                "basis": (
                    "Created/assessed in reporting period"
                    if in_window else
                    "Centrepiece demo risk (synthetic) — payment disruption"),
                "evidence": r.get("residual_evidence") or "See risk record.",
            })
    return pd.DataFrame(rows)


def committee_actions(conn, overdue, critical_weak, material_inc, outside,
                      resilience_demo) -> pd.DataFrame:
    """Risk committee action table — sourced from real records."""
    rows = []

    def add(**kw):
        rows.append(kw)

    if overdue is not None and not overdue.empty:
        for _, a in overdue.head(8).iterrows():
            add(issue=a.get("title") or a["id"],
                risk_impact=f"Source: {a.get('source_kind')} {a.get('source_id')}",
                recommended_action=a.get("title") or "",
                owner=a.get("owner") or "Unassigned",
                due_date=a.get("due_at") or "Missing",
                required_decision="Complete or re-baseline due date",
                status=a.get("status") or "open",
                source_ref=a["id"])

    if critical_weak is not None and not critical_weak.empty:
        for _, c in critical_weak.head(5).iterrows():
            add(issue=f"Control weakness: {c.get('name') or c['id']}",
                risk_impact="Key control not rated effective",
                recommended_action="Retest / remediate control design or operation",
                owner=c.get("owner") or "Control owner",
                due_date="Not set on control record",
                required_decision="Accept residual or mandate remediation",
                status="open",
                source_ref=c["id"])

    if outside is not None and not outside.empty:
        for _, r in outside.head(5).iterrows():
            add(issue=f"Outside appetite: {r['id']}",
                risk_impact=f"Residual {r['residual_score']} {r['residual_band']}",
                recommended_action="Escalate appetite exception to Risk Committee",
                owner=r.get("owner") or "",
                due_date=r.get("next_review_at") or "Missing",
                required_decision="Accept, mitigate, or transfer",
                status=r.get("residual_status") or "open",
                source_ref=r["id"])

    if material_inc is not None and not material_inc.empty:
        for _, i in material_inc.head(3).iterrows():
            add(issue=f"Incident: {i.get('title') or i['id']}",
                risk_impact=f"Severity {i.get('severity')}",
                recommended_action="Confirm PIR actions and residual risk reassessment",
                owner=i.get("owner") or "",
                due_date="See incident record",
                required_decision="Close PIR / keep open",
                status=i.get("workflow_status") or i.get("status") or "",
                source_ref=i["id"])

    if resilience_demo:
        racts = resilience_demo.get("actions")
        if isinstance(racts, pd.DataFrame) and not racts.empty:
            for _, a in racts.iterrows():
                add(issue=a.get("title") or a["id"],
                    risk_impact=f"Resilience / {a.get('related_risk_id') or ''}",
                    recommended_action=a.get("title") or "",
                    owner=a.get("owner") or "",
                    due_date=a.get("due_at") or "Missing",
                    required_decision="Approve resilience remediation",
                    status=a.get("status") or "open",
                    source_ref=a["id"])
        if resilience_demo.get("fail_option"):
            add(issue="Unresolved failover deficiency (scenario OPT3)",
                risk_impact="Illustrative impact tolerance exceeded under "
                            "cloud-region scenario",
                recommended_action="Close DNS/runbook finding and re-test failover",
                owner="Head of Business Continuity",
                due_date="See RACT-DEMO-01",
                required_decision="Fund / prioritize re-test",
                status="open",
                source_ref="SCN-DEMO-CLOUD")

    return pd.DataFrame(rows)


def _provenance_index(*frames_and_lists) -> list[dict]:
    """Traceability list for metrics and statements."""
    items = []
    labels = (
        ("risk_outside_appetite", "risk"),
        ("kri_breach", "kri"),
        ("control_weakness", "control"),
        ("material_incident", "incident"),
        ("overdue_action", "action"),
        ("concentration_flag", "hypothesis"),
        ("emerging_risk", "risk"),
    )
    for (kind, record_type), frame in zip(labels, frames_and_lists):
        if frame is None:
            continue
        if isinstance(frame, pd.DataFrame):
            if frame.empty:
                continue
            id_col = next((c for c in ("id", "risk_id", "incident_id", "source_ref")
                           if c in frame.columns), None)
            for _, r in frame.iterrows():
                items.append({
                    "statement_kind": kind,
                    "record_type": record_type,
                    "record_id": r[id_col] if id_col else "",
                    "evidence": "Application record" if id_col else "Missing id",
                })
        elif isinstance(frame, list):
            for r in frame:
                items.append({
                    "statement_kind": kind,
                    "record_type": record_type,
                    "record_id": r.get("risk_id") or r.get("id") or "",
                    "evidence": r.get("reason_for_change") or "Audit log",
                })
    return items


# --- narrative --------------------------------------------------------------------

def draft_narrative(*, metrics, outside, kri_breaches, critical_weak,
                    material_inc, overdue, concentration, emerging, movements,
                    resilience_demo, bounds, synthetic) -> dict:
    """Template narrative from data. FACTS / ANALYSIS / RECOMMENDATIONS."""

    def ids(frame, col="id", n=5):
        if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty):
            return "none recorded"
        if col not in frame.columns:
            col = next((c for c in ("risk_id", "id") if c in frame.columns), None)
            if not col:
                return "ids missing"
        vals = [str(x) for x in frame[col].head(n).tolist()]
        return ", ".join(vals)

    facts = [
        f"Reporting period {bounds['label']}.",
        f"{metrics['open_risks']} open risks in the register; "
        f"{metrics['outside_appetite']} outside documented appetite "
        f"({ids(outside)}).",
        f"KRI status: {metrics['kri_red']} Red, {metrics['kri_amber']} Amber "
        f"({ids(kri_breaches)}).",
        f"{metrics['critical_weak_controls']} key controls not rated effective "
        f"({ids(critical_weak)}).",
        f"{metrics['material_incidents']} material incidents (P1/P2) in period "
        f"({ids(material_inc)}).",
        f"{metrics['overdue_actions']} overdue remediation actions "
        f"({ids(overdue)}).",
        f"{metrics['concentration_flags']} third-party / resilience hypotheses "
        f"flagged for validation.",
        f"{metrics['movements_in_period']} risk-field updates in the audit log "
        f"for the period.",
    ]
    if synthetic:
        facts.append(
            "All figures above are from synthetic demonstration records "
            f"for {ENTITY} — not Revolut data.")
    if resilience_demo:
        facts.append(
            f"Resilience scenario {resilience_demo.get('scenario_id')}: "
            f"baseline duration {resilience_demo.get('duration_minutes')} min; "
            f"linked risk {resilience_demo.get('linked_risk_id')}.")

    analysis = [
        "Interpretation: residual-band concentration and appetite exceptions "
        "indicate where management attention is warranted — not a calibrated "
        "capital forecast.",
    ]
    if metrics["kri_red"]:
        analysis.append(
            "Potential driver: Red KRIs may reflect deteriorating process "
            "performance; confirm with observation-level evidence before "
            "concluding root cause.")
    if metrics["material_incidents"]:
        analysis.append(
            "Incident activity in the period may elevate residual assessments "
            "for linked risks — only where the risk record has been updated.")
    if metrics["concentration_flags"]:
        analysis.append(
            "Emerging-risk hypothesis: shared third-party dependencies could "
            "amplify a single-provider disruption across services — requires "
            "validation, not confirmed.")
    if resilience_demo and resilience_demo.get("fail_option"):
        analysis.append(
            "Resilience hypothesis: arrangements with an unresolved failover "
            "defect exceed the illustrative impact tolerance in the cloud "
            "scenario; tested multi-region recovery does not. This is "
            "scenario analysis, not a statistical forecast.")
    if not movements:
        analysis.append(
            "No material residual-rating movements with documented reasons "
            "were found in the audit log for this period.")

    recommendations = [
        "Review appetite exceptions with Risk Committee and record accept/"
        "mitigate decisions.",
        "Clear overdue remediation actions or formally re-baseline due dates.",
    ]
    if metrics["kri_red"]:
        recommendations.append(
            "Investigate Red KRI observations and link outcomes to risk/"
            "control owners.")
    if metrics["critical_weak_controls"]:
        recommendations.append(
            "Schedule retests for key controls not rated effective; attach "
            "evidence before closing.")
    if resilience_demo:
        recommendations.append(
            "Prioritize closure of the unresolved failover finding and timed "
            "re-test (see resilience action RACT-DEMO-01).")
    recommendations.append(
        "Do not treat this draft as confirmation of regulatory compliance.")

    sections = {
        "A_executive_summary": {
            "facts": facts[:4],
            "analysis": analysis[:1],
            "recommendations": recommendations[:1],
        },
        "B_material_developments": {
            "facts": [
                f"Material incidents: {ids(material_inc)}.",
                f"Risk movements logged: {metrics['movements_in_period']}.",
                f"Emerging / demo risks surfaced: {ids(emerging, 'risk_id')}.",
            ],
            "analysis": analysis[1:3] or [
                "No further material-development analysis beyond recorded facts."],
            "recommendations": [
                "Confirm PIR outcomes for each material incident before the "
                "next committee."],
        },
        "C_risk_appetite_exceptions": {
            "facts": [
                f"{metrics['outside_appetite']} risks outside appetite: "
                f"{ids(outside)}."],
            "analysis": [
                "Outside-appetite status is computed from residual score vs "
                "category limit — not a judgment of legal breach."],
            "recommendations": [
                "Require a named decision (accept / mitigate / transfer) for "
                "each exception."],
        },
        "D_control_environment": {
            "facts": [
                f"Key controls not effective: {ids(critical_weak)}.",
                f"Overdue actions: {ids(overdue)}."],
            "analysis": [
                "Control ratings come from the latest recorded test; absence "
                "of a test is shown as not effective / not tested — evidence "
                "may be missing."],
            "recommendations": [
                "Attach test evidence before marking controls effective."],
        },
        "E_operational_incidents": {
            "facts": [
                f"P1/P2 in period: {ids(material_inc)}."],
            "analysis": [
                "Customer and financial impact figures on incidents are labeled "
                "confirmed / estimate / hypothesis on the incident record."],
            "recommendations": [
                "Ensure each material incident has an RCA with unconfirmed "
                "items explicitly listed."],
        },
        "F_resilience_concerns": {
            "facts": [
                f"Concentration hypotheses: {metrics['concentration_flags']}.",
                (f"Scenario linked risk: {resilience_demo.get('linked_risk_id')}"
                 if resilience_demo else
                 "No parameterised resilience scenario summary available."),
            ],
            "analysis": [
                a for a in analysis if "Resilience" in a or "third-party" in a
                or "Emerging-risk hypothesis" in a] or [
                "No additional resilience analysis beyond flagged hypotheses."],
            "recommendations": [
                "Validate concentration hypotheses before treating them as "
                "confirmed findings."],
        },
        "G_outstanding_decisions": {
            "facts": [
                f"Committee action rows prepared: see action table "
                f"({metrics['overdue_actions']} overdue + exceptions)."],
            "analysis": [
                "Outstanding decisions are listed only where a source record "
                "exists."],
            "recommendations": [
                "Close or escalate each committee action with owner and date."],
        },
        "H_next_period_priorities": {
            "facts": [
                "Priorities below are suggested from open exceptions and "
                "overdue work — not approved OKRs."],
            "analysis": [
                "Priority order should be confirmed by the Head of Operational "
                "Risk against local capacity."],
            "recommendations": recommendations,
        },
    }
    return {
        "sections": sections,
        "disclaimer": NOTICE + " " + (SYNTHETIC_WATERMARK if synthetic else ""),
    }


# --- exports ----------------------------------------------------------------------

def _safe_cell(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def export_html(rep: dict) -> str:
    """Printable one-page-oriented HTML executive report."""
    m = rep["metrics"]
    wm = (f'<div class="wm">{html.escape(rep["watermark"])}</div>'
          if rep.get("watermark") else "")
    bands = m.get("by_residual_band") or {}
    band_html = "".join(
        f"<li>{html.escape(str(k))}: {v}</li>" for k, v in sorted(bands.items()))
    narr = rep["narrative"]["sections"]

    def block(key, title):
        s = narr[key]
        parts = [f"<h3>{html.escape(title)}</h3>"]
        for label, items in (("FACTS", s["facts"]),
                             ("ANALYSIS", s["analysis"]),
                             ("RECOMMENDATIONS", s["recommendations"])):
            parts.append(f"<p><b>{label}</b></p><ul>")
            for it in items:
                parts.append(f"<li>{html.escape(it)}</li>")
            parts.append("</ul>")
        return "\n".join(parts)

    actions = rep["committee_actions"]
    act_rows = ""
    if actions is not None and not actions.empty:
        for _, a in actions.iterrows():
            act_rows += (
                "<tr>"
                + "".join(f"<td>{html.escape(str(a.get(c) or ''))}</td>"
                          for c in ("issue", "risk_impact", "recommended_action",
                                    "owner", "due_date", "required_decision",
                                    "status", "source_ref"))
                + "</tr>")

    move_html = ""
    for mv in rep.get("movements") or []:
        move_html += (
            f"<li><b>{html.escape(mv['risk_id'])}</b> "
            f"{html.escape(mv.get('title') or '')}: "
            f"prior {html.escape(str(mv['prior']))} → "
            f"current {html.escape(str(mv['current']))}. "
            f"Reason: {html.escape(mv['reason_for_change'])}. "
            f"Owner: {html.escape(str(mv.get('owner') or ''))}. "
            f"Approval: {html.escape(str(mv.get('approval_status') or ''))}."
            f"</li>")
    if not move_html:
        move_html = "<li>No documented residual movements in this period.</li>"

    prov = "".join(
        f"<li>{html.escape(p['statement_kind'])}: "
        f"{html.escape(p['record_type'])} "
        f"<code>{html.escape(str(p['record_id']))}</code> — "
        f"{html.escape(p['evidence'])}</li>"
        for p in (rep.get("provenance") or [])[:40])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>{html.escape(rep['title'])}</title>
<style>
body {{ font-family: Georgia, "Times New Roman", serif; color: #0a2540;
  max-width: 900px; margin: 24px auto; padding: 0 16px; line-height: 1.45; }}
h1 {{ font-size: 22px; margin-bottom: 4px; }}
h2 {{ font-size: 15px; margin-top: 22px; border-bottom: 1px solid #e3e8ee;
  padding-bottom: 4px; }}
h3 {{ font-size: 13px; margin-top: 14px; }}
.meta {{ font-size: 12px; color: #425466; }}
.wm {{ background: #fdeceb; border: 1px solid #b3261e; color: #b3261e;
  padding: 8px 10px; font-size: 12px; font-weight: 600; margin: 12px 0; }}
.notice {{ font-size: 11px; color: #6b7c93; margin: 8px 0 16px; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
.card {{ border: 1px solid #e3e8ee; border-radius: 6px; padding: 8px 10px; }}
.card .n {{ font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.card .l {{ font-size: 11px; color: #6b7c93; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
th, td {{ border: 1px solid #e3e8ee; padding: 4px 6px; text-align: left;
  vertical-align: top; }}
th {{ background: #f6f9fc; }}
ul {{ margin: 4px 0 8px 18px; padding: 0; font-size: 12.5px; }}
code {{ font-size: 11px; }}
@media print {{
  body {{ margin: 0; max-width: none; }}
  .wm {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style></head><body>
{wm}
<h1>{html.escape(rep['title'])}</h1>
<p class="meta">
Period: {html.escape(rep['period']['label'])}<br/>
Generated: {html.escape(rep['generated_at'])}<br/>
Document status: {html.escape(rep['document_status'])} ·
Review: {html.escape(rep['review_status'])}<br/>
Entity: {html.escape(rep['bank'])} · Provenance: application records
{"(synthetic demo)" if rep["synthetic"] else ""}
</p>
<p class="notice">{html.escape(rep['notice'])}</p>

<h2>1. Reporting dashboard</h2>
<div class="cards">
  <div class="card"><div class="n">{m['open_risks']}</div>
    <div class="l">Open risks</div></div>
  <div class="card"><div class="n">{m['outside_appetite']}</div>
    <div class="l">Outside appetite</div></div>
  <div class="card"><div class="n">{m['kri_red']}</div>
    <div class="l">KRI Red</div></div>
  <div class="card"><div class="n">{m['overdue_actions']}</div>
    <div class="l">Overdue actions</div></div>
  <div class="card"><div class="n">{m['critical_weak_controls']}</div>
    <div class="l">Critical control weaknesses</div></div>
  <div class="card"><div class="n">{m['material_incidents']}</div>
    <div class="l">Material incidents (P1/P2)</div></div>
  <div class="card"><div class="n">{m['concentration_flags']}</div>
    <div class="l">Third-party concentration flags</div></div>
  <div class="card"><div class="n">{m['emerging_risks']}</div>
    <div class="l">Emerging / highlighted risks</div></div>
</div>
<p><b>Residual distribution</b></p>
<ul>{band_html or "<li>No risks</li>"}</ul>

<h2>2. Risk movement</h2>
<ul>{move_html}</ul>

<h2>3. Management narrative</h2>
{block("A_executive_summary", "A. Executive summary")}
{block("B_material_developments", "B. Material developments")}
{block("C_risk_appetite_exceptions", "C. Risk appetite exceptions")}
{block("D_control_environment", "D. Control environment observations")}
{block("E_operational_incidents", "E. Operational incidents")}
{block("F_resilience_concerns", "F. Resilience concerns")}
{block("G_outstanding_decisions", "G. Outstanding management decisions")}
{block("H_next_period_priorities", "H. Next-period priorities")}

<h2>4. Risk committee actions</h2>
<table>
<thead><tr>
<th>Issue</th><th>Risk impact</th><th>Recommended action</th><th>Owner</th>
<th>Due</th><th>Required decision</th><th>Status</th><th>Source</th>
</tr></thead>
<tbody>{act_rows or "<tr><td colspan='8'>None</td></tr>"}</tbody>
</table>

<h2>5. Explainability (evidence links)</h2>
<ul>{prov or "<li>No provenance rows.</li>"}</ul>

<p class="notice">{html.escape(rep['method_note'])}</p>
</body></html>
"""


def export_pdf(rep: dict) -> bytes:
    from .simple_pdf import Document
    doc = Document()
    doc.heading(rep["title"][:80], size=14)
    doc.text(f"Period: {rep['period']['label']}", size=8)
    doc.text(f"Generated: {rep['generated_at']}  ·  Status: {rep['document_status']}  ·  "
             f"{rep['review_status']}", size=8)
    doc.text(f"Entity: {rep['bank']}", size=8)
    if rep.get("watermark"):
        doc.text(rep["watermark"], size=8, bold=True)
    doc.text(rep["notice"], size=7)
    doc.space(4)
    m = rep["metrics"]
    doc.heading("Dashboard", size=11)
    doc.text(
        f"Open risks {m['open_risks']} · Outside appetite {m['outside_appetite']} · "
        f"KRI Red {m['kri_red']} / Amber {m['kri_amber']} · "
        f"Weak key controls {m['critical_weak_controls']} · "
        f"Material incidents {m['material_incidents']} · "
        f"Overdue actions {m['overdue_actions']} · "
        f"Concentration flags {m['concentration_flags']} · "
        f"Emerging {m['emerging_risks']}", size=8)
    bands = m.get("by_residual_band") or {}
    if bands:
        doc.text("Residual bands: " + ", ".join(f"{k}={v}" for k, v in bands.items()),
                 size=8)
    doc.space(4)
    doc.heading("Risk movement", size=11)
    if not rep.get("movements"):
        doc.text("No documented residual movements in this period.", size=8)
    for mv in rep.get("movements") or []:
        doc.text(f"{mv['risk_id']} {mv.get('title') or ''}", size=8, bold=True)
        doc.text(f"Prior {mv['prior']} -> Current {mv['current']}", size=7)
        doc.text(f"Reason: {mv['reason_for_change']}", size=7)
        doc.text(f"Evidence: {mv.get('new_evidence')} · Owner: {mv.get('owner')} · "
                 f"Approval: {mv.get('approval_status')}", size=7)
        doc.space(2)
    doc.space(4)
    doc.heading("Management narrative", size=11)
    labels = {
        "A_executive_summary": "A. Executive summary",
        "B_material_developments": "B. Material developments",
        "C_risk_appetite_exceptions": "C. Risk appetite exceptions",
        "D_control_environment": "D. Control environment",
        "E_operational_incidents": "E. Operational incidents",
        "F_resilience_concerns": "F. Resilience concerns",
        "G_outstanding_decisions": "G. Outstanding decisions",
        "H_next_period_priorities": "H. Next-period priorities",
    }
    for key, title in labels.items():
        sec = rep["narrative"]["sections"][key]
        doc.text(title, size=9, bold=True)
        for label, items in (("FACTS", sec["facts"]),
                             ("ANALYSIS", sec["analysis"]),
                             ("RECOMMENDATIONS", sec["recommendations"])):
            doc.text(label, size=8, bold=True)
            for it in items:
                doc.text(f"- {it}", size=7)
        doc.space(2)
    doc.space(4)
    doc.heading("Risk committee actions", size=11)
    acts = rep["committee_actions"]
    if acts is None or acts.empty:
        doc.text("None.", size=8)
    else:
        for _, a in acts.iterrows():
            doc.text(f"{a.get('source_ref')}: {a.get('issue')}", size=8, bold=True)
            doc.text(
                f"Impact: {a.get('risk_impact')} · Action: {a.get('recommended_action')} · "
                f"Owner: {a.get('owner')} · Due: {a.get('due_date')} · "
                f"Decision: {a.get('required_decision')} · Status: {a.get('status')}",
                size=7)
            doc.space(2)
    doc.space(4)
    doc.heading("Explainability", size=11)
    for p in (rep.get("provenance") or [])[:30]:
        doc.text(f"{p['statement_kind']}: {p['record_type']} {p['record_id']} — "
                 f"{p['evidence']}", size=7)
    doc.space(4)
    doc.text(rep["method_note"], size=7)
    return doc.render()


def export_excel(rep: dict) -> bytes:
    lines = [rep["title"], f"Period: {rep['period']['label']}",
             f"Generated: {rep['generated_at']}",
             f"Status: {rep['document_status']} / {rep['review_status']}", ""]
    if rep.get("watermark"):
        lines += [rep["watermark"], ""]
    lines += [rep["notice"], "", rep["method_note"]]
    m = rep["metrics"]
    metrics_df = pd.DataFrame([
        {"Metric": k, "Value": str(v)} for k, v in m.items()
        if k != "by_residual_band"
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame({"": lines}).to_excel(xw, sheet_name="Read me", index=False,
                                           header=False)
        metrics_df.map(_safe_cell).to_excel(xw, sheet_name="Dashboard", index=False)
        for name, frame in (
            ("Outside appetite", rep["outside_appetite"]),
            ("KRI breaches", rep["kri_breaches"]),
            ("Weak controls", rep["critical_controls"]),
            ("Incidents", rep["incidents"]),
            ("Overdue actions", rep["overdue_actions"]),
            ("Committee actions", rep["committee_actions"]),
            ("Emerging", rep["emerging"]),
        ):
            f = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
            if not f.empty:
                f.map(_safe_cell).to_excel(xw, sheet_name=name[:31], index=False)
            else:
                pd.DataFrame({"note": ["None"]}).to_excel(
                    xw, sheet_name=name[:31], index=False)
        pd.DataFrame(rep.get("movements") or []).to_excel(
            xw, sheet_name="Movements", index=False)
        pd.DataFrame(rep.get("provenance") or []).to_excel(
            xw, sheet_name="Provenance", index=False)
    return buf.getvalue()


def seed(conn, index_conn=None, *, today: dt.date | None = None,
         force: bool = False) -> dict:
    """Ensure upstream demo modules are present for the executive pack."""
    if not force and risk.get_meta(conn, "exec_report_seed_version") == SEED_VERSION:
        return {"seeded": False}
    from . import demo_data
    demo_data.seed(conn, index_conn, today=today)
    if ka is not None:
        ka.seed(conn, today=today)
    if im is not None:
        im.seed(conn, index_conn, today=today)
    if rs is not None:
        rs.seed(conn, index_conn, today=today)
    risk.set_meta(conn, "exec_report_seed_version", SEED_VERSION)
    risk.set_meta(conn, "exec_report_seeded_at", risk.now())
    return {"seeded": True, "title": DEMO_TITLE}
