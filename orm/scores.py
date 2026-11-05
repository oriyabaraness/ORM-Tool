"""Layer 5 of the ORM Analysis Standard: scores and the delta statement.

  Regulatory Intensity Index (RII)  0-100 per country and risk category:
      100 x (0.35 Coverage + 0.25 Bindingness + 0.20 Specificity
             + 0.10 Recency + 0.10 Enforcement)
      A component that can't be measured is left out and the remaining
      weights are rescaled, so missing data never counts as zero.
  Entry Readiness   per home -> target pair: share of the target's assessed
      obligations that home controls already meet (Equivalent or Looser).
  Confidence grade  A full text + specialist-reviewed · B full text, machine
      only · C titles and metadata only.

No Streamlit here: everything returns plain dicts / DataFrames.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

import pandas as pd

from . import rdl, taxonomy, verdicts

PENALTY = re.compile(r"\bpenalt\w*|\bsanction\w*|\bfine[sd]?\b|\badministrative\s+fines?\b|"
                     r"\bdisciplinary\s+(?:action|measure)", re.I)
NEW_CONTROL = "No home control"


def _recency(latest: str, today: dt.date | None = None) -> float | None:
    try:
        when = dt.date.fromisoformat((latest or "")[:10])
    except ValueError:
        return None
    years = ((today or dt.date.today()) - when).days / 365.25
    full, zero = rdl.RECENCY_FULL_YEARS, rdl.RECENCY_ZERO_YEARS
    if years <= full:
        return 1.0
    if years >= zero:
        return 0.0
    return round(1 - (years - full) / (zero - full), 3)


def _grade(clauses: int, confirmed: int) -> str:
    if clauses == 0:
        return "C"
    return "A" if confirmed / clauses >= rdl.GRADE_A_SHARE else "B"


def intensity(conn: sqlite3.Connection, jurisdiction: str, category_id: str,
              today: dt.date | None = None) -> dict:
    """The Regulatory Intensity Index and its components for one cell."""
    auth = rdl.authority(jurisdiction, category_id)
    clauses = conn.execute("""
        SELECT p.id, p.document_id, p.text, pc.reviewed FROM provision_category pc
        JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.category_id = ? AND d.jurisdiction = ? AND pc.reviewed >= 0
    """, (category_id, jurisdiction)).fetchall()
    ids = [c["id"] for c in clauses]
    recs = [r for rs in verdicts.records_by_provision(conn, ids).values() for r in rs]
    latest = conn.execute("""
        SELECT MAX(COALESCE(NULLIF(d.published, ''), d.lastmod))
        FROM document_category dc JOIN document d ON d.id = dc.document_id
        WHERE dc.category_id = ? AND d.jurisdiction = ?
    """, (category_id, jurisdiction)).fetchone()[0]

    parts: dict[str, float | None] = dict.fromkeys(rdl.RII_WEIGHTS)
    cat = taxonomy.BY_ID[category_id]
    if clauses and cat.expectations:
        found = conn.execute("""
            SELECT COUNT(DISTINCT expectation_id) FROM expectation_hit
            WHERE jurisdiction = ? AND category_id = ?
        """, (jurisdiction, category_id)).fetchone()[0]
        parts["coverage"] = found / len(cat.expectations)
    if recs:
        parts["bindingness"] = sum(rdl.FORCE_WEIGHT[r["force"]] for r in recs) / len(recs)
        parts["specificity"] = sum(
            1 for r in recs if r["measure"] or r["frequency_months"] is not None
        ) / len(recs)
    if clauses:
        docs: dict[str, bool] = {}
        for c in clauses:
            docs[c["document_id"]] = docs.get(c["document_id"], False) or \
                bool(PENALTY.search(c["text"]))
        parts["enforcement"] = sum(docs.values()) / len(docs)
    parts["recency"] = _recency(latest, today) if latest else None

    measured = {k: v for k, v in parts.items() if v is not None}
    rii = None
    if clauses and measured:
        weight = sum(rdl.RII_WEIGHTS[k] for k in measured)
        rii = round(100 * sum(rdl.RII_WEIGHTS[k] * v for k, v in measured.items())
                    / weight, 1)
    confirmed = sum(1 for c in clauses if c["reviewed"] == 1)
    return {"jurisdiction": jurisdiction, "category_id": category_id,
            "rii": rii, **{k: (round(v, 3) if v is not None else None)
                           for k, v in parts.items()},
            "clauses": len(clauses), "records": len(recs),
            "grade": _grade(len(clauses), confirmed),
            "scope": auth.scope, "authority": auth.authority}


def intensity_table(conn: sqlite3.Connection, jurisdictions: tuple[str, ...],
                    category_ids: list[str] | None = None) -> pd.DataFrame:
    cats = category_ids or [c.id for c in taxonomy.CATEGORIES]
    return pd.DataFrame([intensity(conn, j, c) for c in cats for j in jurisdictions])


# --- Entry Readiness and the delta statement --------------------------------------

def _has_text(conn, jurisdiction: str, category_id: str) -> bool:
    return conn.execute("""
        SELECT 1 FROM provision_category pc JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.category_id = ? AND d.jurisdiction = ? AND pc.reviewed >= 0 LIMIT 1
    """, (category_id, jurisdiction)).fetchone() is not None


def _clauses(conn, jurisdiction: str, category_id: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT p.id, p.ref, p.text, d.ref AS doc_ref, d.title AS doc_title
        FROM provision_category pc JOIN provision p ON p.id = pc.provision_id
        JOIN document d ON d.id = p.document_id
        WHERE pc.category_id = ? AND d.jurisdiction = ? AND pc.reviewed >= 0
        ORDER BY d.ref, d.id, p.seq
    """, (category_id, jurisdiction)).fetchall()


def _where(row) -> str:
    return " ".join(x for x in (row["doc_ref"] or row["doc_title"], row["ref"]) if x)


def readiness_items(conn: sqlite3.Connection, home: str, target: str,
                    category_ids: list[str] | None = None) -> pd.DataFrame:
    """One row per target obligation (and per gap): what a firm from `home`
    must do about it to operate in `target`."""
    cats = category_ids or [c for c in rdl.LENSES]
    rows = []
    for cat in cats:
        auth = rdl.authority(target, cat)
        home_text, target_text = _has_text(conn, home, cat), _has_text(conn, target, cat)
        # target obligations, judged against the best home equivalent
        for t in _clauses(conn, target, cat):
            best = conn.execute("""
                SELECT m.match_id, m.score, v.verdict, v.reason, p.ref,
                       d.ref AS doc_ref, d.title AS doc_title,
                       r.status AS review
                FROM provision_match m
                JOIN provision p ON p.id = m.match_id
                JOIN document d ON d.id = p.document_id
                LEFT JOIN provision_verdict v ON v.provision_id = m.provision_id
                     AND v.match_id = m.match_id AND v.category_id = m.category_id
                LEFT JOIN verdict_review r ON r.provision_id = m.provision_id
                     AND r.match_id = m.match_id AND r.category_id = m.category_id
                WHERE m.provision_id = ? AND m.category_id = ? AND d.jurisdiction = ?
                  AND COALESCE(r.status, 0) >= 0
                ORDER BY COALESCE(r.status, 0) DESC, m.score DESC LIMIT 1
            """, (t["id"], cat, home)).fetchone()
            if best:
                # stored verdict reads target -> home; the client reads home -> target
                verdict = rdl.invert(best["verdict"] or rdl.NOT_ASSESSED)
                reason = best["reason"] or ""
                home_where = _where(best)
                reviewed = best["review"] == 1
            elif home_text:
                verdict, reason, home_where, reviewed = (
                    NEW_CONTROL, "No equivalent clause in the home country", "", False)
            else:
                verdict, reason, home_where, reviewed = (
                    rdl.NOT_ASSESSED, "Home country has no indexed text here", "", False)
            rows.append({"category_id": cat, "kind": "target obligation",
                         "verdict": verdict, "reason": reason,
                         "target_clause": _where(t), "home_clause": home_where,
                         "text": t["text"], "reviewed": reviewed})
        # home obligations the target doesn't set at all
        for h in _clauses(conn, home, cat):
            has_match = conn.execute("""
                SELECT 1 FROM provision_match m JOIN provision p ON p.id = m.match_id
                JOIN document d ON d.id = p.document_id
                WHERE m.provision_id = ? AND m.category_id = ? AND d.jurisdiction = ?
                LIMIT 1""", (h["id"], cat, target)).fetchone()
            if has_match:
                continue
            v = verdicts.unmatched_verdict(target, cat, target_text)
            if v.verdict == rdl.GAP or auth.scope == rdl.OTHER:
                rows.append({"category_id": cat, "kind": "home obligation",
                             "verdict": v.verdict, "reason": v.reason,
                             "target_clause": "", "home_clause": _where(h),
                             "text": h["text"], "reviewed": False})
    cols = ["category_id", "kind", "verdict", "reason", "target_clause",
            "home_clause", "text", "reviewed"]
    df = pd.DataFrame(rows, columns=cols)
    df.insert(1, "category", df["category_id"].map(lambda c: taxonomy.BY_ID[c].name))
    return df


def readiness(items: pd.DataFrame) -> dict:
    """Entry Readiness, the counts behind it and its confidence grade."""
    target_rows = items[items["kind"] == "target obligation"]
    count = target_rows["verdict"].value_counts().to_dict()
    met = count.get(rdl.EQUIVALENT, 0) + count.get(rdl.LOOSER, 0)
    stricter = count.get(rdl.STRICTER, 0)
    new = count.get(rdl.DIFFERENT, 0) + count.get(NEW_CONTROL, 0)
    assessed = met + stricter + new
    gaps = int((items["verdict"] == rdl.GAP).sum())
    reviewed = int(target_rows["reviewed"].sum())
    return {"readiness": round(100 * met / assessed, 1) if assessed else None,
            "met": met, "stricter": stricter, "new_mechanisms": new, "gaps": gaps,
            "not_assessed": int((items["verdict"] == rdl.NOT_ASSESSED).sum()),
            "assessed": assessed,
            "grade": _grade(assessed, reviewed)}


def delta_statement(home_name: str, target_name: str, items: pd.DataFrame) -> str:
    """The standard's signature line, e.g. "Entering Turkey from Israel:
    4 stricter, 2 new mechanisms, 1 gap; most in Incident reporting."""
    s = readiness(items)
    if not s["assessed"] and not s["gaps"]:
        return (f"Entering {target_name} from {home_name}: not assessed yet, no "
                "comparable indexed text.")

    def n(k, one, many):
        return f"{k} {one if k == 1 else many}"
    line = (f"Entering {target_name} from {home_name}: {n(s['stricter'], 'stricter obligation', 'stricter obligations')}, "
            f"{n(s['new_mechanisms'], 'new mechanism', 'new mechanisms')}, "
            f"{n(s['gaps'], 'gap', 'gaps')}")
    work = items[items["verdict"].isin([rdl.STRICTER, rdl.DIFFERENT, NEW_CONTROL])]
    if not work.empty:
        line += f"; most in {work['category'].value_counts().index[0]}"
    if s["readiness"] is not None:
        line += (f". Entry Readiness {s['readiness']:.0f}% "
                 f"(grade {s['grade']}, {rdl.VERSION}).")
    return line
