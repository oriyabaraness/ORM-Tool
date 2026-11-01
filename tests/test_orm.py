"""Tests for the Risk Compare pipeline.

Text fixtures below are short synthetic passages written for the tests; they
are not quotations of any regulator's text.
"""
import contextlib
import importlib
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from orm import classify, db, extract, pipeline, queries, sources, taxonomy  # noqa: E402

IL_TEXT = """
Business Continuity Test Directive
Page 1 of 3
1. Definitions
In this directive, "critical activity" means an activity whose disruption would
materially affect customers or the banking corporation.
2. The board of directors shall approve the business continuity plan and review
it at least once a year. The plan shall set a recovery time objective for each
critical activity and address severe but plausible scenarios.
3. The banking corporation shall test its continuity and recovery arrangements
annually, including a disaster recovery drill.
4. A banking corporation shall notify the Supervisor of Banks of any significant
operational incident within 24 hours of identifying it, and shall submit a root
cause analysis within 30 days.
2
"""

JO_TEXT = """
Instructions on Operational Continuity (test fixture)
Article (1)
Banks shall maintain a business continuity plan covering critical operations and
shall review the plan annually under the oversight of the board of directors.
Article (2)
Banks shall report any disruption of critical operations to the Central Bank
within three (3) business days.
"""


def _fake_docs():
    return [
        {"id": "IL-TEST-1", "jurisdiction": "IL", "regulator": "Bank of Israel",
         "ref": "Directive 999", "title": "Business continuity management",
         "subject": "סיכון תפעולי", "url": "", "pdf_url": None,
         "published": "2024-01-01", "lastmod": "2024-01-02", "source": "test"},
        {"id": "JO-TEST-1", "jurisdiction": "JO", "regulator": "Central Bank of Jordan",
         "ref": "No. 1/2025", "title": "Instructions on operational continuity",
         "subject": "", "url": "", "pdf_url": None,
         "published": "", "lastmod": "2025-02-01", "source": "test"},
        {"id": "JO-TEST-2", "jurisdiction": "JO", "regulator": "Central Bank of Jordan",
         "ref": "", "title": "Instructions of Anti Money Laundering",
         "subject": "", "url": "", "pdf_url": None,
         "published": "", "lastmod": "2020-01-01", "source": "test"},
    ]


@pytest.fixture
def built_db(tmp_path, monkeypatch):
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "IL-TEST-1.txt").write_text(IL_TEXT, encoding="utf-8")
    (manual / "JO-TEST-1.txt").write_text(JO_TEXT, encoding="utf-8")
    monkeypatch.setattr(extract, "MANUAL_DIR", str(manual))
    monkeypatch.setattr(extract, "TEXT_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(sources, "CONNECTORS",
                        {"test": ("IL", lambda: [d for d in _fake_docs()
                                                 if d["jurisdiction"] == "IL"]),
                         "test_jo": ("JO", lambda: [d for d in _fake_docs()
                                                    if d["jurisdiction"] == "JO"])})
    path = str(tmp_path / "orm.db")
    pipeline.build(path, fetch=False)
    return path


# --- extraction -------------------------------------------------------------

def test_split_provisions_numbers_and_furniture():
    provs = extract.split_provisions(IL_TEXT, min_chars=60)
    refs = [r for r, _ in provs]
    assert "§2" in refs and "§3" in refs and "§4" in refs
    joined = " ".join(t for _, t in provs)
    assert "Page 1 of 3" not in joined
    assert all(len(t) >= 20 for _, t in provs)


def test_split_provisions_articles():
    provs = extract.split_provisions(JO_TEXT, min_chars=60)
    assert [r for r, _ in provs] == ["Article 1", "Article 2"]


def test_split_long_block_cut_at_sentences():
    text = "1. " + " ".join(["The bank shall keep records."] * 300)
    provs = extract.split_provisions(text, max_chars=500)
    assert len(provs) > 5
    assert all(len(t) <= 500 for _, t in provs)
    assert provs[0][0].startswith("§1 (part 1)")


# --- classification -----------------------------------------------------------

def test_deadlines_normalized():
    found = dict(classify.extract_deadlines(
        "notify within 24 hours; report within three (3) business days; "
        "no later than 30 days; within one month"))
    assert found["within 24 hours"] == 24
    assert found["within three (3) business days"] == pytest.approx(3 * 24 * 7 / 5)
    assert found["no later than 30 days"] == 720
    assert found["within one month"] == 730


def test_frequencies():
    assert classify.extract_frequencies(
        "review it at least once a year and test it quarterly") == [
        "at least once a year", "quarterly"]


def test_document_tagging_uses_hebrew_subject_and_title():
    tags = {t.category_id: t for t in classify.classify_document(
        "Cloud Computing", "סיכוני טכנולוגיית המידע, אבטחת מידע והגנת סייבר")}
    assert tags["ict_cyber"].method == "subject"
    assert "third_party" in tags   # "cloud" in the title


def test_provision_tagging_needs_two_hits_unless_doc_context():
    text = "The bank shall keep a continuity plan on file."
    assert "op_resilience" not in {t.category_id for t in classify.classify_provision(text)}
    assert "op_resilience" in {t.category_id for t in classify.classify_provision(
        text, {"op_resilience"})}


def test_every_category_has_a_valid_definition():
    ids = [c.id for c in taxonomy.CATEGORIES]
    assert len(ids) == len(set(ids))
    exp_ids = [e.id for _, e in taxonomy.ALL_EXPECTATIONS]
    assert len(exp_ids) == len(set(exp_ids))
    for c in taxonomy.CATEGORIES:
        if c.orm_core:
            assert c.expectations, f"{c.id} needs baseline expectations"


# --- connectors on the real repo indexes ---------------------------------------

def test_real_connectors_normalize_repo_csvs():
    il = list(sources.boi_proper_conduct())
    jo = list(sources.cbj_regulations())
    assert len(il) > 100 and len(jo) > 30
    assert len({d["id"] for d in il + jo}) == len(il) + len(jo)
    assert all(d["pdf_url"] for d in il)
    assert any(d["pdf_url"] for d in jo)
    assert any(d["ref"] == "No. 8/2024" for d in jo)


# --- end to end -----------------------------------------------------------------

def test_pipeline_builds_comparable_index(built_db):
    with db.session(built_db) as conn:
        status = queries.index_status(conn).set_index("jurisdiction")
        assert status.loc["IL", "with_text"] == 1
        assert status.loc["JO", "with_text"] == 1

        m = queries.coverage_matrix(conn).set_index("category_id")
        assert m.loc["op_resilience", "IL_level"] == "text"
        assert m.loc["op_resilience", "JO_level"] == "text"
        assert m.loc["aml", "JO_level"] == "metadata"
        assert m.loc["aml", "IL_level"] == "none"

        gap = queries.expectation_table(conn, "op_resilience").set_index("expectation_id")
        assert gap.loc["res_bcp", "IL_status"] == "found"
        assert gap.loc["res_bcp", "JO_status"] == "found"
        assert gap.loc["res_rto", "IL_status"] == "found"
        assert gap.loc["res_rto", "JO_status"] == "not found"
        aml_gap = queries.expectation_table(conn, "aml").set_index("expectation_id")
        assert aml_gap.loc["aml_str", "JO_status"] == "not assessed"

        dl = queries.deadlines(conn)
        assert {"within 24 hours", "within three (3) business days"} <= set(dl["value_text"])

        provs = queries.category_provisions(conn, "op_resilience", "IL", query="recovery")
        assert not provs.empty
        assert all("recovery" in t.lower() for t in provs["text"])


def test_reclassify_keeps_human_review(built_db):
    with db.session(built_db) as conn:
        pid = conn.execute("SELECT provision_id FROM provision_category "
                           "WHERE category_id='op_resilience' LIMIT 1").fetchone()[0]
        conn.execute("UPDATE provision_category SET reviewed=1 WHERE provision_id=? "
                     "AND category_id='op_resilience'", (pid,))
        conn.commit()
        pipeline.classify_all(conn)
        reviewed = conn.execute("SELECT reviewed FROM provision_category WHERE "
                                "provision_id=? AND category_id='op_resilience'",
                                (pid,)).fetchone()[0]
        assert reviewed == 1


# --- UI smoke test with a stand-in for streamlit ------------------------------------

class _Ctx(contextlib.nullcontext):
    pass


def _fake_streamlit(rendered):
    st = types.ModuleType("streamlit")
    st.markdown = lambda body, **_: rendered.append(body)
    st.caption = lambda body, **_: rendered.append(body)
    st.columns = lambda spec, **_: [_Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs = lambda names: [_Ctx() for _ in names]
    st.expander = lambda *a, **k: _Ctx()
    st.spinner = lambda *a, **k: _Ctx()
    st.toggle = lambda label, value=False, **_: value
    st.button = lambda *a, **k: False
    st.selectbox = lambda label, options, **_: (
        "op_resilience" if "op_resilience" in options else options[0])
    st.text_input = lambda label, value="", **_: "recovery"
    st.download_button = lambda *a, **k: None
    st.dataframe = lambda df, **_: rendered.append(df.to_string())
    st.rerun = lambda: None
    st.container = lambda *a, **k: _Ctx()
    st.session_state = {}
    st.column_config = types.SimpleNamespace(NumberColumn=lambda *a, **k: None)
    return st


def test_risk_compare_section_renders(built_db, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit(rendered))
    sys.modules.pop("orm_compare", None)
    orm_compare = importlib.import_module("orm_compare")
    orm_compare.render_risk_compare_section(built_db)
    page = "\n".join(rendered)
    assert "Operational risk &amp; resilience" in page
    assert "Israel" in page and "Jordan" in page
    assert "<mark>recovery</mark>" in page.lower() or "<mark>Recovery</mark>" in page
    assert "within 24 hours" in page
    assert "not found" in page
    assert "Equivalent in Jordan" in page
    assert "Article 1" in page


def test_clause_matching_pairs_equivalent_clauses(built_db):
    with db.session(built_db) as conn:
        il = queries.clauses(conn, "IL", "op_resilience")
        bcp = il[il["text"].str.contains("business continuity plan")].iloc[0]
        eq = queries.equivalents(conn, int(bcp["provision_id"]), "op_resilience")
        assert not eq.empty
        best = eq.iloc[0]
        assert best["jurisdiction"] == "JO" and best["ref"] == "Article 1"
        assert "Documented business continuity plan" in best["shared_expectation_labels"]
        # and the reverse direction exists too
        jo = queries.clauses(conn, "JO", "op_resilience")
        assert (jo["matches"] > 0).all()


def test_match_scoring_helpers():
    from orm import match
    v = match.Vectorizer(["notify the supervisor of incidents",
                          "report incidents to the central bank",
                          "capital ratio requirements"])
    a, b, c = v.vectors()
    assert match.cosine(a, b) > match.cosine(a, c)
    assert match.strength(0.5) == "Strong match"
    assert match.strength(0.1) == "Weak match"
