import json
import os
import re
import time
from urllib.parse import urlparse

from groq import Groq

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
    """For each keyword/LLM, check if target's domain or brand name appears in the LLM answer text."""
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


def _compact_serp(serp_data: dict, per_engine_limit: int = 5) -> dict:
    """Keep top N results per engine; drop extra fields."""
    compact = {}
    for kw, engines in (serp_data or {}).items():
        compact[kw] = {}
        for engine, results in (engines or {}).items():
            if isinstance(results, list):
                compact[kw][engine] = [
                    {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("snippet") or "")[:200]}
                    for r in results[:per_engine_limit]
                ]
            else:
                compact[kw][engine] = results
    return compact


def _compact_llm(llm_data: dict, answer_chars: int = 600) -> dict:
    compact = {}
    for kw, llms in (llm_data or {}).items():
        compact[kw] = {}
        for llm_name, result in (llms or {}).items():
            if isinstance(result, dict):
                compact[kw][llm_name] = {
                    "answer_excerpt": (result.get("answer") or "")[:answer_chars] if result.get("answer") else None,
                    "citations": result.get("citations", []),
                    "error": result.get("error"),
                }
            else:
                compact[kw][llm_name] = result
    return compact


def analyze_gaps(target_url, target_intent, keywords, serp_data, llm_data) -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    mentions = _detect_mentions(target_url, llm_data)
    serp_compact = _compact_serp(serp_data)
    llm_compact = _compact_llm(llm_data)

    target_h1 = target_intent.get("page", {}).get("h1", [])
    target_h2 = target_intent.get("page", {}).get("h2", [])
    target_h3 = target_intent.get("page", {}).get("h3", [])
    target_word_count = len((target_intent.get("page", {}).get("body_excerpt") or "").split())
    target_schema = bool(target_intent.get("page", {}).get("schema_snippets"))

    system_prompt = """You are a senior SEO + GEO analyst. You produce evidence-backed recommendations that reference specific competitor URLs and propose concrete fixes. You never give generic advice like 'improve content quality.' Every gap and recommendation must name a specific competitor domain and describe a specific action."""

    user_prompt = f"""Analyze the target page against SERP winners and LLM answers. Be specific. Reference competitor URLs by name.

TARGET URL: {target_url}
TARGET DOMAIN: {urlparse(target_url).netloc}
TARGET WORD COUNT (excerpt): ~{target_word_count}
TARGET HAS SCHEMA: {target_schema}
TARGET INTENT: {json.dumps(target_intent.get('intent', {}), indent=2)}
TARGET H1: {target_h1}
TARGET H2s: {target_h2}
TARGET H3s: {target_h3[:10]}

KEYWORDS ANALYZED: {keywords}

PRE-COMPUTED MENTIONS (target domain found in LLM answer text):
{json.dumps(mentions, indent=2)}

SERP DATA (top 5 per engine, with title/url/snippet):
{json.dumps(serp_compact, indent=2)[:6000]}

LLM ANSWERS (first 600 chars of each LLM's answer):
{json.dumps(llm_compact, indent=2)[:4000]}

RULES YOU MUST FOLLOW:
1. Use the PRE-COMPUTED MENTIONS object directly for target_cited_in_llms. Do not re-compute.
2. For every SEO gap, name at least one competitor URL from the SERP data and say what they do that the target doesn't.
3. For every recommendation, write a specific action (e.g. "Add an H2 'WhatsApp Business API pricing tiers'") not a generic one (e.g. "Improve content").
4. Estimate impact based on how many top-3 competitors share a feature the target lacks.
5. Priority: P0 = blocks ranking, P1 = competitive disadvantage, P2 = nice polish.

Return ONLY this JSON schema:
{{
  "target_cited_in_llms": <use the PRE-COMPUTED MENTIONS object verbatim>,
  "competitor_landscape": [
    {{
      "keyword": "...",
      "top_3_urls": ["url1", "url2", "url3"],
      "common_angles": ["angle1", "angle2"],
      "what_winners_do_target_doesnt": "specific text referencing each URL"
    }}
  ],
  "seo_gaps": [
    {{
      "keyword": "...",
      "gap_type": "missing_h2|missing_entity|intent_mismatch|schema|thin_content|bad_title|missing_internal_link",
      "competitor_evidence": "competitor.com does X — see their position in SERP",
      "fix": "Add/change SPECIFIC thing on target page",
      "priority": "P0|P1|P2"
    }}
  ],
  "geo_gaps": [
    {{
      "keyword": "...",
      "llm": "groq_llama|ddg_gpt4o_mini|ddg_claude",
      "llm_answer_summary": "one sentence summary of what LLM said",
      "competitors_in_answer": ["domain1", "domain2"],
      "fix": "specific action to get mentioned (e.g. write a comparison page, get a citation from authority site X)",
      "priority": "P0|P1|P2"
    }}
  ],
  "seo_vs_geo_divergence": "Specific text — name the top SERP domains, name the domains LLMs mentioned, describe the gap",
  "top_recommendations": [
    {{
      "action": "Concrete action — what to add/change and where on the page",
      "rationale": "Reference specific competitor URLs and what they have that target lacks",
      "estimated_impact": "high|medium|low",
      "priority": "P0|P1|P2",
      "channel": "SEO|GEO|both"
    }}
  ]
}}"""

    text = _groq_call_with_retry(client, system_prompt, user_prompt)
    text = _strip_code_fence(text)
    try:
        result = json.loads(text)
        result["target_cited_in_llms"] = mentions
        return result
    except json.JSONDecodeError:
        return {
            "raw": text,
            "error": "Gap analyzer returned non-JSON output. Inspect 'raw' field.",
            "target_cited_in_llms": mentions,
            "competitor_landscape": [],
            "seo_gaps": [],
            "geo_gaps": [],
            "seo_vs_geo_divergence": "",
            "top_recommendations": [],
        }
