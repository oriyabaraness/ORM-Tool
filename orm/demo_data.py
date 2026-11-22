"""Synthetic demonstration data for the risk register.

Everything here is invented for a demo: the bank ("Demo Digital Bank Ltd"),
its services, risks, controls, test results, KRI readings, incidents, losses
and actions. Nothing comes from any real bank. Every row is marked
is_synthetic = 1 and the screens and exports say so.

The one thing that is not invented is the regulation. Each risk links to
obligations found in the index (orm.db) by searching a directive for a phrase.
If the phrase is not found -- a different index, a changed text -- the link
is left out and reported in `missing`, never typed in by hand.

Seeding is idempotent and writes only to the risk store (orm_risk.db).
"""
from __future__ import annotations

import datetime as dt
import json

from . import risk

SEED_VERSION = "3"
ACTOR = "Synthetic demo seed"
BANK = "Demo Digital Bank Ltd (fictional)"
CURRENCY = "ILS"
ENTITY = "Demo Digital Bank Ltd (fictional)"
UNIT = "Payments"

SERVICES = (
    {"id": "SVC-001", "name": "Card payments",
     "description": "Authorising and settling customer card payments.",
     "owner": "Head of Payments Operations", "criticality": "critical",
     "impact_tolerance_hours": 4, "rto_hours": 2, "rpo_hours": 0.25,
     "dependencies": ["Card processing platform (in-house)",
                      "Cloud hosting provider (fictional: NimbusCloud)",
                      "Card scheme connectivity"],
     "test_days_ago": 45,
     "last_test_result": "Failover to the second region completed in 1 h 40 min; "
                         "one manual DNS step was not in the runbook."},
    {"id": "SVC-002", "name": "Customer onboarding and login",
     "description": "Opening accounts and signing customers in to the app.",
     "owner": "Head of Customer Platform", "criticality": "important",
     "impact_tolerance_hours": 8, "rto_hours": 4, "rpo_hours": 1,
     "dependencies": ["Identity verification provider (fictional: VerifyNow)",
                      "Cloud hosting provider (fictional: NimbusCloud)"],
     "test_days_ago": 120, "last_test_result": "Recovered within RTO."},
)

APPETITE = (
    ("ict_cyber", 8, "Low appetite for technology failures that disrupt customers."),
    ("op_resilience", 9, "Critical services stay within impact tolerance in severe "
                         "but plausible scenarios."),
    ("third_party", 9, "No single provider failure may take a critical service "
                       "beyond its impact tolerance."),
    ("incident_reporting", 6, "Very low appetite for late or incomplete regulatory "
                              "notifications."),
)

def _risk_fields(**extra):
    """Common RCSA fields for synthetic risks. Residuals are explicit assessments."""
    base = {
        "business_unit": UNIT, "legal_entity": ENTITY, "jurisdiction": "IL",
        "residual_status": "approved", "residual_approver": ACTOR,
        "residual_evidence": "Synthetic RCSA working papers (demo only).",
    }
    base.update(extra)
    return base


RISKS = (
    _risk_fields(
        id="RSK-001", title="Payment outage caused by a failed production change",
        description="A software or configuration change to the card payment platform "
                    "fails in production and stops authorisations.",
        cause="Change deployed without adequate testing or rollback.",
        effect="Customers cannot pay by card; fee refunds and complaints.",
        category_id="ict_cyber", event_type="Business disruption and system failures",
        service_id="SVC-001", owner="Head of Payments Engineering",
        business_process="Card payment authorisation",
        cross_cutting=json.dumps(["IT and technology risk", "Change and transformation risk",
                                  "Payments operations"]),
        inherent_likelihood=4, inherent_impact=4,
        impact_financial=3, impact_customer=4, impact_operational=4,
        impact_regulatory=3, impact_reputational=3,
        residual_likelihood=3, residual_impact=2,
        residual_rationale="Assessor judgment after partial change-control failures; "
                           "not an automatic reduction from control count."),
    _risk_fields(
        id="RSK-002", title="Prolonged outage at a critical cloud hosting provider",
        description="The cloud provider hosting the payment platform suffers a "
                    "multi-hour regional outage.",
        cause="Provider infrastructure failure; concentration on one provider.",
        effect="Card payments and login unavailable until failover or recovery.",
        category_id="third_party", event_type="Business disruption and system failures",
        service_id="SVC-001", owner="Head of Third-Party Risk",
        business_process="Card payment authorisation",
        cross_cutting=json.dumps(["Third-party and outsourcing risk",
                                  "Operational resilience", "Payments operations"]),
        inherent_likelihood=3, inherent_impact=5,
        impact_financial=5, impact_customer=5, impact_operational=5,
        impact_regulatory=4, impact_reputational=4,
        residual_likelihood=1, residual_impact=4,
        residual_rationale="Assessor judgment considering monitoring and partial failover."),
    _risk_fields(
        id="RSK-003", title="Late or incomplete regulatory notification of a "
                            "technology incident",
        description="A reportable technology incident is not reported to the "
                    "supervisor within the required time.",
        cause="Unclear classification, no on-call compliance cover out of hours.",
        effect="Breach of reporting obligations; supervisory findings.",
        category_id="incident_reporting",
        event_type="Execution, delivery and process management",
        service_id=None, owner="Head of Operational Risk",
        business_process="Incident response and supervisory notification",
        cross_cutting=json.dumps(["IT and technology risk", "Cybersecurity"]),
        inherent_likelihood=3, inherent_impact=4,
        impact_financial=2, impact_customer=2, impact_operational=3,
        impact_regulatory=4, impact_reputational=3,
        residual_likelihood=3, residual_impact=4,
        residual_rationale="Notification control tested ineffective; residual kept near inherent."),
    _risk_fields(
        id="RSK-004", title="Data cannot be restored after a destructive cyber attack",
        description="Ransomware or a destructive attack corrupts production data and "
                    "backups cannot restore it within tolerance.",
        cause="Backups not isolated or not restore-tested.",
        effect="Extended outage; loss of transaction records.",
        category_id="op_resilience", event_type="Business disruption and system failures",
        service_id="SVC-001", owner="Chief Information Security Officer",
        business_process="Data backup and recovery",
        cross_cutting=json.dumps(["Cybersecurity", "Data management",
                                  "Operational resilience"]),
        inherent_likelihood=2, inherent_impact=5,
        impact_financial=5, impact_customer=5, impact_operational=5,
        impact_regulatory=4, impact_reputational=5,
        residual_likelihood=2, residual_impact=4,
        residual_rationale="Restore testing effective; residual impact reduced by assessor."),
    # Centrepiece RCSA demo risk (Feature / Part 8).
    _risk_fields(
        id="DEMO-RISK-001", title="Disruption of Payment Processing Services",
        description="A critical cloud service provider experiences a regional outage "
                    "that interrupts payment authorization and processing.",
        cause="Third-party infrastructure failure; single-region concentration; "
              "failed failover; inadequate recovery testing.",
        effect="Failed customer transactions; revenue disruption; service unavailability; "
               "customer dissatisfaction; potential regulatory reporting considerations.",
        category_id="third_party", event_type="Business disruption and system failures",
        service_id="SVC-001", owner="Head of Payments Operations",
        business_process="Card payment authorisation and settlement",
        cross_cutting=json.dumps(["Third-party and outsourcing risk",
                                  "Operational resilience", "Payments operations",
                                  "IT and technology risk"]),
        inherent_likelihood=4, inherent_impact=5,
        impact_financial=5, impact_customer=5, impact_operational=5,
        impact_regulatory=4, impact_reputational=4,
        residual_likelihood=3, residual_impact=4,
        residual_rationale="Hypothetical assessed residual with synthetic evidence of "
                           "partially effective failover testing. Not derived from control count.",
        residual_evidence="Synthetic failed recovery test CTT-DEMO-03: failover exceeded "
                          "RTO by 35 minutes; DNS runbook step missing."),
)

# (risk, directive, phrase that must appear in the obligation sentence, why it applies)
OBLIGATION_LINKS = (
    ("RSK-001", "IL-BOI-PC-364", "all changes are adequately tested in a test environment",
     "The risk materialises when a change reaches production untested."),
    ("RSK-001", "IL-BOI-PC-355", "Change control policy",
     "Changes to systems that support critical services need change control."),
    ("RSK-001", "IL-BOI-PC-350", "identification and assessment of the operational risk inherent",
     "Requires this risk to be identified and assessed."),
    ("RSK-002", "IL-BOI-PC-362", "cloud-computing service provider is accountable",
     "The bank stays accountable for its cloud provider's service."),
    ("RSK-002", "IL-BOI-PC-355", "test national and other scenarios",
     "Provider outage is a scenario that can affect critical services."),
    ("RSK-003", "IL-BOI-PC-366", "within two hours of identifying the incident",
     "Sets the initial reporting deadline this risk is about."),
    ("RSK-003", "IL-BOI-PC-366", "at least once daily",
     "Ongoing updates during an incident."),
    ("RSK-004", "IL-BOI-PC-357", "reconstructing information from backup copies",
     "Restoring data from backups is the control objective at stake."),
    ("RSK-004", "IL-BOI-PC-355", "data synchronization procedures",
     "Data at the recovery site must be accurate and up to date."),
    ("RSK-004", "IL-BOI-PC-350", "business resiliency and continuity plans",
     "Continuity plans must limit losses in severe disruption."),
)
NOTIFICATION_LINK = ("IL-BOI-PC-366", "within two hours of identifying the incident")

CONTROLS = (
    {"id": "CTL-001", "name": "Change approval and pre-release testing for payment services",
     "description": "Every production change is approved and passes tests in a test "
                    "environment before release.",
     "objective": "Prevent untested payment changes reaching production.",
     "library_id": "ICT-06", "type": "preventive", "nature": "hybrid",
     "frequency": "Each change", "owner": "Head of Payments Engineering",
     "business_process": "Change management"},
    {"id": "CTL-002", "name": "Automated rollback of failed payment releases",
     "description": "A release that breaks health checks is rolled back automatically.",
     "objective": "Limit customer impact when a release fails.",
     "library_id": "ICT-06", "type": "corrective", "nature": "automated",
     "frequency": "Each release", "owner": "SRE Lead",
     "business_process": "Change management"},
    {"id": "CTL-003", "name": "Failover testing for card payments",
     "description": "Failover to the second region is tested and timed against RTO.",
     "objective": "Prove recovery within impact tolerance.",
     "library_id": "RES-03", "type": "corrective", "nature": "manual",
     "frequency": "Semi-annually", "owner": "Head of Business Continuity",
     "business_process": "Business continuity"},
    {"id": "CTL-004", "name": "Cloud provider exit and substitution plan",
     "description": "A documented plan to move critical workloads off the provider.",
     "objective": "Reduce concentration on a single cloud provider.",
     "library_id": "TPR-05", "type": "corrective", "nature": "manual",
     "frequency": "Reviewed annually", "owner": "Head of Third-Party Risk",
     "business_process": "Third-party risk"},
    {"id": "CTL-005", "name": "Critical provider SLA monitoring",
     "description": "Provider availability and SLA breaches are monitored and "
                    "reviewed monthly.",
     "objective": "Detect third-party degradation early.",
     "library_id": "TPR-04", "type": "detective", "nature": "automated",
     "frequency": "Monthly", "owner": "Vendor Manager",
     "business_process": "Third-party risk"},
    {"id": "CTL-006", "name": "Regulatory incident notification procedure",
     "description": "Reportable incidents are classified and reported to the "
                    "supervisor by an on-call compliance officer.",
     "objective": "Meet supervisory notification timelines.",
     "library_id": "INC-02", "type": "preventive", "nature": "manual",
     "frequency": "Per incident", "owner": "Head of Compliance",
     "business_process": "Incident response"},
    {"id": "CTL-007", "name": "Isolated backups and restore testing",
     "description": "Immutable backups are kept off-network and full restores are "
                    "tested.", "objective": "Recover data within RPO/RTO.",
     "library_id": "ICT-05", "type": "corrective",
     "nature": "hybrid", "frequency": "Quarterly restore test",
     "owner": "Chief Information Security Officer",
     "business_process": "Data backup and recovery"},
    # DEMO-RISK-001 suggested controls (synthetic — do not assume any real firm has them)
    {"id": "CTL-DEMO-01", "name": "Multi-region resilience architecture (synthetic)",
     "description": "Payment authorisation active-active across two regions.",
     "objective": "Survive a single-region cloud outage.",
     "library_id": "RES-03", "type": "preventive", "nature": "automated",
     "frequency": "Continuous", "owner": "Head of Payments Engineering",
     "business_process": "Card payment authorisation and settlement"},
    {"id": "CTL-DEMO-02", "name": "Third-party service monitoring (synthetic)",
     "description": "Real-time health checks on the critical cloud provider.",
     "objective": "Detect provider degradation within minutes.",
     "library_id": "TPR-04", "type": "detective", "nature": "automated",
     "frequency": "Continuous", "owner": "Vendor Manager",
     "business_process": "Card payment authorisation and settlement"},
    {"id": "CTL-DEMO-03", "name": "Failover and recovery testing (synthetic)",
     "description": "Scheduled failover drills timed against impact tolerance.",
     "objective": "Prove failover meets RTO under severe but plausible scenarios.",
     "library_id": "RES-03", "type": "detective", "nature": "manual",
     "frequency": "Quarterly", "owner": "Head of Business Continuity",
     "business_process": "Card payment authorisation and settlement",
     "exceptions": "Last drill exceeded RTO; DNS step missing from runbook.",
     "remediation_status": "open"},
    {"id": "CTL-DEMO-04", "name": "Documented incident escalation (synthetic)",
     "description": "Escalation tree from detection to crisis management.",
     "objective": "Escalate P1 payment outages within 15 minutes.",
     "library_id": "INC-02", "type": "preventive", "nature": "manual",
     "frequency": "Per incident", "owner": "Head of Payments Operations",
     "business_process": "Incident response"},
    {"id": "CTL-DEMO-05", "name": "Business continuity exercises (synthetic)",
     "description": "Tabletop and technical exercises for payment disruption.",
     "objective": "Keep BCP current for payment processing disruption.",
     "library_id": "RES-01", "type": "detective", "nature": "manual",
     "frequency": "Semi-annually", "owner": "Head of Business Continuity",
     "business_process": "Business continuity"},
)

# (control, days ago, design, operating, findings)
TESTS = (
    ("CTL-001", 30, "effective", "partially_effective",
     "3 of 25 sampled changes had no record of test-environment sign-off."),
    ("CTL-002", 30, "effective", "effective", "Rollback worked in all sampled releases."),
    ("CTL-003", 45, "effective", "partially_effective",
     "Failover met RTO, but one manual step was not documented."),
    ("CTL-004", 200, "partially_effective", "not_tested",
     "Plan exists but has never been exercised."),
    ("CTL-005", 20, "effective", "effective", "Monthly reviews held and minuted."),
    ("CTL-006", 15, "effective", "ineffective",
     "INC-001's first report took 2 h 35 min against the internal 2 h target; "
     "no deputy on-call cover."),
    ("CTL-007", 60, "effective", "effective", "Full restore completed in 3 h."),
    ("CTL-DEMO-01", 40, "effective", "effective",
     "Synthetic: dual-region routing verified in lab."),
    ("CTL-DEMO-02", 10, "effective", "effective",
     "Synthetic: provider health checks alerted within 3 minutes."),
    ("CTL-DEMO-03", 25, "effective", "partially_effective",
     "Synthetic failed recovery test: failover completed 35 minutes after RTO; "
     "manual DNS step was not in the runbook. Documentation alone is not "
     "operating effectiveness."),
    ("CTL-DEMO-04", 18, "effective", "effective",
     "Synthetic: escalation tree exercised in tabletop."),
    ("CTL-DEMO-05", 90, "effective", "not_tested",
     "Synthetic: BCP exercise scheduled but not yet run this half-year."),
)

RISK_CONTROLS = (
    ("RSK-001", "CTL-001", "likelihood"), ("RSK-001", "CTL-002", "impact"),
    ("RSK-002", "CTL-005", "likelihood"), ("RSK-002", "CTL-003", "impact"),
    ("RSK-002", "CTL-004", "impact"),
    ("RSK-003", "CTL-006", "likelihood"),
    ("RSK-004", "CTL-007", "impact"), ("RSK-004", "CTL-003", "impact"),
    ("DEMO-RISK-001", "CTL-DEMO-01", "impact"),
    ("DEMO-RISK-001", "CTL-DEMO-02", "likelihood"),
    ("DEMO-RISK-001", "CTL-DEMO-03", "impact"),
    ("DEMO-RISK-001", "CTL-DEMO-04", "likelihood"),
    ("DEMO-RISK-001", "CTL-DEMO-05", "impact"),
)

# six monthly readings, oldest first
KRIS = (
    {"id": "KRI-001", "risk_id": "RSK-001", "name": "Failed change rate",
     "definition": "Share of production changes to payment services rolled back or "
                   "causing an incident.", "unit": "%", "direction": "higher_is_worse",
     "green_limit": 3, "amber_limit": 5, "frequency": "Monthly",
     "data_source": "Change management tool", "owner": "Head of Payments Engineering",
     "values": (2.1, 2.8, 3.4, 2.6, 4.2, 6.3)},
    {"id": "KRI-002", "risk_id": "RSK-002", "name": "Card authorisation availability",
     "definition": "Minutes card authorisation was available ÷ minutes in the month.",
     "unit": "%", "direction": "lower_is_worse", "green_limit": 99.9,
     "amber_limit": 99.5, "frequency": "Monthly", "data_source": "Monitoring platform",
     "owner": "Head of Payments Operations",
     "values": (99.95, 99.93, 99.96, 99.91, 99.94, 99.71)},
    {"id": "KRI-003", "risk_id": "RSK-002", "name": "Critical provider SLA breaches",
     "definition": "SLA breaches by critical providers in the month.", "unit": "count",
     "direction": "higher_is_worse", "green_limit": 0, "amber_limit": 1,
     "frequency": "Monthly", "data_source": "Vendor management register",
     "owner": "Vendor Manager", "values": (0, 0, 1, 0, 0, 0)},
    {"id": "KRI-004", "risk_id": "RSK-003", "name": "Time to first regulatory report",
     "definition": "Longest time in the month from classifying an incident as reportable "
                   "to the first report. Amber limit equals the deadline in the linked "
                   "notification obligation.", "unit": "minutes",
     "direction": "higher_is_worse", "green_limit": 60, "amber_limit": 120,
     "frequency": "Monthly", "data_source": "Incident tool", "owner": "Head of Compliance",
     "values": (45, 50, 38, 55, 70, 155)},
    {"id": "KRI-005", "risk_id": "RSK-004", "name": "Days since last full restore test",
     "definition": "Days since a full production restore was last tested successfully.",
     "unit": "days", "direction": "higher_is_worse", "green_limit": 90, "amber_limit": 180,
     "frequency": "Monthly", "data_source": "Backup platform",
     "owner": "Chief Information Security Officer",
     "values": (30, 60, 90, 120, 150, 45)},
)


def _iso(d: dt.datetime) -> str:
    return d.isoformat(timespec="minutes")


def _months(anchor: dt.date, n: int) -> list[str]:
    out, y, m = [], anchor.year, anchor.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def find_obligation(index_conn, document_id: str, phrase: str) -> dict | None:
    """The first obligation in `document_id` whose sentence contains `phrase`."""
    if index_conn is None:
        return None
    try:
        row = index_conn.execute(
            "SELECT okey FROM obligation WHERE document_id = ? AND "
            "LOWER(sentence) LIKE ? ORDER BY id LIMIT 1",
            (document_id, f"%{phrase.lower()}%")).fetchone()
    except Exception:
        return None
    return risk.obligation_citation(index_conn, row["okey"]) if row else None


def seed(conn, index_conn=None, *, today: dt.date | None = None) -> dict:
    """Load the demo once (again when SEED_VERSION changes and the store holds
    only demo rows). Returns what was linked and what was not found."""
    current = risk.get_meta(conn, "seed_version")
    if current == SEED_VERSION:
        return {"seeded": False, "linked": 0, "missing": []}
    if current:
        if _real_rows(conn):
            return {"seeded": False, "linked": 0, "missing": []}
        _wipe(conn, ACTOR)
    today = today or dt.date.today()
    base = dt.datetime.combine(today, dt.time(9, 0))
    syn = {"is_synthetic": 1, "provenance": "synthetic", "validation_status": "draft"}

    def add(table, row, **extra):
        risk.insert(conn, table, {**row, **extra}, actor=ACTOR)

    for s in SERVICES:
        row = {k: v for k, v in s.items() if k not in ("dependencies", "test_days_ago")}
        add("business_service", {**row, **syn,
                                 "dependencies": json.dumps(s["dependencies"]),
                                 "last_test_date": (today - dt.timedelta(
                                     days=s["test_days_ago"])).isoformat()})
    for cat, limit, statement in APPETITE:
        add("appetite", {"category_id": cat, "max_residual_score": limit,
                         "statement": statement, "approved_by": "Board Risk Committee",
                         "approved_at": (today - dt.timedelta(days=90)).isoformat(), **syn})
    for r in RISKS:
        add("risk", {**r, **syn,
                     "assessed_at": (today - dt.timedelta(days=14)).isoformat(),
                     "next_review_at": (today + dt.timedelta(days=76)).isoformat(),
                     "residual_approved_at": risk.now()})
    linked, missing = 0, []
    for risk_id, doc, phrase, why in OBLIGATION_LINKS:
        found = find_obligation(index_conn, doc, phrase)
        if not found:
            missing.append(f"{risk_id}: {doc} “{phrase}”")
            continue
        add("risk_obligation", {
            "risk_id": risk_id, "okey": found["okey"], "document_id": found["document_id"],
            "clause_ref": found["clause_ref"], "citation": found["citation"],
            "link": found["link"], "sentence": found["sentence"],
            "sentence_sha": risk.sentence_sha(found["sentence"]), "rationale": why,
            **syn, "validation_status": "suggested"})
        linked += 1
    for c in CONTROLS:
        add("control", {**c, **syn, "key_control": 1})
    for i, (cid, days, design, operating, findings) in enumerate(TESTS, 1):
        tid = f"CTT-DEMO-{i - 7:02d}" if cid.startswith("CTL-DEMO") else f"CTT-{i:03d}"
        add("control_test", {"id": tid, "control_id": cid,
                             "tested_at": (today - dt.timedelta(days=days)).isoformat(),
                             "tester": "Second line, Operational Risk",
                             "design_rating": design, "operating_rating": operating,
                             "findings": findings, "evidence_ref": f"Test file {tid}",
                             **syn})
    # Obligation link for the centrepiece demo risk (cloud accountability).
    demo_obl = find_obligation(index_conn, "IL-BOI-PC-362",
                               "cloud-computing service provider is accountable")
    if demo_obl:
        add("risk_obligation", {
            "risk_id": "DEMO-RISK-001", "okey": demo_obl["okey"],
            "document_id": demo_obl["document_id"], "clause_ref": demo_obl["clause_ref"],
            "citation": demo_obl["citation"], "link": demo_obl["link"],
            "sentence": demo_obl["sentence"],
            "sentence_sha": risk.sentence_sha(demo_obl["sentence"]),
            "rationale": "Cloud accountability underpins the payment-outage scenario.",
            **syn, "validation_status": "suggested"})
        linked += 1
    else:
        missing.append('DEMO-RISK-001: IL-BOI-PC-362 “cloud-computing service provider '
                       'is accountable”')
    demo_obl2 = find_obligation(index_conn, "IL-BOI-PC-355",
                                "test national and other scenarios")
    if demo_obl2:
        add("risk_obligation", {
            "risk_id": "DEMO-RISK-001", "okey": demo_obl2["okey"],
            "document_id": demo_obl2["document_id"], "clause_ref": demo_obl2["clause_ref"],
            "citation": demo_obl2["citation"], "link": demo_obl2["link"],
            "sentence": demo_obl2["sentence"],
            "sentence_sha": risk.sentence_sha(demo_obl2["sentence"]),
            "rationale": "Scenario testing of continuity arrangements.",
            **syn, "validation_status": "suggested"})
        linked += 1
    for risk_id, cid, reduces in RISK_CONTROLS:
        add("risk_control", {"risk_id": risk_id, "control_id": cid, "reduces": reduces})
    periods = _months(today.replace(day=1) - dt.timedelta(days=1), 6)
    for k in KRIS:
        add("kri", {key: v for key, v in k.items() if key != "values"} | syn)
        for period, value in zip(periods, k["values"]):
            add("kri_reading", {"kri_id": k["id"], "period": period, "value": value,
                                "entered_by": ACTOR, "entered_at": risk.now(),
                                "is_synthetic": 1})

    t0 = base - dt.timedelta(days=20) + dt.timedelta(minutes=12)
    add("incident", {
        "id": "INC-001", "title": "Card authorisations failed after a payment gateway release",
        "description": "A configuration change to the payment gateway rejected most card "
                       "authorisations until it was reverted.",
        "event_type": "Business disruption and system failures", "service_id": "SVC-001",
        "severity": "P1", "occurred_at": _iso(t0),
        "detected_at": _iso(t0 + dt.timedelta(minutes=7)),
        "escalated_at": _iso(t0 + dt.timedelta(minutes=19)),
        "regulator_notified_at": _iso(t0 + dt.timedelta(minutes=7 + 155)),
        "resolved_at": _iso(t0 + dt.timedelta(hours=4, minutes=25)),
        "customers_affected": 38400, "gross_loss": 186500, "recovered": 41200,
        "currency": CURRENCY, "status": "contained", "owner": "Head of Payments Operations",
        "root_cause": "Change released without test-environment sign-off; automated "
                      "rollback did not trigger because the health-check threshold was "
                      "set too loosely.", **syn})
    t1 = base - dt.timedelta(days=75)
    add("incident", {
        "id": "INC-002", "title": "Slow login during a cloud region degradation",
        "description": "Login latency rose for about 50 minutes during a provider "
                       "incident; no failed payments.",
        "event_type": "Business disruption and system failures", "service_id": "SVC-002",
        "severity": "P3", "occurred_at": _iso(t1),
        "detected_at": _iso(t1 + dt.timedelta(minutes=4)),
        "resolved_at": _iso(t1 + dt.timedelta(minutes=50)),
        "customers_affected": 5200, "gross_loss": 0, "recovered": 0, "currency": CURRENCY,
        "status": "closed", "owner": "Head of Customer Platform",
        "root_cause": "Provider-side network degradation in one region.", **syn})
    for inc, kind, target in (("INC-001", "risk", "RSK-001"), ("INC-001", "risk", "RSK-003"),
                              ("INC-001", "failed_control", "CTL-001"),
                              ("INC-001", "failed_control", "CTL-002"),
                              ("INC-001", "failed_control", "CTL-006"),
                              ("INC-002", "risk", "RSK-002")):
        add("incident_link", {"incident_id": inc, "kind": kind, "target_id": target})
    note = find_obligation(index_conn, *NOTIFICATION_LINK)
    if note:
        add("incident_link", {"incident_id": "INC-001", "kind": "notification_obligation",
                              "target_id": note["okey"]})

    def day(n):
        return (today + dt.timedelta(days=n)).isoformat()
    for a in (
        {"id": "ACT-001", "source_kind": "incident", "source_id": "INC-001",
         "title": "Make test-environment sign-off a hard gate for payment releases",
         "owner": "Head of Payments Engineering", "due_at": day(25), "status": "in_progress"},
        {"id": "ACT-002", "source_kind": "incident", "source_id": "INC-001",
         "title": "Fix the rollback health-check threshold and re-test it",
         "owner": "SRE Lead", "due_at": day(-5), "status": "open"},
        {"id": "ACT-003", "source_kind": "control_test", "source_id": "CTT-006",
         "title": "Add deputy compliance on-call and a reporting timer in the incident tool",
         "owner": "Head of Compliance", "due_at": day(10), "status": "open"},
        {"id": "ACT-004", "source_kind": "control_test", "source_id": "CTT-004",
         "title": "Run a tabletop exercise of the cloud exit plan",
         "owner": "Head of Third-Party Risk", "due_at": day(60), "status": "open"},
        {"id": "ACT-005", "source_kind": "control_test", "source_id": "CTT-003",
         "title": "Add the manual DNS step to the failover runbook",
         "owner": "Head of Business Continuity", "due_at": day(-20), "status": "done",
         "closed_at": day(-22), "closure_evidence": "Runbook v4.2"},
        {"id": "ACT-DEMO-01", "source_kind": "risk", "source_id": "DEMO-RISK-001",
         "title": "Re-run payment failover drill and fix the DNS runbook gap",
         "owner": "Head of Business Continuity", "due_at": day(14), "status": "open"},
        {"id": "ACT-DEMO-02", "source_kind": "control_test", "source_id": "CTT-DEMO-03",
         "title": "Document and retest the failed recovery scenario for DEMO-RISK-001",
         "owner": "Head of Payments Operations", "due_at": day(-2), "status": "open"},
    ):
        add("action", {**a, **syn})
    # KRI for the centrepiece demo risk
    add("kri", {"id": "KRI-DEMO-01", "risk_id": "DEMO-RISK-001",
                "name": "Payment authorisation success rate",
                "definition": "Successful card authorisations ÷ attempts (synthetic).",
                "unit": "%", "direction": "lower_is_worse", "green_limit": 99.9,
                "amber_limit": 99.5, "frequency": "Monthly",
                "data_source": "Synthetic monitoring", "owner": "Head of Payments Operations",
                **syn})
    for period, value in zip(periods, (99.96, 99.94, 99.95, 99.91, 99.88, 99.40)):
        add("kri_reading", {"kri_id": "KRI-DEMO-01", "period": period, "value": value,
                            "entered_by": ACTOR, "entered_at": risk.now(),
                            "is_synthetic": 1})

    risk.set_meta(conn, "dataset", "synthetic_demo")
    risk.set_meta(conn, "bank", BANK)
    risk.set_meta(conn, "seed_version", SEED_VERSION)
    risk.set_meta(conn, "seeded_at", risk.now())
    risk.set_meta(conn, "missing_links", json.dumps(missing, ensure_ascii=False))
    return {"seeded": True, "linked": linked, "missing": missing}


def _real_rows(conn) -> str | None:
    """The first table holding a row that is not synthetic, if any."""
    for table in risk.TABLES:
        if "is_synthetic" in risk._columns(conn, table) and conn.execute(
                f"SELECT 1 FROM {table} WHERE is_synthetic = 0 LIMIT 1").fetchone():
            return table
    return None


def _wipe(conn, actor: str) -> None:
    for table in reversed(risk.TABLES):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM meta WHERE key != 'dataset'")
    risk._log(conn, actor, "demo_reset", "meta", "dataset", None, {"at": risk.now()})


def reset(conn, index_conn=None, *, actor: str, today: dt.date | None = None) -> dict:
    """Wipe and re-load the demo. Refuses if the store holds any row that is
    not synthetic, so real work can never be lost this way."""
    table = _real_rows(conn)
    if table:
        raise PermissionError(
            f"The risk store holds non-synthetic rows in {table}; not resetting.")
    _wipe(conn, actor)
    return seed(conn, index_conn, today=today)
