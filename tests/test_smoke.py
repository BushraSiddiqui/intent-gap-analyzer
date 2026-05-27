"""Smoke test: runs the full 5-bucket pipeline against a known maritime URL.

Requires GROQ_API_KEY to be set. Skips if absent.

Run: pytest tests/test_smoke.py -v -s
"""
import os
from pathlib import Path

import pytest

from src.gap_analyzer import run_full_diagnosis


TARGET_URL = "https://zeronorth.com/bunker-pricer"
KEYWORDS = ["bunker price intelligence"]


@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set",
)
def test_full_pipeline_on_zeronorth_bunker_pricer():
    diagnosis = run_full_diagnosis(TARGET_URL, KEYWORDS)

    # Required top-level keys
    assert "health_score" in diagnosis, "missing health_score"
    assert "verdict" in diagnosis, "missing verdict"
    assert "bucket_scores" in diagnosis, "missing bucket_scores"
    assert "ranked_fixes" in diagnosis, "missing ranked_fixes"
    assert "per_keyword" in diagnosis, "missing per_keyword"
    assert "differentiation" in diagnosis, "missing differentiation"
    assert "distribution" in diagnosis, "missing distribution"

    # All 5 buckets present in bucket_scores
    bucket_scores = diagnosis["bucket_scores"]
    expected_buckets = {"intent", "authority", "differentiation", "distribution", "competitiveness"}
    assert set(bucket_scores.keys()) == expected_buckets, (
        f"missing buckets in bucket_scores: {expected_buckets - set(bucket_scores.keys())}"
    )

    # Per-keyword should have bucket 1, 2, 5 outputs
    assert KEYWORDS[0] in diagnosis["per_keyword"], "test keyword missing from per_keyword"
    pk = diagnosis["per_keyword"][KEYWORDS[0]]
    assert "bucket1_intent" in pk
    assert "bucket2_authority" in pk
    assert "bucket5_competitiveness" in pk

    # At least 3 ranked fixes
    fixes = diagnosis.get("ranked_fixes") or []
    valid_fixes = [f for f in fixes if isinstance(f, dict) and "error" not in f]
    assert len(valid_fixes) >= 3, (
        f"expected >= 3 ranked_fixes, got {len(valid_fixes)}. "
        f"errors: {[f for f in fixes if isinstance(f, dict) and 'error' in f]}"
    )

    # Health score in valid range
    assert isinstance(diagnosis["health_score"], int)
    assert 0 <= diagnosis["health_score"] <= 100

    # Bucket scores all in valid range
    for name, score in bucket_scores.items():
        assert 0 <= score <= 100, f"{name} score out of range: {score}"


def test_run_full_diagnosis_returns_dict_with_empty_inputs():
    """Even with no GROQ_API_KEY, the function should not raise on bad inputs — it logs errors."""
    # This test runs without GROQ_API_KEY set; the function should still return a dict.
    if not os.environ.get("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = "invalid-key-for-smoke-test"
    try:
        result = run_full_diagnosis("https://example.com", [])
        assert isinstance(result, dict)
        assert "url" in result
        assert "keywords" in result
        assert result["keywords"] == []
    finally:
        if os.environ.get("GROQ_API_KEY") == "invalid-key-for-smoke-test":
            del os.environ["GROQ_API_KEY"]
