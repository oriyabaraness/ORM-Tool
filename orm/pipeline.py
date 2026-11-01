"""Orchestrates ingest -> extract -> classify into the SQLite index."""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Callable

from . import classify as clf
from . import db, extract, sources

Log = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def ingest(conn: sqlite3.Connection, jurisdictions: set[str] | None = None,
           log: Log = _noop) -> int:
    """Load document metadata from every connector."""
    db.init(conn)
    docs = sources.all_documents(jurisdictions)
    for doc in docs:
        db.upsert_document(conn, doc)
    log(f"ingest: {len(docs)} documents")
    return len(docs)


def extract_texts(conn: sqlite3.Connection, *, fetch: bool = True,
                  jurisdictions: set[str] | None = None,
                  limit: int | None = None, retry_errors: bool = False,
                  log: Log = _noop) -> dict[str, int]:
    """Get text for each document and split it into provisions."""
    where = ["1=1"]
    params: list = []
    if jurisdictions:
        where.append(f"jurisdiction IN ({','.join('?' * len(jurisdictions))})")
        params.extend(sorted(jurisdictions))
    statuses = ("'pending'", "'no_text'", "'error'") if retry_errors else \
        ("'pending'", "'no_text'")
    where.append(f"text_status IN ({','.join(statuses)})")
    sql = f"SELECT id, pdf_url FROM document WHERE {' AND '.join(where)} ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    if limit:
        rows = rows[:limit]

    counts = {"ok": 0, "no_text": 0, "error": 0}
    for i, row in enumerate(rows, 1):
        doc_id = row["id"]
        try:
            text, pages, path, origin = extract.get_text(
                doc_id, row["pdf_url"], fetch=fetch)
            provisions = extract.split_provisions(text)
            db.replace_provisions(conn, doc_id, provisions)
            conn.execute(
                "UPDATE document SET text_status='ok', text_path=?, "
                "pages=COALESCE(?, pages), chars=?, error=NULL WHERE id=?",
                (path, pages, len(text), doc_id))
            counts["ok"] += 1
            log(f"[{i}/{len(rows)}] {doc_id}: {len(provisions)} provisions ({origin})")
        except LookupError as exc:
            conn.execute("UPDATE document SET text_status='no_text', error=? "
                         "WHERE id=?", (str(exc), doc_id))
            counts["no_text"] += 1
        except Exception as exc:  # network, bad PDF, ...
            conn.execute("UPDATE document SET text_status='error', error=? "
                         "WHERE id=?", (f"{type(exc).__name__}: {exc}"[:300], doc_id))
            counts["error"] += 1
            log(f"[{i}/{len(rows)}] {doc_id}: ERROR {exc}")
        conn.commit()
    log(f"extract: {counts}")
    return counts


def classify_all(conn: sqlite3.Connection, log: Log = _noop) -> dict[str, int]:
    """(Re)build every machine-generated tag, attribute and expectation hit."""
    db.clear_classification(conn)
    doc_cats: dict[str, set[str]] = {}
    for doc in conn.execute("SELECT id, title, subject FROM document"):
        tags = clf.classify_document(doc["title"], doc["subject"] or "")
        doc_cats[doc["id"]] = {t.category_id for t in tags}
        conn.executemany(
            "INSERT INTO document_category(document_id, category_id, score, "
            "method, evidence) VALUES (?,?,?,?,?)",
            [(doc["id"], t.category_id, t.score, t.method, t.evidence) for t in tags])

    n_prov = n_attr = n_exp = 0
    rows = conn.execute(
        "SELECT p.id, p.document_id, p.text, d.jurisdiction FROM provision p "
        "JOIN document d ON d.id = p.document_id").fetchall()
    for p in rows:
        tags = clf.classify_provision(p["text"], doc_cats.get(p["document_id"]))
        conn.executemany(
            "INSERT OR IGNORE INTO provision_category(provision_id, category_id, "
            "score, evidence) VALUES (?,?,?,?)",
            [(p["id"], t.category_id, t.score, t.evidence) for t in tags])
        n_prov += bool(tags)
        for value, hours in clf.extract_deadlines(p["text"]):
            conn.execute("INSERT INTO obligation_attr(provision_id, kind, "
                         "value_text, hours) VALUES (?, 'deadline', ?, ?)",
                         (p["id"], value, hours))
            n_attr += 1
        for value in clf.extract_frequencies(p["text"]):
            conn.execute("INSERT INTO obligation_attr(provision_id, kind, "
                         "value_text) VALUES (?, 'frequency', ?)", (p["id"], value))
            n_attr += 1
        for eid, evidence in clf.match_expectations(p["text"]):
            cat = next(c for c, e in clf.taxonomy.ALL_EXPECTATIONS if e.id == eid)
            conn.execute(
                "INSERT OR IGNORE INTO expectation_hit(jurisdiction, category_id, "
                "expectation_id, provision_id, evidence) VALUES (?,?,?,?,?)",
                (p["jurisdiction"], cat, eid, p["id"], evidence))
            n_exp += 1
    db.set_meta(conn, "classified_at", dt.datetime.now().isoformat(timespec="seconds"))
    conn.commit()
    stats = {"documents": len(doc_cats), "tagged_provisions": n_prov,
             "attributes": n_attr, "expectation_hits": n_exp}
    log(f"classify: {stats}")
    return stats


def build(path: str | None = None, *, fetch: bool = False,
          jurisdictions: set[str] | None = None, limit: int | None = None,
          retry_errors: bool = False, log: Log = _noop) -> None:
    """Full run. With fetch=False only cached/manual text is used (fast)."""
    with db.session(path) as conn:
        ingest(conn, jurisdictions, log)
        extract_texts(conn, fetch=fetch, jurisdictions=jurisdictions,
                      limit=limit, retry_errors=retry_errors, log=log)
        classify_all(conn, log)
