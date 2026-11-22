"""Incident and operational loss management: lifecycle, RCA, loss events,
regulatory reporting assessment and a synthetic cloud-outage demo.

Integrates with the risk register, controls, KRIs and obligations in orm_risk.db.
All demo content is labelled synthetic. Regulatory reporting rows are
assessments for review — never automatic notification decisions.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid

import pandas as pd

from . import risk

SEED_VERSION = "inc-1"
ACTOR = "Synthetic incident demo seed"
ENTITY = "Demo Digital Bank Ltd (fictional)"
NOTICE = (
    "Synthetic demonstration incident. Not Revolut data. Confirmed facts, "
    "estimates and hypotheses are labelled separately."
)

WORKFLOW = (
    "detected",
    "triaged",
    "investigating",
    "contained",
    "recovering",
    "resolved",
    "post_incident_review",
    "closed",
)
WORKFLOW_LABEL = {
    "detected": "Detected",
    "triaged": "Triaged",
    "investigating": "Investigating",
    "contained": "Contained",
    "recovering": "Recovering",
    "resolved": "Resolved",
    "post_incident_review": "Post-Incident Review",
    "closed": "Closed",
}
# Forward path + reopen from closed → investigating
ALLOWED = {
    "detected": ("triaged",),
    "triaged": ("investigating",),
    "investigating": ("contained", "recovering"),
    "contained": ("recovering", "investigating"),
    "recovering": ("resolved", "investigating"),
    "resolved": ("post_incident_review", "investigating"),
    "post_incident_review": ("closed", "investigating"),
    "closed": ("investigating",),  # reopen
}

SEVERITIES = ("P1", "P2", "P3", "P4")
CERTAINTY = ("confirmed", "estimate", "hypothesis")
REPORTING_STATUSES = (
    "not_assessed", "under_review", "not_required", "submitted", "not_applicable",
)

SEVERITY_FRAMEWORK_NOTE = (
    "Illustrative severity framework for this prototype only — not any bank's "
    "approved scale and not Revolut's. Ratings weigh customer impact, failed "
    "transactions, duration, financial impact, critical-service availability, "
    "data integrity, regulatory consequences and recovery progress."
)


# --- timing -----------------------------------------------------------------------

def parse_ts(value: str | None) -> dt.datetime | None:
    if not value or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    # Allow trailing Z
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def minutes_between(start: str | None, end: str | None) -> float | None:
    a, b = parse_ts(start), parse_ts(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60.0, 2)


def timing_metrics(inc: dict) -> dict:
    """Consistent definitions used on screen and in tests."""
    return {
        "detection_delay_min": minutes_between(inc.get("occurred_at"),
                                               inc.get("detected_at")),
        "time_to_escalation_min": minutes_between(inc.get("detected_at"),
                                                  inc.get("escalated_at")),
        "disruption_duration_min": minutes_between(
            inc.get("occurred_at"),
            inc.get("restored_at") or inc.get("resolved_at")),
        "recovery_duration_min": minutes_between(
            inc.get("recovery_started_at"),
            inc.get("restored_at") or inc.get("resolved_at")),
    }


def net_loss(gross: float | None, recovered: float | None) -> float:
    return float(gross or 0) - float(recovered or 0)


# --- workflow ---------------------------------------------------------------------

def current_status(inc: dict) -> str:
    return (inc.get("workflow_status") or "").strip() or _legacy_status(inc.get("status"))


def _legacy_status(status: str | None) -> str:
    return {
        "open": "investigating",
        "contained": "contained",
        "closed": "closed",
    }.get(status or "", "detected")


def _legacy_mirror(workflow: str) -> str:
    if workflow == "closed":
        return "closed"
    if workflow in ("contained", "recovering", "resolved", "post_incident_review"):
        return "contained"
    return "open"


def transition(conn, incident_id: str, to_status: str, *, actor: str,
               note: str = "", at: str | None = None) -> dict:
    if to_status not in WORKFLOW:
        raise ValueError(f"Unknown workflow status: {to_status}")
    if not (actor or "").strip():
        raise ValueError("State transitions require a named actor.")
    row = conn.execute("SELECT * FROM incident WHERE id=?", (incident_id,)).fetchone()
    if not row:
        raise LookupError(incident_id)
    inc = dict(row)
    frm = current_status(inc)
    allowed = ALLOWED.get(frm, ())
    if to_status not in allowed:
        raise ValueError(
            f"Cannot move from {WORKFLOW_LABEL.get(frm, frm)} to "
            f"{WORKFLOW_LABEL.get(to_status, to_status)}. "
            f"Allowed: {', '.join(WORKFLOW_LABEL[s] for s in allowed) or 'none'}.")
    when = at or risk.now()
    tid = f"ITR-{uuid.uuid4().hex[:10]}"
    conn.execute(
        "INSERT INTO incident_transition(id, incident_id, from_status, to_status, "
        "actor, at, note, is_synthetic) VALUES (?,?,?,?,?,?,?,?)",
        (tid, incident_id, frm, to_status, actor.strip(), when, note or "",
         int(inc.get("is_synthetic") or 0)))
    changes = {
        "workflow_status": to_status,
        "status": _legacy_mirror(to_status),
    }
    if to_status == "closed":
        changes["closed_at"] = when
    if to_status == "recovering" and not inc.get("recovery_started_at"):
        changes["recovery_started_at"] = when
    if to_status in ("resolved", "post_incident_review", "closed") and not inc.get("resolved_at"):
        changes["resolved_at"] = when
    if to_status == "resolved" and not inc.get("restored_at"):
        changes["restored_at"] = when
    return risk.update(conn, "incident", incident_id, changes, actor=actor)


def transitions(conn, incident_id: str) -> pd.DataFrame:
    return risk._df(conn, """
        SELECT * FROM incident_transition WHERE incident_id=?
        ORDER BY at, rowid""", (incident_id,))


# --- register / detail ------------------------------------------------------------

def register(conn) -> pd.DataFrame:
    df = risk.incidents(conn)
    if df.empty:
        return df
    df = df.copy()
    df["workflow_status"] = [
        (w if isinstance(w, str) and w else _legacy_status(s))
        for w, s in zip(df.get("workflow_status", [""] * len(df)), df["status"])]
    df["workflow_label"] = df["workflow_status"].map(
        lambda s: WORKFLOW_LABEL.get(s, s))
    timings = [timing_metrics(r) for _, r in df.iterrows()]
    for key in ("detection_delay_min", "time_to_escalation_min",
                "disruption_duration_min", "recovery_duration_min"):
        df[key] = [t[key] for t in timings]
    # Aggregate loss table if present
    losses = risk._df(conn, """
        SELECT incident_id,
               SUM(gross_loss) AS loss_gross,
               SUM(recovered) AS loss_recovered,
               SUM(gross_loss) - SUM(recovered) AS loss_net
        FROM incident_loss GROUP BY incident_id""")
    if not losses.empty:
        df = df.merge(losses, left_on="id", right_on="incident_id", how="left")
        df["net_loss"] = df["loss_net"].fillna(df["net_loss"])
    return df


def detail(conn, incident_id: str, index_conn=None) -> dict:
    row = conn.execute("SELECT * FROM incident WHERE id=?", (incident_id,)).fetchone()
    if not row:
        raise LookupError(incident_id)
    inc = dict(row)
    links = [dict(r) for r in conn.execute(
        "SELECT * FROM incident_link WHERE incident_id=?", (incident_id,))]
    losses = risk._df(conn, "SELECT * FROM incident_loss WHERE incident_id=? "
                            "ORDER BY recognition_date, id", (incident_id,))
    rca = conn.execute("SELECT * FROM incident_rca WHERE incident_id=?",
                       (incident_id,)).fetchone()
    reporting = risk._df(conn, "SELECT * FROM incident_reporting WHERE incident_id=? "
                               "ORDER BY id", (incident_id,))
    acts = risk.actions(conn)
    acts = acts[(acts["source_kind"] == "incident") & (acts["source_id"] == incident_id)] \
        if not acts.empty else acts
    # Enrich obligation citations for reporting rows
    if index_conn is not None and not reporting.empty:
        cites = []
        for _, r in reporting.iterrows():
            c = risk.obligation_citation(index_conn, r["obligation_okey"]) \
                if r.get("obligation_okey") else None
            cites.append(c["citation"] if c else r.get("citation") or "")
        reporting = reporting.copy()
        reporting["live_citation"] = cites
    return {
        "incident": inc,
        "timing": timing_metrics(inc),
        "links": links,
        "losses": losses,
        "rca": dict(rca) if rca else None,
        "reporting": reporting,
        "actions": acts,
        "transitions": transitions(conn, incident_id),
        "severity_note": SEVERITY_FRAMEWORK_NOTE,
        "notice": NOTICE if inc.get("is_synthetic") else "",
    }


def save_rca(conn, incident_id: str, fields: dict, *, actor: str) -> dict:
    payload = {
        "incident_id": incident_id,
        "what_happened": fields.get("what_happened") or "",
        "technical_trigger": fields.get("technical_trigger") or "",
        "process_weakness": fields.get("process_weakness") or "",
        "detection_gap": fields.get("detection_gap") or "",
        "controls_failed": fields.get("controls_failed") or "",
        "controls_worked": fields.get("controls_worked") or "",
        "evidence": fields.get("evidence") or "",
        "unconfirmed": fields.get("unconfirmed") or "",
        "five_whys_json": fields.get("five_whys_json") or "[]",
        "updated_at": risk.now(),
        "updated_by": actor or "",
        "is_synthetic": int(fields.get("is_synthetic") or 0),
    }
    existing = conn.execute(
        "SELECT incident_id FROM incident_rca WHERE incident_id=?",
        (incident_id,)).fetchone()
    if existing:
        sets = ", ".join(f"{k}=?" for k in payload if k != "incident_id")
        conn.execute(
            f"UPDATE incident_rca SET {sets} WHERE incident_id=?",
            [payload[k] for k in payload if k != "incident_id"] + [incident_id])
        risk._log(conn, actor, "update", "incident_rca", incident_id, None, payload)
        return payload
    conn.execute(
        "INSERT INTO incident_rca(" + ", ".join(payload) + ") VALUES ("
        + ", ".join("?" * len(payload)) + ")", list(payload.values()))
    risk._log(conn, actor, "create", "incident_rca", incident_id, None, payload)
    return payload


def add_loss(conn, incident_id: str, *, gross: float, recovered: float = 0,
             currency: str = "ILS", category: str = "", recognition_date: str = "",
             evidence: str = "", certainty: str = "estimate", note: str = "",
             actor: str = "", is_synthetic: int = 0) -> dict:
    if certainty not in CERTAINTY:
        raise ValueError(f"Certainty must be one of {CERTAINTY}")
    return risk.insert(conn, "incident_loss", {
        "id": f"LOSS-{uuid.uuid4().hex[:8]}",
        "incident_id": incident_id,
        "gross_loss": float(gross),
        "recovered": float(recovered),
        "currency": currency,
        "loss_category": category,
        "recognition_date": recognition_date or risk._today(),
        "evidence_ref": evidence,
        "certainty": certainty,
        "note": note,
        "is_synthetic": int(is_synthetic),
        "provenance": "synthetic" if is_synthetic else "user",
    }, actor=actor or "system")


def create_remediation(conn, *, incident_id: str, title: str, owner: str,
                       due_at: str, priority: str = "high",
                       control_deficiency: str = "", related_risk_id: str = "",
                       evidence_required: str = "", actor: str = "",
                       is_synthetic: int = 0) -> dict:
    return risk.insert(conn, "action", {
        "id": f"ACT-INC-{uuid.uuid4().hex[:8]}",
        "source_kind": "incident",
        "source_id": incident_id,
        "title": title,
        "owner": owner,
        "due_at": due_at,
        "status": "open",
        "priority": priority,
        "control_deficiency": control_deficiency,
        "related_risk_id": related_risk_id,
        "evidence_required": evidence_required,
        "validation_outcome": "pending",
        "is_synthetic": int(is_synthetic),
        "provenance": "synthetic" if is_synthetic else "user",
    }, actor=actor or "system")


def mark_owner_complete(conn, action_id: str, *, owner: str,
                        evidence: str = "") -> dict:
    """Owner marks work done — does not set independent validation."""
    if not (owner or "").strip():
        raise ValueError("Owner completion requires a named owner.")
    changes = {
        "status": "done",
        "closed_at": risk.now(),
        "validation_outcome": "pending",
    }
    if evidence:
        changes["closure_evidence"] = evidence
    return risk.update(conn, "action", action_id, changes, actor=owner)


def validate_action_closure(conn, action_id: str, *, outcome: str, reviewer: str,
                            evidence: str = "") -> dict:
    if outcome not in ("validated", "rejected", "pending"):
        raise ValueError("Validation outcome must be validated, rejected or pending.")
    if not (reviewer or "").strip():
        raise ValueError("Independent closure validation needs a named reviewer.")
    changes = {
        "validation_outcome": outcome,
        "closure_reviewer": reviewer.strip(),
        "validated_at": risk.now(),
    }
    if evidence:
        changes["closure_evidence"] = evidence
    if outcome == "validated":
        changes["status"] = "done"
        changes["closed_at"] = risk.now()
    elif outcome == "rejected":
        changes["status"] = "open"
        changes["closed_at"] = None
    return risk.update(conn, "action", action_id, changes, actor=reviewer)


# --- dashboard / export -----------------------------------------------------------

def dashboard(conn) -> dict:
    reg = register(conn)
    open_ = reg[~reg["workflow_status"].isin(["closed"])] if not reg.empty else reg
    by_sev = open_.groupby("severity").size().to_dict() if not open_.empty else {}
    by_type = open_.groupby("event_type").size().to_dict() if not open_.empty else {}
    acts = risk.actions(conn)
    overdue = acts[acts["overdue"]] if not acts.empty else acts
    # Repeated failed controls across incidents
    failed = risk._df(conn, """
        SELECT target_id AS control_id, COUNT(*) AS n
        FROM incident_link WHERE kind='failed_control'
        GROUP BY target_id HAVING COUNT(*) > 1""")
    themes = risk._df(conn, """
        SELECT process_weakness AS theme, COUNT(*) AS n FROM incident_rca
        WHERE process_weakness IS NOT NULL AND process_weakness != ''
        GROUP BY process_weakness""")
    return {
        "notice": NOTICE,
        "register": reg,
        "open_by_severity": by_sev,
        "open_by_event_type": by_type,
        "avg_detection_min": float(open_["detection_delay_min"].dropna().mean())
        if not open_.empty and open_["detection_delay_min"].notna().any() else None,
        "avg_restoration_min": float(open_["disruption_duration_min"].dropna().mean())
        if not open_.empty and open_["disruption_duration_min"].notna().any() else None,
        "overdue_actions": overdue,
        "repeated_control_failures": failed,
        "root_cause_themes": themes,
        "total_net_loss": float(reg["net_loss"].fillna(0).sum()) if not reg.empty else 0.0,
    }


def export_csv(reg: pd.DataFrame) -> bytes:
    cols = [
        "id", "title", "workflow_status", "severity", "severity_rationale",
        "occurred_at", "detected_at", "escalated_at", "recovery_started_at",
        "restored_at", "resolved_at", "closed_at", "owner", "business_process",
        "legal_entity", "jurisdiction", "customers_affected", "failed_transactions",
        "gross_loss", "recovered", "net_loss", "currency",
        "detection_delay_min", "time_to_escalation_min",
        "disruption_duration_min", "recovery_duration_min", "is_synthetic",
    ]
    use = [c for c in cols if c in (reg.columns if reg is not None else [])]
    buf = io.StringIO()
    if reg is None or reg.empty:
        csv.writer(buf).writerow(cols)
    else:
        reg[use].to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# --- synthetic demo ---------------------------------------------------------------

def seed(conn, index_conn=None, *, today: dt.date | None = None,
         force: bool = False) -> dict:
    """Cloud-provider disruption affecting payments — labelled synthetic."""
    if not force and risk.get_meta(conn, "incident_seed_version") == SEED_VERSION:
        return {"seeded": False}
    from . import demo_data, kri_appetite
    demo_data.seed(conn, index_conn, today=today)
    kri_appetite.seed(conn, today=today)

    # Remove prior demo incident artefacts
    iid = "INC-DEMO-CLOUD"
    for table, col in (("incident_transition", "incident_id"),
                       ("incident_loss", "incident_id"),
                       ("incident_rca", "incident_id"),
                       ("incident_reporting", "incident_id"),
                       ("incident_link", "incident_id")):
        conn.execute(f"DELETE FROM {table} WHERE {col}=?", (iid,))
    conn.execute("DELETE FROM action WHERE source_kind='incident' AND source_id=?", (iid,))
    conn.execute("DELETE FROM incident WHERE id=?", (iid,))

    # Fixed demo day so timings are stable in screenshots; use today if preferred.
    day = (today or dt.date.today()).isoformat()

    def ts(hm: str) -> str:
        return f"{day}T{hm}:00+00:00"

    risk.insert(conn, "incident", {
        "id": iid,
        "title": "Cloud provider disruption interrupting payment authorisation",
        "description": (
            "A regional disruption at the critical cloud hosting provider interrupted "
            "card payment authorisation for Demo Digital Bank Ltd (fictional). "
            "All timeline entries below are synthetic demonstration data."),
        "event_type": "Business disruption and system failures",
        "service_id": "SVC-001",
        "severity": "P1",
        "severity_rationale": (
            "Illustrative P1: critical payment service unavailable, material customer "
            "transaction failures, duration over one hour, third-party concentration. "
            + SEVERITY_FRAMEWORK_NOTE),
        "occurred_at": ts("09:00"),
        "detected_at": ts("09:05"),
        "escalated_at": ts("09:08"),
        "recovery_started_at": ts("09:25"),
        "restored_at": ts("10:40"),
        "resolved_at": ts("10:40"),
        "closed_at": None,
        "workflow_status": "post_incident_review",
        "status": "contained",
        "discovery_source": "Monitoring / KRI breach (synthetic)",
        "business_process": "Card payment authorisation",
        "legal_entity": ENTITY,
        "jurisdiction": "IL",
        "owner": "Head of Payments Operations",
        "customers_affected": 42000,
        "failed_transactions": 18500,
        "customer_impact": "Confirmed: card authorisations failed for ~100 minutes "
                           "(synthetic count).",
        "financial_impact_note": "Estimate: fee refunds and goodwill; see loss event.",
        "regulatory_impact": "Hypothesis: may meet technology-incident reporting "
                             "criteria — requires compliance assessment (not decided).",
        "third_party_involvement": "Confirmed: critical cloud provider regional outage "
                                   "(synthetic name: NimbusCloud).",
        "gross_loss": 95000,
        "recovered": 12000,
        "currency": "ILS",
        "root_cause": "See structured RCA — preliminary.",
        "lessons_learned": "",
        "timezone": "UTC",
        "is_synthetic": 1,
        "provenance": "synthetic",
        "validation_status": "draft",
    }, actor=ACTOR)

    # Timeline transitions (synthetic actors)
    path = [
        ("detected", "09:05", "Monitoring identified payment failure spike"),
        ("triaged", "09:08", "Incident triage opened"),
        ("investigating", "09:15", "Potential dependency on affected cloud region"),
        ("contained", "09:25", "Recovery procedures initiated"),
        ("recovering", "09:25", "Failover / recovery in progress"),
        ("resolved", "10:40", "Normal service restored"),
        ("post_incident_review", "11:30", "PIR opened; RCA in progress"),
    ]
    prev = None
    for to, hm, note in path:
        conn.execute(
            "INSERT INTO incident_transition(id, incident_id, from_status, to_status, "
            "actor, at, note, is_synthetic) VALUES (?,?,?,?,?,?,?,1)",
            (f"ITR-DEMO-{to}", iid, prev, to, ACTOR, ts(hm), note))
        prev = to

    for kind, target in (
        ("risk", "DEMO-RISK-001"),
        ("risk", "RSK-002"),
        ("failed_control", "CTL-DEMO-03"),
        ("kri_breach", "KRI-PAY-FAIL"),
    ):
        risk.insert(conn, "incident_link", {
            "incident_id": iid, "kind": kind, "target_id": target,
        }, actor=ACTOR)

    add_loss(conn, iid, gross=95000, recovered=12000, currency="ILS",
             category="Business disruption — payment fees & goodwill",
             recognition_date=day, evidence="Synthetic finance memo FIN-DEMO-01",
             certainty="estimate",
             note="Estimate only — not a confirmed statutory loss figure.",
             actor=ACTOR, is_synthetic=1)

    save_rca(conn, iid, {
        "what_happened": "Confirmed (synthetic): payment authorisation failed during a "
                         "cloud-region disruption until failover completed.",
        "technical_trigger": "Confirmed (synthetic): provider regional infrastructure "
                             "event affecting the primary region.",
        "process_weakness": "Hypothesis: single-region concentration and incomplete "
                            "follow-up on a prior failover test finding.",
        "detection_gap": "Confirmed (synthetic): KRI rose at 09:03; human triage at 09:08 "
                         "(3–5 minutes after detection).",
        "controls_failed": json.dumps([
            "CTL-DEMO-03 Failover and recovery testing (partially effective — prior "
            "unresolved finding)",
        ]),
        "controls_worked": json.dumps([
            "CTL-DEMO-02 Third-party service monitoring (alerted)",
            "CTL-DEMO-04 Documented incident escalation",
        ]),
        "evidence": "Synthetic: monitoring alerts; KRI-PAY-FAIL observations; "
                    "prior test file CTT-DEMO-03 findings.",
        "unconfirmed": "Provider root cause details beyond the public status page; "
                       "exact regulatory notification obligation applicability.",
        "five_whys_json": json.dumps([
            {"why": "Why were payments failing?",
             "answer": "Authorisation path depended on the disrupted cloud region.",
             "certainty": "confirmed"},
            {"why": "Why was traffic not already on the second region?",
             "answer": "Active-active routing was incomplete for this path.",
             "certainty": "estimate"},
            {"why": "Why was the gap not closed earlier?",
             "answer": "A scheduled failover test had flagged an unresolved runbook issue.",
             "certainty": "confirmed"},
            {"why": "Why was the test finding still open?",
             "answer": "Remediation ownership/due-date follow-up was weak (hypothesis).",
             "certainty": "hypothesis"},
            {"why": "Why did that process weakness persist?",
             "answer": "Requires PIR confirmation — not established from metrics alone.",
             "certainty": "hypothesis"},
        ]),
        "is_synthetic": 1,
    }, actor=ACTOR)

    create_remediation(
        conn, incident_id=iid,
        title="Close out the unresolved failover-test finding and re-test payment failover",
        owner="Head of Business Continuity",
        due_at=(dt.date.fromisoformat(day) + dt.timedelta(days=14)).isoformat(),
        priority="critical",
        control_deficiency="CTL-DEMO-03 partially effective — unresolved DNS/runbook gap",
        related_risk_id="DEMO-RISK-001",
        evidence_required="Updated runbook + successful timed failover test record",
        actor=ACTOR, is_synthetic=1)

    # Regulatory reporting assessment — for review, not a notification decision
    okey = None
    citation = ""
    doc = "IL-BOI-PC-366"
    if index_conn is not None:
        try:
            found = index_conn.execute(
                "SELECT okey FROM obligation WHERE document_id=? AND "
                "LOWER(sentence) LIKE ? LIMIT 1",
                (doc, "%within two hours%")).fetchone()
            if found:
                okey = found["okey"]
                cite = risk.obligation_citation(index_conn, okey)
                citation = cite["citation"] if cite else ""
        except Exception:
            okey = None
    risk.insert(conn, "incident_reporting", {
        "id": "IRPT-DEMO-01",
        "incident_id": iid,
        "obligation_okey": okey or "",
        "document_id": doc,
        "citation": citation or "Bank of Israel · Directive 366 (assess if in scope)",
        "jurisdiction": "IL",
        "trigger_criteria": (
            "Technology / cyber incident reporting criteria in Directive 366 — "
            "confirm applicability, materiality and timing with Compliance."),
        "review_required": "Legal/Compliance review of whether this event meets "
                           "reporting thresholds and clocks.",
        "evidence": "Incident timeline; customer impact counts; provider notices "
                    "(synthetic).",
        "decision_owner": "Head of Compliance",
        "reporting_status": "under_review",
        "decision_note": "No notification decision has been taken in this demo. "
                         "Do not treat this row as a mandatory filing.",
        "is_synthetic": 1,
        "provenance": "synthetic",
    }, actor=ACTOR)

    risk.set_meta(conn, "incident_seed_version", SEED_VERSION)
    risk.set_meta(conn, "incident_seeded_at", risk.now())
    return {"seeded": True, "incident_id": iid, "timing": timing_metrics(
        dict(conn.execute("SELECT * FROM incident WHERE id=?", (iid,)).fetchone()))}
