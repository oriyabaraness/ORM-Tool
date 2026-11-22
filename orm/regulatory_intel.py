"""Regulatory Intelligence: source library, obligation explorer, comparison,
applicability and risk-mapping suggestions.

Built on the existing index (orm.db), reviews (orm_state.db) and risk store
(orm_risk.db). No Streamlit here. AI or rule interpretations are always
labelled separately from exact regulatory quotations. Citations that cannot
be verified against indexed clause text are marked
"Source verification required."
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import os
import re
import sqlite3
import uuid

import pandas as pd

from . import audit, controls as control_lib, match, obligations, risk, taxonomy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Demo registry: official Bank of Israel Proper Conduct topics used in the
# interview walkthrough. Titles and URLs are filled from the live index at
# runtime; we never invent directive text. Items missing from the index are
# marked unverified.
DEMO_DOCUMENT_IDS = (
    "IL-BOI-PC-350",
    "IL-BOI-PC-355",
    "IL-BOI-PC-364",
    "IL-BOI-PC-366",
    "IL-BOI-PC-362",
)

# Product-facing requirement categories (Feature 2) mapped from taxonomy ids.
RI_CATEGORY = {
    "governance": "Operational risk governance",
    "op_resilience": "Business continuity",
    "ict_cyber": "Information technology risk",
    "third_party": "Third-party risk",
    "incident_reporting": "Incident management",
    "aml": "Fraud and process risk",
    "conduct": "Fraud and process risk",
}
# Extra labels used when keyword hints fire on top of the taxonomy tag.
RI_HINTS = (
    ("Cloud outsourcing", re.compile(r"\bcloud\b", re.I)),
    ("Cybersecurity", re.compile(r"\bcyber|information security\b", re.I)),
    ("Regulatory reporting", re.compile(r"\breport|notif", re.I)),
    ("Payments resilience", re.compile(r"\bpayment|authoris|clearing|settlement\b", re.I)),
    ("Change management", re.compile(r"\bchange (control|management)|test(?:ed|ing).{0,40}environment\b", re.I)),
    ("Data integrity", re.compile(r"\bdata (integrity|quality)|backup|restore|recover", re.I)),
)

PROCESS_BY_CATEGORY = {
    "governance": "Risk governance and board reporting",
    "op_resilience": "Business continuity and crisis management",
    "ict_cyber": "Technology change and IT operations",
    "third_party": "Third-party and cloud outsourcing",
    "incident_reporting": "Incident response and supervisory notification",
    "aml": "Financial crime controls",
    "conduct": "Customer operations",
}

RELATION_LABEL = {
    "substantially_aligned": "Substantially aligned",
    "partially_aligned": "Partially aligned",
    "different_scope": "Different scope",
    "potentially_conflicting": "Potentially conflicting",
    "no_comparable": "No comparable requirement found",
    "unable": "Unable to determine",
}

COMPARISON_DISCLAIMER = (
    "Semantic similarity is a finding aid, not proof of legal equivalence. "
    "A specialist must confirm before relying on any alignment."
)

UNVERIFIED_CITATION = "Source verification required."
PAGE_UNAVAILABLE = "Not available (text extracted without page positions)"
INTERPRETATION_NOTE = (
    "Machine interpretation — not official regulatory text. Edit and validate "
    "before relying on it."
)


def _today() -> str:
    return dt.date.today().isoformat()


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _as_path(path) -> str:
    if path is None:
        return ""
    try:
        if path != path:  # NaN from pandas
            return ""
    except Exception:
        return ""
    text = str(path).strip()
    return "" if text in ("", "None", "nan") else text


def _checksum_for(path) -> str:
    path = _as_path(path)
    if not path or not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _mtime(path) -> str:
    path = _as_path(path)
    if not path or not os.path.isfile(path):
        return ""
    return dt.datetime.fromtimestamp(
        os.path.getmtime(path), tz=dt.timezone.utc).date().isoformat()


# --- Feature 1: source document management ----------------------------------------

def source_library(conn: sqlite3.Connection,
                   document_ids: tuple[str, ...] | None = None) -> pd.DataFrame:
    """One row per indexed document with the RI source fields.

    Effective date, version and supersession are marked Unverified when the
    index does not hold them — never invented.
    """
    obligations.init(conn)
    where, params = ["1=1"], []
    if document_ids:
        where.append(f"d.id IN ({','.join('?' * len(document_ids))})")
        params.extend(document_ids)
    df = pd.read_sql_query(f"""
        SELECT d.id AS document_id, d.regulator, d.jurisdiction, d.title,
               d.ref AS directive_number, d.published AS publication_date,
               d.lastmod AS index_lastmod, d.url AS source_url,
               d.pdf_url, d.text_status AS extraction_status, d.text_path,
               d.pages, d.chars, d.error, d.source AS ingest_source,
               (SELECT COUNT(*) FROM obligation o WHERE o.document_id = d.id) AS obligations
        FROM document d
        WHERE {' AND '.join(where)}
        ORDER BY d.jurisdiction, d.ref, d.title
    """, conn, params=params)
    if df.empty:
        return df
    rows = []
    for _, r in df.iterrows():
        text_ok = r["extraction_status"] == "ok" and (r["chars"] or 0) > 0
        rows.append({
            **r.to_dict(),
            "official_title": r["title"],
            "document_version": "Unverified — not recorded in index",
            "effective_date": "Unverified — not recorded in index",
            "file_checksum": _checksum_for(r["text_path"]) if text_ok else "",
            "upload_timestamp": _mtime(r["text_path"]),
            "document_language": (
                "English (official translation)" if r["jurisdiction"] == "IL"
                else "As published by the regulator"),
            "supersession_status": "Not assessed",
            "last_verification_date": r["index_lastmod"] or "",
            "verification_status": (
                "Index-verified metadata" if text_ok
                else ("Extraction incomplete" if r["extraction_status"] != "ok"
                      else "Unverified — no indexed text")),
            "original_reference": r["pdf_url"] or r["source_url"] or "",
        })
    return pd.DataFrame(rows)


def demo_registry(conn: sqlite3.Connection) -> pd.DataFrame:
    """The five BOI demo documents, joined to the live index."""
    lib = source_library(conn, DEMO_DOCUMENT_IDS)
    by_id = {r["document_id"]: r for _, r in lib.iterrows()} if not lib.empty else {}
    rows = []
    for doc_id in DEMO_DOCUMENT_IDS:
        if doc_id in by_id:
            row = by_id[doc_id].to_dict()
            row["registry_status"] = row["verification_status"]
            row["in_index"] = True
        else:
            row = {
                "document_id": doc_id, "regulator": "Bank of Israel",
                "jurisdiction": "IL", "official_title": "",
                "directive_number": doc_id.split("-")[-1],
                "verification_status": "Unverified — document not in this index",
                "registry_status": "Unverified — document not in this index",
                "extraction_status": "missing", "obligations": 0,
                "original_reference": "", "in_index": False,
                "document_version": "Unverified",
                "effective_date": "Unverified",
                "supersession_status": "Not assessed",
                "last_verification_date": "",
            }
        rows.append(row)
    return pd.DataFrame(rows)


# --- Feature 2: structured obligation extraction ----------------------------------

def requirement_category(category_id: str, sentence: str) -> str:
    for label, pattern in RI_HINTS:
        if pattern.search(sentence or ""):
            # Prefer cloud label when the taxonomy is third_party + cloud words.
            if label == "Cloud outsourcing" and category_id == "third_party":
                return label
            if label in ("Cybersecurity", "Change management", "Data integrity",
                         "Payments resilience", "Regulatory reporting"):
                return label
    cat = taxonomy.BY_ID.get(category_id)
    return RI_CATEGORY.get(category_id, cat.name if cat else category_id or "Uncategorised")


def verify_citation(conn: sqlite3.Connection, okey: str,
                    sentence: str | None = None,
                    provision_id: int | None = None) -> dict:
    """Confirm the quoted sentence still appears in the indexed clause text."""
    row = conn.execute(
        "SELECT o.sentence, o.provision_id, p.text FROM obligation o "
        "JOIN provision p ON p.id = o.provision_id WHERE o.okey = ? LIMIT 1",
        (okey,)).fetchone()
    if not row and provision_id is None:
        return {"verified": False, "status": UNVERIFIED_CITATION,
                "detail": "Obligation not found in index"}
    if sentence is None:
        if not row:
            return {"verified": False, "status": UNVERIFIED_CITATION,
                    "detail": "Obligation not found in index"}
        sentence = row["sentence"]
    if provision_id is None:
        provision_id = row["provision_id"] if row else None
        clause = row["text"] if row else ""
    else:
        clause_row = conn.execute(
            "SELECT text FROM provision WHERE id = ?", (provision_id,)).fetchone()
        clause = clause_row["text"] if clause_row else ""
    if not clause:
        return {"verified": False, "status": UNVERIFIED_CITATION,
                "detail": "Clause text missing from index"}
    if _norm(sentence) and _norm(sentence) in _norm(clause):
        return {"verified": True, "status": "Verified against indexed clause",
                "detail": ""}
    return {"verified": False, "status": UNVERIFIED_CITATION,
            "detail": "Quoted sentence not found in the indexed clause text"}


def obligations_explorer(conn: sqlite3.Connection, reviews: dict | None = None,
                         *, jurisdiction: str | None = None,
                         category_id: str | None = None,
                         document_id: str | None = None,
                         search: str = "",
                         demo_only: bool = False) -> pd.DataFrame:
    """Obligations with RI fields; exact quote kept separate from interpretation."""
    reviews = reviews or {}
    doc_ids = DEMO_DOCUMENT_IDS if demo_only else None
    if document_id:
        doc_ids = (document_id,)
    base = audit.obligation_table(
        conn, reviews, jurisdiction=jurisdiction, category_id=category_id,
        document_id=document_id if not demo_only else None)
    if demo_only and not base.empty:
        base = base[base["document_id"].isin(DEMO_DOCUMENT_IDS)].reset_index(drop=True)
    if base.empty:
        return base
    if search.strip():
        q = search.strip().lower()
        mask = (base["sentence"].str.lower().str.contains(q, na=False)
                | base["action"].str.lower().str.contains(q, na=False)
                | base["citation"].str.lower().str.contains(q, na=False)
                | base["doc_ref"].fillna("").str.lower().str.contains(q, na=False))
        base = base[mask].reset_index(drop=True)
    base = base.copy()
    checks = [verify_citation(conn, okey) for okey in base["okey"]]
    base["citation_verified"] = [bool(c["verified"]) for c in checks]
    base["citation_status"] = [c["status"] for c in checks]
    base["requirement_category"] = [
        requirement_category(cid, sent)
        for cid, sent in zip(base["category_id"], base["sentence"])]
    base["business_process"] = base["category_id"].map(
        lambda c: PROCESS_BY_CATEGORY.get(c, "Operations (review to confirm)"))
    base["page_number"] = PAGE_UNAVAILABLE
    base["source_language"] = base["jurisdiction"].map(
        lambda j: "English (indexed translation)" if j == "IL" else "As indexed")
    base["plain_language"] = base["action"]
    base["interpretation_note"] = INTERPRETATION_NOTE
    base["control_objective"] = base["control_name"]
    base["suggested_evidence"] = base["evidence"]
    base["validation_status"] = base["status"].map(
        lambda s: {"Approved": "Validated", "Rejected": "Rejected",
                   "Unreviewed": "Suggested — needs review"}.get(s, s))
    base["exact_source_text"] = base["sentence"]
    return base


# --- Feature 3: cross-jurisdictional comparison -----------------------------------

def relation_from_score(score: float | None, *, text_available: bool) -> str:
    if not text_available:
        return "unable"
    if score is None:
        return "no_comparable"
    if score >= 0.35:
        return "substantially_aligned"
    if score >= 0.18:
        return "partially_aligned"
    if score >= match.SAME_CLAUSE_SIMILARITY:
        return "different_scope"
    return "no_comparable"


def compare_documents(conn: sqlite3.Connection, document_ids: list[str],
                      *, category_id: str | None = None,
                      limit_per_side: int = 40) -> pd.DataFrame:
    """Compare obligations across two or more documents via clause matches.

    Uses existing provision_match scores. Does not assert legal equivalence.
    """
    document_ids = [d for d in document_ids if d]
    if len(document_ids) < 2:
        return pd.DataFrame()
    obligations.init(conn)
    home_id, *others = document_ids
    where_cat = "AND o.category_id = ?" if category_id else ""
    params: list = [home_id]
    if category_id:
        params.append(category_id)
    homes = conn.execute(f"""
        SELECT o.okey, o.sentence, o.action, o.modality, o.category_id, o.jurisdiction,
               o.provision_id, p.ref AS clause_ref, d.ref AS doc_ref, d.title AS doc_title,
               d.regulator, COALESCE(NULLIF(d.pdf_url,''), d.url) AS link
        FROM obligation o
        JOIN provision p ON p.id = o.provision_id
        JOIN document d ON d.id = o.document_id
        WHERE o.document_id = ? {where_cat}
        ORDER BY p.seq, o.id LIMIT ?
    """, (*params, limit_per_side)).fetchall()
    rows = []
    for h in homes:
        cite_h = audit.citation(dict(h))
        v_h = verify_citation(conn, h["okey"], h["sentence"], h["provision_id"])
        for other_id in others:
            other_doc = conn.execute(
                "SELECT id, text_status, chars, jurisdiction, ref, title, regulator, "
                "COALESCE(NULLIF(pdf_url,''), url) AS link FROM document WHERE id=?",
                (other_id,)).fetchone()
            text_ok = bool(other_doc and other_doc["text_status"] == "ok"
                           and (other_doc["chars"] or 0) > 0)
            best = None
            if text_ok:
                best = conn.execute("""
                    SELECT o.okey, o.sentence, o.action, o.modality, o.jurisdiction,
                           o.provision_id, p.ref AS clause_ref, d.ref AS doc_ref,
                           d.title AS doc_title, d.regulator,
                           COALESCE(NULLIF(d.pdf_url,''), d.url) AS link,
                           pm.score, pm.text_similarity, pm.shared_terms,
                           pm.shared_expectations
                    FROM provision_match pm
                    JOIN obligation o ON o.provision_id = pm.match_id
                    JOIN provision p ON p.id = o.provision_id
                    JOIN document d ON d.id = o.document_id
                    WHERE pm.provision_id = ? AND d.id = ?
                    ORDER BY pm.score DESC LIMIT 1
                """, (h["provision_id"], other_id)).fetchone()
            if best:
                rel = relation_from_score(best["score"], text_available=True)
                v_o = verify_citation(conn, best["okey"], best["sentence"],
                                      best["provision_id"])
                rows.append({
                    "home_okey": h["okey"], "home_citation": cite_h,
                    "home_quote": h["sentence"],
                    "home_interpretation": h["action"],
                    "home_citation_status": v_h["status"],
                    "other_document_id": other_id,
                    "other_okey": best["okey"],
                    "other_citation": audit.citation(dict(best)),
                    "other_quote": best["sentence"],
                    "other_interpretation": best["action"],
                    "other_citation_status": v_o["status"],
                    "other_link": best["link"],
                    "relation": rel,
                    "relation_label": RELATION_LABEL[rel],
                    "score": round(float(best["score"]), 4),
                    "similarity_note": (
                        f"Shared terms: {best['shared_terms'] or '—'}. "
                        f"Shared expectations: {best['shared_expectations'] or '—'}."
                    ),
                    "difference_note": (
                        "Modalities differ." if (h["modality"] != best["modality"])
                        else "Review wording and scope side by side."),
                    "operational_implication": (
                        "Treat as a candidate match for RCSA mapping; confirm with "
                        "legal/compliance before treating as equivalent."),
                    "validation_status": "Suggested — needs review",
                    "disclaimer": COMPARISON_DISCLAIMER,
                    "home_link": h["link"],
                })
            else:
                rel = relation_from_score(None, text_available=text_ok)
                rows.append({
                    "home_okey": h["okey"], "home_citation": cite_h,
                    "home_quote": h["sentence"],
                    "home_interpretation": h["action"],
                    "home_citation_status": v_h["status"],
                    "other_document_id": other_id,
                    "other_okey": "",
                    "other_citation": (
                        f"{other_doc['regulator']} · {other_doc['ref']}"
                        if other_doc else other_id),
                    "other_quote": "",
                    "other_interpretation": "",
                    "other_citation_status": (
                        "Not assessed — no indexed text" if not text_ok
                        else UNVERIFIED_CITATION),
                    "other_link": (other_doc["link"] if other_doc else ""),
                    "relation": rel,
                    "relation_label": RELATION_LABEL[rel],
                    "score": None,
                    "similarity_note": "No clause-level match stored for this pair.",
                    "difference_note": (
                        "Other jurisdiction text is not yet indexed."
                        if not text_ok else
                        "No comparable obligation found in the matched clauses."),
                    "operational_implication": (
                        "Possible gap or different drafting — specialist review "
                        "required before concluding."),
                    "validation_status": "Suggested — needs review",
                    "disclaimer": COMPARISON_DISCLAIMER,
                    "home_link": h["link"],
                })
    return pd.DataFrame(rows)


# --- Feature 4: applicability -----------------------------------------------------

def applicability_questions(document_id: str, title: str = "") -> list[str]:
    """Questions an ORM / compliance reviewer should answer. Not legal advice."""
    return [
        f"Does the legal entity hold a licence or registration that brings "
        f"«{title or document_id}» into scope?",
        "Which products or services (e.g. card payments, cloud hosting, "
        "customer onboarding) does this directive address for us?",
        "Are we a banking corporation, a payment institution, or another "
        "entity type named in the directive's application section?",
        "Is there a group, branch or outsourcing arrangement that extends "
        "the perimeter across jurisdictions?",
        "Has legal/compliance confirmed the reading, or is specialist "
        "interpretation still required?",
    ]


def list_applicability(risk_conn) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM applicability ORDER BY updated_at DESC, document_id",
        risk_conn)


def save_applicability(risk_conn, row: dict, *, actor: str) -> dict:
    status = row.get("status") or "not_yet_assessed"
    if status not in risk.APPLICABILITY_STATUSES:
        raise ValueError(f"Unknown applicability status: {status}")
    payload = {
        "id": row.get("id") or f"APP-{uuid.uuid4().hex[:10]}",
        "document_id": row["document_id"],
        "status": status,
        "legal_entity": (row.get("legal_entity") or "").strip(),
        "license_perimeter": (row.get("license_perimeter") or "").strip(),
        "product_service": (row.get("product_service") or "").strip(),
        "jurisdiction": (row.get("jurisdiction") or "").strip(),
        "reasoning": (row.get("reasoning") or "").strip(),
        "reviewer": (actor or row.get("reviewer") or "").strip(),
        "review_date": row.get("review_date") or _today(),
        "supporting_reference": (row.get("supporting_reference") or "").strip(),
        "provenance": row.get("provenance") or "user",
        "validation_status": (
            "validated" if status.startswith("confirmed") else "draft"),
        "is_synthetic": int(row.get("is_synthetic") or 0),
    }
    existing = risk_conn.execute(
        "SELECT id FROM applicability WHERE id=?", (payload["id"],)).fetchone()
    if existing:
        return risk.update(risk_conn, "applicability", payload["id"], payload,
                           actor=actor)
    return risk.insert(risk_conn, "applicability", payload, actor=actor)


def applicability_for_document(risk_conn, document_id: str) -> list[dict]:
    return [dict(r) for r in risk_conn.execute(
        "SELECT * FROM applicability WHERE document_id=? ORDER BY updated_at DESC",
        (document_id,))]


# --- Feature 5: map obligation → operational risk ---------------------------------

def risk_mapping_suggestions(conn: sqlite3.Connection, okey: str) -> dict:
    """Editable suggestions. Always validation_status=suggested until a person
    links them to a risk. Never presented as verified compliance conclusions."""
    row = conn.execute("""
        SELECT o.okey, o.sentence, o.action, o.actor, o.evidence, o.category_id,
               o.modality, o.document_id, o.jurisdiction, p.ref AS clause_ref,
               d.ref AS doc_ref, d.title AS doc_title, d.regulator,
               COALESCE(NULLIF(d.pdf_url,''), d.url) AS link,
               (SELECT control_id FROM obligation_control oc
                WHERE oc.obligation_id = o.id ORDER BY score DESC LIMIT 1) AS control_id
        FROM obligation o
        JOIN provision p ON p.id = o.provision_id
        JOIN document d ON d.id = o.document_id
        WHERE o.okey = ? LIMIT 1
    """, (okey,)).fetchone()
    if not row:
        return {"okey": okey, "found": False, "validation_status": "suggested",
                "citation_status": UNVERIFIED_CITATION}
    check = verify_citation(conn, okey, row["sentence"])
    cat = taxonomy.BY_ID.get(row["category_id"])
    ctl = control_lib.BY_ID.get(row["control_id"] or "")
    return {
        "found": True,
        "okey": okey,
        "citation": audit.citation(dict(row)),
        "link": row["link"],
        "exact_source_text": row["sentence"],
        "citation_status": check["status"],
        "citation_verified": check["verified"],
        "interpretation": row["action"],
        "interpretation_note": INTERPRETATION_NOTE,
        "validation_status": "suggested",
        "risk_event": f"Failure to meet: {row['action'][:160]}",
        "risk_category": cat.name if cat else row["category_id"],
        "category_id": row["category_id"],
        "event_type": (
            "Business disruption and system failures"
            if row["category_id"] in ("op_resilience", "ict_cyber", "third_party")
            else "Execution, delivery and process management"),
        "causes": (
            f"Control breakdown or missing ownership for «{row['actor'] or 'the firm'}»; "
            "unclear procedures; incomplete testing or monitoring."),
        "consequences": (
            "Service disruption, customer impact, supervisory findings, "
            "or delayed regulatory notification."),
        "business_processes": PROCESS_BY_CATEGORY.get(
            row["category_id"], "Operations (review to confirm)"),
        "control_objectives": ctl.name if ctl else (
            "Design and operate a control that evidences the duty in the citation"),
        "potential_kris": (
            "Control test fail rate; overdue policy reviews; "
            "minutes from detection to supervisory notification; "
            "critical-service downtime vs impact tolerance."),
        "potential_evidence": row["evidence"] or (ctl.evidence if ctl else ""),
        "accountable_stakeholders": (
            f"{row['actor'] or 'Business owner'}; Operational Risk; "
            "Compliance; Control owner"),
        "suggested_control_id": row["control_id"] or "",
        "disclaimer": (
            "Suggestions only. A named reviewer must validate before the "
            "obligation is treated as linked to a risk or control."),
    }


def link_suggestion_to_risk(risk_conn, index_conn, *, risk_id: str, okey: str,
                            rationale: str, actor: str) -> dict:
    """Attach a verified (or flagged) obligation citation to an existing risk."""
    cite = risk.obligation_citation(index_conn, okey)
    if not cite:
        raise LookupError("Obligation not found in the regulation index.")
    check = verify_citation(index_conn, okey, cite["sentence"])
    row = {
        "risk_id": risk_id,
        "okey": okey,
        "document_id": cite["document_id"],
        "clause_ref": cite.get("clause_ref") or "",
        "citation": cite.get("citation") or audit.citation(cite),
        "link": cite.get("link") or "",
        "sentence": cite["sentence"],
        "sentence_sha": risk.sentence_sha(cite["sentence"]),
        "rationale": (rationale or "").strip() or "Linked from Regulatory Intelligence",
        "provenance": "user",
        "validation_status": "validated" if check["verified"] else "suggested",
        "is_synthetic": 0,
    }
    if not check["verified"]:
        row["rationale"] = (
            f"{row['rationale']} [{UNVERIFIED_CITATION}]").strip()
    return risk.insert(risk_conn, "risk_obligation", row, actor=actor)


# --- export -----------------------------------------------------------------------

def to_csv(df: pd.DataFrame, columns: list[str] | None = None) -> bytes:
    if df is None or df.empty:
        buf = io.StringIO()
        csv.writer(buf).writerow(columns or ["empty"])
        return buf.getvalue().encode("utf-8")
    use = [c for c in (columns or list(df.columns)) if c in df.columns]
    buf = io.StringIO()
    df[use].to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def import_guidance() -> str:
    """How to add documents without fetching arbitrary URLs."""
    return (
        "Import only through the existing pipeline: place a PDF or plain-text "
        "file in orm_texts/manual/<document-id>.pdf (or .txt), add the document "
        "row via the regulator connector or a local CSV, then run "
        "`python orm_pipeline.py build`. The app does not fetch untrusted URLs "
        "from this screen."
    )
