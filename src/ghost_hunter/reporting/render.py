"""JSON and Markdown report output."""

from __future__ import annotations

import json
from pathlib import Path

from ghost_hunter.models import AuditReport, Status
from ghost_hunter.evidence.redaction import redact_text, redact_value


def _safe_report_data(report: AuditReport) -> dict:
    data = report.model_dump(mode="json")
    for result in data["results"]:
        for key in (
            "checkpoint",
            "expected_behavior",
            "actual_observation",
            "reproducibility",
            "confidence_rationale",
        ):
            result[key] = redact_text(result[key])
        for evidence in result["evidence"]:
            evidence["reference"] = redact_text(evidence["reference"])
            evidence["summary"] = redact_text(evidence["summary"])
            evidence["details"] = redact_value(evidence["details"])
    data["limitations"] = [redact_text(item) for item in data["limitations"]]
    return data


def render_json(report: AuditReport) -> str:
    return json.dumps(_safe_report_data(report), indent=2, ensure_ascii=False) + "\n"


def _cell(value: str) -> str:
    return redact_text(value, 1000).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: AuditReport) -> str:
    summary = report.summary
    lines = [
        f"# Ghost Feature Hunter report: {report.results[0].feature if report.results else 'audit'}",
        "",
        f"- Generated: {report.generated_at.isoformat()}",
        f"- Project: `{_cell(report.project_path)}`",
        f"- Tool version: {report.tool_version}",
        "",
        "## Summary",
        "",
        f"| Total | PASS | FAIL | UNKNOWN |",
        "|---:|---:|---:|---:|",
        f"| {summary.total} | {summary.pass_count} | {summary.fail_count} | {summary.unknown_count} |",
        "",
        "## Checkpoints",
        "",
        "| Status | Checkpoint | Expected behavior | Actual observation |",
        "|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            "| "
            + " | ".join(
                (
                    result.status.value,
                    _cell(f"{result.checkpoint_id}: {result.checkpoint}"),
                    _cell(result.expected_behavior),
                    _cell(result.actual_observation),
                )
            )
            + " |"
        )
    lines.extend(["", "## Evidence", ""])
    if not any(result.evidence for result in report.results):
        lines.append("No evidence was collected.")
    for result in report.results:
        lines.extend([f"### {result.checkpoint_id}: {result.checkpoint}", ""])
        lines.append(f"- Confidence: {_cell(result.confidence_rationale)}")
        lines.append(f"- Reproducibility: {_cell(result.reproducibility)}")
        if result.evidence:
            for item in result.evidence:
                details = json.dumps(redact_value(item.details), ensure_ascii=False, sort_keys=True)
                lines.append(
                    f"- `{_cell(item.reference)}` — {_cell(item.summary)} "
                    f"(observed {item.observed_at.isoformat()}; `{_cell(details)}`)"
                )
        else:
            lines.append("- No evidence reference was available for this result.")
        lines.append("")
    lines.extend(["## Limitations", ""])
    if report.limitations:
        lines.extend(f"- {_cell(item)}" for item in report.limitations)
    else:
        lines.append("No additional limitations were recorded.")
    lines.extend(["", "## Recommended next steps", ""])
    if summary.fail_count:
        lines.append("Investigate each FAIL checkpoint and rerun the same journey after any fix.")
    if summary.unknown_count:
        lines.append("Resolve unavailable prerequisites or add evidence, then rerun UNKNOWN checkpoints.")
    if summary.pass_count == summary.total:
        lines.append("The defined assertions passed. Review the journey scope before treating the feature as verified.")
    if not report.results:
        lines.append("Add at least one explicit journey checkpoint and run the audit again.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: AuditReport, output_dir: Path, *, force: bool = False) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ghost-report.json"
    markdown_path = output_dir / "ghost-report.md"
    existing = [path for path in (json_path, markdown_path) if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing report(s): {names}; pass --force to replace them")
    json_path.write_text(render_json(report), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
