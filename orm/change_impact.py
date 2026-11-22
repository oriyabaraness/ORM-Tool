"""Regulatory Change Impact Analyzer.

Compares two verified versions of the same document family, classifies clause
changes, maps them to existing risks/controls, and proposes review actions.

A textual change is not automatically a material regulatory change.
Interpretations do not establish applicability or noncompliance.
All material assessments require human review.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import uuid
from difflib import SequenceMatcher

import pandas as pd

from . import risk

SEED_VERSION = "chg-1"
ACTOR = "Synthetic change-impact demo seed"
NOTICE = (
    "A textual difference is not automatically a material regulatory change. "
    "Interpretations do not establish applicability. This analyzer never marks "
    "an organization noncompliant solely because a directive changed. "
    "All material assessments require human review."
)
FICTIONAL_PUBLISHER = (
    "Illustrative fictional standard for demonstration only — not issued by "
    "any real regulator and not Bank of Israel, CBJ, BRSA, or Revolut text."
)

CHANGE_KINDS = ("added", "removed", "modified", "unchanged", "uncertain")
PRIORITY = ("critical", "high", "medium", "low")

# Similarity bands for match quality
_UNCHANGED_MIN = 0.97
_MODIFIED_MIN = 0.45


# --- pure diff helpers ------------------------------------------------------------

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio(), 4)


def unified_diff(a: str, b: str, *, from_label: str = "A", to_label: str = "B") -> str:
    return "\n".join(difflib.unified_diff(
        (a or "").splitlines(), (b or "").splitlines(),
        fromfile=from_label, tofile=to_label, lineterm=""))


def interpret_change(kind: str, ref: str, text_a: str | None, text_b: str | None) -> dict:
    """Plain-language interpretation — hypothesis, not a compliance finding."""
    if kind == "unchanged":
        return {
            "kind": kind,
            "interpretation": f"Clause {ref} appears unchanged between versions.",
            "certainty": "confirmed",
            "materiality": "not_assessed",
            "note": "Unchanged text still requires human confirmation of context.",
        }
    if kind == "added":
        return {
            "kind": kind,
            "interpretation": (
                f"Clause {ref} appears only in the newer version. Hypothesis: a "
                f"new obligation may have been introduced — applicability and "
                f"materiality are not established."),
            "certainty": "hypothesis",
            "materiality": "not_assessed",
            "note": NOTICE,
        }
    if kind == "removed":
        return {
            "kind": kind,
            "interpretation": (
                f"Clause {ref} appears only in the older version. Hypothesis: an "
                f"obligation may have been withdrawn or relocated — confirm "
                f"before retiring related controls."),
            "certainty": "hypothesis",
            "materiality": "not_assessed",
            "note": NOTICE,
        }
    if kind == "modified":
        return {
            "kind": kind,
            "interpretation": (
                f"Clause {ref} text differs between versions. Hypothesis: the "
                f"obligation wording changed and linked risks/controls may need "
                f"reassessment — not a determination of noncompliance."),
            "certainty": "hypothesis",
            "materiality": "not_assessed",
            "note": NOTICE,
        }
    return {
        "kind": "uncertain",
        "interpretation": (
            f"Match for clause {ref} is ambiguous. Manual review required before "
            f"any mapping or remediation decision."),
        "certainty": "hypothesis",
        "materiality": "not_assessed",
        "note": NOTICE,
    }


def classify_pair(ref: str, text_a: str | None, text_b: str | None,
                  *, sim: float | None = None) -> dict:
    if text_a and not text_b:
        kind = "removed"
        sim = 0.0
    elif text_b and not text_a:
        kind = "added"
        sim = 0.0
    else:
        sim = text_similarity(text_a or "", text_b or "") if sim is None else sim
        if sim >= _UNCHANGED_MIN:
            kind = "unchanged"
        elif sim >= _MODIFIED_MIN:
            kind = "modified"
        else:
            kind = "uncertain"
    interp = interpret_change(kind, ref, text_a, text_b)
    return {
        "clause_ref": ref,
        "change_kind": kind,
        "similarity": sim,
        "text_a": text_a or "",
        "text_b": text_b or "",
        "diff": unified_diff(text_a or "", text_b or "",
                             from_label=f"{ref}@A", to_label=f"{ref}@B")
        if kind in ("modified", "uncertain") else "",
        **interp,
    }


def compare_versions(clauses_a: list[dict], clauses_b: list[dict]) -> list[dict]:
    """Compare two clause lists. Match primarily by clause_ref, else by text."""
    by_ref_a = {c["clause_ref"]: c for c in clauses_a}
    by_ref_b = {c["clause_ref"]: c for c in clauses_b}
    refs = sorted(set(by_ref_a) | set(by_ref_b),
                  key=lambda r: (by_ref_a.get(r) or by_ref_b.get(r) or {}).get("seq", 0))
    results = []
    used_b = set()
    for ref in refs:
        a = by_ref_a.get(ref)
        b = by_ref_b.get(ref)
        if a and b:
            used_b.add(ref)
            results.append(classify_pair(ref, a["text"], b["text"]))
        elif a and not b:
            # try fuzzy attach to unmatched B by text
            best_ref, best_sim = None, 0.0
            for rb, cb in by_ref_b.items():
                if rb in used_b or rb in by_ref_a:
                    continue
                s = text_similarity(a["text"], cb["text"])
                if s > best_sim:
                    best_sim, best_ref = s, rb
            if best_ref and best_sim >= _MODIFIED_MIN:
                used_b.add(best_ref)
                results.append(classify_pair(
                    f"{ref}≈{best_ref}", a["text"], by_ref_b[best_ref]["text"],
                    sim=best_sim))
            else:
                results.append(classify_pair(ref, a["text"], None))
        elif b and not a:
            if ref in used_b:
                continue
            results.append(classify_pair(ref, None, b["text"]))
            used_b.add(ref)
    return results


# --- store access -----------------------------------------------------------------

def families(conn) -> pd.DataFrame:
    return risk._df(conn, "SELECT * FROM reg_doc_family ORDER BY id")


def versions(conn, family_id: str | None = None) -> pd.DataFrame:
    if family_id:
        return risk._df(conn, """
            SELECT * FROM reg_doc_version WHERE family_id=?
            ORDER BY published_at, version_label""", (family_id,))
    return risk._df(conn, "SELECT * FROM reg_doc_version ORDER BY family_id, published_at")


def clauses(conn, version_id: str) -> pd.DataFrame:
    return risk._df(conn, """
        SELECT * FROM reg_doc_clause WHERE version_id=? ORDER BY seq, clause_ref""",
                    (version_id,))


def analyze(conn, version_a_id: str, version_b_id: str) -> dict:
    """Full impact analysis for two versions."""
    va = conn.execute("SELECT * FROM reg_doc_version WHERE id=?",
                      (version_a_id,)).fetchone()
    vb = conn.execute("SELECT * FROM reg_doc_version WHERE id=?",
                      (version_b_id,)).fetchone()
    if not va or not vb:
        raise LookupError("One or both versions were not found.")
    if va["family_id"] != vb["family_id"]:
        raise ValueError("Versions must belong to the same document family.")
    fam = conn.execute("SELECT * FROM reg_doc_family WHERE id=?",
                       (va["family_id"],)).fetchone()
    ca = clauses(conn, version_a_id)
    cb = clauses(conn, version_b_id)
    diffs = compare_versions(
        ca.to_dict("records") if not ca.empty else [],
        cb.to_dict("records") if not cb.empty else [])

    changed = [d for d in diffs if d["change_kind"] != "unchanged"]
    mapping = _affected_mappings(conn, changed)
    actions = suggested_actions(conn, fam=dict(fam), version_a=dict(va),
                                version_b=dict(vb), diffs=changed, mapping=mapping)
    summary = management_summary(fam=dict(fam), version_a=dict(va),
                                 version_b=dict(vb), diffs=diffs,
                                 mapping=mapping, actions=actions)
    counts = {k: sum(1 for d in diffs if d["change_kind"] == k) for k in CHANGE_KINDS}
    return {
        "family": dict(fam),
        "version_a": dict(va),
        "version_b": dict(vb),
        "diffs": diffs,
        "changed": changed,
        "counts": counts,
        "mapping": mapping,
        "actions": actions,
        "summary": summary,
        "notice": NOTICE,
        "fictional_publisher": fam["publisher_note"] if fam else FICTIONAL_PUBLISHER,
    }


def _affected_mappings(conn, changed: list[dict]) -> dict:
    """Link changed clauses to existing risks/controls via keyword overlap + demo links."""
    reg = risk.register(conn)
    ctl = risk.control_status(conn)
    risks_hit, controls_hit = [], []

    # Keyword cues from changed text
    blob = " ".join(
        (d.get("text_b") or d.get("text_a") or "") for d in changed).lower()
    cues = {
        "recovery": ["recovery", "failover", "resilience", "continuity"],
        "test": ["test", "testing", "evidence", "periodic"],
        "cloud": ["cloud", "third-party", "provider", "outsourcing"],
        "payment": ["payment", "authorisation", "authorization"],
    }
    hit_themes = [t for t, words in cues.items() if any(w in blob for w in words)]

    if not reg.empty:
        for _, r in reg.iterrows():
            title = f"{r['title']} {r.get('description') or ''}".lower()
            score = sum(1 for t in hit_themes if t in title or any(
                w in title for w in cues.get(t, [])))
            # Always surface DEMO-RISK-001 for the fictional cloud demo family
            if r["id"] == "DEMO-RISK-001" and changed:
                score = max(score, 2)
            if score <= 0:
                continue
            risks_hit.append({
                "risk_id": r["id"],
                "title": r["title"],
                "residual": f"{r['residual_score']} {r['residual_band']}",
                "owner": r.get("owner") or "",
                "reason": (
                    "Hypothesis: theme overlap with changed clause text "
                    f"({', '.join(hit_themes) or 'general'}). Requires human "
                    "review — not an automatic reassessment trigger."),
                "requires_reassessment": True,
                "certainty": "hypothesis",
            })

    if not ctl.empty:
        for _, c in ctl.iterrows():
            name = f"{c['name']} {c.get('description') or ''}".lower()
            score = sum(1 for t in hit_themes if any(w in name for w in cues.get(t, [])))
            if c["id"] == "CTL-DEMO-03" and changed:
                score = max(score, 2)
            if score <= 0:
                continue
            controls_hit.append({
                "control_id": c["id"],
                "name": c["name"],
                "rating": c.get("rating") or "",
                "owner": c.get("owner") or "",
                "reason": (
                    "Hypothesis: control objective may relate to changed recovery/"
                    "testing language. Testing program may need review — not a "
                    "finding of control failure."),
                "testing_program_review": "test" in hit_themes or "recovery" in hit_themes,
                "certainty": "hypothesis",
            })

    return {
        "risks": risks_hit,
        "controls": controls_hit,
        "themes": hit_themes,
        "disclaimer": NOTICE,
    }


def suggested_actions(conn, *, fam, version_a, version_b, diffs, mapping) -> list[dict]:
    """Propose review actions — draft, requiring human review."""
    today = dt.date.today()
    actions = []
    for d in diffs:
        if d["change_kind"] not in ("added", "modified", "removed"):
            continue
        pri = "high" if d["change_kind"] in ("added", "modified") else "medium"
        actions.append({
            "id": f"CIA-{uuid.uuid4().hex[:8]}",
            "clause_ref": d["clause_ref"],
            "change_kind": d["change_kind"],
            "title": (
                f"Review clause {d['clause_ref']} ({d['change_kind']}) for "
                f"{fam['id']} {version_a['version_label']}→{version_b['version_label']}"),
            "owner": "Head of Operational Risk",
            "priority": pri,
            "due_at": (today + dt.timedelta(days=14)).isoformat(),
            "related_risk_id": (mapping["risks"][0]["risk_id"]
                                if mapping["risks"] else ""),
            "related_control_id": (mapping["controls"][0]["control_id"]
                                   if mapping["controls"] else ""),
            "rationale": d["interpretation"],
            "requires_human_review": True,
            "status": "suggested",
        })
    # Dedicated testing-program action when B adds testing language
    if any("test" in (d.get("text_b") or "").lower() for d in diffs):
        actions.append({
            "id": f"CIA-{uuid.uuid4().hex[:8]}",
            "clause_ref": "program",
            "change_kind": "modified",
            "title": "Review control testing program for evidence-supported recovery tests",
            "owner": "Head of Business Continuity",
            "priority": "high",
            "due_at": (today + dt.timedelta(days=21)).isoformat(),
            "related_risk_id": "DEMO-RISK-001",
            "related_control_id": "CTL-DEMO-03",
            "rationale": (
                "Hypothesis: newer version language references periodic "
                "evidence-supported recovery testing. Confirm whether CTL-DEMO-03 "
                "and the testing calendar meet the revised wording. Not a "
                "noncompliance determination."),
            "requires_human_review": True,
            "status": "suggested",
        })
    return actions


def persist_actions(conn, analysis: dict, *, actor: str) -> list[dict]:
    """Write suggested actions into change_impact_action (and optionally action)."""
    saved = []
    fam = analysis["family"]
    va, vb = analysis["version_a"], analysis["version_b"]
    for a in analysis["actions"]:
        row = risk.insert(conn, "change_impact_action", {
            "id": a["id"],
            "family_id": fam["id"],
            "version_a_id": va["id"],
            "version_b_id": vb["id"],
            "clause_ref": a.get("clause_ref") or "",
            "change_kind": a.get("change_kind") or "",
            "title": a["title"],
            "owner": a.get("owner") or "",
            "priority": a.get("priority") or "medium",
            "due_at": a.get("due_at") or "",
            "status": "open",
            "related_risk_id": a.get("related_risk_id") or "",
            "related_control_id": a.get("related_control_id") or "",
            "rationale": a.get("rationale") or "",
            "requires_human_review": 1,
            "is_synthetic": int(fam.get("is_synthetic") or 0),
            "provenance": "synthetic" if fam.get("is_synthetic") else "user",
            "validation_status": "draft",
        }, actor=actor)
        # Also raise a remediation action on the related risk for audit trail
        if a.get("related_risk_id"):
            risk.insert(conn, "action", {
                "id": f"ACT-{a['id']}",
                "source_kind": "change_impact",
                "source_id": a["id"],
                "title": a["title"],
                "owner": a.get("owner") or "",
                "due_at": a.get("due_at") or "",
                "status": "open",
                "priority": a.get("priority") or "medium",
                "related_risk_id": a.get("related_risk_id") or "",
                "control_deficiency": a.get("related_control_id") or "",
                "evidence_required": "Human review outcome + updated mapping notes",
                "validation_outcome": "pending",
                "is_synthetic": int(fam.get("is_synthetic") or 0),
                "provenance": "synthetic" if fam.get("is_synthetic") else "user",
            }, actor=actor)
        saved.append(row)
    return saved


def management_summary(*, fam, version_a, version_b, diffs, mapping,
                       actions) -> dict:
    changed = [d for d in diffs if d["change_kind"] != "unchanged"]
    return {
        "title": f"Change impact — {fam['title']}",
        "family_id": fam["id"],
        "from_version": version_a["version_label"],
        "to_version": version_b["version_label"],
        "publisher_note": fam.get("publisher_note") or FICTIONAL_PUBLISHER,
        "headline": (
            f"{len(changed)} clause-level difference(s) identified between "
            f"{version_a['version_label']} and {version_b['version_label']}. "
            "Differences are hypotheses for review — not materiality or "
            "compliance conclusions."),
        "counts": {k: sum(1 for d in diffs if d["change_kind"] == k)
                   for k in CHANGE_KINDS},
        "key_changes": [
            {"ref": d["clause_ref"], "kind": d["change_kind"],
             "interpretation": d["interpretation"]}
            for d in changed[:8]
        ],
        "risks_for_reassessment": mapping.get("risks") or [],
        "controls_for_review": mapping.get("controls") or [],
        "proposed_actions": [
            {"id": a["id"], "title": a["title"], "owner": a["owner"],
             "priority": a["priority"], "due_at": a["due_at"]}
            for a in actions
        ],
        "disclaimer": NOTICE,
    }


def export_summary_text(summary: dict) -> str:
    lines = [
        f"# {summary['title']}",
        f"Versions: {summary['from_version']} → {summary['to_version']}",
        f"Publisher note: {summary['publisher_note']}",
        "",
        summary["headline"],
        "",
        "## Disclaimer",
        summary["disclaimer"],
        "",
        "## Counts",
        json.dumps(summary["counts"]),
        "",
        "## Key changes",
    ]
    for c in summary["key_changes"]:
        lines.append(f"- [{c['kind']}] {c['ref']}: {c['interpretation']}")
    lines += ["", "## Risks for reassessment"]
    for r in summary["risks_for_reassessment"]:
        lines.append(f"- {r['risk_id']} {r['title']} ({r['certainty']})")
    lines += ["", "## Controls for review"]
    for c in summary["controls_for_review"]:
        lines.append(f"- {c['control_id']} {c['name']} ({c['certainty']})")
    lines += ["", "## Proposed actions"]
    for a in summary["proposed_actions"]:
        lines.append(
            f"- {a['id']}: {a['title']} · {a['owner']} · {a['priority']} · "
            f"due {a['due_at']}")
    return "\n".join(lines)


# --- demo seed --------------------------------------------------------------------

def seed(conn, index_conn=None, *, today: dt.date | None = None,
         force: bool = False) -> dict:
    """Two fictional versions of a cloud resilience requirement."""
    if not force and risk.get_meta(conn, "change_impact_seed_version") == SEED_VERSION:
        return {"seeded": False}
    from . import demo_data
    demo_data.seed(conn, index_conn, today=today)

    family_id = "DEMO-CLOUD-RES"
    ver_a, ver_b = "DEMO-CLOUD-RES-A", "DEMO-CLOUD-RES-B"

    conn.execute("DELETE FROM change_impact_action WHERE family_id=?", (family_id,))
    conn.execute("DELETE FROM action WHERE source_kind='change_impact'")
    for vid in (ver_a, ver_b):
        conn.execute("DELETE FROM reg_doc_clause WHERE version_id=?", (vid,))
        conn.execute("DELETE FROM reg_doc_version WHERE id=?", (vid,))
    conn.execute("DELETE FROM reg_doc_family WHERE id=?", (family_id,))

    risk.insert(conn, "reg_doc_family", {
        "id": family_id,
        "title": "Illustrative Cloud Service Resilience Standard (fictional)",
        "publisher_note": FICTIONAL_PUBLISHER,
        "topic": "cloud recovery / operational resilience",
        "is_synthetic": 1,
    }, actor=ACTOR)

    day = (today or dt.date.today()).isoformat()
    risk.insert(conn, "reg_doc_version", {
        "id": ver_a,
        "family_id": family_id,
        "version_label": "Version A",
        "published_at": "2024-01-15",
        "summary": "Requires documented recovery procedures for critical cloud services.",
        "is_synthetic": 1,
        "provenance": "synthetic",
    }, actor=ACTOR)
    risk.insert(conn, "reg_doc_version", {
        "id": ver_b,
        "family_id": family_id,
        "version_label": "Version B",
        "published_at": "2025-06-01",
        "summary": "Adds periodic evidence-supported recovery testing.",
        "is_synthetic": 1,
        "provenance": "synthetic",
    }, actor=ACTOR)

    clauses_a = [
        ("§1", 1, "Purpose. This illustrative standard sets expectations for "
                  "resilience of critical cloud-hosted services used in payment "
                  "processing. It is fictional demonstration text only."),
        ("§2", 2, "Documented recovery procedures. The firm shall maintain "
                  "documented recovery procedures for each critical cloud-hosted "
                  "service, including roles, steps and communication paths."),
        ("§3", 3, "Dependency inventory. The firm shall keep an inventory of "
                  "material cloud dependencies supporting critical services."),
    ]
    clauses_b = [
        ("§1", 1, "Purpose. This illustrative standard sets expectations for "
                  "resilience of critical cloud-hosted services used in payment "
                  "processing. It is fictional demonstration text only."),
        ("§2", 2, "Documented recovery procedures. The firm shall maintain "
                  "documented recovery procedures for each critical cloud-hosted "
                  "service, including roles, steps and communication paths."),
        ("§2A", 3, "Periodic evidence-supported recovery testing. The firm shall "
                   "perform periodic recovery testing of critical cloud-hosted "
                   "services and retain evidence that tests were completed and "
                   "reviewed. Testing frequency and scope shall be risk-based."),
        ("§3", 4, "Dependency inventory. The firm shall keep an inventory of "
                  "material cloud dependencies supporting critical services."),
    ]
    for ref, seq, text in clauses_a:
        risk.insert(conn, "reg_doc_clause", {
            "id": f"{ver_a}-{ref}",
            "version_id": ver_a,
            "clause_ref": ref,
            "seq": seq,
            "text": text,
            "is_synthetic": 1,
        }, actor=ACTOR)
    for ref, seq, text in clauses_b:
        risk.insert(conn, "reg_doc_clause", {
            "id": f"{ver_b}-{ref}",
            "version_id": ver_b,
            "clause_ref": ref,
            "seq": seq,
            "text": text,
            "is_synthetic": 1,
        }, actor=ACTOR)

    analysis = analyze(conn, ver_a, ver_b)
    persist_actions(conn, analysis, actor=ACTOR)

    risk.set_meta(conn, "change_impact_seed_version", SEED_VERSION)
    risk.set_meta(conn, "change_impact_seeded_at", risk.now())
    return {
        "seeded": True,
        "family_id": family_id,
        "version_a": ver_a,
        "version_b": ver_b,
        "added": analysis["counts"]["added"],
        "modified": analysis["counts"]["modified"],
        "unchanged": analysis["counts"]["unchanged"],
    }
