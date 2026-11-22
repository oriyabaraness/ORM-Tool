"""Tests for Regulatory Intelligence (orm.regulatory_intel).

Fixtures use short synthetic passages from test_orm — not quotations of any
regulator's text. Citation verification and missing-source behaviour are the
focus here.
"""
import importlib
import os
import sys

import pytest

from test_orm import ROOT, _fake_streamlit_full, built_db  # noqa: F401

from orm import db, demo_data, obligations, regulatory_intel as ri, risk


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ORM_RISK_DB", str(tmp_path / "risk.db"))


def test_verify_citation_accepts_exact_quote_and_rejects_invented(built_db):
    conn = db.connect(built_db)
    obligations.init(conn)
    obligations.build_all(conn)
    conn.commit()
    row = conn.execute(
        "SELECT okey, sentence FROM obligation LIMIT 1").fetchone()
    assert row is not None
    ok = ri.verify_citation(conn, row["okey"], row["sentence"])
    assert ok["verified"] is True
    assert ok["status"].startswith("Verified")

    bad = ri.verify_citation(conn, row["okey"],
                             "The bank shall invent a duty that does not exist.")
    assert bad["verified"] is False
    assert bad["status"] == ri.UNVERIFIED_CITATION

    missing = ri.verify_citation(conn, "okey-does-not-exist")
    assert missing["verified"] is False
    assert missing["status"] == ri.UNVERIFIED_CITATION


def test_source_library_marks_missing_fields_unverified_not_invented(built_db):
    conn = db.connect(built_db)
    lib = ri.source_library(conn)
    assert not lib.empty
    row = lib.iloc[0]
    assert "Unverified" in row["effective_date"]
    assert "Unverified" in row["document_version"]
    assert row["supersession_status"] == "Not assessed"
    assert isinstance(row["original_reference"], str)


def test_demo_registry_marks_absent_documents_unverified(built_db):
    conn = db.connect(built_db)
    demo = ri.demo_registry(conn)
    assert list(demo["document_id"]) == list(ri.DEMO_DOCUMENT_IDS)
    # Fixture index has no BOI 350 etc. — every row must say unverified / missing.
    assert (demo["in_index"] == False).all()
    assert demo["registry_status"].str.contains("Unverified", regex=False).all()
    # Must not invent an official title for a missing document.
    assert (demo["official_title"].fillna("") == "").all()


def test_demo_registry_uses_index_titles_when_present():
    path = os.path.join(ROOT, "orm.db")
    if not os.path.exists(path):
        pytest.skip("no local index")
    conn = db.connect(path)
    demo = ri.demo_registry(conn)
    present = demo[demo["in_index"] == True]
    if present.empty:
        pytest.skip("local index missing BOI demo documents")
    assert present["official_title"].str.len().gt(0).all()
    assert present["extraction_status"].eq("ok").any()
    # Still never invent effective dates / versions.
    assert present["effective_date"].str.contains("Unverified", regex=False).all()


def test_obligations_explorer_separates_quote_from_interpretation(built_db):
    conn = db.connect(built_db)
    obligations.init(conn)
    obligations.build_all(conn)
    conn.commit()
    df = ri.obligations_explorer(conn, {}, demo_only=False)
    assert not df.empty
    row = df.iloc[0]
    assert row["exact_source_text"] == row["sentence"]
    assert row["plain_language"] == row["action"]
    assert "Machine interpretation" in row["interpretation_note"]
    assert row["page_number"] == ri.PAGE_UNAVAILABLE
    assert row["validation_status"] == "Suggested — needs review"
    assert bool(row["citation_verified"]) is True


def test_compare_documents_honest_when_other_has_no_text(built_db):
    conn = db.connect(built_db)
    obligations.init(conn)
    obligations.build_all(conn)
    conn.commit()
    # JO-TEST-2 has no text in the fixture.
    cmp = ri.compare_documents(conn, ["IL-TEST-1", "JO-TEST-2"])
    assert not cmp.empty
    assert set(cmp["relation"]).issubset({"unable", "no_comparable"})
    assert (cmp["validation_status"] == "Suggested — needs review").all()
    assert cmp["disclaimer"].iloc[0] == ri.COMPARISON_DISCLAIMER
    assert cmp["home_quote"].str.len().gt(0).all()


def test_compare_documents_finds_aligned_pair_when_text_exists(built_db):
    conn = db.connect(built_db)
    obligations.init(conn)
    obligations.build_all(conn)
    conn.commit()
    cmp = ri.compare_documents(conn, ["IL-TEST-1", "JO-TEST-1"])
    assert not cmp.empty
    assert cmp["relation_label"].isin(list(ri.RELATION_LABEL.values())).all()
    matched = cmp[cmp["other_okey"] != ""]
    if not matched.empty:
        assert matched["other_quote"].str.len().gt(0).all()
        assert matched["score"].notna().all()


def test_applicability_requires_known_status_and_is_logged():
    with risk.session() as conn:
        saved = ri.save_applicability(conn, {
            "document_id": "IL-TEST-1",
            "status": "potentially_applicable",
            "legal_entity": "Demo Digital Bank Ltd (fictional)",
            "product_service": "Card payments",
            "jurisdiction": "IL",
            "reasoning": "Payment services may fall in scope — legal to confirm.",
            "is_synthetic": 1,
        }, actor="Ana")
        assert saved["status"] == "potentially_applicable"
        assert saved["validation_status"] == "draft"
        rows = ri.applicability_for_document(conn, "IL-TEST-1")
        assert len(rows) == 1
        assert rows[0]["reviewer"] == "Ana"
        log = risk.history(conn, "applicability", saved["id"])
        assert log and log[0]["action"] == "create"
        with pytest.raises(ValueError):
            ri.save_applicability(conn, {
                "document_id": "IL-TEST-1", "status": "binding_forever",
            }, actor="Ana")


def test_risk_mapping_suggestions_are_suggested_not_validated(built_db):
    conn = db.connect(built_db)
    obligations.init(conn)
    obligations.build_all(conn)
    conn.commit()
    okey = conn.execute("SELECT okey FROM obligation LIMIT 1").fetchone()["okey"]
    sug = ri.risk_mapping_suggestions(conn, okey)
    assert sug["found"] is True
    assert sug["validation_status"] == "suggested"
    assert sug["exact_source_text"]
    assert "Suggestions only" in sug["disclaimer"]
    assert sug["risk_event"]
    assert sug["potential_kris"]


def test_link_suggestion_to_risk(built_db):
    index = db.connect(built_db)
    obligations.init(index)
    obligations.build_all(index)
    index.commit()
    okey = index.execute("SELECT okey FROM obligation LIMIT 1").fetchone()["okey"]
    with risk.session() as rconn:
        risk.insert(rconn, "risk", {
            "id": "RSK-TEST", "title": "Test risk", "category_id": "op_resilience",
            "inherent_likelihood": 3, "inherent_impact": 3,
            "provenance": "user", "validation_status": "draft",
        }, actor="Ana")
        linked = ri.link_suggestion_to_risk(
            rconn, index, risk_id="RSK-TEST", okey=okey,
            rationale="Unit test link", actor="Ana")
        assert linked["okey"] == okey
        assert linked["sentence"]
        with pytest.raises(LookupError):
            ri.link_suggestion_to_risk(
                rconn, index, risk_id="RSK-TEST", okey="missing-okey",
                rationale="x", actor="Ana")


def test_import_guidance_forbids_arbitrary_url_fetch():
    text = ri.import_guidance().lower()
    assert "does not fetch untrusted urls" in text
    assert "orm_texts/manual" in text


def test_regulatory_intelligence_screen_renders(built_db, monkeypatch):
    rendered: list = []
    fake = _fake_streamlit_full(rendered)
    fake.checkbox = lambda label, value=False, **_: value
    fake.text_area = lambda label, value="", **_: value
    fake.number_input = lambda label, value=0, **_: value
    fake.multiselect = lambda label, options, default=None, **_: list(default or [])[:1]
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    index = db.connect(built_db)
    obligations.init(index)
    obligations.build_all(index)
    index.commit()
    with risk.session() as rconn:
        demo_data.seed(rconn, index)
    for name in ("orm_compare", "ui_theme", "controls_views", "regulatory_views",
                 "risk_views"):
        sys.modules.pop(name, None)
    views = importlib.import_module("regulatory_views")
    views.page_regulatory_intelligence()
    page = "\n".join(str(x) for x in rendered)
    assert '<h1 class="page-title">Regulatory Intelligence</h1>' in page
    assert "From regulatory requirements to operational risk decisions" in page
    assert "Machine interpretation" in page or "Applicability" in page or "Source" in page
    assert "does not fetch untrusted" in page.lower() or "orm_texts/manual" in page
