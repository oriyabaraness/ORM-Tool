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

Primary navigation (left rail on desktop, in this order):

| Item | Purpose |
|---|---|
| **Compare** (home) | The clause-comparison workspace. The default screen. |
| **Coverage** | Countries × risk categories matrix: how much each country regulates each area. |
| **Gaps** | Baseline expectations per category: found / not found / not assessed, per country. Exportable. |
| **Deadlines** | Every extracted reporting deadline and review frequency, normalized and comparable. |
| **Changes** | New and amended regulations since a date (future; drives alerts). |
| **Sources** | The document library: catalog, PDF reader, search. Secondary, for when users need the original. |
| **Market context** | Macro indicators (FX reserves, rates, banking-sector indicators). Secondary. |

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

| Token | Value | Use |
|---|---|---|
| `--ink` | `#14171f` | Primary text |
| `--ink-2` | `#4a5160` | Secondary text |
| `--ink-3` | `#7b8292` | Metadata, captions |
| `--line` | `#e3e5ea` | Dividers, borders |
| `--surface` | `#ffffff` | Panes, cards |
| `--canvas` | `#f6f7f9` | App background |
| `--subtle` | `#f0f2f5` | Hover, selected-row tint, inputs |
| `--primary` | `#17345b` | Primary actions, selection, active nav |
| `--primary-hover` | `#102845` | Hover on primary |
| `--focus` | `#3b6fd8` | Keyboard focus ring |
| `--found` | `#2f7a4a` on `#e8f3ec` | Found / strong match / confirmed |
| `--partial` | `#9a6a00` on `#fbf2dc` | Partial match |
| `--gap` | `#b3261e` on `#fbe9e7` | Not found / possible gap |
| `--na` | `#7b8292` on `#f0f2f5` | Not assessed / no text |
| `--highlight` | `#fff1b8` | Search and keyword highlights in text |

Country accents (thin 3px rules and small dots only, never fills):
Israel `#006d7e`, Jordan `#9b2f4a`; add one muted hue per new country.
Never use color as the only signal: every status also has a text label.

Dark mode: plan for it in tokens; not required for the Streamlit stage.

### Typography

| Role | Face | Size / line height | Weight |
|---|---|---|---|
| UI, labels, tables | Inter (fallback: system-ui) | 13–14px / 1.4 | 400, 500, 600 |
| Screen titles | Inter | 20px / 1.3 | 600 |
| Pane headers | Inter | 12px uppercase, +0.04em tracking | 600 |
| Regulation text | Source Serif 4 (fallback: Georgia) | 15–16px / 1.65 | 400 |
| Citations, refs | Inter, tabular numbers | 12–13px | 500 |

Use tabular numerals anywhere numbers line up (counts, dates, hours).

### Spacing and shape

- 4px base unit; common steps 4 / 8 / 12 / 16 / 24 / 32.
- Radius: 6px for panes and inputs, 4px for buttons, 999px for pills.
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

## Don't

- Don't bring back the Sefaria / library / bookshelf look.
- Don't add hero banners, onboarding carousels or marketing blocks to the app.
- Don't show a gap when the honest state is "not assessed".
- Don't show any match or claim without a citation.
- Don't use color alone to carry meaning.
- Don't hide the country and category scope.
