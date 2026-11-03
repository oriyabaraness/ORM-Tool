"""Read-side queries behind the comparison views (no Streamlit here, so they
are unit-testable and reusable from an API later)."""
from __future__ import annotations

import sqlite3

import pandas as pd

from . import db, taxonomy

JURISDICTIONS = ("IL", "JO")
JURISDICTION_NAMES = {"IL": "Israel", "JO": "Jordan"}


def _df(conn: sqlite3.Connection, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def index_status(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per jurisdiction: documents, with text, provisions."""
    return _df(conn, """
        SELECT d.jurisdiction,
               COUNT(*) AS documents,
               SUM(d.text_status = 'ok') AS with_text,
               (SELECT COUNT(*) FROM provision p JOIN document x
                  ON x.id = p.document_id
                WHERE x.jurisdiction = d.jurisdiction) AS provisions
        FROM document d GROUP BY d.jurisdiction ORDER BY d.jurisdiction
    """)


def coverage_matrix(conn: sqlite3.Connection, orm_only: bool = False) -> pd.DataFrame:
    """One row per category; per jurisdiction: docs, docs with text,
    tagged provisions, most recent date and a coverage level.

    level: 'none'     -- no document mapped to the category
           'metadata' -- documents mapped from titles, no text yet
           'text'     -- provisions extracted and tagged
    """
    cats = _df(conn, "SELECT id, name, orm_core, sort FROM risk_category ORDER BY sort")
    if orm_only:
        cats = cats[cats["orm_core"] == 1]
    docs = _df(conn, """
        SELECT dc.category_id, d.jurisdiction,
               COUNT(*) AS docs,
               SUM(d.text_status = 'ok') AS docs_text,
               MAX(COALESCE(NULLIF(d.published, ''), d.lastmod)) AS latest
        FROM document_category dc JOIN document d ON d.id = dc.document_id
        GROUP BY 1, 2
    """)
    provs = _df(conn, """
        SELECT pc.category_id, d.jurisdiction, COUNT(*) AS provisions
        FROM provision_category pc
        JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.reviewed >= 0
        GROUP BY 1, 2
    """)
    out = cats.rename(columns={"id": "category_id"})[["category_id", "name", "orm_core"]]
    for j in JURISDICTIONS:
        dj = docs[docs["jurisdiction"] == j].drop(columns="jurisdiction")
        pj = provs[provs["jurisdiction"] == j].drop(columns="jurisdiction")
        dj = dj.add_prefix(f"{j}_").rename(columns={f"{j}_category_id": "category_id"})
        pj = pj.add_prefix(f"{j}_").rename(columns={f"{j}_category_id": "category_id"})
        out = out.merge(dj, on="category_id", how="left").merge(pj, on="category_id", how="left")
        for col in (f"{j}_docs", f"{j}_docs_text", f"{j}_provisions"):
            out[col] = out[col].fillna(0).astype(int)
        out[f"{j}_latest"] = out[f"{j}_latest"].fillna("")
        out[f"{j}_level"] = [
            "text" if p > 0 else ("metadata" if d > 0 else "none")
            for d, p in zip(out[f"{j}_docs"], out[f"{j}_provisions"])]
    return out.reset_index(drop=True)


def category_documents(conn: sqlite3.Connection, category_id: str,
                       jurisdiction: str) -> pd.DataFrame:
    return _df(conn, """
        SELECT d.id, d.ref, d.title, d.url, d.pdf_url, d.text_status,
               COALESCE(NULLIF(d.published, ''), d.lastmod) AS date,
               dc.method, dc.evidence, dc.score
        FROM document_category dc JOIN document d ON d.id = dc.document_id
        WHERE dc.category_id = ? AND d.jurisdiction = ?
        ORDER BY dc.score DESC, date DESC
    """, (category_id, jurisdiction))


def category_provisions(conn: sqlite3.Connection, category_id: str,
                        jurisdiction: str, query: str = "",
                        limit: int = 50) -> pd.DataFrame:
    """Provisions tagged with the category, strongest first; optional
    full-text filter."""
    params: list = [category_id, jurisdiction]
    extra = ""
    if query.strip():
        ids = db.search_provisions(conn, query, limit=2000)
        if not ids:
            return pd.DataFrame(columns=["provision_id", "doc_ref", "doc_title",
                                         "ref", "text", "score", "evidence",
                                         "deadlines", "frequencies"])
        extra = f" AND p.id IN ({','.join(str(int(i)) for i in ids)})"
    params.append(limit)
    df = _df(conn, f"""
        SELECT p.id AS provision_id, d.id AS document_id, d.ref AS doc_ref,
               d.title AS doc_title, d.pdf_url, p.ref, p.text, pc.score,
               pc.evidence, pc.reviewed
        FROM provision_category pc
        JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.category_id = ? AND d.jurisdiction = ? AND pc.reviewed >= 0 {extra}
        ORDER BY pc.reviewed DESC, pc.score DESC, d.id, p.seq
        LIMIT ?
    """, params)
    attrs = provision_attributes(conn, df["provision_id"].tolist())
    df["deadlines"] = [attrs.get(i, {}).get("deadline", []) for i in df["provision_id"]]
    df["frequencies"] = [attrs.get(i, {}).get("frequency", []) for i in df["provision_id"]]
    return df


def provision_attributes(conn: sqlite3.Connection,
                         provision_ids: list[int]) -> dict[int, dict[str, list[str]]]:
    if not provision_ids:
        return {}
    rows = conn.execute(
        f"SELECT provision_id, kind, value_text FROM obligation_attr "
        f"WHERE provision_id IN ({','.join(str(int(i)) for i in provision_ids)})"
    ).fetchall()
    out: dict[int, dict[str, list[str]]] = {}
    for r in rows:
        bucket = out.setdefault(r["provision_id"], {}).setdefault(r["kind"], [])
        if r["value_text"] not in bucket:
            bucket.append(r["value_text"])
    return out


def expectation_table(conn: sqlite3.Connection, category_id: str) -> pd.DataFrame:
    """Gap analysis for one category.

    status per jurisdiction:
        found        -- at least one provision matches the expectation
        not found    -- the jurisdiction has text in this category but no match
        not assessed -- no text available yet for this category
    """
    cat = taxonomy.BY_ID[category_id]
    rows = []
    for e in cat.expectations:
        row = {"expectation_id": e.id, "expectation": e.label}
        for j in JURISDICTIONS:
            assessed = conn.execute("""
                SELECT COUNT(*) FROM provision_category pc
                JOIN provision p ON p.id = pc.provision_id
                JOIN document d ON d.id = p.document_id
                WHERE pc.category_id = ? AND d.jurisdiction = ?
            """, (category_id, j)).fetchone()[0] > 0
            hit = conn.execute("""
                SELECT eh.evidence, d.ref, d.title, p.ref AS pref
                FROM expectation_hit eh
                JOIN provision p ON p.id = eh.provision_id
                JOIN document d ON d.id = p.document_id
                LEFT JOIN provision_category pc
                  ON pc.provision_id = p.id AND pc.category_id = eh.category_id
                WHERE eh.jurisdiction = ? AND eh.expectation_id = ?
                ORDER BY (pc.provision_id IS NOT NULL) DESC, d.id, p.seq
                LIMIT 1
            """, (j, e.id)).fetchone()
            if hit:
                status = "found"
                source = " ".join(x for x in (hit["ref"] or hit["title"], hit["pref"]) if x)
                evidence = hit["evidence"]
            else:
                status = "not found" if assessed else "not assessed"
                source = evidence = ""
            row[f"{j}_status"] = status
            row[f"{j}_source"] = source
            row[f"{j}_evidence"] = evidence
        rows.append(row)
    return pd.DataFrame(rows)


def deadlines(conn: sqlite3.Connection, category_id: str | None = None) -> pd.DataFrame:
    """Every extracted deadline, optionally within one category."""
    params: list = []
    cat_join = ""
    if category_id:
        cat_join = ("JOIN provision_category pc ON pc.provision_id = p.id "
                    "AND pc.category_id = ? AND pc.reviewed >= 0")
        params.append(category_id)
    return _df(conn, f"""
        SELECT d.jurisdiction, d.ref AS doc_ref, d.title AS doc_title,
               p.ref, oa.value_text, oa.hours, p.text
        FROM obligation_attr oa
        JOIN provision p ON p.id = oa.provision_id
        JOIN document d ON d.id = p.document_id
        {cat_join}
        WHERE oa.kind = 'deadline'
        ORDER BY oa.hours, d.jurisdiction
    """, params)


# --- clause explorer ------------------------------------------------------------

def category_counts(conn: sqlite3.Connection, jurisdiction: str) -> dict[str, int]:
    """Tagged clauses per category for one country."""
    rows = conn.execute("""
        SELECT pc.category_id, COUNT(*) FROM provision_category pc
        JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE d.jurisdiction = ? AND pc.reviewed >= 0
        GROUP BY 1
    """, (jurisdiction,)).fetchall()
    return {r[0]: r[1] for r in rows}


def clauses(conn: sqlite3.Connection, jurisdiction: str, category_id: str,
            query: str = "", limit: int = 300) -> pd.DataFrame:
    """Clauses of one country in one category, in document order, with how
    many cross-country equivalents each has."""
    extra = ""
    if query.strip():
        ids = db.search_provisions(conn, query, limit=5000)
        if not ids:
            return pd.DataFrame(columns=["provision_id", "document_id", "doc_ref",
                                         "doc_title", "ref", "text", "matches"])
        extra = f" AND p.id IN ({','.join(str(int(i)) for i in ids)})"
    return _df(conn, f"""
        SELECT p.id AS provision_id, d.id AS document_id, d.ref AS doc_ref,
               d.title AS doc_title, p.ref, p.text,
               (SELECT COUNT(*) FROM provision_match m
                 WHERE m.provision_id = p.id AND m.category_id = pc.category_id)
                 AS matches
        FROM provision_category pc
        JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.category_id = ? AND d.jurisdiction = ? AND pc.reviewed >= 0 {extra}
        ORDER BY d.ref, d.id, p.seq
        LIMIT ?
    """, (category_id, jurisdiction, limit))


def clause(conn: sqlite3.Connection, provision_id: int) -> dict | None:
    row = conn.execute("""
        SELECT p.id AS provision_id, p.ref, p.text, d.id AS document_id,
               d.ref AS doc_ref, d.title AS doc_title, d.jurisdiction,
               d.pdf_url, d.url
        FROM provision p JOIN document d ON d.id = p.document_id
        WHERE p.id = ?
    """, (int(provision_id),)).fetchone()
    return dict(row) if row else None


def equivalents(conn: sqlite3.Connection, provision_id: int,
                category_id: str) -> pd.DataFrame:
    """The clause's best matches in other countries, strongest first."""
    df = _df(conn, """
        SELECT m.match_id AS provision_id, m.score, m.text_similarity,
               m.shared_expectations, m.shared_terms,
               d.jurisdiction, d.ref AS doc_ref, d.title AS doc_title,
               d.pdf_url, d.url, p.ref, p.text
        FROM provision_match m
        JOIN provision p ON p.id = m.match_id
        JOIN document d ON d.id = p.document_id
        WHERE m.provision_id = ? AND m.category_id = ?
        ORDER BY d.jurisdiction, m.score DESC
    """, (int(provision_id), category_id))
    labels = {e.id: e.label for _c, e in taxonomy.ALL_EXPECTATIONS}
    df["shared_expectation_labels"] = [
        [labels.get(x, x) for x in (s or "").split(",") if x]
        for s in df["shared_expectations"]]
    return df


def has_text_in_category(conn: sqlite3.Connection, jurisdiction: str,
                         category_id: str) -> bool:
    return category_counts(conn, jurisdiction).get(category_id, 0) > 0


# --- full directive reader ----------------------------------------------------

def documents(conn: sqlite3.Connection, jurisdiction: str) -> pd.DataFrame:
    """Every document of one country, with how much of it was read."""
    return _df(conn, """
        SELECT d.id AS document_id, d.ref AS doc_ref, d.title AS doc_title,
               d.text_status, d.error, d.pages, d.chars, d.pdf_url, d.url,
               (SELECT COUNT(*) FROM provision p WHERE p.document_id = d.id)
                 AS provisions,
               (SELECT COALESCE(SUM(LENGTH(REPLACE(p.text, ' ', ''))), 0) FROM provision p
                 WHERE p.document_id = d.id) AS provision_chars,
               (SELECT COUNT(DISTINCT pc.provision_id) FROM provision_category pc
                 JOIN provision p ON p.id = pc.provision_id
                 WHERE p.document_id = d.id AND pc.reviewed >= 0) AS tagged
        FROM document d
        WHERE d.jurisdiction = ?
        ORDER BY (d.text_status = 'ok') DESC, d.ref, d.title
    """, (jurisdiction,))


def document_provisions(conn: sqlite3.Connection, document_id: str) -> pd.DataFrame:
    """Every provision of one document in reading order, with its risk tags
    (comma-separated category ids; empty when the clause wasn't tagged)."""
    return _df(conn, """
        SELECT p.id AS provision_id, p.seq, p.ref, p.text,
               COALESCE((SELECT GROUP_CONCAT(pc.category_id) FROM provision_category pc
                 WHERE pc.provision_id = p.id AND pc.reviewed >= 0), '') AS categories
        FROM provision p
        WHERE p.document_id = ?
        ORDER BY p.seq
    """, (document_id,))
