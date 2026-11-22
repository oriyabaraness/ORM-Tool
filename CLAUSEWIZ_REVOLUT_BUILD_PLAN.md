# ClauseWiz → Operational Risk Workflow: Audit and Build Plan

**Status (22 Nov 2026):**
- **Audit:** complete (this document).
- **Production (clausewiz.ai / `main` at plan commit):** regulatory comparison +
  obligations/controls/audit readiness. Plan file is on `main`; the risk
  vertical slice is **not** deployed yet.
- **Local working tree (uncommitted):** interview-ready vertical slice coded
  (`orm/risk.py`, `orm/demo_data.py`, `orm/risk_report.py`, `risk_views.py`,
  `tests/test_risk.py`, `app.py` Risk nav, `.gitignore`). **62 tests pass**
  (`51` existing + `11` risk). Not committed or pushed — waiting for explicit
  go before shipping.

Purpose: show, in an interview for an Operational Risk Manager role, that
ClauseWiz can grow from regulatory comparison into a traceable operational
risk workflow:

```
Regulatory document → Obligation → Operational risk → Control → KRI
                    → Incident → Remediation action → Management report
```

Everything risk-side in the demo is **synthetic** and labelled as such. It
uses no Revolut internal information and makes no claim to.

---

## 1. Existing architecture summary

| Area | What is actually there |
|---|---|
| Language | Python 3.12 (Render pins 3.12.8). ~18k lines including the local risk slice. |
| UI framework | **Streamlit 1.58** multipage app (`st.navigation`). No React, Next.js or FastAPI. `starlette`/`uvicorn` in `requirements.txt` are Streamlit's own dependencies. |
| Entry point | `app.py` wires pages only. It re-imports `orm`, `orm_compare`, `ui_theme`, `controls_views`, `risk_views` on every run so a running server never serves stale code. |
| Routing | `st.Page(..., url_path=...)`: `/` (Home), `/compare`, `/coverage`, `/gaps`, `/deadlines`, `/changes`, `/obligations`, `/controls`, `/audit`, and locally `/risks`, `/risk-report`, `/sources`. Scope (country, category, directive) is kept in `st.session_state` and query params. |
| Screens | `orm_compare.py` (Home, Compare, Coverage, Gaps, Deadlines, Changes), `controls_views.py` (Obligations, Controls, Audit readiness), `risk_views.py` (Risk register, Risk report — local only), `reference_views.py` (Sources; Market context switched off). Styling in `ui_theme.py` plus `.streamlit/config.toml`. |
| Backend / API | **No HTTP API.** The Streamlit server calls the `orm/` package directly. Logic lives in `orm/`; screens only render. |
| Persistence | Two SQLite files in production; three locally once risk is enabled. **`orm.db`**: regulation index, rebuilt on every deploy (`ORM_DB`). **`orm_state.db`**: human work — reviews, match decisions, uploaded bank controls, append-only audit log — never rebuilt (`ORM_STATE_DB`). **`orm_risk.db`** (local / planned): synthetic ORM workflow data (`ORM_RISK_DB`). |
| Batch pipeline | `orm_pipeline.py` CLI → `orm/pipeline.py`: ingest metadata from CSVs (`orm/sources.py`) → download PDFs and extract text (`orm/extract.py`, PyMuPDF) → split into numbered clauses → tag with risk taxonomy → match clauses across countries → extract obligations → suggest controls. `orm/update.py` re-crawls regulators with backup/rollback. |
| Crawlers | Root scripts (`boi_*.py`, `jordan_cbj_*.py`, `turkey_cbrt_index.py`); two use Playwright. Run by hand or by `orm_pipeline.py update`, not at deploy. |
| AI | Optional Anthropic Claude via plain `requests` (`orm/llm.py`, `orm/llm_review.py`). Offline batch only, results cached as JSON in the repo; the app never calls an API at runtime. **No caches exist today** (`orm_texts/llm/` and `orm_texts/llm_reviews/` are absent), so production is 100% rule-based. |
| Deployment | Railway (`railway.json`): build runs `orm_pipeline.py build --fetch` then `status`; start runs Streamlit on `$PORT`. Auto-deploys from `main`. `render.yaml` kept as an alternative. Domain: clausewiz.ai. |
| Tests | `tests/test_orm.py` (51) + local `tests/test_risk.py` (11) = **62 passing**. Uses a small built-index fixture and a fake `streamlit` module to render screens. |

### Index contents today (local `orm.db`)

| Measure | Count |
|---|---|
| Documents | 233 (IL 129 all with text; JO 91, 83 with text, 2 errors, 6 no text; TR 13, none with text) |
| Clauses (`provision`) | 8,407 |
| Clause-level category tags | 6,269 |
| Cross-country clause matches | 29,678 |
| Baseline-expectation hits | 1,811 |
| Obligations (all rule-based) | 6,076 |
| Suggested obligation → control links | 2,892 |
| Human reviews / match decisions / bank controls / log entries (local state) | typically empty unless used |

Bank of Israel directives already indexed that matter for this interview (titles as stored in the index):
310 Risk Management · 350 Operational Risk Management · 355 Business continuity management ·
357 Information Technology Management · 359A Outsourcing · 361 Cyber Defense Management ·
362 Cloud Computing · 363 Supply Chain Cyber Risk Management ·
364 Management of IT, Information Security, and Cyber Protection Risks ·
366 Reporting of Technological Failures and Cyber Incidents · 206 Capital Adequacy — Operational Risk.

These are English translations from the BOI site; some state that only the
Hebrew version is binding. The plan never quotes from memory, only from
indexed text.

---

## 2. Audit by area (the 15 points)

1. **Languages and frameworks.** Python, Streamlit, pandas, SQLite (with FTS5), PyMuPDF, openpyxl, requests, BeautifulSoup, Playwright (crawlers only). There's no JavaScript build: custom HTML/CSS goes through `st.markdown(unsafe_allow_html=True)`, and `boi_pdf_viewer.py` uses an inline HTML component.
2. **Frontend and routing.** Streamlit pages grouped in the sidebar as *Compare* / *Controls* / *Risk* (local) / *Reference*. A shared scope bar (`orm_compare.scope_bar`) is remembered across screens. The design system is in `DESIGN.md` with tokens in `ui_theme.py`. Mobile-tested at 390/768/1280/1500 px for the comparison workspace.
3. **Backend and endpoints.** No REST endpoints. "Backend" = `orm/` modules called in-process: `queries.py` (read models), `audit.py` (obligation table, coverage, audit pack), `state.py` (writes plus audit log), `obligations.py`, `match.py`, `review.py`, and locally `risk.py` / `risk_report.py` / `demo_data.py`.
4. **Database.** `orm.db` tables: `jurisdiction`, `document`, `risk_category`, `document_category`, `provision` (+ `provision_fts`), `provision_category`, `obligation_attr`, `expectation_hit`, `provision_match`, `obligation`, `obligation_control`, `meta`. `orm_state.db` tables: `obligation_review`, `match_review`, `bank_control`, `audit_log`. Cross-file links use **stable content keys** (`okey` = hash of document + sentence; `mkey` = hashes of both clause texts), so human decisions survive rebuilds and are invalidated automatically when the source text changes. Local `orm_risk.db`: see §5.
5. **AI providers.** Anthropic Messages API only, model from `ORM_LLM_MODEL` (default `claude-sonnet-5-5`), key from `ANTHROPIC_API_KEY`. Two prompts: obligation extraction (`orm/llm.py`) and clause-pair review (`orm/llm_review.py`).
6. **PDF / document handling.** PDFs are downloaded at build time, text extracted with PyMuPDF, stored as `orm_texts/<slug>.txt.gz`; the PDF is discarded. Manual PDFs can be dropped into `orm_texts/manual/<id>.pdf`. **No user PDF upload.** The only user upload is the bank control list (CSV/Excel) on Audit readiness. The Sources reader re-fetches a PDF and renders page images.
7. **Regulatory comparison.** Country → risk category → directive → clause → equivalents in other countries. Matching is TF-IDF cosine × 0.7 + shared-expectation Jaccard × 0.3, within the same category, top 5 per clause; Strong ≥ 0.35, Partial ≥ 0.18. Cover/contents/definition clauses are excluded. Suggested matches can be confirmed/rejected and are logged. Coverage matrix, baseline-expectation gaps (found / not found / not assessed), deadlines, and changes are all present.
8. **Prompts and extraction logic.** Rule-based: modal-verb sentence extraction (`shall/must/required` = mandatory, `should/expected` = expected), actor detection, deadline/frequency normalisation, evidence hint by verb. LLM prompts are short, JSON-only, and guarded: **every LLM item must quote a sentence that exists verbatim in the cited clause or it is dropped**; penalties/costs/severity not in the source are stripped (`llm_review._clean`).
9. **Citations.** Every clause carries regulator · document ref · clause ref plus a link to the official PDF/page (`audit.citation`, `orm_compare._cite`). Obligations store the exact source sentence. The audit pack and (locally) the risk report carry citations and a disclaimer. No page numbers (text is stored without page positions).
10. **Authentication / authorisation.** **None.** The site is public; the "reviewer" is a free-text name typed on screen. Anyone with the URL can write reviews and upload controls.
11. **Deployment.** Railway build-then-start. The index is rebuilt on every deploy (network fetch with a 20 s timeout and per-host failure cut-off). `orm_state.db` persists only if `ORM_STATE_DB` points to a mounted Railway volume. The UI itself warns that a redeploy may reset it.
12. **Environment variables.** `ORM_DB`, `ORM_STATE_DB`, `ORM_RISK_DB` (local/planned), `ORM_FETCH_TIMEOUT`, `ORM_LLM_MODEL`, `ANTHROPIC_API_KEY`, `BOI_PDF_TEXT_MANIFEST`, `PORT`. No secrets are committed (keys are only read from the environment).
13. **Error handling and monitoring.** Pipeline records per-document errors in `document.error` and skips failing hosts. `update.py` rolls back bad crawls. UI catches bad uploads and reader fetch failures. **No logging framework, no error tracking, no health checks or alerting** beyond Railway's logs and restart-on-failure.
14. **Dependencies and tests.** Pinned `requirements.txt`, no paid services. Existing tests cover splitting, tagging, connectors, matching, honest states, reviews surviving rebuilds, audit replay "as of" a date, control upload, coverage and audit pack, LLM quote guardrails, and screen rendering. Local risk tests cover scoring, RAG, audit log, soft delete, seed integrity, report labelling, formula-safe Excel, and HTML escaping.
15. **What already supports risk management.**
    - 13-category risk taxonomy with ORM-core flag (governance, op resilience, third party, ICT/cyber, incident reporting, AML, conduct …).
    - Baseline expectations per category (e.g. BCP, RTO/RPO, testing, scenarios, loss data).
    - Obligation extraction with owner (actor), deadline, frequency and evidence.
    - **45-control starter library** (`orm/controls.py` `LIBRARY`), including RCSA, loss data, crisis management, incident notification, RCA, change management and exit plans.
    - Control suggestions, bank control upload and coverage scoring.
    - Append-only audit log with point-in-time replay, plus Excel/PDF audit pack generation (`orm/simple_pdf.py`, openpyxl).
    - `review.py` already classifies text by Basel-style cause themes (People, Processes, Systems, External events, Third parties).
    - **Local (uncommitted):** full synthetic chain Risk → Control → KRI → Incident → Action → Report, with BOI citations resolved from the live index.

---

## 3. Functional gap analysis

Status reflects **production today**, with a note where local uncommitted code already closes the gap.

| # | Capability | Status | Evidence | Smallest change to close |
|---|---|---|---|---|
| A | Regulatory obligation extraction | **Implemented but unreliable** | 6,076 rule-based obligations, 0 human-reviewed, 0 LLM-verified. Actor and scope detection are heuristic. | For the demo, validate linked obligations from BOI 350/355/362/364/366. Optionally run `--llm` on those directives (needs the owner's key) and commit the verified cache. |
| B | Directive comparison across jurisdictions | **Implemented** | Compare screen, matches, confirm/reject, gaps. Limits: Turkey has no text; Jordan 83/91. | None for the slice. |
| C | Regulatory applicability assessment | **Implemented** (Regulatory Intelligence panel D) | `applicability` table in `orm_risk.db`; statuses, entity/perimeter/product, reasoning, reviewer, date; AI suggests questions only. | Polish: surface status on Compare/Sources later if needed. |
| D | Operational risk identification | **Missing in prod** · **Partially implemented locally** | Taxonomy ≠ risk register. Local: 4 seeded synthetic risks with owners, Basel event types, causes/effects. | Commit/push the local Risk register screen. |
| E | Inherent and residual risk scoring | **Missing in prod** · **Implemented locally** | Local 5×5 scoring, weakest-key-control residual, override with mandatory rationale, unit-tested. | Ship `orm/risk.py` scoring + UI. |
| F | Control mapping and effectiveness | **Partially implemented** (prod library/upload) · **local adds design/operating tests** | Prod: 45-control library, suggestions, bank upload, text-similarity coverage. Local: `control`, `risk_control`, `control_test` with ratings. | Ship local control-test layer; keep library IDs so Controls screen still works. |
| G | KRI monitoring and thresholds | **Missing in prod** · **Implemented locally** | Local: 5 KRIs, 30 readings, green/amber/red by direction. | Ship KRI tabs + report breaches. |
| H | Incident tracking | **Shipped** | Full lifecycle (Detected→Closed), RCA, loss events, remediation validation, reporting assessment, `INC-DEMO-CLOUD` walkthrough, Incidents & Loss nav. | Keep demo synthetic; never auto-notify. |
| I | Business impact and resilience | **Missing in prod** · **Partially implemented locally** | Local: 2 business services with criticality, impact tolerance, RTO/RPO, last test; incidents show tolerance breach. No full dependency graph UI. | Ship service records; deepen later if needed. |
| J | Management risk reporting | **Partially implemented** (prod audit pack) · **local risk report** | Prod: Excel/PDF audit pack. Local: heat map, outside appetite, KRI breaches, incidents/losses, overdue actions, weak controls, unvalidated links; Excel/PDF with synthetic watermark. | Ship Risk report page. |

---

## 4. Proposed architecture (smallest maintainable)

**No new services, frameworks or paid dependencies.** Same Streamlit app, same
`orm/` logic layer, same SQLite approach, same deploy.

```
            rebuilt every deploy                 human/demo work, never rebuilt
          ┌──────────────────────┐            ┌────────────────────────────────┐
regulator │ orm.db               │  okey      │ orm_risk.db  (ORM_RISK_DB)     │
PDFs ───► │ document → provision │◄────────── │ risk_obligation (citation snap)│
          │ → obligation (okey)  │            │ risk · control · control_test  │
          └──────────────────────┘            │ kri · kri_reading · incident   │
          ┌──────────────────────┐            │ business_service · action      │
          │ orm_state.db (as is) │            │ appetite · applicability(*)    │
          │ reviews, audit_log   │            │ risk_audit_log · meta          │
          └──────────────────────┘            └────────────────────────────────┘
                     ▲                                       ▲
                     └──────── orm/ (logic, no Streamlit) ───┘
                                orm/risk.py  orm/risk_report.py  orm/demo_data.py
                                         ▲
                                risk_views.py (render only) ── app.py nav group "Risk"
```

(\*) `applicability` is in the plan; not yet in the local schema.

Why a **separate `orm_risk.db`** rather than new tables in `orm_state.db`:

- The demo is synthetic. Keeping it in its own file means "Reset demo data" can recreate that file without any chance of touching real reviews in `orm_state.db` (rule: never delete user data).
- Same SQLite patterns as `orm/state.py` (`session()`, `CREATE TABLE IF NOT EXISTS`, append-only log), so nothing new to learn or operate.
- Pointing `ORM_RISK_DB` at a Railway volume later makes it persistent, exactly like `ORM_STATE_DB`.

Linking to regulation uses the existing stable `okey`. When a regulator
changes a sentence, its `okey` disappears from `orm.db` on the next build. The
risk link is then shown as **"Source text changed: re-validate"** instead of
silently pointing at different text. Local seeder verified: **10/10** obligation
links resolve against the current index (`missing_links = []`).

---

## 5. Proposed data model

### Conventions (every table below)

| Column | Meaning |
|---|---|
| `id` | Stable, human-readable, never reused: `SVC-001`, `RSK-001`, `CTL-001`, `CTT-001`, `KRI-001`, `INC-001`, `ACT-001`. |
| `created_at`, `created_by`, `updated_at`, `updated_by` | UTC ISO-8601 timestamps; free-text actor (no auth yet, see §11). |
| `owner` | Accountable person or role (on business objects). |
| `provenance` | `synthetic` · `user` · `regulation` · `ai_suggestion`. |
| `validation_status` | `draft` · `suggested` · `validated` · `rejected`. AI or rule output starts as `suggested`; only a named person can set `validated`. |
| `is_synthetic` | 1 for every demo row. UI and exports show a "Synthetic demonstration data" label when any row in view is synthetic. |

Every insert/update/delete writes `risk_audit_log(ts, actor, action, table_name, object_id, before_json, after_json)`. That's the same append-only pattern as `state.audit_log`, plus `before` so changes can be diffed. Deletes are soft (`status='retired'`); nothing is hard-deleted from the UI.

### Tables

```sql
-- Important business services (resilience / BIA)
business_service(id PK, name, description, owner, criticality,          -- critical|important|standard
                 impact_tolerance_hours REAL, rto_hours REAL, rpo_hours REAL,
                 dependencies_json,                                     -- systems, third parties
                 last_test_date, last_test_result, ...conventions)

-- Risk register (RCSA unit)
risk(id PK, title, description, cause, effect,
     category_id,                       -- orm.taxonomy id, e.g. op_resilience, ict_cyber
     event_type,                        -- Basel II level-1 event type
     service_id FK business_service,
     owner, status,                     -- open|retired
     inherent_likelihood INT 1-5, inherent_impact INT 1-5,
     residual_likelihood INT 1-5, residual_impact INT 1-5,   -- computed
     residual_override_likelihood, residual_override_impact, override_rationale,
     assessed_at, next_review_at, ...conventions)

risk_obligation(risk_id FK, okey,       -- okey = orm.obligations.okey (stable)
                document_id, clause_ref, citation, sentence_sha,  -- snapshot at link time
                rationale, ...conventions,
                PRIMARY KEY (risk_id, okey))

control(id PK, name, description, library_id,   -- e.g. RES-03 from orm/controls.py
        bank_control_ref, type,                  -- preventive|detective|corrective
        nature,                                  -- manual|automated
        frequency, key_control INT, owner, ...conventions)

risk_control(risk_id FK, control_id FK, reduces,  -- likelihood|impact|both
             PRIMARY KEY (risk_id, control_id))

control_test(id PK, control_id FK, tested_at, tester,
             design_rating,                 -- effective|partially_effective|ineffective
             operating_rating,              -- same, or not_tested
             evidence_ref, findings, ...conventions)

appetite(category_id PK, statement, max_residual_score INT,
         approved_by, approved_at, ...conventions)

kri(id PK, risk_id FK, name, definition, unit, direction,  -- higher_is_worse|lower_is_worse
    green_limit REAL, amber_limit REAL, frequency, data_source, owner, ...conventions)

kri_reading(kri_id FK, period, value REAL, rag,   -- computed on save
            note, entered_by, entered_at, is_synthetic,
            PRIMARY KEY (kri_id, period))

incident(id PK, title, description, event_type, service_id FK, severity,  -- P1..P4
         occurred_at, detected_at, resolved_at, escalated_at, regulator_notified_at,
         customers_affected INT, gross_loss REAL, recovered REAL, currency,
         root_cause, status,                       -- open|contained|closed
         owner, ...conventions)

incident_link(incident_id FK, kind,               -- risk|failed_control|notification_obligation
              target_id,                          -- RSK-…, CTL-…, or okey
              PRIMARY KEY (incident_id, kind, target_id))

action(id PK, source_kind,                        -- incident|control_test|risk|kri
       source_id, title, owner, due_at, status,   -- open|in_progress|done|overdue(derived)
       closed_at, closure_evidence, ...conventions)

applicability(document_id PK, decision,           -- applies|partly|does_not_apply
              entity_type, rationale, reviewer, decided_at, ...conventions)
              -- PLANNED; not yet in local schema

risk_audit_log(id PK, ts, actor, action, table_name, object_id, before_json, after_json)
meta(key PK, value)                               -- dataset=synthetic_demo, seed_version
```

### Scoring rules (illustrative, documented on screen)

- Inherent score = likelihood × impact (1–25). Bands: 1–4 Low, 5–9 Medium, 10–16 High, 20–25 Critical.
- Control effectiveness for a risk = the weakest **key** control, combining design and operating ratings. Not tested counts as ineffective.
- Residual: Effective lowers the mitigated dimension by 2 levels, Partially effective by 1, Ineffective by 0 (floor 1). The assessor may override with a mandatory rationale, which is logged.
- Appetite: residual score above `appetite.max_residual_score` for the category, or any KRI red, means **Outside appetite → escalate**.
- KRI RAG: compare the value with `green_limit` / `amber_limit` according to `direction`.

The screen labels this "Illustrative methodology for demonstration. Not a
bank's approved framework."

---

## 6. Interview-ready vertical slice

One synthetic but realistic story, end to end, every regulatory link cited
from the real index:

**Synthetic Bank "Demo Digital Bank Ltd" (fictional) — Card payments service.**

| Step | Content | Local status |
|---|---|---|
| Service | `SVC-001` Card payments (+ `SVC-002` onboarding). Critical, impact tolerance / RTO / RPO set. | Seeded |
| Risks | `RSK-001`…`RSK-004` (change outage, cloud outage, late notification, unrecoverable data). | Seeded |
| Obligations | Linked by `okey` from BOI 350/355/362/364/366 via phrase search. | **10 links, 0 missing** on current index |
| Controls | Library-backed controls with one partially effective test so residual stays high. | Seeded (7 controls, 7 tests) |
| KRIs | Five KRIs, six months of readings, amber and red present. | Seeded (5 KRIs, 30 readings) |
| Incident | Card authorisation outage + second incident; loss, timestamps, failed control, BOI 366 notification link. | Seeded (2) |
| Actions | RCA follow-ups; overdue derived from dates. | Seeded (5) |
| Report | Heat map, outside appetite, KRI breaches, incidents, overdue actions, weak controls; Excel/PDF. | Implemented locally |

Demo walkthrough (5 minutes): Compare (BOI 366 vs Jordan) → Obligation →
Risk register (`RSK-001` chain) → Management report → audit history.

Still optional for a polished interview demo: "Linked risks" back-links from
Obligations/Compare (step 8), and a fuller README refresh (step 11).
Applicability and the Regulatory Intelligence workspace are in place.

---

## 7. Minimal implementation sequence

Each step is one small, reviewable commit. Tests pass before each push.

| Step | Change | Files | Status |
|---|---|---|---|
| 0 | Safety baseline: confirm existing tests pass; do not touch `orm_state.db`. | none | Done (62 green locally) |
| 1 | Risk data layer: schema, writes with audit log, soft delete, scoring and RAG. | `orm/risk.py`, `tests/test_risk.py` | **Coded locally, uncommitted** |
| 2 | Synthetic seed: idempotent; resolves obligation links from `orm.db`; writes only to `orm_risk.db`. | `orm/demo_data.py`, tests, `.gitignore` | **Coded locally, uncommitted** |
| 3 | Risk register and chain screen + "Risk" nav + synthetic banner. | `risk_views.py`, `app.py` | **Coded locally, uncommitted** |
| 4 | Controls and tests, KRIs with readings, appetite. | same | **Coded locally, uncommitted** |
| 5 | Incidents and remediation actions. | same | **Coded locally, uncommitted** |
| 6 | Resilience: business services, impact tolerance on incidents. | same | **Coded locally, uncommitted** |
| 7 | Management report plus Excel/PDF export. | `orm/risk_report.py`, `risk_views.py`, tests | **Coded locally, uncommitted** |
| 8 | Hooks: "Linked risks" on Obligations and Compare (read-only). | `controls_views.py`, `orm_compare.py` | **Not started** (RI panel E links from obligations) |
| 9 | Applicability decision per directive. | `orm/risk.py`, `orm/regulatory_intel.py`, `regulatory_views.py` | **Done** |
| 9b | Regulatory Intelligence workspace (source library, explorer, comparison, mapping). | `orm/regulatory_intel.py`, `regulatory_views.py`, tests | **Done** |
| 10 (optional) | AI suggestion "risks this obligation may create", offline, quote-verified. | `orm/llm_risk.py` | **Not started** (rule-based suggestions ship in RI panel E) |
| 11 | Docs: DESIGN.md IA, README, AGENTS.md. | docs | **Partial** (DESIGN + AGENTS updated) |

**Recommended next action:** after user "go", commit the local slice (steps 1–7)
as one reviewable commit (or split data layer / UI / report if preferred), run
tests, push to `main`, verify clausewiz.ai. Then steps 8 and 11 before the
interview; 9–10 only if time remains.

---

## 8. Expected modified files

New (present locally, uncommitted):
- `orm/risk.py`: schema, writes with audit log, scoring, read models.
- `orm/demo_data.py`: synthetic seed, citation resolver.
- `orm/risk_report.py`: management report frame plus Excel/PDF.
- `risk_views.py`: Risk register and Report screens (render only).
- `tests/test_risk.py`.

Modified (small, local):
- `app.py`: "Risk" nav group; `risk_views` in fresh-import list.
- `.gitignore`: `orm_risk.db`.

Still expected later:
- `controls_views.py`, `orm_compare.py`: one read-only "Linked risks" line (step 8).
- `ui_theme.py`: only if shared tokens need a tweak (risk screens currently use scoped `.rk-*` CSS in `risk_views.py`).
- `DESIGN.md`, `README.md`, `AGENTS.md`: document the new screens and rules.

Not touched: `orm/db.py` schema, `orm/match.py`, `orm/obligations.py` logic, the pipeline, crawlers, `railway.json`, `render.yaml`, `orm_state.db` contents.

---

## 9. Dependencies

None new. Everything uses packages already pinned: Streamlit, pandas, sqlite3
(stdlib), openpyxl, the in-repo `simple_pdf`. Charts (heat map, KRI trend)
use HTML/CSS or Streamlit's built-in Altair. Optional AI step reuses `requests`
plus the Anthropic API with the owner's own key.

---

## 10. Risks of breaking existing functionality

| Risk | Mitigation |
|---|---|
| New module not in `app.py` fresh-import list, so stale code is served after deploy | `risk_views` already added to `_FRESH` locally; `orm.*` already covered. |
| Global CSS in `ui_theme.py` changes existing screens | Risk styles are scoped `.rk-*` inside `risk_views.py`; no edits to existing selectors required for the slice. |
| Seeder needs `orm.db` built; on Railway the index is built at build time | Seed lazily on first open of a Risk screen (already how `_stores()` works); if the index has no text, seed risks without obligation links and say so. |
| `okey` links go stale when regulators edit text | Show "Source text changed: re-validate"; covered by a test. |
| Duplicate `okey` across categories (already seen once on Obligations) | Join risk links on `okey` only, de-duplicated; Obligations already dedupes in `audit.py`. |
| Fake `streamlit` in tests lacks widgets we use | Risk screen tests already render via the existing fake; extend only if new widgets are added. |
| SQLite write contention (two users editing) | Short transactions as in `state.py`; acceptable for a demo. |
| Demo data mistaken for real data | Banner on every Risk screen, `is_synthetic` on every row, watermark in exports, fictional bank name. |
| Accidental commit of unrelated dirty files | Commit only risk files + `app.py` + `.gitignore`; never `.streamlit 2.pid.icloud`, CSV crawl refreshes, or `.icloud` placeholders. |

---

## 11. Testing strategy

- **Unit (pure functions):** inherent/residual scoring, override needs a rationale, KRI RAG both directions, appetite breach, overdue actions, impact-tolerance breach. *(covered in `test_risk.py`)*
- **Integrity:** every `risk_obligation.okey` exists in `orm.db`; its stored sentence hash matches the live sentence; no seeded citation is free text. *(covered; also `test_real_index_links_every_demo_risk_to_quoted_text`)*
- **Safety:** seeding and "Reset demo" never open `orm_state.db` for writing; no hard deletes; every write produces an audit row with before/after. *(covered)*
- **Labelling:** Risk screens and both exports contain "Synthetic demonstration data"; AI suggestions render as "Suggested", never "Validated".
- **Screens:** render each new page with the existing fake streamlit and the built-index fixture; existing 51 tests unchanged.
- **Manual QA:** browser at 390 / 768 / 1280 px, keyboard focus, honest states; screenshot evidence before pushing.
- Rule: `python -m pytest tests` green before every push to `main`.

---

## 12. Deployment strategy

1. Work in small commits on `main`; Railway auto-deploys each push (current practice).
2. `orm_risk.db` is created and seeded at runtime. It's synthetic, so a reset on redeploy is acceptable, and a "Reset demo data" button recreates it on demand.
3. Real data later: mount a Railway volume and set `ORM_RISK_DB` (and `ORM_STATE_DB`) to paths on it.
4. No build-step changes; `railway.json` and `render.yaml` stay as they are.
5. Rollback: revert the commit; the regulation features don't depend on the new file.
6. **Do not deploy until tests pass and the user says go.**

---

## 13. Security considerations

- **No authentication today.** Any visitor can write reviews, upload controls and (after this work) edit demo risks. For the interview demo this is acceptable because the data is synthetic. Before any real use, add Streamlit's built-in OIDC login (`st.login`, no new dependency) or put the app behind the host's access control, and make the Risk screens read-only for anonymous users.
- **Secrets:** `ANTHROPIC_API_KEY` only from the environment; never committed, logged or shown. The app makes no runtime AI calls.
- **HTML injection:** screens use `unsafe_allow_html`. All user-entered text must pass through `ui_theme.e` (HTML escape), as the existing screens do; risk tests include a `<script>` escape check.
- **Spreadsheet formula injection:** prefix cells starting with `= + - @` in Excel exports.
- **Data minimisation:** no personal data in the demo; owners are role names ("Head of Payments Ops").
- **Integrity:** append-only audit log; soft deletes; citations verified against the index.
- **AI output:** always labelled "Suggestion: verify before relying on it"; never sets `validated`; quotes must match source text verbatim (existing guardrail pattern).

---

## 14. Known limitations

- Obligations are rule-extracted and unreviewed. Good for discovery, not for a compliance conclusion.
- English translations of BOI directives. The binding text is Hebrew where the directive says so.
- Turkey has no extracted text; Jordan is 83/91. Cross-country comparisons for those are partial ("not assessed" where text is missing).
- No page numbers in citations (text is stored without positions); citations go to directive + clause + official link.
- Scoring methodology is illustrative, not a bank's approved framework. KRI values, incidents and losses are synthetic; there are no live data feeds.
- No authentication or roles. "Reviewer" is self-declared.
- SQLite and Streamlit suit a single-team demo, not a multi-entity production platform. `DESIGN.md` already names Next.js + FastAPI over the same `orm/` package as the future stack.
- The demo uses no Revolut internal information and claims none. Any resemblance of the fictional bank to a real firm is unintended.
- Applicability assessment and back-links from Compare/Obligations are still outstanding for the polished interview path.

---

## 15. Decision log for the owner

| Question | Recommendation |
|---|---|
| Rewrite in React/Next? | **No** for the interview. Stay on Streamlit; keep `orm/` as the portable logic layer. |
| New microservice / Postgres? | **No.** Third SQLite file is enough and matches existing ops. |
| Ship risk code now? | **Only after you say go.** Code is ready locally; production still comparison-only. |
| Claim Revolut data? | **Never.** Banner + fictional bank name + synthetic watermark. |
| What to demo first? | Risk register → open `RSK-001` → Regulation tab (real BOI quotes) → Controls/KRIs/Incident → Risk report export. |
