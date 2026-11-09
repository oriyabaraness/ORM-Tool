"""Audit readiness: obligations joined with reviews, controls and the bank's
own control set, plus the audit pack (Excel and PDF).

No Streamlit here, so everything is unit-testable.

Coverage is a suggestion, never a conclusion: an obligation is shown as
covered when one of the bank's controls describes the same duty closely
enough, and a reviewer confirms it. The wording on screen and in the pack
says so.
"""
from __future__ import annotations

import datetime as dt
import io
import sqlite3

import pandas as pd

from . import controls as control_lib
from . import match, obligations, taxonomy
from .state import STATUS_LABEL

NAMES = {"IL": "Israel", "JO": "Jordan", "TR": "Turkey"}
COVERED, PARTIAL = 0.24, 0.13


def obligation_table(conn: sqlite3.Connection, reviews: dict[str, dict], *,
                     jurisdiction: str | None = None, category_id: str | None = None,
                     document_id: str | None = None) -> pd.DataFrame:
    """One row per obligation, with the reviewer's decisions applied."""
    obligations.init(conn)
    where, params = ["1=1"], []
    for col, val in (("o.jurisdiction", jurisdiction), ("o.category_id", category_id),
                     ("o.document_id", document_id)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    df = pd.read_sql_query(f"""
        SELECT o.id, o.okey, o.jurisdiction, o.category_id, o.document_id,
               d.regulator, d.ref AS doc_ref, d.title AS doc_title,
               COALESCE(NULLIF(d.pdf_url, ''), d.url) AS link,
               p.ref AS clause_ref, p.seq, o.actor, o.action, o.modality,
               o.deadline_text, o.deadline_hours, o.frequency, o.evidence,
               o.sentence, o.method,
               (SELECT GROUP_CONCAT(oc.control_id) FROM (
                    SELECT control_id FROM obligation_control
                    WHERE obligation_id = o.id ORDER BY score DESC) oc) AS suggested
        FROM obligation o
        JOIN document d ON d.id = o.document_id
        JOIN provision p ON p.id = o.provision_id
        WHERE {' AND '.join(where)}
        ORDER BY o.jurisdiction, d.ref, p.seq, o.id
    """, conn, params=params)
    if df.empty:
        return df.assign(status="", reviewer="", reviewed_at="", control_id="",
                         control_source="", control_name="", original_action="")
    df["suggested"] = df["suggested"].fillna("")
    df["original_action"] = df["action"]
    status, reviewer, at, ctl, src, note = [], [], [], [], [], []
    for _, r in df.iterrows():
        rv = reviews.get(r["okey"])
        top = r["suggested"].split(",")[0] if r["suggested"] else ""
        if rv:
            status.append(STATUS_LABEL.get(rv["status"], "Unreviewed"))
            reviewer.append(rv.get("reviewer") or "")
            at.append(rv.get("reviewed_at") or "")
            note.append(rv.get("note") or "")
            if rv.get("action_edit"):
                df.at[_, "action"] = rv["action_edit"]
            chosen = rv.get("control_id")
            if chosen is None:
                chosen = top
            ctl.append(chosen)
            src.append("reviewer" if rv["status"] == 1 else ("suggested" if chosen else ""))
        else:
            status.append("Unreviewed")
            reviewer.append("")
            at.append("")
            note.append("")
            ctl.append(top)
            src.append("suggested" if top else "")
    df["status"], df["reviewer"], df["reviewed_at"] = status, reviewer, at
    df["note"], df["control_id"], df["control_source"] = note, ctl, src
    df["control_name"] = df["control_id"].map(
        lambda c: control_lib.BY_ID[c].name if c in control_lib.BY_ID else "")
    df["citation"] = df.apply(citation, axis=1)
    return df


def citation(r) -> str:
    ref = " ".join(x for x in (r.get("doc_ref") or "", r.get("clause_ref") or "") if x)
    return f"{r.get('regulator') or ''} · {ref or r.get('doc_title') or ''}".strip(" ·")


# --- coverage against the bank's own controls ------------------------------------

def _bank_text(c: dict) -> str:
    return " ".join(x for x in (c.get("name"), c.get("description"),
                                c.get("frequency")) if x)


def _obl_text(r) -> str:
    lib = control_lib.BY_ID.get(r.get("control_id") or "")
    extra = f" {lib.name}. {lib.description}" if lib else ""
    return f"{r['action']} {r['sentence']}{extra}"


def coverage(obls: pd.DataFrame, bank: list[dict]) -> pd.DataFrame:
    """Best-matching bank control per obligation and a coverage level:
    covered / partial / not covered (by text similarity, for review)."""
    out = obls.copy()
    if out.empty:
        return out.assign(bank_control="", bank_owner="", coverage="", coverage_score=0.0)
    if not bank:
        return out.assign(bank_control="", bank_owner="", coverage="no controls loaded",
                          coverage_score=0.0)
    otexts = [_obl_text(r) for _, r in out.iterrows()]
    btexts = [_bank_text(c) for c in bank]
    vec = match.Vectorizer(otexts + btexts)
    ov = [vec.vector(match.tokens(t)) for t in otexts]
    bv = [vec.vector(match.tokens(t)) for t in btexts]
    best_name, best_owner, level, score = [], [], [], []
    for (_, r), o in zip(out.iterrows(), ov):
        best, best_s = None, 0.0
        for c, b in zip(bank, bv):
            if c.get("category_id") and c["category_id"] != r["category_id"]:
                continue
            s = match.cosine(o, b)
            if s > best_s:
                best, best_s = c, s
        if best is None or best_s < PARTIAL:
            best_name.append("")
            best_owner.append("")
            level.append("not covered")
        else:
            label = (f"{best['ref']} · " if best.get("ref") else "") + best["name"]
            best_name.append(label)
            best_owner.append(best.get("owner") or "")
            level.append("covered" if best_s >= COVERED else "partial")
        score.append(round(best_s, 3))
    out["bank_control"], out["bank_owner"] = best_name, best_owner
    out["coverage"], out["coverage_score"] = level, score
    return out


def coverage_summary(cov: pd.DataFrame) -> pd.DataFrame:
    """Counts by country x category x coverage level (approved and
    unreviewed obligations; rejected ones are left out)."""
    if cov.empty:
        return pd.DataFrame(columns=["country", "category", "covered", "partial",
                                     "not covered", "total"])
    live = cov[cov["status"] != "Rejected"]
    t = (live.groupby(["jurisdiction", "category_id", "coverage"]).size()
         .unstack(fill_value=0).reset_index())
    for col in ("covered", "partial", "not covered"):
        if col not in t:
            t[col] = 0
    t["total"] = t[["covered", "partial", "not covered"]].sum(axis=1)
    t["country"] = t["jurisdiction"].map(NAMES)
    t["category"] = t["category_id"].map(lambda c: taxonomy.BY_ID[c].name)
    return t[["country", "category", "covered", "partial", "not covered", "total"]]


# --- audit pack -------------------------------------------------------------------

PACK_COLUMNS = [
    ("country", "Country"), ("category", "Risk category"), ("citation", "Source"),
    ("link", "Source link"), ("actor", "Who"), ("action", "Obligation"),
    ("modality", "Force"), ("deadline_text", "Deadline"), ("frequency", "Frequency"),
    ("control_name", "Mapped control"), ("bank_control", "Bank control"),
    ("bank_owner", "Control owner"), ("coverage", "Coverage"),
    ("evidence", "Evidence to hold"), ("status", "Review status"),
    ("reviewer", "Reviewed by"), ("reviewed_at", "Reviewed at"), ("note", "Note"),
    ("sentence", "Source text"),
]


def pack_frame(cov: pd.DataFrame) -> pd.DataFrame:
    df = cov.copy()
    df["country"] = df["jurisdiction"].map(NAMES)
    df["category"] = df["category_id"].map(lambda c: taxonomy.BY_ID[c].name)
    for col, _ in PACK_COLUMNS:
        if col not in df:
            df[col] = ""
    return df[[c for c, _ in PACK_COLUMNS]].rename(columns=dict(PACK_COLUMNS))


NOTICE = ("Obligations and control mappings are extracted and suggested by "
          "software from the regulators' published text, then reviewed by people. "
          "Rows not marked Approved have not been confirmed by a reviewer. A "
          "difference between jurisdictions is not a compliance gap, and "
          "coverage is based on control descriptions, not on testing.")


def audit_pack_excel(cov: pd.DataFrame, *, scope: str, log: list[dict]) -> bytes:
    buf = io.BytesIO()
    frame = pack_frame(cov)
    summary = coverage_summary(cov)
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    reviewed = int((cov["status"] == "Approved").sum()) if not cov.empty else 0
    cover = pd.DataFrame({"": [
        "Clausewiz audit pack", f"Scope: {scope}", f"Generated: {generated}",
        f"Obligations: {len(cov)} (approved by a reviewer: {reviewed})", "", NOTICE]})
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        cover.to_excel(xw, sheet_name="Read me", index=False, header=False)
        summary.to_excel(xw, sheet_name="Coverage summary", index=False)
        frame.to_excel(xw, sheet_name="Obligations", index=False)
        pd.DataFrame(log or [], columns=["ts", "actor", "action", "object_id", "detail"]) \
            .rename(columns={"ts": "When (UTC)", "actor": "Who", "action": "What",
                             "object_id": "Item", "detail": "New state"}) \
            .to_excel(xw, sheet_name="Change log", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(60, max(10, width + 2))
            ws.freeze_panes = "A2" if ws.title != "Read me" else None
    return buf.getvalue()


def audit_pack_pdf(cov: pd.DataFrame, *, scope: str) -> bytes:
    from .simple_pdf import Document
    doc = Document()
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    doc.heading("Clausewiz audit pack")
    doc.text(f"Scope: {scope}   ·   Generated: {generated}", size=9)
    doc.text(NOTICE, size=8)
    doc.space(6)
    doc.heading("Coverage summary", size=12)
    for _, r in coverage_summary(cov).iterrows():
        doc.text(f"{r['country']} · {r['category']}: {r['covered']} covered, "
                 f"{r['partial']} partial, {r['not covered']} not covered "
                 f"(of {r['total']})", size=9)
    doc.space(6)
    doc.heading("Obligations", size=12)
    for _, r in cov.iterrows():
        doc.text(f"{citation(r)}  [{r['status']}]", size=9, bold=True)
        who = f"{r['actor']}: " if r.get("actor") else ""
        doc.text(f"{who}{r['action']}", size=9)
        facts = [f"Deadline: {r['deadline_text']}" if r.get("deadline_text") else "",
                 f"Frequency: {r['frequency']}" if r.get("frequency") else "",
                 f"Control: {r['control_name']}" if r.get("control_name") else
                 "Control: none mapped",
                 f"Bank control: {r['bank_control']} ({r['coverage']})"
                 if r.get("bank_control") else "",
                 f"Evidence: {r['evidence']}"]
        doc.text(" · ".join(f for f in facts if f), size=8)
        doc.space(4)
    return doc.render()
