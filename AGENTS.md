# Notes for AI coding assistants

- **Design:** follow `DESIGN.md`. The old Sefaria-inspired library design is
  retired; do not reintroduce it.
- **Core feature:** Risk Compare (`orm/` package + `orm_compare.py`). Country →
  risk category → clause → equivalent clauses in other countries.
- **Controls layer:** obligations (`orm/obligations.py`), control library
  (`orm/controls.py`), reviews and audit log (`orm/state.py`), coverage and
  audit pack (`orm/audit.py`); screens in `controls_views.py`.
- **Risk + RCSA + KRI + Incidents + Resilience + Executive report + Regulatory
  Intelligence:** `orm/risk.py`, `orm/rcsa.py`, `orm/kri_appetite.py`,
  `orm/incident_mgmt.py`, `orm/resilience.py`, `orm/exec_report.py`,
  `orm/demo_data.py`, `orm/risk_report.py`, `orm/regulatory_intel.py`; screens
  in `risk_views.py`, `rcsa_views.py`, `kri_views.py`, `incident_views.py`,
  `resilience_views.py`, `exec_report_views.py` and `regulatory_views.py`.
  Synthetic demo data only; residual risk is explicit; KRI values come from
  observations (not hard-coded in UI); incident facts / estimates / hypotheses
  are labelled; resilience scenarios use deterministic assumptions; executive
  narratives separate FACTS / ANALYSIS / RECOMMENDATIONS and never invent
  movement reasons or compliance conclusions; never invent citations, approved
  impact tolerances, or auto-decide regulatory notifications.
- **Logic vs UI:** data, tagging and matching live in `orm/`; UI files only
  render what `orm.queries` / `orm.regulatory_intel` returns.
- **Index:** build with `python orm_pipeline.py build --fetch`; check with
  `python orm_pipeline.py status`.
- **Tests:** `python -m pytest tests` must pass before committing.
- **Owner experience level:** the project owner is new to coding. When you
  finish a task, explain what changed and what to do next in plain,
  step-by-step language.
