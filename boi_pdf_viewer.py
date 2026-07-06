"""
Reusable interactive PDF reader for Bank of Israel publications.

The server side turns a PDF into page images, extracted text, and word boxes.
The browser side provides the paired PDF/text reading experience, search,
result navigation, and synchronized page scrolling.
"""
import base64
import json
from typing import Any

import fitz  # pymupdf
import requests
import streamlit as st

from boi_pdf_text import HEADERS


def download_pdf(url: str) -> bytes:
    """Download a BOI PDF and return its bytes."""
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("The selected URL did not return a PDF.")
    return response.content


def build_pdf_viewer_model(
        pdf_bytes: bytes,
        *,
        title: str,
        source_url: str,
        render_scale: float = 1.35,
        max_pages: int | None = None) -> dict[str, Any]:
    """Build a self-contained document model for the HTML reader."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    try:
        total_pages = doc.page_count
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
        for page_index in range(total_pages):
            page = doc.load_page(page_index)
            rect = page.rect
            pix = page.get_pixmap(
                matrix=fitz.Matrix(render_scale, render_scale),
                alpha=False,
                colorspace=fitz.csRGB,
            )
            image_data = base64.b64encode(pix.tobytes("png")).decode("ascii")
            words = []
            for word in page.get_text("words", sort=True):
                x0, y0, x1, y1, text, block_no, line_no, word_no = word[:8]
                text = str(text).strip()
                if not text:
                    continue
                words.append({
                    "t": text,
                    "x0": round(float(x0), 2),
                    "y0": round(float(y0), 2),
                    "x1": round(float(x1), 2),
                    "y1": round(float(y1), 2),
                    "b": int(block_no),
                    "l": int(line_no),
                    "w": int(word_no),
                })

            pages.append({
                "number": page_index + 1,
                "width": round(float(rect.width), 2),
                "height": round(float(rect.height), 2),
                "imageWidth": pix.width,
                "imageHeight": pix.height,
                "image": "data:image/png;base64," + image_data,
                "text": page.get_text("text"),
                "words": words,
            })
    finally:
        doc.close()

    return {
        "title": title or "Bank of Israel publication",
        "sourceUrl": source_url,
        "pageCount": len(pages),
        "pages": pages,
    }


def render_pdf_viewer(model: dict[str, Any], *, height: int = 860) -> None:
    """Render the interactive reader inside Streamlit."""
    st.iframe(pdf_viewer_html(model), height=height)


def pdf_viewer_html(model: dict[str, Any]) -> str:
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: light;
    --bg: #f6f4ef;
    --ink: #172026;
    --muted: #5d6870;
    --line: #ded8cf;
    --paper: #fffefa;
    --panel: #f8f6f1;
    --accent: #244e60;
    --accent-strong: #163744;
    --hit: rgba(241, 204, 83, 0.40);
    --hit-active: rgba(68, 127, 146, 0.34);
    --shadow: 0 18px 45px rgba(38, 31, 20, 0.13);
  }}

  * {{ box-sizing: border-box; }}

  html,
  body {{
    height: 100%;
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}

  button,
  input {{
    font: inherit;
  }}

  .reader {{
    height: 100vh;
    display: grid;
    grid-template-columns: 330px minmax(0, 1fr);
    gap: 0;
    overflow: hidden;
    border: 1px solid var(--line);
    background: var(--panel);
  }}

  .sidebar {{
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 18px 16px;
    border-right: 1px solid var(--line);
    background: #f9f7f2;
  }}

  .title {{
    display: grid;
    gap: 6px;
  }}

  .title h1 {{
    margin: 0;
    font-size: 19px;
    line-height: 1.25;
    font-weight: 700;
    letter-spacing: 0;
  }}

  .title a {{
    color: var(--accent);
    font-size: 13px;
    text-decoration: none;
  }}

  .title a:hover {{
    text-decoration: underline;
  }}

  .rail-label {{
    color: var(--muted);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}

  .search {{
    display: grid;
    gap: 8px;
  }}

  .search input,
  .page-jump input {{
    width: 100%;
    height: 38px;
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0 10px;
    color: var(--ink);
    background: white;
    outline: none;
  }}

  .search input:focus,
  .page-jump input:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(43, 111, 120, 0.12);
  }}

  .toolbar {{
    display: grid;
    grid-template-columns: 38px 1fr 38px;
    gap: 8px;
    align-items: center;
  }}

  .toolbar button,
  .result-nav button {{
    height: 36px;
    border: 1px solid var(--line);
    border-radius: 7px;
    color: var(--ink);
    background: white;
    cursor: pointer;
  }}

  .toolbar button:hover,
  .result-nav button:hover {{
    border-color: var(--accent);
    color: var(--accent-strong);
  }}

  .page-jump {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
    font-size: 13px;
    white-space: nowrap;
  }}

  .page-jump input {{
    text-align: center;
    padding: 0;
  }}

  .result-nav {{
    display: grid;
    grid-template-columns: 1fr 38px 38px;
    gap: 8px;
    align-items: center;
  }}

  .result-count {{
    color: var(--muted);
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .context {{
    display: grid;
    gap: 8px;
    padding: 13px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: white;
  }}

  .context-title {{
    color: var(--accent-strong);
    font-size: 13px;
    font-weight: 800;
  }}

  .context-body {{
    color: var(--muted);
    font-family: Georgia, "Times New Roman", serif;
    font-size: 14px;
    line-height: 1.45;
  }}

  .chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }}

  .chip {{
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 4px 8px;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.72);
    font-size: 11px;
    font-weight: 700;
  }}

  .results {{
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    display: grid;
    align-content: start;
    gap: 8px;
    padding-right: 3px;
  }}

  .result {{
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px;
    background: white;
    color: var(--ink);
    text-align: left;
    cursor: pointer;
  }}

  .result:hover,
  .result.active {{
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(43, 111, 120, 0.10);
  }}

  .result .meta {{
    color: var(--accent-strong);
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 5px;
  }}

  .result .snippet {{
    color: var(--muted);
    font-size: 12px;
    line-height: 1.35;
  }}

  .empty {{
    padding: 12px;
    color: var(--muted);
    font-size: 13px;
    border: 1px dashed var(--line);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.65);
  }}

  .main {{
    min-width: 0;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 1px;
    background: var(--line);
    overflow: hidden;
  }}

  .stage-header {{
    min-width: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 16px;
    align-items: center;
    padding: 13px 18px;
    border-bottom: 1px solid var(--line);
    background: rgba(255, 254, 250, 0.96);
  }}

  .stage-title {{
    min-width: 0;
    display: grid;
    gap: 2px;
  }}

  .stage-title strong {{
    overflow: hidden;
    color: var(--ink);
    font-size: 16px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  .stage-title span,
  .stage-meta {{
    color: var(--muted);
    font-size: 12px;
  }}

  .stage-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }}

  .stage-meta b {{
    color: var(--accent-strong);
  }}

  .stage {{
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(360px, 1.08fr) minmax(340px, 0.92fr);
    gap: 1px;
    overflow: hidden;
    background: var(--line);
  }}

  .pane {{
    min-width: 0;
    height: 100%;
    overflow: auto;
    scroll-behavior: smooth;
    background: var(--bg);
  }}

  .pdf-pane {{
    padding: 24px 22px 38px;
  }}

  .text-pane {{
    padding: 24px 24px 44px;
    background: var(--paper);
  }}

  .pdf-page {{
    position: relative;
    width: min(100%, 920px);
    margin: 0 auto 24px;
    background: white;
    box-shadow: var(--shadow);
  }}

  .pdf-page.active {{
    outline: 3px solid rgba(36, 78, 96, 0.20);
  }}

  .pdf-page img {{
    display: block;
    width: 100%;
    height: auto;
  }}

  .pdf-overlay {{
    position: absolute;
    inset: 0;
    pointer-events: none;
  }}

  .pdf-hit {{
    position: absolute;
    border-radius: 2px;
    background: var(--hit);
    mix-blend-mode: multiply;
  }}

  .pdf-hit.active {{
    background: var(--hit-active);
    outline: 2px solid rgba(23, 77, 86, 0.82);
    z-index: 2;
  }}

  .text-page {{
    max-width: 760px;
    margin: 0 auto 28px;
    padding: 14px 18px 24px;
    border-bottom: 1px solid var(--line);
  }}

  .text-page.active {{
    background: rgba(237, 243, 244, 0.72);
  }}

  .text-page.active .page-label {{
    color: var(--accent-strong);
  }}

  .page-label {{
    margin-bottom: 10px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}

  .page-text {{
    white-space: pre-wrap;
    color: #20272d;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 17px;
    line-height: 1.64;
  }}

  mark {{
    border-radius: 3px;
    padding: 0 2px;
    color: inherit;
    background: var(--hit);
  }}

  @media (max-width: 980px) {{
    .reader {{
      grid-template-columns: 1fr;
      grid-template-rows: auto minmax(0, 1fr);
    }}

    .sidebar {{
      border-right: 0;
      border-bottom: 1px solid var(--line);
      max-height: 330px;
    }}

    .results {{
      max-height: 120px;
    }}

    .stage-header {{
      grid-template-columns: 1fr;
    }}

    .stage {{
      grid-template-columns: 1fr;
    }}

    .pane {{
      height: 48vh;
    }}
  }}
</style>
</head>
<body>
<div class="reader">
  <aside class="sidebar">
    <div class="title">
      <div class="rail-label">Bank of Israel Reader</div>
      <h1 id="docTitle"></h1>
      <a id="sourceLink" target="_blank" rel="noreferrer">Source PDF</a>
    </div>
    <div class="search">
      <input id="searchInput" type="search" placeholder="Search inside this document" autocomplete="off">
      <div class="result-nav">
        <div id="resultCount" class="result-count">No query</div>
        <button id="prevResult" type="button" title="Previous result">&uarr;</button>
        <button id="nextResult" type="button" title="Next result">&darr;</button>
      </div>
    </div>
    <div class="toolbar">
      <button id="prevPage" type="button" title="Previous page">&lsaquo;</button>
      <label class="page-jump">
        <span>Page</span>
        <input id="pageInput" type="number" min="1" value="1">
        <span id="pageTotal"></span>
      </label>
      <button id="nextPage" type="button" title="Next page">&rsaquo;</button>
    </div>
    <section class="context">
      <div class="rail-label">Selected source</div>
      <div id="selectedTitle" class="context-title">Page 1</div>
      <div id="selectedContext" class="context-body">Search or scroll to focus a passage.</div>
      <div class="chips">
        <span class="chip">Annotations</span>
        <span class="chip">Bookmarks</span>
        <span class="chip">Citations</span>
        <span class="chip">Ask AI</span>
      </div>
    </section>
    <div id="results" class="results"></div>
  </aside>
  <main class="main">
    <header class="stage-header">
      <div class="stage-title">
        <span>PDF + extracted text</span>
        <strong id="stageTitle"></strong>
      </div>
      <div class="stage-meta">
        <span>Page <b id="livePage">1</b> of <b id="liveTotal">1</b></span>
        <span id="liveMatches">No query</span>
      </div>
    </header>
    <div class="stage">
      <section id="pdfPane" class="pane pdf-pane" aria-label="PDF pages"></section>
      <section id="textPane" class="pane text-pane" aria-label="Extracted text"></section>
    </div>
  </main>
</div>
<script id="payload" type="application/json">{payload}</script>
<script>
(() => {{
  const payload = JSON.parse(document.getElementById("payload").textContent);
  const pages = payload.pages || [];
  const state = {{
    activePage: 1,
    activeResult: -1,
    matches: [],
    queryParts: [],
    syncing: false,
    syncTimer: null
  }};

  const pdfPane = document.getElementById("pdfPane");
  const textPane = document.getElementById("textPane");
  const resultsEl = document.getElementById("results");
  const searchInput = document.getElementById("searchInput");
  const resultCount = document.getElementById("resultCount");
  const pageInput = document.getElementById("pageInput");
  const pageTotal = document.getElementById("pageTotal");
  const selectedTitle = document.getElementById("selectedTitle");
  const selectedContext = document.getElementById("selectedContext");
  const stageTitle = document.getElementById("stageTitle");
  const livePage = document.getElementById("livePage");
  const liveTotal = document.getElementById("liveTotal");
  const liveMatches = document.getElementById("liveMatches");

  document.getElementById("docTitle").textContent = payload.title;
  stageTitle.textContent = payload.title;
  document.getElementById("sourceLink").href = payload.sourceUrl;
  pageInput.max = String(Math.max(1, payload.pageCount || pages.length || 1));
  pageTotal.textContent = "/ " + pageInput.max;
  liveTotal.textContent = pageInput.max;

  function escapeHtml(value) {{
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }}

  function escapeRegex(value) {{
    return value.replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&");
  }}

  function cleanToken(value) {{
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  }}

  function parseQuery(raw) {{
    const parts = [];
    const matcher = /"([^"]+)"|(\\S+)/g;
    let match;
    while ((match = matcher.exec(raw)) !== null) {{
      const label = (match[1] || match[2] || "").trim();
      const tokens = label.split(/\\s+/).map(cleanToken).filter(Boolean);
      if (tokens.length) {{
        parts.push({{ label, tokens }});
      }}
    }}
    return parts;
  }}

  function markText(rawText, parts) {{
    const terms = [...new Set(parts.flatMap(part => part.tokens))]
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
    if (!terms.length) {{
      return escapeHtml(rawText || "");
    }}
    const re = new RegExp("(" + terms.map(escapeRegex).join("|") + ")", "gi");
    let out = "";
    let last = 0;
    const text = String(rawText || "");
    for (const match of text.matchAll(re)) {{
      out += escapeHtml(text.slice(last, match.index));
      out += "<mark>" + escapeHtml(match[0]) + "</mark>";
      last = match.index + match[0].length;
    }}
    out += escapeHtml(text.slice(last));
    return out;
  }}

  function renderPages() {{
    pdfPane.innerHTML = pages.map(page => `
      <article class="pdf-page" data-page="${{page.number}}" style="aspect-ratio:${{page.width}} / ${{page.height}}">
        <img src="${{page.image}}" alt="Page ${{page.number}}">
        <div class="pdf-overlay" data-page="${{page.number}}"></div>
      </article>
    `).join("");

    textPane.innerHTML = pages.map(page => `
      <article class="text-page" data-page="${{page.number}}">
        <div class="page-label">Page ${{page.number}}</div>
        <div class="page-text">${{markText(page.text, state.queryParts)}}</div>
      </article>
    `).join("");
  }}

  function snippetFor(page, startWord, endWord) {{
    const before = Math.max(0, startWord - 10);
    const after = Math.min(page.words.length, endWord + 11);
    const left = before > 0 ? "... " : "";
    const right = after < page.words.length ? " ..." : "";
    return left + page.words.slice(before, after).map(word => word.t).join(" ") + right;
  }}

  function pagePreview(pageNumber) {{
    const page = pages[pageNumber - 1];
    if (!page) {{
      return "No page selected.";
    }}
    const text = String(page.text || "").replace(/\\s+/g, " ").trim();
    return text ? text.slice(0, 260) + (text.length > 260 ? " ..." : "") : "No extracted text on this page.";
  }}

  function buildMatches() {{
    const matches = [];
    if (!state.queryParts.length) {{
      return matches;
    }}

    pages.forEach(page => {{
      const tokens = (page.words || []).map(word => cleanToken(word.t));
      state.queryParts.forEach(part => {{
        if (part.tokens.length === 1) {{
          const term = part.tokens[0];
          tokens.forEach((token, index) => {{
            if (token.includes(term)) {{
              matches.push({{
                id: matches.length,
                page: page.number,
                label: part.label,
                wordStart: index,
                wordEnd: index,
                boxes: [page.words[index]],
                snippet: snippetFor(page, index, index)
              }});
            }}
          }});
          return;
        }}

        const span = part.tokens.length;
        for (let index = 0; index <= tokens.length - span; index += 1) {{
          let ok = true;
          for (let offset = 0; offset < span; offset += 1) {{
            if (tokens[index + offset] !== part.tokens[offset]) {{
              ok = false;
              break;
            }}
          }}
          if (ok) {{
            matches.push({{
              id: matches.length,
              page: page.number,
              label: part.label,
              wordStart: index,
              wordEnd: index + span - 1,
              boxes: page.words.slice(index, index + span),
              snippet: snippetFor(page, index, index + span - 1)
            }});
          }}
        }}
      }});
    }});
    return matches;
  }}

  function renderHighlights() {{
    document.querySelectorAll(".pdf-overlay").forEach(node => {{
      node.innerHTML = "";
    }});

    state.matches.forEach(match => {{
      const page = pages[match.page - 1];
      const overlay = document.querySelector(`.pdf-overlay[data-page="${{match.page}}"]`);
      if (!page || !overlay) {{
        return;
      }}
      match.boxes.forEach(box => {{
        const node = document.createElement("div");
        node.className = "pdf-hit" + (match.id === state.activeResult ? " active" : "");
        node.style.left = (box.x0 / page.width * 100).toFixed(3) + "%";
        node.style.top = (box.y0 / page.height * 100).toFixed(3) + "%";
        node.style.width = ((box.x1 - box.x0) / page.width * 100).toFixed(3) + "%";
        node.style.height = ((box.y1 - box.y0) / page.height * 100).toFixed(3) + "%";
        overlay.appendChild(node);
      }});
    }});
  }}

  function renderResults() {{
    if (!state.queryParts.length) {{
      resultCount.textContent = "No query";
      liveMatches.textContent = "No query";
      resultsEl.innerHTML = '<div class="empty">Search this document</div>';
      return;
    }}

    const count = state.matches.length;
    resultCount.textContent = count === 1 ? "1 result" : count + " results";
    liveMatches.textContent = resultCount.textContent;
    if (!count) {{
      resultsEl.innerHTML = '<div class="empty">No matches</div>';
      return;
    }}

    resultsEl.innerHTML = state.matches.map((match, index) => `
      <button class="result ${{match.id === state.activeResult ? "active" : ""}}" type="button" data-result="${{match.id}}">
        <div class="meta">Page ${{match.page}} &middot; ${{escapeHtml(match.label)}}</div>
        <div class="snippet">${{escapeHtml(match.snippet)}}</div>
      </button>
    `).join("");

    resultsEl.querySelectorAll(".result").forEach(button => {{
      button.addEventListener("click", () => {{
        selectResult(Number(button.dataset.result));
      }});
    }});
  }}

  function setActivePage(pageNumber) {{
    const max = pages.length || 1;
    state.activePage = Math.min(Math.max(1, Number(pageNumber) || 1), max);
    pageInput.value = String(state.activePage);
    livePage.textContent = String(state.activePage);
    document.querySelectorAll("[data-page]").forEach(node => {{
      node.classList.toggle("active", Number(node.dataset.page) === state.activePage);
    }});
    updateSelectedContext();
  }}

  function scrollPaneToPage(pane, pageNumber) {{
    const target = pane.querySelector(`[data-page="${{pageNumber}}"]`);
    if (!target) {{
      return;
    }}
    pane.scrollTo({{
      top: target.offsetTop - pane.offsetTop - 12,
      behavior: "smooth"
    }});
  }}

  function scrollToPage(pageNumber) {{
    setActivePage(pageNumber);
    state.syncing = true;
    scrollPaneToPage(pdfPane, state.activePage);
    scrollPaneToPage(textPane, state.activePage);
    window.setTimeout(() => {{
      state.syncing = false;
    }}, 450);
  }}

  function selectResult(resultId) {{
    const match = state.matches.find(item => item.id === resultId);
    if (!match) {{
      return;
    }}
    state.activeResult = resultId;
    renderHighlights();
    renderResults();
    updateSelectedContext(match);
    scrollToPage(match.page);
    const selected = resultsEl.querySelector(`[data-result="${{resultId}}"]`);
    if (selected) {{
      selected.scrollIntoView({{ block: "nearest", behavior: "smooth" }});
    }}
  }}

  function updateSelectedContext(match) {{
    const activeMatch = match || state.matches.find(item => item.id === state.activeResult);
    if (activeMatch) {{
      selectedTitle.textContent = `Page ${{activeMatch.page}} - ${{activeMatch.label}}`;
      selectedContext.textContent = activeMatch.snippet;
      return;
    }}
    selectedTitle.textContent = `Page ${{state.activePage}}`;
    selectedContext.textContent = pagePreview(state.activePage);
  }}

  function findVisiblePage(pane) {{
    const paneTop = pane.getBoundingClientRect().top;
    let bestPage = state.activePage;
    let bestDistance = Number.POSITIVE_INFINITY;
    pane.querySelectorAll("[data-page]").forEach(node => {{
      const distance = Math.abs(node.getBoundingClientRect().top - paneTop - 12);
      if (distance < bestDistance) {{
        bestDistance = distance;
        bestPage = Number(node.dataset.page);
      }}
    }});
    return bestPage;
  }}

  function bindScrollSync(source, target) {{
    source.addEventListener("scroll", () => {{
      if (state.syncing) {{
        return;
      }}
      const page = findVisiblePage(source);
      setActivePage(page);
      window.clearTimeout(state.syncTimer);
      state.syncTimer = window.setTimeout(() => {{
        state.syncing = true;
        scrollPaneToPage(target, page);
        window.setTimeout(() => {{
          state.syncing = false;
        }}, 350);
      }}, 100);
    }}, {{ passive: true }});
  }}

  function runSearch() {{
    state.queryParts = parseQuery(searchInput.value);
    state.matches = buildMatches();
    state.activeResult = state.matches.length ? state.matches[0].id : -1;
    renderPages();
    renderHighlights();
    renderResults();
    if (state.activeResult >= 0) {{
      updateSelectedContext(state.matches[0]);
    }} else {{
      updateSelectedContext();
    }}
    setActivePage(state.activePage);
  }}

  document.getElementById("prevPage").addEventListener("click", () => {{
    scrollToPage(state.activePage - 1);
  }});
  document.getElementById("nextPage").addEventListener("click", () => {{
    scrollToPage(state.activePage + 1);
  }});
  pageInput.addEventListener("change", () => {{
    scrollToPage(pageInput.value);
  }});
  document.getElementById("prevResult").addEventListener("click", () => {{
    if (!state.matches.length) return;
    const pos = Math.max(0, state.matches.findIndex(item => item.id === state.activeResult));
    const next = state.matches[(pos - 1 + state.matches.length) % state.matches.length];
    selectResult(next.id);
  }});
  document.getElementById("nextResult").addEventListener("click", () => {{
    if (!state.matches.length) return;
    const pos = Math.max(0, state.matches.findIndex(item => item.id === state.activeResult));
    const next = state.matches[(pos + 1) % state.matches.length];
    selectResult(next.id);
  }});
  searchInput.addEventListener("input", runSearch);

  renderPages();
  renderResults();
  setActivePage(1);
  bindScrollSync(pdfPane, textPane);
  bindScrollSync(textPane, pdfPane);
}})();
</script>
</body>
</html>"""
