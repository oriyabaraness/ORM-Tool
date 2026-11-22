"""Operational resilience: calculations, tolerances, dependencies, demo export."""
import datetime as dt
import json

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import resilience as rs, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


DEMO_DAY = dt.date(2026, 11, 22)


def _seed(conn):
    return rs.seed(conn, today=DEMO_DAY, force=True)


def test_scenario_calculations_and_units():
    # 100 minutes, 12_000 tx/h, 95% failure
    assert rs.outage_hours(100) == pytest.approx(100 / 60, rel=1e-4)
    attempted = rs.attempted_transactions(12_000, 100)
    assert attempted == pytest.approx(12_000 * (100 / 60), rel=1e-4)
    failed = rs.failed_transactions(12_000, 100, 95)
    assert failed == pytest.approx(attempted * 0.95, rel=1e-4)
    calc = rs.run_scenario_calc(
        duration_minutes=100, avg_tx_per_hour=12_000, failure_rate_pct=95,
        estimated_customers=42_000, impact_tolerance_hours=1.5, rto_hours=2.0)
    assert calc["inputs"]["input_kind"] == "assumption"
    assert "outage_hours" in calc["formulas"]
    assert calc["rto_achieved"] is True  # 1.666… h <= 2 h RTO
    assert calc["tolerance"]["status"] == "fail"  # 1.666 > 1.5
    assert "not a statistically calibrated" in calc["disclaimer"].lower()


def test_missing_values_and_undefined_tolerance():
    assert rs.outage_hours(None) is None
    assert rs.attempted_transactions(100, None) is None
    assert rs.failed_transactions(100, 60, None) is None
    tol = rs.tolerance_result(2.0, None)
    assert tol["status"] == "indeterminate"
    assert tol["label"] == "Impact tolerance not defined."
    assert tol["decision_required"] is True
    assert "Approved impact tolerance" in tol["missing_evidence"][0]
    tol2 = rs.tolerance_result(None, 1.5)
    assert tol2["status"] == "indeterminate"
    pass_ = rs.tolerance_result(1.0, 1.5)
    assert pass_["status"] == "pass"
    assert pass_["margin_hours"] == pytest.approx(0.5)


def test_sensitivity_to_assumptions():
    base = rs.failed_transactions(10_000, 60, 50)
    higher_rate = rs.failed_transactions(10_000, 60, 80)
    longer = rs.failed_transactions(10_000, 120, 50)
    assert higher_rate > base
    assert longer > base
    assert higher_rate == pytest.approx(8000)
    assert longer == pytest.approx(10000)


def test_cloud_demo_comparison_and_links():
    with risk.session() as conn:
        out = _seed(conn)
        assert out["seeded"] is True
        assert out["opt2_status"] == "pass"
        assert out["opt3_status"] == "fail"
        d = rs.scenario_detail(conn, "SCN-DEMO-CLOUD")
        scn = d["scenario"]
        assert scn["duration_minutes"] == 100
        assert scn["linked_risk_id"] == "DEMO-RISK-001"
        assert "SVC-001" in json.loads(scn["affected_services_json"])
        assert "CTL-DEMO-03" in json.loads(scn["linked_control_ids_json"])
        assert len(d["comparisons"]) == 3
        opt2 = d["comparisons"][1]
        opt3 = d["comparisons"][2]
        assert int(opt2["option"]["control_tested"]) == 1
        assert opt2["calc"]["tolerance"]["status"] == "pass"
        assert opt3["option"]["unresolved_deficiency"]
        assert opt3["calc"]["tolerance"]["status"] == "fail"
        # 100 min baseline failed tx
        assert d["base_calc"]["failed_transactions"] == pytest.approx(
            12_000 * (100 / 60) * 0.95, rel=1e-4)


def test_ibs_designation_is_selective():
    with risk.session() as conn:
        _seed(conn)
        svcs = rs.services(conn).set_index("id")
        assert int(svcs.loc["SVC-001", "is_ibs"]) == 1
        assert int(svcs.loc["SVC-002", "is_ibs"]) == 0
        assert "SVC-003" in svcs.index
        assert int(svcs.loc["SVC-003", "is_ibs"]) == 0
        bia3 = dict(conn.execute(
            "SELECT * FROM service_bia WHERE service_id='SVC-003'").fetchone())
        assert bia3["impact_tolerance_hours"] is None
        calc = rs.run_scenario_calc(
            duration_minutes=60, avg_tx_per_hour=10, failure_rate_pct=10,
            estimated_customers=1, impact_tolerance_hours=bia3["impact_tolerance_hours"])
        assert calc["tolerance"]["label"] == "Impact tolerance not defined."


def test_service_dependency_links_and_flags():
    with risk.session() as conn:
        _seed(conn)
        deps = risk._df(conn, "SELECT * FROM service_dependency WHERE service_id='SVC-001'")
        layers = set(deps["layer"])
        assert {"process", "application", "infrastructure",
                "third_party", "recovery"} <= layers
        flags = rs.concentration_flags(conn)
        kinds = set(flags["kind"]) if not flags.empty else set()
        assert "shared_provider_concentration" in kinds
        assert "no_documented_alternative" in kinds
        assert "unresolved_spof" in kinds
        assert flags["requires_validation"].all()
        assert (flags["certainty"] == "hypothesis").all()
        graph = rs.dependency_graph_mermaid(conn, "SVC-001")
        assert "SVC-001" in graph
        assert "flowchart" in graph


def test_bia_keeps_rto_rpo_tolerance_separate():
    with risk.session() as conn:
        _seed(conn)
        bia = dict(conn.execute(
            "SELECT * FROM service_bia WHERE service_id='SVC-001'").fetchone())
        assert bia["rto_hours"] == 2.0
        assert bia["rpo_hours"] == 0.25
        assert bia["impact_tolerance_hours"] == 1.5
        assert bia["rto_hours"] != bia["impact_tolerance_hours"]
        assert "separate" in (bia["impact_tolerance_basis"] or "").lower() or \
            "separate" in (bia["assumptions_note"] or "").lower()


def test_management_summary_and_export():
    with risk.session() as conn:
        _seed(conn)
        summary = rs.management_summary(conn, "SCN-DEMO-CLOUD")
        assert summary["linked_risk_id"] == "DEMO-RISK-001"
        assert summary["pass_option"] is not None
        assert summary["fail_option"] is not None
        assert "tested capability" in summary["headline"].lower()
        text = rs.export_summary_text(summary)
        assert "DEMO-RISK-001" in text
        assert "Option 2" in text or "Multi-region failover, successfully tested" in text
        detail = rs.scenario_detail(conn, "SCN-DEMO-CLOUD")
        csv_bytes = rs.export_scenario_csv(detail)
        decoded = csv_bytes.decode("utf-8")
        assert "failed_transactions" in decoded
        assert "OPT2_tolerance" in decoded
        assert "pass" in decoded and "fail" in decoded


def test_custom_scenario_and_templates():
    with risk.session() as conn:
        _seed(conn)
        scns = rs.scenarios(conn)
        codes = set(scns["code"])
        assert {"A", "B", "C", "D", "E"} <= codes
        row = rs.create_custom_scenario(
            conn, name="User flood test", duration_minutes=30,
            avg_tx_per_hour=500, failure_rate_pct=10,
            service_ids=["SVC-001"], actor="tester")
        assert row["scenario_type"] == "custom"
        d = rs.scenario_detail(conn, row["id"])
        assert d["base_calc"]["outage_hours"] == 0.5


def test_idempotent_seed():
    with risk.session() as conn:
        assert _seed(conn)["seeded"] is True
        assert rs.seed(conn, today=DEMO_DAY, force=False)["seeded"] is False
        assert rs.seed(conn, today=DEMO_DAY, force=True)["seeded"] is True
