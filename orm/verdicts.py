"""Layer 4 of the ORM Analysis Standard: directional verdicts.

The matcher (orm.match) says how *similar* two clauses are. A specialist needs
to know which side asks for *more*, read from a home country toward a target
country:

    Equivalent · Stricter · Looser · Different mechanism · Gap · Not assessed

Two obligation records line up when their Action (by family), Object and
Trigger agree (an empty part counts as agreeing). Then the first part that
differs decides, in the standard's order: Force, Proportionality, Measure,
Frequency, Evidence.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import rdl

FAMILY_PRIORITY = (rdl.STRICTER, rdl.LOOSER, rdl.EQUIVALENT)


@dataclass
class Verdict:
    verdict: str
    decided_by: str | None
    reason: str


def _aligned(a: dict, b: dict) -> bool:
    fa, fb = rdl.action_family(a["action"]), rdl.action_family(b["action"])
    if not fa or fa != fb:
        return False
    if a["object"] and b["object"] and a["object"] != b["object"]:
        return False
    ta, tb = a["trigger"], b["trigger"]
    return ta == tb or "Always" in (ta, tb)


def _breadth(rec: dict) -> int:
    return 2 if rec["proportionality"] == "All institutions" else 1


def _side(home_stricter: bool) -> str:
    return rdl.LOOSER if home_stricter else rdl.STRICTER


def compare_records(home: dict, target: dict, home_name: str = "home",
                    target_name: str = "target") -> Verdict:
    """Verdict for one aligned pair of records, home toward target."""
    def said(rec, value):
        return f"{value} ({home_name if rec is home else target_name})"

    # 1 Force
    wh, wt = rdl.FORCE_WEIGHT[home["force"]], rdl.FORCE_WEIGHT[target["force"]]
    if wh != wt:
        return Verdict(_side(wh > wt), "force",
                       f"Force: {said(home, home['force'])} vs {said(target, target['force'])}")
    # 2 Proportionality
    bh, bt = _breadth(home), _breadth(target)
    if bh != bt:
        return Verdict(_side(bh > bt), "proportionality",
                       f"Applies to: {said(home, home['proportionality'])} vs "
                       f"{said(target, target['proportionality'])}")
    # 3 Measure (a quantified duty is stricter than an open one)
    hh, ht = home["measure_hours"], target["measure_hours"]
    if hh is not None and ht is not None:
        if abs(hh - ht) > rdl.MEASURE_TOLERANCE * max(hh, ht):
            return Verdict(_side(hh < ht), "measure",
                           f"Deadline: {said(home, home['measure'])} vs "
                           f"{said(target, target['measure'])}")
    elif (hh is None) != (ht is None):
        has = home if hh is not None else target
        return Verdict(_side(has is home), "measure",
                       f"Deadline: only {said(has, has['measure'])} sets one")
    # 4 Frequency (shorter interval is stricter)
    fh, ft = home["frequency_months"], target["frequency_months"]
    if fh is not None and ft is not None and fh != ft:
        return Verdict(_side(fh < ft), "frequency",
                       f"Frequency: {said(home, home['frequency'])} vs "
                       f"{said(target, target['frequency'])}")
    if (fh is None) != (ft is None):
        has = home if fh is not None else target
        return Verdict(_side(has is home), "frequency",
                       f"Frequency: only {said(has, has['frequency'])} sets one")
    # 5 Evidence
    if bool(home["evidence"]) != bool(target["evidence"]):
        has = home if home["evidence"] else target
        return Verdict(_side(has is home), "evidence",
                       f"Evidence: only {said(has, has['evidence'])} demands proof")
    return Verdict(rdl.EQUIVALENT, None,
                   f"Same duty: {rdl.action_family(home['action'])} "
                   f"{home['object'] or ''}".strip())


def _duty(rec: dict) -> str:
    who = "" if rec["addressee"] == "Institution" else f"{rec['addressee']} "
    on = rec["target"] or rec["object"]
    return f"{who}{rec['action']}{(' ' + on) if on else ''}"


def pair_verdict(home_records: list[dict], target_records: list[dict],
                 home_name: str = "home", target_name: str = "target") -> Verdict:
    """Verdict for two matched clauses (each a list of obligation records)."""
    if not home_records or not target_records:
        return Verdict(rdl.NOT_ASSESSED, None,
                       "One of the clauses has no obligation wording to code")
    pairs = [(h, t) for h in home_records for t in target_records if _aligned(h, t)]
    results = [compare_records(h, t, home_name, target_name) for h, t in pairs]
    if results:
        # A duty one side has and the other lacks also decides the direction.
        paired_h = {id(h) for h, _t in pairs}
        paired_t = {id(t) for _h, t in pairs}
        for rec in target_records:
            if rec["action"] and id(rec) not in paired_t:
                results.append(Verdict(rdl.STRICTER, "action",
                                       f"Only {target_name} requires: {_duty(rec)}"))
        for rec in home_records:
            if rec["action"] and id(rec) not in paired_h:
                results.append(Verdict(rdl.LOOSER, "action",
                                       f"Only {home_name} requires: {_duty(rec)}"))
    if not results:
        acts_h = sorted({r["action"] for r in home_records if r["action"]})
        acts_t = sorted({r["action"] for r in target_records if r["action"]})
        return Verdict(rdl.DIFFERENT, "action",
                       f"Same risk area, different action: "
                       f"{', '.join(acts_h) or '—'} ({home_name}) vs "
                       f"{', '.join(acts_t) or '—'} ({target_name})")
    for wanted in FAMILY_PRIORITY:
        hits = [r for r in results if r.verdict == wanted]
        if hits:
            return Verdict(wanted, hits[0].decided_by,
                           "; ".join(dict.fromkeys(r.reason for r in hits)))
    return results[0]


def records_by_provision(conn: sqlite3.Connection,
                         provision_ids: list[int] | None = None) -> dict[int, list[dict]]:
    sql = "SELECT * FROM obligation_record"
    if provision_ids is not None:
        if not provision_ids:
            return {}
        sql += f" WHERE provision_id IN ({','.join(str(int(i)) for i in provision_ids)})"
    out: dict[int, list[dict]] = {}
    for r in conn.execute(sql + " ORDER BY provision_id, seq"):
        out.setdefault(r["provision_id"], []).append(dict(r))
    return out


def compute_verdicts(conn: sqlite3.Connection,
                     names: dict[str, str] | None = None) -> int:
    """Rebuild provision_verdict for every matched pair. Returns rows written."""
    conn.execute("DELETE FROM provision_verdict")
    names = names or {}
    jurisdiction = {r[0]: r[1] for r in conn.execute(
        "SELECT p.id, d.jurisdiction FROM provision p "
        "JOIN document d ON d.id = p.document_id")}
    records = records_by_provision(conn)
    rows = conn.execute(
        "SELECT provision_id, match_id, category_id FROM provision_match").fetchall()
    for r in rows:
        home, target = r["provision_id"], r["match_id"]
        v = pair_verdict(records.get(home, []), records.get(target, []),
                         names.get(jurisdiction.get(home), "home"),
                         names.get(jurisdiction.get(target), "target"))
        conn.execute(
            "INSERT OR REPLACE INTO provision_verdict(provision_id, match_id, "
            "category_id, verdict, decided_by, reason) VALUES (?,?,?,?,?,?)",
            (home, target, r["category_id"], v.verdict, v.decided_by, v.reason))
    return len(rows)


def unmatched_verdict(target: str, category_id: str, target_has_text: bool) -> Verdict:
    """Verdict for a home clause with no equivalent in the target country."""
    auth = rdl.authority(target, category_id)
    if auth.scope == rdl.OTHER:
        return Verdict(rdl.NOT_ASSESSED, "authority",
                       f"This area is regulated by {auth.authority}, which is not "
                       "indexed yet")
    if not target_has_text:
        return Verdict(rdl.NOT_ASSESSED, "coverage",
                       "No indexed text in this category yet")
    if auth.scope == rdl.SHARED:
        return Verdict(rdl.NOT_ASSESSED, "authority",
                       f"Shared area ({auth.authority}); index both before calling "
                       "it a gap")
    return Verdict(rdl.GAP, "coverage",
                   "Full text indexed and no matching obligation found")


def review(conn: sqlite3.Connection, provision_id: int, match_id: int,
           category_id: str, status: int, verdict: str) -> None:
    """Record a specialist's confirm (1) or reject (-1) of a verdict."""
    import datetime as dt
    conn.execute(
        "INSERT INTO verdict_review(provision_id, match_id, category_id, status, "
        "verdict, reviewed_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(provision_id, match_id, category_id) DO UPDATE SET "
        "status=excluded.status, verdict=excluded.verdict, "
        "reviewed_at=excluded.reviewed_at",
        (int(provision_id), int(match_id), category_id, int(status), verdict,
         dt.datetime.now().isoformat(timespec="seconds")))
