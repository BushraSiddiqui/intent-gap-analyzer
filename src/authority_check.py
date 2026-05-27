"""Bucket 2: authority signals for target vs SERP winners.

Free signals only:
- Domain age via python-whois
- Reddit + LinkedIn brand mentions via Google scrape
- Bing outbound link count via `linkfromdomain:` operator

All external calls are non-fatal — failures return zero/empty values, never raise.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import whois
except ImportError:
    whois = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def domain_age_years(domain: str) -> float:
    """Years since domain registration; 0.0 if whois unavailable, missing, or fails."""
    if not whois:
        return 0.0
    try:
        w = whois.whois(domain)
        created = w.creation_date
        if isinstance(created, list):
            created = created[0] if created else None
        if not created:
            return 0.0
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                return 0.0
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return round((now - created).days / 365.25, 1)
    except Exception:
        return 0.0


def _google_results_count(query: str) -> int:
    """Approximate result count from a Google search. 0 on any failure."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=20"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return 0
        soup = BeautifulSoup(resp.text, "html.parser")
        stats = soup.find("div", id="result-stats") or soup.find("div", id="resultStats")
        if stats:
            text = stats.get_text()
            m = re.search(r"([\d,]+)\s+result", text)
            if m:
                return int(m.group(1).replace(",", ""))
        return len(soup.select("div.g, div.MjjYud"))
    except Exception:
        return 0


def google_mention_count(domain: str, site: str) -> int:
    """Number of Google results for `site:<site> "<domain>"`."""
    return _google_results_count(f'site:{site} "{domain}"')


def bing_linkfromdomain(domain: str) -> int:
    """Approximate outbound-link count using Bing's linkfromdomain: operator."""
    url = f"https://www.bing.com/search?q={quote_plus('linkfromdomain:' + domain)}&count=50"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return 0
        soup = BeautifulSoup(resp.text, "html.parser")
        return len(soup.select("li.b_algo"))
    except Exception:
        return 0


def check_authority(url: str) -> dict:
    """Run all free authority signals for one URL."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = parsed.netloc.lower().replace("www.", "") if parsed.netloc else url.lower()
    return {
        "url": url,
        "domain": domain,
        "age_years": domain_age_years(domain),
        "reddit_mentions": google_mention_count(domain, "reddit.com"),
        "linkedin_mentions": google_mention_count(domain, "linkedin.com"),
        "bing_outbound_links": bing_linkfromdomain(domain),
    }


def _composite_score(s: dict) -> float:
    age = s.get("age_years", 0) or 0
    reddit = s.get("reddit_mentions", 0) or 0
    linkedin = s.get("linkedin_mentions", 0) or 0
    outlinks = s.get("bing_outbound_links", 0) or 0
    return min(100.0, age * 4 + min(reddit, 50) + min(linkedin, 50) * 0.5 + min(outlinks, 50))


def compute_authority_gap(target_signals: dict, winner_signals: list) -> dict:
    """Classify the gap: narrow / moderate / wide. Returns dict with gap + numeric details."""
    target_score = _composite_score(target_signals)
    valid_winners = [w for w in (winner_signals or []) if isinstance(w, dict) and "error" not in w]
    if not valid_winners:
        return {
            "authority_gap": "unknown",
            "target_score": round(target_score, 1),
            "winner_median_score": None,
            "raw_gap": None,
        }
    winner_scores = sorted(_composite_score(w) for w in valid_winners)
    median = winner_scores[len(winner_scores) // 2]
    raw_gap = median - target_score
    if raw_gap < 15:
        gap = "narrow"
    elif raw_gap < 40:
        gap = "moderate"
    else:
        gap = "wide"
    return {
        "authority_gap": gap,
        "target_score": round(target_score, 1),
        "winner_median_score": round(median, 1),
        "raw_gap": round(raw_gap, 1),
    }


def _interpret(gap_result: dict, target: dict, winners: list) -> str:
    gap = gap_result.get("authority_gap")
    if gap == "narrow":
        return "Your domain authority is roughly on par with the top SERP results. Authority is not the bottleneck here — focus on content quality and differentiation."
    if gap == "moderate":
        return "Your domain has moderately weaker authority than the top SERP winners. Closing this gap means earned mentions on Reddit/LinkedIn/industry sites and time. Pursuable but slow."
    if gap == "wide":
        winner_ages = [w.get("age_years", 0) for w in winners if isinstance(w, dict) and "age_years" in w]
        avg_winner_age = sum(winner_ages) / len(winner_ages) if winner_ages else 0
        return (
            f"Your domain is significantly behind the top SERP winners (avg winner age: "
            f"{avg_winner_age:.1f}y vs yours: {target.get('age_years', 0)}y). For this keyword, "
            "authority is a real blocker — consider going after narrower long-tail variants instead."
        )
    return "Could not assess authority gap — insufficient signals from SERP winners."


def run_authority_bucket(target_url: str, serp_top_results: list, sleep_between: float = 2.0) -> dict:
    """Main entry: signals for target + top 3 winners + gap classification + interpretation."""
    target_signals = check_authority(target_url)
    time.sleep(sleep_between)

    winners = []
    for r in (serp_top_results or [])[:3]:
        if not isinstance(r, dict) or not r.get("url"):
            continue
        try:
            winners.append(check_authority(r["url"]))
        except Exception as e:
            winners.append({"url": r.get("url"), "error": str(e)})
        time.sleep(sleep_between)

    gap_result = compute_authority_gap(target_signals, winners)
    interpretation = _interpret(gap_result, target_signals, winners)

    return {
        "target": target_signals,
        "winners": winners,
        **gap_result,
        "interpretation": interpretation,
    }
