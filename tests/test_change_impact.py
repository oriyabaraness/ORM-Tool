"""Regulatory change impact: clause diff, mapping, demo story, actions."""
import datetime as dt

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import change_impact as ci, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


def test_classify_added_removed_modified_unchanged_uncertain():
    assert ci.classify_pair("§1", "same text here", "same text here")["change_kind"] == "unchanged"
    assert ci.classify_pair("§2", None, "new obligation text")["change_kind"] == "added"
    assert ci.classify_pair("§3", "old obligation text", None)["change_kind"] == "removed"
    mod = ci.classify_pair(
        "§4",
        "The firm shall maintain documented recovery procedures.",
        "The firm shall maintain documented recovery procedures and test them.",
    )
    assert mod["change_kind"] == "modified"
    assert mod["diff"]
    assert mod["certainty"] == "hypothesis"
    assert mod["materiality"] == "not_assessed"
    unc = ci.classify_pair("§5", "alpha beta gamma", "completely different zeta")
    assert unc["change_kind"] in ("uncertain", "modified")


def test_compare_versions_demo_story_shape():
    a = [
        {"clause_ref": "§1", "seq": 1, "text": "Purpose unchanged."},
        {"clause_ref": "§2", "seq": 2, "text": "Documented recovery procedures required."},
    ]
    b = [
        {"clause_ref": "§1", "seq": 1, "text": "Purpose unchanged."},
        {"clause_ref": "§2", "seq": 2, "text": "Documented recovery procedures required."},
        {"clause_ref": "§2A", "seq": 3,
         "text": "Periodic evidence-supported recovery testing required."},
    ]
    diffs = ci.compare_versions(a, b)
    kinds = {d["clause_ref"]: d["change_kind"] for d in diffs}
    assert kinds["§1"] == "unchanged"
    assert kinds["§2"] == "unchanged"
    assert kinds["§2A"] == "added"


def test_fictional_demo_seed_and_analysis():
    with risk.session() as conn:
        out = ci.seed(conn, today=dt.date(2026, 11, 22), force=True)
        assert out["seeded"] is True
        assert out["added"] >= 1
        assert out["unchanged"] >= 2
        analysis = ci.analyze(conn, out["version_a"], out["version_b"])
        fam = analysis["family"]
        assert "fictional" in fam["publisher_note"].lower()
        assert "bank of israel" not in fam["title"].lower()
        assert "revolut" not in fam["title"].lower()
        # §2A added
        added = [d for d in analysis["changed"] if d["change_kind"] == "added"]
        assert any("test" in (d["text_b"] or "").lower() for d in added)
        # Mapping hits demo risk/control
        risk_ids = {r["risk_id"] for r in analysis["mapping"]["risks"]}
        ctl_ids = {c["control_id"] for c in analysis["mapping"]["controls"]}
        assert "DEMO-RISK-001" in risk_ids
        assert "CTL-DEMO-03" in ctl_ids
        assert any(c.get("testing_program_review") for c in analysis["mapping"]["controls"])
        blob = ci.export_summary_text(analysis["summary"]).lower()
        assert "never marks" in blob or "not a determination of noncompliance" in blob \
            or "never mark" in analysis["notice"].lower()
        assert "human review" in analysis["notice"].lower() or "human review" in blob
        assert "is noncompliant" not in blob


def test_persist_actions_creates_auditable_rows():
    with risk.session() as conn:
        ci.seed(conn, force=True)
        analysis = ci.analyze(conn, "DEMO-CLOUD-RES-A", "DEMO-CLOUD-RES-B")
        # Clear prior seed actions then re-persist once for the assert
        conn.execute("DELETE FROM change_impact_action WHERE family_id='DEMO-CLOUD-RES'")
        conn.execute("DELETE FROM action WHERE source_kind='change_impact'")
        saved = ci.persist_actions(conn, analysis, actor="tester")
        assert saved
        row = conn.execute(
            "SELECT * FROM change_impact_action WHERE id=?",
            (saved[0]["id"],)).fetchone()
        assert row["requires_human_review"] == 1
        assert row["related_risk_id"] or row["related_control_id"]
        linked = risk.actions(conn)
        assert not linked[linked["source_kind"] == "change_impact"].empty


def test_cross_family_versions_rejected():
    with risk.session() as conn:
        ci.seed(conn, force=True)
        risk.insert(conn, "reg_doc_family", {
            "id": "OTHER", "title": "Other", "publisher_note": "fictional",
            "is_synthetic": 1,
        }, actor="t")
        risk.insert(conn, "reg_doc_version", {
            "id": "OTHER-V1", "family_id": "OTHER", "version_label": "V1",
            "is_synthetic": 1, "provenance": "synthetic",
        }, actor="t")
        with pytest.raises(ValueError):
            ci.analyze(conn, "DEMO-CLOUD-RES-A", "OTHER-V1")


def test_idempotent_seed():
    with risk.session() as conn:
        assert ci.seed(conn, force=True)["seeded"] is True
        assert ci.seed(conn, force=False)["seeded"] is False
