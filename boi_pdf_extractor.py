"""
Extract document (PDF/Excel/Word) links from Bank of Israel publication pages.

The site is behind Radware Bot Manager, so we drive a real Chromium browser via
Playwright. A warm-up visit to /en/ acquires the Radware clearance cookies, then
each publication page is visited and its document links are collected.

Anti-bot hardening (Radware escalates as a single session ages):
  * Session rotation  -- a fresh browser + cookie jar every ROTATE_EVERY pages.
  * Block-cluster cool-down -- on CONSEC_BLOCK_LIMIT blocks in a row, sleep and
    rebuild the session from scratch.
  * Jittered, polite pacing between pages.

Design notes:
  * Scope: regular-publications + research/analysis pages from the sitemap index.
  * Resumable: pages already recorded as "ok" in the progress file are skipped,
    so the run can be stopped (Ctrl-C) and restarted at any time. Blocked pages
    are NOT marked done, so a re-run retries them.

Outputs (in the project dir):
  boi_pdf_links.csv     one row per document link found
  boi_pdf_progress.csv  one row per page visited (status = ok | blocked)
"""
import csv
import os
import random
import time
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "boi_publications_index.csv")
OUT_LINKS = os.path.join(HERE, "boi_pdf_links.csv")
OUT_PROGRESS = os.path.join(HERE, "boi_pdf_progress.csv")

DOC_EXT = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".pptx", ".ppt")
DELAY = 2.0               # base seconds between pages (+ jitter)
JITTER = 1.5             # up to this many extra seconds, randomly
PAGE_SETTLE = 3000       # ms to let Radware JS + content render
MAX_ATTEMPTS = 3         # per-page retries before marking blocked
ROTATE_EVERY = 35        # rebuild the browser session every N pages
CONSEC_BLOCK_LIMIT = 3   # this many blocks in a row -> cool-down + rotate
COOLDOWN = 45            # seconds to wait when blocks cluster

# A few realistic desktop UAs to vary across sessions.
UAS = [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
]

STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = {runtime:{}};
"""


def is_blocked(title):
    t = (title or "").lower()
    return any(k in t for k in ("radware", "captcha", "403", "forbidden"))


def load_done():
    """Return the set of source pages already processed successfully."""
    if not os.path.exists(OUT_PROGRESS):
        return set()
    try:
        p = pd.read_csv(OUT_PROGRESS)
        return set(p.loc[p["status"] == "ok", "source_page"])
    except Exception:
        return set()


def select_targets():
    df = pd.read_csv(INDEX)
    u = df["url"].str.lower()
    mask = u.str.contains("regular-publications") | u.str.contains("research")
    return df[mask].reset_index(drop=True)


def warm_up(page, ctx):
    page.goto("https://www.boi.org.il/en/", wait_until="domcontentloaded",
              timeout=45000)
    page.wait_for_timeout(5000)
    return len(ctx.cookies())


def build_session(p, old_browser=None):
    """(Re)create a fresh browser + context + warmed-up page.

    A brand-new context means an empty cookie jar, so Radware issues fresh
    clearance -- this is what resets the "session age" it uses to escalate.
    """
    if old_browser is not None:
        try:
            old_browser.close()
        except Exception:
            pass
    browser = p.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=random.choice(UAS), locale="en-US",
        viewport={"width": random.choice([1366, 1440, 1536]),
                  "height": random.choice([864, 900, 960])})
    ctx.add_init_script(STEALTH)
    page = ctx.new_page()
    cookies = warm_up(page, ctx)
    print(f"  [session] fresh browser, {cookies} cookies", flush=True)
    return browser, ctx, page


def extract_docs(page, url):
    pairs = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))",
    )
    seen, docs = set(), []
    for a in pairs:
        href = a.get("href")
        if not href:
            continue
        absolute = urljoin(url, href)
        if absolute.lower().split("?")[0].endswith(DOC_EXT):
            if absolute not in seen:
                seen.add(absolute)
                docs.append((absolute, (a.get("text") or "").strip()))
    return docs


def visit(page, ctx, url):
    """Load a page with retries; re-warm the current context on a block.

    Returns the page title (may indicate a block) or an 'ERR ...' string.
    """
    title = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(PAGE_SETTLE + attempt * 2500)
            title = page.title()
            if not is_blocked(title):
                return title
            warm_up(page, ctx)  # cheap in-context recovery
        except Exception as e:
            title = f"ERR {e}"
        time.sleep(2)
    return title


def main():
    targets = select_targets()
    done = load_done()
    todo = targets[~targets["url"].isin(done)]
    print(f"Targets: {len(targets)} | already done: {len(done)} | "
          f"to process: {len(todo)}", flush=True)

    links_new = not os.path.exists(OUT_LINKS)
    prog_new = not os.path.exists(OUT_PROGRESS)
    lf = open(OUT_LINKS, "a", newline="", encoding="utf-8")
    pf = open(OUT_PROGRESS, "a", newline="", encoding="utf-8")
    lw = csv.writer(lf)
    pw_ = csv.writer(pf)
    if links_new:
        lw.writerow(["source_page", "source_title", "section", "lastmod",
                     "doc_title", "doc_url", "doc_type"])
    if prog_new:
        pw_.writerow(["source_page", "status", "doc_count"])

    with sync_playwright() as p:
        browser, ctx, page = build_session(p)
        since_rotate = 0
        consec_blocks = 0
        total = len(todo)

        for i, (_, row) in enumerate(todo.iterrows(), 1):
            # Proactive rotation before the session gets "old".
            if since_rotate >= ROTATE_EVERY:
                browser, ctx, page = build_session(p, browser)
                since_rotate = 0

            url = row["url"]
            title = visit(page, ctx, url)
            since_rotate += 1

            if is_blocked(title) or title.startswith("ERR"):
                pw_.writerow([url, "blocked", 0])
                pf.flush()
                consec_blocks += 1
                print(f"[{i}/{total}] BLOCKED ({consec_blocks}) {url[:66]}",
                      flush=True)
                # Blocks clustering -> cool down and rebuild from scratch.
                if consec_blocks >= CONSEC_BLOCK_LIMIT:
                    print(f"  [cooldown] {COOLDOWN}s after {consec_blocks} "
                          f"consecutive blocks, rotating session", flush=True)
                    time.sleep(COOLDOWN)
                    browser, ctx, page = build_session(p, browser)
                    since_rotate = 0
                    consec_blocks = 0
                else:
                    time.sleep(DELAY + random.uniform(0, JITTER))
                continue

            consec_blocks = 0
            docs = extract_docs(page, url)
            for doc_url, doc_title in docs:
                ext = doc_url.lower().split("?")[0].rsplit(".", 1)[-1]
                lw.writerow([url, row.get("title", ""), row.get("section", ""),
                             row.get("lastmod", ""), doc_title, doc_url, ext])
            lf.flush()
            pw_.writerow([url, "ok", len(docs)])
            pf.flush()
            print(f"[{i}/{total}] ok docs:{len(docs):<2} {url[:66]}", flush=True)
            time.sleep(DELAY + random.uniform(0, JITTER))

        browser.close()

    lf.close()
    pf.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
