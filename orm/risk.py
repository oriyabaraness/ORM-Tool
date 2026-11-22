"""Operational risk register: risks, controls and tests, KRIs, incidents,
remediation actions and business services, each traceable to the regulation.

    regulation (orm.db) -> obligation (okey) -> risk -> control -> KRI
                        -> incident -> action -> management report

Kept in its own SQLite file, orm_risk.db (or the path in ORM_RISK_DB), apart
from the rebuildable index (orm.db) and from people's reviews (orm_state.db).
The demo data in it is synthetic (orm/demo_data.py): resetting it can never
touch real reviews.

A risk links to an obligation by its stable okey, with a snapshot of the
citation and a hash of the sentence. When a regulator changes that sentence,
the okey disappears from the index and the link shows as "source changed",
never as a link to different text.

Every write goes through `insert` / `update`, which append the old and new
state to risk_audit_log. Nothing is hard-deleted: `retire` sets status.

The scoring here is an illustrative 5x5 method for demonstration, not any
bank's approved framework. No Streamlit here, so everything is unit-testable.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager

import pandas as pd

from . import audit, controls as control_lib, taxonomy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_COMMON = """
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL,
    updated_by        TEXT NOT NULL DEFAULT '',
    provenance        TEXT NOT NULL DEFAULT 'user',      -- synthetic|user|regulation|ai_suggestion
    validation_status TEXT NOT NULL DEFAULT 'draft',     -- draft|suggested|validated|rejected
    is_synthetic      INTEGER NOT NULL DEFAULT 0"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS business_service (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, owner TEXT,
    criticality TEXT NOT NULL DEFAULT 'important',      -- critical|important|standard
    impact_tolerance_hours REAL, rto_hours REAL, rpo_hours REAL,
    dependencies TEXT,                                  -- JSON list
    last_test_date TEXT, last_test_result TEXT,
    status TEXT NOT NULL DEFAULT 'active',{_COMMON});

CREATE TABLE IF NOT EXISTS risk (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, cause TEXT, effect TEXT,
    category_id TEXT NOT NULL, event_type TEXT, service_id TEXT REFERENCES business_service(id),
    owner TEXT, status TEXT NOT NULL DEFAULT 'open',    -- open|retired
    inherent_likelihood INTEGER NOT NULL, inherent_impact INTEGER NOT NULL,
    override_likelihood INTEGER, override_impact INTEGER, override_rationale TEXT,
    assessed_at TEXT, next_review_at TEXT,{_COMMON});

CREATE TABLE IF NOT EXISTS risk_obligation (
    risk_id TEXT NOT NULL REFERENCES risk(id), okey TEXT NOT NULL,
    document_id TEXT NOT NULL, clause_ref TEXT, citation TEXT, link TEXT,
    sentence TEXT NOT NULL, sentence_sha TEXT NOT NULL, rationale TEXT,{_COMMON},
    PRIMARY KEY (risk_id, okey));

CREATE TABLE IF NOT EXISTS control (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    library_id TEXT, bank_control_ref TEXT,
    type TEXT, nature TEXT, frequency TEXT,             -- preventive|detective|corrective, manual|automated
    key_control INTEGER NOT NULL DEFAULT 1, owner TEXT,
    status TEXT NOT NULL DEFAULT 'active',{_COMMON});

CREATE TABLE IF NOT EXISTS risk_control (
    risk_id TEXT NOT NULL REFERENCES risk(id), control_id TEXT NOT NULL REFERENCES control(id),
    reduces TEXT NOT NULL DEFAULT 'likelihood',         -- likelihood|impact|both
    PRIMARY KEY (risk_id, control_id));

CREATE TABLE IF NOT EXISTS control_test (
    id TEXT PRIMARY KEY, control_id TEXT NOT NULL REFERENCES control(id),
    tested_at TEXT NOT NULL, tester TEXT,
    design_rating TEXT NOT NULL, operating_rating TEXT NOT NULL,
    evidence_ref TEXT, findings TEXT,{_COMMON});

CREATE TABLE IF NOT EXISTS appetite (
    category_id TEXT PRIMARY KEY, statement TEXT, max_residual_score INTEGER NOT NULL,
    approved_by TEXT, approved_at TEXT,{_COMMON});

CREATE TABLE IF NOT EXISTS kri (
    id TEXT PRIMARY KEY, risk_id TEXT NOT NULL REFERENCES risk(id), name TEXT NOT NULL,
    definition TEXT, unit TEXT, direction TEXT NOT NULL,  -- higher_is_worse|lower_is_worse
    green_limit REAL NOT NULL, amber_limit REAL NOT NULL,
    frequency TEXT, data_source TEXT, owner TEXT,
    status TEXT NOT NULL DEFAULT 'active',{_COMMON});

CREATE TABLE IF NOT EXISTS kri_reading (
    kri_id TEXT NOT NULL REFERENCES kri(id), period TEXT NOT NULL, value REAL NOT NULL,
    note TEXT, entered_by TEXT, entered_at TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kri_id, period));

CREATE TABLE IF NOT EXISTS incident (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, event_type TEXT,
    service_id TEXT REFERENCES business_service(id), severity TEXT,
    occurred_at TEXT, detected_at TEXT, escalated_at TEXT, resolved_at TEXT,
    regulator_notified_at TEXT, customers_affected INTEGER,
    gross_loss REAL, recovered REAL, currency TEXT, root_cause TEXT,
    status TEXT NOT NULL DEFAULT 'open', owner TEXT,{_COMMON});

CREATE TABLE IF NOT EXISTS incident_link (
    incident_id TEXT NOT NULL REFERENCES incident(id),
    kind TEXT NOT NULL,                                 -- risk|failed_control|notification_obligation
    target_id TEXT NOT NULL,
    PRIMARY KEY (incident_id, kind, target_id));

CREATE TABLE IF NOT EXISTS action (
    id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
    title TEXT NOT NULL, owner TEXT, due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',                -- open|in_progress|done
    closed_at TEXT, closure_evidence TEXT,{_COMMON});

CREATE TABLE IF NOT EXISTS risk_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT,
    action TEXT NOT NULL, table_name TEXT NOT NULL, object_id TEXT NOT NULL,
    before_json TEXT, after_json TEXT);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS ix_rlog_obj ON risk_audit_log(table_name, object_id);
"""

TABLES = ("business_service", "risk", "risk_obligation", "control", "risk_control",
          "control_test", "appetite", "kri", "kri_reading", "incident",
          "incident_link", "action")
KEYS = {"risk_obligation": ("risk_id", "okey"), "risk_control": ("risk_id", "control_id"),
        "kri_reading": ("kri_id", "period"), "appetite": ("category_id",),
        "incident_link": ("incident_id", "kind", "target_id")}
_TIMESTAMPED = {"business_service", "risk", "risk_obligation", "control", "control_test",
                "appetite", "kri", "incident", "action"}

EVENT_TYPES = (
    "Internal fraud", "External fraud", "Employment practices and workplace safety",
    "Clients, products and business practices", "Damage to physical assets",
    "Business disruption and system failures",
    "Execution, delivery and process management",
)
RATINGS = ("effective", "partially_effective", "ineffective", "not_tested")
RATING_LABEL = {"effective": "Effective", "partially_effective": "Partially effective",
                "ineffective": "Ineffective", "not_tested": "Not tested"}
METHOD_NOTE = ("Illustrative 5×5 method for demonstration, not a bank's approved "
               "framework. Score = likelihood × impact (1 to 25). Residual = inherent "
               "lowered by the weakest key control on each side: effective by 2 "
               "levels, partially effective by 1, ineffective or not tested by 0.")


def default_path() -> str:
    return os.environ.get("ORM_RISK_DB", os.path.join(HERE, "orm_risk.db"))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@contextmanager
def session(path: str | None = None):
    path = path or default_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_meta(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# --- writes, each with an audit entry ---------------------------------------------

def _columns(conn, table: str) -> set[str]:
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}")
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _key(table: str, row: dict) -> tuple[tuple[str, ...], str]:
    cols = KEYS.get(table, ("id",))
    return cols, "|".join(str(row[c]) for c in cols)


def _get(conn, table: str, cols, values) -> dict | None:
    where = " AND ".join(f"{c}=?" for c in cols)
    row = conn.execute(f"SELECT * FROM {table} WHERE {where}", values).fetchone()
    return dict(row) if row else None


def _log(conn, actor: str, action: str, table: str, object_id: str,
         before: dict | None, after: dict | None) -> None:
    conn.execute(
        "INSERT INTO risk_audit_log(ts, actor, action, table_name, object_id, "
        "before_json, after_json) VALUES (?,?,?,?,?,?,?)",
        (now(), actor or "", action, table, object_id,
         json.dumps(before, ensure_ascii=False) if before else None,
         json.dumps(after, ensure_ascii=False) if after else None))


def insert(conn, table: str, row: dict, *, actor: str) -> dict:
    """Add one row (or leave an identical existing row alone)."""
    allowed = _columns(conn, table)
    row = {k: v for k, v in row.items() if k in allowed}
    if table in _TIMESTAMPED:
        at = now()
        row = {"created_at": at, "updated_at": at, "created_by": actor or "",
               "updated_by": actor or "", **row}
    cols, oid = _key(table, row)
    if _get(conn, table, cols, [row[c] for c in cols]):
        return _get(conn, table, cols, [row[c] for c in cols])
    names = ", ".join(row)
    conn.execute(f"INSERT INTO {table}({names}) VALUES ({', '.join('?' * len(row))})",
                 list(row.values()))
    _log(conn, actor, "create", table, oid, None, row)
    return row


def update(conn, table: str, key, changes: dict, *, actor: str) -> dict:
    """Change some fields of one row. Unchanged values are not logged."""
    cols = KEYS.get(table, ("id",))
    values = list(key) if isinstance(key, (tuple, list)) else [key]
    before = _get(conn, table, cols, values)
    if before is None:
        raise LookupError(f"{table} {values} not found")
    allowed = _columns(conn, table) - set(cols) - {"created_at", "created_by"}
    changes = {k: v for k, v in changes.items() if k in allowed and before.get(k) != v}
    if not changes:
        return before
    if table in _TIMESTAMPED:
        changes.update(updated_at=now(), updated_by=actor or "")
    sets = ", ".join(f"{k}=?" for k in changes)
    where = " AND ".join(f"{c}=?" for c in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {where}", [*changes.values(), *values])
    after = {**before, **changes}
    _log(conn, actor, "update", table, "|".join(map(str, values)), before, after)
    return after


def retire(conn, table: str, key, *, actor: str) -> dict:
    """Soft delete: the row stays, with status 'retired'."""
    return update(conn, table, key, {"status": "retired"}, actor=actor)


def history(conn, table: str | None = None, object_id: str | None = None,
            limit: int = 200) -> list[dict]:
    where, params = ["1=1"], []
    if table:
        where.append("table_name=?")
        params.append(table)
    if object_id:
        where.append("object_id=?")
        params.append(object_id)
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM risk_audit_log WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
        (*params, limit))]


def set_residual_override(conn, risk_id: str, likelihood: int | None, impact: int | None,
                          rationale: str, *, actor: str) -> dict:
    """An assessor's own residual rating. A reason is required."""
    if (likelihood or impact) and not (rationale or "").strip():
        raise ValueError("An override needs a rationale.")
    for v in (likelihood, impact):
        if v is not None and not 1 <= int(v) <= 5:
            raise ValueError("Ratings run from 1 to 5.")
    return update(conn, "risk", risk_id,
                  {"override_likelihood": likelihood, "override_impact": impact,
                   "override_rationale": (rationale or "").strip() or None}, actor=actor)


# --- scoring -----------------------------------------------------------------------

BANDS = ((4, "Low"), (9, "Medium"), (16, "High"), (25, "Critical"))
_STEP = {"effective": 2, "partially_effective": 1, "ineffective": 0, "not_tested": 0}
_ORDER = {"effective": 3, "partially_effective": 2, "ineffective": 1, "not_tested": 0}


def band(score: int) -> str:
    return next(label for top, label in BANDS if score <= top)


def combined_rating(design: str | None, operating: str | None) -> str:
    """A control is as good as the weaker of its design and its operation."""
    ratings = [r if r in _ORDER else "not_tested" for r in (design, operating)]
    return min(ratings, key=_ORDER.get)


def residual(likelihood: int, impact: int,
             controls: list[tuple[str, str, bool]]) -> tuple[int, int]:
    """(likelihood, impact) after controls. Each control is (rating, reduces,
    key_control). Per dimension, the weakest key control that reduces it sets
    the step; a dimension no key control reduces is not lowered."""
    out = {"likelihood": likelihood, "impact": impact}
    for dim in out:
        ratings = [r for r, reduces, key in controls
                   if key and reduces in (dim, "both")]
        if ratings:
            weakest = min(ratings, key=lambda r: _ORDER.get(r, 0))
            out[dim] = max(1, out[dim] - _STEP.get(weakest, 0))
    return out["likelihood"], out["impact"]


def kri_rag(value: float | None, green: float, amber: float, direction: str) -> str:
    if value is None:
        return "No data"
    if direction == "lower_is_worse":
        return "Green" if value >= green else ("Amber" if value >= amber else "Red")
    return "Green" if value <= green else ("Amber" if value <= amber else "Red")


def sentence_sha(sentence: str) -> str:
    norm = re.sub(r"\W+", " ", (sentence or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _today() -> str:
    return dt.date.today().isoformat()


# --- read models (what the screens render) ------------------------------------------

def _df(conn, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def control_status(conn) -> pd.DataFrame:
    """Each active control with its latest test and combined rating."""
    df = _df(conn, """
        SELECT c.*, t.id AS test_id, t.tested_at, t.tester, t.design_rating,
               t.operating_rating, t.findings, t.evidence_ref
        FROM control c
        LEFT JOIN control_test t ON t.id = (
            SELECT id FROM control_test WHERE control_id = c.id
            ORDER BY tested_at DESC, id DESC LIMIT 1)
        WHERE c.status = 'active' ORDER BY c.id""")
    df["rating"] = [combined_rating(d, o) for d, o in
                    zip(df["design_rating"], df["operating_rating"])] if not df.empty else []
    df["library_name"] = df["library_id"].map(
        lambda c: control_lib.BY_ID[c].name if c in control_lib.BY_ID else "")
    return df


def kri_status(conn) -> pd.DataFrame:
    """Each active KRI with its latest reading and RAG."""
    df = _df(conn, """
        SELECT k.*, r.period, r.value
        FROM kri k
        LEFT JOIN kri_reading r ON r.kri_id = k.id AND r.period = (
            SELECT MAX(period) FROM kri_reading WHERE kri_id = k.id)
        WHERE k.status = 'active' ORDER BY k.id""")
    df["rag"] = [kri_rag(None if pd.isna(v) else float(v), g, a, d) for v, g, a, d in
                 zip(df["value"], df["green_limit"], df["amber_limit"], df["direction"])] \
        if not df.empty else []
    return df


def kri_readings(conn, kri_id: str) -> pd.DataFrame:
    df = _df(conn, "SELECT r.period, r.value, r.note, k.green_limit, k.amber_limit, "
                   "k.direction FROM kri_reading r JOIN kri k ON k.id = r.kri_id "
                   "WHERE r.kri_id = ? ORDER BY r.period", (kri_id,))
    df["rag"] = [kri_rag(v, g, a, d) for v, g, a, d in
                 zip(df["value"], df["green_limit"], df["amber_limit"], df["direction"])] \
        if not df.empty else []
    return df


def actions(conn, today: str | None = None) -> pd.DataFrame:
    today = today or _today()
    df = _df(conn, "SELECT * FROM action WHERE status != 'retired' ORDER BY due_at, id")
    df["overdue"] = [(s != "done") and bool(d) and d < today
                     for s, d in zip(df["status"], df["due_at"])] if not df.empty else []
    return df


def incidents(conn) -> pd.DataFrame:
    df = _df(conn, """
        SELECT i.*, s.name AS service_name, s.impact_tolerance_hours
        FROM incident i LEFT JOIN business_service s ON s.id = i.service_id
        WHERE i.status != 'retired' ORDER BY i.occurred_at DESC""")
    if df.empty:
        return df.assign(net_loss=[], outage_hours=[], tolerance_breached=[],
                         notify_minutes=[])
    df["net_loss"] = df["gross_loss"].fillna(0) - df["recovered"].fillna(0)
    df["outage_hours"] = [_hours(a, b) for a, b in zip(df["occurred_at"], df["resolved_at"])]
    df["tolerance_breached"] = [
        None if pd.isna(h) or pd.isna(t) else bool(h > t)
        for h, t in zip(df["outage_hours"], df["impact_tolerance_hours"])]
    df["notify_minutes"] = [None if (m := _hours(a, b)) is None else round(m * 60)
                            for a, b in zip(df["detected_at"], df["regulator_notified_at"])]
    return df


def _hours(start: str | None, end: str | None) -> float | None:
    if not start or not end or pd.isna(start) or pd.isna(end):
        return None
    a, b = dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end)
    return round((b - a).total_seconds() / 3600, 2)


def _related(acts: pd.DataFrame, risk_id: str, incident_ids: list[str],
             test_ids: list[str]) -> pd.DataFrame:
    """Actions raised on the risk itself, its incidents, or its controls' tests."""
    if acts.empty:
        return acts
    return acts[((acts["source_kind"] == "risk") & (acts["source_id"] == risk_id))
                | ((acts["source_kind"] == "incident") & acts["source_id"].isin(incident_ids))
                | ((acts["source_kind"] == "control_test") & acts["source_id"].isin(test_ids))]


def register(conn, today: str | None = None) -> pd.DataFrame:
    """One row per open risk: inherent, residual, appetite, linked counts."""
    risks = _df(conn, """
        SELECT r.*, s.name AS service_name, a.max_residual_score
        FROM risk r
        LEFT JOIN business_service s ON s.id = r.service_id
        LEFT JOIN appetite a ON a.category_id = r.category_id
        WHERE r.status = 'open' ORDER BY r.id""")
    if risks.empty:
        return risks
    ctl = control_status(conn).set_index("id") if conn.execute(
        "SELECT 1 FROM control LIMIT 1").fetchone() else pd.DataFrame()
    links = _df(conn, "SELECT * FROM risk_control")
    kris = kri_status(conn)
    acts = actions(conn, today)
    inc_links = _df(conn, "SELECT l.target_id AS risk_id, l.incident_id, i.status "
                          "FROM incident_link l JOIN incident i ON i.id = l.incident_id "
                          "WHERE l.kind = 'risk'")
    tests = _df(conn, "SELECT id, control_id FROM control_test")
    obl = _df(conn, "SELECT risk_id, COUNT(*) n FROM risk_obligation "
                    "WHERE validation_status != 'rejected' GROUP BY risk_id")
    obl = dict(zip(obl["risk_id"], obl["n"]))
    rows = []
    for _, r in risks.iterrows():
        mine = links[links["risk_id"] == r["id"]]
        controls = [(ctl.loc[c, "rating"], reduces, bool(ctl.loc[c, "key_control"]))
                    for c, reduces in zip(mine["control_id"], mine["reduces"])
                    if c in ctl.index]
        rl, ri = residual(int(r["inherent_likelihood"]), int(r["inherent_impact"]), controls)
        overridden = not pd.isna(r["override_likelihood"]) or not pd.isna(r["override_impact"])
        if not pd.isna(r["override_likelihood"]):
            rl = int(r["override_likelihood"])
        if not pd.isna(r["override_impact"]):
            ri = int(r["override_impact"])
        my_kris = kris[kris["risk_id"] == r["id"]]
        reds = int((my_kris["rag"] == "Red").sum())
        ambers = int((my_kris["rag"] == "Amber").sum())
        limit = None if pd.isna(r["max_residual_score"]) else int(r["max_residual_score"])
        outside = (limit is not None and rl * ri > limit) or reds > 0
        my_incs = list(inc_links.loc[inc_links["risk_id"] == r["id"], "incident_id"])
        my_tests = list(tests.loc[tests["control_id"].isin(mine["control_id"]), "id"])
        my_acts = _related(acts, r["id"], my_incs, my_tests)
        rows.append({
            "id": r["id"], "title": r["title"], "category_id": r["category_id"],
            "category": taxonomy.BY_ID[r["category_id"]].name
            if r["category_id"] in taxonomy.BY_ID else r["category_id"],
            "event_type": r["event_type"], "service": r["service_name"] or "",
            "owner": r["owner"] or "",
            "inherent_likelihood": int(r["inherent_likelihood"]),
            "inherent_impact": int(r["inherent_impact"]),
            "inherent_score": int(r["inherent_likelihood"]) * int(r["inherent_impact"]),
            "residual_likelihood": rl, "residual_impact": ri, "residual_score": rl * ri,
            "residual_overridden": overridden,
            "appetite_limit": limit,
            "appetite": ("Outside appetite" if outside else
                         "Within appetite" if limit is not None else "No appetite set"),
            "kri_red": reds, "kri_amber": ambers,
            "controls": len(controls),
            "weak_controls": sum(1 for c in controls if c[0] != "effective"),
            "obligations": int(obl.get(r["id"], 0)),
            "open_incidents": int(((inc_links["risk_id"] == r["id"])
                                   & (inc_links["status"] != "closed")).sum())
            if not inc_links.empty else 0,
            "open_actions": int((my_acts["status"] != "done").sum()) if not my_acts.empty else 0,
            "overdue_actions": int(my_acts["overdue"].sum()) if not my_acts.empty else 0,
            "is_synthetic": int(r["is_synthetic"]),
            "validation_status": r["validation_status"],
            "assessed_at": r["assessed_at"] or "", "next_review_at": r["next_review_at"] or "",
        })
    out = pd.DataFrame(rows)
    out["inherent_band"] = out["inherent_score"].map(band)
    out["residual_band"] = out["residual_score"].map(band)
    return out.sort_values(["residual_score", "inherent_score"], ascending=False) \
        .reset_index(drop=True)


def check_obligation_links(conn, index_conn) -> pd.DataFrame:
    """Every risk -> obligation link, with whether the cited sentence is still
    in the index exactly as it was when linked."""
    links = _df(conn, "SELECT * FROM risk_obligation ORDER BY risk_id, document_id, clause_ref")
    if links.empty:
        return links.assign(source_state=[])
    live: dict[str, str] = {}
    if index_conn is not None:
        try:
            keys = list(links["okey"].unique())
            marks = ",".join("?" * len(keys))
            for r in index_conn.execute(
                    f"SELECT okey, sentence FROM obligation WHERE okey IN ({marks})", keys):
                live.setdefault(r["okey"], r["sentence"])
        except sqlite3.OperationalError:
            index_conn = None
    states = []
    for okey_, sha in zip(links["okey"], links["sentence_sha"]):
        if index_conn is None:
            states.append("not checked")
        elif okey_ not in live:
            states.append("source changed")
        elif sentence_sha(live[okey_]) != sha:
            states.append("source changed")
        else:
            states.append("current")
    links["source_state"] = states
    return links


def risk_chain(conn, risk_id: str, index_conn=None, today: str | None = None) -> dict:
    """Everything linked to one risk, for the chain view and the report."""
    row = conn.execute("SELECT * FROM risk WHERE id=?", (risk_id,)).fetchone()
    if row is None:
        raise LookupError(risk_id)
    reg = register(conn, today)
    summary = reg[reg["id"] == risk_id].iloc[0].to_dict() if not reg.empty and \
        (reg["id"] == risk_id).any() else {}
    obl = check_obligation_links(conn, index_conn)
    obl = obl[obl["risk_id"] == risk_id] if not obl.empty else obl
    ctl = control_status(conn)
    links = _df(conn, "SELECT control_id, reduces FROM risk_control WHERE risk_id=?",
                (risk_id,))
    ctl = links.merge(ctl, left_on="control_id", right_on="id", how="inner") \
        if not ctl.empty else ctl
    kris = kri_status(conn)
    kris = kris[kris["risk_id"] == risk_id] if not kris.empty else kris
    inc_ids = [r[0] for r in conn.execute(
        "SELECT incident_id FROM incident_link WHERE kind='risk' AND target_id=?", (risk_id,))]
    inc = incidents(conn)
    inc = inc[inc["id"].isin(inc_ids)] if not inc.empty else inc
    inc_links = {i: [dict(r) for r in conn.execute(
        "SELECT kind, target_id FROM incident_link WHERE incident_id=?", (i,))]
        for i in inc_ids}
    test_ids = [r[0] for r in conn.execute(
        "SELECT t.id FROM control_test t JOIN risk_control rc ON rc.control_id = t.control_id "
        "WHERE rc.risk_id = ?", (risk_id,))]
    acts = _related(actions(conn, today), risk_id, inc_ids, test_ids)
    service = None
    if row["service_id"]:
        s = conn.execute("SELECT * FROM business_service WHERE id=?",
                         (row["service_id"],)).fetchone()
        service = dict(s) if s else None
    return {"risk": dict(row), "summary": summary, "service": service,
            "obligations": obl, "controls": ctl, "kris": kris,
            "incidents": inc, "incident_links": inc_links, "actions": acts}


def is_synthetic(conn) -> bool:
    return get_meta(conn, "dataset") == "synthetic_demo" or bool(conn.execute(
        "SELECT 1 FROM risk WHERE is_synthetic = 1 LIMIT 1").fetchone())


def obligation_citation(index_conn, okey_: str) -> dict | None:
    """Citation fields for one obligation in the index (None if not there)."""
    row = index_conn.execute("""
        SELECT o.okey, o.document_id, o.sentence, p.ref AS clause_ref, d.regulator,
               d.ref AS doc_ref, d.title AS doc_title,
               COALESCE(NULLIF(d.pdf_url, ''), d.url) AS link
        FROM obligation o JOIN provision p ON p.id = o.provision_id
        JOIN document d ON d.id = o.document_id WHERE o.okey = ? LIMIT 1""",
        (okey_,)).fetchone()
    if row is None:
        return None
    r = dict(row)
    r["citation"] = audit.citation(r)
    return r
