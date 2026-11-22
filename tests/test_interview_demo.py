"""Interview demonstration front page — responsibility map integrity."""
from orm import interview_demo as ix


# Exact LinkedIn posting wording (must not drift).
EXPECTED = [
    "Building and optimising local risk management frameworks and processes",
    "Developing and maintaining risk tools and IT systems",
    "Identifying and assessing a range of risks, including IT Risk",
    "Guiding teams to design and implement effective controls",
    "Supporting the development and implementation of operational risk policies and procedures",
    "Contributing to the definition of key indicators and the risk appetite statement",
    "Developing techniques for quantification of operational risk and resilience, including stress testing and impact tolerances",
    "Managing the risk incident process and ensuring accurate recording of events, including preparing and handling of incident reports",
    "Monitoring operational risk against defined limits and thresholds, and coordinating resolutions with risk stakeholders",
    "Producing risk reports for management and relevant stakeholders",
    "Conducting presentations and workshops on risk identification and mitigation",
]

# Real app.py page keys — destinations must exist.
KNOWN_PAGES = {
    "interview", "overview", "home", "compare", "coverage", "gaps", "deadlines",
    "changes", "obligations", "controls", "audit", "risks", "rcsa", "kri",
    "incidents", "resilience", "risk_report", "executive", "regulatory",
    "change_impact", "sources",
}


def test_eleven_responsibilities_exact_wording():
    assert len(ix.RESPONSIBILITIES) == 11
    texts = [r["text"] for r in ix.RESPONSIBILITIES]
    assert texts == EXPECTED
    ids = [r["id"] for r in ix.RESPONSIBILITIES]
    assert ids == [f"R{i:02d}" for i in range(1, 12)]


def test_every_destination_is_a_real_page_key():
    for r in ix.RESPONSIBILITIES:
        assert r["page_key"] in KNOWN_PAGES, r
        assert r["capability"] and r["focus"]
    for s in ix.GUIDE_STEPS:
        assert s["page_key"] in KNOWN_PAGES


def test_disclaimer_denies_revolut_affiliation():
    low = ix.DISCLAIMER.lower()
    assert "not" in low and "revolut" in low
    assert "affiliated" in low or "endorsed" in low


def test_guide_is_six_payment_steps():
    assert len(ix.GUIDE_STEPS) == 6
    assert [s["page_key"] for s in ix.GUIDE_STEPS] == [
        "regulatory", "risks", "rcsa", "kri", "incidents", "executive"]


def test_workflow_chain():
    assert ix.WORKFLOW == [
        "Regulatory Obligation", "Operational Risk", "Control",
        "KRI", "Incident", "Management Decision",
    ]
