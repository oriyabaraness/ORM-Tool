# Bank of Israel Publications Explorer — Design Reference
> Styling-only reference for a calm, text-first regulatory library inspired by the provided screenshot layout: white paper, soft gray dividers, deep navy actions, compact search, thin colored rules, and a right-hand source/context sidebar.

**Theme:** light

This document defines the visual system for the Bank of Israel Publications Explorer. It should capture the screenshot's structure and atmosphere without carrying over the screenshot's original subject matter. The experience should feel like an official research library for regulatory publications: readable, restrained, source-led, and precise.

The interface is not a SaaS landing page and not a marketing dashboard. It is a searchable publication library for Bank of Israel material, including PDFs, directives, circulars, reports, and extracted text. Use a fixed-feeling top navigation bar, a full-width informational banner, a two-column browse grid, and a right-hand sidebar for context, recent sources, and indexed material. Color should be sparse: deep navy for primary actions, pale blue for system notices, warm gray for dividers, and thin muted category rules to organize publication groups.

## Content Guardrails

This file is for styling and BOI project implementation only.

- Do not use any wording, categories, examples, or content from the visual reference site; keep all examples BOI/regulatory or generic.
- Do not hardcode original-domain copy from the reference screenshot.
- Do use Bank of Israel / regulatory-publication language where component examples need labels.
- Keep the top navigation visible at 100% zoom: **Catalog**, **Directives**, **Reader**, **Search**.
- Keep the current Library segmented control items as **Catalog**, **Reader**, **Regional Map**, and **Risk Compare**.
- Do not add a separate **Proper Conduct of Banking Business Directives** tab; that content belongs inside the Reader/searchable publication experience.
- Treat **Reader** as the single place for searchable PDFs, extracted text, highlighted matches, page navigation, and downloadable source PDFs.
- Treat **Regional Map** as the separate comparison workspace for Israel, Jordan, and future regional central bank corpora.

## Current BOI App Inventory

This design file reflects the current Streamlit application surface as of the Jordan connection pass.

- **Top visual navigation:** Catalog, Directives, Reader, Search.
- **Library tabs:** Catalog, Reader, Regional Map, Risk Compare.
- **Catalog:** searchable/filterable BOI publication metadata, publication type filter, file type filter, year filter, official link column, extraction actions, and CSV download.
- **Reader:** all-PDF full-text search, exact/broad match toggle, publication type filter, matching publication table, reader opener, source PDF download, synchronized PDF and extracted-text/legal-analysis viewer.
- **Regional Map:** Middle East banking map, active BOI corpus, connected Central Bank of Jordan regulation index, pending regional corpora, market status table, Jordan regulation search, official CBJ links, and CSV download.
- **Risk Compare:** Israel vs Jordan coverage matrix by risk category, side-by-side provisions, gap analysis against baseline expectations, and extracted deadlines. Uses the same paper/navy/rule styling; category rules teal (Israel) and rose (Jordan).
- **Proper Conduct directives:** available through Reader/search workflows and catalog metadata; do not restore the older redundant directive-only Library tab.

## Page Structure

### Header Navigation

- **Logo:** Bank of Israel Publications Explorer
- **Top visual labels:** Catalog, Directives, Reader, Search
- **Library segmented control:** Catalog, Reader, Regional Map
- **Current behavior:** keep the existing Streamlit navigation model; this design pass is styling-only unless a later implementation task explicitly asks for new routing or controls.
- **Future optional controls:** a compact global search pill, help/language/status icons, and a navy primary action may be added later, but they are not part of the current page contract.

### Informational Banner

**Analyze Bank of Israel Publications Faster**
Search official publications, preview source PDFs, and surface relevant regulatory language with highlighted source matches.

**Primary button:** Start Search
**Secondary link:** View indexed sources

### Main Library Heading

**Browse Publications**

### Current Library Tabs

#### Catalog
Browse and filter the BOI publication catalog. Keep the table dense, source-led, and readable. Use understated filters and official source links.

#### Reader
Search inside indexed PDFs across the catalog and open a Sefaria-inspired reading experience with PDF pages, search results, synchronized extracted text/legal analysis, source metadata, and downloads.

#### Regional Map
Compare Bank of Israel source coverage with connected regional banking regulators. Jordan is the first connected external corpus through Central Bank of Jordan regulation records; other regional feeds can be added incrementally.

### Suggested BOI Browse Groups

These are example groups for the interface, not mandatory hardcoded categories. The design should support whatever taxonomy the BOI project returns from the data layer.

#### Banking Supervision
Official supervisory publications, regulatory updates, circulars, and guidance issued for banking entities and supervised institutions.

#### Directives
Directive numbers, official source links, PDF previews, and extracted text prepared for reader/search workflows.

#### Operational Resilience
Publications and directive excerpts related to continuity, incident response, technology resilience, outsourcing, and recovery capabilities.

#### Payment Systems
Guidance and publications related to payments, open banking, payment infrastructure, settlement, and API-related material.

#### Financial Stability
Reports and publications covering systemic risk, banking-sector conditions, macroprudential themes, and resilience indicators.

#### Research & Statistics
Research papers, statistical releases, data-oriented publications, and supporting analytical material.

#### Consumer Protection
Publications and guidance related to banking customers, disclosures, complaints, consumer-facing obligations, and fair treatment.

#### Reports & Reviews
Annual reports, periodic reviews, policy summaries, and long-form institutional publications.

#### Notices & Circulars
Short-form updates, circulars, notices, consultation papers, and implementation announcements.

#### Source Archive
Indexed PDFs, metadata records, download links, publication dates, source URLs, and extraction status.

### Right Sidebar Examples

#### About This Explorer
A searchable workspace for Bank of Israel publications. Use it to browse indexed sources, open official PDFs, search inside extracted text, and cite exact publication passages.

**Button:** Getting Started (2 min)

#### Recently Opened
Banking Supervision Directive preview •
Operational resilience search results

All history ›

#### Indexed Sources
Track which publications have metadata, source PDFs, extracted text, and reader-ready search coverage.

PDFs indexed • Text extracted • Matches highlighted • Sources downloadable

## Tokens — Colors

| Name | Value | Token | Role |
|------|-------|-------|------|
| BOI Navy | `#17345b` | `--color-boi-navy` | Primary buttons, logo accent, active nav states, important actions |
| Navy Hover | `#102845` | `--color-navy-hover` | Hover state for primary buttons and active controls |
| Paper White | `#ffffff` | `--color-paper-white` | Header, main content, sidebar, reader surface |
| Page Warm Gray | `#f7f7f5` | `--color-page-warm-gray` | Overall page background outside content columns |
| Search Gray | `#ececea` | `--color-search-gray` | Search input background and quiet input areas |
| Rule Gray | `#ddddda` | `--color-rule-gray` | Horizontal dividers, sidebar separators, header border |
| Text Ink | `#222222` | `--color-text-ink` | Main readable text, publication titles, source labels |
| Text Muted | `#666666` | `--color-text-muted` | Descriptions, metadata, secondary nav, helper text |
| Banner Blue | `#eef5ff` | `--color-banner-blue` | Informational assistant/search banner |
| Banner Border | `#d6e5ff` | `--color-banner-border` | Banner outline |
| Category Teal | `#006d7e` | `--color-category-teal` | Thin category rule for publication group A |
| Category Blue | `#6fa6bd` | `--color-category-blue` | Thin category rule for publication group B |
| Category Gold | `#c0ad5c` | `--color-category-gold` | Thin category rule for publication group C |
| Category Green | `#5f986c` | `--color-category-green` | Thin category rule for publication group D |
| Category Rose | `#9b2f4a` | `--color-category-rose` | Thin category rule for publication group E |
| Category Purple | `#5d3f85` | `--color-category-purple` | Thin category rule for publication group F |
| Category Magenta | `#b84d73` | `--color-category-magenta` | Thin category rule for publication group G |
| Category Lavender | `#8d91b2` | `--color-category-lavender` | Thin category rule for publication group H |
| Category Emerald | `#00947f` | `--color-category-emerald` | Thin category rule for publication group I |
| Category Sage | `#93aa83` | `--color-category-sage` | Thin category rule for publication group J |

## Tokens — Typography

### UI Sans — Navigation, banners, buttons, body descriptions · `--font-ui`
- **Substitute:** system-ui, Inter, Arial, sans-serif
- **Weights:** 400, 500, 600, 700
- **Sizes:** 13px, 14px, 16px, 18px, 24px
- **Line height:** 1.2–1.4
- **Role:** Header navigation, search, buttons, metadata, filters, descriptions, banners, sidebar headings, and reader controls.

### Source Serif — Publication titles and source references · `--font-source-serif`
- **Substitute:** Georgia, Times New Roman, serif
- **Weights:** 400, 600, 700
- **Sizes:** 17px, 20px, 28px
- **Line height:** 1.15–1.3
- **Role:** Browse group titles, publication titles, source references, and recently opened source links. Use this only where the page should feel document-led rather than app-led.

### Type Scale

| Role | Size | Line Height | Weight | Token |
|------|------|-------------|--------|-------|
| utility | 13px | 1.2 | 500 | `--text-utility` |
| body-sm | 14px | 1.35 | 400 | `--text-body-sm` |
| body | 16px | 1.35 | 400 | `--text-body` |
| nav | 16px | 1.2 | 600 | `--text-nav` |
| sidebar-heading | 24px | 1.2 | 700 | `--text-sidebar-heading` |
| section-heading | 24px | 1.2 | 700 | `--text-section-heading` |
| category-title | 28px | 1.15 | 400 | `--text-category-title` |
| source-title | 20px | 1.25 | 400 | `--text-source-title` |

## Tokens — Spacing & Shapes

**Base unit:** 4px
**Density:** spacious but information-rich

### Spacing Scale

| Name | Value | Token |
|------|-------|-------|
| 4 | 4px | `--spacing-4` |
| 8 | 8px | `--spacing-8` |
| 12 | 12px | `--spacing-12` |
| 16 | 16px | `--spacing-16` |
| 20 | 20px | `--spacing-20` |
| 24 | 24px | `--spacing-24` |
| 32 | 32px | `--spacing-32` |
| 40 | 40px | `--spacing-40` |
| 48 | 48px | `--spacing-48` |
| 64 | 64px | `--spacing-64` |
| 80 | 80px | `--spacing-80` |

### Border Radius

| Element | Value |
|---------|-------|
| Search input | 18px |
| Primary buttons | 4px |
| Banner | 8px |
| Icon buttons | 50% |
| Browse items | 0px; use rules and whitespace instead of cards |
| Reader/source panels | 4px to 8px only when a contained panel is necessary |

### Layout

- **Header height:** 72px
- **Announcement height:** approximately 84px
- **Page max-width:** 1280px
- **Main column width:** 760px
- **Sidebar width:** 340px
- **Main content gap:** 80px
- **Browse grid:** 2 columns on desktop, 1 column on mobile
- **Browse block gap:** 32px vertical, 12px title-to-description gap
- **Category rule height:** 4px
- **Sidebar divider:** 1px solid `#ddddda`

## Components

### Top Navigation Bar
**Role:** Site-wide navigation for the BOI publication workspace

White background with a subtle bottom border. The logo sits on the far left, followed by text labels for **Catalog**, **Directives**, **Reader**, and **Search**. These labels must remain visible at 100% zoom and should not collapse into a hidden menu on normal desktop widths. If a future global search input is added, place it right-aligned and use a rounded gray pill background. Primary actions should be compact navy buttons.

### Search Input
**Role:** Global publication search

Rounded pill with `#ececea` background, no visible border, search icon on the left, and muted placeholder text. Desktop width should be roughly 250–320px. Placeholder examples: “Search publications,” “Search PDFs,” or “Search operational resilience.”

### Informational Banner
**Role:** Contextual guidance / assistant entry point

Full-width pale-blue banner below the header. It has an 8px radius, soft blue border, bold title, one-sentence body copy, an underlined inline link when needed, a navy primary button, and a secondary text action. Keep it practical and BOI-specific; avoid promotional or off-domain wording.

### Browse Publications Grid
**Role:** Primary content area

Two-column grid or shelf of publication groups. Each item begins with a 4px colored rule or a thin divider, followed by a serif group title and a short sans-serif description. Items are not enclosed in rounded cards. Structure comes from rules, whitespace, and typography.

### Category Rule
**Role:** Visual grouping marker

A thin 4px horizontal line above each publication group. Assign each group one muted category color. The rule spans the full width of the group block. Do not use saturated blocks, badges, gradients, or large color fills.

### Group Title
**Role:** Main link to a publication group

Large serif text, black, approximately 28px. It should feel like a source-library heading, not a marketing headline.

### Sidebar Section
**Role:** Context, history, source status, and reader support

Right-hand column with stacked sections. Each section has a bold sans-serif heading, a thin horizontal divider, and compact body copy. Sidebar content is secondary and should never compete with the browse grid.

### Reader Button
**Role:** Primary route into searchable PDFs

Navy rectangular button with white text, 4px radius, and a subtle shadow. Use for actions such as “Open Reader,” “Start Search,” or “View Source PDF.”

### Recently Opened Source Link
**Role:** Returning users to previous publication locations

Serif source-style text link with two recent items separated by a dot. It should appear denser and more document-like than the surrounding sans-serif UI.

### Indexed Sources List
**Role:** Coverage and extraction status

Compact inline or stacked list for metadata such as “PDF indexed,” “text extracted,” “source URL saved,” “matches highlighted,” and “download available.” Use muted text and separators; do not turn this into a colorful analytics card.

### Reader View
**Role:** Searchable publication/PDF reading experience

A document-first view with the source PDF or extracted text as the dominant surface. Support search highlights, page navigation, citation/source metadata, download links, and clear return paths to Catalog and Search. Keep controls compact and navy/gray.

### PDF Viewer Direction
**Role:** Sefaria-inspired source reading surface

The reusable PDF viewer should feel like a quiet source reader, not a dashboard. The PDF page is the dominant surface. The left rail is for source title, in-document search, page navigation, selected source context, and result snippets. The right rail is for legal analysis: regulatory reading, issues flagged, selected evidence, and review questions. Use white paper, warm gray gutters, deep navy controls, serif source text, and subtle highlighted matches.

## Do's and Don'ts

### Do
- Use a white page canvas with warm gray surrounding space and subtle borders.
- Keep the interface text-first; prioritize source titles, metadata, publication descriptions, and search clarity.
- Use navy only for primary actions, active controls, and the logo accent.
- Use serif typography for publication group titles and source references.
- Use sans-serif typography for navigation, descriptions, banners, filters, and sidebar headings.
- Use thin colored rules to distinguish publication groups instead of large colored blocks.
- Preserve the two-column browse grid and the right-hand sidebar on desktop.
- Keep body descriptions short and plain.
- Keep **Catalog**, **Directives**, **Reader**, and **Search** visible in the top nav at desktop width.
- Place directive-specific PDF reading, highlighting, and source extraction inside **Reader** rather than creating extra redundant tabs.

### Don't
- Don't use wording, categories, examples, or copy from the visual reference site.
- Don't use gradients, glowing shadows, mint surfaces, or SaaS-style product cards.
- Don't turn each publication group into a rounded card; use lines and whitespace.
- Don't make the sidebar visually dominant; it should be secondary to the browse grid.
- Don't over-saturate the category colors; they should feel official, scholarly, and muted.
- Don't use large marketing hero copy; the page begins with browsing and searching, not promotion.
- Don't hide top nav items behind a hamburger at 100% zoom on desktop.
- Don't create a separate **Proper Conduct of Banking Business Directives** tab.

## Surfaces

| Level | Name | Value | Purpose |
|-------|------|-------|---------|
| 0 | Page Warm Gray | `#f7f7f5` | Outer page background |
| 1 | Paper White | `#ffffff` | Header, main content, sidebar, reader canvas |
| 2 | Banner Blue | `#eef5ff` | Informational assistant/search banner |
| 3 | Search Gray | `#ececea` | Search pill and quiet input areas |
| 4 | Reader Panel | `#fafafa` | Optional contained panel for extracted text, metadata, or source previews |

## Elevation

- **Primary navy buttons:** subtle shadow only when needed, `rgba(0,0,0,0.18) 0px 2px 6px`
- **Header:** no shadow; use a 1px bottom border
- **Browse grid:** no shadow
- **Sidebar:** no shadow
- **Banner:** no shadow; use a border and pale fill
- **Reader panels:** minimal elevation only when separating PDF preview from extracted text

## Imagery and Icons

The page does not rely on imagery. Icons should be small, monochrome, and functional: search, play/help, language, index/status, download, external source, page navigation, and account/profile. Avoid illustrations, photos, complex icons, decorative background patterns, or large brand graphics. The visual identity comes from typography, spacing, navy buttons, dividers, and category rules.

## Layout

The top navigation spans the full viewport and stays visually lightweight. Below it, the informational banner spans the full width with a small margin around it. The main content area is centered and begins lower on the page with generous top padding.

Desktop layout: the left column contains **Browse Publications** and the two-column publication grid. The right column contains the information/sidebar sections. The sidebar begins roughly aligned with the Browse heading and uses dividers between sections. A subtle pale-gray vertical area may separate the main content from the sidebar.

Mobile layout: stack the banner actions, then show **Browse Publications**, then publication groups in one column, followed by sidebar sections. Keep top-level navigation accessible, but do not hide desktop nav items at normal desktop widths.

## Agent Prompt Guide

Primary action: deep navy button with white text.
Overall direction: create a BOI publication-library interface with a calm academic/regulatory feel, a searchable header, an informational banner, a two-column browse grid, a compact right sidebar, and a Reader for searchable PDFs and extracted text.

Example Component Prompts:

1. Style the existing top navigation bar with the left-aligned “Bank of Israel Publications Explorer” logo and visible labels for Catalog, Directives, Reader, and Search; do not add new navigation behavior unless explicitly requested.
2. Style the existing Library segmented control for Catalog, Reader, and Regional Map with restrained spacing, clear active state, and no hidden desktop items.
3. Style the existing Browse Publications area as a two-column source shelf. Each group should use a 4px colored rule, a large serif title, and a short sans-serif description.
4. Style the right sidebar/info area with sections for the BOI library summary and current index, each separated by thin gray horizontal rules.
5. Style the Reader view so users can search inside extracted PDF text, see highlighted matches, navigate pages, open the official source PDF, and download sources.
6. Style the Regional Map view so Jordan appears as the first connected external corpus while remaining visually separate from the Reader.
7. Make the page feel official, calm, scholarly, and readable. Avoid gradients, product cards, oversized hero text, saturated effects, and any non-BOI source language.

## Quick Start

### CSS Custom Properties

```css
:root {
  /* Colors */
  --color-boi-navy: #17345b;
  --color-navy-hover: #102845;
  --color-paper-white: #ffffff;
  --color-page-warm-gray: #f7f7f5;
  --color-search-gray: #ececea;
  --color-rule-gray: #ddddda;
  --color-text-ink: #222222;
  --color-text-muted: #666666;
  --color-banner-blue: #eef5ff;
  --color-banner-border: #d6e5ff;
  --color-reader-panel: #fafafa;

  /* Category rule colors */
  --color-category-teal: #006d7e;
  --color-category-blue: #6fa6bd;
  --color-category-gold: #c0ad5c;
  --color-category-green: #5f986c;
  --color-category-rose: #9b2f4a;
  --color-category-purple: #5d3f85;
  --color-category-magenta: #b84d73;
  --color-category-lavender: #8d91b2;
  --color-category-emerald: #00947f;
  --color-category-sage: #93aa83;

  /* Typography */
  --font-ui: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif;
  --font-source-serif: Georgia, "Times New Roman", serif;

  /* Type scale */
  --text-utility: 13px;
  --text-body-sm: 14px;
  --text-body: 16px;
  --text-nav: 16px;
  --text-sidebar-heading: 24px;
  --text-section-heading: 24px;
  --text-category-title: 28px;
  --text-source-title: 20px;

  /* Spacing */
  --spacing-4: 4px;
  --spacing-8: 8px;
  --spacing-12: 12px;
  --spacing-16: 16px;
  --spacing-20: 20px;
  --spacing-24: 24px;
  --spacing-32: 32px;
  --spacing-40: 40px;
  --spacing-48: 48px;
  --spacing-64: 64px;
  --spacing-80: 80px;

  /* Layout */
  --header-height: 72px;
  --page-max-width: 1280px;
  --main-column-width: 760px;
  --sidebar-width: 340px;
  --main-content-gap: 80px;

  /* Radius */
  --radius-search: 18px;
  --radius-button: 4px;
  --radius-banner: 8px;
  --radius-reader-panel: 6px;

  /* Borders and shadows */
  --border-subtle: 1px solid var(--color-rule-gray);
  --shadow-button: rgba(0, 0, 0, 0.18) 0px 2px 6px;
}
```

### Tailwind v4 Theme Tokens

```css
@theme {
  --color-boi-navy: #17345b;
  --color-navy-hover: #102845;
  --color-paper-white: #ffffff;
  --color-page-warm-gray: #f7f7f5;
  --color-search-gray: #ececea;
  --color-rule-gray: #ddddda;
  --color-text-ink: #222222;
  --color-text-muted: #666666;
  --color-banner-blue: #eef5ff;
  --color-banner-border: #d6e5ff;
  --color-reader-panel: #fafafa;

  --color-category-teal: #006d7e;
  --color-category-blue: #6fa6bd;
  --color-category-gold: #c0ad5c;
  --color-category-green: #5f986c;
  --color-category-rose: #9b2f4a;
  --color-category-purple: #5d3f85;
  --color-category-magenta: #b84d73;
  --color-category-lavender: #8d91b2;
  --color-category-emerald: #00947f;
  --color-category-sage: #93aa83;

  --font-ui: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif;
  --font-source-serif: Georgia, "Times New Roman", serif;

  --radius-search: 18px;
  --radius-button: 4px;
  --radius-banner: 8px;
  --radius-reader-panel: 6px;
}
```
