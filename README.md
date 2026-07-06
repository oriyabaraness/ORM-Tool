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

To add more PDFs to the searchable full-text corpus:

```bash
python boi_pdf_text.py
```
