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


def render_audit_markdown(audit_data: dict[str, Any]) -> str:
    """Render a human-readable Markdown report from repository audit results."""
    lines = [
        f"# Ghost Hunt Repository Audit: {audit_data.get('project_context', {}).get('project_name', 'Project')}",
        "",
        "## Summary",
        f"- **Detected Languages**: {', '.join(audit_data.get('detected_languages', []))}",
        f"- **Files Scanned**: {audit_data.get('file_count', 0)} (Limit: {audit_data.get('file_limit', 15000)}, Truncated: {audit_data.get('scan_truncated', False)})",
        f"- **Total Routes**: {audit_data.get('total_routes', 0)}",
        f"- **Total Client Calls**: {audit_data.get('total_client_calls', 0)}",
        f"- **Ghost Feature Candidates (Primary App)**: {len(audit_data.get('primary_application_findings', {}).get('ghost_features', audit_data.get('ghost_features', [])))}",
        f"- **Empty / Unfinished Candidates (Primary App)**: {len(audit_data.get('primary_application_findings', {}).get('empty_or_unfinished', audit_data.get('empty_or_unfinished', [])))}",
        f"- **Missing Route Candidates (Primary App)**: {len(audit_data.get('primary_application_findings', {}).get('missing_route_candidates', audit_data.get('missing_route_candidates', [])))}",
        f"- **Method Mismatches (Primary App)**: {len(audit_data.get('primary_application_findings', {}).get('method_mismatches', audit_data.get('method_mismatches', [])))}",
        f"- **Uncovered Routes (Primary App)**: {len(audit_data.get('primary_application_findings', {}).get('uncovered_routes', audit_data.get('uncovered_routes', [])))}",
        f"- **Structural Duplicate Blocks**: {len(audit_data.get('duplicate_logic', []))} ({audit_data.get('code_waste_estimate', {}).get('duplicate_lines', 0)} lines)",
        "",
        "## Application Boundaries",
    ]
    boundaries = audit_data.get("application_boundaries", [])
    if boundaries:
        for b in boundaries:
            lines.append(f"- **{b['app_name']}** (`{b['relative_path']}`): {', '.join(b.get('manifests', []))}")
    else:
        lines.append("- Single application root.")

    lines.append("")
    lines.append("## Source-Role Inventory")
    role_inv = audit_data.get("source_role_inventory", {})
    if role_inv:
        lines.append("| Source Role | File Count | Scope Category |")
        lines.append("| --- | --- | --- |")
        for role, count in sorted(role_inv.items()):
            if count > 0:
                scope = "Primary Application" if role == "application_source" else ("Examples & Demos" if role in ("example", "demo", "benchmark") else ("Tests & Fixtures" if role in ("test", "fixture") else "Tooling & Docs"))
                lines.append(f"| `{role}` | {count} | {scope} |")

    lines.append("")
    lines.append("## Capability Matrix")
    lines.append("| Language / Framework | Status | Capability | Limitations |")
    lines.append("| --- | --- | --- | --- |")
    for cap in audit_data.get("capability_matrix", []):
        lines.append(f"| {cap['language_framework']} | {cap['status']} | {cap['analysis_capability']} | {cap['limitations']} |")

    # Inventory-only manifests
    dep_audit = audit_data.get("dependency_hygiene", {})
    inv_only = dep_audit.get("inventory_only_manifests", [])
    if inv_only:
        lines.append("")
        lines.append("## Inventory-Only Manifests (Unsupported Dependency Ecosystems)")
        for inv in inv_only:
            lines.append(f"- **{inv['manifest']}** ({inv['ecosystem']}): {inv['explanation']}")

    lines.append("")
    lines.append("## Primary Application Findings")
    primary_gf = audit_data.get("primary_application_findings", {}).get("ghost_features", audit_data.get("ghost_features", []))
    if primary_gf:
        for gf in primary_gf:
            lines.append(f"### {gf.get('id', 'Ghost')}: {gf.get('chain_stage', '')}")
            lines.append(f"- **Explanation**: {gf.get('explanation', '')}")
            lines.append(f"- **Location**: `{gf.get('source', '')}:{gf.get('line', '')}` ({gf.get('app_name', 'primary')})")
            lines.append(f"- **Confidence**: {gf.get('confidence', '')}")
            lines.append(f"- **Impact**: {gf.get('potential_impact', '')}")
            lines.append(f"- **Recommended Action**: {gf.get('recommended_action', '')}")
            lines.append("")
    else:
        lines.append("No ghost features detected in primary application code.")
        lines.append("")

    # Example findings (isolated)
    example_gf = audit_data.get("example_findings", {}).get("ghost_features", [])
    if example_gf:
        lines.append("## Example and Demo Findings (Isolated)")
        lines.append("> [!NOTE] These findings originate in example/demo applications and do not affect production code.")
        lines.append("")
        for gf in example_gf:
            lines.append(f"### {gf.get('id', 'Example-Ghost')}: {gf.get('chain_stage', '')}")
            lines.append(f"- **Explanation**: {gf.get('explanation', '')}")
            lines.append(f"- **Location**: `{gf.get('source', '')}:{gf.get('line', '')}` (Example: {gf.get('app_name', 'example')})")
            lines.append(f"- **Confidence**: {gf.get('confidence', '')}")
            lines.append("")

    return "\n".join(lines) + "\n"


@app.command()
def discover(
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project root to inspect."),
    force: bool = typer.Option(False, "--force", help="Replace existing discovery output."),
) -> None:
    """Statically discover project routes, models, tests, frontend files, and multi-language capabilities."""
    root = project_root.resolve()
    try:
        config = load_config(root)
        from ghost_hunter.discovery.languages.registry import LanguageRegistry
        from ghost_hunter.discovery.project import detect_project_context

        registry = LanguageRegistry()
        scan_data = registry.scan_repository(root)
        context = detect_project_context(root)
        flask_result = discover_project(root)

        # Primary multi-language discovery result
        result = {
            "schema_version": "2.0",
            "project_name": context.get("project_name", "unknown"),
            "languages": scan_data.get("detected_languages", []),
            "frameworks": scan_data.get("frameworks", []),
            "application_boundaries": scan_data.get("application_boundaries", []),
            "source_role_inventory": scan_data.get("source_role_inventory", {}),
            "capability_matrix": scan_data.get("capability_matrix", []),
            "routes": [
                {
                    "path": r.path,
                    "methods": r.methods,
                    "source": r.source,
                    "line": r.line,
                    "framework": r.framework,
                    "app_name": r.app_name,
                    "source_role": r.source_role,
                }
                for r in scan_data.get("routes", [])
            ],
            "models": [
                {
                    "name": m.name,
                    "source": m.source,
                    "line": m.line,
                    "framework": m.framework,
                    "app_name": m.app_name,
                }
                for m in scan_data.get("models", [])
            ],
            "client_calls": [
                {
                    "path": c.path,
                    "method": c.method,
                    "source": c.source,
                    "line": c.line,
                    "framework": c.framework,
                    "app_name": c.app_name,
                    "call_type": c.call_type,
                }
                for c in scan_data.get("client_calls", [])
            ],
            "components": [
                {
                    "name": comp.name,
                    "source": comp.source,
                    "line": comp.line,
                    "framework": comp.framework,
                    "app_name": comp.app_name,
                }
                for comp in scan_data.get("components", [])
            ],
            # Legacy Flask discovery retained for backwards compatibility
            "flask_compatibility": flask_result,
            "framework_support": flask_result.get("framework_support", "generic"),
            "tests": flask_result.get("tests", []),
            "frontend_files": flask_result.get("frontend_files", []),
            "multi_language": {
                "detected_languages": scan_data.get("detected_languages", []),
                "frameworks": [f["framework"] for f in scan_data.get("frameworks", [])],
                "capability_matrix": scan_data.get("capability_matrix", []),
            },
        }
        json_path, markdown_path = write_discovery(result, _safe_report_dir(root, config.report_dir), force=force)
    except (ValueError, OSError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(
        f"Languages: {', '.join(scan_data.get('detected_languages', [])) or 'None'}; "
        f"routes: {len(result['routes'])}; "
        f"models: {len(result['models'])}; "
        f"applications: {len(result['application_boundaries'])}"
    )
    if flask_result.get("framework_support") != "generic":
        typer.echo(f"Flask compatibility view: {len(flask_result.get('routes', []))} routes")
    typer.echo(f"JSON: {json_path}\nMarkdown: {markdown_path}")


@app.command(name="audit-routes")
def audit_routes(
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project root to inspect."),
) -> None:
    """Statically audit route connections between backend handlers and frontend callers."""
    root = project_root.resolve()
    from ghost_hunter.discovery.audit import audit_repository_routes

    result = audit_repository_routes(root)
    typer.echo(f"Routes inspected: {result['total_routes_inspected']}")
    typer.echo(f"Frontend calls inspected: {result['total_frontend_calls_inspected']}")
    typer.echo(f"Missing route candidates: {len(result['missing_route_candidates'])}")
    typer.echo(f"Potentially unused endpoints: {len(result['potentially_unused_endpoints'])}")
    typer.echo(f"Uncovered routes: {len(result['uncovered_routes'])}")
    for candidate in result["missing_route_candidates"]:
        typer.echo(f"  [MISSING] {candidate['endpoint']} (called from {candidate['source']}:{candidate['line']})")
    for unused in result["potentially_unused_endpoints"]:
        typer.echo(f"  [UNUSED CANDIDATE] {unused['endpoint']} ({unused['source']}:{unused['line']})")
    for uncovered in result["uncovered_routes"]:
        typer.echo(f"  [{uncovered.get('coverage_status', 'UNCOVERED')}] {uncovered['endpoint']} ({uncovered['source']}:{uncovered['line']})")


@app.command(name="audit-repo")
def audit_repo(
    project_root: Path = typer.Option(Path.cwd(), "--project-root", "-p", help="Project root to audit."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Report destination file (.json or .md)."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON format instead of human-readable text."),
    include_examples: bool = typer.Option(False, "--include-examples", help="Include example and demo findings in primary audit output."),
    force: bool = typer.Option(False, "--force", help="Replace existing report file at destination."),
    allow_external_output: bool = typer.Option(
        False, "--allow-external-output", help="Permit writing report outside the project root."
    ),
) -> None:
    """Perform a comprehensive multi-language repository audit with ghost feature detection."""
    root = project_root.resolve()
    from ghost_hunter.discovery.audit import audit_repository

    result = audit_repository(root, include_examples=include_examples)

    if output is not None:
        destination = output if output.is_absolute() else (root / output)
        resolved_dest = destination.resolve()
        is_contained = resolved_dest == root or root in resolved_dest.parents
        if not is_contained and not allow_external_output:
            raise typer.BadParameter(
                f"Refusing to write report outside project root ({root}) to {resolved_dest}. "
                "Pass --allow-external-output to permit writing outside the project root."
            )
        if destination.exists() and not force:
            raise typer.BadParameter(f"Refusing to overwrite existing {destination}; pass --force to replace it")
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.suffix.lower() == ".json" or json_output:
            destination.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        else:
            destination.write_text(render_audit_markdown(result), encoding="utf-8")
        typer.echo(f"Audit report written to: {destination}")
        return

    if json_output:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    typer.echo(f"Project: {result['project_context']['project_name']}")
    boundaries = result.get("application_boundaries", [])
    if boundaries:
        typer.echo(f"Application Boundaries ({len(boundaries)}):")
        for b in boundaries:
            typer.echo(f"  - {b['app_name']} ({b['relative_path']}): {', '.join(b.get('manifests', []))}")

    typer.echo("Language / Framework Capabilities:")
    for cap in result["capability_matrix"]:
        typer.echo(f"  - {cap['language_framework']}: {cap['status']} ({cap['analysis_capability']})")

    primary_findings = result.get("primary_application_findings", {})
    typer.echo(f"\n[Primary Application Findings]")
    typer.echo(f"  Ghost Feature Candidates: {len(primary_findings.get('ghost_features', []))}")
    for gf in primary_findings.get("ghost_features", []):
        typer.echo(f"    [{gf['chain_stage']}] {gf['explanation']} ({gf['source']}:{gf['line']})")

    typer.echo(f"  Empty / Unfinished Candidates: {len(primary_findings.get('empty_or_unfinished', []))}")
    for item in primary_findings.get("empty_or_unfinished", []):
        typer.echo(f"    [{item['item_type']}] {item['name']} ({item['source']}:{item['line']})")

    typer.echo(f"  Missing Route Candidates: {len(primary_findings.get('missing_route_candidates', []))}")
    for candidate in primary_findings.get("missing_route_candidates", []):
        typer.echo(f"    [MISSING] {candidate['method']} {candidate['endpoint']} ({candidate['source']}:{candidate['line']})")

    typer.echo(f"  Method Mismatches: {len(primary_findings.get('method_mismatches', []))}")
    for mm in primary_findings.get("method_mismatches", []):
        typer.echo(f"    [MISMATCH] Client calls {mm['client_method']} {mm['endpoint']} (Allowed: {mm['allowed_methods']})")

    typer.echo(f"  Potentially Unused Endpoints: {len(primary_findings.get('potentially_unused_endpoints', []))}")
    for unused in primary_findings.get("potentially_unused_endpoints", []):
        typer.echo(f"    [UNUSED] {unused['endpoint']} ({unused['source']}:{unused['line']})")

    typer.echo(f"  Structural Duplicate Code: {len(primary_findings.get('duplicate_logic', []))} blocks ({result['code_waste_estimate']['duplicate_lines']} waste lines)")

    example_findings = result.get("example_findings", {})
    ex_ghost_count = len(example_findings.get("ghost_features", []))
    ex_empty_count = len(example_findings.get("empty_or_unfinished", []))
    if ex_ghost_count or ex_empty_count:
        typer.echo(f"\n[Example & Demo Findings (Isolated - {ex_ghost_count} ghost, {ex_empty_count} empty)]")
        if include_examples:
            for gf in example_findings.get("ghost_features", []):
                typer.echo(f"    [EXAMPLE GHOST: {gf['chain_stage']}] {gf['explanation']} ({gf['source']}:{gf['line']})")
        else:
            typer.echo("    (Pass --include-examples to view detailed findings for example directories)")




@app.command()
def report(
    report_json: Path = typer.Argument(..., help="Existing Ghost Hunter JSON report."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Markdown destination."),
    force: bool = typer.Option(False, "--force", help="Replace an existing Markdown report."),
    allow_external_output: bool = typer.Option(
        False, "--allow-external-output", help="Permit writing report outside the project root."
    ),
) -> None:
    """Render Markdown from a previously generated JSON report."""
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
        audit_report = AuditReport.model_validate(data)
        destination = output or report_json.with_name("ghost-report.md")
        resolved_dest = destination.resolve()
        project_root = Path(audit_report.project_path).resolve()

        is_contained = resolved_dest == project_root or project_root in resolved_dest.parents
        if not is_contained and not allow_external_output:
            raise ValueError(
                f"Refusing to write report outside project root ({project_root}) to {resolved_dest}. "
                "Pass --allow-external-output to permit writing outside the project root."
            )

        check_path = destination
        while check_path != check_path.parent:
            if check_path.is_symlink():
                target = check_path.resolve()
                if (target != project_root and project_root not in target.parents) and not allow_external_output:
                    raise ValueError(
                        f"Refusing to write through symlink {check_path} escaping project root. "
                        "Pass --allow-external-output to permit writing outside the project root."
                    )
            check_path = check_path.parent

        if destination.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing {destination}; pass --force to replace it")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_markdown(audit_report), encoding="utf-8")
    except (ValueError, OSError, json.JSONDecodeError, ValidationError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Markdown: {destination}")


if __name__ == "__main__":
    app()
