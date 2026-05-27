import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from src.cache import ttl_cache
from src.http_utils import http_get

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@ttl_cache(ttl_seconds=3600)
def bing_search(query: str, num: int = 10) -> list:
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num}"
    resp = http_get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for li in soup.select("li.b_algo"):
        a = li.find("a")
        h2 = li.find("h2")
        snippet_el = li.select_one(".b_caption p")
        if not a or not h2:
            continue
        results.append({
            "title": h2.get_text(strip=True),
            "url": a.get("href"),
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })
    return results[:num]


@ttl_cache(ttl_seconds=3600)
def duckduckgo_search(query: str, num: int = 10) -> list:
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=num))
    return [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
        for r in results
    ]


@ttl_cache(ttl_seconds=3600)
def google_search(query: str, num: int = 10) -> list:
    # googlesearch-python scrapes Google HTML — rate-limited, may break.
    from googlesearch import search
    results = []
    for r in search(query, num_results=num, advanced=True, sleep_interval=2):
        results.append({
            "title": getattr(r, "title", ""),
            "url": getattr(r, "url", ""),
            "snippet": getattr(r, "description", ""),
        })
    return results


def crawl_serps(keywords: list) -> dict:
    data = {}
    for kw in keywords:
        print(f"  - {kw}")
        engines = {}

        try:
            engines["bing"] = bing_search(kw)
        except Exception as e:
            engines["bing"] = {"error": str(e)}
        time.sleep(2)

        try:
            engines["duckduckgo"] = duckduckgo_search(kw)
        except Exception as e:
            engines["duckduckgo"] = {"error": str(e)}
        time.sleep(2)

        try:
            engines["google"] = google_search(kw)
        except Exception as e:
            engines["google"] = {"error": str(e)}
        time.sleep(5)

        data[kw] = engines
    return data
