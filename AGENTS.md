# Notes for AI coding assistants

- **Design:** follow `DESIGN.md`. The old Sefaria-inspired library design is
  retired; do not reintroduce it.
- **Core feature:** Risk Compare (`orm/` package + `orm_compare.py`). Country →
  risk category → clause → equivalent clauses in other countries.
- **Logic vs UI:** data, tagging and matching live in `orm/`; UI files only
  render what `orm.queries` returns.
- **Index:** build with `python orm_pipeline.py build --fetch`; check with
  `python orm_pipeline.py status`.
- **Tests:** `python -m pytest tests` must pass before committing.
- **Owner experience level:** the project owner is new to coding. When you
  finish a task, explain what changed and what to do next in plain,
  step-by-step language.
