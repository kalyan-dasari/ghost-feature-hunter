import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ghost_hunter.models import AuditReport, Journey, JourneyStep, Status

REPO = Path(__file__).resolve().parents[2]


def _validator(name):
    schema = json.loads((REPO / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def test_journey_schema_validates_demo_checkout_definition():
    schema = _validator("journey.schema.json")
    journey = json.loads(
        (REPO / "examples" / "broken-flask-shop" / "journeys" / "checkout.json").read_text(encoding="utf-8")
    )
    schema.validate(journey)


def test_report_schema_validates_serialized_evidence_report(tmp_path):
    journey = Journey(
        feature="sample",
        steps=[
            JourneyStep(
                id="first",
                checkpoint="First checkpoint",
                adapter="http",
                expected_behavior="Status is 200",
            )
        ],
    )
    from ghost_hunter.adapters.base import unknown_result
    import time

    result = unknown_result(journey, journey.steps[0], "No target configured.", time.monotonic())
    report = AuditReport.build(tmp_path, [result], ["No request was sent."])
    instance = json.loads(report.model_dump_json())
    _validator("report.schema.json").validate(instance)
    assert result.status is Status.UNKNOWN
