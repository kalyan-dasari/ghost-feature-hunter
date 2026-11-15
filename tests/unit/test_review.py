"""Unit tests for the Ghost Hunt review engine and CLI command."""

from __future__ import annotations

from pathlib import Path

from ghost_hunter.review import render_review_markdown, run_code_review


def test_review_detects_unfinished_code_and_secret_leak(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text(
        """def process_payment():
    api_key = "dummy_secret_token_abcdef123456"
    pass
""",
        encoding="utf-8",
    )

    review_result = run_code_review(tmp_path)
    findings = review_result["findings"]

    # Check that findings contain required 7 fields
    assert len(findings) >= 1
    for f in findings:
        assert "current_behavior" in f
        assert "failure_scenario" in f
        assert "evidence" in f
        assert "root_cause" in f
        assert "recommended_fix" in f
        assert "impact" in f
        assert "false_positive_risk" in f
        assert f["severity"] in ("Critical", "High", "Medium", "Low")
        assert f["confidence"] in ("High", "Medium", "Low")

    # Verify secret leak was identified as Critical
    secret_findings = [f for f in findings if f["category"] == "security"]
    assert len(secret_findings) >= 1
    assert secret_findings[0]["severity"] == "Critical"
    assert "[REDACTED SECRET]" in secret_findings[0]["evidence"]


def test_review_markdown_rendering(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """def run():
    try:
        do_work()
    except Exception:
        pass
""",
        encoding="utf-8",
    )

    review_result = run_code_review(tmp_path)
    md = render_review_markdown(review_result)

    assert "# Ghost Hunt — Code Change Review Report" in md
    assert "### Project Context Summary" in md
    assert "## Detailed Findings" in md
    assert "What the code currently does" in md
    assert "What can go wrong" in md
    assert "Evidence" in md
    assert "Root Cause" in md
    assert "Minimal Recommended Fix" in md
    assert "Impact if Unresolved" in md
    assert "False Positive Risk" in md
