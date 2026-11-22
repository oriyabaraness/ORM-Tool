"""Incident lifecycle, timings, links, remediation, loss and audit tests."""
import datetime as dt
import json

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import incident_mgmt as im, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


DEMO_DAY = dt.date(2026, 11, 22)


def _seed(conn, index=None):
    return im.seed(conn, index, today=DEMO_DAY, force=True)


def test_cloud_demo_timings_and_labels():
    with risk.session() as conn:
        out = _seed(conn)
        assert out["seeded"] is True
        t = out["timing"]
        assert t["detection_delay_min"] == 5.0
        assert t["time_to_escalation_min"] == 3.0
        assert t["disruption_duration_min"] == 100.0
        assert t["recovery_duration_min"] == 75.0
        inc = dict(conn.execute(
            "SELECT * FROM incident WHERE id='INC-DEMO-CLOUD'").fetchone())
        assert inc["is_synthetic"] == 1
        assert "synthetic" in (inc["description"] or "").lower() or \
            "Synthetic" in im.NOTICE
        assert inc["severity"] == "P1"
        assert "illustrative" in (inc["severity_rationale"] or "").lower()
        assert im.current_status(inc) == "post_incident_review"


def test_incident_links_chain():
    with risk.session() as conn:
        _seed(conn)
        links = {(r["kind"], r["target_id"]) for r in conn.execute(
            "SELECT kind, target_id FROM incident_link WHERE incident_id=?",
            ("INC-DEMO-CLOUD",))}
        assert ("risk", "DEMO-RISK-001") in links
        assert ("failed_control", "CTL-DEMO-03") in links
        assert ("kri_breach", "KRI-PAY-FAIL") in links
        acts = risk.actions(conn)
        rem = acts[(acts["source_kind"] == "incident")
                   & (acts["source_id"] == "INC-DEMO-CLOUD")]
        assert not rem.empty
        row = rem.iloc[0]
        assert row["related_risk_id"] == "DEMO-RISK-001"
        assert "CTL-DEMO-03" in (row["control_deficiency"] or "")
        assert row["validation_outcome"] == "pending"


def test_state_transitions_and_reopen():
    with risk.session() as conn:
        risk.insert(conn, "incident", {
            "id": "INC-TEST-WF",
            "title": "Workflow unit test",
            "description": "Synthetic",
            "workflow_status": "detected",
            "status": "open",
            "severity": "P3",
            "occurred_at": "2026-11-22T09:00:00+00:00",
            "detected_at": "2026-11-22T09:05:00+00:00",
            "is_synthetic": 1,
            "provenance": "synthetic",
        }, actor="tester")
        im.transition(conn, "INC-TEST-WF", "triaged", actor="Alice",
                      note="triage", at="2026-11-22T09:08:00+00:00")
        im.transition(conn, "INC-TEST-WF", "investigating", actor="Alice")
        im.transition(conn, "INC-TEST-WF", "contained", actor="Bob")
        im.transition(conn, "INC-TEST-WF", "recovering", actor="Bob")
        im.transition(conn, "INC-TEST-WF", "resolved", actor="Bob")
        im.transition(conn, "INC-TEST-WF", "post_incident_review", actor="Carol")
        im.transition(conn, "INC-TEST-WF", "closed", actor="Carol")
        row = dict(conn.execute(
            "SELECT * FROM incident WHERE id='INC-TEST-WF'").fetchone())
        assert row["workflow_status"] == "closed"
        assert row["status"] == "closed"
        assert row["closed_at"]
        # Illegal skip
        with pytest.raises(ValueError):
            im.transition(conn, "INC-TEST-WF", "detected", actor="Eve")
        # Reopen
        im.transition(conn, "INC-TEST-WF", "investigating", actor="Carol",
                      note="reopen for new evidence")
        row = dict(conn.execute(
            "SELECT * FROM incident WHERE id='INC-TEST-WF'").fetchone())
        assert row["workflow_status"] == "investigating"
        tr = im.transitions(conn, "INC-TEST-WF")
        assert not tr.empty
        reopen = tr[tr["note"].astype(str).str.contains("reopen", case=False)]
        assert not reopen.empty
        assert reopen.iloc[-1]["actor"] == "Carol"
        assert reopen.iloc[-1]["to_status"] == "investigating"
        # Actor required
        with pytest.raises(ValueError):
            im.transition(conn, "INC-TEST-WF", "contained", actor="  ")


def test_timestamp_calculations_and_missing_data():
    assert im.minutes_between("2026-11-22T09:00:00+00:00",
                              "2026-11-22T09:05:00+00:00") == 5.0
    assert im.minutes_between("2026-11-22T09:00:00Z",
                              "2026-11-22T10:40:00+00:00") == 100.0
    assert im.minutes_between(None, "2026-11-22T09:05:00+00:00") is None
    assert im.minutes_between("2026-11-22T09:00:00+00:00", None) is None
    assert im.minutes_between("", "") is None
    metrics = im.timing_metrics({
        "occurred_at": "2026-11-22T09:00:00+00:00",
        "detected_at": None,
        "escalated_at": "2026-11-22T09:08:00+00:00",
        "recovery_started_at": "2026-11-22T09:25:00+00:00",
        "restored_at": None,
        "resolved_at": "2026-11-22T10:40:00+00:00",
    })
    assert metrics["detection_delay_min"] is None
    assert metrics["disruption_duration_min"] == 100.0
    assert metrics["recovery_duration_min"] == 75.0


def test_loss_calculations_and_zero_loss_incident():
    assert im.net_loss(95000, 12000) == 83000
    assert im.net_loss(None, None) == 0.0
    with risk.session() as conn:
        risk.insert(conn, "incident", {
            "id": "INC-ZERO-LOSS",
            "title": "No financial loss",
            "description": "Impact was operational only",
            "workflow_status": "resolved",
            "status": "contained",
            "severity": "P4",
            "gross_loss": 0,
            "recovered": 0,
            "is_synthetic": 1,
        }, actor="tester")
        # Zero loss events is valid
        d = im.detail(conn, "INC-ZERO-LOSS")
        assert d["losses"].empty
        loss = im.add_loss(conn, "INC-ZERO-LOSS", gross=0, recovered=0,
                           certainty="confirmed", actor="tester")
        assert loss["gross_loss"] == 0
        with pytest.raises(ValueError):
            im.add_loss(conn, "INC-ZERO-LOSS", gross=1, certainty="invented")


def test_remediation_deadline_and_validation_split():
    with risk.session() as conn:
        _seed(conn)
        acts = risk.actions(conn)
        rem = acts[(acts["source_kind"] == "incident")
                   & (acts["source_id"] == "INC-DEMO-CLOUD")].iloc[0]
        aid = rem["id"]
        # Owner complete ≠ validated
        im.mark_owner_complete(conn, aid, owner="Head of Business Continuity",
                               evidence="draft runbook")
        row = dict(conn.execute("SELECT * FROM action WHERE id=?", (aid,)).fetchone())
        assert row["status"] == "done"
        assert row["validation_outcome"] == "pending"
        assert not row.get("closure_reviewer")
        # Independent validation
        im.validate_action_closure(
            conn, aid, outcome="validated", reviewer="ORM Second Line",
            evidence="Test evidence pack")
        row = dict(conn.execute("SELECT * FROM action WHERE id=?", (aid,)).fetchone())
        assert row["validation_outcome"] == "validated"
        assert row["closure_reviewer"] == "ORM Second Line"
        # Rejection reopens
        aid2 = im.create_remediation(
            conn, incident_id="INC-DEMO-CLOUD", title="Follow-up",
            owner="Ops", due_at="2026-01-01", actor="tester")["id"]
        im.mark_owner_complete(conn, aid2, owner="Ops")
        im.validate_action_closure(conn, aid2, outcome="rejected",
                                   reviewer="ORM Second Line")
        row = dict(conn.execute("SELECT * FROM action WHERE id=?", (aid2,)).fetchone())
        assert row["status"] == "open"
        assert row["validation_outcome"] == "rejected"
        # Overdue detection
        overdue = risk.actions(conn, today="2026-12-31")
        assert bool(overdue[overdue["id"] == aid2].iloc[0]["overdue"])


def test_rca_certainty_labels_and_five_whys():
    with risk.session() as conn:
        _seed(conn)
        rca = dict(conn.execute(
            "SELECT * FROM incident_rca WHERE incident_id='INC-DEMO-CLOUD'"
        ).fetchone())
        assert "Confirmed" in (rca["what_happened"] or "")
        assert "Hypothesis" in (rca["process_weakness"] or "") or \
            "hypothesis" in (rca["process_weakness"] or "").lower()
        assert rca["unconfirmed"]
        whys = json.loads(rca["five_whys_json"])
        assert len(whys) == 5
        certs = {w["certainty"] for w in whys}
        assert "hypothesis" in certs
        assert "confirmed" in certs


def test_reporting_assessment_not_auto_mandatory():
    with risk.session() as conn:
        _seed(conn)
        rows = list(conn.execute(
            "SELECT * FROM incident_reporting WHERE incident_id='INC-DEMO-CLOUD'"))
        assert rows
        r = dict(rows[0])
        assert r["reporting_status"] == "under_review"
        note = (r["decision_note"] or "").lower()
        assert "no notification decision" in note or "mandatory" in note
        assert r["decision_owner"]


def test_audit_events_on_transition_and_loss():
    with risk.session() as conn:
        risk.insert(conn, "incident", {
            "id": "INC-AUDIT",
            "title": "Audit trail",
            "workflow_status": "detected",
            "status": "open",
            "is_synthetic": 1,
        }, actor="tester")
        im.transition(conn, "INC-AUDIT", "triaged", actor="Alice")
        im.add_loss(conn, "INC-AUDIT", gross=100, recovered=25, currency="ILS",
                    certainty="estimate", actor="Finance")
        hist = risk.history(conn, table="incident", object_id="INC-AUDIT")
        assert any(h["action"] == "update" for h in hist)
        loss_hist = risk.history(conn, table="incident_loss")
        assert any(h["action"] == "create" for h in loss_hist)
        tr = im.transitions(conn, "INC-AUDIT")
        assert tr.iloc[0]["actor"] == "Alice"


def test_export_and_dashboard():
    with risk.session() as conn:
        _seed(conn)
        reg = im.register(conn)
        assert "INC-DEMO-CLOUD" in set(reg["id"])
        blob = im.export_csv(reg)
        text = blob.decode("utf-8")
        assert "INC-DEMO-CLOUD" in text
        assert "detection_delay_min" in text
        empty = im.export_csv(reg.iloc[0:0])
        assert b"id" in empty
        dash = im.dashboard(conn)
        assert dash["total_net_loss"] >= 0
        assert "P1" in dash["open_by_severity"] or dash["open_by_severity"]
        assert not dash["root_cause_themes"].empty


def test_idempotent_seed():
    with risk.session() as conn:
        assert _seed(conn)["seeded"] is True
        assert im.seed(conn, today=DEMO_DAY, force=False)["seeded"] is False
        assert im.seed(conn, today=DEMO_DAY, force=True)["seeded"] is True
