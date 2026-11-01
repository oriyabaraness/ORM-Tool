# orm-revolut

Bank of Israel publications explorer and extraction utilities.

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
python jordan_cbj_financial_stability.py
python jordan_cbj_foreign_exchange_reserves.py
python jordan_cbj_fx_rates.py
python israel_boi_fx_reserves.py
python overnight_rate_analysis.py
python banking_sector_indicators.py
```

## Risk Compare (Israel vs Jordan POC)

The **Risk Compare** section lines up Bank of Israel and Central Bank of Jordan
regulation against one risk taxonomy (`orm/taxonomy.py`): governance,
operational resilience, outsourcing, IT/cyber, incident reporting, AML,
conduct, plus prudential categories.

It shows:

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
