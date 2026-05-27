"""Combined 5-bucket diagnosis orchestrator.

Public entry points:
- run_full_diagnosis(url, keywords): orchestrates all 5 buckets and ranks fixes
- analyze_gaps(...): legacy entry point preserved for streamlit_app.py until Phase 10
- rank_fixes_by_impact(...): consolidates bucket outputs into top 5 ranked fixes
"""
import json
import os
import re
import time
from urllib.parse import urlparse

from groq import Groq

from src.intent_extractor import extract_intent, compare_intent_to_serp
from src.serp_crawler import crawl_serps
from src.llm_crawler import crawl_llms
from src.authority_check import (
    check_authority,
    compute_authority_gap,
    run_authority_bucket,
)
from src.differentiation_scorer import score_differentiation
from src.distribution_audit import audit_distribution
from src.competitiveness_verdict import assess_competitiveness

GROQ_MODEL = "llama-3.3-70b-versatile"


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
                temperature=0.2,
                max_tokens=4096,
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


def _detect_mentions(target_url: str, llm_data: dict) -> dict:
    """Check if the target domain or brand name appears in each LLM answer."""
    domain = urlparse(target_url).netloc.lower().replace("www.", "")
    brand = domain.split(".")[0] if "." in domain else domain
    short_brand = brand if len(brand) >= 4 else None

    mentions = {}
    for kw, llms in (llm_data or {}).items():
        mentions[kw] = {}
        for llm_name, result in (llms or {}).items():
            answer = ((result or {}).get("answer") or "").lower()
            mentioned = bool(answer) and (domain in answer or (short_brand and short_brand in answer))
            mentions[kw][llm_name] = mentioned
    return mentions


def _best_serp_results(engines: dict) -> list:
    """Pick the first non-empty list of SERP results (bing > duckduckgo > google)."""
    for key in ("bing", "duckduckgo", "google"):
        results = engines.get(key)
        if isinstance(results, list) and results:
            return results
    return []


def _compute_health_score(per_keyword: dict, differentiation: dict, distribution: dict):
    n = max(1, len(per_keyword))

    intent_avg = sum(
        (pk.get("bucket1_intent") or {}).get("match_score", 0) or 0
        for pk in per_keyword.values()
    ) / n

    auth_scores = []
    for pk in per_keyword.values():
        gap = (pk.get("bucket2_authority") or {}).get("raw_gap")
        gap = 0 if gap is None else max(0, gap)
        auth_scores.append(max(0, 100 - gap * 2.5))
    auth_avg = sum(auth_scores) / n

    diff_score = (differentiation or {}).get("differentiation_score", 0) or 0
    dist_score = (distribution or {}).get("distribution_score", 0) or 0

    realistic_count = sum(
        1 for pk in per_keyword.values()
        if (pk.get("bucket5_competitiveness") or {}).get("realistic_to_rank")
    )
    compet_score = round((realistic_count / n) * 100)

    weights = {"intent": 0.25, "authority": 0.20, "differentiation": 0.25, "distribution": 0.15, "competitiveness": 0.15}
    health = (
        intent_avg * weights["intent"]
        + auth_avg * weights["authority"]
        + diff_score * weights["differentiation"]
        + dist_score * weights["distribution"]
        + compet_score * weights["competitiveness"]
    )

    if health >= 75:
        verdict = "Strong — only minor optimisations needed."
    elif health >= 55:
        verdict = "Mixed — several buckets need attention."
    elif health >= 35:
        verdict = "Weak — multiple buckets failing. Focus the top 5 fixes."
    else:
        verdict = "Critical — content unlikely to rank without major rework or keyword pivot."

    bucket_scores = {
        "intent": round(intent_avg),
        "authority": round(auth_avg),
        "differentiation": round(diff_score),
        "distribution": round(dist_score),
        "competitiveness": round(compet_score),
    }
    return round(health), verdict, bucket_scores


def rank_fixes_by_impact(
    url: str,
    target_intent: dict,
    per_keyword: dict,
    differentiation: dict,
    distribution: dict,
    mentions: dict,
) -> list:
    """Ask Groq to rank the top 5 fixes by impact across all buckets."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    summary = {
        "url": url,
        "intent_per_keyword": {
            kw: {
                "match_score": (pk.get("bucket1_intent") or {}).get("match_score"),
                "verdict": (pk.get("bucket1_intent") or {}).get("verdict"),
                "rewrite_instruction": (pk.get("bucket1_intent") or {}).get("rewrite_instruction"),
            }
            for kw, pk in per_keyword.items()
        },
        "authority_per_keyword": {
            kw: {
                "authority_gap": (pk.get("bucket2_authority") or {}).get("authority_gap"),
                "score_gap": (pk.get("bucket2_authority") or {}).get("raw_gap"),
                "interpretation": (pk.get("bucket2_authority") or {}).get("interpretation"),
            }
            for kw, pk in per_keyword.items()
        },
        "differentiation": {
            "score": (differentiation or {}).get("differentiation_score"),
            "verdict": (differentiation or {}).get("verdict"),
            "maritime_suggestions": (differentiation or {}).get("maritime_suggestions", []),
        },
        "distribution": {
            "score": (distribution or {}).get("distribution_score"),
            "channels_missing": (distribution or {}).get("channels_missing", []),
            "suggestions": (distribution or {}).get("suggestions", [])[:5],
        },
        "competitiveness_per_keyword": {
            kw: {
                "difficulty_label": (pk.get("bucket5_competitiveness") or {}).get("difficulty_label"),
                "realistic_to_rank": (pk.get("bucket5_competitiveness") or {}).get("realistic_to_rank"),
                "long_tail_variants": (pk.get("bucket5_competitiveness") or {}).get("long_tail_variants", []),
            }
            for kw, pk in per_keyword.items()
        },
        "llm_mentions": mentions,
    }

    system_prompt = (
        "You are a senior SEO + content strategist for ZeroNorth (maritime SaaS). "
        "Rank the top 5 fixes by impact. Be ruthless: only the highest-leverage actions. "
        "Each fix must be atomic, concrete, and reference specific bucket evidence. "
        "Suggest fixes in the maritime context (vessel performance, voyage data, bunker prices, emissions) where relevant."
    )

    user_prompt = f"""Given this full 5-bucket diagnosis, return the top 5 fixes ranked by impact.

DIAGNOSIS:
{json.dumps(summary, indent=2)[:7000]}

RULES:
1. Each fix is a concrete, atomic action (not "improve content").
2. effort_hours = realistic estimate (1, 2, 4, 8, 16, 40).
3. expected_impact = 1-10 (10 = could meaningfully move ranking position).
4. why_this_matters = 1-2 sentences citing specific bucket evidence.
5. Each fix tags which bucket it addresses (intent|authority|differentiation|distribution|competitiveness).
6. Order strictly by expected_impact descending.

Return ONLY this JSON schema:
{{
  "ranked_fixes": [
    {{
      "rank": 1,
      "action": "Specific atomic action with exact what/where",
      "bucket": "intent|authority|differentiation|distribution|competitiveness",
      "effort_hours": int,
      "expected_impact": 1-10,
      "why_this_matters": "1-2 sentence rationale citing bucket evidence"
    }}
  ]
}}"""

    try:
        text = _groq_call_with_retry(client, system_prompt, user_prompt)
        text = _strip_code_fence(text)
        parsed = json.loads(text)
        return parsed.get("ranked_fixes", [])[:5]
    except Exception as e:
        return [{"error": str(e)}]


def _run_buckets_with_data(target_url: str, target_intent: dict, keywords: list, serp_data: dict, llm_data: dict) -> dict:
    """Shared core: given crawled data, run all 5 buckets and build diagnosis dict."""
    diagnosis = {
        "url": target_url,
        "keywords": keywords,
        "target_intent": target_intent,
        "serp_data": serp_data,
        "llm_data": llm_data,
        "errors": [],
    }

    try:
        distribution = audit_distribution(target_url)
    except Exception as e:
        distribution = {"error": str(e), "distribution_score": 0}
        diagnosis["errors"].append({"stage": "audit_distribution", "error": str(e)})

    per_keyword = {}
    target_authority_cache = None
    bucket3_differentiation = None

    for i, kw in enumerate(keywords):
        engines = (serp_data or {}).get(kw, {}) or {}
        results = _best_serp_results(engines)

        try:
            bucket1 = compare_intent_to_serp(target_intent, results)
        except Exception as e:
            bucket1 = {"match_score": 0, "verdict": "error", "error": str(e)}

        try:
            if target_authority_cache is None:
                bucket2 = run_authority_bucket(target_url, results)
                target_authority_cache = bucket2.get("target")
            else:
                winners_auth = []
                for r in results[:3]:
                    if isinstance(r, dict) and r.get("url"):
                        try:
                            winners_auth.append(check_authority(r["url"]))
                        except Exception as e:
                            winners_auth.append({"url": r["url"], "error": str(e)})
                        time.sleep(2)
                gap_result = compute_authority_gap(target_authority_cache, winners_auth)
                bucket2 = {
                    "target": target_authority_cache,
                    "winners": winners_auth,
                    **gap_result,
                    "interpretation": "Re-using target authority (computed once for first keyword).",
                }
        except Exception as e:
            bucket2 = {"authority_gap": "unknown", "error": str(e)}

        try:
            bucket5 = assess_competitiveness(
                kw,
                target_authority_cache or {},
                bucket2.get("winners", []),
                target_intent.get("intent", {}),
                results,
            )
        except Exception as e:
            bucket5 = {"realistic_to_rank": True, "error": str(e)}

        if i == 0:
            try:
                bucket3_differentiation = score_differentiation(
                    target_intent.get("page", {}),
                    target_intent.get("intent", {}),
                    results,
                )
            except Exception as e:
                bucket3_differentiation = {"differentiation_score": 0, "error": str(e)}

        per_keyword[kw] = {
            "bucket1_intent": bucket1,
            "bucket2_authority": bucket2,
            "bucket5_competitiveness": bucket5,
            "top_serp_urls": [r.get("url") for r in results[:5] if isinstance(r, dict)],
        }

    diagnosis["per_keyword"] = per_keyword
    diagnosis["differentiation"] = bucket3_differentiation or {"differentiation_score": 0}
    diagnosis["distribution"] = distribution

    mentions = _detect_mentions(target_url, llm_data)
    diagnosis["target_cited_in_llms"] = mentions

    health_score, verdict, bucket_scores = _compute_health_score(
        per_keyword, diagnosis["differentiation"], diagnosis["distribution"]
    )
    diagnosis["health_score"] = health_score
    diagnosis["verdict"] = verdict
    diagnosis["bucket_scores"] = bucket_scores

    try:
        diagnosis["ranked_fixes"] = rank_fixes_by_impact(
            target_url, target_intent, per_keyword,
            diagnosis["differentiation"], diagnosis["distribution"], mentions,
        )
    except Exception as e:
        diagnosis["ranked_fixes"] = []
        diagnosis["errors"].append({"stage": "rank_fixes", "error": str(e)})

    return diagnosis


def run_full_diagnosis(url: str, keywords: list) -> dict:
    """Main entry: orchestrate all 5 buckets, compute health, rank fixes.

    Internally fetches target intent + SERPs + LLM data, then runs buckets.
    """
    try:
        target_intent = extract_intent(url)
    except Exception as e:
        target_intent = {"page": {}, "intent": {}, "error": str(e)}

    try:
        serp_data = crawl_serps(keywords)
    except Exception:
        serp_data = {}

    try:
        llm_data = crawl_llms(keywords)
    except Exception:
        llm_data = {}

    return _run_buckets_with_data(url, target_intent, keywords, serp_data, llm_data)


# ---------------------------------------------------------------------------
# Legacy entry point for streamlit_app.py until Phase 10 migrates it.
# Re-uses already-crawled SERP/LLM data; runs the same 5-bucket pipeline.
# ---------------------------------------------------------------------------
def analyze_gaps(target_url, target_intent, keywords, serp_data, llm_data) -> dict:
    diagnosis = _run_buckets_with_data(target_url, target_intent, keywords, serp_data, llm_data)

    # Legacy compatibility: derive top_recommendations from ranked_fixes
    ranked = diagnosis.get("ranked_fixes") or []
    diagnosis["top_recommendations"] = [
        {
            "action": f.get("action", ""),
            "rationale": f.get("why_this_matters", ""),
            "priority": (
                "P0" if (f.get("expected_impact", 0) or 0) >= 8
                else "P1" if (f.get("expected_impact", 0) or 0) >= 5
                else "P2"
            ),
            "channel": f.get("bucket", ""),
            "estimated_impact": (
                "high" if (f.get("expected_impact", 0) or 0) >= 8
                else "medium" if (f.get("expected_impact", 0) or 0) >= 5
                else "low"
            ),
        }
        for f in ranked
        if isinstance(f, dict) and "error" not in f
    ]
    return diagnosis
