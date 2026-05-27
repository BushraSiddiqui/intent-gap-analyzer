#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.intent_extractor import extract_intent
from src.serp_crawler import crawl_serps
from src.llm_crawler import crawl_llms
from src.gap_analyzer import analyze_gaps
from src.report_builder import build_report


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Analyze URL intent gap for SEO + GEO")
    parser.add_argument("--url", required=True, help="Target URL to analyze")
    parser.add_argument("--keywords", required=True, help="Comma-separated target keywords")
    parser.add_argument("--output-dir", default="output", help="Where to write the HTML report")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not keywords:
        sys.exit("No keywords provided")

    print(f"[1/5] Extracting intent from {args.url}")
    target_intent = extract_intent(args.url)

    print(f"[2/5] Crawling SERPs for {len(keywords)} keyword(s)")
    serp_data = crawl_serps(keywords)

    print(f"[3/5] Crawling LLMs for {len(keywords)} keyword(s)")
    llm_data = crawl_llms(keywords)

    print("[4/5] Analyzing gaps")
    gap_report = analyze_gaps(
        target_url=args.url,
        target_intent=target_intent,
        keywords=keywords,
        serp_data=serp_data,
        llm_data=llm_data,
    )

    print("[5/5] Building HTML report")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(args.output_dir) / f"report-{timestamp}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_report(
        output_path=output_path,
        target_url=args.url,
        target_intent=target_intent,
        keywords=keywords,
        serp_data=serp_data,
        llm_data=llm_data,
        gap_report=gap_report,
    )

    print(f"\nReport written: {output_path}")


if __name__ == "__main__":
    main()
