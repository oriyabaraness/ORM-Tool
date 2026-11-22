"""Management risk report: one view of the risk profile for a risk committee,
plus Excel and PDF exports.

Built only from the risk store (orm.risk) and the regulation index. Every
regulatory statement in it is a citation of an indexed obligation; nothing is
paraphrased into a compliance conclusion. When the store holds synthetic demo
data, the report says so on every page and sheet.
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from . import risk

SYNTHETIC_NOTICE = (
    "SYNTHETIC DEMONSTRATION DATA. The bank, its services, risks, controls, test "
    "results, KRI readings, incidents, losses and actions are invented for a "
    "demo. They are not any real bank's information.")
NOTICE = (
    "Regulatory obligations are quoted from the regulator texts in the index "
    "(English translations; where a directive says so, only the Hebrew version is "
    "binding). A link between a risk and an obligation is a suggestion until a "
    "named person validates it. This report is not a compliance conclusion.")
INCIDENT_WINDOW_DAYS = 90


def build(conn, index_conn=None, today: dt.date | None = None) -> dict:
    """Everything the report shows, as plain frames and numbers."""
    today = today or dt.date.today()
    iso = today.isoformat()
    reg = risk.register(conn, iso)
    kris = risk.kri_status(conn)
    inc = risk.incidents(conn)
    acts = risk.actions(conn, iso)
    ctl = risk.control_status(conn)
    links = risk.check_obligation_links(conn, index_conn)

    since = (today - dt.timedelta(days=INCIDENT_WINDOW_DAYS)).isoformat()
    recent = inc[inc["occurred_at"].fillna("") >= since] if not inc.empty else inc
    breaches = kris[kris["rag"].isin(["Red", "Amber"])] if not kris.empty else kris
    weak = ctl[ctl["rating"] != "effective"] if not ctl.empty else ctl
    open_acts = acts[acts["status"] != "done"] if not acts.empty else acts
    to_check = links[(links["validation_status"] != "validated")
                     | (links["source_state"] != "current")] if not links.empty else links

    heat = pd.DataFrame(0, index=range(5, 0, -1), columns=range(1, 6))
    for _, r in reg.iterrows():
        heat.loc[r["residual_impact"], r["residual_likelihood"]] += 1

    metrics = {
        "open_risks": len(reg),
        "outside_appetite": int((reg["appetite"] == "Outside appetite").sum()) if not reg.empty else 0,
        "kri_red": int((kris["rag"] == "Red").sum()) if not kris.empty else 0,
        "kri_amber": int((kris["rag"] == "Amber").sum()) if not kris.empty else 0,
        "incidents_recent": len(recent),
        "net_loss_recent": float(recent["net_loss"].sum()) if not recent.empty else 0.0,
        "currency": (recent["currency"].dropna().iloc[0]
                     if not recent.empty and recent["currency"].notna().any() else ""),
        "tolerance_breaches": int(recent["tolerance_breached"].fillna(False).astype(bool).sum())
        if not recent.empty else 0,
        "overdue_actions": int(acts["overdue"].sum()) if not acts.empty else 0,
        "weak_controls": len(weak),
        "links_to_check": len(to_check),
    }
    return {"date": iso, "synthetic": risk.is_synthetic(conn),
            "bank": risk.get_meta(conn, "bank"), "metrics": metrics,
            "register": reg, "heat": heat, "kris": breaches, "incidents": recent,
            "actions": open_acts, "controls": weak, "links": to_check}


def headline(rep: dict) -> list[str]:
    """Short factual lines, each derived from a count in the report."""
    m = rep["metrics"]

    def n(count, one, many=None):
        return f"{count} {one if count == 1 else many or one + 's'}"
    lines = [f"{m['outside_appetite']} of {n(m['open_risks'], 'open risk')} "
             f"{'is' if m['outside_appetite'] == 1 else 'are'} outside appetite."]
    if m["kri_red"] or m["kri_amber"]:
        lines.append(f"KRIs at the latest reading: {m['kri_red']} red, {m['kri_amber']} amber.")
    lines.append(f"{n(m['incidents_recent'], 'incident')} in the last {INCIDENT_WINDOW_DAYS} "
                 f"days, net loss {m['net_loss_recent']:,.0f} {m['currency']}".rstrip() + "; "
                 f"{m['tolerance_breaches']} exceeded the service's impact tolerance.")
    lines.append(f"{n(m['weak_controls'], 'key control')} not rated effective; "
                 f"{n(m['overdue_actions'], 'remediation action')} overdue.")
    if m["links_to_check"]:
        lines.append(f"{n(m['links_to_check'], 'risk-to-regulation link')} still "
                     f"{'needs' if m['links_to_check'] == 1 else 'need'} a person to "
                     "validate.")
    return lines


# --- frames for the tables and exports --------------------------------------------

def risk_frame(reg: pd.DataFrame) -> pd.DataFrame:
    if reg.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Risk": reg["id"], "Title": reg["title"], "Category": reg["category"],
        "Owner": reg["owner"],
        "Inherent": reg["inherent_score"].astype(str) + " " + reg["inherent_band"],
        "Residual": reg["residual_score"].astype(str) + " " + reg["residual_band"]
        + reg["residual_overridden"].map({True: " (override)", False: ""}),
        "Appetite": reg["appetite"],
        "KRIs red/amber": reg["kri_red"].astype(str) + "/" + reg["kri_amber"].astype(str),
        "Open actions": reg["open_actions"], "Overdue": reg["overdue_actions"],
    })


def kri_frame(kris: pd.DataFrame) -> pd.DataFrame:
    if kris.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "KRI": kris["id"], "Name": kris["name"], "Risk": kris["risk_id"],
        "Latest": kris["value"].map(lambda v: f"{v:g}") + " " + kris["unit"].fillna(""),
        "Period": kris["period"], "Status": kris["rag"],
        "Limits (green / amber)": kris["green_limit"].map(lambda v: f"{v:g}") + " / "
        + kris["amber_limit"].map(lambda v: f"{v:g}"),
    })


def incident_frame(inc: pd.DataFrame) -> pd.DataFrame:
    if inc.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Incident": inc["id"], "Title": inc["title"], "Severity": inc["severity"],
        "Service": inc["service_name"].fillna(""),
        "Occurred": inc["occurred_at"].fillna("").str.replace("T", " "),
        "Outage (h)": inc["outage_hours"],
        "Tolerance breached": inc["tolerance_breached"].map(
            {True: "Yes", False: "No"}).fillna("n/a"),
        "Net loss": inc["net_loss"].map(lambda v: f"{v:,.0f}") + " "
        + inc["currency"].fillna(""),
        "Status": inc["status"],
    })


def action_frame(acts: pd.DataFrame) -> pd.DataFrame:
    if acts.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Action": acts["id"], "Title": acts["title"], "Owner": acts["owner"],
        "Due": acts["due_at"], "Status": acts["status"].str.replace("_", " "),
        "Overdue": acts["overdue"].map({True: "Overdue", False: ""}),
        "Raised from": acts["source_kind"].str.replace("_", " ") + " " + acts["source_id"],
    })


def control_frame(ctl: pd.DataFrame) -> pd.DataFrame:
    if ctl.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Control": ctl["id"], "Name": ctl["name"], "Owner": ctl["owner"],
        "Tested": ctl["tested_at"].fillna("never"),
        "Design": ctl["design_rating"].map(risk.RATING_LABEL).fillna("Not tested"),
        "Operating": ctl["operating_rating"].map(risk.RATING_LABEL).fillna("Not tested"),
        "Findings": ctl["findings"].fillna(""),
    })


def link_frame(links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Risk": links["risk_id"], "Source": links["citation"],
        "Obligation (quoted)": links["sentence"], "Link status": links["validation_status"],
        "Source text": links["source_state"], "Source link": links["link"],
    })


# --- exports ----------------------------------------------------------------------

def _safe(v):
    """Stop spreadsheet apps from running a cell as a formula."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def excel(rep: dict) -> bytes:
    lines = [f"Management risk report · {rep['bank'] or 'Risk register'}",
             f"Date: {rep['date']}", ""]
    if rep["synthetic"]:
        lines += [SYNTHETIC_NOTICE, ""]
    lines += headline(rep) + ["", NOTICE, "", risk.METHOD_NOTE]
    sheets = [("Read me", pd.DataFrame({"": lines})),
              ("Risks", risk_frame(rep["register"])),
              ("KRI breaches", kri_frame(rep["kris"])),
              ("Incidents", incident_frame(rep["incidents"])),
              ("Open actions", action_frame(rep["actions"])),
              ("Control exceptions", control_frame(rep["controls"])),
              ("Regulation links", link_frame(rep["links"]))]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, frame in sheets:
            frame = frame.map(_safe) if not frame.empty else frame
            frame.to_excel(xw, sheet_name=name, index=False, header=name != "Read me")
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(70, max(10, width + 2))
            if ws.title != "Read me":
                ws.freeze_panes = "A2"
    return buf.getvalue()


def pdf(rep: dict) -> bytes:
    from .simple_pdf import Document
    doc = Document()
    doc.heading("Management risk report")
    doc.text(f"{rep['bank'] or 'Risk register'}   ·   {rep['date']}", size=9)
    if rep["synthetic"]:
        doc.text(SYNTHETIC_NOTICE, size=8, bold=True)
    doc.text(NOTICE, size=8)
    doc.space(6)
    doc.heading("Summary", size=12)
    for line in headline(rep):
        doc.text(line, size=9)
    doc.space(6)
    doc.heading("Risks by residual score", size=12)
    for _, r in rep["register"].iterrows():
        doc.text(f"{r['id']} {r['title']}", size=9, bold=True)
        doc.text(f"Owner: {r['owner']} · Inherent {r['inherent_score']} ({r['inherent_band']})"
                 f" · Residual {r['residual_score']} ({r['residual_band']})"
                 f"{' override' if r['residual_overridden'] else ''} · {r['appetite']}"
                 f" · KRIs red {r['kri_red']}, amber {r['kri_amber']}"
                 f" · open actions {r['open_actions']} ({r['overdue_actions']} overdue)", size=8)
        doc.space(2)
    sections = (("KRI breaches", kri_frame(rep["kris"])),
                ("Incidents", incident_frame(rep["incidents"])),
                ("Open remediation actions", action_frame(rep["actions"])),
                ("Key controls not rated effective", control_frame(rep["controls"])))
    for title, frame in sections:
        doc.space(4)
        doc.heading(title, size=12)
        if frame.empty:
            doc.text("None.", size=9)
        for _, r in frame.iterrows():
            doc.text(" · ".join(f"{k}: {v}" for k, v in r.items() if str(v)), size=8)
            doc.space(2)
    doc.space(4)
    doc.heading("Regulation links to validate", size=12)
    links = rep["links"]
    if links.empty:
        doc.text("None.", size=9)
    for _, r in links.iterrows():
        doc.text(f"{r['risk_id']} · {r['citation']} · {r['validation_status']}, "
                 f"source {r['source_state']}", size=8, bold=True)
        doc.text(f"“{r['sentence']}”", size=8)
        doc.space(2)
    doc.space(4)
    doc.text(risk.METHOD_NOTE, size=7)
    return doc.render()
