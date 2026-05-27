import os
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from src.gap_analyzer import run_full_diagnosis
from src.rate_limit import (
    FREE_DAILY_LIMIT,
    fingerprint_from_headers,
    record_run,
    runs_remaining,
)
from src.report_builder import build_report

load_dotenv()

st.set_page_config(page_title="Intent Gap Analyzer", layout="wide", page_icon=":anchor:")

# ZeroNorth brand
NAVY = "#0A1F3D"
TEAL = "#00B5B0"

CUSTOM_CSS = f"""
<style>
  html, body, [class*="css"] {{ font-family: "Inter", -apple-system, system-ui, sans-serif; }}
  .hero-band {{
    background: linear-gradient(135deg, {NAVY} 0%, #14315a 100%);
    color: white; padding: 1.5rem 1.75rem; border-radius: 14px; margin-bottom: 1.5rem;
  }}
  .hero-band h1 {{ margin: 0; font-size: 1.7rem; font-weight: 700; letter-spacing: -0.01em; }}
  .hero-band p  {{ margin: 0.35rem 0 0; color: #c2cce0; font-size: 0.95rem; }}
  .health-num {{ font-size: 3.2rem; font-weight: 800; color: {TEAL}; line-height: 1; }}
  .health-suf {{ font-size: 1.1rem; color: #8a96ad; margin-left: 4px; }}
  .health-verdict {{ font-size: 1rem; color: #e6ecf5; margin-top: 0.25rem; }}
  .bucket-pill {{
    display: inline-block; background: #e8f7f6; color: {TEAL};
    padding: 2px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  }}
</style>
"""


def get_fingerprint() -> str:
    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}
    return fingerprint_from_headers(headers)


def init_history():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "queued_keyword" not in st.session_state:
        st.session_state.queued_keyword = ""
    if "queued_url" not in st.session_state:
        st.session_state.queued_url = ""


def push_history(entry: dict):
    st.session_state.history = ([entry] + st.session_state.history)[:5]


def render_sidebar(host_has_key: bool, fingerprint: str):
    user_key = ""
    with st.sidebar:
        st.markdown(f"### Intent Gap Analyzer")
        st.caption("Diagnose **why** a URL isn't ranking across 5 buckets.")
        st.divider()

        st.subheader("Your Groq key (optional)")
        st.caption(
            "Free key from [console.groq.com](https://console.groq.com/keys). "
            "With your own key: unlimited runs."
        )
        user_key = st.text_input("Groq API key", type="password", label_visibility="collapsed")

        if user_key:
            st.success("Using your key. Unlimited runs.")
            can_run, remaining = True, None
        elif host_has_key:
            remaining = runs_remaining(fingerprint)
            can_run = remaining > 0
            if can_run:
                st.info(f"Free trial: **{remaining}/{FREE_DAILY_LIMIT}** runs left today.")
            else:
                st.warning("Free trial used up. Paste your own Groq key above.")
        else:
            can_run, remaining = False, 0
            st.error("Host has no shared key. Paste your own Groq key above.")

        st.divider()
        st.subheader("Recent runs")
        if not st.session_state.history:
            st.caption("No runs yet. Run your first analysis below.")
        else:
            for i, entry in enumerate(st.session_state.history):
                with st.container(border=True):
                    st.markdown(
                        f"**{entry.get('health_score', 0)}/100** · {entry.get('url', '')[:50]}"
                    )
                    st.caption(
                        f"{entry.get('timestamp', '')} · "
                        f"{', '.join(entry.get('keywords', [])[:2])}"
                    )

    return user_key, can_run, remaining


def render_diagnosis(diagnosis: dict, html_bytes: bytes, report_path: Path):
    health = diagnosis.get("health_score", 0)
    verdict = diagnosis.get("verdict", "")

    st.markdown(
        f"""
        <div class="hero-band">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:2rem;flex-wrap:wrap;">
            <div>
              <h1>{diagnosis.get('url', '')}</h1>
              <p>Keywords: {', '.join(diagnosis.get('keywords', []))}</p>
            </div>
            <div style="text-align:right;">
              <span class="health-num">{health}</span><span class="health-suf">/100</span>
              <div class="health-verdict">{verdict}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Top 5 ranked fixes")
    fixes = diagnosis.get("ranked_fixes") or []
    valid_fixes = [f for f in fixes if isinstance(f, dict) and "error" not in f]
    if valid_fixes:
        for f in valid_fixes:
            with st.container(border=True):
                imp = f.get("expected_impact", 0)
                cols = st.columns([1, 8, 2])
                with cols[0]:
                    st.markdown(f"### {f.get('rank', '?')}")
                with cols[1]:
                    st.markdown(f"**{f.get('action', '')}**")
                    st.caption(f.get("why_this_matters", ""))
                with cols[2]:
                    st.markdown(
                        f"<span class='bucket-pill'>{f.get('bucket', '')}</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"impact **{imp}/10**  ·  {f.get('effort_hours', '?')}h")
    else:
        st.info("No ranked fixes returned.")

    # 5-bucket tabs
    st.subheader("5-bucket diagnosis")
    tab_intent, tab_auth, tab_diff, tab_dist, tab_compet = st.tabs(
        ["1. Intent", "2. Authority", "3. Differentiation", "4. Distribution", "5. Competitiveness"]
    )

    per_keyword = diagnosis.get("per_keyword", {})

    with tab_intent:
        for kw, pk in per_keyword.items():
            b1 = pk.get("bucket1_intent") or {}
            with st.container(border=True):
                st.markdown(f"**Keyword:** `{kw}`  ·  **Match score:** {b1.get('match_score', 0)}/100  ·  **Verdict:** {b1.get('verdict', '—')}")
                st.caption(
                    f"Target format: **{b1.get('target_format', '—')}** vs Winners': "
                    f"**{b1.get('winners_dominant_format', '—')}**  ·  "
                    f"Target angle: **{b1.get('target_angle', '—')}** vs Winners': "
                    f"**{b1.get('winners_dominant_angle', '—')}**"
                )
                if b1.get("rewrite_instruction"):
                    st.markdown(f"**Rewrite:** {b1['rewrite_instruction']}")

    with tab_auth:
        for kw, pk in per_keyword.items():
            b2 = pk.get("bucket2_authority") or {}
            with st.container(border=True):
                st.markdown(
                    f"**Keyword:** `{kw}`  ·  **Gap:** {b2.get('authority_gap', '—')}  ·  "
                    f"target {b2.get('target_score', 0)} vs winners median {b2.get('winner_median_score', '—')}"
                )
                t = b2.get("target") or {}
                if t:
                    st.caption(
                        f"Domain: `{t.get('domain')}` · age {t.get('age_years')}y · "
                        f"Reddit mentions: {t.get('reddit_mentions')} · "
                        f"LinkedIn mentions: {t.get('linkedin_mentions')} · "
                        f"Bing outbound: {t.get('bing_outbound_links')}"
                    )
                if b2.get("interpretation"):
                    st.write(b2["interpretation"])

    with tab_diff:
        d = diagnosis.get("differentiation") or {}
        with st.container(border=True):
            st.markdown(
                f"**Score:** {d.get('differentiation_score', 0)}/100  ·  "
                f"**Verdict:** {d.get('verdict', '—')}  ·  "
                f"**Similarity to winners:** {d.get('similarity_to_winners', 0)}/100"
            )
        if d.get("rubric"):
            st.markdown("**7-point rubric**")
            rows = [
                {"dimension": dim.replace("_", " "), "score": f"{v.get('score', 0)}/10", "evidence": v.get("evidence", "")}
                for dim, v in d["rubric"].items()
            ]
            st.table(rows)
        if d.get("maritime_suggestions"):
            st.markdown("**Maritime-flavoured suggestions**")
            for s in d["maritime_suggestions"]:
                st.markdown(f"- {s}")

    with tab_dist:
        dist = diagnosis.get("distribution") or {}
        with st.container(border=True):
            st.markdown(
                f"**Score:** {dist.get('distribution_score', 0)}/100  ·  "
                f"**Verdict:** {dist.get('verdict', '—')}"
            )
            if dist.get("interpretation"):
                st.write(dist["interpretation"])
        if dist.get("channels_audited"):
            rows = [
                {
                    "channel": c.get("channel"),
                    "category": (c.get("category") or "").replace("_", " "),
                    "mentions": c.get("mentions"),
                    "status": "present" if c.get("hit") else "missing",
                }
                for c in dist["channels_audited"]
            ]
            st.table(rows)
        if dist.get("suggestions"):
            st.markdown("**Channel actions**")
            for sg in dist["suggestions"]:
                st.markdown(f"- **{sg.get('channel')}**: {sg.get('action')}")

    with tab_compet:
        for kw, pk in per_keyword.items():
            b5 = pk.get("bucket5_competitiveness") or {}
            with st.container(border=True):
                st.markdown(
                    f"**Keyword:** `{kw}`  ·  **Difficulty:** {b5.get('difficulty_label', '—')} "
                    f"({b5.get('difficulty_score', 0)}/100)  ·  "
                    f"**Realistic to rank:** {'yes' if b5.get('realistic_to_rank') else 'no'}"
                )
                if b5.get("gap_assessment"):
                    st.write(b5["gap_assessment"])
                variants = b5.get("long_tail_variants") or []
                valid_variants = [v for v in variants if isinstance(v, dict) and "error" not in v]
                if valid_variants:
                    st.markdown("**Narrower long-tail variants**")
                    for j, v in enumerate(valid_variants):
                        cols = st.columns([7, 2])
                        with cols[0]:
                            st.markdown(
                                f"- `{v.get('keyword')}` — {v.get('why_narrower', '')} "
                                f"_(competition: {v.get('estimated_competition', '—')})_"
                            )
                        with cols[1]:
                            if st.button(
                                "Re-run with this",
                                key=f"rerun_{kw}_{j}",
                            ):
                                st.session_state.queued_keyword = v.get("keyword", "")
                                st.session_state.queued_url = diagnosis.get("url", "")
                                st.rerun()

    # Download + inline report
    st.subheader("Full HTML report")
    st.download_button(
        "Download HTML report",
        data=html_bytes,
        file_name=report_path.name,
        mime="text/html",
    )
    with st.expander("View full report inline"):
        components.html(html_bytes.decode("utf-8"), height=1600, scrolling=True)


def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    init_history()
    host_has_key = bool(os.environ.get("GROQ_API_KEY"))
    fingerprint = get_fingerprint()

    user_key, can_run, remaining = render_sidebar(host_has_key, fingerprint)

    st.title(":anchor: Intent Gap Analyzer")
    st.caption("5-bucket diagnostic for why your URL isn't ranking. Maritime context bundled in.")

    queued_kw = st.session_state.queued_keyword
    queued_url = st.session_state.queued_url

    with st.form("analyze_form"):
        url = st.text_input(
            "Target URL",
            value=queued_url or "",
            placeholder="https://zeronorth.com/products/bunker-pricer",
        )
        keywords_raw = st.text_input(
            "Keywords (comma-separated)",
            value=queued_kw or "",
            placeholder="bunker price intelligence, maritime fuel pricing",
        )
        st.caption("Tip: 1–3 keywords on the free tier. SERP scraping rate-limits fast.")
        submitted = st.form_submit_button("Analyze", type="primary", disabled=not can_run)

    if queued_kw or queued_url:
        st.session_state.queued_keyword = ""
        st.session_state.queued_url = ""

    if not submitted:
        return

    if not url.strip() or not keywords_raw.strip():
        st.error("URL and keywords are required.")
        return

    api_key = user_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        st.error("No Groq API key available. Paste one in the sidebar.")
        return

    os.environ["GROQ_API_KEY"] = api_key
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    # 5-stage progress bar
    progress = st.progress(0, text="Starting...")
    status = st.empty()

    try:
        status.info("Stage 1/5: Crawling target page + SERPs + LLMs")
        progress.progress(15, text="Crawling target + SERPs + LLMs")

        # Real work happens inside run_full_diagnosis. We use coarse stages.
        diagnosis = run_full_diagnosis(url.strip(), keywords)
        progress.progress(60, text="Bucket diagnostics done")

        status.info("Stage 4/5: Building report")
        output_dir = Path("/tmp/intent_gap_reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = output_dir / f"report-{timestamp}.html"
        build_report(
            output_path=report_path,
            target_url=url.strip(),
            target_intent=diagnosis.get("target_intent", {}),
            keywords=keywords,
            serp_data=diagnosis.get("serp_data", {}),
            llm_data=diagnosis.get("llm_data", {}),
            gap_report=diagnosis,
        )
        progress.progress(85, text="Report built")

        status.info("Stage 5/5: Rendering")
        if not user_key and host_has_key:
            record_run(fingerprint)
        progress.progress(100, text="Done")
        status.success("Analysis complete.")

        push_history({
            "url": url.strip(),
            "keywords": keywords,
            "timestamp": datetime.now().strftime("%H:%M %d-%b"),
            "health_score": diagnosis.get("health_score", 0),
            "verdict": diagnosis.get("verdict", ""),
            "report_path": str(report_path),
        })
    except Exception as e:
        status.error(f"Analysis failed: {e}")
        st.exception(e)
        return

    st.divider()
    html_bytes = report_path.read_bytes()
    render_diagnosis(diagnosis, html_bytes, report_path)


if __name__ == "__main__":
    main()
