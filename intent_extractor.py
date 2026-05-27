import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from groq import Groq

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

GROQ_MODEL = "llama-3.3-70b-versatile"


def fetch_page(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = ""
    m = soup.find("meta", attrs={"name": "description"})
    if m and m.get("content"):
        meta_desc = m["content"].strip()

    h1 = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2 = [h.get_text(strip=True) for h in soup.find_all("h2")]
    h3 = [h.get_text(strip=True) for h in soup.find_all("h3")]

    schema_snippets = []
    for s in soup.find_all("script", type="application/ld+json"):
        if s.string and '"@type"' in s.string:
            schema_snippets.append(s.string[:300])

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.get_text(" ", strip=True)[:8000]

    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "schema_snippets": schema_snippets,
        "body_excerpt": body,
    }


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _groq_call_with_retry(client, prompt: str, max_retries: int = 3) -> str:
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise analyst. Always respond with valid JSON only, no prose."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=2048,
            )
            return resp.choices[0].message.content
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if "429" in str(e) or "rate" in msg or "quota" in msg:
                time.sleep(20 * (attempt + 1))
                continue
            raise
    raise last_error


def classify_intent(page: dict) -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = f"""Analyze this web page and return a JSON object with these keys:
- primary_topic: short phrase
- intent_type: one of [informational, commercial, transactional, navigational]
- target_audience: short phrase
- key_entities: list of named entities the page covers
- content_angles: list of the main angles or sub-topics the page covers
- depth_signals: object with {{word_count_estimate: int, has_examples: bool, has_data: bool, has_visuals_implied: bool}}

Page:
Title: {page['title']}
Meta: {page['meta_description']}
H1: {page['h1']}
H2s: {page['h2']}
H3s: {page['h3']}
Body excerpt: {page['body_excerpt']}
"""
    text = _groq_call_with_retry(client, prompt)
    text = _strip_code_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text, "error": "could not parse JSON"}


def extract_intent(url: str) -> dict:
    page = fetch_page(url)
    intent = classify_intent(page)
    return {"page": page, "intent": intent}
