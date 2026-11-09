"""One-command refresh: re-crawl each regulator, rebuild the index, and
report what changed.

    python orm_pipeline.py update

Steps:
  1. run each regulator's crawler script (the same ones you run by hand)
  2. download and read any new PDFs, re-tag and re-match (pipeline.build)
  3. compare the index before and after, and write a short report

Safety: before a crawler runs, its CSV is backed up. If the crawler fails,
or leaves a CSV with far fewer rows than before (a blocked or half-finished
run), the backup is put back so a bad night never shrinks the corpus.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable

from . import db, pipeline

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(HERE, "update_reports")

Log = Callable[[str], None]


@dataclass
class Step:
    name: str
    script: str               # file in the repo root
    output: str | None        # CSV the script (re)writes, protected by backup
    timeout: int = 3 * 3600   # seconds


# Order matters: the BOI directive crawler reads the page list from step 1.
STEPS = [
    Step("Bank of Israel page list", "boi_index.py", "boi_publications_index.csv",
         timeout=900),
    Step("Bank of Israel directives", "boi_proper_conduct_index.py",
         "boi_proper_conduct_directives.csv"),
    Step("Central Bank of Jordan regulations", "jordan_cbj_index.py",
         "jordan_cbj_regulations.csv", timeout=1800),
    Step("Central Bank of Turkey regulations", "turkey_cbrt_index.py",
         "turkey_cbrt_regulations.csv", timeout=900),
]

# A crawl that keeps less than this share of the previous rows is treated as
# blocked/partial and rolled back.
MIN_KEEP = 0.8


@dataclass
class StepResult:
    name: str
    ok: bool
    message: str
    rows_before: int | None = None
    rows_after: int | None = None


@dataclass
class Report:
    started: str
    finished: str = ""
    steps: list[StepResult] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    newly_read: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    # per changed or newly read document: its obligations and the controls
    # they map to, so the owner of each control knows to re-check it
    affected: list[dict] = field(default_factory=list)

    def to_text(self) -> str:
        def docs(rows, extra=""):
            if not rows:
                return ["  (none)"]
            return [f"  - [{r['jurisdiction']}] {(r['ref'] + ' · ') if r['ref'] else ''}"
                    f"{r['title']}{(' — ' + r[extra]) if extra and r.get(extra) else ''}"
                    for r in rows]

        lines = [f"Risk Compare update — {self.started[:16].replace('T', ' ')}", ""]
        lines.append("Sources:")
        for s in self.steps:
            rows = (f" ({s.rows_before} → {s.rows_after} rows)"
                    if s.rows_before is not None and s.rows_after is not None else "")
            lines.append(f"  {'✓' if s.ok else '✗'} {s.name}{rows}: {s.message}")
        lines += ["", f"New documents: {len(self.new)}", *docs(self.new)]
        lines += ["", f"Updated documents: {len(self.changed)}",
                  *docs(self.changed, "why")]
        lines += ["", f"Text read for the first time: {len(self.newly_read)}",
                  *docs(self.newly_read)]
        lines += ["", f"Could not be read: {len(self.failed)}",
                  *docs(self.failed, "error")]
        lines += ["", f"Controls to re-check: {len(self.affected)} document(s)"]
        if not self.affected:
            lines.append("  (none)")
        for a in self.affected:
            ctl = "; ".join(a["controls"]) or "no control mapped yet"
            lines.append(f"  - [{a['jurisdiction']}] {a['label']}: "
                         f"{a['obligations']} obligation(s) → {ctl}")
        return "\n".join(lines) + "\n"


def _count_rows(path: str) -> int | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return max(0, sum(1 for line in f if line.strip()) - 1)  # minus header


def run_step(step: Step, log: Log, root: str = HERE,
             python: str = sys.executable) -> StepResult:
    out = os.path.join(root, step.output) if step.output else None
    backup = out + ".before-update" if out else None
    before = _count_rows(out) if out else None
    if out and os.path.exists(out):
        shutil.copy2(out, backup)

    def restore(reason: str) -> StepResult:
        if backup and os.path.exists(backup):
            shutil.move(backup, out)
            reason += " — kept the previous list"
        return StepResult(step.name, False, reason, before, _count_rows(out) if out else None)

    log(f"update: running {step.script} …")
    try:
        proc = subprocess.run([python, os.path.join(root, step.script)], cwd=root,
                              capture_output=True, text=True, timeout=step.timeout)
    except subprocess.TimeoutExpired:
        return restore(f"stopped after {step.timeout // 60} minutes")
    except OSError as exc:
        return restore(f"could not start: {exc}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["no output"]
        return restore(f"failed: {tail[0][:200]}")

    after = _count_rows(out) if out else None
    if before and (after is None or after < before * MIN_KEEP):
        return restore(f"returned only {after or 0} of {before} rows "
                       "(probably blocked)")
    if backup and os.path.exists(backup):
        os.remove(backup)
    return StepResult(step.name, True, "ok", before, after)


def _snapshot(conn) -> dict[str, dict]:
    db.init(conn)
    return {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, jurisdiction, ref, title, pdf_url, lastmod, published, "
        "text_status, error FROM document")}


def compare(before: dict[str, dict], after: dict[str, dict], report: Report) -> None:
    for doc_id, d in sorted(after.items()):
        old = before.get(doc_id)
        if old is None:
            report.new.append(d)
        else:
            why = [label for key, label in (("lastmod", "page updated"),
                                            ("published", "new publication date"),
                                            ("pdf_url", "new PDF"))
                   if (d[key] or "") != (old[key] or "") and d[key]]
            if why:
                report.changed.append({**d, "why": ", ".join(why)})
            if d["text_status"] == "ok" and old["text_status"] != "ok":
                report.newly_read.append(d)
        if d["text_status"] == "error":
            report.failed.append(d)


def affected_controls(conn, document_ids: list[str],
                      reviews: dict[str, dict] | None = None) -> list[dict]:
    """For each document: how many obligations it carries and which controls
    they map to (a reviewer's choice wins over the suggestion)."""
    from . import controls as control_lib
    from . import obligations, state
    obligations.init(conn)
    if reviews is None:
        with state.session() as s:
            reviews = state.reviews(s)
    out = []
    for doc_id in dict.fromkeys(document_ids):
        doc = conn.execute("SELECT jurisdiction, ref, title FROM document WHERE id=?",
                           (doc_id,)).fetchone()
        if not doc:
            continue
        rows = conn.execute("""
            SELECT o.okey, (SELECT control_id FROM obligation_control oc
                             WHERE oc.obligation_id = o.id
                             ORDER BY score DESC LIMIT 1) AS top
            FROM obligation o WHERE o.document_id = ?""", (doc_id,)).fetchall()
        ids = []
        for r in rows:
            rv = reviews.get(r["okey"])
            if rv and rv["status"] == -1:
                continue
            chosen = rv["control_id"] if rv and rv.get("control_id") else r["top"]
            if chosen:
                ids.append(chosen)
        names = [control_lib.BY_ID[c].name for c in dict.fromkeys(ids)
                 if c in control_lib.BY_ID]
        label = f"{doc['ref'] + ' · ' if doc['ref'] else ''}{doc['title']}"
        out.append({"document_id": doc_id, "jurisdiction": doc["jurisdiction"],
                    "label": label, "obligations": len(rows), "controls": names})
    return out


def update(path: str | None = None, *, steps: list[Step] | None = None,
           root: str = HERE, report_dir: str = REPORT_DIR,
           log: Log = print) -> Report:
    report = Report(started=dt.datetime.now().isoformat(timespec="seconds"))
    with db.session(path) as conn:
        before = _snapshot(conn)

    for step in STEPS if steps is None else steps:
        result = run_step(step, log, root)
        report.steps.append(result)
        log(f"update: {step.name}: {result.message}")

    pipeline.build(path, fetch=True, retry_errors=True, log=log)

    with db.session(path) as conn:
        compare(before, _snapshot(conn), report)
        report.affected = affected_controls(
            conn, [d["id"] for d in report.changed + report.newly_read])
    report.finished = dt.datetime.now().isoformat(timespec="seconds")

    os.makedirs(report_dir, exist_ok=True)
    text = report.to_text()
    stamp = report.started[:16].replace(":", "-").replace("T", "_")
    for name in (f"update_{stamp}.txt", "latest.txt"):
        with open(os.path.join(report_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
    return report
