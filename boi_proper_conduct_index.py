"""
Build a local index of Proper Conduct of Banking Business Directives.

The Bank of Israel pages expose directive metadata only after the browser
renders past Radware, so this uses Playwright and the sitemap-backed
boi_publications_index.csv as the list of pages to visit.
"""
import csv
import os
import random
import re
import time
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLICATIONS_INDEX = os.path.join(HERE, "boi_publications_index.csv")
OUT = os.path.join(HERE, "boi_proper_conduct_directives.csv")

DELAY = 1.0
JITTER = 0.8
PAGE_SETTLE = 2500
MAX_ATTEMPTS = 3
ROTATE_EVERY = 12
CONSEC_BLOCK_LIMIT = 2
COOLDOWN = 20
DOC_EXT = (".pdf", ".xlsx", ".xls", ".docx", ".doc")

UAS = [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"),
]

STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = {runtime:{}};
"""

FIELDS = [
    "title",
    "url",
    "lastmod",
    "publication_date",
    "directive_number",
    "circular_number",
    "area",
    "subject",
    "file_url",
    "page_title",
    "status",
]


def is_blocked(title):
    t = (title or "").lower()
    return any(k in t for k in ("radware", "captcha", "403", "forbidden"))


def compact(value):
    return re.sub(r"\s+", " ", (value or "").replace("\u200f", "")).strip()


def load_done():
    if not os.path.exists(OUT):
        return set()
    try:
        df = pd.read_csv(OUT, dtype=str).fillna("")
    except Exception:
        return set()
    return set(df.loc[df["status"].eq("ok"), "url"])


def load_targets():
    df = pd.read_csv(PUBLICATIONS_INDEX).fillna("")
    proper = df["url"].str.contains("/proper_conduct/", case=False, na=False)
    targets = df[proper].copy()
    slugs = targets["url"].str.rstrip("/").str.split("/").str[-1]
    targets = targets[slugs != "proper_conduct"]
    return targets.drop_duplicates(subset=["url"]).reset_index(drop=True)


def warm_up(page, ctx):
    last_error = None
    for attempt in range(3):
        try:
            page.goto("https://www.boi.org.il/en/",
                      wait_until="domcontentloaded",
                      timeout=60000)
            page.wait_for_timeout(5000 + attempt * 2000)
            return len(ctx.cookies())
        except Exception as exc:
            last_error = exc
            time.sleep(5 + attempt * 5)
    raise last_error


def build_session(p, old_browser=None):
    if old_browser is not None:
        try:
            old_browser.close()
        except Exception:
            pass
    browser = p.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=random.choice(UAS),
        locale="en-US",
        viewport={"width": 1440, "height": 900},
    )
    ctx.add_init_script(STEALTH)
    page = ctx.new_page()
    cookies = warm_up(page, ctx)
    print(f"  [session] fresh browser, {cookies} cookies", flush=True)
    return browser, ctx, page


def field_from_lines(lines, label):
    prefix = f"{label.lower()}:"
    for line in lines:
        if line.lower().startswith(prefix):
            return compact(line.split(":", 1)[1])
    return ""


def first_download_url(page, source_url):
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(a => ({href: a.getAttribute('href'), text: a.innerText}))",
    )
    for link in links:
        href = link.get("href") or ""
        text = compact(link.get("text") or "")
        absolute = urljoin(source_url, href)
        path = absolute.lower().split("?", 1)[0]
        if "download" in text.lower() or path.endswith(DOC_EXT):
            return absolute
    return ""


def scrape_page(page, ctx, row):
    url = row["url"]
    title = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(PAGE_SETTLE + attempt * 1500)
            title = page.title()
            if not is_blocked(title):
                body = page.locator("body").inner_text(timeout=10000)
                lines = [compact(line) for line in body.splitlines()
                         if compact(line)]
                directive_number = field_from_lines(lines, "Instruction number")
                if not directive_number:
                    directive_number = field_from_lines(lines, "Directive number")
                return {
                    "title": compact(row.get("title", "")),
                    "url": url,
                    "lastmod": row.get("lastmod", ""),
                    "publication_date": field_from_lines(lines, "Publication date"),
                    "directive_number": directive_number,
                    "circular_number": field_from_lines(lines, "Circular number"),
                    "area": field_from_lines(lines, "Area"),
                    "subject": field_from_lines(lines, "Subject"),
                    "file_url": first_download_url(page, url),
                    "page_title": compact(title.rsplit("|", 1)[0]),
                    "status": "ok",
                }
            warm_up(page, ctx)
        except Exception as exc:
            title = f"ERR {exc}"
        time.sleep(1)

    return {
        "title": compact(row.get("title", "")),
        "url": url,
        "lastmod": row.get("lastmod", ""),
        "publication_date": "",
        "directive_number": "",
        "circular_number": "",
        "area": "",
        "subject": "",
        "file_url": "",
        "page_title": compact(title),
        "status": "blocked",
    }


def main():
    targets = load_targets()
    done = load_done()
    todo = targets[~targets["url"].isin(done)]
    print(f"Targets: {len(targets)} | already done: {len(done)} | "
          f"to process: {len(todo)}", flush=True)

    new_file = not os.path.exists(OUT)
    with open(OUT, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()

        with sync_playwright() as p:
            browser, ctx, page = build_session(p)
            since_rotate = 0
            consec_blocks = 0

            for i, (_, row) in enumerate(todo.iterrows(), 1):
                if since_rotate >= ROTATE_EVERY:
                    browser, ctx, page = build_session(p, browser)
                    since_rotate = 0

                result = scrape_page(page, ctx, row)
                writer.writerow(result)
                fh.flush()
                since_rotate += 1
                print(f"[{i}/{len(todo)}] {result['status']:<7} "
                      f"{result['directive_number'] or '-':<6} "
                      f"{result['title'][:70]}", flush=True)
                if result["status"] == "blocked":
                    consec_blocks += 1
                    if consec_blocks >= CONSEC_BLOCK_LIMIT:
                        print(f"  [cooldown] {COOLDOWN}s after "
                              f"{consec_blocks} consecutive blocks",
                              flush=True)
                        time.sleep(COOLDOWN)
                    browser, ctx, page = build_session(p, browser)
                    since_rotate = 0
                    consec_blocks = 0
                else:
                    consec_blocks = 0
                time.sleep(DELAY + random.uniform(0, JITTER))

            browser.close()

    print(f"Saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
