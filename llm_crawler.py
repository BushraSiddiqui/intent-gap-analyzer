import os
import time

from groq import Groq

GROQ_MODEL = "llama-3.3-70b-versatile"


def groq_llama_answer(query: str) -> dict:
    """Free Groq Llama 3.3 70B — answer text only, no citations (no web access)."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    last_error = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": query}],
                temperature=0.3,
                max_tokens=1024,
            )
            return {"answer": resp.choices[0].message.content, "citations": []}
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if "429" in str(e) or "rate" in msg or "quota" in msg:
                time.sleep(20 * (attempt + 1))
                continue
            raise
    raise last_error


def ddg_chat(query: str, model: str = "gpt-4o-mini") -> dict:
    """Free DuckDuckGo AI Chat — answer text only, no citations exposed."""
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        answer = ddgs.chat(query, model=model)
    return {"answer": answer, "citations": []}


def bing_copilot_stub(query: str) -> dict:
    return {
        "answer": None,
        "citations": [],
        "error": "Bing Copilot scrape not implemented (requires Playwright).",
    }


def crawl_llms(keywords: list) -> dict:
    data = {}
    for kw in keywords:
        print(f"  - {kw}")
        natural = f"What is the best answer for: {kw}"
        results = {}

        try:
            results["groq_llama"] = groq_llama_answer(natural)
        except Exception as e:
            results["groq_llama"] = {"error": str(e)}
        time.sleep(2)

        try:
            results["ddg_gpt4o_mini"] = ddg_chat(natural, model="gpt-4o-mini")
        except Exception as e:
            results["ddg_gpt4o_mini"] = {"error": str(e)}
        time.sleep(2)

        try:
            results["ddg_claude"] = ddg_chat(natural, model="claude-3-haiku")
        except Exception as e:
            results["ddg_claude"] = {"error": str(e)}
        time.sleep(2)

        results["bing_copilot"] = bing_copilot_stub(natural)
        data[kw] = results
    return data
