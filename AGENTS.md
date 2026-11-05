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
- **ORM Analysis Standard (RDL):** vocabulary, authority map, lenses and score
  weights live only in `orm/rdl.py`; grammar in `orm/grammar.py`, verdicts in
  `orm/verdicts.py`, scores in `orm/scores.py`. Any change to a term or weight
  bumps `rdl.VERSION` and adds a `rdl.CHANGELOG` line. Never report a "gap" for
  an area `rdl.authority()` marks as another authority.
