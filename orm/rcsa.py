"""Risk and Control Self-Assessment (RCSA) helpers.

Built on orm.risk. Taxonomy, multi-dimensional impact, gap indicators, heat-map
frames, and the obligation → risk workflow. Scoring methodology is illustrative
and labelled as a prototype — not any bank's approved framework.
"""
from __future__ import annotations

import json
import uuid

import pandas as pd

from . import risk, taxonomy

# Basel II level-1 event types (exclusive primary category).
EVENT_TAXONOMY = tuple(
    {"id": f"ET-{i}", "name": name} for i, name in enumerate(risk.EVENT_TYPES, 1)
)

# Cross-cutting lenses — not forced into exclusive event categories.
CROSS_CUTTING_TAXONOMY = tuple(
    {"id": f"XC-{i}", "name": name} for i, name in enumerate(risk.CROSS_CUTTING, 1)
)

SCALE_CARD = {
    "likelihood": risk.LIKELIHOOD_LABELS,
    "impact": risk.IMPACT_LABELS,
    "bands": risk.BANDS,
    "impact_dimensions": risk.IMPACT_DIMENSIONS,
    "impact_aggregation_default": "max",
    "method_note": risk.METHOD_NOTE,
}


def parse_cross_cutting(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    try:
        data = json.loads(value)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return [p.strip() for p in str(value).split(",") if p.strip()]


def heat_map(reg: pd.DataFrame, *, view: str = "residual") -> pd.DataFrame:
    """5×5 counts. view = residual | inherent."""
    heat = pd.DataFrame(0, index=range(5, 0, -1), columns=range(1, 6))
    if reg is None or reg.empty:
        return heat
    lcol = "residual_likelihood" if view == "residual" else "inherent_likelihood"
    icol = "residual_impact" if view == "residual" else "inherent_impact"
    for _, r in reg.iterrows():
        heat.loc[int(r[icol]), int(r[lcol])] += 1
    return heat


def filter_register(reg: pd.DataFrame, *, business_unit: str = "",
                    category_id: str = "", event_type: str = "",
                    cross_cutting: str = "") -> pd.DataFrame:
    if reg is None or reg.empty:
        return reg
    out = reg
    if business_unit:
        out = out[out["business_unit"] == business_unit]
    if category_id:
        out = out[out["category_id"] == category_id]
    if event_type:
        out = out[out["event_type"] == event_type]
    if cross_cutting:
        out = out[out["cross_cutting"].fillna("").map(
            lambda x: cross_cutting in parse_cross_cutting(x))]
    return out.reset_index(drop=True)


def control_gaps(conn, today: str | None = None) -> pd.DataFrame:
    """Workflow indicators for review — not regulatory noncompliance conclusions."""
    reg = risk.register(conn, today)
    ctl = risk.control_status(conn)
    acts = risk.actions(conn, today)
    today = today or risk._today()
    rows = []

    def add(risk_id, title, kind, detail, severity="review"):
        rows.append({"risk_id": risk_id, "title": title, "gap_kind": kind,
                     "detail": detail, "severity": severity,
                     "disclaimer": "Indicator for review — not a compliance conclusion."})

    if reg.empty:
        return pd.DataFrame(rows)

    for _, r in reg.iterrows():
        rid, title = r["id"], r["title"]
        if int(r["controls"]) == 0:
            add(rid, title, "no_linked_controls",
                "Risk has no linked controls.", "high")
        if int(r["inherent_score"]) >= 10 and int(r["untested_controls"]) > 0:
            add(rid, title, "high_risk_untested_controls",
                f"{int(r['untested_controls'])} linked control(s) not tested "
                f"(inherent score {int(r['inherent_score'])}).", "high")
        if int(r["weak_controls"]) > 0:
            add(rid, title, "weak_or_failed_controls",
                f"{int(r['weak_controls'])} linked control(s) not rated effective.",
                "medium")
        if not (r.get("owner") or "").strip():
            add(rid, title, "missing_owner", "Risk owner is blank.", "high")
        nxt = r.get("next_review_at") or ""
        if nxt and nxt < today:
            add(rid, title, "overdue_review",
                f"Next review date {nxt} is past.", "high")
        if r.get("appetite") == "Outside appetite":
            add(rid, title, "outside_appetite",
                "Residual score or KRI breach is outside stated appetite.", "high")
        if int(r["overdue_actions"]) > 0:
            add(rid, title, "overdue_actions",
                f"{int(r['overdue_actions'])} remediation action(s) past due.",
                "high")
        if not r.get("residual_assessed"):
            add(rid, title, "residual_not_approved",
                "Residual risk has not been explicitly approved by a named assessor.",
                "medium")

    # Control-level evidence / failed tests (not tied to one risk only)
    if not ctl.empty:
        for _, c in ctl.iterrows():
            if c["rating"] == "ineffective":
                linked = conn.execute(
                    "SELECT risk_id FROM risk_control WHERE control_id=?",
                    (c["id"],)).fetchall()
                for (rid,) in linked or [(None,)]:
                    title = ""
                    if rid and not reg.empty and (reg["id"] == rid).any():
                        title = reg.loc[reg["id"] == rid, "title"].iloc[0]
                    add(rid or "—", title or c["name"], "failed_control_test",
                        f"Control {c['id']} latest test is ineffective: "
                        f"{c.get('findings') or 'no findings recorded'}.", "high")
            if not (c.get("evidence_ref") or "").strip() and c.get("tested_at"):
                add("—", c["name"], "missing_evidence",
                    f"Control {c['id']} has a test date but no evidence reference.",
                    "medium")

    if not acts.empty:
        for _, a in acts[acts["overdue"]].iterrows():
            add(a["source_id"] if a["source_kind"] == "risk" else "—",
                a["title"], "overdue_actions",
                f"Action {a['id']} due {a['due_at']} is overdue "
                f"(from {a['source_kind']} {a['source_id']}).", "high")

    return pd.DataFrame(rows).drop_duplicates(
        subset=["risk_id", "gap_kind", "detail"]).reset_index(drop=True) \
        if rows else pd.DataFrame(rows)


def suggest_residual(conn, risk_id: str) -> dict:
    """Optional heuristic suggestion from control tests. Never auto-applied."""
    chain = risk.risk_chain(conn, risk_id)
    r = chain["risk"]
    s = chain["summary"]
    if not s:
        raise LookupError(risk_id)
    return {
        "risk_id": risk_id,
        "inherent_likelihood": s["inherent_likelihood"],
        "inherent_impact": s["inherent_impact"],
        "inherent_score": s["inherent_score"],
        "suggested_likelihood": s["suggested_residual_likelihood"],
        "suggested_impact": s["suggested_residual_impact"],
        "suggested_score": s["suggested_residual_score"],
        "note": (
            "Illustrative suggestion from the weakest key-control ratings. "
            "A named assessor must confirm residual likelihood and impact; "
            "controls do not reduce inherent risk automatically."
        ),
        "validation_status": "suggested",
        "current_residual_status": s.get("residual_status"),
        "owner": r.get("owner") or "",
    }


def create_risk_from_obligation(conn, index_conn, *, okey: str, title: str,
                                description: str, event_type: str, category_id: str,
                                causes: str, consequences: str,
                                inherent_likelihood: int, inherent_impact: int,
                                owner: str, actor: str,
                                business_process: str = "",
                                business_unit: str = "",
                                legal_entity: str = "",
                                jurisdiction: str = "",
                                cross_cutting: list[str] | None = None,
                                impact_dimensions: dict | None = None,
                                risk_id: str | None = None,
                                is_synthetic: int = 0) -> dict:
    """Acceptance path: obligation → new risk with linked citation."""
    cite = risk.obligation_citation(index_conn, okey)
    if not cite:
        raise LookupError("Obligation not found in the regulation index.")
    if event_type not in risk.EVENT_TYPES:
        raise ValueError("Unknown event type.")
    if category_id not in taxonomy.BY_ID:
        raise ValueError("Unknown risk category.")
    for v in (inherent_likelihood, inherent_impact):
        if not 1 <= int(v) <= 5:
            raise ValueError("Ratings run from 1 to 5.")
    dims = impact_dimensions or {}
    agg = risk.aggregate_impact(dims, "max")
    impact = int(agg if agg is not None else inherent_impact)
    rid = risk_id or f"RSK-{uuid.uuid4().hex[:8].upper()}"
    row = risk.insert(conn, "risk", {
        "id": rid,
        "title": title.strip(),
        "description": description.strip(),
        "cause": causes.strip(),
        "effect": consequences.strip(),
        "category_id": category_id,
        "event_type": event_type,
        "owner": owner.strip(),
        "inherent_likelihood": int(inherent_likelihood),
        "inherent_impact": impact,
        "business_process": business_process.strip(),
        "business_unit": business_unit.strip(),
        "legal_entity": legal_entity.strip(),
        "jurisdiction": jurisdiction.strip(),
        "cross_cutting": json.dumps(cross_cutting or [], ensure_ascii=False),
        "impact_financial": dims.get("financial"),
        "impact_customer": dims.get("customer"),
        "impact_operational": dims.get("operational"),
        "impact_regulatory": dims.get("regulatory"),
        "impact_reputational": dims.get("reputational"),
        "residual_status": "not_assessed",
        "assessed_at": risk._today(),
        "next_review_at": "",
        "provenance": "user",
        "validation_status": "draft",
        "is_synthetic": int(is_synthetic),
    }, actor=actor)
    risk.insert(conn, "risk_obligation", {
        "risk_id": rid,
        "okey": okey,
        "document_id": cite["document_id"],
        "clause_ref": cite.get("clause_ref") or "",
        "citation": cite.get("citation") or "",
        "link": cite.get("link") or "",
        "sentence": cite["sentence"],
        "sentence_sha": risk.sentence_sha(cite["sentence"]),
        "rationale": "Created from obligation via RCSA workflow",
        "provenance": "user",
        "validation_status": "validated",
        "is_synthetic": int(is_synthetic),
    }, actor=actor)
    return row


def link_control(conn, *, risk_id: str, control_id: str, reduces: str = "likelihood",
                 actor: str) -> dict:
    if reduces not in ("likelihood", "impact", "both"):
        raise ValueError("reduces must be likelihood, impact or both")
    return risk.insert(conn, "risk_control", {
        "risk_id": risk_id, "control_id": control_id, "reduces": reduces,
    }, actor=actor)


def upsert_control(conn, row: dict, *, actor: str) -> dict:
    """Create or update a control with RCSA fields."""
    payload = {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "objective": row.get("objective") or row.get("description") or "",
        "type": row.get("type") or "preventive",
        "nature": row.get("nature") or "manual",
        "frequency": row.get("frequency") or "",
        "owner": row.get("owner") or "",
        "business_process": row.get("business_process") or "",
        "library_id": row.get("library_id") or "",
        "bank_control_ref": row.get("bank_control_ref") or "",
        "key_control": int(row.get("key_control", 1)),
        "exceptions": row.get("exceptions") or "",
        "remediation_status": row.get("remediation_status") or "",
        "status": row.get("status") or "active",
        "provenance": row.get("provenance") or "user",
        "validation_status": row.get("validation_status") or "draft",
        "is_synthetic": int(row.get("is_synthetic") or 0),
    }
    existing = conn.execute("SELECT id FROM control WHERE id=?", (payload["id"],)).fetchone()
    if existing:
        return risk.update(conn, "control", payload["id"], payload, actor=actor)
    return risk.insert(conn, "control", payload, actor=actor)
