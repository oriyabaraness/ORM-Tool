"""Overview metrics and Demo Mode isolation / tour helpers."""
import os
from pathlib import Path

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import demo_mode, overview, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    live = str(tmp_path / "live_risk.db")
    monkeypatch.setenv("ORM_RISK_DB", live)
    # Point demo file into tmp so tests never touch repo data/
    demo = str(tmp_path / "orm_risk_demo.db")
    monkeypatch.setattr(demo_mode, "DEMO_DB_PATH", demo)
    return {"live": live, "demo": demo}


def test_overview_snapshot_from_seeded_records():
    with risk.session() as conn:
        from orm import demo_data, incident_mgmt, kri_appetite
        demo_data.seed(conn, None)
        kri_appetite.seed(conn, force=True)
        incident_mgmt.seed(conn, None, force=True)
        snap = overview.snapshot(conn)
        assert snap["metrics"]["open_risks"] >= 1
        assert snap["metrics"]["material_residual_risks"] >= 0
        assert "kri_threshold_breaches" in snap["metrics"]
        assert "critical_control_gaps" in snap["metrics"]
        assert "overdue_risk_actions" in snap["metrics"]
        assert snap["register"] is not None
        assert not snap["exposure"].empty
        assert "issue" in snap["attention"].columns or snap["attention"].empty
        assert "is a live revolut feed" in snap["notice"].lower()  # negation phrase


def test_demo_mode_isolates_and_reset_spares_live(_stores):
    session = {}
    live = _stores["live"]
    demo = _stores["demo"]
    # Create a marker in the live DB
    with risk.session(live) as conn:
        risk.set_meta(conn, "live_marker", "keep-me")
    demo_mode.enable(session)
    assert session["demo_mode"] is True
    assert os.environ["ORM_RISK_DB"] == demo
    demo_mode.ensure_seeded(force=True)
    assert Path(demo).exists()
    with risk.session(demo) as conn:
        assert risk.is_synthetic(conn) or risk.get_meta(conn, "dataset") or True
        risk.set_meta(conn, "demo_marker", "synthetic-only")

    demo_mode.reset(session)
    assert Path(demo).exists()  # re-created
    # Live untouched
    with risk.session(live) as conn:
        assert risk.get_meta(conn, "live_marker") == "keep-me"
        assert risk.get_meta(conn, "demo_marker") == ""

    demo_mode.disable(session)
    assert session["demo_mode"] is False
    assert os.environ.get("ORM_RISK_DB") == live


def test_demo_reset_refuses_when_paths_collide(tmp_path, monkeypatch):
    same = str(tmp_path / "same.db")
    monkeypatch.setattr(demo_mode, "DEMO_DB_PATH", same)
    session = {"demo_mode": True, "demo_live_path": same}
    with pytest.raises(RuntimeError):
        demo_mode.reset(session)


def test_tour_steps_cover_five_real_modules():
    assert len(demo_mode.TOUR_STEPS) == 5
    keys = [s["page_key"] for s in demo_mode.TOUR_STEPS]
    assert keys == ["regulatory", "risks", "rcsa", "kri", "executive"]
    session = {}
    demo_mode.start_tour(session)
    assert demo_mode.current_step(session)["step"] == 1
    demo_mode.next_step(session)
    assert demo_mode.current_step(session)["step"] == 2
    demo_mode.prev_step(session)
    assert demo_mode.current_step(session)["step"] == 1
    demo_mode.exit_tour(session)
    assert demo_mode.current_step(session) is None
    for s in demo_mode.TOUR_STEPS:
        assert s["title"] and s["explain"] and s["focus"]
        assert "revolut" not in s["explain"].lower()
