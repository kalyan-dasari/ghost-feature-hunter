import json

from typer.testing import CliRunner

from ghost_hunter.cli import app
from ghost_hunter.models import AuditReport, EvidenceItem, Journey, Status
from ghost_hunter.reporting.render import render_markdown, render_json
from ghost_hunter.runner import run_journey
from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.config import HunterConfig


def test_report_json_and_markdown_include_status_and_limitations(tmp_path):
    journey = Journey(
        feature="checkout",
        steps=[
            {
                "id": "blocked-post",
                "checkpoint": "Checkout approval",
                "adapter": "http",
                "expected_behavior": "POST is explicitly approved",
                "settings": {"method": "POST", "url": "/checkout", "checks": {"status_code": 201}},
            }
        ],
    )
    result = run_journey(AdapterContext(tmp_path, HunterConfig()), journey)[0]
    report = AuditReport.build(tmp_path, [result], ["Network was not contacted."])
    decoded = json.loads(render_json(report))
    assert decoded["results"][0]["status"] == "UNKNOWN"
    assert decoded["summary"]["unknown_count"] == 1
    markdown = render_markdown(report)
    assert "UNKNOWN" in markdown
    assert "Network was not contacted." in markdown


def test_report_renderers_redact_untrusted_evidence_details(tmp_path):
    journey = Journey(
        feature="redaction",
        steps=[
            {
                "id": "report",
                "checkpoint": "Secret result is not disclosed",
                "adapter": "http",
                "expected_behavior": "A result is checked",
            }
        ],
    )
    from ghost_hunter.models import CheckResult

    result = CheckResult(
        feature="redaction",
        checkpoint_id="report",
        checkpoint=journey.steps[0].checkpoint,
        expected_behavior=journey.steps[0].expected_behavior,
        actual_observation="request completed",
        status=Status.PASS,
        evidence=[EvidenceItem(reference="http:test", summary="observed", details={"api_token": "do-not-leak"})],
        reproducibility="rerun",
        confidence_rationale="checked",
        duration_ms=1,
    )
    report = AuditReport.build(tmp_path, [result])
    assert "do-not-leak" not in render_json(report)
    assert "do-not-leak" not in render_markdown(report)


def test_init_creates_config_and_sample_journey_without_overwrite(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--project-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "ghost-hunter.json").exists()
    assert (tmp_path / "journeys" / "health.json").exists()
    second = runner.invoke(app, ["init", "--project-root", str(tmp_path)])
    assert second.exit_code != 0


def test_cli_help_documents_expected_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "discover", "audit", "report"):
        assert command in result.output


def test_evidence_item_accepts_timestamp_default():
    evidence = EvidenceItem(reference="unit:test", summary="assertion observed")
    assert evidence.observed_at.tzinfo is not None


def test_report_rejects_unjailed_output_path(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    unsafe_dest = tmp_path.parent / "escape.md"
    result = runner.invoke(app, ["report", str(report_file), "--output", str(unsafe_dest)])
    assert result.exit_code != 0
    assert "Refusing to write report outside project root" in result.output
    assert not unsafe_dest.exists()


def test_report_rejects_external_output_even_with_force(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    unsafe_dest = tmp_path.parent / "escape_force.md"
    result = runner.invoke(app, ["report", str(report_file), "--output", str(unsafe_dest), "--force"])
    assert result.exit_code != 0
    assert "Refusing to write report outside project root" in result.output
    assert not unsafe_dest.exists()


def test_report_rejects_directory_traversal(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    traversal_dest = tmp_path / "subdir" / ".." / ".." / "escaped_traversal.md"
    result = runner.invoke(app, ["report", str(report_file), "--output", str(traversal_dest)])
    assert result.exit_code != 0
    assert "Refusing to write report outside project root" in result.output
    assert not (tmp_path.parent / "escaped_traversal.md").exists()


def test_report_allows_external_output_with_explicit_flag(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    external_dest = tmp_path.parent / "allowed_external.md"
    result = runner.invoke(
        app,
        ["report", str(report_file), "--output", str(external_dest), "--allow-external-output"],
    )
    assert result.exit_code == 0, result.output
    assert external_dest.exists()
    assert "# Ghost Feature Hunter report:" in external_dest.read_text(encoding="utf-8")


def test_report_refuses_overwrite_without_force(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    target_dest = tmp_path / "ghost-report.md"
    target_dest.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["report", str(report_file), "--output", str(target_dest)])
    assert result.exit_code != 0
    assert "Refusing to overwrite existing" in result.output
    assert target_dest.read_text(encoding="utf-8") == "existing content"

    # With --force it should succeed
    force_result = runner.invoke(app, ["report", str(report_file), "--output", str(target_dest), "--force"])
    assert force_result.exit_code == 0, force_result.output
    assert "# Ghost Feature Hunter report:" in target_dest.read_text(encoding="utf-8")


def test_report_existing_external_requires_both_force_and_allow_external(tmp_path):
    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    external_dest = tmp_path.parent / "existing_external.md"
    external_dest.write_text("initial external", encoding="utf-8")

    # 1. No flags -> rejected by containment
    r1 = runner.invoke(app, ["report", str(report_file), "--output", str(external_dest)])
    assert r1.exit_code != 0
    assert "Refusing to write report outside project root" in r1.output

    # 2. Only --force -> rejected by containment
    r2 = runner.invoke(app, ["report", str(report_file), "--output", str(external_dest), "--force"])
    assert r2.exit_code != 0
    assert "Refusing to write report outside project root" in r2.output

    # 3. Only --allow-external-output -> rejected by overwrite guard
    r3 = runner.invoke(
        app,
        ["report", str(report_file), "--output", str(external_dest), "--allow-external-output"],
    )
    assert r3.exit_code != 0
    assert "Refusing to overwrite existing" in r3.output

    # 4. Both --allow-external-output and --force -> succeeds!
    r4 = runner.invoke(
        app,
        [
            "report",
            str(report_file),
            "--output",
            str(external_dest),
            "--allow-external-output",
            "--force",
        ],
    )
    assert r4.exit_code == 0, r4.output
    assert "# Ghost Feature Hunter report:" in external_dest.read_text(encoding="utf-8")


def test_report_symlink_escape_rejection(tmp_path):
    import os
    import pytest

    report_file = tmp_path / "report.json"
    report = AuditReport.build(tmp_path, [])
    report_file.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")

    outside_dir = tmp_path.parent / "symlink_target_dir"
    outside_dir.mkdir(exist_ok=True)
    symlink_in_project = tmp_path / "linked_dir"
    try:
        os.symlink(str(outside_dir), str(symlink_in_project), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated privileges on this environment")

    symlink_dest = symlink_in_project / "escaped_report.md"
    runner = CliRunner()
    result = runner.invoke(app, ["report", str(report_file), "--output", str(symlink_dest)])
    assert result.exit_code != 0
    assert (
        "Refusing to write report outside project root" in result.output
        or "Refusing to write through symlink" in result.output
    )
    assert not (outside_dir / "escaped_report.md").exists()

