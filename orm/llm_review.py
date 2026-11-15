"""Optional: have Claude compare a clause with its equivalent for an ORM manager.

    ANTHROPIC_API_KEY=... python orm_pipeline.py reviews --llm --document IL-BOI-PC-301

Each pair is saved to orm_texts/llm_reviews/<home id>__<other id or none>.json
with a key made from both clause texts. Commit those files and the Compare
screen shows the analysis in place of the rule-based review card, with no API
key needed when the app runs. A clause whose text changes gets a new key, so
the old analysis is no longer shown and the next run analyses it again.

Guardrails: every point must quote a sentence that really appears in one of
the two clauses, or it is dropped. Penalties, costs and severity that the
clauses do not mention are removed. A difference in the text is not a
compliance gap.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import re
import sqlite3

import requests

from . import match, queries
from .llm import API_URL, DEFAULT_MODEL, _norm

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "orm_texts", "llm_reviews")
PROMPT_VERSION = "1"
MAX_CLAUSE_CHARS = 6000
STATUSES = ("aligned", "differs", "no_equivalent", "not_a_requirement")

PROMPT = """You help the operational-risk (ORM) manager of a bank that operates
in both {home} and {other}. Compare the two regulation clauses below.

Return only JSON:
{{
  "status": "aligned" | "differs" | "no_equivalent" | "not_a_requirement",
  "headline": one sentence, the practical difference in plain words,
  "points": up to 4 objects {{"text": short bullet, "quotes": [{{"from": "home" | "other",
            "text": the exact sentence copied from that clause}}]}},
  "so_what": one sentence on what this means for a bank in both countries,
  "check_internally": up to 2 questions the ORM manager should ask the control owner
}}

Rules:
- "not_a_requirement" when either clause is a heading, table of contents,
  definition or scope line (e.g. "Chapter 1 General 1..").
- "no_equivalent" when there is no {other} clause, or it does not cover the
  same requirement.
- Points cover, only where the text says so: who must act, what must be done,
  deadline or frequency, how strict the wording is (shall/must vs should), and
  what evidence an auditor would ask for.
- Every point needs at least one quote copied word for word from the clause.
- Never invent penalties, costs, severity or the bank's own controls.
- A difference in the text is not a compliance gap. Say so where relevant.
- "so_what" may say which requirement is stricter, whether one control could
  cover both, or that {other} states nothing comparable.

{home} clause ("home"):
{home_text}

{other} clause ("other"):
{other_text}
"""

is_not_a_requirement = match.is_not_a_requirement
_INVENTED = re.compile(
    r"\b(?:penalt\w*|fines?|fined|costs?|costly|severity|severe)\b", re.I)


def review_key(home_text: str, other_text: str | None) -> str:
    raw = "\x00".join((PROMPT_VERSION, _norm(home_text or ""), _norm(other_text or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(home_id: int, other_id: int | None) -> str:
    return os.path.join(CACHE_DIR, f"{home_id}__{other_id if other_id else 'none'}.json")


def _call(api_key: str, model: str, prompt: str) -> tuple[dict, dict]:
    resp = requests.post(
        API_URL, timeout=180,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 1500,
              "messages": [{"role": "user", "content": prompt}]})
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", [])
                   if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    return (json.loads(m.group(0)) if m else {}), body.get("usage", {})


def _clean(text, sources: str) -> str:
    """Drop sentences that bring in penalties, costs or severity the clauses never state."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        invented = [w for w in _INVENTED.findall(sentence)
                    if not re.search(rf"\b{re.escape(w)}\b", sources, re.I)]
        if sentence and not invented:
            kept.append(sentence)
    return " ".join(kept)


def verify(raw: dict, home_text: str, other_text: str | None) -> dict | None:
    """Keep only what the two clauses support. None when nothing usable is left."""
    texts = {"home": _norm(home_text or ""), "other": _norm(other_text or "")}
    sources = f"{home_text or ''} {other_text or ''}"
    status = raw.get("status") if raw.get("status") in STATUSES else "differs"
    if other_text is None and status in {"aligned", "differs"}:
        status = "no_equivalent"
    if is_not_a_requirement(home_text) or (other_text and is_not_a_requirement(other_text)):
        status = "not_a_requirement"

    points = []
    for point in raw.get("points") or []:
        if not isinstance(point, dict):
            continue
        text = _clean(point.get("text"), sources)
        quotes = [q for q in point.get("quotes") or [] if isinstance(q, dict)]
        good = []
        for q in quotes:
            side = q.get("from") if q.get("from") in texts else ""
            quote = re.sub(r"\s+", " ", str(q.get("text") or "")).strip()
            if side and len(_norm(quote)) >= 15 and _norm(quote) in texts[side]:
                good.append({"from": side, "text": quote})
        if text and good and len(good) == len(quotes):
            points.append({"text": text, "quotes": good})

    headline = _clean(raw.get("headline"), sources)
    if status == "not_a_requirement":
        return {"status": status,
                "headline": headline or ("This clause is a heading, table of contents, "
                                         "definition or scope line, not a requirement."),
                "points": [], "so_what": "", "check_internally": []}
    if not headline:
        return None
    questions = [q for q in (_clean(q, sources) for q in raw.get("check_internally") or [])
                 if q][:2]
    return {"status": status, "headline": headline, "points": points[:4],
            "so_what": _clean(raw.get("so_what"), sources),
            "check_internally": questions}


def analyse(home_name: str, home_text: str, other_name: str,
            other_text: str | None, *, api_key: str, model: str = DEFAULT_MODEL
            ) -> tuple[dict | None, dict]:
    """Ask Claude about one pair. Headings and contents lines skip the call."""
    if is_not_a_requirement(home_text):
        return verify({"status": "not_a_requirement"}, home_text, other_text), {}
    prompt = PROMPT.format(
        home=home_name, other=other_name,
        home_text=(home_text or "")[:MAX_CLAUSE_CHARS],
        other_text=(other_text or "")[:MAX_CLAUSE_CHARS]
        or f"(none: no {other_name} clause was found for this requirement)")
    raw, usage = _call(api_key, model, prompt)
    return verify(raw, home_text, other_text), usage


def pairs(conn: sqlite3.Connection, document_id: str) -> list[dict]:
    """The pairs the Compare review column shows for one directive: each clause
    with its top same-clause equivalent per country, or with none when that
    country has text in the clause's risk categories but no equivalent."""
    doc = conn.execute("SELECT jurisdiction FROM document WHERE id=?",
                       (document_id,)).fetchone()
    if doc is None:
        raise LookupError(f"{document_id} is not in the index.")
    home = doc["jurisdiction"]
    others = [r[0] for r in conn.execute(
        "SELECT DISTINCT jurisdiction FROM document WHERE jurisdiction != ? "
        "ORDER BY jurisdiction", (home,))]
    counts = {j: queries.category_counts(conn, j) for j in others}
    rows = queries.directive_clauses(conn, document_id)
    out = []
    for _, r in rows.iterrows():
        pid = int(r["provision_id"])
        cats = [c for c in str(r["categories"] or "").split(",") if c]
        eq = queries.equivalents(conn, pid)
        if not eq.empty:
            eq = eq[eq["text_similarity"].map(match.same_clause)]
        for j in others:
            mj = eq[eq["jurisdiction"] == j] if not eq.empty else eq
            if not mj.empty:
                m = mj.iloc[0]
                out.append({"home_id": pid, "home_text": r["text"], "home_ref": r["ref"],
                            "other": j, "other_id": int(m["provision_id"]),
                            "other_text": m["text"], "other_ref": m["ref"]})
            elif any(counts[j].get(c, 0) > 0 for c in cats):
                out.append({"home_id": pid, "home_text": r["text"], "home_ref": r["ref"],
                            "other": j, "other_id": None, "other_text": None,
                            "other_ref": ""})
    return out


def _write(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def review_document(conn: sqlite3.Connection, document_id: str, names: dict[str, str],
                    *, api_key: str | None = None, model: str = DEFAULT_MODEL,
                    limit: int | None = None, force: bool = False, log=print) -> dict:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY to use --llm.")
    home = conn.execute("SELECT jurisdiction FROM document WHERE id=?",
                        (document_id,)).fetchone()["jurisdiction"]
    stats = {"pairs": 0, "analysed": 0, "cached": 0, "skipped": 0,
             "input_tokens": 0, "output_tokens": 0}
    for p in pairs(conn, document_id):
        stats["pairs"] += 1
        key = review_key(p["home_text"], p["other_text"])
        path = cache_path(p["home_id"], p["other_id"])
        if not force and load(p["home_text"], p["other_text"]) is not None:
            stats["cached"] += 1
            continue
        if limit is not None and stats["analysed"] >= limit:
            stats["skipped"] += 1
            continue
        result, usage = analyse(names.get(home, home), p["home_text"],
                                names.get(p["other"], p["other"]), p["other_text"],
                                api_key=api_key, model=model)
        stats["input_tokens"] += int(usage.get("input_tokens") or 0)
        stats["output_tokens"] += int(usage.get("output_tokens") or 0)
        stats["analysed"] += 1
        if result is None:
            log(f"llm-review: {p['home_ref'] or p['home_id']} vs {p['other']}: "
                "nothing verifiable, kept the rule-based review")
            continue
        _write(path, {"key": key, "document_id": document_id,
                      "home_provision_id": p["home_id"], "home_ref": p["home_ref"],
                      "other_provision_id": p["other_id"], "other_ref": p["other_ref"],
                      "other_jurisdiction": p["other"], "model": model,
                      "analysed_at": dt.datetime.now().isoformat(timespec="seconds"),
                      "usage": usage, "analysis": result})
        log(f"llm-review: {p['home_ref'] or p['home_id']} vs {p['other']}: "
            f"{result['status']}, {len(result['points'])} points kept")
    return stats


_INDEX: dict = {"stamp": None, "by_key": {}}


def _index() -> dict[str, dict]:
    try:
        stamp = os.stat(CACHE_DIR).st_mtime_ns
    except OSError:
        return {}
    if _INDEX["stamp"] != (CACHE_DIR, stamp):
        by_key = {}
        for path in glob.glob(os.path.join(CACHE_DIR, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    record = json.load(f)
            except (OSError, ValueError):
                continue
            if record.get("key") and record.get("analysis"):
                by_key[record["key"]] = record["analysis"]
        _INDEX.update(stamp=(CACHE_DIR, stamp), by_key=by_key)
    return _INDEX["by_key"]


def load(home_text: str, other_text: str | None) -> dict | None:
    """The saved analysis for exactly these two texts, or None."""
    return _index().get(review_key(home_text, other_text))
