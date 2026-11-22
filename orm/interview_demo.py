"""Interview demonstration map — Revolut ORM job responsibilities → ClauseWiz routes.

Exact responsibility wording is taken from the public LinkedIn job posting
(Operational Risk Manager · Revolut · Israel). ClauseWiz is not affiliated with
Revolut; destinations use synthetic demo data when Demo Mode is on.
"""
from __future__ import annotations

from typing import Any

# Exact strings from:
# https://www.linkedin.com/jobs/view/operational-risk-manager-at-revolut-4489580385/
RESPONSIBILITIES: list[dict[str, Any]] = [
    {
        "id": "R01",
        "text": (
            "Building and optimising local risk management frameworks and processes"
        ),
        "page_key": "risks",
        "capability": "Risk Register · taxonomy, appetite, governance",
        "focus": (
            "Risk taxonomy, assessment methodology, ownership, inherent / residual "
            "scores, and appetite status on the register."
        ),
        "anchor": "register",
    },
    {
        "id": "R02",
        "text": "Developing and maintaining risk tools and IT systems",
        "page_key": "overview",
        "capability": "Risk Overview · connected platform",
        "focus": (
            "Executive metrics, residual heat map, attention queue, KRI and "
            "regulatory strips — the connected risk data architecture."
        ),
        "anchor": "kpis",
    },
    {
        "id": "R03",
        "text": "Identifying and assessing a range of risks, including IT Risk",
        "page_key": "risks",
        "capability": "Risk Register · IT & operational risk",
        "focus": (
            "Open risks including technology / third-party dependency themes, "
            "inherent vs residual ratings, and the residual heat map."
        ),
        "anchor": "heatmap",
        "prefer_risk_id": "DEMO-RISK-001",
    },
    {
        "id": "R04",
        "text": "Guiding teams to design and implement effective controls",
        "page_key": "controls",
        "capability": "Controls · design & operating effectiveness",
        "focus": (
            "Control library with objectives, testing, effectiveness ratings, "
            "weaknesses, evidence and ownership."
        ),
        "anchor": "library",
    },
    {
        "id": "R05",
        "text": (
            "Supporting the development and implementation of operational risk "
            "policies and procedures"
        ),
        "page_key": "regulatory",
        "capability": "Regulatory Intelligence · obligation → policy",
        "focus": (
            "Sourced obligations, applicability, and regulation-to-risk mapping "
            "with citation traceability."
        ),
        "anchor": "obligations",
    },
    {
        "id": "R06",
        "text": (
            "Contributing to the definition of key indicators and the risk "
            "appetite statement"
        ),
        "page_key": "kri",
        "capability": "KRI Monitoring · appetite & thresholds",
        "focus": (
            "KRI catalogue, calculation notes, appetite statements, warning and "
            "breach thresholds, and observation trends."
        ),
        "anchor": "library",
        "prefer_kri_id": "KRI-PAY-FAIL",
    },
    {
        "id": "R07",
        "text": (
            "Developing techniques for quantification of operational risk and "
            "resilience, including stress testing and impact tolerances"
        ),
        "page_key": "resilience",
        "capability": "Operational Resilience · scenarios & tolerances",
        "focus": (
            "Important business services, dependencies, BIA, impact tolerances, "
            "and severe-but-plausible scenario analysis."
        ),
        "anchor": "scenarios",
    },
    {
        "id": "R08",
        "text": (
            "Managing the risk incident process and ensuring accurate recording "
            "of events, including preparing and handling of incident reports"
        ),
        "page_key": "incidents",
        "capability": "Incident Management · lifecycle & RCA",
        "focus": (
            "Incident register, severity, timelines, root-cause analysis, "
            "reporting assessment, and corrective actions."
        ),
        "anchor": "register",
        "prefer_incident_id": "INC-DEMO-CLOUD",
    },
    {
        "id": "R09",
        "text": (
            "Monitoring operational risk against defined limits and thresholds, "
            "and coordinating resolutions with risk stakeholders"
        ),
        "page_key": "kri",
        "capability": "KRI Monitoring · breaches & escalation",
        "focus": (
            "Limit / threshold monitoring, Red/Amber breaches, accountable "
            "owners, escalations and remediation coordination."
        ),
        "anchor": "breaches",
        "prefer_kri_id": "KRI-PAY-FAIL",
    },
    {
        "id": "R10",
        "text": "Producing risk reports for management and relevant stakeholders",
        "page_key": "executive",
        "capability": "Executive report · management pack",
        "focus": (
            "Period-filtered executive summary separating FACTS, ANALYSIS and "
            "RECOMMENDATIONS with exportable evidence links."
        ),
        "anchor": "pack",
    },
    {
        "id": "R11",
        "text": (
            "Conducting presentations and workshops on risk identification "
            "and mitigation"
        ),
        "page_key": "rcsa",
        "capability": "RCSA · workshop-style assessment",
        "focus": (
            "Structured residual assessment, control gaps, collaborative review "
            "of DEMO-RISK-001, and explicit residual approval — workshop mode."
        ),
        "anchor": "workshop",
        "prefer_risk_id": "DEMO-RISK-001",
    },
]

# Six-step payment-disruption walkthrough (~5 minutes).
GUIDE_STEPS: list[dict[str, Any]] = [
    {
        "step": 1,
        "title": "Regulatory requirement",
        "explain": (
            "Start from a sourced continuity obligation that underpins the "
            "payment-disruption risk."
        ),
        "page_key": "regulatory",
        "focus": "Obligation explorer · Directive / continuity citations.",
        "resp_id": "R05",
    },
    {
        "step": 2,
        "title": "Operational risk identification",
        "explain": (
            "Open DEMO-RISK-001 — payment authorisation disruption after a "
            "change — with inherent and residual ratings."
        ),
        "page_key": "risks",
        "focus": "DEMO-RISK-001 · IT / third-party dependency risk.",
        "resp_id": "R03",
        "prefer_risk_id": "DEMO-RISK-001",
    },
    {
        "step": 3,
        "title": "Risk and control assessment",
        "explain": (
            "RCSA shows residual judgement, control gaps, and workshop-style "
            "assessment — not auto-scored from controls alone."
        ),
        "page_key": "rcsa",
        "focus": "DEMO-RISK-001 residual approval and control gaps.",
        "resp_id": "R11",
        "prefer_risk_id": "DEMO-RISK-001",
    },
    {
        "step": 4,
        "title": "KRI threshold breach",
        "explain": (
            "Payment-failure KRI moves to Red against appetite thresholds."
        ),
        "page_key": "kri",
        "focus": "KRI-PAY-FAIL · warning and breach thresholds.",
        "resp_id": "R06",
        "prefer_kri_id": "KRI-PAY-FAIL",
    },
    {
        "step": 5,
        "title": "Operational incident",
        "explain": (
            "INC-DEMO-CLOUD records the disruption timeline, severity, RCA and "
            "corrective actions."
        ),
        "page_key": "incidents",
        "focus": "INC-DEMO-CLOUD · 100-minute cloud disruption story.",
        "resp_id": "R08",
        "prefer_incident_id": "INC-DEMO-CLOUD",
    },
    {
        "step": 6,
        "title": "Management reporting",
        "explain": (
            "Executive pack summarises exposure, the incident, and recommended "
            "actions with FACTS / ANALYSIS / RECOMMENDATIONS labelled."
        ),
        "page_key": "executive",
        "focus": "Executive report · committee-ready narrative.",
        "resp_id": "R10",
    },
]

WORKFLOW = [
    "Regulatory Obligation",
    "Operational Risk",
    "Control",
    "KRI",
    "Incident",
    "Management Decision",
]

DISCLAIMER = (
    "Interactive product demonstration for an operational risk management "
    "interview. ClauseWiz is an independent platform and is not developed by, "
    "endorsed by, or affiliated with Revolut. Synthetic demo records are labelled."
)


def by_id(resp_id: str) -> dict[str, Any] | None:
    for r in RESPONSIBILITIES:
        if r["id"] == resp_id:
            return r
    return None


def destination_pages() -> set[str]:
    return {r["page_key"] for r in RESPONSIBILITIES} | {
        s["page_key"] for s in GUIDE_STEPS
    }
