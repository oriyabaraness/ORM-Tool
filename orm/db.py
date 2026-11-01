"""SQLite storage for the comparison index.

Schema (one row per thing, everything joinable):

    jurisdiction        IL, JO ...
    document            one regulation / directive / instruction
    risk_category       the taxonomy (mirrors orm.taxonomy)
    document_category   document -> category, from title/subject metadata
    provision           a numbered paragraph/section of a document's text
    provision_fts       full-text index over provision text
    provision_category  provision -> category, with evidence and review flag
    obligation_attr     structured facts pulled from a provision (deadlines,
                        frequencies) for side-by-side comparison
    expectation_hit     baseline expectation found in a jurisdiction, with the
                        provision that evidences it (drives gap analysis)
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

from . import taxonomy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("ORM_DB", os.path.join(HERE, "orm.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS jurisdiction (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    regulator   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (
    id           TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL REFERENCES jurisdiction(code),
    regulator    TEXT NOT NULL,
    ref          TEXT,
    title        TEXT NOT NULL,
    subject      TEXT,
    url          TEXT,
    pdf_url      TEXT,
    published    TEXT,
    lastmod      TEXT,
    source       TEXT NOT NULL,
    text_status  TEXT NOT NULL DEFAULT 'pending',
    text_path    TEXT,
    pages        INTEGER,
    chars        INTEGER,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS risk_category (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    orm_core    INTEGER NOT NULL,
    sort        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS document_category (
    document_id TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    category_id TEXT NOT NULL REFERENCES risk_category(id),
    score       REAL NOT NULL,
    method      TEXT NOT NULL,
    evidence    TEXT,
    PRIMARY KEY (document_id, category_id)
);

CREATE TABLE IF NOT EXISTS provision (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    ref         TEXT,
    text        TEXT NOT NULL,
    UNIQUE (document_id, seq)
);

CREATE VIRTUAL TABLE IF NOT EXISTS provision_fts USING fts5(
    text, content='provision', content_rowid='id'
);

CREATE TABLE IF NOT EXISTS provision_category (
    provision_id INTEGER NOT NULL REFERENCES provision(id) ON DELETE CASCADE,
    category_id  TEXT NOT NULL REFERENCES risk_category(id),
    score        REAL NOT NULL,
    evidence     TEXT,
    reviewed     INTEGER NOT NULL DEFAULT 0,  -- 0 unreviewed, 1 confirmed, -1 rejected
    PRIMARY KEY (provision_id, category_id)
);

CREATE TABLE IF NOT EXISTS obligation_attr (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    provision_id INTEGER NOT NULL REFERENCES provision(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,          -- deadline | frequency
    value_text   TEXT NOT NULL,          -- as written, e.g. "within 24 hours"
    hours        REAL                    -- normalized, for deadlines
);

CREATE TABLE IF NOT EXISTS expectation_hit (
    jurisdiction   TEXT NOT NULL,
    category_id    TEXT NOT NULL,
    expectation_id TEXT NOT NULL,
    provision_id   INTEGER NOT NULL REFERENCES provision(id) ON DELETE CASCADE,
    evidence       TEXT,
    PRIMARY KEY (jurisdiction, expectation_id, provision_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS ix_doc_jur ON document(jurisdiction);
CREATE INDEX IF NOT EXISTS ix_prov_doc ON provision(document_id);
CREATE INDEX IF NOT EXISTS ix_pc_cat ON provision_category(category_id);
CREATE INDEX IF NOT EXISTS ix_dc_cat ON document_category(category_id);
"""

JURISDICTIONS = (
    ("IL", "Israel", "Bank of Israel – Banking Supervision Department"),
    ("JO", "Jordan", "Central Bank of Jordan"),
)


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: str | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO jurisdiction(code, name, regulator) VALUES (?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET name=excluded.name, "
        "regulator=excluded.regulator",
        JURISDICTIONS)
    conn.executemany(
        "INSERT INTO risk_category(id, name, description, orm_core, sort) "
        "VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
        "description=excluded.description, orm_core=excluded.orm_core, "
        "sort=excluded.sort",
        [(c.id, c.name, c.description, int(c.orm_core), i)
         for i, c in enumerate(taxonomy.CATEGORIES)])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def upsert_document(conn: sqlite3.Connection, doc: dict) -> None:
    """Insert or refresh a document's metadata, keeping extraction state."""
    conn.execute(
        """
        INSERT INTO document(id, jurisdiction, regulator, ref, title, subject,
                             url, pdf_url, published, lastmod, source)
        VALUES (:id, :jurisdiction, :regulator, :ref, :title, :subject,
                :url, :pdf_url, :published, :lastmod, :source)
        ON CONFLICT(id) DO UPDATE SET
            regulator=excluded.regulator, ref=excluded.ref,
            title=excluded.title, subject=excluded.subject, url=excluded.url,
            pdf_url=COALESCE(excluded.pdf_url, document.pdf_url),
            published=excluded.published, lastmod=excluded.lastmod,
            source=excluded.source
        """,
        doc)


def replace_provisions(conn: sqlite3.Connection, document_id: str,
                       provisions: list[tuple[str, str]]) -> None:
    """Replace a document's provisions with (ref, text) pairs."""
    old = conn.execute("SELECT id, text FROM provision WHERE document_id=?",
                       (document_id,)).fetchall()
    for row in old:
        conn.execute(
            "INSERT INTO provision_fts(provision_fts, rowid, text) "
            "VALUES ('delete', ?, ?)", (row["id"], row["text"]))
    conn.execute("DELETE FROM provision WHERE document_id=?", (document_id,))
    for seq, (ref, text) in enumerate(provisions):
        cur = conn.execute(
            "INSERT INTO provision(document_id, seq, ref, text) VALUES (?,?,?,?)",
            (document_id, seq, ref, text))
        conn.execute("INSERT INTO provision_fts(rowid, text) VALUES (?, ?)",
                     (cur.lastrowid, text))


def clear_classification(conn: sqlite3.Connection) -> None:
    """Drop machine-generated tags; keep human review decisions."""
    conn.execute("DELETE FROM document_category")
    conn.execute("DELETE FROM provision_category WHERE reviewed = 0")
    conn.execute("DELETE FROM obligation_attr")
    conn.execute("DELETE FROM expectation_hit")


def search_provisions(conn: sqlite3.Connection, query: str,
                      limit: int = 200) -> list[int]:
    """Provision ids matching an FTS5 query (plain words are AND-ed)."""
    terms = [t for t in query.replace('"', " ").split() if t]
    if not terms:
        return []
    fts_query = " ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT rowid FROM provision_fts WHERE provision_fts MATCH ? "
        "ORDER BY rank LIMIT ?", (fts_query, limit)).fetchall()
    return [r[0] for r in rows]
