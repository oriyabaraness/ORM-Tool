import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import time

START_URLS = [
    "https://www.boi.org.il/en/communication-and-publications/regular-publications/",
    "https://www.boi.org.il/en/economic-roles/research-and-publications/",
]

DOMAIN = "www.boi.org.il"
MAX_PAGES = 500
DELAY = 0.5

visited = set()
to_visit = list(START_URLS)
results = []

headers = {
    "User-Agent": "BOI-publications-research-crawler/1.0"
}

def is_boi_url(url):
    parsed = urlparse(url)
    return parsed.netloc in ["www.boi.org.il", "boi.org.il"]

def looks_like_publication(url, text):
    keywords = [
        "publication", "publications", "research", "report",
        "financial-stability", "monetary-policy", "annual-report",
        "banking-system", "statistical", "paper", "forecast"
    ]
    value = (url + " " + text).lower()
    return any(k in value for k in keywords)

def fetch(url):
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            return r
    except Exception:
        return None
    return None

while to_visit and len(visited) < MAX_PAGES:
    url = to_visit.pop(0)

    if url in visited:
        continue

    visited.add(url)
    response = fetch(url)

    if not response:
        continue

    content_type = response.headers.get("content-type", "").lower()

    if "pdf" in content_type or url.lower().endswith(".pdf"):
        results.append({
            "type": "pdf",
            "title": "",
            "url": url,
            "source_page": ""
        })
        continue

    soup = BeautifulSoup(response.text, "html.parser")
    page_title = soup.get_text(" ", strip=True)[:150]

    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"]).split("#")[0]
        text = a.get_text(" ", strip=True)

        if not is_boi_url(link):
            continue

        if link.lower().endswith(".pdf"):
            results.append({
                "type": "pdf",
                "title": text,
                "url": link,
                "source_page": url
            })

        elif looks_like_publication(link, text):
            results.append({
                "type": "page",
                "title": text or page_title,
                "url": link,
                "source_page": url
            })

            if link not in visited and link not in to_visit:
                to_visit.append(link)

    time.sleep(DELAY)

df = pd.DataFrame(results).drop_duplicates(subset=["url"])
df.to_csv("boi_publications_index.csv", index=False)

print(f"Visited pages: {len(visited)}")
print(f"Found items: {len(df)}")
print("Saved to boi_publications_index.csv")
