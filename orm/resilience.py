"""Operational resilience and scenario analysis.

Deterministic scenario calculations for important business services,
dependency concentration flags (hypotheses), BIA, impact-tolerance testing
and arrangement comparison. Not a full quantitative risk model and not
Monte Carlo. Synthetic demo content is labelled. Impact tolerances are
never invented when missing.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid

import pandas as pd

from . import risk

SEED_VERSION = "res-1"
ACTOR = "Synthetic resilience demo seed"
ENTITY = "Demo Digital Bank Ltd (fictional)"
NOTICE = (
    "Synthetic operational-resilience demonstration. Not Revolut data. "
    "Scenario figures are illustrative assumptions, not statistically "
    "calibrated forecasts. Concentration flags are hypotheses for review."
)
METHOD_NOTE = (
    "Illustrative scenario-analysis method for this prototype only — not any "
    "bank's approved operational-resilience framework."
)

LAYERS = ("process", "application", "infrastructure", "third_party", "recovery")
LAYER_LABEL = {
    "process": "Business process",
    "application": "Application",
    "infrastructure": "Infrastructure",
    "third_party": "Third party",
    "recovery": "Recovery capability",
}

FORMULAS = {
    "outage_hours": "duration_minutes ÷ 60",
    "attempted_transactions": "avg_tx_per_hour × outage_hours",
    "failed_transactions": "attempted_transactions × (failure_rate_pct ÷ 100)",
    "tolerance_margin_hours": "impact_tolerance_hours − disruption_hours",
}

TEMPLATE_SCENARIOS = (
    ("A", "Cloud region failure", "cloud",
     "Severe-but-plausible loss of a primary cloud region."),
    ("B", "Critical payment provider outage", "provider",
     "Outage at a critical payment / scheme connectivity provider."),
    ("C", "Cyberattack affecting availability", "cyber",
     "Availability impact from a cyber event on payment platforms."),
    ("D", "Corrupted transaction data", "data",
     "Integrity incident corrupting transaction records."),
    ("E", "Concurrent primary and backup recovery failure", "recovery",
     "Primary and backup recovery paths both fail in the same window."),
)


# --- pure calculations ------------------------------------------------------------

def outage_hours(duration_minutes: float | None) -> float | None:
    if duration_minutes is None or (isinstance(duration_minutes, float)
                                    and pd.isna(duration_minutes)):
        return None
    return round(float(duration_minutes) / 60.0, 4)


def attempted_transactions(avg_tx_per_hour: float | None,
                           duration_minutes: float | None) -> float | None:
    hours = outage_hours(duration_minutes)
    if hours is None or avg_tx_per_hour is None:
        return None
    return round(float(avg_tx_per_hour) * hours, 2)


def failed_transactions(avg_tx_per_hour: float | None,
                        duration_minutes: float | None,
                        failure_rate_pct: float | None) -> float | None:
    attempted = attempted_transactions(avg_tx_per_hour, duration_minutes)
    if attempted is None or failure_rate_pct is None:
        return None
    return round(attempted * (float(failure_rate_pct) / 100.0), 2)


def tolerance_result(disruption_hours: float | None,
                     impact_tolerance_hours: float | None) -> dict:
    """Pass / fail / indeterminate. Never invent a tolerance."""
    if impact_tolerance_hours is None or (
            isinstance(impact_tolerance_hours, float)
            and pd.isna(impact_tolerance_hours)):
        return {
            "status": "indeterminate",
            "label": "Impact tolerance not defined.",
            "margin_hours": None,
            "tolerance_hours": None,
            "disruption_hours": disruption_hours,
            "decision_required": True,
            "missing_evidence": ["Approved impact tolerance for this service"],
        }
    if disruption_hours is None:
        return {
            "status": "indeterminate",
            "label": "Disruption duration not available.",
            "margin_hours": None,
            "tolerance_hours": float(impact_tolerance_hours),
            "disruption_hours": None,
            "decision_required": True,
            "missing_evidence": ["Scenario disruption duration"],
        }
    margin = round(float(impact_tolerance_hours) - float(disruption_hours), 4)
    if margin >= 0:
        return {
            "status": "pass",
            "label": "Within illustrative impact tolerance",
            "margin_hours": margin,
            "tolerance_hours": float(impact_tolerance_hours),
            "disruption_hours": float(disruption_hours),
            "decision_required": False,
            "missing_evidence": [],
        }
    return {
        "status": "fail",
        "label": "Exceeds illustrative impact tolerance",
        "margin_hours": margin,
        "tolerance_hours": float(impact_tolerance_hours),
        "disruption_hours": float(disruption_hours),
        "decision_required": True,
        "missing_evidence": [],
    }


def run_scenario_calc(*, duration_minutes: float | None,
                      avg_tx_per_hour: float | None,
                      failure_rate_pct: float | None,
                      estimated_customers: float | None,
                      impact_tolerance_hours: float | None,
                      rto_hours: float | None = None) -> dict:
    hours = outage_hours(duration_minutes)
    attempted = attempted_transactions(avg_tx_per_hour, duration_minutes)
    failed = failed_transactions(avg_tx_per_hour, duration_minutes, failure_rate_pct)
    tol = tolerance_result(hours, impact_tolerance_hours)
    rto_met = None
    if hours is not None and rto_hours is not None and not (
            isinstance(rto_hours, float) and pd.isna(rto_hours)):
        rto_met = hours <= float(rto_hours)
    return {
        "inputs": {
            "duration_minutes": duration_minutes,
            "avg_tx_per_hour": avg_tx_per_hour,
            "failure_rate_pct": failure_rate_pct,
            "estimated_customers": estimated_customers,
            "impact_tolerance_hours": impact_tolerance_hours,
            "rto_hours": rto_hours,
            "input_kind": "assumption",  # illustrative — not observed
        },
        "formulas": FORMULAS,
        "outage_hours": hours,
        "attempted_transactions": attempted,
        "failed_transactions": failed,
        "estimated_customers": estimated_customers,
        "rto_achieved": rto_met,
        "tolerance": tol,
        "disclaimer": (
            "Illustrative deterministic calculation from stated assumptions. "
            "Not a statistically calibrated forecast."),
    }


# --- inventory / BIA / dependencies -----------------------------------------------

def _json_list(value) -> list:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return value
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return [text]


def services(conn) -> pd.DataFrame:
    df = risk._df(conn, """
        SELECT * FROM business_service
        WHERE status != 'retired' ORDER BY criticality, id""")
    if df.empty:
        return df
    df = df.copy()
    df["is_ibs"] = df.get("is_important_business_service", 0).fillna(0).astype(int)
    return df


def service_detail(conn, service_id: str) -> dict:
    row = conn.execute("SELECT * FROM business_service WHERE id=?",
                       (service_id,)).fetchone()
    if not row:
        raise LookupError(service_id)
    svc = dict(row)
    bia = conn.execute("SELECT * FROM service_bia WHERE service_id=?",
                       (service_id,)).fetchone()
    deps = risk._df(conn, """
        SELECT * FROM service_dependency WHERE service_id=?
        ORDER BY CASE layer
            WHEN 'process' THEN 1 WHEN 'application' THEN 2
            WHEN 'infrastructure' THEN 3 WHEN 'third_party' THEN 4
            WHEN 'recovery' THEN 5 ELSE 9 END, name""", (service_id,))
    risks = risk._df(conn, """
        SELECT id, title, residual_status FROM risk
        WHERE service_id=? AND status != 'retired' ORDER BY id""", (service_id,))
    return {
        "service": svc,
        "bia": dict(bia) if bia else None,
        "dependencies": deps,
        "risks": risks,
        "notice": NOTICE if svc.get("is_synthetic") else "",
    }


def upsert_bia(conn, service_id: str, fields: dict, *, actor: str) -> dict:
    payload = {
        "service_id": service_id,
        "financial_impact": fields.get("financial_impact") or "",
        "customer_impact": fields.get("customer_impact") or "",
        "operational_impact": fields.get("operational_impact") or "",
        "reputational_impact": fields.get("reputational_impact") or "",
        "legal_regulatory": fields.get("legal_regulatory") or "",
        "criticality": fields.get("criticality") or "",
        "max_tolerable_disruption_hours": fields.get("max_tolerable_disruption_hours"),
        "rto_hours": fields.get("rto_hours"),
        "rpo_hours": fields.get("rpo_hours"),
        "impact_tolerance_hours": fields.get("impact_tolerance_hours"),
        "impact_tolerance_basis": fields.get("impact_tolerance_basis") or "",
        "evidence": fields.get("evidence") or "",
        "assumptions_note": fields.get("assumptions_note") or "",
        "updated_at": risk.now(),
        "updated_by": actor or "",
        "is_synthetic": int(fields.get("is_synthetic") or 0),
    }
    existing = conn.execute(
        "SELECT service_id FROM service_bia WHERE service_id=?",
        (service_id,)).fetchone()
    if existing:
        sets = ", ".join(f"{k}=?" for k in payload if k != "service_id")
        conn.execute(
            f"UPDATE service_bia SET {sets} WHERE service_id=?",
            [payload[k] for k in payload if k != "service_id"] + [service_id])
        risk._log(conn, actor, "update", "service_bia", service_id, None, payload)
        return payload
    cols = ", ".join(payload)
    conn.execute(
        f"INSERT INTO service_bia({cols}) VALUES ({', '.join('?' * len(payload))})",
        list(payload.values()))
    risk._log(conn, actor, "create", "service_bia", service_id, None, payload)
    return payload


def concentration_flags(conn) -> pd.DataFrame:
    """Hypothesis flags for review — not confirmed findings."""
    deps = risk._df(conn, "SELECT * FROM service_dependency")
    svcs = services(conn)
    flags = []
    if deps.empty:
        return pd.DataFrame(flags)

    # Shared provider: 2+ services, at least one critical or IBS
    crit_or_ibs = set()
    if not svcs.empty:
        for _, s in svcs.iterrows():
            if s.get("criticality") == "critical" or int(s.get("is_ibs") or 0) == 1:
                crit_or_ibs.add(s["id"])
    shared = deps[deps["shared_key"].notna() & (deps["shared_key"] != "")]
    if not shared.empty:
        for key, grp in shared.groupby("shared_key"):
            svc_set = sorted(set(grp["service_id"]))
            if len(svc_set) >= 2 and (set(svc_set) & crit_or_ibs):
                flags.append({
                    "kind": "shared_provider_concentration",
                    "certainty": "hypothesis",
                    "shared_key": key,
                    "services": ", ".join(svc_set),
                    "detail": (
                        f"Hypothesis: {len(svc_set)} services share dependency "
                        f"key '{key}' (includes critical/IBS). Requires validation."),
                    "requires_validation": True,
                })

    for _, d in deps.iterrows():
        if d.get("has_alternative") == 0:
            flags.append({
                "kind": "no_documented_alternative",
                "certainty": "hypothesis",
                "shared_key": d.get("shared_key") or "",
                "services": d["service_id"],
                "detail": (
                    f"Hypothesis: {d['name']} ({d['layer']}) on {d['service_id']} "
                    "has no documented alternative."),
                "requires_validation": True,
            })
        if d.get("layer") == "recovery" and not d.get("last_tested_at"):
            flags.append({
                "kind": "recovery_untested",
                "certainty": "hypothesis",
                "shared_key": "",
                "services": d["service_id"],
                "detail": (
                    f"Hypothesis: recovery capability '{d['name']}' on "
                    f"{d['service_id']} has no documented test date."),
                "requires_validation": True,
            })
        if int(d.get("is_spof") or 0) == 1:
            flags.append({
                "kind": "unresolved_spof",
                "certainty": "hypothesis",
                "shared_key": d.get("shared_key") or "",
                "services": d["service_id"],
                "detail": (
                    f"Hypothesis: single point of failure flagged for "
                    f"'{d['name']}' on {d['service_id']} — confirm if still open."),
                "requires_validation": True,
            })
    return pd.DataFrame(flags)


def dependency_graph_mermaid(conn, service_id: str | None = None) -> str:
    """Text graph for UI rendering (Mermaid flowchart)."""
    q = "SELECT * FROM service_dependency"
    params: tuple = ()
    if service_id:
        q += " WHERE service_id=?"
        params = (service_id,)
    deps = risk._df(conn, q + " ORDER BY service_id, name", params)
    lines = ["flowchart TD"]
    if deps.empty:
        lines.append("  empty[No dependencies mapped]")
        return "\n".join(lines)
    svc_nodes = set()
    for _, d in deps.iterrows():
        sid = d["service_id"]
        if sid not in svc_nodes:
            lines.append(f'  {sid}["Service: {sid}"]')
            svc_nodes.add(sid)
        nid = d["id"].replace("-", "_")
        label = f"{LAYER_LABEL.get(d['layer'], d['layer'])}: {d['name']}"
        lines.append(f'  {nid}["{label}"]')
        parent = d.get("parent_id")
        if parent and str(parent).strip():
            pid = str(parent).replace("-", "_")
            lines.append(f"  {pid} --> {nid}")
        else:
            lines.append(f"  {sid} --> {nid}")
    return "\n".join(lines)


# --- scenarios --------------------------------------------------------------------

def scenarios(conn) -> pd.DataFrame:
    return risk._df(conn, """
        SELECT * FROM resilience_scenario ORDER BY code, id""")


def scenario_options(conn, scenario_id: str) -> pd.DataFrame:
    return risk._df(conn, """
        SELECT * FROM scenario_option WHERE scenario_id=?
        ORDER BY sort_order, option_code""", (scenario_id,))


def scenario_detail(conn, scenario_id: str) -> dict:
    row = conn.execute("SELECT * FROM resilience_scenario WHERE id=?",
                       (scenario_id,)).fetchone()
    if not row:
        raise LookupError(scenario_id)
    scn = dict(row)
    opts = scenario_options(conn, scenario_id)
    services_json = _json_list(scn.get("affected_services_json"))
    primary = services_json[0] if services_json else None
    bia = None
    if primary:
        brow = conn.execute("SELECT * FROM service_bia WHERE service_id=?",
                            (primary,)).fetchone()
        bia = dict(brow) if brow else None
    tol_hours = (bia or {}).get("impact_tolerance_hours")
    rto = (bia or {}).get("rto_hours")
    base = run_scenario_calc(
        duration_minutes=scn.get("duration_minutes"),
        avg_tx_per_hour=scn.get("avg_tx_per_hour"),
        failure_rate_pct=scn.get("failure_rate_pct"),
        estimated_customers=scn.get("estimated_customers"),
        impact_tolerance_hours=tol_hours,
        rto_hours=rto,
    )
    comparisons = []
    for _, o in opts.iterrows():
        calc = run_scenario_calc(
            duration_minutes=o.get("assumed_duration_minutes"),
            avg_tx_per_hour=scn.get("avg_tx_per_hour"),
            failure_rate_pct=o.get("assumed_failure_rate_pct"),
            estimated_customers=o.get("assumed_customers")
            if o.get("assumed_customers") is not None
            else scn.get("estimated_customers"),
            impact_tolerance_hours=tol_hours,
            rto_hours=rto,
        )
        comparisons.append({
            "option": dict(o),
            "calc": calc,
            "assumption_deltas": _option_deltas(scn, o),
        })
    acts = risk._df(conn, """
        SELECT * FROM resilience_action
        WHERE scenario_id=? OR service_id=?
        ORDER BY due_at, id""", (scenario_id, primary or ""))
    return {
        "scenario": scn,
        "bia": bia,
        "primary_service_id": primary,
        "base_calc": base,
        "comparisons": comparisons,
        "actions": acts,
        "notice": NOTICE if scn.get("is_synthetic") else "",
        "method_note": METHOD_NOTE,
    }


def _option_deltas(scn: dict, opt) -> list[str]:
    deltas = []
    if opt.get("assumed_duration_minutes") != scn.get("duration_minutes"):
        deltas.append(
            f"Duration assumption: {scn.get('duration_minutes')} → "
            f"{opt.get('assumed_duration_minutes')} minutes")
    if opt.get("assumed_failure_rate_pct") != scn.get("failure_rate_pct"):
        deltas.append(
            f"Failure rate assumption: {scn.get('failure_rate_pct')}% → "
            f"{opt.get('assumed_failure_rate_pct')}%")
    if int(opt.get("control_tested") or 0) == 1:
        deltas.append("Recovery control assumed successfully tested")
    else:
        deltas.append("Recovery control not assumed successfully tested")
    if opt.get("unresolved_deficiency"):
        deltas.append(f"Unresolved deficiency: {opt['unresolved_deficiency']}")
    return deltas


def management_summary(conn, scenario_id: str) -> dict:
    d = scenario_detail(conn, scenario_id)
    scn = d["scenario"]
    comps = d["comparisons"]
    # Prefer option that fails due to deficiency and one that passes
    fail = next((c for c in comps
                 if c["calc"]["tolerance"]["status"] == "fail"), None)
    passed = next((c for c in comps
                   if c["calc"]["tolerance"]["status"] == "pass"), None)
    vulns = []
    for c in comps:
        if c["option"].get("unresolved_deficiency"):
            vulns.append(c["option"]["unresolved_deficiency"])
        if int(c["option"].get("control_tested") or 0) == 0:
            vulns.append(f"Untested / not successfully tested: {c['option']['label']}")
    return {
        "title": scn.get("name"),
        "scenario_id": scenario_id,
        "service_ids": _json_list(scn.get("affected_services_json")),
        "linked_risk_id": scn.get("linked_risk_id"),
        "linked_controls": _json_list(scn.get("linked_control_ids_json")),
        "duration_minutes": scn.get("duration_minutes"),
        "base": d["base_calc"],
        "pass_option": passed,
        "fail_option": fail,
        "vulnerabilities": list(dict.fromkeys(vulns)),
        "actions": d["actions"],
        "tolerance_basis": (d["bia"] or {}).get("impact_tolerance_basis"),
        "disclaimer": NOTICE + " " + METHOD_NOTE,
        "headline": _headline(passed, fail),
    }


def _headline(passed, fail) -> str:
    if passed and fail:
        return (
            f"Illustrative arrangements that are successfully tested "
            f"({passed['option']['label']}) stay within the illustrative "
            f"impact tolerance; arrangements with an unresolved recovery "
            f"defect ({fail['option']['label']}) do not. Resilience depends "
            f"on tested capability, not design alone.")
    if fail:
        return "At least one arrangement exceeds the illustrative impact tolerance."
    if passed:
        return "Compared arrangements stay within the illustrative impact tolerance."
    return "Impact tolerance comparison incomplete — see missing evidence."


def create_custom_scenario(conn, *, name: str, description: str = "",
                           duration_minutes: float, avg_tx_per_hour: float,
                           failure_rate_pct: float, service_ids: list[str],
                           linked_risk_id: str = "", actor: str = "",
                           **extra) -> dict:
    sid = f"SCN-CUSTOM-{uuid.uuid4().hex[:8]}"
    return risk.insert(conn, "resilience_scenario", {
        "id": sid,
        "code": f"CUSTOM-{sid[-4:].upper()}",
        "name": name,
        "description": description,
        "scenario_type": "custom",
        "duration_minutes": duration_minutes,
        "avg_tx_per_hour": avg_tx_per_hour,
        "failure_rate_pct": failure_rate_pct,
        "affected_services_json": json.dumps(service_ids),
        "linked_risk_id": linked_risk_id,
        "is_template": 0,
        "is_synthetic": int(extra.get("is_synthetic") or 0),
        "confidence": extra.get("confidence") or "low — user-defined",
        "starting_conditions": extra.get("starting_conditions") or "",
        "recovery_strategy": extra.get("recovery_strategy") or "",
        "estimated_customers": extra.get("estimated_customers"),
        "provenance": "user",
    }, actor=actor or "system")


# --- export / dashboard -----------------------------------------------------------

def dashboard(conn) -> dict:
    svcs = services(conn)
    ibs = svcs[svcs["is_ibs"] == 1] if not svcs.empty else svcs
    flags = concentration_flags(conn)
    scns = scenarios(conn)
    return {
        "notice": NOTICE,
        "services": svcs,
        "ibs_count": 0 if ibs.empty else len(ibs),
        "service_count": 0 if svcs.empty else len(svcs),
        "scenario_count": 0 if scns.empty else len(scns),
        "flag_count": 0 if flags.empty else len(flags),
        "flags": flags,
        "scenarios": scns,
    }


def export_scenario_csv(detail: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["field", "value", "kind"])
    scn = detail["scenario"]
    for k in ("id", "code", "name", "duration_minutes", "avg_tx_per_hour",
              "failure_rate_pct", "estimated_customers", "linked_risk_id",
              "confidence"):
        w.writerow([k, scn.get(k), "scenario"])
    base = detail["base_calc"]
    for k in ("outage_hours", "attempted_transactions", "failed_transactions"):
        w.writerow([k, base.get(k), "calculated"])
    tol = base["tolerance"]
    w.writerow(["tolerance_status", tol["status"], "calculated"])
    w.writerow(["tolerance_label", tol["label"], "calculated"])
    w.writerow(["tolerance_margin_hours", tol["margin_hours"], "calculated"])
    for c in detail["comparisons"]:
        o = c["option"]
        calc = c["calc"]
        prefix = o["option_code"]
        w.writerow([f"{prefix}_label", o["label"], "option"])
        w.writerow([f"{prefix}_duration_min", o["assumed_duration_minutes"],
                    "assumption"])
        w.writerow([f"{prefix}_failed_tx", calc["failed_transactions"], "calculated"])
        w.writerow([f"{prefix}_tolerance", calc["tolerance"]["status"], "calculated"])
        w.writerow([f"{prefix}_control_tested", o["control_tested"], "assumption"])
        w.writerow([f"{prefix}_deficiency", o.get("unresolved_deficiency") or "",
                    "assumption"])
    w.writerow(["disclaimer", base["disclaimer"], "note"])
    return buf.getvalue().encode("utf-8")


def export_summary_text(summary: dict) -> str:
    lines = [
        f"# Scenario summary: {summary.get('title')}",
        "",
        summary.get("headline") or "",
        "",
        f"Linked risk: {summary.get('linked_risk_id') or '—'}",
        f"Services: {', '.join(summary.get('service_ids') or []) or '—'}",
        f"Baseline duration (min): {summary.get('duration_minutes')}",
        "",
        "## Disclaimer",
        summary.get("disclaimer") or NOTICE,
        "",
    ]
    if summary.get("pass_option"):
        p = summary["pass_option"]
        lines += [
            f"## Arrangement that meets illustrative tolerance",
            f"- {p['option']['label']}",
            f"- Duration (min): {p['option']['assumed_duration_minutes']}",
            f"- Failed tx (illustrative): {p['calc']['failed_transactions']}",
            f"- Control tested: {bool(p['option']['control_tested'])}",
            "",
        ]
    if summary.get("fail_option"):
        f = summary["fail_option"]
        lines += [
            f"## Arrangement that exceeds illustrative tolerance",
            f"- {f['option']['label']}",
            f"- Duration (min): {f['option']['assumed_duration_minutes']}",
            f"- Failed tx (illustrative): {f['calc']['failed_transactions']}",
            f"- Deficiency: {f['option'].get('unresolved_deficiency') or '—'}",
            "",
        ]
    if summary.get("vulnerabilities"):
        lines.append("## Main vulnerabilities")
        for v in summary["vulnerabilities"]:
            lines.append(f"- {v}")
        lines.append("")
    acts = summary.get("actions")
    if acts is not None and not getattr(acts, "empty", True):
        lines.append("## Recommended actions")
        for _, a in acts.iterrows():
            lines.append(f"- {a['id']}: {a['title']} (owner: {a.get('owner') or '—'})")
    return "\n".join(lines)


# --- synthetic demo seed ----------------------------------------------------------

def seed(conn, index_conn=None, *, today: dt.date | None = None,
         force: bool = False) -> dict:
    if not force and risk.get_meta(conn, "resilience_seed_version") == SEED_VERSION:
        return {"seeded": False}
    from . import demo_data
    demo_data.seed(conn, index_conn, today=today)
    today = today or dt.date.today()
    day = today.isoformat()

    # Wipe prior resilience demo artefacts only
    for sid in ("SCN-DEMO-CLOUD",):
        conn.execute("DELETE FROM scenario_option WHERE scenario_id=?", (sid,))
        conn.execute("DELETE FROM resilience_action WHERE scenario_id=?", (sid,))
        conn.execute("DELETE FROM resilience_scenario WHERE id=?", (sid,))
    for sid in ("SVC-001", "SVC-002", "SVC-003"):
        conn.execute("DELETE FROM service_dependency WHERE service_id=? AND "
                     "is_synthetic=1", (sid,))
        conn.execute("DELETE FROM service_bia WHERE service_id=?", (sid,))
    for code, *_ in TEMPLATE_SCENARIOS:
        conn.execute("DELETE FROM resilience_scenario WHERE id=?",
                     (f"SCN-TPL-{code}",))

    # Enrich services — do not auto-designate every critical process as IBS
    if conn.execute("SELECT id FROM business_service WHERE id='SVC-001'").fetchone():
        risk.update(conn, "business_service", "SVC-001", {
            "legal_entity": ENTITY,
            "jurisdiction": "IL",
            "customer_impact": "Confirmed (synthetic): cardholders cannot pay "
                               "at merchants during an outage.",
            "is_important_business_service": 1,
            "ibs_designation_rationale": (
                "Designated IBS (synthetic) because prolonged disruption would "
                "materially affect customers and market integrity for card "
                "payments. Designation is explicit — not inferred from "
                "criticality alone."),
            "critical_processes_json": json.dumps([
                "Card authorisation", "Settlement handoff",
            ]),
            "technology_deps_json": json.dumps([
                "Payment authorisation platform", "API gateway",
            ]),
            "third_party_deps_json": json.dumps([
                "NimbusCloud (fictional)", "Card scheme connectivity",
            ]),
            "people_deps_json": json.dumps([
                "Payments on-call", "SRE failover operators",
            ]),
            "data_deps_json": json.dumps([
                "Authorisation ledger", "Merchant routing config",
            ]),
            "alternate_arrangements": (
                "Secondary region failover (documented). Manual DNS step still "
                "a known residual from last test."),
            "recovery_objectives": "Illustrative RTO 2h; RPO 15m; IBS impact "
                                   "tolerance documented in BIA (separate).",
            "last_resilience_assessment": day,
        }, actor=ACTOR)

    if conn.execute("SELECT id FROM business_service WHERE id='SVC-002'").fetchone():
        risk.update(conn, "business_service", "SVC-002", {
            "legal_entity": ENTITY,
            "jurisdiction": "IL",
            "customer_impact": "Login / onboarding delays.",
            "is_important_business_service": 0,
            "ibs_designation_rationale": (
                "Not designated as an IBS in this synthetic inventory. "
                "Criticality='important' does not automatically equal IBS."),
            "critical_processes_json": json.dumps(["Customer login"]),
            "third_party_deps_json": json.dumps([
                "NimbusCloud (fictional)", "VerifyNow (fictional)",
            ]),
            "last_resilience_assessment": day,
        }, actor=ACTOR)

    # Standard (non-IBS) service to show designation is selective
    if not conn.execute("SELECT id FROM business_service WHERE id='SVC-003'").fetchone():
        risk.insert(conn, "business_service", {
            "id": "SVC-003",
            "name": "Marketing preferences portal",
            "description": "Customer marketing preference centre (non-critical).",
            "owner": "Head of Digital Marketing",
            "criticality": "standard",
            "legal_entity": ENTITY,
            "jurisdiction": "IL",
            "is_important_business_service": 0,
            "ibs_designation_rationale": (
                "Not an IBS. Included to show designation is selective."),
            "impact_tolerance_hours": None,
            "rto_hours": 48,
            "rpo_hours": 24,
            "is_synthetic": 1,
            "provenance": "synthetic",
            "status": "active",
        }, actor=ACTOR)

    # BIA — RTO / RPO / impact tolerance kept conceptually separate
    upsert_bia(conn, "SVC-001", {
        "financial_impact": "Estimate: forgone interchange / goodwill (synthetic).",
        "customer_impact": "Confirmed assumption set: card payments unavailable.",
        "operational_impact": "Authorisation path halted until failover completes.",
        "reputational_impact": "Hypothesis: media / app-store reviews if prolonged.",
        "legal_regulatory": (
            "Hypothesis: technology-incident reporting may apply — assess with "
            "Compliance; not decided here."),
        "criticality": "critical",
        "max_tolerable_disruption_hours": 2.0,
        "rto_hours": 2.0,
        "rpo_hours": 0.25,
        "impact_tolerance_hours": 1.5,  # 90 minutes — illustrative IBS tolerance
        "impact_tolerance_basis": (
            "Illustrative IBS impact tolerance of 90 minutes for this synthetic "
            "demo only. Not a board-approved Revolut or bank figure. "
            "Kept separate from RTO (2h) and RPO (15m)."),
        "evidence": "Synthetic BIA worksheet BIA-DEMO-001; last failover test notes.",
        "assumptions_note": (
            "Max tolerable disruption, RTO and impact tolerance are related but "
            "distinct concepts — do not treat them as interchangeable."),
        "is_synthetic": 1,
    }, actor=ACTOR)

    # SVC-003 deliberately has no impact tolerance defined
    upsert_bia(conn, "SVC-003", {
        "financial_impact": "Low (synthetic).",
        "customer_impact": "Preference updates delayed.",
        "operational_impact": "Non-critical backlog.",
        "reputational_impact": "Minimal.",
        "legal_regulatory": "None identified in demo.",
        "criticality": "standard",
        "max_tolerable_disruption_hours": 72,
        "rto_hours": 48,
        "rpo_hours": 24,
        "impact_tolerance_hours": None,  # explicitly undefined
        "impact_tolerance_basis": "Impact tolerance not defined for this service.",
        "evidence": "",
        "assumptions_note": "No approved IBS impact tolerance — show indeterminate.",
        "is_synthetic": 1,
    }, actor=ACTOR)

    def dep(**kw):
        risk.insert(conn, "service_dependency", {
            "id": kw["id"],
            "service_id": kw["service_id"],
            "layer": kw["layer"],
            "name": kw["name"],
            "parent_id": kw.get("parent_id"),
            "shared_key": kw.get("shared_key"),
            "has_alternative": kw.get("has_alternative"),
            "last_tested_at": kw.get("last_tested_at"),
            "test_result": kw.get("test_result"),
            "is_spof": int(kw.get("is_spof") or 0),
            "note": kw.get("note") or "",
            "is_synthetic": 1,
        }, actor=ACTOR)

    # SVC-001 chain: process → app → infra → third party → recovery
    dep(id="DEP-001-PROC", service_id="SVC-001", layer="process",
        name="Card authorisation process")
    dep(id="DEP-001-APP", service_id="SVC-001", layer="application",
        name="Payment authorisation platform", parent_id="DEP-001-PROC")
    dep(id="DEP-001-INF", service_id="SVC-001", layer="infrastructure",
        name="Primary cloud region (compute/network)", parent_id="DEP-001-APP",
        shared_key="nimbuscloud-region-a", has_alternative=1, is_spof=0)
    dep(id="DEP-001-TPP", service_id="SVC-001", layer="third_party",
        name="NimbusCloud (fictional cloud provider)", parent_id="DEP-001-INF",
        shared_key="nimbuscloud", has_alternative=0, is_spof=1,
        note="Hypothesis: concentrated third-party dependency.")
    dep(id="DEP-001-REC", service_id="SVC-001", layer="recovery",
        name="Multi-region failover runbook", parent_id="DEP-001-TPP",
        has_alternative=1,
        last_tested_at=(today - dt.timedelta(days=45)).isoformat(),
        test_result="Partial: completed in 100 min; unresolved manual DNS step.",
        is_spof=1,
        note="Unresolved finding from scheduled failover test (synthetic).")

    # SVC-002 shares NimbusCloud → concentration hypothesis
    dep(id="DEP-002-TPP", service_id="SVC-002", layer="third_party",
        name="NimbusCloud (fictional cloud provider)",
        shared_key="nimbuscloud", has_alternative=0)
    dep(id="DEP-002-REC", service_id="SVC-002", layer="recovery",
        name="Login region failover", has_alternative=1,
        last_tested_at=None, test_result=None)

    # Template catalogue A–E
    for code, name, stype, desc in TEMPLATE_SCENARIOS:
        risk.insert(conn, "resilience_scenario", {
            "id": f"SCN-TPL-{code}",
            "code": code,
            "name": name,
            "description": desc + " (template — configure parameters before use).",
            "scenario_type": stype,
            "starting_conditions": "Template defaults — replace with assessed assumptions.",
            "duration_minutes": None,
            "avg_tx_per_hour": None,
            "failure_rate_pct": None,
            "is_template": 1,
            "is_synthetic": 1,
            "confidence": "n/a — template",
            "evidence_sources": "Not populated until parameterised.",
            "provenance": "synthetic",
        }, actor=ACTOR)

    # Interview demo: cloud region disruption 100 minutes / DEMO-RISK-001
    scn_id = "SCN-DEMO-CLOUD"
    risk.insert(conn, "resilience_scenario", {
        "id": scn_id,
        "code": "A",
        "name": "Cloud region failure — Payment Processing",
        "description": (
            "Synthetic severe-but-plausible scenario: critical cloud provider "
            "regional disruption affecting Payment Processing (SVC-001) for "
            "100 minutes. Linked to DEMO-RISK-001. Aligns with INC-DEMO-CLOUD "
            "timeline for interview continuity."),
        "scenario_type": "cloud",
        "starting_conditions": (
            "Primary region active; secondary region available but last failover "
            "test left an unresolved DNS/runbook finding."),
        "disruption_start": f"{day}T09:00:00+00:00",
        "duration_minutes": 100,
        "affected_services_json": json.dumps(["SVC-001"]),
        "affected_deps_json": json.dumps([
            "DEP-001-INF", "DEP-001-TPP", "DEP-001-REC",
        ]),
        "avg_tx_per_hour": 12000,          # assumption
        "failure_rate_pct": 95,            # assumption during outage
        "estimated_customers": 42000,      # assumption / estimate
        "recovery_strategy": "Failover to secondary region per runbook.",
        "recovery_assumptions": (
            "Assumes operators available; DNS change required; scheme links intact."),
        "control_effectiveness_assumptions": (
            "CTL-DEMO-03 partially effective when unresolved test finding remains."),
        "recovery_completion_minutes": 100,
        "confidence": "medium — illustrative assumptions, not calibrated",
        "evidence_sources": (
            "Synthetic: BIA-DEMO-001; failover test CTT-DEMO-03; "
            "INC-DEMO-CLOUD timeline; DEMO-RISK-001."),
        "linked_risk_id": "DEMO-RISK-001",
        "linked_control_ids_json": json.dumps(["CTL-DEMO-03", "CTL-DEMO-02"]),
        "is_template": 0,
        "is_synthetic": 1,
        "provenance": "synthetic",
    }, actor=ACTOR)

    # Comparison options — resilience = tested capability
    options = (
        ("OPT1", "Option 1 — Single-region architecture",
         "No secondary region. Rebuild / wait for provider recovery.",
         360, 98, 0,
         "No multi-region failover capability", 1),
        ("OPT2", "Option 2 — Multi-region failover, successfully tested",
         "Active secondary region; failover drill passed within target.",
         45, 40, 1, "", 2),
        ("OPT3", "Option 3 — Multi-region failover with unresolved control deficiency",
         "Secondary region exists, but unresolved DNS/runbook finding delays recovery "
         "to 100 minutes (matches synthetic incident).",
         100, 95, 0,
         "Unresolved manual DNS step from last failover test (CTL-DEMO-03)", 3),
    )
    for code, label, desc, dur, rate, tested, deficiency, order in options:
        risk.insert(conn, "scenario_option", {
            "id": f"SCN-DEMO-CLOUD-{code}",
            "scenario_id": scn_id,
            "option_code": code,
            "label": label,
            "arrangement_description": desc,
            "assumed_duration_minutes": dur,
            "assumed_failure_rate_pct": rate,
            "assumed_customers": 42000 if dur >= 90 else 8000,
            "control_tested": tested,
            "unresolved_deficiency": deficiency,
            "assumptions_json": json.dumps({
                "duration_minutes": dur,
                "failure_rate_pct": rate,
                "control_tested": bool(tested),
            }),
            "sort_order": order,
            "is_synthetic": 1,
        }, actor=ACTOR)

    risk.insert(conn, "resilience_action", {
        "id": "RACT-DEMO-01",
        "scenario_id": scn_id,
        "service_id": "SVC-001",
        "title": "Close unresolved failover DNS/runbook finding and re-test within 45 min",
        "owner": "Head of Business Continuity",
        "due_at": (today + dt.timedelta(days=14)).isoformat(),
        "status": "open",
        "related_risk_id": "DEMO-RISK-001",
        "related_control_id": "CTL-DEMO-03",
        "rationale": (
            "Option 3 shows illustrative impact tolerance exceeded when the "
            "known recovery defect remains. Option 2 shows tested capability "
            "staying within tolerance."),
        "is_synthetic": 1,
        "provenance": "synthetic",
    }, actor=ACTOR)

    risk.set_meta(conn, "resilience_seed_version", SEED_VERSION)
    risk.set_meta(conn, "resilience_seeded_at", risk.now())
    detail = scenario_detail(conn, scn_id)
    return {
        "seeded": True,
        "scenario_id": scn_id,
        "base_failed_tx": detail["base_calc"]["failed_transactions"],
        "opt2_status": detail["comparisons"][1]["calc"]["tolerance"]["status"],
        "opt3_status": detail["comparisons"][2]["calc"]["tolerance"]["status"],
    }
