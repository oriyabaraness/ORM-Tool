# Design Guide

> **This replaces the earlier Sefaria-inspired "publication library" direction.**
> Do not reintroduce library shelves, "Browse the Library" headings, book-style
> category grids, or Sefaria references. The product is a **regulatory risk
> comparison workspace**, not a reading library.

## What the product is

A subscription tool for operational-risk, compliance and legal teams at banks
and fintechs. Its core job: **take one regulatory obligation in one country and
show, instantly and with evidence, how every other covered country handles the
same thing.**

Users are expert, busy, and accountable for what they cite. They will judge the
product on three things, in this order:

1. **Trust**: can I see exactly where every statement comes from?
2. **Speed**: can I get from a question to the answer in a few clicks?
3. **Output**: can I put the result in front of my board or regulator?

Everything below serves those three.

## Design principles

1. **Source-first.** Every clause, match, gap and number links to the exact
   paragraph in the official document. Show citations in a consistent format:
   `Bank of Israel · Directive 359A §4.2`. Never show an unsourced claim.
2. **Honest states.** Always distinguish:
   - *Found*: a matching clause exists (show it).
   - *Not found*: we have the text and found nothing (a possible gap).
   - *Not assessed*: we don't have the text yet (not a gap).
   - *Machine-suggested* vs *human-confirmed* matches.
   Never let "no data" look like "no requirement".
3. **The workflow is the navigation.** Country → risk category → clause →
   equivalents. The scope (countries + category) is always visible and always
   changeable from the top bar.
4. **Dense, calm, precise.** Closer to Bloomberg, Linear or a good legal
   research tool than to a marketing site. Small type, tight spacing, strong
   alignment, few colors. Whitespace separates; boxes are rare.
5. **Read the law comfortably.** Regulation text is the one place for a serif
   face and a generous line height. Everything else is UI.
6. **Board-ready exports.** Any comparison or gap view can be exported (PDF,
   Excel, CSV) with citations intact and a clean layout.
7. **No decoration.** No hero banners, illustrations, gradients, glow, emoji
   icons or marketing copy inside the app.

## Information architecture

Navigation follows the **operational risk lifecycle**. The default landing
screen is **Demonstration** (interview product front page mapping ORM job
responsibilities to live modules). **Overview** remains the operational risk
snapshot and is unchanged. The original country → category Home into Compare
remains under **Compare** (approved exception: no library shelves, no hero
marketing).

**Demo Mode — Synthetic Data** (sidebar toggle) points `ORM_RISK_DB` at an
isolated demo SQLite file, shows a persistent banner, and supports a five-step
guided interview tour. Reset deletes only the demo file — never live user data.
Demo content is never described as Revolut data.

Primary navigation (left rail, sectioned):

| Section | Items |
|---|---|
| **Demonstration** | Interview front page: 11 ORM responsibilities → live modules; guided payment-disruption walkthrough. |
| **Overview** | Operational risk snapshot, heat map, KRI trends, priority actions, regulatory changes, recent events. |
| **Regulatory Intelligence** | Regulatory Intelligence, Regulatory Change Impact, Obligations, Sources. |
| **Compare** | Home (country × category entry), Compare, Coverage, Gaps, Deadlines, Changes. |
| **Risk Register** | Risk register. |
| **Controls & RCSA** | Controls, RCSA, Audit readiness. |
| **KRI Monitoring** | KRI & Appetite. |
| **Incident Management** | Incidents & Loss. |
| **Operational Resilience** | Operational Resilience. |
| **Management Reporting** | Executive report, Risk report. |

| Item | Purpose |
|---|---|
| **Overview** | Lifecycle dashboard from live application metrics only. Default screen. |
| **Home** | Country dropdown and risk-category cards into Compare (approved exception). |
| **Compare** | The clause-comparison workspace. |
| **Coverage** | Countries × risk categories matrix. |
| **Gaps** | Baseline expectations: found / not found / not assessed. |
| **Deadlines** | Reporting deadlines and review frequencies. |
| **Changes** | New and amended regulations since a date. |
| **Sources** | Document catalog and PDF reader. |
| **Obligations** | Duty checklist (who, what, deadline, evidence, source). |
| **Controls** | Control library with per-country obligation coverage. |
| **Audit readiness** | Upload controls, coverage, audit pack; history. |
| **Risk register** | Operational risk register (inherent/residual). Synthetic when demo. |
| **RCSA** | 5×5 heat map, explicit residual approval, control gaps. |
| **KRI Monitoring** | Indicators, appetite/tolerance, breach escalations. |
| **Incident Management** | Incident lifecycle, loss, RCA, remediation, reporting assessment. |
| **Operational Resilience** | IBS inventory, dependencies, BIA, scenario analysis. |
| **Risk report** | Management risk report export (Excel/PDF). |
| **Executive report** | Period-filtered executive pack with FACTS/ANALYSIS/RECOMMENDATIONS. |
| **Regulatory Intelligence** | Source library, obligation explorer, applicability, map-to-risk. |
| **Regulatory Change Impact** | Compare two document versions; map changed clauses to risks/controls; draft review actions. Textual change ≠ materiality or noncompliance. |
| ~~Market context~~ | Switched off; code kept in `reference_views.py`. |

Global top bar, visible on every screen:
`[Country ▾]  [Compare with: Jordan ✕ + Add]  [Risk category ▾]  [Search clauses…]`

## Key screens

### 1. Compare (the core screen)

Three panes, left to right:

| Pane | Width | Content |
|---|---|---|
| **Clause list** | ~30% | The selected country's clauses in the selected category, grouped by document (document ref + title as group header). Each row: clause ref (`§4.2`), first line of text, match indicator (e.g. `2 equivalents`, or `gap` / `n/a`). Selected row: navy left border + tinted background. |
| **Selected clause** | ~35% | Full clause text (serif), citation line, "Open in source" link, extracted attributes as small tags (⏱ *within 24 hours*, ↻ *annually*), checklist items it satisfies. |
| **Equivalents** | ~35% | One section per comparison country. Ranked matching clauses, each with: strength label (Strong / Partial / Weak) plus a thin bar, citation, clause text, *why it matched* (shared checklist items, shared key terms), "Open in source", and Confirm / Reject controls. If none: the honest-state message (*no comparable clause, possible gap* vs *text not yet available*). |

Behavior: click a clause → the middle and right panes update with no page
jump. Up/down arrow keys move through the clause list (when the framework
allows).

### 2. Coverage

A matrix: rows = risk categories (ORM core first, then prudential), columns =
countries. Each cell: a status mark + the count of clauses + latest update date.
Click a cell → opens Compare scoped to that country + category.

### 3. Gaps

For one category: rows = baseline expectations, columns = countries. Each cell:
status pill (Found / Not found / Not assessed) and, when found, the citation
and a one-line excerpt. Export button top-right.

### 4. Sources (reader)

Original PDF on the left, extracted text on the right, the target clause
highlighted and scrolled into view. Used when someone clicks "Open in source".

## Visual system

### Color

These are the values the app ships with (`ui_theme.py`). If the two ever
disagree, change this table to match `ui_theme.py`.

| Token | Value | Use |
|---|---|---|
| `--ink` | `#0a2540` | Primary text |
| `--ink-2` | `#425466` | Secondary text |
| `--ink-3` | `#6b7c93` | Metadata, captions |
| `--line` | `#e3e8ee` | Dividers, borders |
| `--surface` | `#ffffff` | Panes, cards |
| `--canvas` | `#f6f9fc` | App background |
| `--subtle` | `#f6f9fc` | Hover, selected-row tint, inputs |
| `--primary` | `#635bff` | Primary actions, selection, active nav |
| `--primary-hover` | `#0a2540` | Hover on primary |
| `--focus` | `#635bff` | Keyboard focus ring |
| `--found` | `#1f7a4d` on `#e7f6ee` | Found / strong match / confirmed |
| `--partial` | `#9a6a00` on `#fbf6e8` | Partial match |
| `--gap` | `#b3261e` on `#fdeceb` | Not found / possible gap |
| `--na` | `#6b7c93` on `#f6f9fc` | Not assessed / no text / rejected |
| `--highlight` | `#fff1b8` | Search and keyword highlights in text |

Country accents (thin 3px rules and small dots only, never fills):
Israel `#006d7e`, Jordan `#9b2f4a`, Turkey `#8a6a1f`; add one muted hue per new country.
Never use color as the only signal: every status also has a text label.

Dark mode: plan for it in tokens; not required for the Streamlit stage.

### Typography

| Role | Face | Size / line height | Weight |
|---|---|---|---|
| UI, labels, tables | General Sans (fallback: system-ui) | 13–14px / 1.4 | 400, 500, 600 |
| Screen titles | General Sans | 28px / 1.15 | 500 |
| Pane headers | General Sans | 13px, sentence case, −0.02em tracking | 600 |
| Regulation text | Source Serif 4 (fallback: Georgia) | 15–16px / 1.65 | 400 |
| Citations, refs | General Sans, tabular numbers | 12–13px | 500 |

Use tabular numerals anywhere numbers line up (counts, dates, hours).

### Spacing and shape

- 4px base unit; common steps 4 / 8 / 12 / 16 / 24 / 32.
- Radius: 10px for cards and panes, 8px for buttons and inputs, 999px for pills.
- Borders: 1px `--line`. Shadows: none, except menus and popovers.
- Max content width: none for Compare (it uses the full screen); 1200px for
  text-heavy screens like Gaps exports.

### Components

- **Status pill:** small, rounded, colored text on a tinted background, always
  with a word ("Found", "Not assessed").
- **Match strength:** label + 3px bar whose length reflects the score.
- **Citation line:** `Regulator · Document ref §clause · Title`, with an
  "Open in source ↗" link.
- **Attribute tag:** compact pill for deadlines (⏱) and frequencies (↻).
- **Empty / honest-state notice:** one sentence saying what's missing and the
  action that fixes it. Neutral tint, never an alarming color unless it is a
  genuine gap.
- **Tables:** sticky header, row hover tint, left-aligned text, right-aligned
  numbers, no zebra striping.

## Writing in the interface

- Plain, exact, short. Name things the way compliance teams do ("clause",
  "requirement", "gap", "equivalent").
- Labels describe what the user gets, not the technology ("Equivalent in
  Jordan", not "TF-IDF results").
- Always say when something is a suggestion: "Suggested match: confirm before
  relying on it."
- No marketing language inside the product.

## Implementation notes

- **Today:** Streamlit (`app.py`, `orm_compare.py`). Apply this guide within
  Streamlit's limits: custom CSS through the existing style block, `st.columns`
  for panes, and native widgets for pickers. Don't fight Streamlit with fragile
  hacks; note anything that needs the future stack.
- **Target:** Next.js + Tailwind + shadcn/ui front end over a FastAPI back end
  that reuses the `orm/` package. Define the tokens above as CSS variables /
  Tailwind theme values so they carry over unchanged.
- Data and logic stay in `orm/` (taxonomy, matching, queries). UI files only
  render what `orm.queries` returns.
- Keep the product name out of the code for now: use "the app" or a single
  constant, so renaming later is one change.

## Implementation status (Streamlit stage)

Built: left rail (Home, Compare, Coverage, Gaps, Deadlines, Changes ·
Obligations, Controls, Audit readiness · Sources), shared scope bar remembered
across screens, honest-state notices, status pills, citation lines, serif
regulation text, CSV exports for Coverage, Gaps and Deadlines. Tokens live in
`ui_theme.py`.

Compare today: the scope bar is Country · Compare with · Risk area · "<risk
area> directives" (only directives filed under that risk area). Four panes:
the directive's clauses, the selected clause, equivalents, and an ORM review
column. Suggested matches carry Confirm / Reject (recorded with the
reviewer's name in `orm_state.db` and the audit log); rejected matches drop
out of the review column. The review column shows a saved AI analysis when
one exists ("AI analysis, check before relying on it"), otherwise the
rule-based review.

Not yet (needs the future stack): arrow-key navigation in the clause list,
clicking a Coverage cell to open Compare (today: pick country + category under
the matrix), PDF export of the comparison.

## Don't

- Don't bring back the Sefaria / library / bookshelf look.
- Don't add hero banners, onboarding carousels or marketing blocks to the app.
- Don't show a gap when the honest state is "not assessed".
- Don't show any match or claim without a citation.
- Don't use color alone to carry meaning.
- Don't hide the country and category scope.
