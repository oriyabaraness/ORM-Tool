"""What people decide, kept apart from the rebuildable index.

orm.db is rebuilt from the regulators' documents on every deploy. Human work
-- obligation reviews, control mappings, a bank's own control list -- lives
here instead, in orm_state.db (or the path in ORM_STATE_DB), so a rebuild
never loses it. On Railway, point ORM_STATE_DB at a mounted volume to keep it
across deploys too.

Every change is also written to an append-only audit log with the full new
state, so the store can answer "what did we have in place on 1 March?"
(reviews_as_of).

Tables:
    obligation_review  okey -> status, edited wording, chosen control, reviewer
    bank_control       the bank's own controls, uploaded from Excel/CSV
    audit_log          every change: when, who, what, and the new state
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_path() -> str:
    return os.environ.get("ORM_STATE_DB", os.path.join(HERE, "orm_state.db"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS obligation_review (
    okey         TEXT PRIMARY KEY,
    status       INTEGER NOT NULL DEFAULT 0,   -- 1 approved, -1 rejected, 0 unreviewed
    action_edit  TEXT,                          -- reviewer's wording, if changed
    control_id   TEXT,                          -- chosen control ('' = needs new control)
    note         TEXT,
    reviewer     TEXT,
    reviewed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_control (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref          TEXT,
    name         TEXT NOT NULL,
    description  TEXT,
    owner        TEXT,
    frequency    TEXT,
    category_id  TEXT,
    uploaded_at  TEXT NOT NULL,
    uploaded_by  TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    actor        TEXT,
    action       TEXT NOT NULL,     -- review | controls_uploaded | controls_cleared
    object_id    TEXT,
    detail       TEXT               -- JSON: the new state
);
CREATE INDEX IF NOT EXISTS ix_log_ts ON audit_log(ts);
"""

STATUS_LABEL = {1: "Approved", -1: "Rejected", 0: "Unreviewed"}
STATUS_CODE = {v: k for k, v in STATUS_LABEL.items()}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@contextmanager
def session(path: str | None = None):
    path = path or default_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _log(conn, actor: str, action: str, object_id: str, detail: dict) -> None:
    conn.execute(
        "INSERT INTO audit_log(ts, actor, action, object_id, detail) VALUES (?,?,?,?,?)",
        (detail.get("at") or now(), actor or "", action, object_id,
         json.dumps(detail, ensure_ascii=False)))


# --- obligation reviews ---------------------------------------------------------

def reviews(conn) -> dict[str, dict]:
    return {r["okey"]: dict(r) for r in conn.execute("SELECT * FROM obligation_review")}


def save_review(conn, okey: str, *, status: int, reviewer: str,
                action_edit: str | None = None, control_id: str | None = None,
                note: str | None = None, at: str | None = None) -> None:
    """Record one decision. Unchanged decisions are not logged twice."""
    at = at or now()
    old = conn.execute("SELECT * FROM obligation_review WHERE okey=?", (okey,)).fetchone()
    new = {"status": int(status), "action_edit": action_edit or "",
           "control_id": control_id if control_id is not None else "",
           "note": note or ""}
    if old and all((old[k] or "") == (v or "") if k != "status" else old[k] == v
                   for k, v in new.items()):
        return
    conn.execute(
        "INSERT INTO obligation_review(okey, status, action_edit, control_id, note, "
        "reviewer, reviewed_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(okey) DO UPDATE SET status=excluded.status, "
        "action_edit=excluded.action_edit, control_id=excluded.control_id, "
        "note=excluded.note, reviewer=excluded.reviewer, reviewed_at=excluded.reviewed_at",
        (okey, new["status"], new["action_edit"], new["control_id"], new["note"],
         reviewer or "", at))
    _log(conn, reviewer, "review", okey, {**new, "reviewer": reviewer or "", "at": at})


def reviews_as_of(conn, when: str) -> dict[str, dict]:
    """Replay the audit log up to `when` (ISO date or datetime, inclusive)."""
    if len(when) == 10:            # a date: include the whole day
        when = when + "T23:59:59+99:99"
    state: dict[str, dict] = {}
    for r in conn.execute("SELECT ts, object_id, detail FROM audit_log "
                          "WHERE action='review' AND ts <= ? ORDER BY id", (when,)):
        d = json.loads(r["detail"])
        state[r["object_id"]] = {"okey": r["object_id"], "status": d["status"],
                                 "action_edit": d.get("action_edit", ""),
                                 "control_id": d.get("control_id", ""),
                                 "note": d.get("note", ""),
                                 "reviewer": d.get("reviewer", ""),
                                 "reviewed_at": r["ts"]}
    return state


# --- the bank's own controls -----------------------------------------------------

_COLUMNS = {
    "ref": ("ref", "id", "control id", "control ref", "reference", "control number"),
    "name": ("name", "control", "control name", "title"),
    "description": ("description", "control description", "details", "activity"),
    "owner": ("owner", "control owner", "responsible", "accountable"),
    "frequency": ("frequency", "how often", "periodicity", "cadence"),
    "category": ("category", "risk category", "area", "risk area", "domain"),
}


def normalize_controls(df) -> tuple[list[dict], list[str]]:
    """Map a bank's spreadsheet onto our fields. Returns (rows, problems)."""
    from . import taxonomy
    cols = {str(c).strip().lower(): c for c in df.columns}
    pick = {}
    for field, names in _COLUMNS.items():
        for n in names:
            if n in cols:
                pick[field] = cols[n]
                break
    problems = []
    if "name" not in pick and "description" not in pick:
        return [], ["The file needs a column called 'name' or 'description'."]
    by_name = {c.name.lower(): c.id for c in taxonomy.CATEGORIES}
    by_name.update({c.id: c.id for c in taxonomy.CATEGORIES})
    rows = []
    for i, r in df.iterrows():
        def get(f):
            v = r[pick[f]] if f in pick else ""
            return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()
        name = get("name") or get("description")[:80]
        if not name:
            continue
        cat_raw = get("category").lower()
        cat = by_name.get(cat_raw) or next(
            (cid for nm, cid in by_name.items() if cat_raw and cat_raw in nm), "")
        if cat_raw and not cat:
            problems.append(f"Row {i + 2}: category '{get('category')}' not recognised; "
                            "it will be matched against every category.")
        rows.append({"ref": get("ref"), "name": name, "description": get("description"),
                     "owner": get("owner"), "frequency": get("frequency"),
                     "category_id": cat})
    if not rows:
        problems.append("No controls found in the file.")
    return rows, problems


def replace_bank_controls(conn, rows: list[dict], uploaded_by: str) -> int:
    at = now()
    conn.execute("DELETE FROM bank_control")
    for r in rows:
        conn.execute(
            "INSERT INTO bank_control(ref, name, description, owner, frequency, "
            "category_id, uploaded_at, uploaded_by) VALUES (?,?,?,?,?,?,?,?)",
            (r.get("ref", ""), r["name"], r.get("description", ""), r.get("owner", ""),
             r.get("frequency", ""), r.get("category_id", ""), at, uploaded_by or ""))
    _log(conn, uploaded_by, "controls_uploaded", "bank_control",
         {"count": len(rows), "at": at})
    return len(rows)


def bank_controls(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM bank_control ORDER BY id")]


def log_entries(conn, limit: int = 500) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT ts, actor, action, object_id, detail FROM audit_log "
        "ORDER BY id DESC LIMIT ?", (limit,))]
