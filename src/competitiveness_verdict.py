"""Bucket 5: competitiveness verdict.

Estimates keyword difficulty from SERP winner authority signals.
Returns realistic_to_rank bool + 3 narrower long-tail variants (maritime-flavoured)
when the target can't realistically compete.
"""
import json
import os
import re
import time

from groq import Groq

GROQ_MODEL = "llama-3.3-70b-versatile"

MARITIME_CONTEXT = """
ZeroNorth operates in maritime/shipping SaaS. Their target audience and themes:
- Roles: ship owners, charterers, commercial operators, fleet managers, bunker traders
- Products: voyage optimisation, bunker procurement, ShipPalm, hull performance, eBDN, emissions reporting
- Compliance themes: CII, EU ETS, FuelEU Maritime, IMO MARPOL
- Vessel types: tankers, bulkers, container ships
- Geographies: major bunker hubs (Rotterdam, Singapore, Fujairah), shipping lanes
""".strip()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _composite_score(s: dict) -> float:
    if not isinstance(s, dict):
        return 0.0
    age = s.get("age_years", 0) or 0
    reddit = s.get("reddit_mentions", 0) or 0
    linkedin = s.get("linkedin_mentions", 0) or 0
    outlinks = s.get("bing_outbound_links", 0) or 0
    return min(100.0, age * 4 + min(reddit, 50) + min(linkedin, 50) * 0.5 + min(outlinks, 50))


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
                temperature=0.4,
                max_tokens=1500,
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


def _suggest_long_tail(client, keyword: str, target_intent: dict, winner_summaries: list) -> list:
    """Ask Groq for 3 narrower maritime long-tail variants of the keyword."""
    system_prompt = (
        "You suggest narrower, more rankable long-tail keyword variants for a maritime SaaS company. "
        "Use the maritime context provided to make variants concrete and audience-specific."
    )
    user_prompt = f"""ORIGINAL KEYWORD: "{keyword}"

MARITIME CONTEXT:
{MARITIME_CONTEXT}

TARGET PAGE INTENT (what the page is currently about):
{json.dumps(target_intent or {}, indent=2)[:1500]}

CURRENT SERP WINNERS (what currently ranks for the original keyword):
{json.dumps((winner_summaries or [])[:5], indent=2)[:1500]}

Suggest 3 narrower long-tail variants that:
1. Match the same underlying user intent
2. Add maritime specificity (vessel type, role, region, regulation, or product context)
3. Are realistically rankable (lower competition than the original)
4. Are searches a real maritime professional would actually type

Return ONLY this JSON schema:
{{
  "variants": [
    {{
      "keyword": "the narrower long-tail keyword",
      "why_narrower": "1 sentence explaining the narrowing dimension (e.g. 'adds bulk carrier specificity')",
      "estimated_competition": "low" | "medium"
    }},
    ...
  ]
}}"""

    try:
        text = _groq_call_with_retry(client, system_prompt, user_prompt)
        text = _strip_code_fence(text)
        parsed = json.loads(text)
        return parsed.get("variants", [])[:3]
    except Exception:
        return []


def assess_competitiveness(
    keyword: str,
    target_authority: dict,
    winner_authorities: list,
    target_intent: dict | None = None,
    winner_summaries: list | None = None,
) -> dict:
    """Main entry: difficulty estimation + realistic_to_rank + long-tail suggestions."""
    target_score = _composite_score(target_authority or {})
    valid_winners = [w for w in (winner_authorities or []) if isinstance(w, dict) and "error" not in w]
    winner_scores = sorted(_composite_score(w) for w in valid_winners) if valid_winners else []
    winner_median = winner_scores[len(winner_scores) // 2] if winner_scores else 0.0
    winner_top = max(winner_scores) if winner_scores else 0.0

    # Difficulty: weighted blend of median (60%) and top winner (40%)
    difficulty_score = round(winner_median * 0.6 + winner_top * 0.4)

    # Realistic to rank if target is within 20 points of winner median
    score_gap = winner_median - target_score
    realistic_to_rank = score_gap <= 20 or not valid_winners

    if difficulty_score >= 75:
        difficulty_label = "very_hard"
    elif difficulty_score >= 50:
        difficulty_label = "hard"
    elif difficulty_score >= 25:
        difficulty_label = "moderate"
    else:
        difficulty_label = "easy"

    gap_assessment = _gap_assessment(realistic_to_rank, difficulty_label, score_gap)

    long_tail_variants = []
    if not realistic_to_rank:
        try:
            client = Groq(api_key=os.environ["GROQ_API_KEY"])
            long_tail_variants = _suggest_long_tail(
                client, keyword, target_intent or {}, winner_summaries or []
            )
        except Exception as e:
            long_tail_variants = [{"error": str(e)}]

    rationale = _rationale(keyword, realistic_to_rank, difficulty_label, target_score, winner_median, winner_top)

    return {
        "keyword": keyword,
        "difficulty_score": difficulty_score,
        "difficulty_label": difficulty_label,
        "target_score": round(target_score, 1),
        "winner_median_score": round(winner_median, 1),
        "winner_top_score": round(winner_top, 1),
        "score_gap": round(score_gap, 1),
        "realistic_to_rank": realistic_to_rank,
        "gap_assessment": gap_assessment,
        "rationale": rationale,
        "long_tail_variants": long_tail_variants,
    }


def _gap_assessment(realistic: bool, difficulty_label: str, gap: float) -> str:
    if realistic:
        return f"Realistic — you're within {gap:.0f} points of the winner median. Authority is not blocking you."
    if difficulty_label == "very_hard":
        return f"Unrealistic on this keyword — winners are {gap:.0f} authority points ahead. Pivot to narrower variants below."
    return f"Stretch — you're {gap:.0f} points behind. Rankable in 6-12 months with concerted authority work, or pivot to long-tail."


def _rationale(keyword: str, realistic: bool, label: str, target_score: float, winner_median: float, winner_top: float) -> str:
    base = (
        f"Keyword '{keyword}' has difficulty label '{label}'. "
        f"Winners' median authority score: {winner_median:.0f}/100, top winner: {winner_top:.0f}/100. "
        f"Your score: {target_score:.0f}/100."
    )
    if realistic:
        return base + " You have a realistic shot at ranking here — focus on the other 4 buckets (intent, differentiation, distribution, content quality)."
    return base + " Authority gap is too wide for direct competition. Long-tail variants below have lower competition and clearer intent match."
