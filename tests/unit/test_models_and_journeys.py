import json

import pytest
from pydantic import ValidationError

from ghost_hunter.journeys.loader import load_journey
from ghost_hunter.models import AuditReport, CheckResult, Journey, JourneyStep, Status


def test_journey_rejects_duplicate_checkpoint_ids():
    step = JourneyStep(
        id="same",
        checkpoint="First",
        adapter="http",
        expected_behavior="Returns HTTP 200",
    )
    with pytest.raises(ValidationError, match="unique"):
        Journey(feature="checkout", steps=[step, step])


def test_journey_loader_validates_adapter_and_required_expectations(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"feature": "checkout", "steps": [{"id": "x", "checkpoint": "x", "adapter": "shell"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid journey"):
        load_journey(path)


def test_journey_loader_accepts_explicit_http_step(tmp_path):
    path = tmp_path / "health.json"
    path.write_text(
        json.dumps(
            {
                "feature": "health",
                "steps": [
                    {
                        "id": "health",
                        "checkpoint": "Health is reachable",
                        "adapter": "http",
                        "expected_behavior": "GET /health returns 200",
                        "settings": {"url": "/health", "checks": {"status_code": 200}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_journey(path).steps[0].id == "health"


def test_observed_status_requires_evidence():
    with pytest.raises(ValidationError, match="require at least one evidence item"):
        CheckResult(
            feature="health",
            checkpoint_id="health",
            checkpoint="Health responds",
            expected_behavior="HTTP 200",
            actual_observation="HTTP 200",
            status=Status.PASS,
            reproducibility="rerun",
            confidence_rationale="observed",
            duration_ms=1,
        )


def test_report_rejects_inconsistent_summary(tmp_path):
    from ghost_hunter.models import EvidenceItem, ReportSummary

    result = CheckResult(
        feature="health",
        checkpoint_id="health",
        checkpoint="Health responds",
        expected_behavior="HTTP 200",
        actual_observation="HTTP 200",
        status=Status.PASS,
        evidence=[EvidenceItem(reference="http:/health", summary="response observed")],
        reproducibility="rerun",
        confidence_rationale="observed",
        duration_ms=1,
    )
    with pytest.raises(ValidationError, match="summary counts must match"):
        AuditReport(
            tool_version="0.1.0",
            project_path=str(tmp_path),
            results=[result],
            summary=ReportSummary(total=1, pass_count=0, fail_count=0, unknown_count=1),
        )
