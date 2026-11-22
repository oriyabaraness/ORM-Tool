"""Key Risk Indicators and risk appetite: catalogue, deterministic calculations,
observations, escalations and management commentary drafts.

Built on orm.risk (same orm_risk.db). Values are never hard-coded in the UI —
they come from kri_observation / kri_reading. Synthetic demo data is labelled.
No external alerts are sent automatically.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid

import pandas as pd

from . import risk

SEED_VERSION = "kri-1"
ACTOR = "Synthetic KRI demo seed"
ENTITY = "Demo Digital Bank Ltd (fictional)"
NOTICE = (
    "Illustrative KRI and appetite figures for a synthetic demonstration. "
    "Not Revolut data and not any real bank's thresholds."
)

# leading = early warning; lagging = after-the-fact; mixed = both aspects.
LEADING_LAGGING_HELP = {
    "leading": "Leading — tends to signal rising risk before a major loss event.",
    "lagging": "Lagging — reflects outcomes after risk has crystallised.",
    "mixed": "Mixed — combines early-warning and outcome elements.",
}


# --- deterministic calculations ---------------------------------------------------

class ZeroDenominator(ValueError):
    """Raised when a rate formula has denominator 0."""


def compute_rate(numerator: float | None, denominator: float | None) -> float | None:
    """(numerator / denominator) * 100. None inputs → None. den=0 → ZeroDenominator."""
    if numerator is None or denominator is None:
        return None
    if float(denominator) == 0.0:
        raise ZeroDenominator("Denominator is zero; rate is undefined.")
    return round(100.0 * float(numerator) / float(denominator), 6)


def compute_count(numerator: float | None, denominator: float | None = None) -> float | None:
    """Count KRIs use the numerator only."""
    if numerator is None:
        return None
    return float(numerator)


FORMULAS = {
    "rate_pct": compute_rate,
    "count": compute_count,
}


def classify_rag(value: float | None, green: float, amber: float,
                 direction: str) -> str:
    """Boundary-inclusive green/amber as documented on each KRI."""
    return risk.kri_rag(value, green, amber, direction)


def trend(current: float | None, previous: float | None,
          direction: str) -> str:
    if current is None or previous is None:
        return "No data"
    if current == previous:
        return "Stable"
    worse = (current > previous) if direction == "higher_is_worse" else (current < previous)
    return "Deteriorating" if worse else "Improving"


# --- catalogue / observations -----------------------------------------------------

def library(conn) -> pd.DataFrame:
    """KRI catalogue with latest value and RAG."""
    status = risk.kri_status(conn)
    if status.empty:
        return status
    # Enrich with linked risks
    links = risk._df(conn, "SELECT kri_id, GROUP_CONCAT(risk_id) AS risk_ids "
                           "FROM kri_risk GROUP BY kri_id")
    by = dict(zip(links["kri_id"], links["risk_ids"])) if not links.empty else {}
    status = status.copy()
    status["linked_risks"] = status["id"].map(
        lambda i: by.get(i) or status.loc[status["id"] == i, "risk_id"].iloc[0])
    status["warning_threshold"] = status.apply(
        lambda r: r["warning_threshold"] if pd.notna(r.get("warning_threshold"))
        else r["amber_limit"], axis=1)
    status["breach_threshold"] = status.apply(
        lambda r: r["breach_threshold"] if pd.notna(r.get("breach_threshold"))
        else (r["amber_limit"] if r["direction"] == "higher_is_worse"
              else r["amber_limit"]), axis=1)
    # For higher_is_worse: green<=g, amber<=a, red>a → breach threshold is amber edge
    # For lower_is_worse: green>=g, amber>=a, red<a → breach threshold is amber edge
    status["classification"] = status["leading_lagging"].fillna("mixed").map(
        lambda x: LEADING_LAGGING_HELP.get(x, LEADING_LAGGING_HELP["mixed"]))
    return status


def observations(conn, kri_id: str) -> pd.DataFrame:
    return risk._df(conn, """
        SELECT * FROM kri_observation WHERE kri_id = ?
        ORDER BY observed_at, period""", (kri_id,))


def record_observation(conn, *, kri_id: str, period: str, observed_at: str,
                       numerator: float | None = None, denominator: float | None = None,
                       value: float | None = None, formula: str = "rate_pct",
                       source: str = "manual", note: str = "", actor: str = "",
                       is_synthetic: int = 0, unit: str = "") -> dict:
    """Persist one observation; value is computed when numerator/denominator given."""
    kri = conn.execute("SELECT * FROM kri WHERE id=?", (kri_id,)).fetchone()
    if not kri:
        raise LookupError(kri_id)
    if value is None and formula in FORMULAS:
        value = FORMULAS[formula](numerator, denominator)
    elif value is None:
        value = numerator
    oid = f"OBS-{uuid.uuid4().hex[:10]}"
    at = risk.now()
    row = {
        "id": oid, "kri_id": kri_id, "observed_at": observed_at, "period": period,
        "numerator": numerator, "denominator": denominator, "value": value,
        "unit": unit or kri["unit"], "source": source, "note": note,
        "entered_by": actor or "", "entered_at": at, "is_synthetic": int(is_synthetic),
    }
    risk.insert(conn, "kri_observation", row, actor=actor or "system")
    # Mirror into kri_reading for existing screens / reports.
    existing = conn.execute(
        "SELECT 1 FROM kri_reading WHERE kri_id=? AND period=?",
        (kri_id, period)).fetchone()
    if existing:
        conn.execute(
            "UPDATE kri_reading SET value=?, note=?, entered_by=?, entered_at=?, "
            "is_synthetic=? WHERE kri_id=? AND period=?",
            (value, note, actor or "", at, int(is_synthetic), kri_id, period))
    else:
        risk.insert(conn, "kri_reading", {
            "kri_id": kri_id, "period": period, "value": value, "note": note,
            "entered_by": actor or "", "entered_at": at,
            "is_synthetic": int(is_synthetic),
        }, actor=actor or "system")
    conn.execute("UPDATE kri SET last_validated_at=? WHERE id=?", (at, kri_id))
    return evaluate_and_escalate(conn, kri_id, period, value, oid, actor=actor or "")


def ingest_csv(conn, text: str, *, actor: str, is_synthetic: int = 0) -> list[dict]:
    """CSV columns: kri_id, period, observed_at, numerator, denominator[, value, note]."""
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        kri_id = (row.get("kri_id") or "").strip()
        if not kri_id:
            continue
        num = row.get("numerator")
        den = row.get("denominator")
        val = row.get("value")
        formula = "count" if den in (None, "") and num not in (None, "") else "rate_pct"
        out.append(record_observation(
            conn, kri_id=kri_id, period=(row.get("period") or "").strip(),
            observed_at=(row.get("observed_at") or row.get("period") or risk.now()),
            numerator=None if num in (None, "") else float(num),
            denominator=None if den in (None, "") else float(den),
            value=None if val in (None, "") else float(val),
            formula=formula, source="csv", note=row.get("note") or "",
            actor=actor, is_synthetic=is_synthetic,
            unit=row.get("unit") or ""))
    return out


# --- appetite ---------------------------------------------------------------------

def appetite_statements(conn) -> pd.DataFrame:
    return risk._df(conn, "SELECT * FROM appetite_statement WHERE status='active' "
                          "ORDER BY id")


def concepts_glossary() -> list[tuple[str, str]]:
    return [
        ("Risk appetite", "The type and amount of risk the firm is willing to take "
         "to meet its objectives (board-approved statement)."),
        ("Risk tolerance", "The acceptable variation around appetite for a metric "
         "or residual score — often expressed as amber/red bands."),
        ("KRI warning threshold", "The amber boundary on a specific indicator; "
         "an early prompt for management attention."),
        ("Service impact tolerance", "The maximum disruption a critical service "
         "can absorb (e.g. hours) before resilience objectives are breached."),
    ]


# --- escalations ------------------------------------------------------------------

def evaluate_and_escalate(conn, kri_id: str, period: str, value: float | None,
                          observation_id: str, *, actor: str) -> dict:
    """If Amber/Red, open or refresh an escalation. Never sends mail."""
    kri = dict(conn.execute("SELECT * FROM kri WHERE id=?", (kri_id,)).fetchone())
    rag = classify_rag(value, float(kri["green_limit"]), float(kri["amber_limit"]),
                       kri["direction"])
    result = {"kri_id": kri_id, "period": period, "value": value, "rag": rag,
              "escalation_id": None}
    if rag not in ("Amber", "Red") or value is None:
        return result
    risks = [r[0] for r in conn.execute(
        "SELECT risk_id FROM kri_risk WHERE kri_id=?", (kri_id,))]
    if not risks and kri.get("risk_id"):
        risks = [kri["risk_id"]]
    owner = kri.get("metric_owner") or kri.get("owner") or kri.get("risk_owner") or ""
    recommendation = (
        f"Review {kri['name']} ({rag}). Latest value {value:g} {kri['unit']} "
        f"for period {period}. Confirm data quality, assess linked risks "
        f"({', '.join(risks) or 'none linked'}), and decide whether to open "
        f"an investigation or remediation action. No external notification "
        f"has been sent.")
    commentary = management_commentary(kri, value, rag, period, risks, owner)
    existing = conn.execute(
        "SELECT id FROM kri_escalation WHERE kri_id=? AND period=? AND "
        "ack_status IN ('open','acknowledged')", (kri_id, period)).fetchone()
    if existing:
        risk.update(conn, "kri_escalation", existing["id"], {
            "status_rag": rag, "value": value, "observation_id": observation_id,
            "recommendation": recommendation, "commentary": commentary,
            "related_risks": json.dumps(risks), "owner": owner,
        }, actor=actor or "system")
        result["escalation_id"] = existing["id"]
        return result
    eid = f"ESC-{uuid.uuid4().hex[:10]}"
    risk.insert(conn, "kri_escalation", {
        "id": eid, "kri_id": kri_id, "observation_id": observation_id,
        "period": period, "status_rag": rag, "value": value,
        "triggered_at": risk.now(), "related_risks": json.dumps(risks),
        "owner": owner, "recommendation": recommendation, "commentary": commentary,
        "ack_status": "open", "provenance": "synthetic" if kri.get("is_synthetic") else "user",
        "validation_status": "draft", "is_synthetic": int(kri.get("is_synthetic") or 0),
    }, actor=actor or "system")
    result["escalation_id"] = eid
    return result


def management_commentary(kri: dict, value: float, rag: str, period: str,
                          risk_ids: list[str], owner: str) -> str:
    """Editable draft. Facts and hypotheses are separated explicitly."""
    direction = "higher values are worse" if kri["direction"] == "higher_is_worse" \
        else "lower values are worse"
    return (
        f"FACTS\n"
        f"- Indicator: {kri['name']} ({kri['id']}).\n"
        f"- Period: {period}. Observed value: {value:g} {kri['unit']} "
        f"({direction}).\n"
        f"- Status: {rag} against illustrative green {kri['green_limit']:g} / "
        f"amber {kri['amber_limit']:g}.\n"
        f"- Linked risks: {', '.join(risk_ids) or 'none recorded'}.\n"
        f"- Accountable metric owner: {owner or 'not set'}.\n"
        f"\n"
        f"HYPOTHESES (not established — require investigation)\n"
        f"- Possible contributors could include process exceptions, third-party "
        f"degradation, change activity, or data-quality issues. These are "
        f"prompts for review, not root causes inferred from the metric alone.\n"
        f"\n"
        f"PROPORTIONATE NEXT STEPS (draft)\n"
        f"1. Acknowledge this escalation and validate the observation.\n"
        f"2. Review linked RCSA risks and recent control-test exceptions.\n"
        f"3. Open an investigation or remediation action if the breach is confirmed.\n"
        f"4. Report to the stated audience: {kri.get('reporting_audience') or 'management'}.\n"
        f"\n"
        f"{NOTICE}"
    )


def escalations(conn, *, open_only: bool = False) -> pd.DataFrame:
    where = "WHERE ack_status IN ('open','acknowledged')" if open_only else ""
    return risk._df(conn, f"SELECT * FROM kri_escalation {where} "
                          f"ORDER BY triggered_at DESC")


def acknowledge_escalation(conn, escalation_id: str, *, actor: str,
                           note: str = "") -> dict:
    return risk.update(conn, "kri_escalation", escalation_id, {
        "ack_status": "acknowledged",
        "acknowledged_by": actor,
        "acknowledged_at": risk.now(),
        "resolution_note": note,
    }, actor=actor)


def approve_escalation_action(conn, escalation_id: str, *, actor: str,
                              title: str = "", due_days: int = 14) -> dict:
    """Create a remediation action linked to the escalation; does not email anyone."""
    esc = conn.execute("SELECT * FROM kri_escalation WHERE id=?",
                       (escalation_id,)).fetchone()
    if not esc:
        raise LookupError(escalation_id)
    aid = f"ACT-KRI-{uuid.uuid4().hex[:8]}"
    due = (dt.date.today() + dt.timedelta(days=due_days)).isoformat()
    risk.insert(conn, "action", {
        "id": aid, "source_kind": "kri", "source_id": esc["kri_id"],
        "title": title or f"Investigate {esc['kri_id']} {esc['status_rag']} breach "
                          f"({esc['period']})",
        "owner": esc["owner"] or actor, "due_at": due, "status": "open",
        "provenance": "user", "validation_status": "draft",
        "is_synthetic": int(esc["is_synthetic"] or 0),
    }, actor=actor)
    return risk.update(conn, "kri_escalation", escalation_id, {
        "ack_status": "actioned", "action_id": aid,
        "acknowledged_by": actor, "acknowledged_at": risk.now(),
    }, actor=actor)


# --- dashboard frames -------------------------------------------------------------

def dashboard(conn, today: str | None = None) -> dict:
    today = today or risk._today()
    lib = library(conn)
    esc = escalations(conn, open_only=True)
    reg = risk.register(conn, today)
    acts = risk.actions(conn, today)
    breaches = lib[lib["rag"] == "Red"] if not lib.empty else lib
    warnings = lib[lib["rag"] == "Amber"] if not lib.empty else lib
    outside = reg[reg["appetite"] == "Outside appetite"] if not reg.empty else reg
    overdue = acts[acts["overdue"]] if not acts.empty else acts
    return {
        "notice": NOTICE,
        "cards": {
            "active_breaches": len(breaches),
            "warning_indicators": len(warnings),
            "risks_exceeding_appetite": len(outside),
            "overdue_actions": len(overdue),
        },
        "library": lib,
        "escalations": esc,
        "register": reg,
        "appetite": appetite_statements(conn),
        "overdue_actions": overdue,
    }


def filter_library(lib: pd.DataFrame, *, business_process: str = "",
                   legal_entity: str = "", owner: str = "",
                   severity: str = "") -> pd.DataFrame:
    if lib is None or lib.empty:
        return lib
    out = lib
    if business_process:
        out = out[out["business_process"] == business_process]
    if legal_entity:
        out = out[out["legal_entity"] == legal_entity]
    if owner:
        out = out[(out["metric_owner"] == owner) | (out["owner"] == owner)]
    if severity and severity != "All":
        out = out[out["rag"] == severity]
    return out.reset_index(drop=True)


# --- synthetic demo seed ----------------------------------------------------------

def seed(conn, *, today: dt.date | None = None, force: bool = False) -> dict:
    """Idempotent synthetic KRI catalogue + 30-day payment-failure story."""
    if not force and risk.get_meta(conn, "kri_seed_version") == SEED_VERSION:
        return {"seeded": False}
    # Ensure parent risks exist (RCSA demo).
    from . import demo_data
    demo_data.seed(conn, None, today=today)
    today = today or dt.date.today()

    # Wipe prior synthetic KRI demo rows only (by id prefix / is_synthetic kri ids).
    for kid in ("KRI-PAY-FAIL", "KRI-TPP-AVAIL", "KRI-OVERDUE-ACT", "KRI-RECOVERY"):
        conn.execute("DELETE FROM kri_escalation WHERE kri_id=?", (kid,))
        conn.execute("DELETE FROM kri_observation WHERE kri_id=?", (kid,))
        conn.execute("DELETE FROM kri_reading WHERE kri_id=?", (kid,))
        conn.execute("DELETE FROM kri_risk WHERE kri_id=?", (kid,))
        conn.execute("DELETE FROM kri WHERE id=?", (kid,))
    conn.execute("DELETE FROM appetite_statement WHERE id LIKE 'APP-KRI-%'")

    def add(table, row):
        risk.insert(conn, table, {**row, "is_synthetic": 1, "provenance": "synthetic",
                                  "validation_status": "draft"}, actor=ACTOR)

    add("appetite_statement", {
        "id": "APP-KRI-PAY",
        "title": "Payment service availability appetite",
        "statement": (
            "Payment service availability risk should remain within approved "
            "operational tolerances, with material breaches escalated promptly "
            "to accountable management."),
        "kind": "appetite", "category_id": "third_party",
        "legal_entity": ENTITY, "business_process": "Card payment authorisation",
        "approved_by": "Board Risk Committee (synthetic)",
        "approved_at": (today - dt.timedelta(days=60)).isoformat(),
    })
    add("appetite_statement", {
        "id": "APP-KRI-TOL",
        "title": "Payment failure-rate tolerance",
        "statement": (
            "Illustrative tolerance: payment transaction failure rate amber above "
            "0.5% and red above 1.0% of eligible attempts."),
        "kind": "tolerance", "category_id": "op_resilience",
        "legal_entity": ENTITY, "business_process": "Card payment authorisation",
        "approved_by": "CRO (synthetic)",
        "approved_at": (today - dt.timedelta(days=60)).isoformat(),
    })

    catalogue = (
        {
            "id": "KRI-PAY-FAIL", "risk_id": "DEMO-RISK-001",
            "name": "Payment Transaction Failure Rate",
            "description": "Share of eligible payment attempts that fail. "
                           "Exclusions (timeouts after issuer decline codes, "
                           "test traffic) are configurable in exclusions_json.",
            "definition": "Failed payment attempts / Total eligible payment "
                          "attempts × 100",
            "formula": "Failed / Eligible × 100",
            "unit": "%", "direction": "higher_is_worse",
            "green_limit": 0.5, "amber_limit": 1.0,
            "warning_threshold": 0.5, "breach_threshold": 1.0,
            "baseline": 0.3, "frequency": "Daily",
            "collection_frequency": "Daily", "measurement_period": "Calendar day",
            "data_source": "Synthetic payment authorisation ledger",
            "owner": "Head of Payments Operations",
            "metric_owner": "Head of Payments Operations",
            "risk_owner": "Head of Payments Operations",
            "business_process": "Card payment authorisation",
            "legal_entity": ENTITY,
            "leading_lagging": "leading",
            "appetite_statement_id": "APP-KRI-PAY",
            "escalation_rules": "Amber: notify metric owner same day. "
                                "Red: open escalation and propose investigation action.",
            "reporting_audience": "Payments Ops; Operational Risk; CRO (synthetic)",
            "exclusions_json": json.dumps([
                "Issuer soft declines marked as customer-choice",
                "Synthetic load-test traffic",
            ]),
            "numerator_label": "Failed payment attempts",
            "denominator_label": "Eligible payment attempts",
            "last_validated_at": risk.now(),
        },
        {
            "id": "KRI-TPP-AVAIL", "risk_id": "DEMO-RISK-001",
            "name": "Critical Third-Party Service Availability",
            "description": "Availability of the critical cloud provider supporting "
                           "payment authorisation.",
            "definition": "Available monitored minutes / Total monitored minutes × 100",
            "formula": "Available minutes / Monitored minutes × 100",
            "unit": "%", "direction": "lower_is_worse",
            "green_limit": 99.9, "amber_limit": 99.5,
            "warning_threshold": 99.9, "breach_threshold": 99.5,
            "baseline": 99.95, "frequency": "Daily",
            "collection_frequency": "Daily", "measurement_period": "Calendar day",
            "data_source": "Synthetic provider monitoring",
            "owner": "Vendor Manager", "metric_owner": "Vendor Manager",
            "risk_owner": "Head of Third-Party Risk",
            "business_process": "Card payment authorisation",
            "legal_entity": ENTITY, "leading_lagging": "leading",
            "appetite_statement_id": "APP-KRI-PAY",
            "escalation_rules": "Amber/Red: escalate to third-party risk owner.",
            "reporting_audience": "Third-Party Risk; Payments Ops",
            "numerator_label": "Available monitored minutes",
            "denominator_label": "Total monitored minutes",
            "last_validated_at": risk.now(),
        },
        {
            "id": "KRI-OVERDUE-ACT", "risk_id": "DEMO-RISK-001",
            "name": "Overdue High-Severity Remediation Actions",
            "description": "Count of open high-severity remediation actions past due.",
            "definition": "Count of open high-severity actions past due date",
            "formula": "Count(open high-severity actions where due_at < today)",
            "unit": "count", "direction": "higher_is_worse",
            "green_limit": 0, "amber_limit": 2,
            "warning_threshold": 1, "breach_threshold": 3,
            "baseline": 0, "frequency": "Daily",
            "collection_frequency": "Daily", "measurement_period": "Point in time",
            "data_source": "Risk action tracker (synthetic)",
            "owner": "Head of Operational Risk",
            "metric_owner": "Head of Operational Risk",
            "risk_owner": "Head of Operational Risk",
            "business_process": "Remediation tracking",
            "legal_entity": ENTITY, "leading_lagging": "lagging",
            "escalation_rules": "Amber at 1–2; Red at 3+ overdue high-severity actions.",
            "reporting_audience": "Operational Risk Committee (synthetic)",
            "numerator_label": "Overdue high-severity actions",
            "denominator_label": "",
            "last_validated_at": risk.now(),
        },
        {
            "id": "KRI-RECOVERY", "risk_id": "DEMO-RISK-001",
            "name": "Unsuccessful Critical Recovery Tests",
            "description": "Count of unsuccessful critical recovery / failover tests "
                           "in the reporting period.",
            "definition": "Count of unsuccessful critical recovery tests",
            "formula": "Count(unsuccessful critical recovery tests in period)",
            "unit": "count", "direction": "higher_is_worse",
            "green_limit": 0, "amber_limit": 1,
            "warning_threshold": 1, "breach_threshold": 2,
            "baseline": 0, "frequency": "Monthly",
            "collection_frequency": "Per test / monthly roll-up",
            "measurement_period": "Rolling 30 days",
            "data_source": "Continuity test register (synthetic)",
            "owner": "Head of Business Continuity",
            "metric_owner": "Head of Business Continuity",
            "risk_owner": "Head of Payments Operations",
            "business_process": "Business continuity",
            "legal_entity": ENTITY, "leading_lagging": "mixed",
            "escalation_rules": "Any unsuccessful critical test → Amber; 2+ → Red.",
            "reporting_audience": "Business Continuity; Operational Risk",
            "numerator_label": "Unsuccessful critical recovery tests",
            "denominator_label": "",
            "last_validated_at": risk.now(),
        },
    )
    for row in catalogue:
        add("kri", row)
        add("kri_risk", {"kri_id": row["id"], "risk_id": "DEMO-RISK-001"})
        if row["id"] == "KRI-PAY-FAIL":
            add("kri_risk", {"kri_id": row["id"], "risk_id": "RSK-002"})

    # 30-day payment failure story: 0.3% → 1.8% with consistent counts.
    # Eligible attempts fixed at 100,000/day (illustrative).
    eligible = 100_000
    # Smooth path: days 1-10 green (~0.3%), 11-20 amber (~0.7%), 21-30 red up to 1.8%
    for i in range(30):
        day = today - dt.timedelta(days=29 - i)
        period = day.isoformat()
        if i < 10:
            rate = 0.30 + i * 0.01  # 0.30 → 0.39
        elif i < 20:
            rate = 0.55 + (i - 10) * 0.04  # 0.55 → 0.91
        else:
            rate = 1.05 + (i - 20) * 0.075  # 1.05 → 1.80
        failed = int(round(eligible * rate / 100.0))
        # Force exact 1.8% on the last day for the interview demo.
        if i == 29:
            failed, rate = 1800, 1.8
        if i == 0:
            failed, rate = 300, 0.3
        record_observation(
            conn, kri_id="KRI-PAY-FAIL", period=period,
            observed_at=day.isoformat() + "T18:00:00+00:00",
            numerator=failed, denominator=eligible, formula="rate_pct",
            source="synthetic", note=f"Illustrative: {failed} / {eligible}",
            actor=ACTOR, is_synthetic=1, unit="%")

    # Availability: mostly green, one amber dip
    for i in range(30):
        day = today - dt.timedelta(days=29 - i)
        period = day.isoformat()
        total = 1440
        avail = 1439 if i != 22 else 1430  # ~99.93% vs ~99.31%
        record_observation(
            conn, kri_id="KRI-TPP-AVAIL", period=period,
            observed_at=day.isoformat() + "T23:59:00+00:00",
            numerator=avail, denominator=total, formula="rate_pct",
            source="synthetic", note="Illustrative monitored minutes",
            actor=ACTOR, is_synthetic=1, unit="%")

    # Overdue actions & recovery tests — sparse daily counts
    for i in range(30):
        day = today - dt.timedelta(days=29 - i)
        period = day.isoformat()
        overdue = 0 if i < 20 else (1 if i < 27 else 3)
        record_observation(
            conn, kri_id="KRI-OVERDUE-ACT", period=period,
            observed_at=day.isoformat() + "T17:00:00+00:00",
            numerator=overdue, formula="count", source="synthetic",
            note="Illustrative count of overdue high-severity actions",
            actor=ACTOR, is_synthetic=1, unit="count")
        failed_tests = 0 if i < 25 else (1 if i < 28 else 2)
        record_observation(
            conn, kri_id="KRI-RECOVERY", period=period,
            observed_at=day.isoformat() + "T17:00:00+00:00",
            numerator=failed_tests, formula="count", source="synthetic",
            note="Illustrative unsuccessful critical recovery tests",
            actor=ACTOR, is_synthetic=1, unit="count")

    risk.set_meta(conn, "kri_seed_version", SEED_VERSION)
    risk.set_meta(conn, "kri_seeded_at", risk.now())
    return {"seeded": True, "kri_ids": [c["id"] for c in catalogue]}
