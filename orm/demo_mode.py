"""Demo Mode — isolated synthetic risk dataset and guided interview tour.

When Demo Mode is on, ORM_RISK_DB points at a dedicated demo SQLite file so
reset never touches the live risk store. Regulation quotes still come from
the shared index (orm.db). Records are labelled synthetic and never described
as Revolut data.
"""
from __future__ import annotations

import os
from typing import Any

from . import risk

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DB_PATH = os.path.join(HERE, "data", "orm_risk_demo.db")
DEMO_BANNER = (
    "Demo Mode — Synthetic Data. Hypothetical digital-payments entity only. "
    "Not Revolut data. Live user risk data is not modified."
)

# Guided walkthrough — each step lands on a real module page.
TOUR_STEPS: list[dict[str, Any]] = [
    {
        "step": 1,
        "title": "Select a sourced regulatory obligation",
        "explain": "Open a Bank of Israel clause linked to the payment-disruption risk.",
        "page_key": "regulatory",
        "focus": "DEMO-RISK-001 obligation links (Directive 362 / continuity).",
    },
    {
        "step": 2,
        "title": "Review the linked payment risk and controls",
        "explain": "Inspect DEMO-RISK-001 and its suggested controls, including failover testing.",
        "page_key": "risks",
        "focus": "Risk DEMO-RISK-001 · controls CTL-DEMO-01…05.",
    },
    {
        "step": 3,
        "title": "Inspect inherent and residual exposure",
        "explain": "Open RCSA to see explicit residual assessment — not auto-calculated from controls alone.",
        "page_key": "rcsa",
        "focus": "DEMO-RISK-001 residual score and approval status.",
    },
    {
        "step": 4,
        "title": "Observe a KRI breach and related incident",
        "explain": "Payment-failure KRI rises to Red; INC-DEMO-CLOUD shows the 100-minute disruption timeline.",
        "page_key": "kri",
        "focus": "KRI-PAY-FAIL Red · then Incidents → INC-DEMO-CLOUD.",
        "also_page_key": "incidents",
    },
    {
        "step": 5,
        "title": "Generate a management summary",
        "explain": "Produce the executive pack with a remediation action for the unresolved failover finding.",
        "page_key": "executive",
        "focus": "Executive report export · committee action on failover re-test.",
    },
]


def demo_db_path() -> str:
    return DEMO_DB_PATH


def is_enabled(session: dict) -> bool:
    return bool(session.get("demo_mode"))


def apply_env(session: dict) -> None:
    """Point ORM_RISK_DB at the demo file when Demo Mode is on."""
    if is_enabled(session):
        os.makedirs(os.path.dirname(DEMO_DB_PATH), exist_ok=True)
        # Remember live path once
        if "demo_live_path" not in session:
            session["demo_live_path"] = os.environ.get(
                "ORM_RISK_DB", risk.default_path())
        os.environ["ORM_RISK_DB"] = DEMO_DB_PATH
    else:
        live = session.get("demo_live_path")
        if live and os.environ.get("ORM_RISK_DB") == DEMO_DB_PATH:
            os.environ["ORM_RISK_DB"] = live
        elif os.environ.get("ORM_RISK_DB") == DEMO_DB_PATH:
            # Fall back to package default without wiping caller's unset state oddly
            os.environ.pop("ORM_RISK_DB", None)


def enable(session: dict) -> None:
    if "demo_live_path" not in session:
        session["demo_live_path"] = os.environ.get("ORM_RISK_DB", risk.default_path())
    session["demo_mode"] = True
    apply_env(session)
    ensure_seeded()


def disable(session: dict) -> None:
    session["demo_mode"] = False
    session["demo_tour_step"] = None
    session["demo_tour_active"] = False
    apply_env(session)


def reset(session: dict) -> None:
    """Wipe only the demo SQLite file and re-seed. Never touches live DB."""
    apply_env(session)
    path = DEMO_DB_PATH
    if os.path.abspath(path) == os.path.abspath(session.get("demo_live_path") or ""):
        raise RuntimeError("Refusing to reset: demo path equals live risk DB.")
    if os.path.exists(path):
        os.remove(path)
    for key in ("kri_seed_version", "incident_seed_version",
                "resilience_seed_version", "exec_report_seed_version"):
        pass  # file gone — versions recreate on seed
    ensure_seeded(force=True)


def ensure_seeded(*, force: bool = False, index_conn=None) -> dict:
    """Populate the demo risk DB from synthetic modules. No paid APIs."""
    os.makedirs(os.path.dirname(DEMO_DB_PATH), exist_ok=True)
    from . import demo_data, exec_report, incident_mgmt, kri_appetite, resilience
    with risk.session(DEMO_DB_PATH) as conn:
        # demo_data.seed is idempotent via meta; force wipe is delete-file (reset).
        demo_data.seed(conn, index_conn)
        kri_appetite.seed(conn, force=force)
        incident_mgmt.seed(conn, index_conn, force=force)
        resilience.seed(conn, index_conn, force=force)
        exec_report.seed(conn, index_conn, force=force)
        return {"path": DEMO_DB_PATH, "synthetic": risk.is_synthetic(conn)}


def start_tour(session: dict) -> None:
    enable(session)
    session["demo_tour_active"] = True
    session["demo_tour_step"] = 1


def exit_tour(session: dict) -> None:
    session["demo_tour_active"] = False
    session["demo_tour_step"] = None


def current_step(session: dict) -> dict | None:
    if not session.get("demo_tour_active"):
        return None
    n = int(session.get("demo_tour_step") or 1)
    for s in TOUR_STEPS:
        if s["step"] == n:
            return s
    return TOUR_STEPS[-1]


def next_step(session: dict) -> dict | None:
    n = int(session.get("demo_tour_step") or 1)
    if n >= len(TOUR_STEPS):
        exit_tour(session)
        return None
    session["demo_tour_step"] = n + 1
    return current_step(session)


def prev_step(session: dict) -> dict | None:
    n = int(session.get("demo_tour_step") or 1)
    session["demo_tour_step"] = max(1, n - 1)
    return current_step(session)
