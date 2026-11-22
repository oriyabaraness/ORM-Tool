"""Tests for the risk register (orm.risk), the synthetic demo (orm.demo_data),
the management report (orm.risk_report) and the risk screens."""
import datetime as dt
import hashlib
import importlib
import io
import os
import sys

import pytest
from openpyxl import load_workbook

from test_orm import ROOT, _fake_streamlit_full, built_db  # noqa: F401  (fixture)

from orm import db, demo_data, risk, risk_report, state  # noqa: E402


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


def _seeded(index_path=None):
    index = db.connect(index_path) if index_path else None
    ctx = risk.session()
    conn = ctx.__enter__()
    report = demo_data.seed(conn, index)
    return ctx, conn, index, report


# --- scoring ------------------------------------------------------------------------

def test_scoring_rules():
    assert [risk.band(s) for s in (1, 4, 5, 9, 10, 16, 20, 25)] == \
        ["Low", "Low", "Moderate", "Moderate", "High", "High", "Critical", "Critical"]
    assert risk.combined_rating("effective", "partially_effective") == "partially_effective"
    assert risk.combined_rating("effective", None) == "not_tested"
    # weakest key control per side; non-key controls do not count
    assert risk.residual(4, 4, [("effective", "likelihood", True)]) == (2, 4)
    assert risk.residual(4, 4, [("effective", "both", True),
                                ("partially_effective", "impact", True)]) == (2, 3)
    assert risk.residual(4, 4, [("effective", "likelihood", False)]) == (4, 4)
    assert risk.residual(1, 2, [("effective", "both", True)]) == (1, 1)
    assert risk.residual(3, 5, [("not_tested", "impact", True)]) == (3, 5)
    assert risk.kri_rag(2, 3, 5, "higher_is_worse") == "Green"
    assert risk.kri_rag(4, 3, 5, "higher_is_worse") == "Amber"
    assert risk.kri_rag(6, 3, 5, "higher_is_worse") == "Red"
    assert risk.kri_rag(99.95, 99.9, 99.5, "lower_is_worse") == "Green"
    assert risk.kri_rag(99.7, 99.9, 99.5, "lower_is_worse") == "Amber"
    assert risk.kri_rag(99.0, 99.9, 99.5, "lower_is_worse") == "Red"
    assert risk.kri_rag(None, 1, 2, "higher_is_worse") == "No data"


def test_every_write_is_logged_and_nothing_is_hard_deleted():
    with risk.session() as conn:
        risk.insert(conn, "risk", {"id": "RSK-900", "title": "Test risk",
                                   "category_id": "ict_cyber", "inherent_likelihood": 3,
                                   "inherent_impact": 3}, actor="Ana")
        risk.update(conn, "risk", "RSK-900", {"owner": "Head of IT"}, actor="Ben")
        risk.update(conn, "risk", "RSK-900", {"owner": "Head of IT"}, actor="Ben")
        risk.retire(conn, "risk", "RSK-900", actor="Ben")
        log = risk.history(conn, "risk", "RSK-900")
        assert [x["action"] for x in log] == ["update", "update", "create"]
        assert '"owner": null' in log[1]["before_json"]
        assert '"owner": "Head of IT"' in log[1]["after_json"]
        row = conn.execute("SELECT * FROM risk WHERE id='RSK-900'").fetchone()
        assert row["status"] == "retired" and row["updated_by"] == "Ben"
        assert row["created_by"] == "Ana"
        assert risk.register(conn).empty
        with pytest.raises(ValueError):
            risk.insert(conn, "obligation_review", {"okey": "x"}, actor="Ana")


def test_residual_override_needs_a_reason():
    with risk.session() as conn:
        risk.insert(conn, "risk", {"id": "RSK-901", "title": "T", "category_id": "ict_cyber",
                                   "inherent_likelihood": 4, "inherent_impact": 4}, actor="A")
        with pytest.raises(ValueError):
            risk.set_residual_override(conn, "RSK-901", 2, None, "  ", actor="A")
        with pytest.raises(ValueError):
            risk.set_residual_override(conn, "RSK-901", 7, None, "why", actor="A")
        risk.set_residual_override(conn, "RSK-901", 2, None, "New monitoring", actor="A")
        r = risk.register(conn).iloc[0]
        assert (r["residual_likelihood"], r["residual_impact"]) == (2, 4)
        assert r["residual_overridden"]


# --- synthetic demo -----------------------------------------------------------------

def test_demo_is_synthetic_idempotent_and_never_touches_reviews(built_db, tmp_path):
    with state.session() as s:
        state.save_review(s, "okey1", status=1, reviewer="Real reviewer")
    state_file = os.environ["ORM_STATE_DB"]
    before = hashlib.sha256(open(state_file, "rb").read()).hexdigest()
    ctx, conn, index, first = _seeded(built_db)
    try:
        assert first["seeded"] and first["linked"] == 0
        # the test index has no Bank of Israel directives: links are left out, not invented
        assert len(first["missing"]) >= len(demo_data.OBLIGATION_LINKS)
        assert conn.execute("SELECT COUNT(*) FROM risk_obligation").fetchone()[0] == 0
        assert demo_data.seed(conn, index)["seeded"] is False
        assert conn.execute("SELECT COUNT(*) FROM risk").fetchone()[0] == len(demo_data.RISKS)
        for table in risk.TABLES:
            cols = risk._columns(conn, table)
            if "is_synthetic" in cols:
                assert not conn.execute(
                    f"SELECT 1 FROM {table} WHERE is_synthetic = 0").fetchone(), table
        assert risk.is_synthetic(conn)
    finally:
        ctx.__exit__(None, None, None)
    assert hashlib.sha256(open(state_file, "rb").read()).hexdigest() == before


def test_seeded_links_quote_the_index_and_flag_changed_sources(built_db, monkeypatch):
    monkeypatch.setattr(demo_data, "OBLIGATION_LINKS", (
        ("RSK-003", "IL-TEST-1", "notify the Supervisor of Banks", "Notification duty."),
        ("RSK-002", "IL-TEST-1", "a phrase that is not in the directive", "Should be skipped."),
    ))
    monkeypatch.setattr(demo_data, "NOTIFICATION_LINK",
                        ("IL-TEST-1", "notify the Supervisor of Banks"))
    real_find = demo_data.find_obligation

    def find_skip_boi(index_conn, document_id, phrase):
        # Fixture has no BOI docs; keep DEMO-RISK-001 extras from inventing links.
        if str(document_id).startswith("IL-BOI-PC-"):
            return None
        return real_find(index_conn, document_id, phrase)

    monkeypatch.setattr(demo_data, "find_obligation", find_skip_boi)
    ctx, conn, index, rep = _seeded(built_db)
    try:
        assert rep["linked"] == 1
        assert any("phrase that is not" in m for m in rep["missing"])
        link = conn.execute("SELECT * FROM risk_obligation").fetchone()
        clause = index.execute(
            "SELECT p.text FROM obligation o JOIN provision p ON p.id = o.provision_id "
            "WHERE o.okey = ?", (link["okey"],)).fetchone()["text"]
        assert " ".join(link["sentence"].split()) in " ".join(clause.split())
        assert link["citation"].startswith("Bank of Israel · Directive 999")
        assert link["validation_status"] == "suggested"
        assert list(risk.check_obligation_links(conn, index)["source_state"]) == ["current"]
        chain = risk.risk_chain(conn, "RSK-001", index)
        assert any(lnk["kind"] == "notification_obligation"
                   for lnk in chain["incident_links"]["INC-001"])
        index.execute("UPDATE obligation SET okey = 'changed' WHERE okey = ?", (link["okey"],))
        assert list(risk.check_obligation_links(conn, index)["source_state"]) == \
            ["source changed"]
    finally:
        ctx.__exit__(None, None, None)


def test_register_chain_and_incident_figures():
    ctx, conn, _, _ = _seeded()
    try:
        reg = risk.register(conn).set_index("id")
        # notification control rated ineffective: no reduction, 3 x 4 = 12 > appetite 6
        assert reg.loc["RSK-003", "residual_score"] == 12
        assert reg.loc["RSK-003", "appetite"] == "Outside appetite"
        # within the score limit but a red KRI puts it outside appetite
        assert reg.loc["RSK-001", "residual_score"] <= reg.loc["RSK-001", "appetite_limit"]
        assert reg.loc["RSK-001", "kri_red"] == 1
        assert reg.loc["RSK-001", "appetite"] == "Outside appetite"
        assert reg.loc["RSK-001", "overdue_actions"] == 1
        assert reg.loc["RSK-002", "appetite"] == "Within appetite"
        inc = risk.incidents(conn).set_index("id")
        assert inc.loc["INC-001", "tolerance_breached"] is True or \
            bool(inc.loc["INC-001", "tolerance_breached"])
        assert inc.loc["INC-001", "notify_minutes"] == 155
        assert inc.loc["INC-001", "net_loss"] == 186500 - 41200
        chain = risk.risk_chain(conn, "RSK-001")
        assert set(chain["controls"]["id"]) == {"CTL-001", "CTL-002"}
        assert set(chain["actions"]["id"]) >= {"ACT-001", "ACT-002"}
    finally:
        ctx.__exit__(None, None, None)


def test_reset_refuses_when_the_store_holds_real_rows():
    ctx, conn, _, _ = _seeded()
    try:
        risk.update(conn, "risk", "RSK-001", {"owner": "Someone else"}, actor="A")
        demo_data.reset(conn, actor="A")
        assert conn.execute("SELECT owner FROM risk WHERE id='RSK-001'").fetchone()[0] == \
            "Head of Payments Engineering"
        risk.insert(conn, "risk", {"id": "RSK-500", "title": "Real", "category_id": "aml",
                                   "inherent_likelihood": 2, "inherent_impact": 2}, actor="A")
        with pytest.raises(PermissionError):
            demo_data.reset(conn, actor="A")
        assert conn.execute("SELECT 1 FROM risk WHERE id='RSK-500'").fetchone()
    finally:
        ctx.__exit__(None, None, None)


def test_new_demo_version_reloads_only_an_all_synthetic_store(monkeypatch):
    ctx, conn, _, _ = _seeded()
    try:
        risk.update(conn, "risk", "RSK-001", {"owner": "Edited"}, actor="A")
        monkeypatch.setattr(demo_data, "SEED_VERSION", "99")
        assert demo_data.seed(conn)["seeded"]
        assert conn.execute("SELECT owner FROM risk WHERE id='RSK-001'").fetchone()[0] != \
            "Edited"
        risk.insert(conn, "risk", {"id": "RSK-500", "title": "Real", "category_id": "aml",
                                   "inherent_likelihood": 2, "inherent_impact": 2}, actor="A")
        monkeypatch.setattr(demo_data, "SEED_VERSION", "100")
        assert not demo_data.seed(conn)["seeded"]
        assert conn.execute("SELECT 1 FROM risk WHERE id='RSK-500'").fetchone()
    finally:
        ctx.__exit__(None, None, None)


# --- report -------------------------------------------------------------------------

def test_report_is_labelled_and_exports_are_formula_safe():
    ctx, conn, _, _ = _seeded()
    try:
        risk.update(conn, "risk", "RSK-002", {"title": "=HYPERLINK(\"http://x\")"}, actor="A")
        rep = risk_report.build(conn)
        assert rep["synthetic"]
        assert rep["metrics"]["outside_appetite"] >= 2
        assert rep["metrics"]["overdue_actions"] >= 1
        assert any("outside appetite" in line for line in risk_report.headline(rep))
        book = load_workbook(io.BytesIO(risk_report.excel(rep)))
        readme = " ".join(str(c.value) for c in book["Read me"]["A"])
        assert "SYNTHETIC DEMONSTRATION DATA" in readme and "not a compliance" in readme
        titles = [c.value for c in book["Risks"]["B"]]
        assert "'=HYPERLINK(\"http://x\")" in titles
        pdf = risk_report.pdf(rep)
        assert pdf.startswith(b"%PDF") and b"SYNTHETIC DEMONSTRATION DATA" in pdf
    finally:
        ctx.__exit__(None, None, None)


# --- screens ------------------------------------------------------------------------

def test_risk_screens_render_and_escape_text(built_db, monkeypatch):
    rendered: list = []
    fake = _fake_streamlit_full(rendered)
    fake.text_area = lambda label, value="", **_: value
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    for name in ("orm_compare", "ui_theme", "controls_views", "risk_views"):
        sys.modules.pop(name, None)
    views = importlib.import_module("risk_views")
    with risk.session() as conn:
        demo_data.seed(conn, db.connect(built_db))
        risk.update(conn, "risk", "RSK-003", {"title": "<script>alert(1)</script>"}, actor="A")
    views.page_risks()
    views.page_report()
    page = "\n".join(str(x) for x in rendered)
    assert '<h1 class="page-title">Risk register</h1>' in page
    assert '<h1 class="page-title">Risk report</h1>' in page
    assert "Synthetic demonstration data" in page
    assert "Outside appetite" in page and "rk-heat" in page
    assert "were not found in this index and were left out" in page
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_real_index_links_every_demo_risk_to_quoted_text():
    path = os.path.join(ROOT, "orm.db")
    if not os.path.exists(path):
        pytest.skip("no local index")
    index = db.connect(path)
    try:
        has = index.execute("SELECT 1 FROM obligation WHERE document_id='IL-BOI-PC-366' "
                            "LIMIT 1").fetchone()
    except Exception:
        has = None
    if not has:
        pytest.skip("local index has no Bank of Israel obligations")
    with risk.session() as conn:
        rep = demo_data.seed(conn, index, today=dt.date(2026, 11, 22))
        assert rep["missing"] == []
        links = risk.check_obligation_links(conn, index)
        assert set(links["source_state"]) == {"current"}
        assert "RSK-001" in set(links["risk_id"])
        assert "DEMO-RISK-001" in set(links["risk_id"])
