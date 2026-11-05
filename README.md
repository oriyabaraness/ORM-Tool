# banking-orm-tool

Banking ORM tool: compares banking regulatory risk across countries (Israel, Jordan, Turkey), plus a Bank of Israel publications explorer.

The app opens on **Compare**. The left menu has the comparison workspace
(Compare, Coverage, Gaps, Deadlines, Changes) and the reference screens
(Sources: catalog and PDF reader; Market context: regional map and macro
data). Design rules are in `DESIGN.md`; shared styles in `ui_theme.py`.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Or, if the local `.venv` already exists:

```bash
./run_app.sh
```

The Streamlit app expects the CSV catalog files in this directory and extracted
text files under `boi_texts/`. Full-text search uses
`boi_pdf_text_manifest.csv` plus the gzip text files in `boi_texts/`.

The Reader tab opens any PDF from `boi_pdf_links.csv` in an interactive
side-by-side viewer. It downloads the selected publication on demand, renders
the original PDF pages, extracts page text and word boxes, and supports
in-document search with synchronized PDF/text navigation.

The Regional Map tab includes country-adjusted publication views and a focused
ORM risk screen. Choose the publication country from the regional map, then
compare all BOI Proper Conduct directive update frequency against a single risk
proxy. The method is fixed to same-year annual correlation, since 2012, using
website update dates.

To add more PDFs to the searchable full-text corpus:

```bash
python boi_pdf_text.py
```

To refresh connected Central Bank of Jordan feeds:

```bash
python jordan_cbj_index.py
python turkey_cbrt_index.py
python jordan_cbj_financial_stability.py
python jordan_cbj_foreign_exchange_reserves.py
python jordan_cbj_fx_rates.py
python israel_boi_fx_reserves.py
python overnight_rate_analysis.py
python banking_sector_indicators.py
```

## Risk Compare (Israel, Jordan, Turkey)

The **Risk Compare** section lines up Bank of Israel, Central Bank of Jordan
and Central Bank of the Republic of Türkiye (CBRT) regulation against one risk taxonomy (`orm/taxonomy.py`): governance,
operational resilience, outsourcing, IT/cyber, incident reporting, AML,
conduct, plus prudential categories.

It shows:

- **Clause explorer** – choose a country and a risk category, click any clause,
  and the closest equivalent clauses from the other country appear beside it,
  ranked Strong / Partial / Weak with the reasons for the match (shared
  baseline expectations and key terms). Matching lives in `orm/match.py`.
- **Coverage matrix** – category × country, with how deep the coverage is
  (provisions indexed / mapped from titles only / nothing found).
- **Side by side** – both countries' documents and tagged provisions for one
  category, with extracted deadlines (⏱) and review frequencies (↻).
- **Gap analysis** – baseline expectations per ORM category (e.g. "recovery
  time objectives", "exit strategy for outsourcing") marked found / not found /
  not assessed per country, with the evidencing provision.
- **Deadlines** – every "within N hours/days" obligation, normalized to hours.

The index lives in `orm.db` (SQLite, git-ignored). The app builds it from the
CSV indexes on first open. To pull the regulation text:

```bash
python orm_pipeline.py build --fetch          # download + extract PDFs, tag everything
python orm_pipeline.py status --missing       # what still has no text
python orm_pipeline.py classify               # re-tag after editing the taxonomy
```

Most CBJ entries have no direct PDF link. Run `python jordan_cbj_index.py`
to try scraping them, or save a PDF from the CBJ site as
`orm_texts/manual/<document id>.pdf` (ids come from `status --missing`).

Code layout: `orm/` (taxonomy, db, sources, extract, classify, pipeline,
queries), `orm_compare.py` (the Streamlit view), `tests/test_orm.py`
(`python -m pytest tests`).

Turkey note: the CBRT covers monetary policy, payment systems and reserve
operations. Most Turkish prudential banking rules (capital, liquidity, credit
risk, outsourcing, IT) are issued by the BRSA (BDDK), so Turkey will show few
matches in those categories until a BDDK feed is added.

## ORM Analysis Standard (RDL)

The tool reads regulation under one fixed method, the **Regulatory Delta
Language (RDL v1.0)**, so every analysis is coded the same way. Five layers,
each in its own file under `orm/`:

| Layer | What it does | File |
|---|---|---|
| 1 Authority map | Who writes the rules per country and risk area; areas run by another body (e.g. Turkey's BDDK) show "Other authority", never "gap" | `orm/rdl.py` |
| 2 Obligation grammar | Each clause coded into records: Force, Addressee, Action, Object, Trigger, Measure, Frequency, Evidence, Proportionality | `orm/grammar.py` |
| 3 Risk lenses | Basel loss event and resilience principle per category; control type per record | `orm/rdl.py`, `orm/grammar.py` |
| 4 Directional verdicts | Each matched pair judged home → target: Equivalent, Stricter, Looser, Different mechanism, Gap, Not assessed | `orm/verdicts.py` |
| 5 Scores | Regulatory Intensity Index (0–100), Entry Readiness, Confidence grade A/B/C, delta statement | `orm/scores.py` |

Where it shows in the app:

- **Compare**: the selected clause shows its coded obligations in RDL notation;
  each equivalent shows its verdict and why, with Confirm / Reject buttons. A
  confirmed verdict survives index rebuilds and lifts the grade to A.
- **Coverage**: every cell shows its Intensity score and grade.
- **Gaps**: areas written by another authority are marked as such.
- **Delta** (new): the delta statement and Entry Readiness for a home → target
  pair, with every line item, exportable as CSV.

The vocabulary, authority map and score weights live in `orm/rdl.py`. Changing
any of them is a change to the standard: bump `VERSION` and add a line to
`CHANGELOG` there. After pulling a new version, re-code the index with
`python orm_pipeline.py classify`.

## Automatic updates

`./update.sh` refreshes everything in one go:

1. re-crawls the Bank of Israel page list and Proper Conduct directives
2. re-reads the Central Bank of Jordan and Central Bank of Turkey regulations lists
3. downloads and reads any new PDFs, then re-tags and re-matches clauses
4. writes a short "what's new" report to `update_reports/latest.txt`

If a regulator's site blocks the crawler, its previous list is kept, so a bad
run never removes documents. The full log is in `update_reports/update.log`.

To run it every week on a Mac, add one line with `crontab -e`, for example
Sunday 08:17:

```
17 8 * * 0 /full/path/to/banking-orm-tool/update.sh
```

The computer must be awake at that time.
