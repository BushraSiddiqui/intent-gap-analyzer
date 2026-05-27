"""Bucket 4: distribution audit.

Counts mentions of the target URL across distribution channels via free Google scrapes.
Channels: LinkedIn, Reddit, Substack, Beehiiv, YouTube, gCaptain, Maritime Executive.
Outputs a distribution_score, channels_hit, channels_missing, and channel-specific suggestions.
All scrape failures return 0 (non-fatal).
"""
import re
import time
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Channels to audit. Each entry: (label, site_for_query, suggestion_template, channel_category)
CHANNELS = [
    ("LinkedIn", "linkedin.com", "Share this URL in a LinkedIn post from your CEO/CMO account, and have ~3 employees comment-amplify it.", "social"),
    ("Reddit", "reddit.com", "Find 2-3 maritime/logistics subreddits (r/maritime, r/shipping, r/MaritimeIndustry) and post a discussion thread, NOT a link drop.", "community"),
    ("Substack", "substack.com", "Pitch the piece to a maritime/B2B SaaS Substack newsletter (Splash247 newsletter, Maritime CEO, or maritime-focused operators on Substack).", "newsletter"),
    ("Beehiiv", "beehiiv.com", "Identify maritime newsletters on Beehiiv and offer a quoted excerpt + co-promotion swap.", "newsletter"),
    ("YouTube", "youtube.com", "Turn the page into a 3-5 min explainer video, embed it on the page, and cross-post on LinkedIn.", "video"),
    ("gCaptain", "gcaptain.com", "Pitch a contributed article or commentary to gCaptain referencing the data from this page.", "maritime_press"),
    ("Maritime Executive", "maritime-executive.com", "Submit as a thought leadership piece to The Maritime Executive's opinion section.", "maritime_press"),
]


def _google_results_count(query: str) -> int:
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


def _mentions_on_site(url: str, site: str) -> int:
    """Count Google results for `site:<site> "<url>"` and a domain-only fallback."""
    domain = urlparse(url if "://" in url else f"https://{url}").netloc.lower().replace("www.", "")
    primary = _google_results_count(f'site:{site} "{url}"')
    if primary > 0:
        return primary
    return _google_results_count(f'site:{site} "{domain}"')


def audit_distribution(url: str, sleep_between: float = 2.0) -> dict:
    """Main entry: run a Google scrape per channel, build score + suggestions."""
    channels_data = []
    for label, site, suggestion, category in CHANNELS:
        mentions = _mentions_on_site(url, site)
        channels_data.append({
            "channel": label,
            "category": category,
            "mentions": mentions,
            "hit": mentions > 0,
            "suggestion": suggestion if mentions == 0 else None,
        })
        time.sleep(sleep_between)

    total = len(channels_data)
    hits = sum(1 for c in channels_data if c["hit"])
    score = round((hits / total) * 100) if total else 0

    channels_hit = [c["channel"] for c in channels_data if c["hit"]]
    channels_missing = [c["channel"] for c in channels_data if not c["hit"]]
    suggestions = [
        {"channel": c["channel"], "category": c["category"], "action": c["suggestion"]}
        for c in channels_data if c["suggestion"]
    ]

    verdict = _verdict(score)
    interpretation = _interpret(score, channels_hit, channels_missing)

    return {
        "distribution_score": score,
        "channels_audited": channels_data,
        "channels_hit": channels_hit,
        "channels_missing": channels_missing,
        "suggestions": suggestions,
        "verdict": verdict,
        "interpretation": interpretation,
    }


def _verdict(score: int) -> str:
    if score >= 70:
        return "well_distributed"
    if score >= 40:
        return "moderately_distributed"
    return "underdistributed"


def _interpret(score: int, hit: list, missing: list) -> str:
    if score >= 70:
        return f"Strong distribution footprint across {len(hit)} channels. Focus on amplifying existing presence on {', '.join(hit[:3])}."
    if score >= 40:
        return (
            f"Moderate distribution — you're present on {', '.join(hit) if hit else 'few channels'} but missing "
            f"{', '.join(missing[:3])}. SEO rankings reward distribution diversity; close these gaps."
        )
    return (
        f"Poor distribution — only {len(hit)} of 7 channels show mentions. Even great content "
        "underperforms without distribution. Prioritise LinkedIn and one maritime trade publication "
        "(gCaptain or Maritime Executive) as quick wins."
    )
