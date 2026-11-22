"""Tests for KRI calculation, thresholds, escalations and the payment-failure demo."""
import datetime as dt
import importlib
import sys

import pytest

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import kri_appetite as ka, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


def test_formula_correctness_and_zero_denominator():
    assert ka.compute_rate(1800, 100_000) == 1.8
    assert ka.compute_rate(300, 100_000) == 0.3
    assert ka.compute_rate(None, 100) is None
    with pytest.raises(ka.ZeroDenominator):
        ka.compute_rate(1, 0)
    assert ka.compute_count(3) == 3.0
    assert ka.compute_count(None) is None


def test_rag_boundaries_both_directions():
    # higher_is_worse: green <= 0.5, amber <= 1.0, red > 1.0
    assert ka.classify_rag(0.5, 0.5, 1.0, "higher_is_worse") == "Green"
    assert ka.classify_rag(0.50001, 0.5, 1.0, "higher_is_worse") == "Amber"
    assert ka.classify_rag(1.0, 0.5, 1.0, "higher_is_worse") == "Amber"
    assert ka.classify_rag(1.0001, 0.5, 1.0, "higher_is_worse") == "Red"
    # lower_is_worse: green >= 99.9, amber >= 99.5, red < 99.5
    assert ka.classify_rag(99.9, 99.9, 99.5, "lower_is_worse") == "Green"
    assert ka.classify_rag(99.7, 99.9, 99.5, "lower_is_worse") == "Amber"
    assert ka.classify_rag(99.49, 99.9, 99.5, "lower_is_worse") == "Red"
    assert ka.classify_rag(None, 1, 2, "higher_is_worse") == "No data"


def test_trend_and_missing_observations():
    assert ka.trend(1.8, 0.3, "higher_is_worse") == "Deteriorating"
    assert ka.trend(0.2, 0.3, "higher_is_worse") == "Improving"
    assert ka.trend(1.0, 1.0, "higher_is_worse") == "Stable"
    assert ka.trend(None, 1.0, "higher_is_worse") == "No data"


def test_payment_failure_demo_is_internally_consistent():
    with risk.session() as conn:
        ka.seed(conn, today=dt.date(2026, 11, 22), force=True)
        obs = ka.observations(conn, "KRI-PAY-FAIL")
        assert len(obs) == 30
        first, last = obs.iloc[0], obs.iloc[-1]
        assert first["numerator"] == 300 and first["denominator"] == 100_000
        assert first["value"] == 0.3
        assert last["numerator"] == 1800 and last["denominator"] == 100_000
        assert last["value"] == 1.8
        assert ka.classify_rag(first["value"], 0.5, 1.0, "higher_is_worse") == "Green"
        assert ka.classify_rag(last["value"], 0.5, 1.0, "higher_is_worse") == "Red"
        # Every stored value matches numerator/denominator
        for _, r in obs.iterrows():
            assert r["value"] == pytest.approx(
                100.0 * r["numerator"] / r["denominator"], rel=1e-6)
        lib = ka.library(conn).set_index("id")
        assert lib.loc["KRI-PAY-FAIL", "rag"] == "Red"
        assert "DEMO-RISK-001" in str(lib.loc["KRI-PAY-FAIL", "linked_risks"])


def test_escalation_preserves_observation_and_creates_action():
    with risk.session() as conn:
        ka.seed(conn, today=dt.date(2026, 11, 22), force=True)
        esc = ka.escalations(conn)
        pay = esc[esc["kri_id"] == "KRI-PAY-FAIL"]
        assert not pay.empty
        red = pay[pay["status_rag"] == "Red"].iloc[0]
        assert red["observation_id"]
        assert "DEMO-RISK-001" in (red["related_risks"] or "")
        assert "FACTS" in (red["commentary"] or "") and "HYPOTHESES" in red["commentary"]
        assert "not root causes" in red["commentary"].lower() or \
            "not established" in red["commentary"].lower()
        ka.acknowledge_escalation(conn, red["id"], actor="Ana")
        updated = ka.approve_escalation_action(conn, red["id"], actor="Ana")
        assert updated["ack_status"] == "actioned"
        assert updated["action_id"]
        act = conn.execute("SELECT * FROM action WHERE id=?",
                           (updated["action_id"],)).fetchone()
        assert act["source_kind"] == "kri"
        assert act["status"] == "open"


def test_csv_ingest_and_timestamp():
    with risk.session() as conn:
        ka.seed(conn, force=True)
        csv_text = (
            "kri_id,period,observed_at,numerator,denominator,note\n"
            "KRI-PAY-FAIL,2099-06-01,2099-06-01T15:30:00+00:00,200,100000,upload test\n"
        )
        results = ka.ingest_csv(conn, csv_text, actor="Ben")
        assert results[0]["rag"] == "Green"
        obs = ka.observations(conn, "KRI-PAY-FAIL")
        row = obs[obs["period"] == "2099-06-01"].iloc[0]
        assert row["observed_at"].startswith("2099-06-01")
        assert row["source"] == "csv"
        assert row["value"] == 0.2


def test_appetite_concepts_are_distinct():
    titles = [t for t, _ in ka.concepts_glossary()]
    assert "Risk appetite" in titles
    assert "Risk tolerance" in titles
    assert "KRI warning threshold" in titles
    assert "Service impact tolerance" in titles
    with risk.session() as conn:
        ka.seed(conn, force=True)
        app = ka.appetite_statements(conn)
        assert set(app["kind"]) >= {"appetite", "tolerance"}


def test_dashboard_cards():
    with risk.session() as conn:
        ka.seed(conn, today=dt.date(2026, 11, 22), force=True)
        dash = ka.dashboard(conn)
        assert dash["cards"]["active_breaches"] >= 1
        assert dash["notice"] == ka.NOTICE
        assert not dash["library"].empty


def test_kri_screen_renders(built_db, monkeypatch):
    rendered: list = []
    fake = _fake_streamlit_full(rendered)
    fake.text_area = lambda label, value="", **_: value
    fake.line_chart = lambda *a, **k: rendered.append("line_chart")
    fake.file_uploader = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    from orm import db
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    with risk.session() as conn:
        ka.seed(conn, force=True)
    for name in ("orm_compare", "ui_theme", "controls_views", "risk_views",
                 "kri_views", "rcsa_views"):
        sys.modules.pop(name, None)
    views = importlib.import_module("kri_views")
    views.page_kri()
    page = "\n".join(str(x) for x in rendered)
    assert "KRI &amp; Appetite" in page or "KRI & Appetite" in page
    assert "Synthetic demonstration" in page or "Illustrative" in page
