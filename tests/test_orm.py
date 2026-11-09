"""Tests for the Risk Compare pipeline.

Text fixtures below are short synthetic passages written for the tests; they
are not quotations of any regulator's text.
"""
import contextlib
import io
import importlib
import os
import sys
import types

import pandas as pd
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


def test_turkey_cbrt_connector_normalizes_repo_csv():
    tr = list(sources.cbrt_regulations())
    assert len(tr) >= 10
    assert all(d["jurisdiction"] == "TR" for d in tr)
    assert all(d["id"].startswith("TR-CBRT-") for d in tr)
    assert len({d["id"] for d in tr}) == len(tr)
    assert all(d["pdf_url"] and ".pdf" in d["pdf_url"].lower() for d in tr)
    assert any(d["ref"] == "No. 6493" for d in tr)
    assert "TR" in queries.JURISDICTIONS


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
    st.multiselect = lambda label, options, default=None, **_: list(default or [])
    st.date_input = lambda label, value=None, **_: value
    st.switch_page = lambda page: None
    st.session_state = {}
    st.column_config = types.SimpleNamespace(NumberColumn=lambda *a, **k: None)
    return st


def test_coordinator_names_the_difference_between_two_clauses():
    from orm.review import coordinator_notes
    climate = coordinator_notes(
        "Israel",
        "Banking corporations should assess the impact of climate-related "
        "risk drivers on their operations.",
        "Jordan",
        "Business Continuity Plan: the plan that ensures resumption of "
        "operations after an interruption.")
    text = " ".join(climate["points"])
    assert climate["status"] == "differs"
    assert "climate-related" in text
    assert "Jordan does not state" in text
    assert "Not established" in text
    assert "compliance gap" in text

    clock = coordinator_notes(
        "Israel",
        "The bank shall notify the supervisor within 24 hours of a cyber incident.",
        "Jordan",
        "Banks must notify the supervisor within 2 business days of a cyber incident.")
    clock_text = " ".join(clock["points"])
    assert "within 24 hours" in clock_text
    assert "within 2 business days" in clock_text
    assert "shorter time is within 24 hours" in clock_text
    assert "does not, by itself, satisfy" in clock_text

    extra = coordinator_notes(
        "Israel",
        "The bank shall notify the supervisor before using a cloud service provider.",
        "Jordan",
        "Banks shall notify the supervisor before using a cloud service provider "
        "and keep a record.")
    extra_text = " ".join(extra["points"])
    assert "Both countries require" in extra_text
    assert "keep a record" in extra_text

    same = coordinator_notes(
        "Israel",
        "The bank shall notify the supervisor before using a cloud service provider.",
        "Jordan",
        "Banks shall notify the supervisor before using a cloud service provider.")
    assert same["status"] == "aligned"
    same_text = " ".join(same["points"])
    assert "does not mean one control satisfies both" in same_text
    assert "Not established" in same_text

    gap = coordinator_notes(
        "Israel",
        "The board shall approve a written exit strategy for every vendor.",
        "Jordan", None, assessed=True)
    gap_text = " ".join(gap["points"])
    assert gap["status"] == "unmatched"
    assert "exit strategy" in gap_text.lower()
    assert "not a compliance gap" in gap_text
    assert "Not established" in gap_text

    pending = coordinator_notes(
        "Israel", "The board shall approve a written exit strategy.",
        "Jordan", None, assessed=False)
    pending_text = " ".join(pending["points"]).lower()
    assert pending["status"] == "not_assessed"
    assert "not assessed" in pending_text
    assert "gap" not in pending_text


def test_analyst_brief_does_not_invent_costs_or_legal_status():
    from orm.review import analyst_brief
    brief = analyst_brief(
        "Israel",
        "The bank shall notify the supervisor within 24 hours of a cyber incident.",
        "Jordan",
        "Banks must notify the supervisor within 2 business days of a cyber incident.",
        home_regulator="Bank of Israel",
        other_regulator="Central Bank of Jordan",
        home_published="2019-11-01",
        home_ref="Directive 361 §12",
        other_ref="No. 1/2018 Article 6")
    blob = " ".join(
        item["text"] for item in brief["executive"]) + " " + " ".join(brief["risk"])
    assert "Not established" in blob
    assert "Implementation cost" in blob
    assert "penalties" in blob.lower()
    lowered = blob.lower()
    assert "severity: high" not in lowered
    assert "$" not in blob
    by_topic = {row["topic"]: row for row in brief["matrix"]}
    assert by_topic["Legal status"]["home"] == "Not established"
    assert by_topic["Effective date"]["home"] == "Not established"
    assert by_topic["Publication date"]["home"] == "2019-11-01"
    assert by_topic["Page"]["home"] == "Not established"
    assert "within 24 hours" in by_topic["Compliance deadline"]["home"]
    assert brief["actions"]
    assert all(row["priority"] == "Not established" for row in brief["actions"])
    assert all(row["dependency"] == "Not established" for row in brief["actions"])


def test_landing_page_states_the_way_in(built_db, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit(rendered))
    sys.modules.pop("orm_compare", None)
    sys.modules.pop("ui_theme", None)
    orm_compare = importlib.import_module("orm_compare")
    orm_compare.page_home(built_db)
    page = "\n".join(rendered)
    assert "Clausewiz" in page
    assert "Open a clause" in page
    assert "not a compliance gap" in page
    assert "Governance" in page
    assert "Israel" in page


def test_challenge_says_whether_jordan_has_the_clause():
    import orm_compare
    home = ("The bank shall notify the supervisor before using a cloud "
            "service provider.")
    jordan = [{
        "text": "Banks shall notify the supervisor before using a cloud "
                "service provider and keep a record.",
        "doc_ref": "No. 9/2022", "doc_title": "Cloud Computing Guideline",
        "ref": "Article 4", "regulator": "Central Bank of Jordan",
    }, {
        "text": "The liquidity coverage ratio shall be met with high quality assets.",
        "doc_ref": "No. 5/2020", "doc_title": "Liquidity Coverage Ratio",
        "ref": "Article 1", "regulator": "Central Bank of Jordan",
    }]
    found = orm_compare.challenge_clause(home, jordan, "Jordan", "Outsourcing")
    assert found["found"]
    assert "Found in Jordan" in found["answer"]
    assert "Cloud Computing" in found["answer"]
    missing = orm_compare.challenge_clause(
        "The board shall approve a written exit strategy for every vendor.",
        jordan[1:], "Jordan", "Outsourcing")
    assert not missing["found"]
    assert missing["answer"].startswith("Not found in Jordan")
    assert "exit strategy" in missing["answer"].lower()


def test_risk_compare_section_renders(built_db, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit(rendered))
    sys.modules.pop("orm_compare", None)
    sys.modules.pop("ui_theme", None)
    orm_compare = importlib.import_module("orm_compare")
    orm_compare.render_risk_compare_section(built_db)
    page = "\n".join(rendered)
    assert "Operational risk &amp; resilience" in page
    assert "Israel" in page and "Jordan" in page
    assert "<mark>recovery</mark>" in page.lower() or "<mark>Recovery</mark>" in page
    assert "within 24 hours" in page
    assert "Not found" in page            # gap status pill
    assert "Equivalent in Jordan" in page
    assert "Bank of Israel · <b>Directive 999" in page   # citation line
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


# --- reading the whole directive ---------------------------------------------

# Paragraph numbers on their own line, the way PDF text extraction often
# returns them.
SPLIT_LINE_TEXT = """
1.
The board of directors shall approve the outsourcing policy and review it at
least once a year, including the list of material outsourcing arrangements.
2.
The banking corporation shall assess the concentration risk arising from
reliance on a single service provider before entering into an arrangement.
2.1
The assessment shall consider exit strategies and substitutability.
Article (7)
Banks shall notify the Central Bank before outsourcing any material activity.
"""


def test_paragraph_number_on_its_own_line_starts_a_provision():
    provs = extract.split_provisions(SPLIT_LINE_TEXT, min_chars=60)
    refs = [r for r, _ in provs]
    assert refs[:2] == ["§1", "§2"]
    assert "Article 7" in refs
    # nothing is lost: every sentence of the source is in some provision
    joined = " ".join(t for _, t in provs)
    for phrase in ("list of material outsourcing", "exit strategies",
                   "single service provider", "before outsourcing"):
        assert phrase in joined


def test_full_directive_queries_return_every_provision(built_db):
    with db.session(built_db) as conn:
        docs = queries.documents(conn, "IL")
        il = docs[docs["document_id"] == "IL-TEST-1"].iloc[0]
        assert il["text_status"] == "ok"
        provs = queries.document_provisions(conn, "IL-TEST-1")
        assert len(provs) == il["provisions"] > 0
        assert list(provs["seq"]) == sorted(provs["seq"])
        # untagged clauses are still part of the directive
        assert (provs["categories"] == "").any() or len(provs) >= 3
        assert il["provision_chars"] >= 0.9 * il["chars"]
        # the document without text is reported, not silently dropped
        jo = queries.documents(conn, "JO")
        assert set(jo[jo["text_status"] != "ok"]["document_id"]) == {"JO-TEST-2"}


def test_splitter_change_resplits_already_read_documents(built_db, monkeypatch):
    with db.session(built_db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM provision").fetchone()[0]
    monkeypatch.setattr(extract, "SPLITTER_VERSION", "test-next")
    monkeypatch.setattr(extract, "split_provisions",
                        lambda text, **kw: [("§x", "one block")])
    pipeline.build(built_db, fetch=False)
    with db.session(built_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM provision").fetchone()[0]
        assert db.get_meta(conn, "splitter_version") == "test-next"
    assert before > after == 2  # both read documents were re-split


def test_full_directive_tab_renders(built_db, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit(rendered))
    sys.modules.pop("orm_compare", None)
    sys.modules.pop("ui_theme", None)
    orm_compare = importlib.import_module("orm_compare")
    with db.session(built_db) as conn:
        orm_compare.render_full_directive(conn, "IL", "op_resilience")
        orm_compare.render_full_directive(conn, "JO", "op_resilience")
    page = "\n".join(rendered)
    assert "% of the text kept" in page
    assert "§3" in page and "within 30 days" in page   # last sentence is there
    assert "1 of 2 Jordan documents have no text" in page


# --- automatic update --------------------------------------------------------

def _script(root, name, body):
    (root / name).write_text(body, encoding="utf-8")


def test_update_keeps_previous_list_when_crawler_is_blocked(tmp_path):
    from orm import update
    csv_text = "title,url\n" + "".join(f"doc {i},u{i}\n" for i in range(10))
    (tmp_path / "list.csv").write_text(csv_text, encoding="utf-8")
    # a "blocked" crawler that overwrites the list with 1 row
    _script(tmp_path, "crawl.py", "open('list.csv','w').write('title,url\\nx,y\\n')\n")
    res = update.run_step(update.Step("t", "crawl.py", "list.csv"), lambda m: None,
                          root=str(tmp_path))
    assert not res.ok and "kept the previous list" in res.message
    assert (tmp_path / "list.csv").read_text(encoding="utf-8") == csv_text
    # a crashing crawler is rolled back too
    _script(tmp_path, "crash.py", "open('list.csv','w').write('');raise SystemExit(3)\n")
    res = update.run_step(update.Step("t", "crash.py", "list.csv"), lambda m: None,
                          root=str(tmp_path))
    assert not res.ok and (tmp_path / "list.csv").read_text(encoding="utf-8") == csv_text
    # a healthy crawler that adds rows is accepted
    _script(tmp_path, "grow.py", "open('list.csv','a').write('doc 10,u10\\n')\n")
    res = update.run_step(update.Step("t", "grow.py", "list.csv"), lambda m: None,
                          root=str(tmp_path))
    assert res.ok and (res.rows_before, res.rows_after) == (10, 11)
    assert not list(tmp_path.glob("*.before-update"))


def test_update_reports_new_and_changed_documents(built_db, tmp_path, monkeypatch):
    from orm import update
    docs = _fake_docs()
    docs[0]["lastmod"] = "2026-11-01"                      # IL-TEST-1 changed
    docs.append({**docs[2], "id": "JO-TEST-3", "title": "New climate instructions"})
    monkeypatch.setattr(sources, "CONNECTORS", {
        "test": ("IL", lambda: [d for d in docs if d["jurisdiction"] == "IL"]),
        "test_jo": ("JO", lambda: [d for d in docs if d["jurisdiction"] == "JO"])})
    report = update.update(built_db, steps=[], report_dir=str(tmp_path / "r"),
                           log=lambda m: None)
    assert [d["id"] for d in report.new] == ["JO-TEST-3"]
    assert [(d["id"], d["why"]) for d in report.changed] == [("IL-TEST-1", "page updated")]
    text = (tmp_path / "r" / "latest.txt").read_text(encoding="utf-8")
    assert "New documents: 1" in text and "New climate instructions" in text



def test_workspace_pages_render_honest_states(built_db, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit(rendered))
    sys.modules.pop("orm_compare", None)
    sys.modules.pop("ui_theme", None)
    orm_compare = importlib.import_module("orm_compare")
    orm_compare.page_coverage(built_db)
    orm_compare.page_gaps(built_db)
    orm_compare.page_changes(built_db)
    page = "\n".join(rendered)
    assert "Clauses indexed" in page and "Titles only" in page   # coverage legend
    assert "Not assessed" in page or "Found" in page
    assert '<h1 class="page-title">Changes</h1>' in page
    # fixture documents are older than the default 90-day window: honest empty state
    assert "No documents in this scope were published or updated since" in page


# --- deployment guards ---------------------------------------------------------
# The live site once ran with an empty index: the deploy built orm.db without
# downloading any regulation text, and the extracted texts were git-ignored.

def test_deploy_build_downloads_regulation_text():
    import json
    with open(os.path.join(ROOT, "railway.json")) as f:
        cfg = json.load(f)
    build_cmd = cfg.get("build", {}).get("buildCommand", "")
    assert "orm_pipeline.py build" in build_cmd and "--fetch" in build_cmd


def test_extracted_texts_are_not_git_ignored():
    with open(os.path.join(ROOT, ".gitignore")) as f:
        rules = [line.strip() for line in f
                 if line.strip() and not line.startswith("#")]
    assert not any(r.startswith("orm_texts") for r in rules)


def test_blocked_host_is_skipped_after_repeated_failures(tmp_path, monkeypatch):
    import requests
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        raise requests.ConnectionError("blocked")

    monkeypatch.setattr(extract, "TEXT_DIR", str(tmp_path / "texts"))
    monkeypatch.setattr(extract, "MANUAL_DIR", str(tmp_path / "manual"))
    monkeypatch.setattr(extract, "BOI_TEXT_DIR", str(tmp_path / "boi"))
    monkeypatch.setattr(extract.requests, "get", fake_get)
    with db.session(str(tmp_path / "orm.db")) as conn:
        db.init(conn)
        for n in range(6):
            db.upsert_document(conn, {
                "id": f"XX-{n}", "jurisdiction": "JO", "regulator": "Test",
                "ref": "", "title": f"Doc {n}", "subject": "",
                "url": "", "pdf_url": f"https://blocked.example/{n}.pdf",
                "published": "", "lastmod": "", "source": "test"})
        counts = pipeline.extract_texts(conn, fetch=True)
    assert len(calls) == pipeline.MAX_HOST_FAILURES
    assert counts["error"] == pipeline.MAX_HOST_FAILURES
    assert counts["no_text"] == 6 - pipeline.MAX_HOST_FAILURES


# --- obligations, controls and audit readiness ---------------------------------

def test_obligation_extraction_reads_duties_not_definitions():
    from orm import obligations
    text = ("1. In this directive, \"incident\" shall mean any disruption. "
            "2. The board of directors shall approve the business continuity plan "
            "at least once a year. 3. A banking corporation shall notify the "
            "Supervisor of Banks within 24 hours of a significant incident. "
            "4. The plan should be tested annually. This directive shall enter "
            "into force on 1 January.")
    found = obligations.extract(text)
    actions = [o["action"].lower() for o in found]
    assert not any("mean" in a for a in actions)
    assert not any("force" in a for a in actions)
    board = next(o for o in found if o["actor"] == "the board")
    assert "approve" in board["action"].lower()
    assert board["frequency"] == "at least once a year"
    assert "minutes" in board["evidence"].lower()
    notify = next(o for o in found if "notify" in o["action"].lower())
    assert notify["deadline_hours"] == 24.0 and notify["modality"] == "mandatory"
    tested = next(o for o in found if "tested" in o["action"].lower())
    assert tested["modality"] == "expected" and tested["actor"] == "The plan"
    assert obligations.okey("IL-1", "A b.") == obligations.okey("IL-1", "a  B")


def test_build_creates_obligations_with_control_suggestions(built_db):
    from orm import controls
    with db.session(built_db) as conn:
        rows = conn.execute("SELECT * FROM obligation").fetchall()
        assert rows, "the build should extract obligations"
        assert {r["jurisdiction"] for r in rows} == {"IL", "JO"}
        sugg = conn.execute(
            "SELECT o.action, oc.control_id FROM obligation_control oc "
            "JOIN obligation o ON o.id = oc.obligation_id").fetchall()
    assert all(s["control_id"] in controls.BY_ID for s in sugg)
    notify = [s["control_id"] for s in sugg if "notify" in s["action"].lower()]
    assert "INC-02" in notify or "RES-05" in notify or notify


def test_control_library_is_complete():
    from orm import controls
    core = [c.id for c in taxonomy.CATEGORIES if c.orm_core]
    for cid in core:
        assert len(controls.for_category(cid)) >= 4, cid
    assert len({c.id for c in controls.LIBRARY}) == len(controls.LIBRARY)


def test_reviews_survive_and_replay_as_of_a_date(tmp_path):
    from orm import state
    path = str(tmp_path / "state.db")
    with state.session(path) as s:
        state.save_review(s, "k1", status=1, reviewer="Dana", control_id="RES-01",
                          at="2026-03-01T10:00:00+00:00")
        state.save_review(s, "k1", status=1, reviewer="Dana", control_id="RES-01",
                          at="2026-03-02T10:00:00+00:00")       # no change: not logged
        state.save_review(s, "k1", status=-1, reviewer="Omar", note="not a duty",
                          at="2026-04-01T10:00:00+00:00")
        assert len(state.log_entries(s)) == 2
        assert state.reviews(s)["k1"]["status"] == -1
        assert state.reviews_as_of(s, "2026-02-28") == {}
        assert state.reviews_as_of(s, "2026-03-15")["k1"]["status"] == 1
        assert state.reviews_as_of(s, "2026-04-01")["k1"]["reviewer"] == "Omar"


def test_bank_control_upload_is_normalised():
    from orm import state
    df = pd.DataFrame([
        {"Control ID": "C-1", "Control Name": "BCP test", "Owner": "Ops",
         "Frequency": "Annual", "Risk category": "Operational risk & resilience"},
        {"Control ID": "C-2", "Control Name": "Weird", "Owner": "",
         "Frequency": "", "Risk category": "Astrology"},
    ])
    rows, problems = state.normalize_controls(df)
    assert rows[0]["category_id"] == "op_resilience" and rows[0]["ref"] == "C-1"
    assert rows[1]["category_id"] == "" and any("Astrology" in p for p in problems)
    assert state.normalize_controls(pd.DataFrame([{"x": 1}]))[0] == []


def test_coverage_and_audit_pack(built_db, tmp_path):
    from orm import audit, state
    bank = [{"ref": "C-9", "name": "Incident notification",
             "description": "Notify the Supervisor of Banks of significant "
                            "operational incidents within 24 hours",
             "owner": "CRO", "frequency": "Per incident", "category_id": ""}]
    with db.session(built_db) as conn, state.session(str(tmp_path / "s.db")) as s:
        df = audit.obligation_table(conn, {}, jurisdiction="IL")
        k = df[df["action"].str.contains("notify", case=False)].iloc[0]["okey"]
        state.save_review(s, k, status=1, reviewer="Dana", control_id="INC-02")
        df = audit.obligation_table(conn, state.reviews(s), jurisdiction="IL")
        row = df[df["okey"] == k].iloc[0]
        assert row["status"] == "Approved" and row["control_id"] == "INC-02"
        assert row["citation"].startswith("Bank of Israel · Directive 999")
        cov = audit.coverage(df, bank)
        assert cov[cov["okey"] == k].iloc[0]["coverage"] in ("covered", "partial")
        assert "not covered" in set(cov["coverage"])
        xlsx = audit.audit_pack_excel(cov, scope="Israel", log=state.log_entries(s))
        sheets = pd.read_excel(io.BytesIO(xlsx), sheet_name=None)
        assert {"Read me", "Coverage summary", "Obligations", "Change log"} <= set(sheets)
        assert "Directive 999" in " ".join(sheets["Obligations"]["Source"])
        pdf = audit.audit_pack_pdf(cov, scope="Israel")
        assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
        assert b"Clausewiz audit pack" in pdf


def test_update_report_names_controls_to_recheck(built_db):
    from orm import update
    with db.session(built_db) as conn:
        affected = update.affected_controls(conn, ["IL-TEST-1"], reviews={})
    assert affected[0]["obligations"] > 0 and affected[0]["controls"]
    report = update.Report(started="2026-11-09T10:00:00", affected=affected)
    assert "Controls to re-check: 1 document(s)" in report.to_text()


def test_llm_results_must_quote_the_clause():
    from orm import llm
    texts = {3: "The bank shall notify the supervisor within 24 hours."}
    items = [{"seq": 3, "sentence": "The bank shall notify the supervisor within 24 hours.",
              "action": "Notify the supervisor"},
             {"seq": 3, "sentence": "The bank shall pay every customer a bonus.",
              "action": "Pay a bonus"},
             {"seq": 7, "sentence": "The bank shall notify the supervisor within 24 hours.",
              "action": "Wrong clause"}]
    kept = llm.verify(items, texts)
    assert [k["action"] for k in kept] == ["Notify the supervisor"]


def test_llm_cache_replaces_rule_extraction(built_db, tmp_path, monkeypatch):
    import json as _json
    from orm import obligations
    monkeypatch.setattr(obligations, "LLM_CACHE_DIR", str(tmp_path / "llm"))
    with db.session(built_db) as conn:
        seq = conn.execute("SELECT seq, text FROM provision WHERE document_id='IL-TEST-1' "
                           "AND text LIKE '%notify%'").fetchone()
        os.makedirs(obligations.LLM_CACHE_DIR)
        with open(obligations.llm_cache_path("IL-TEST-1"), "w") as f:
            _json.dump({"obligations": [{"seq": seq["seq"], "actor": "the bank",
                                         "action": "Notify the supervisor",
                                         "sentence": "notify the Supervisor of Banks",
                                         "modality": "mandatory"}]}, f)
        obligations.build_all(conn)
        rows = conn.execute("SELECT method, action FROM obligation "
                            "WHERE document_id='IL-TEST-1'").fetchall()
    assert [(r["method"], r["action"]) for r in rows] == [("llm", "Notify the supervisor")]


def _fake_streamlit_full(rendered):
    """The shared fake plus the widgets the controls screens use."""
    st = _fake_streamlit(rendered)
    st.data_editor = lambda df, **_: (rendered.append(df.to_string()), df)[1]
    st.file_uploader = lambda *a, **k: None
    st.segmented_control = lambda label, options, default=None, **_: default
    st.success = st.error = st.warning = lambda body, **_: rendered.append(body)
    st.text_input = lambda label, value="", **_: value
    st.selectbox = lambda label, options, index=0, **_: list(options)[index or 0]

    class _Cols:
        def __getattr__(self, name):
            return lambda *a, **k: None
    st.column_config = _Cols()
    return st


def test_controls_screens_render(built_db, tmp_path, monkeypatch):
    rendered: list[str] = []
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit_full(rendered))
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    for name in ("orm_compare", "ui_theme", "controls_views"):
        sys.modules.pop(name, None)
    views = importlib.import_module("controls_views")
    views.page_obligations()
    views.page_controls()
    views.page_audit()
    page = "\n".join(str(x) for x in rendered)
    for title in ("Obligations", "Controls", "Audit readiness"):
        assert f'<h1 class="page-title">{title}</h1>' in page
    assert "obligations" in page and "approved" in page
    assert "needs a new control" in page.lower()
    assert "No controls saved yet" in page
    assert "Change log" in page


def test_obligation_table_cells_are_filled(built_db, tmp_path, monkeypatch):
    """Regression: the review table once rendered every cell as None because
    its index did not line up with the data."""
    tables = []
    rendered: list[str] = []
    fake = _fake_streamlit_full(rendered)
    fake.data_editor = lambda df, **_: (tables.append(df), df)[1]
    fake.session_state["scope_category"] = "op_resilience"
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setenv("ORM_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setattr(db, "DEFAULT_DB", built_db)
    for name in ("orm_compare", "ui_theme", "controls_views"):
        sys.modules.pop(name, None)
    importlib.import_module("controls_views").page_obligations()
    table = tables[0]
    assert not table["action"].isna().any() and not table["status"].isna().any()
    assert table["action"].str.len().min() > 5
