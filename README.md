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

The Streamlit app expects the CSV catalog files in this directory and extracted text files under `boi_texts/`.
