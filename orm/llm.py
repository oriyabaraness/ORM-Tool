"""Optional: have Claude read a directive and list its obligations.

    ANTHROPIC_API_KEY=... python orm_pipeline.py obligations --llm --document IL-BOI-PC-310

The result is saved to orm_texts/llm/<document id>.json. Commit that file and
every later build uses it in place of the pattern-based extraction for that
document (orm.obligations.build_all), with no API key needed at deploy time.

Guardrail: every obligation must quote a sentence that really appears in the
clause it cites. Anything that does not is dropped, so the model cannot add
duties the regulator never wrote.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3

import requests

from . import obligations

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("ORM_LLM_MODEL", "claude-sonnet-5-5")
CHUNK_CHARS = 14000

PROMPT = """You read banking regulation for an operational-risk team.

Below are numbered clauses from one regulation. List every obligation: a
sentence that requires someone to do something (shall, must, is required to,
should, is expected to). Skip definitions, scope statements and dates of
entry into force.

Return only JSON: {"obligations": [ ... ]}, one object per obligation with
  "seq":            the clause number shown in [brackets]
  "sentence":       the obligation sentence, copied exactly from the clause
  "actor":          who must act (e.g. "the board", "the bank"), or ""
  "action":         the duty in plain words, starting with a verb
  "modality":       "mandatory" (shall/must/required) or "expected" (should)
  "deadline_text":  e.g. "within 24 hours", or ""
  "deadline_hours": that deadline in hours as a number, or null
  "frequency":      e.g. "annually", or ""
  "evidence":       what an auditor would ask to see as proof

Clauses:
"""


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _chunks(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    out, cur, size = [], [], 0
    for r in rows:
        if cur and size + len(r["text"]) > CHUNK_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += len(r["text"])
    if cur:
        out.append(cur)
    return out


def _call(api_key: str, model: str, clauses: str) -> list[dict]:
    resp = requests.post(
        API_URL, timeout=180,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 8000,
              "messages": [{"role": "user", "content": PROMPT + clauses}]})
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json().get("content", [])
                   if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)).get("obligations", []) if m else []


def verify(items: list[dict], texts: dict[int, str]) -> list[dict]:
    """Keep only obligations whose sentence is really in the cited clause."""
    kept = []
    for it in items:
        try:
            seq = int(it.get("seq"))
        except (TypeError, ValueError):
            continue
        sentence = str(it.get("sentence") or "")
        if seq in texts and len(sentence) >= 20 and _norm(sentence) in _norm(texts[seq]):
            it["seq"] = seq
            it["modality"] = "expected" if it.get("modality") == "expected" else "mandatory"
            kept.append(it)
    return kept


def read_document(conn: sqlite3.Connection, document_id: str, *,
                  api_key: str | None = None, model: str = DEFAULT_MODEL,
                  log=print) -> int:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY to use --llm.")
    rows = conn.execute("SELECT seq, ref, text FROM provision WHERE document_id=? "
                        "ORDER BY seq", (document_id,)).fetchall()
    if not rows:
        raise LookupError(f"{document_id} has no extracted text.")
    texts = {r["seq"]: r["text"] for r in rows}
    found: list[dict] = []
    for i, chunk in enumerate(_chunks(rows), 1):
        clauses = "\n\n".join(f"[{r['seq']}] {r['ref'] or ''} {r['text']}" for r in chunk)
        raw = _call(api_key, model, clauses)
        good = verify(raw, texts)
        log(f"llm: {document_id} part {i}: {len(good)} of {len(raw)} obligations kept")
        found.extend(good)
    os.makedirs(obligations.LLM_CACHE_DIR, exist_ok=True)
    with open(obligations.llm_cache_path(document_id), "w", encoding="utf-8") as f:
        json.dump({"document_id": document_id, "model": model,
                   "read_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "obligations": found}, f, ensure_ascii=False, indent=1)
    return len(found)
