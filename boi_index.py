"""
Build an index of Bank of Israel English publication pages.

Why not crawl? www.boi.org.il sits behind Radware Bot Manager, which serves a
JavaScript challenge page to plain HTTP clients (requests/urllib). So a normal
crawler sees an app-shell with zero links. The sitemaps, however, are served
without the challenge, so we use /en/sitemap.xml as the source of truth.

Note: PDF files are NOT listed in the sitemap; they are only linked from the
publication pages (which are behind Radware). Extracting PDF links would require
a real browser (Playwright/Selenium). This script indexes the pages.
"""
import requests
import xml.etree.ElementTree as ET
import pandas as pd

SITEMAP = "https://www.boi.org.il/en/sitemap.xml"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Sections that correspond to the publications you care about.
SECTIONS = (
    "/en/communication-and-publications/",
    "/en/economic-roles/",
)


def title_from_url(url):
    """Derive a readable title from the last non-empty URL segment."""
    slug = [s for s in url.rstrip("/").split("/") if s][-1]
    return slug.replace("-", " ").replace("_", " ").strip().title()


def main():
    r = requests.get(SITEMAP, headers=HEADERS, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    rows = []
    for u in root.findall("s:url", NS):
        loc = u.find("s:loc", NS).text
        lm = u.find("s:lastmod", NS)
        lastmod = lm.text if lm is not None else ""
        if any(sec in loc.lower() for sec in SECTIONS):
            section = loc.split("/en/")[1].split("/")[0]
            rows.append({
                "section": section,
                "title": title_from_url(loc),
                "url": loc,
                "lastmod": lastmod,
            })

    df = pd.DataFrame(rows).drop_duplicates(subset=["url"])
    df = df.sort_values(["section", "lastmod"], ascending=[True, False])
    df.to_csv("boi_publications_index.csv", index=False)

    print(f"Total items: {len(df)}")
    print(df["section"].value_counts().to_string())
    print("Saved to boi_publications_index.csv")


if __name__ == "__main__":
    main()
