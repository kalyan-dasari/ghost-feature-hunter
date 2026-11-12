"""Typer command line interface."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.config import HunterConfig, load_config, write_default_config
from ghost_hunter.discovery.flask import discover_project, write_discovery
from ghost_hunter.journeys.loader import load_journey
from ghost_hunter.models import AuditReport
from ghost_hunter.reporting.render import render_markdown, write_report
from ghost_hunter.runner import run_journey

app = typer.Typer(
    name="ghost-hunter",
    help="Verify software feature journeys using observable evidence.",
    no_args_is_help=True,
    add_completion=False,
)


def _safe_report_dir(project_root: Path, report_dir: str) -> Path:
    root = project_root.resolve()
    target = (root / report_dir).resolve()
    if target != root and root not in target.parents:
        raise ValueError("report_dir must remain inside the project root")
    return target


@app.command()
def init(
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project to initialize."),
) -> None:
    """Create conservative project configuration and a sample GET journey."""
    root = project_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    journey_dir = root / "journeys"
    sample_journey = journey_dir / "health.json"
    if (root / "ghost-hunter.json").exists() or sample_journey.exists():
        raise typer.BadParameter("Refusing to overwrite existing Ghost Hunter configuration or sample journey.")
    journey_dir.mkdir(exist_ok=True)
    config_path = write_default_config(root)
    sample_journey.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "feature": "health",
                "description": "Replace this example with an explicit feature journey.",
                "steps": [
                    {
                        "id": "health-response",
                        "checkpoint": "Health endpoint is reachable",
                        "adapter": "http",
                        "expected_behavior": "GET /health returns HTTP 200",
                        "settings": {"method": "GET", "url": "/health", "checks": {"status_code": 200}},
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Created {config_path} and {sample_journey}")
    typer.echo("Set base_url in ghost-hunter.json, then run: ghost-hunter audit health")


@app.command()
def audit(
    feature: str = typer.Argument(..., help="Journey name; defaults to journeys/<feature>.json."),
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project root."),
    journey_file: Optional[Path] = typer.Option(None, "--journey", help="Explicit journey JSON file."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Explicit base URL override."),
    allow_writes: bool = typer.Option(False, "--allow-writes", help="Approve configured HTTP write checks."),
    approve_production: bool = typer.Option(False, "--approve-production", help="Approve a configured production target."),
    force: bool = typer.Option(False, "--force", help="Replace reports at the configured report path."),
) -> None:
    """Run a developer-defined feature journey and write JSON/Markdown reports."""
    root = project_root.resolve()
    if journey_file is None and not re.fullmatch(r"[A-Za-z0-9_.-]+", feature):
        raise typer.BadParameter("Feature names may contain only letters, numbers, dot, underscore, and hyphen.")
    journey_path = journey_file or (root / "journeys" / f"{feature}.json")
    if journey_file is not None and not journey_file.is_absolute():
        journey_path = root / journey_file
    try:
        config = load_config(root)
        if base_url:
            HunterConfig(base_url=base_url)
        journey = load_journey(journey_path)
        context = AdapterContext(
            project_root=root,
            config=config,
            base_url_override=base_url,
            allow_writes=allow_writes,
            approve_production=approve_production,
        )
        results = run_journey(context, journey)
        limitations = [
            "Discovery does not infer expected behavior; only assertions in the loaded journey were evaluated.",
            "Optional database and browser checks require their extras and local runtime prerequisites.",
        ]
        report = AuditReport.build(root, results, limitations)
        json_path, markdown_path = write_report(
            report,
            _safe_report_dir(root, config.report_dir),
            force=force,
        )
    except (ValueError, OSError, ValidationError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"{report.summary.total} checks: {report.summary.pass_count} PASS, "
        f"{report.summary.fail_count} FAIL, {report.summary.unknown_count} UNKNOWN"
    )
    typer.echo(f"JSON: {json_path}\nMarkdown: {markdown_path}")
    if report.summary.fail_count:
        raise typer.Exit(code=1)


@app.command()
def discover(
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project root to inspect."),
    force: bool = typer.Option(False, "--force", help="Replace existing discovery output."),
) -> None:
    """Statically discover Flask routes, common models, tests, and frontend files."""
    root = project_root.resolve()
    try:
        config = load_config(root)
        result = discover_project(root)
        json_path, markdown_path = write_discovery(result, _safe_report_dir(root, config.report_dir), force=force)
    except (ValueError, OSError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"Framework: {result['framework_support']}; routes: {len(result['routes'])}; "
        f"models: {len(result['models'])}; tests: {len(result['tests'])}; "
        f"frontend files: {len(result['frontend_files'])}"
    )
    typer.echo(f"JSON: {json_path}\nMarkdown: {markdown_path}")


@app.command()
def report(
    report_json: Path = typer.Argument(..., help="Existing Ghost Hunter JSON report."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Markdown destination."),
    force: bool = typer.Option(False, "--force", help="Replace an existing Markdown report."),
) -> None:
    """Render Markdown from a previously generated JSON report."""
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
        audit_report = AuditReport.model_validate(data)
        destination = output or report_json.with_name("ghost-report.md")
        resolved_dest = destination.resolve()
        project_root = Path(audit_report.project_path).resolve()
        if output and resolved_dest != project_root and project_root not in resolved_dest.parents and not force:
            raise ValueError(f"Output destination must remain within the project root ({project_root}); pass --force to override.")
        if destination.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing {destination}; pass --force to replace it")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_markdown(audit_report), encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValidationError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Markdown: {destination}")


if __name__ == "__main__":
    app()
