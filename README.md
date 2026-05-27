---
title: Intent Gap Analyzer
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Intent Gap Analyzer

Free SEO + GEO intent gap analysis. Analyzes a URL against:
- **SEO**: Google, Bing, DuckDuckGo top results
- **GEO**: Gemini (free API with Google Search grounding), GPT-4o-mini + Claude via DuckDuckGo Chat, Bing Copilot (stub)

Outputs a self-contained HTML dashboard with prioritized recommendations.

**Two ways to use it:**
- **Browser app** (recommended for non-technical users) → see [DEPLOY.md](DEPLOY.md) for a step-by-step Hugging Face Spaces deploy. 3 free runs/day per visitor, then they paste their own free Gemini key for unlimited.
- **CLI** (below) — for local development and one-off runs.

## Setup

```bash
cd intent-gap-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your free GEMINI_API_KEY from:
# https://aistudio.google.com/app/apikey
```

## Run

```bash
python analyze.py \
  --url https://example.com/some-page \
  --keywords "primary keyword, secondary keyword, tertiary keyword"
```

The report lands in `output/report-<timestamp>.html`. Open in a browser.

## Cost

$0. The only API used is the free Gemini tier (1500 req/day on Flash). DuckDuckGo Chat and Bing/Google scraping are free.

## Pipeline

```
URL + keywords
  -> intent_extractor   fetch page + classify intent (Gemini)
  -> serp_crawler       Google (lib) + Bing (scrape) + DuckDuckGo (lib)
  -> llm_crawler        Gemini grounding + DDG Chat (GPT-4o-mini, Claude) + Bing Copilot stub
  -> gap_analyzer       Gemini diffs target vs. SERP winners vs. LLM citations
  -> report_builder     Jinja2 HTML with Chart.js
```

## Known limitations

- **Bing Copilot is stubbed.** Real citations require Playwright + UI scraping. Replace `bing_copilot_stub` in `src/llm_crawler.py`.
- **Google scrape rate-limits aggressively.** Keep keyword count low (3–5) per run. If it errors, fall back to Bing + DuckDuckGo only.
- **DuckDuckGo Chat does not expose citations.** Only the answer text is captured for GPT-4o-mini and Claude — useful for content angle analysis, not source mapping.
- **No Perplexity in the free path.** Perplexity has no free API. Add Playwright-based scraping if needed.
- **ToS gray zone.** SERP scraping is fine for personal/internal use. Do not deploy as a public service without legal review.

## Extending

- **Real Bing Copilot citations**: install Playwright (`pip install playwright && playwright install chromium`), navigate to `copilot.microsoft.com`, submit query, parse the sources panel.
- **Real Perplexity citations**: similar Playwright approach on `perplexity.ai`.
- **Competitor crawling**: for each SERP winner, run `intent_extractor.fetch_page()` and feed those intents into `gap_analyzer` for richer side-by-side comparison.
- **Paid swap**: replace `serp_crawler` with SerpAPI/DataForSEO when ready — same return shape, drop-in.
- **Batch mode**: wrap `analyze.py` in a loop over a CSV of URLs.

## File layout

```
intent-gap-analyzer/
  analyze.py                 CLI entry point
  requirements.txt
  .env.example
  src/
    intent_extractor.py      Target URL fetch + intent classification
    serp_crawler.py          Google / Bing / DuckDuckGo
    llm_crawler.py           Gemini / DDG Chat / Bing Copilot stub
    gap_analyzer.py          LLM-powered SEO + GEO diff
    report_builder.py        Jinja2 render
  templates/
    report.html.j2           Dashboard template (Chart.js via CDN)
  output/                    Generated reports land here
```
