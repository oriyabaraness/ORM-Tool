"""Overview dashboard metrics — only values derived from application records.

Powers the Risk Overview page. No fabricated trends: time series appear only
when observation history exists. Attention items are deduplicated by source.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import risk

try:
    from . import kri_appetite as ka
except Exception:  # pragma: no cover
    ka = None
try:
    from . import incident_mgmt as im
except Exception:  # pragma: no cover
    im = None
try:
    from . import queries
except Exception:  # pragma: no cover
    queries = None
try:
    from . import regulatory_intel as ri
except Exception:  # pragma: no cover
    ri = None

NOTICE = (
    "Overview metrics are calculated from the current risk store and regulation "
    "index. Synthetic demo rows are labelled. Nothing here is a live Revolut feed."
)

BAND_ORDER = ("Critical", "High", "Moderate", "Medium", "Low")


def _band_counts(series: pd.Series) -> dict[str, int]:
    counts = {b: 0 for b in ("Critical", "High", "Moderate", "Low")}
    if series is None or series.empty:
        return counts
    for v in series.dropna():
        label = str(v)
        if label == "Medium":
            label = "Moderate"
        if label in counts:
            counts[label] += 1
    return counts


def snapshot(conn, index_conn=None, *, today: dt.date | None = None,
             period: str = "monthly",
             legal_entity: str | None = None) -> dict:
    today = today or dt.date.today()
    iso = today.isoformat()
    reg = risk.register(conn, iso)
    if legal_entity and not reg.empty and "legal_entity" in reg.columns:
        reg = reg[reg["legal_entity"].fillna("") == legal_entity]

    ctl = risk.control_status(conn)
    acts = risk.actions(conn, iso)
    incidents = risk.incidents(conn)
    if im is not None:
        try:
            incidents = im.register(conn)
        except Exception:
            pass

    outside = reg[reg["appetite"] == "Outside appetite"] if not reg.empty else reg
    # Residual bands for distribution / material KPIs use assessed residuals only —
    # suggested scores must not inflate Low / Moderate / High counts.
    if reg.empty:
        assessed = reg
        unassessed = reg
    else:
        assessed_mask = reg["residual_assessed"].fillna(False).astype(bool)
        assessed = reg[assessed_mask]
        unassessed = reg[~assessed_mask]
    material = (
        assessed[assessed["residual_band"].isin(["High", "Critical"])]
        if not assessed.empty else assessed)

    weak = ctl[ctl["rating"] != "effective"] if not ctl.empty else ctl
    if not weak.empty and "key_control" in weak.columns:
        weak = weak[weak["key_control"].fillna(1).astype(int) == 1]

    kri_breaches = pd.DataFrame()
    kri_trends = pd.DataFrame()
    kri_trend_label = ""
    kri_note = ""
    if ka is not None:
        try:
            lib = ka.library(conn)
            kri_breaches = lib[lib["rag"].isin(["Red", "Amber"])] if not lib.empty else lib
            # Prefer a breached KRI that has a real observation series
            candidates = []
            if not kri_breaches.empty:
                candidates.extend(kri_breaches["id"].tolist())
            if not lib.empty:
                candidates.extend([i for i in lib["id"].tolist() if i not in candidates])
            for kid in candidates:
                obs = ka.observations(conn, kid)
                if obs is not None and not obs.empty and "value" in obs.columns:
                    kri_trends = obs
                    kri_trend_label = kid
                    if len(obs) >= 2:
                        break
            if kri_trends.empty and "KRI-PAY-FAIL" in set(lib["id"] if not lib.empty else []):
                kri_trend_label = "KRI-PAY-FAIL"
                kri_trends = ka.observations(conn, kri_trend_label)
        except Exception:
            pass
    if kri_breaches.empty:
        kris = risk.kri_status(conn)
        kri_breaches = kris[kris["rag"].isin(["Red", "Amber"])] if not kris.empty else kris
        if kri_trends.empty and not kris.empty:
            for kid in kris["id"].tolist():
                series = risk.kri_readings(conn, kid)
                if series is not None and not series.empty:
                    kri_trends = series
                    kri_trend_label = kid
                    break

    high_inc = pd.DataFrame()
    if not incidents.empty and "severity" in incidents.columns:
        high_inc = incidents[incidents["severity"].isin(["P1", "P2"])]
    overdue = acts[acts["overdue"]] if not acts.empty else acts

    residual_dist = _band_counts(
        assessed["residual_band"] if not assessed.empty else pd.Series(dtype=object))
    inherent_dist = _band_counts(
        reg["inherent_band"] if not reg.empty else pd.Series(dtype=object))

    # Exposure chart frame retained for secondary use (assessed residual only).
    exposure_rows = []
    for band in ("Low", "Moderate", "High", "Critical"):
        exposure_rows.append({
            "band": band,
            "Inherent": inherent_dist.get(band, 0),
            "Residual": residual_dist.get(band, 0),
        })
    exposure = pd.DataFrame(exposure_rows)

    exposure_breakdown = _exposure_breakdown(
        assessed=assessed, unassessed=unassessed, residual_dist=residual_dist,
        acts=acts)

    # Genuine KRI history only when ≥2 observations exist
    has_kri_history = (
        kri_trends is not None and not kri_trends.empty
        and "value" in kri_trends.columns and len(kri_trends) >= 2)
    if not kri_breaches.empty and not has_kri_history:
        kri_note = (
            f"{len(kri_breaches)} KRI(s) are currently Red/Amber on latest status, "
            "but a multi-point observation series is not available in this store. "
            "Breach count uses latest RAG; the trend chart is blank until history exists."
        )
    elif has_kri_history:
        kri_note = f"Trend series: {kri_trend_label} (recorded observations)."

    assessment_comparison = _assessment_comparison(assessed)
    control_assessment = _control_assessment(
        assessed=assessment_comparison, ctl=ctl, conn=conn, acts=acts)

    categories = []
    if not assessed.empty and "category" in assessed.columns:
        categories = sorted({c for c in assessed["category"].fillna("").tolist() if c})

    changes = pd.DataFrame()
    if index_conn is not None and queries is not None:
        try:
            since = (today - dt.timedelta(days=365)).isoformat()
            changes = queries.changes_since(index_conn, since)
            if isinstance(changes, pd.DataFrame) and len(changes) > 12:
                changes = changes.head(12)
        except Exception:
            changes = pd.DataFrame()

    applicability_pending = pd.DataFrame()
    if ri is not None:
        try:
            apps = ri.list_applicability(conn)
            if not apps.empty:
                applicability_pending = apps[apps["status"].isin(
                    ["not_yet_assessed", "requires_interpretation",
                     "potentially_applicable"])]
        except Exception:
            applicability_pending = pd.DataFrame()

    # Open change-impact review actions (table may be absent on older DBs)
    change_actions = pd.DataFrame()
    try:
        change_actions = risk._df(conn, """
            SELECT * FROM change_impact_action
            WHERE status IN ('open', 'suggested')
            ORDER BY due_at, id LIMIT 8""")
    except Exception:
        change_actions = pd.DataFrame()

    attention = _attention_queue(
        outside=outside, kri_breaches=kri_breaches, weak=weak,
        overdue=overdue, high_inc=high_inc)

    recent_activity = _recent_activity(conn, high_inc, ctl, acts)

    entities = []
    if not reg.empty and "legal_entity" in reg.columns:
        entities = sorted({e for e in reg["legal_entity"].fillna("").tolist() if e})

    return {
        "notice": NOTICE,
        "synthetic": risk.is_synthetic(conn),
        "bank": risk.get_meta(conn, "bank") or "",
        "as_of": iso,
        "period": period,
        "legal_entity": legal_entity or "",
        "legal_entities": entities,
        "updated_at": risk.now(),
        "metrics": {
            "material_residual_risks": 0 if material.empty else len(material),
            "kri_threshold_breaches": 0 if kri_breaches.empty else len(kri_breaches),
            "critical_control_gaps": 0 if weak.empty else len(weak),
            "overdue_risk_actions": 0 if overdue.empty else len(overdue),
            # retained for tests / secondary use
            "material_risks": 0 if material.empty else len(material),
            "appetite_exceptions": 0 if outside.empty else len(outside),
            "control_weaknesses": 0 if weak.empty else len(weak),
            "kri_breaches": 0 if kri_breaches.empty else len(kri_breaches),
            "high_severity_incidents": 0 if high_inc.empty else len(high_inc),
            "overdue_actions": 0 if overdue.empty else len(overdue),
            "open_risks": 0 if reg.empty else len(reg),
            "assessed_risks": 0 if assessed.empty else len(assessed),
            "unassessed_risks": 0 if unassessed.empty else len(unassessed),
            "high_critical_residual": exposure_breakdown["high_critical"],
            "moderate_residual": exposure_breakdown["moderate"],
            "low_residual": exposure_breakdown["low"],
        },
        "kpi_links": {
            "material_residual_risks": "risks",
            "kri_threshold_breaches": "kri",
            "critical_control_gaps": "controls",
            "overdue_risk_actions": "incidents",
        },
        "register": reg,
        "assessed": assessed,
        "unassessed": unassessed,
        "exposure_breakdown": exposure_breakdown,
        "material": material,
        "material_priorities": exposure_breakdown["priorities"],
        "assessment_comparison": assessment_comparison,
        "control_assessment": control_assessment,
        "risk_categories": categories,
        "outside": outside,
        "weak_controls": weak,
        "kri_breaches": kri_breaches,
        "kri_trends": kri_trends,
        "kri_trend_label": kri_trend_label,
        "has_kri_history": has_kri_history,
        "kri_note": kri_note,
        "high_incidents": high_inc,
        "priority_actions": overdue.head(8) if not overdue.empty else overdue,
        "exposure": exposure,
        "residual_distribution": residual_dist,
        "inherent_distribution": inherent_dist,
        "attention": attention,
        "changes": changes if isinstance(changes, pd.DataFrame) else pd.DataFrame(),
        "applicability_pending": applicability_pending,
        "change_actions": change_actions,
        "recent_activity": recent_activity,
        "empty": reg.empty and (incidents.empty if incidents is not None else True),
    }


def _exposure_breakdown(*, assessed, unassessed, residual_dist, acts) -> dict:
    """Assessed residual distribution + sorted material priorities for Overview."""
    high_critical = (
        int(residual_dist.get("Critical", 0)) + int(residual_dist.get("High", 0)))
    moderate = int(residual_dist.get("Moderate", 0))
    low = int(residual_dist.get("Low", 0))
    n_unassessed = 0 if unassessed is None or unassessed.empty else len(unassessed)
    assessed_n = high_critical + moderate + low

    # Stacked bar segments — High/Critical combined for the executive view
    segments = [
        {"key": "high_critical", "label": "High / Critical",
         "count": high_critical, "color": "#c45c4a"},
        {"key": "moderate", "label": "Moderate",
         "count": moderate, "color": "#c9a227"},
        {"key": "low", "label": "Low",
         "count": low, "color": "#3d8b5e"},
    ]

    priorities = _material_priorities(assessed, acts)

    return {
        "high_critical": high_critical,
        "moderate": moderate,
        "low": low,
        "unassessed": n_unassessed,
        "assessed": assessed_n,
        "segments": segments,
        "priorities": priorities,
        "method_note": risk.METHOD_NOTE,
    }


def _top_open_action(acts: pd.DataFrame, risk_id: str) -> str:
    if acts is None or acts.empty:
        return "—"
    mine = acts[(acts["source_kind"] == "risk") & (acts["source_id"] == risk_id)
                & (acts["status"] != "done")]
    if mine.empty:
        return "—"
    mine = mine.copy()
    mine["_rank"] = mine["overdue"].map(lambda o: 0 if o else 1)
    mine = mine.sort_values(["_rank", "due_at", "id"])
    title = mine.iloc[0].get("title") or mine.iloc[0]["id"]
    if mine.iloc[0].get("overdue"):
        return f"{title} (overdue)"
    return str(title)


def _assessment_comparison(assessed: pd.DataFrame) -> pd.DataFrame:
    """Inherent vs residual scores for assessed risks, highest residual first.

    UI limits to 5–8 rows and applies category filters. Scores are documented
    assessments only — never suggested residuals.
    """
    cols = [
        "id", "title", "category", "owner", "inherent_score", "residual_score",
        "inherent_band", "residual_band", "inherent_likelihood", "inherent_impact",
        "residual_likelihood", "residual_impact", "is_synthetic", "assessed_at",
    ]
    if assessed is None or assessed.empty:
        return pd.DataFrame(columns=cols)
    df = assessed.copy()
    df = df.sort_values(
        ["residual_score", "inherent_score"], ascending=[False, False],
        na_position="last")
    keep = [c for c in cols if c in df.columns]
    return df[keep].reset_index(drop=True)


def _evidence_status(row) -> str:
    rating = str(row.get("rating") or "not_tested")
    if rating in ("not_tested", "not_assessed") or pd.isna(row.get("test_id")):
        return "Not tested"
    evidence = row.get("evidence_ref")
    try:
        has_ev = bool(evidence) and not (isinstance(evidence, float) and pd.isna(evidence))
    except (TypeError, ValueError):
        has_ev = bool(evidence)
    if has_ev:
        return "Evidence recorded"
    return "Tested · evidence missing"


def _format_control_rating(rating: str) -> str:
    return {
        "effective": "Effective",
        "partially_effective": "Partially effective",
        "ineffective": "Ineffective",
        "not_tested": "Not tested",
        "not_assessed": "Not assessed",
    }.get(rating, rating.replace("_", " ").title() if rating else "Not assessed")


def _control_assessment(*, assessed, ctl, conn, acts) -> pd.DataFrame:
    """Per-risk control effectiveness summary for the comparison set."""
    cols = ["id", "title", "control_effectiveness", "effectiveness_kind",
            "evidence_status", "owner", "outstanding_action", "is_synthetic"]
    if assessed is None or assessed.empty:
        return pd.DataFrame(columns=cols)
    links = risk._df(conn, "SELECT risk_id, control_id FROM risk_control")
    ctl_ix = {}
    if ctl is not None and not ctl.empty:
        ctl_ix = ctl.set_index("id").to_dict("index")

    rank = {"ineffective": 0, "partially_effective": 1, "not_tested": 2,
            "not_assessed": 2, "effective": 3}
    rows = []
    for _, r in assessed.iterrows():
        rid = r["id"]
        linked_ids = []
        if not links.empty:
            linked_ids = links.loc[links["risk_id"] == rid, "control_id"].tolist()
        linked = [ctl_ix[c] for c in linked_ids if c in ctl_ix]
        if not linked:
            eff, kind, evidence = "No linked controls", "na", "—"
        else:
            worst = min(linked, key=lambda c: rank.get(str(c.get("rating") or "not_tested"), 9))
            rating = str(worst.get("rating") or "not_tested")
            eff = _format_control_rating(rating)
            if len(linked) > 1:
                eff = f"{eff} (weakest of {len(linked)})"
            kind = rating if rating in rank else "na"
            # Evidence: worst-case across linked controls
            statuses = [_evidence_status(c) for c in linked]
            if any(s == "Not tested" for s in statuses):
                evidence = "Not tested"
            elif any(s == "Tested · evidence missing" for s in statuses):
                evidence = "Tested · evidence missing"
            else:
                evidence = "Evidence recorded"
        rows.append({
            "id": rid,
            "title": r.get("title") or rid,
            "control_effectiveness": eff,
            "effectiveness_kind": kind,
            "evidence_status": evidence,
            "owner": r.get("owner") or "—",
            "outstanding_action": _top_open_action(acts, rid),
            "is_synthetic": int(r.get("is_synthetic") or 0),
        })
    return pd.DataFrame(rows, columns=cols)


def _material_priorities(assessed: pd.DataFrame, acts: pd.DataFrame) -> pd.DataFrame:
    """High/Critical assessed risks, sorted for management attention."""
    cols = ["id", "title", "residual_band", "residual_score", "owner", "appetite",
            "top_action", "is_synthetic", "assessed_at", "overdue_actions"]
    if assessed is None or assessed.empty:
        return pd.DataFrame(columns=cols)
    mat = assessed[assessed["residual_band"].isin(["High", "Critical"])].copy()
    if mat.empty:
        return pd.DataFrame(columns=cols)

    band_rank = {"Critical": 0, "High": 1, "Moderate": 2, "Medium": 2, "Low": 3}
    mat["_appetite_rank"] = mat["appetite"].map(
        lambda a: 0 if a == "Outside appetite" else 1)
    mat["_band_rank"] = mat["residual_band"].map(lambda b: band_rank.get(str(b), 9))
    mat["_overdue_rank"] = mat["overdue_actions"].fillna(0).astype(int).map(
        lambda n: 0 if n > 0 else 1)
    # Most recent assessment first → invert string sort with ascending=False
    # Sort: appetite breach → residual severity → overdue remediation → recent assessment
    mat = mat.sort_values(
        ["_appetite_rank", "_band_rank", "residual_score", "_overdue_rank",
         "assessed_at"],
        ascending=[True, True, False, True, False],
        na_position="last")
    mat["top_action"] = [_top_open_action(acts, rid) for rid in mat["id"]]
    keep = [c for c in cols if c in mat.columns or c == "top_action"]
    return mat[keep].reset_index(drop=True)


def _attention_queue(*, outside, kri_breaches, weak, overdue, high_inc) -> pd.DataFrame:
    """Unified, deduplicated management-attention rows. Transparent priority."""
    rows = []
    seen = set()

    def _clean(v, fallback="—"):
        if v is None:
            return fallback
        try:
            if pd.isna(v):
                return fallback
        except (TypeError, ValueError):
            pass
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "nat"):
            return fallback
        return s

    def add(key, issue, category, severity, owner, when, status, page, record_id):
        if key in seen:
            return
        seen.add(key)
        sev = _clean(severity, "—")
        sev_rank = {"Critical": 0, "High": 1, "P1": 0, "P2": 1, "Red": 0,
                    "Amber": 2, "Moderate": 3, "Medium": 3}.get(sev, 4)
        rows.append({
            "key": key,
            "issue": issue,
            "category": category,
            "severity": sev,
            "owner": _clean(owner),
            "when": _clean(when),
            "status": _clean(status, "open"),
            "page": page,
            "record_id": record_id,
            "_rank": sev_rank,
        })

    if outside is not None and not outside.empty:
        for _, r in outside.iterrows():
            add(f"risk:{r['id']}", f"{r['id']} — {r['title']}",
                "Risk above appetite", r.get("residual_band") or "High",
                r.get("owner"), r.get("next_review_at") or r.get("assessed_at"),
                r.get("residual_status") or "open", "risks", r["id"])

    if kri_breaches is not None and not kri_breaches.empty:
        for _, k in kri_breaches.iterrows():
            kid = k.get("id") or k.get("kri_id")
            add(f"kri:{kid}", f"{kid} — {k.get('name') or 'KRI'}",
                "KRI breach", k.get("rag") or "Red",
                k.get("metric_owner") or k.get("owner"),
                k.get("period") or k.get("observed_at"),
                "Threshold breach", "kri", kid)

    if weak is not None and not weak.empty:
        for _, c in weak.iterrows():
            add(f"ctl:{c['id']}", f"{c['id']} — {c.get('name') or 'Control'}",
                "Failed / ineffective control",
                "High" if c.get("rating") == "ineffective" else "Moderate",
                c.get("owner"), c.get("tested_at") or "never",
                c.get("rating") or "not effective", "controls", c["id"])

    if overdue is not None and not overdue.empty:
        for _, a in overdue.iterrows():
            add(f"act:{a['id']}", a.get("title") or a["id"],
                "Overdue remediation", "High",
                a.get("owner"), a.get("due_at"),
                a.get("status") or "open",
                "incidents" if a.get("source_kind") == "incident" else "risks",
                a.get("source_id") or a["id"])

    if high_inc is not None and not high_inc.empty:
        for _, i in high_inc.iterrows():
            add(f"inc:{i['id']}", f"{i['id']} — {i.get('title') or 'Incident'}",
                "High-severity incident", i.get("severity") or "P1",
                i.get("owner"), i.get("occurred_at") or i.get("detected_at"),
                i.get("workflow_status") or i.get("status") or "open",
                "incidents", i["id"])

    if not rows:
        return pd.DataFrame(columns=[
            "issue", "category", "severity", "owner", "when", "status",
            "page", "record_id"])
    df = pd.DataFrame(rows).sort_values(["_rank", "when"]).drop(columns=["_rank", "key"])
    return df.reset_index(drop=True)


def _recent_activity(conn, high_inc, ctl, acts) -> list[dict]:
    """Reliable activity only — audit log + recent incidents / tests."""
    items = []
    if high_inc is not None and not high_inc.empty:
        for _, i in high_inc.head(4).iterrows():
            items.append({
                "kind": "incident",
                "id": i["id"],
                "title": i.get("title") or i["id"],
                "when": i.get("occurred_at") or "",
                "detail": f"Severity {i.get('severity')}",
                "page": "incidents",
            })
    if ctl is not None and not ctl.empty and "tested_at" in ctl.columns:
        tested = ctl[ctl["tested_at"].notna() & (ctl["tested_at"] != "")].copy()
        if not tested.empty:
            tested = tested.sort_values("tested_at", ascending=False).head(3)
            for _, c in tested.iterrows():
                items.append({
                    "kind": "control_test",
                    "id": c["id"],
                    "title": c.get("name") or c["id"],
                    "when": c.get("tested_at") or "",
                    "detail": f"Rating {c.get('rating') or '—'}",
                    "page": "controls",
                })
    for h in risk.history(conn, limit=30):
        if h.get("table_name") not in ("risk", "action", "control_test", "incident"):
            continue
        if h.get("action") not in ("create", "update"):
            continue
        items.append({
            "kind": h.get("table_name"),
            "id": h.get("object_id"),
            "title": f"{h.get('table_name')} {h.get('action')}",
            "when": h.get("ts") or "",
            "detail": f"Actor {h.get('actor') or '—'}",
            "page": {"risk": "risks", "action": "risks", "incident": "incidents",
                     "control_test": "controls"}.get(h.get("table_name"), "risks"),
        })
        if len(items) >= 10:
            break
    # Prefer most recent timestamps first when present
    items.sort(key=lambda x: x.get("when") or "", reverse=True)
    return items[:8]
