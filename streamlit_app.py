import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.gap_analyzer import analyze_gaps
from src.intent_extractor import extract_intent
from src.llm_crawler import crawl_llms
from src.rate_limit import FREE_DAILY_LIMIT, fingerprint_from_headers, record_run, runs_remaining
from src.report_builder import build_report
from src.serp_crawler import crawl_serps

load_dotenv()

st.set_page_config(page_title="Intent Gap Analyzer", layout="wide")


def get_fingerprint() -> str:
    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}
    return fingerprint_from_headers(headers)


def main() -> None:
    host_has_key = bool(os.environ.get("GROQ_API_KEY"))
    fingerprint = get_fingerprint()

    with st.sidebar:
        st.title("Intent Gap Analyzer")
        st.markdown(
            "Find what your page is missing for **SEO** (Google, Bing, DuckDuckGo) and "
            "**GEO** (Llama 3.3, GPT-4o-mini, Claude)."
        )
        st.divider()

        st.subheader("Your Groq key (optional)")
        st.caption(
            "Free key from "
            "[console.groq.com](https://console.groq.com/keys). "
            "With your own key: unlimited runs. Without: free trial below."
        )
        user_key = st.text_input("Groq API key", type="password", label_visibility="collapsed")

        if user_key:
            st.success("Using your key. Unlimited runs.")
            unlimited = True
            remaining = None
        elif host_has_key:
            remaining = runs_remaining(fingerprint)
            unlimited = False
            if remaining > 0:
                st.info(f"Free trial: **{remaining}/{FREE_DAILY_LIMIT}** runs left today.")
            else:
                st.warning(
                    f"Free trial used up for today. "
                    f"Paste your free Groq key above for unlimited runs."
                )
        else:
            unlimited = False
            remaining = 0
            st.error("This host has no shared key configured. Paste your own Groq key above.")

    st.title("Intent Gap Analyzer")
    st.caption("Analyze a URL's intent gap across search engines + LLMs. Get prioritized fixes.")

    with st.form("analyze"):
        url = st.text_input("Target URL", placeholder="https://example.com/some-page")
        keywords_raw = st.text_input(
            "Keywords (comma-separated)",
            placeholder="primary keyword, secondary keyword, tertiary keyword",
        )
        st.caption("Tip: keep it to 1–3 keywords on the free tier. SERP scraping rate-limits fast.")
        can_run = unlimited or (host_has_key and (remaining or 0) > 0)
        submitted = st.form_submit_button("Analyze", type="primary", disabled=not can_run)

    if not submitted:
        return

    if not url.strip() or not keywords_raw.strip():
        st.error("URL and keywords are required.")
        return

    api_key = user_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        st.error("No API key available. Paste one in the sidebar.")
        return

    os.environ["GROQ_API_KEY"] = api_key
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    progress = st.progress(0, text="Starting...")
    status = st.empty()

    try:
        status.info("Step 1 of 5: Fetching target URL and classifying intent")
        target_intent = extract_intent(url.strip())
        progress.progress(20, text="Intent extracted")

        status.info(f"Step 2 of 5: Crawling SERPs ({len(keywords)} keyword(s))")
        serp_data = crawl_serps(keywords)
        progress.progress(45, text="SERP data collected")

        status.info(f"Step 3 of 5: Crawling LLMs ({len(keywords)} keyword(s))")
        llm_data = crawl_llms(keywords)
        progress.progress(70, text="LLM citations collected")

        status.info("Step 4 of 5: Analyzing intent gaps")
        gap_report = analyze_gaps(url.strip(), target_intent, keywords, serp_data, llm_data)
        progress.progress(85, text="Gaps analyzed")

        status.info("Step 5 of 5: Building report")
        output_dir = Path("/tmp/intent_gap_reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = output_dir / f"report-{timestamp}.html"
        build_report(
            output_path=report_path,
            target_url=url.strip(),
            target_intent=target_intent,
            keywords=keywords,
            serp_data=serp_data,
            llm_data=llm_data,
            gap_report=gap_report,
        )
        progress.progress(100, text="Done")
        status.success("Analysis complete.")

        if not user_key and host_has_key:
            record_run(fingerprint)
    except Exception as e:
        status.error(f"Analysis failed: {e}")
        st.exception(e)
        return

    st.divider()

    st.subheader("Target page intent")
    intent = target_intent.get("intent", {}) or {}
    page = target_intent.get("page", {}) or {}
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Primary topic:** {intent.get('primary_topic', '—')}")
        st.markdown(f"**Intent type:** {intent.get('intent_type', '—')}")
        st.markdown(f"**Audience:** {intent.get('target_audience', '—')}")
    with col2:
        st.markdown(f"**Has schema:** {'yes' if page.get('schema_snippets') else 'no'}")
        st.markdown(f"**H1:** {', '.join(page.get('h1', []) or ['—'])}")
        st.markdown(f"**# of H2s:** {len(page.get('h2', []) or [])}")
    st.markdown(f"**Key entities:** {', '.join(intent.get('key_entities', []) or ['—'])}")
    st.markdown(f"**Content angles:** {', '.join(intent.get('content_angles', []) or ['—'])}")

    st.subheader("Brand mention in LLM answers")
    st.caption(
        "Did each free-tier LLM mention your domain or brand name in its answer? "
        "Note: free-tier LLMs (Groq Llama, DDG Chat) have no web access, so a 'yes' here "
        "means the model already knows your brand. A 'no' is normal for less well-known brands."
    )
    cited = gap_report.get("target_cited_in_llms", {})
    if cited:
        rows = []
        for kw, statuses in cited.items():
            rows.append({
                "keyword": kw,
                "Groq Llama 3.3": "mentioned" if statuses.get("groq_llama") else "no mention",
                "DDG GPT-4o-mini": "mentioned" if statuses.get("ddg_gpt4o_mini") else "no mention",
                "DDG Claude": "mentioned" if statuses.get("ddg_claude") else "no mention",
                "Bing Copilot": "n/a (stub)",
            })
        st.table(rows)
    else:
        st.info("No mention data returned. Check the full report below.")

    landscape = gap_report.get("competitor_landscape", [])
    if landscape:
        st.subheader("Competitor landscape")
        for entry in landscape:
            with st.container(border=True):
                st.markdown(f"**Keyword:** {entry.get('keyword', '—')}")
                top3 = entry.get("top_3_urls", []) or []
                if top3:
                    st.markdown("**Top 3 ranking URLs:**")
                    for u in top3:
                        st.markdown(f"- {u}")
                if entry.get("common_angles"):
                    st.markdown(f"**Common angles winners cover:** {', '.join(entry['common_angles'])}")
                if entry.get("what_winners_do_target_doesnt"):
                    st.markdown(f"**What winners do that you don't:** {entry['what_winners_do_target_doesnt']}")

    st.subheader("SEO gaps")
    seo_gaps = gap_report.get("seo_gaps", [])
    if seo_gaps:
        for gap in seo_gaps:
            with st.container(border=True):
                priority = gap.get("priority", "P2")
                st.markdown(f"**[{priority}]** · *{gap.get('gap_type', '')}* — keyword: *{gap.get('keyword', '')}*")
                if gap.get("competitor_evidence"):
                    st.markdown(f"**Evidence:** {gap['competitor_evidence']}")
                if gap.get("fix"):
                    st.markdown(f"**Fix:** {gap['fix']}")
    else:
        st.info("No SEO gaps returned.")

    st.subheader("GEO gaps")
    geo_gaps = gap_report.get("geo_gaps", [])
    if geo_gaps:
        for gap in geo_gaps:
            with st.container(border=True):
                priority = gap.get("priority", "P2")
                st.markdown(f"**[{priority}]** · *{gap.get('llm', '')}* — keyword: *{gap.get('keyword', '')}*")
                if gap.get("llm_answer_summary"):
                    st.markdown(f"**What the LLM said:** {gap['llm_answer_summary']}")
                if gap.get("competitors_in_answer"):
                    st.markdown(f"**Competitors mentioned:** {', '.join(gap['competitors_in_answer'])}")
                if gap.get("fix"):
                    st.markdown(f"**Fix:** {gap['fix']}")
    else:
        st.info("No GEO gaps returned.")

    if gap_report.get("seo_vs_geo_divergence"):
        st.subheader("SEO vs GEO divergence")
        st.info(gap_report["seo_vs_geo_divergence"])

    st.subheader("Top recommendations")
    recs = gap_report.get("top_recommendations", [])
    if recs:
        for rec in recs:
            with st.container(border=True):
                priority = rec.get("priority", "P2")
                channel = rec.get("channel", "")
                impact = rec.get("estimated_impact", "")
                header_parts = [f"**[{priority}]**", f"*{channel}*"]
                if impact:
                    header_parts.append(f"impact: **{impact}**")
                st.markdown(" · ".join(header_parts) + f" — **{rec.get('action', '')}**")
                if rec.get("rationale"):
                    st.write(rec["rationale"])
    else:
        st.info("No recommendations returned.")

    st.subheader("Full report")
    html_bytes = report_path.read_bytes()
    st.download_button(
        "Download HTML report",
        data=html_bytes,
        file_name=report_path.name,
        mime="text/html",
    )
    with st.expander("View full report inline"):
        import streamlit.components.v1 as components
        components.html(html_bytes.decode("utf-8"), height=1400, scrolling=True)


if __name__ == "__main__":
    main()
