"""Bucket 3: differentiation scoring against SERP winners.

7-point rubric (each scored 0–10):
1. Original data
2. Screenshots / visuals
3. Customer examples / case studies
4. Contrarian opinions / hot takes
5. Frameworks / mental models
6. Firsthand experience signals
7. Proprietary research / unique methodology

Plus a similarity-to-winners score (lower = more differentiated).
Suggestions are maritime-flavoured for ZeroNorth's data assets (voyage data,
bunker prices, vessel performance, emissions).
"""
import json
import os
import re
import time

from groq import Groq

GROQ_MODEL = "llama-3.3-70b-versatile"

ZERONORTH_CONTEXT = """
ZeroNorth is a maritime SaaS platform with these proprietary data assets:
- Voyage data (routes, ETAs, weather impact, port operations)
- Bunker price feed (real-time spot prices, transaction-backed methodology)
- Vessel performance data (fuel consumption, hull condition, engine telemetry)
- Emissions data (CO2, CII, EU ETS, FuelEU Maritime compliance)
- Customer case studies (Maersk Tankers, Cargill, X-Press Feeders, Costamare, etc.)
- Industry partnerships (Veson, Spire Maritime, Monjasa, DNV, RightShip)
""".strip()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _groq_call_with_retry(client, system: str, user: str, max_retries: int = 3) -> str:
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=3000,
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


def score_differentiation(target_page: dict, target_intent: dict, serp_top_results: list) -> dict:
    """Bucket 3 main entry. Returns rubric scores + similarity + maritime suggestions."""
    if not target_page:
        return _empty_result("no target page data")

    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    target_summary = {
        "title": target_page.get("title", ""),
        "h1": target_page.get("h1", []),
        "h2": target_page.get("h2", [])[:15],
        "body_excerpt": (target_page.get("body_excerpt") or "")[:3500],
        "intent": target_intent or {},
    }
    winners_summary = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("snippet") or "")[:200],
        }
        for r in (serp_top_results or [])[:5]
    ]

    system_prompt = (
        "You are a senior content strategist evaluating whether a page is genuinely differentiated "
        "or just another generic article on the same topic. Be honest and harsh — if it's generic, "
        "say so. Suggestions must leverage the maritime context provided."
    )

    user_prompt = f"""Evaluate the target page against the SERP winners using a 7-point differentiation rubric.

MARITIME CONTEXT (ZeroNorth's data assets — use these in suggestions):
{ZERONORTH_CONTEXT}

TARGET PAGE:
{json.dumps(target_summary, indent=2)[:4000]}

SERP WINNERS (top 5):
{json.dumps(winners_summary, indent=2)[:2500]}

SCORE EACH DIMENSION 0-10 with a 1-sentence evidence note:
1. original_data — Does the page show first-party numbers, charts, or research?
2. screenshots — Are there product screenshots, UI captures, or annotated visuals?
3. customer_examples — Are real customers/case studies named?
4. contrarian_opinions — Does it take a non-obvious or against-the-grain stance?
5. frameworks — Does it offer a named methodology, model, or framework?
6. firsthand_experience — Is the author's perspective evident (vs. generic SEO copy)?
7. proprietary_research — Does it cite unique studies, surveys, or analyses only this company has?

SIMILARITY: how similar is the target's structure and angle to the SERP winners (0-100, higher = more identical/copycat)?

MARITIME SUGGESTIONS: 3-5 specific actions tied to ZeroNorth's data assets. Each suggestion must name a specific asset (e.g. "Embed a chart of bunker price spreads from Bunker Pricer for Rotterdam vs Singapore over Q1") not generic advice ("add more data").

Return ONLY this JSON schema:
{{
  "rubric": {{
    "original_data": {{"score": 0-10, "evidence": "..."}},
    "screenshots": {{"score": 0-10, "evidence": "..."}},
    "customer_examples": {{"score": 0-10, "evidence": "..."}},
    "contrarian_opinions": {{"score": 0-10, "evidence": "..."}},
    "frameworks": {{"score": 0-10, "evidence": "..."}},
    "firsthand_experience": {{"score": 0-10, "evidence": "..."}},
    "proprietary_research": {{"score": 0-10, "evidence": "..."}}
  }},
  "rubric_score": 0-100 integer (sum of all 7 scores * 100/70),
  "similarity_to_winners": 0-100 integer,
  "differentiation_score": 0-100 integer (rubric_score weighted higher than 100-similarity),
  "verdict": "highly_differentiated" | "moderately_differentiated" | "generic",
  "maritime_suggestions": [
    "Specific action referencing a named ZeroNorth data asset",
    "..."
  ]
}}"""

    try:
        text = _groq_call_with_retry(client, system_prompt, user_prompt)
        text = _strip_code_fence(text)
        result = json.loads(text)
        if "rubric" in result and isinstance(result["rubric"], dict):
            scores = [v.get("score", 0) for v in result["rubric"].values() if isinstance(v, dict)]
            if scores and "rubric_score" not in result:
                result["rubric_score"] = round(sum(scores) * 100 / (10 * len(scores)))
        return result
    except json.JSONDecodeError as e:
        return _empty_result(f"json parse error: {e}")
    except Exception as e:
        return _empty_result(str(e))


def _empty_result(reason: str) -> dict:
    return {
        "rubric": {},
        "rubric_score": 0,
        "similarity_to_winners": 0,
        "differentiation_score": 0,
        "verdict": "unknown",
        "maritime_suggestions": [],
        "error": reason,
    }
