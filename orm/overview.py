"""Overview dashboard metrics — only values derived from application records."""
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

NOTICE = (
    "Overview metrics are calculated from the current risk store and regulation "
    "index. Synthetic demo rows are labelled. Nothing here is a live Revolut feed."
)


def snapshot(conn, index_conn=None, *, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    iso = today.isoformat()
    reg = risk.register(conn, iso)
    ctl = risk.control_status(conn)
    acts = risk.actions(conn, iso)
    incidents = risk.incidents(conn)
    if im is not None:
        try:
            incidents = im.register(conn)
        except Exception:
            pass

    outside = reg[reg["appetite"] == "Outside appetite"] if not reg.empty else reg
    material = reg[reg["residual_band"].isin(["High", "Critical"])] if not reg.empty else reg

    weak = ctl[ctl["rating"] != "effective"] if not ctl.empty else ctl
    if not weak.empty and "key_control" in weak.columns:
        weak = weak[weak["key_control"].fillna(1).astype(int) == 1]

    kri_breaches = pd.DataFrame()
    kri_trends = pd.DataFrame()
    if ka is not None:
        try:
            lib = ka.library(conn)
            kri_breaches = lib[lib["rag"].isin(["Red", "Amber"])] if not lib.empty else lib
            # Prefer payment-failure series for the demo story
            kid = "KRI-PAY-FAIL"
            if not lib.empty and kid in set(lib["id"]):
                kri_trends = ka.observations(conn, kid)
            elif not lib.empty:
                kri_trends = ka.observations(conn, lib.iloc[0]["id"])
        except Exception:
            pass
    if kri_breaches.empty:
        kris = risk.kri_status(conn)
        kri_breaches = kris[kris["rag"].isin(["Red", "Amber"])] if not kris.empty else kris
        if kri_trends.empty and not kris.empty:
            kid = kris.iloc[0]["id"]
            kri_trends = risk.kri_readings(conn, kid)

    high_inc = pd.DataFrame()
    if not incidents.empty and "severity" in incidents.columns:
        high_inc = incidents[incidents["severity"].isin(["P1", "P2"])]
    overdue = acts[acts["overdue"]] if not acts.empty else acts

    # Heat map counts
    heat = pd.DataFrame(0, index=range(5, 0, -1), columns=range(1, 6))
    if not reg.empty:
        for _, r in reg.iterrows():
            heat.loc[int(r["residual_impact"]), int(r["residual_likelihood"])] += 1

    # Regulatory changes requiring review (from index when available)
    changes = pd.DataFrame()
    if index_conn is not None and queries is not None:
        try:
            since = (today - dt.timedelta(days=365)).isoformat()
            changes = queries.changes_since(index_conn, since)
            if isinstance(changes, pd.DataFrame) and len(changes) > 12:
                changes = changes.head(12)
        except Exception:
            changes = pd.DataFrame()

    # Recent risk events = material incidents + recent audit creates
    recent_events = []
    if not high_inc.empty:
        for _, i in high_inc.head(5).iterrows():
            recent_events.append({
                "kind": "incident",
                "id": i["id"],
                "title": i.get("title") or i["id"],
                "when": i.get("occurred_at") or "",
                "detail": f"Severity {i.get('severity')}",
            })
    for h in risk.history(conn, table="risk", limit=20):
        if h.get("action") != "create":
            continue
        recent_events.append({
            "kind": "risk",
            "id": h.get("object_id"),
            "title": f"Risk recorded {h.get('object_id')}",
            "when": h.get("ts") or "",
            "detail": f"Actor {h.get('actor') or '—'}",
        })
        if len(recent_events) >= 8:
            break

    priority_actions = overdue.head(8) if not overdue.empty else overdue

    return {
        "notice": NOTICE,
        "synthetic": risk.is_synthetic(conn),
        "bank": risk.get_meta(conn, "bank") or "",
        "metrics": {
            "material_risks": 0 if material.empty else len(material),
            "appetite_exceptions": 0 if outside.empty else len(outside),
            "control_weaknesses": 0 if weak.empty else len(weak),
            "kri_breaches": 0 if kri_breaches.empty else len(kri_breaches),
            "high_severity_incidents": 0 if high_inc.empty else len(high_inc),
            "overdue_actions": 0 if overdue.empty else len(overdue),
            "open_risks": 0 if reg.empty else len(reg),
        },
        "register": reg,
        "material": material,
        "outside": outside,
        "weak_controls": weak,
        "kri_breaches": kri_breaches,
        "kri_trends": kri_trends,
        "high_incidents": high_inc,
        "priority_actions": priority_actions,
        "heat": heat,
        "changes": changes if isinstance(changes, pd.DataFrame) else pd.DataFrame(),
        "recent_events": recent_events,
        "empty": reg.empty and (incidents.empty if incidents is not None else True),
    }
