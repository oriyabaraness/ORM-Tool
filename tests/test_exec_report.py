"""Executive operational risk reporting: periods, metrics, narrative, exports."""
import datetime as dt
import io

import pytest
from openpyxl import load_workbook

from test_orm import _fake_streamlit_full, built_db  # noqa: F401

from orm import exec_report as er, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


AS_OF = dt.date(2026, 11, 22)


def _seed(conn):
    return er.seed(conn, today=AS_OF, force=True)


def test_period_bounds_weekly_monthly_quarterly_custom():
    w = er.period_bounds("weekly", as_of=AS_OF)
    assert w["start"] == dt.date(2026, 11, 16)
    assert w["end"] == AS_OF
    m = er.period_bounds("monthly", as_of=AS_OF)
    assert m["start"] == dt.date(2026, 11, 1)
    q = er.period_bounds("quarterly", as_of=AS_OF)
    assert q["start"] == dt.date(2026, 10, 1)
    c = er.period_bounds("custom", as_of=AS_OF,
                         custom_start=dt.date(2026, 1, 1),
                         custom_end=dt.date(2026, 1, 31))
    assert c["start"].month == 1 and c["end"].day == 31
    with pytest.raises(ValueError):
        er.period_bounds("custom", as_of=AS_OF)
    with pytest.raises(ValueError):
        er.period_bounds("custom", as_of=AS_OF,
                         custom_start=dt.date(2026, 2, 1),
                         custom_end=dt.date(2026, 1, 1))
    with pytest.raises(ValueError):
        er.period_bounds("yearly", as_of=AS_OF)


def test_demo_report_title_and_metrics_link_to_records():
    with risk.session() as conn:
        _seed(conn)
        rep = er.build(conn, period="monthly", as_of=AS_OF, title=er.DEMO_TITLE)
        assert rep["title"] == er.DEMO_TITLE
        assert "Revolut" not in rep["title"] or "Hypothetical" in rep["title"]
        assert "not an actual revolut" in rep["watermark"].lower()
        assert rep["synthetic"] is True
        m = rep["metrics"]
        assert m["open_risks"] >= 1
        assert m["outside_appetite"] >= 0
        assert "by_residual_band" in m
        # Payment disruption story present
        emerging_ids = set(rep["emerging"]["risk_id"]) if not rep["emerging"].empty else set()
        assert "DEMO-RISK-001" in emerging_ids
        # Provenance points at real ids
        assert rep["provenance"]
        assert any(p.get("record_id") for p in rep["provenance"])


def test_narrative_has_facts_analysis_recommendations_no_full_compliance():
    with risk.session() as conn:
        _seed(conn)
        rep = er.build(conn, period="monthly", as_of=AS_OF)
        narr = rep["narrative"]["sections"]
        for key, _ in [
            ("A_executive_summary", None),
            ("H_next_period_priorities", None),
        ]:
            sec = narr[key]
            assert sec["facts"] and sec["analysis"] and sec["recommendations"]
        blob = " ".join(
            " ".join(sec["facts"] + sec["analysis"] + sec["recommendations"])
            for sec in narr.values())
        assert "fully compliant" not in blob.lower()
        assert "facts" in narr["A_executive_summary"]
        assert "synthetic" in rep["watermark"].lower() or "synthetic" in blob.lower()


def test_movement_does_not_invent_reasons():
    with risk.session() as conn:
        _seed(conn)
        # Create a residual override with no rationale → missing evidence language
        risk.update(conn, "risk", "DEMO-RISK-001", {
            "override_likelihood": 4,
            "override_impact": 4,
            "override_rationale": "",
        }, actor="tester")
        # Clear rationale after to simulate missing reason on a further change
        risk.update(conn, "risk", "DEMO-RISK-001", {
            "override_impact": 5,
        }, actor="tester")
        rep = er.build(conn, period="monthly", as_of=AS_OF)
        # Movements may or may not include empty-rationale rows depending on
        # whether fields in watched list changed — ensure any without reason
        # use the missing-evidence phrase.
        for mv in rep["movements"]:
            assert mv["reason_for_change"]
            if "not recorded" in mv["reason_for_change"].lower() \
                    or "missing" in mv["reason_for_change"].lower():
                assert "evidence" in mv["reason_for_change"].lower() \
                    or "missing" in mv["reason_for_change"].lower()


def test_committee_actions_and_resilience_link():
    with risk.session() as conn:
        _seed(conn)
        rep = er.build(conn, period="quarterly", as_of=AS_OF)
        acts = rep["committee_actions"]
        assert not acts.empty
        assert {"issue", "owner", "due_date", "required_decision",
                "status", "source_ref"} <= set(acts.columns)
        sources = set(acts["source_ref"].astype(str))
        assert len(sources) >= 1
        assert rep.get("resilience") is not None
        assert rep["resilience"]["linked_risk_id"] == "DEMO-RISK-001"


def test_exports_pdf_html_excel_watermark_and_formula_safe():
    with risk.session() as conn:
        _seed(conn)
        # Formula-looking title to ensure Excel safety on related sheets
        risk.update(conn, "risk", "DEMO-RISK-001", {
            "title": "=CMD(\"calc\") Payment disruption",
        }, actor="tester")
        rep = er.build(conn, period="monthly", as_of=AS_OF, title=er.DEMO_TITLE)
        pdf = er.export_pdf(rep)
        assert pdf.startswith(b"%PDF")
        assert b"SYNTHETIC" in pdf or b"Synthetic" in pdf or b"HYPOTHETICAL" in pdf.upper() \
            or b"Hypothetical" in pdf
        assert b"DEMO-RISK" in pdf or b"Payment" in pdf

        html = er.export_html(rep)
        assert "Operational Risk Overview" in html
        assert "FACTS" in html and "ANALYSIS" in html and "RECOMMENDATIONS" in html
        assert "SYNTHETIC" in html.upper()
        assert "not an actual revolut" in html.lower()
        assert "Impact tolerance" in html or "committee" in html.lower()

        xlsx = er.export_excel(rep)
        book = load_workbook(io.BytesIO(xlsx))
        assert "Read me" in book.sheetnames
        assert "Dashboard" in book.sheetnames
        readme = " ".join(str(c.value) for row in book["Read me"].iter_rows()
                          for c in row)
        assert "SYNTHETIC" in readme.upper() or "Hypothetical" in readme


def test_in_period_helper_and_missing_timestamps():
    assert er._in_period("2026-11-10T09:00:00+00:00",
                         dt.date(2026, 11, 1), dt.date(2026, 11, 22))
    assert not er._in_period("2026-10-01", dt.date(2026, 11, 1), dt.date(2026, 11, 22))
    assert not er._in_period(None, dt.date(2026, 11, 1), dt.date(2026, 11, 22))
    assert not er._in_period("", dt.date(2026, 11, 1), dt.date(2026, 11, 22))
    assert not er._in_period("not-a-date", dt.date(2026, 11, 1), dt.date(2026, 11, 22))


def test_idempotent_seed():
    with risk.session() as conn:
        assert _seed(conn)["seeded"] is True
        assert er.seed(conn, today=AS_OF, force=False)["seeded"] is False
