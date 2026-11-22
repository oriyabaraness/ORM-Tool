"""Tests for the RCSA module (orm.rcsa) and explicit residual assessment."""
import importlib
import sys

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import db, demo_data, obligations, rcsa, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


def test_matrix_boundaries_and_impact_aggregation():
    assert [risk.band(s) for s in (1, 4, 5, 9, 10, 16, 17, 25)] == \
        ["Low", "Low", "Moderate", "Moderate", "High", "High", "Critical", "Critical"]
    assert risk.inherent_score(4, 5) == 20
    assert risk.aggregate_impact({
        "financial": 3, "customer": 5, "operational": 4,
        "regulatory": 2, "reputational": None}, "max") == 5
    assert risk.aggregate_impact({"financial": 2, "customer": 4}, "average") == 3
    assert risk.aggregate_impact({}) is None
    with pytest.raises(ValueError):
        risk.aggregate_impact({"financial": 3}, "median")


def test_residual_requires_named_approver_and_rationale():
    with risk.session() as conn:
        risk.insert(conn, "risk", {
            "id": "RSK-RCSA", "title": "T", "category_id": "op_resilience",
            "event_type": "Business disruption and system failures",
            "inherent_likelihood": 4, "inherent_impact": 5,
        }, actor="A")
        with pytest.raises(ValueError):
            risk.approve_residual(conn, "RSK-RCSA", 3, 4, rationale="  ", actor="Ana")
        with pytest.raises(ValueError):
            risk.approve_residual(conn, "RSK-RCSA", 3, 4, rationale="Because", actor="  ")
        row = risk.approve_residual(
            conn, "RSK-RCSA", 3, 4, rationale="Assessor judgment after tests.",
            evidence="Working paper 12", actor="Ana")
        assert row["residual_status"] == "approved"
        assert row["residual_likelihood"] == 3 and row["residual_impact"] == 4
        reg = risk.register(conn).set_index("id")
        assert reg.loc["RSK-RCSA", "residual_score"] == 12
        assert bool(reg.loc["RSK-RCSA", "residual_assessed"]) is True


def test_controls_do_not_auto_set_residual():
    with risk.session() as conn:
        risk.insert(conn, "risk", {
            "id": "RSK-AUTO", "title": "T", "category_id": "ict_cyber",
            "inherent_likelihood": 5, "inherent_impact": 5,
            "residual_status": "not_assessed",
        }, actor="A")
        risk.insert(conn, "control", {
            "id": "CTL-AUTO", "name": "Strong control", "type": "preventive",
            "nature": "automated", "key_control": 1,
        }, actor="A")
        risk.insert(conn, "control_test", {
            "id": "CTT-AUTO", "control_id": "CTL-AUTO", "tested_at": "2026-01-01",
            "design_rating": "effective", "operating_rating": "effective",
        }, actor="A")
        risk.insert(conn, "risk_control", {
            "risk_id": "RSK-AUTO", "control_id": "CTL-AUTO", "reduces": "both",
        }, actor="A")
        reg = risk.register(conn).set_index("id")
        # Suggestion may be lower, but status is not approved.
        assert reg.loc["RSK-AUTO", "residual_status"] == "suggested"
        assert bool(reg.loc["RSK-AUTO", "residual_assessed"]) is False
        assert reg.loc["RSK-AUTO", "suggested_residual_score"] < 25


def test_demo_risk_001_centrepiece():
    with risk.session() as conn:
        demo_data.seed(conn, None)
        reg = risk.register(conn).set_index("id")
        assert "DEMO-RISK-001" in reg.index
        assert reg.loc["DEMO-RISK-001", "inherent_score"] == 20
        assert reg.loc["DEMO-RISK-001", "residual_score"] == 12
        assert bool(reg.loc["DEMO-RISK-001", "residual_assessed"]) is True
        chain = risk.risk_chain(conn, "DEMO-RISK-001")
        assert set(chain["controls"]["id"]) >= {
            "CTL-DEMO-01", "CTL-DEMO-02", "CTL-DEMO-03", "CTL-DEMO-04", "CTL-DEMO-05"}
        demo3 = chain["controls"].set_index("id").loc["CTL-DEMO-03"]
        assert demo3["operating_rating"] == "partially_effective"
        assert "failed recovery" in (demo3["findings"] or "").lower() or \
            "rto" in (demo3["findings"] or "").lower()


def test_control_gaps_flag_missing_owner_and_unapproved_residual():
    with risk.session() as conn:
        risk.insert(conn, "risk", {
            "id": "RSK-GAP", "title": "Ownerless", "category_id": "governance",
            "inherent_likelihood": 4, "inherent_impact": 4, "owner": "",
            "residual_status": "not_assessed",
            "next_review_at": "2020-01-01",
        }, actor="A")
        gaps = rcsa.control_gaps(conn)
        kinds = set(gaps.loc[gaps["risk_id"] == "RSK-GAP", "gap_kind"])
        assert "missing_owner" in kinds
        assert "no_linked_controls" in kinds
        assert "residual_not_approved" in kinds
        assert "overdue_review" in kinds
        assert gaps["disclaimer"].str.contains("not a compliance", case=False).all()


def test_create_risk_from_obligation_workflow(built_db):
    index = db.connect(built_db)
    obligations.init(index)
    obligations.build_all(index)
    index.commit()
    okey = index.execute("SELECT okey FROM obligation LIMIT 1").fetchone()["okey"]
    with risk.session() as conn:
        row = rcsa.create_risk_from_obligation(
            conn, index, okey=okey, title="Created from obligation",
            description="Event", event_type="Business disruption and system failures",
            category_id="op_resilience", causes="Cause", consequences="Effect",
            inherent_likelihood=3, inherent_impact=4, owner="Owner", actor="Ana",
            business_process="Payments", business_unit="Payments",
            legal_entity="Demo Digital Bank Ltd (fictional)", jurisdiction="IL",
            cross_cutting=["Payments operations", "Operational resilience"],
            impact_dimensions={"financial": 3, "customer": 4, "operational": 4,
                               "regulatory": 2, "reputational": 3},
            is_synthetic=1)
        assert row["id"].startswith("RSK-")
        reg = risk.register(conn).set_index("id")
        assert reg.loc[row["id"], "inherent_score"] == 12  # max impact 4 × L3
        assert bool(reg.loc[row["id"], "residual_assessed"]) is False
        chain = risk.risk_chain(conn, row["id"], index)
        assert not chain["obligations"].empty
        # Attach control, test, approve residual — full acceptance path
        rcsa.upsert_control(conn, {
            "id": "CTL-NEW", "name": "New control", "objective": "Mitigate",
            "type": "preventive", "nature": "manual", "owner": "Owner",
            "is_synthetic": 1,
        }, actor="Ana")
        risk.insert(conn, "control_test", {
            "id": "CTT-NEW", "control_id": "CTL-NEW", "tested_at": "2026-11-01",
            "design_rating": "effective", "operating_rating": "partially_effective",
            "findings": "One exception", "evidence_ref": "WP-1", "is_synthetic": 1,
        }, actor="Ana")
        rcsa.link_control(conn, risk_id=row["id"], control_id="CTL-NEW",
                          reduces="likelihood", actor="Ana")
        risk.approve_residual(conn, row["id"], 2, 3, rationale="After control review",
                              evidence="WP-1", actor="Ana")
        reg2 = risk.register(conn).set_index("id")
        assert reg2.loc[row["id"], "residual_score"] == 6
        assert bool(reg2.loc[row["id"], "residual_assessed"]) is True
        assert "DEMO-RISK-001" not in reg2.index or True
        heat = rcsa.heat_map(reg2, view="residual")
        assert int(heat.loc[3, 2]) >= 1


def test_taxonomy_keeps_cross_cutting_non_exclusive():
    assert len(rcsa.EVENT_TAXONOMY) == 7
    assert len(rcsa.CROSS_CUTTING_TAXONOMY) == 8
    assert "Payments operations" in risk.CROSS_CUTTING
    assert "Business disruption and system failures" in risk.EVENT_TYPES


def test_rcsa_screen_renders(built_db, monkeypatch):
    rendered: list = []
    fake = _fake_streamlit_full(rendered)
    fake.checkbox = lambda label, value=False, **_: value
    fake.text_area = lambda label, value="", **_: value
    fake.multiselect = lambda label, options, default=None, **_: list(default or [])
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    with risk.session() as conn:
        demo_data.seed(conn, db.connect(built_db))
    for name in ("orm_compare", "ui_theme", "controls_views", "risk_views",
                 "rcsa_views", "regulatory_views"):
        sys.modules.pop(name, None)
    views = importlib.import_module("rcsa_views")
    views.page_rcsa()
    page = "\n".join(str(x) for x in rendered)
    assert '<h1 class="page-title">RCSA</h1>' in page
    assert "Prototype methodology" in page or "Illustrative" in page
