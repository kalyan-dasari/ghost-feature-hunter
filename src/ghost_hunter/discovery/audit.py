"""Repository-wide static connection analysis, route audit, and code health checks.

Performs conservative, evidence-backed inspection of routes, frontend callers,
and test coverage gaps without executing project code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.flask import FRONTEND_SUFFIXES, IGNORED_DIRS, discover_project
from ghost_hunter.discovery.project import is_example_or_fixture


def extract_client_api_calls(file_path: Path) -> list[dict[str, Any]]:
    """Statically search for API paths in frontend/client files."""
    calls: list[dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return calls

    # Match fetch('/api/...'), axios.get('/api/...'), action="/api/..."
    patterns = [
        re.compile(r"""(?:fetch|axios(?:\.[a-z]+)?|\$\.ajax)\s*\(\s*['"]([/a-zA-Z0-9_.-]+)['"]"""),
        re.compile(r"""action\s*=\s*['"]([/a-zA-Z0-9_.-]+)['"]"""),
        re.compile(r"""url_for\s*\(\s*['"]([a-zA-Z0-9_.-]+)['"]"""),
    ]

    lines = content.splitlines()
    for line_num, line in enumerate(lines, 1):
        for pattern in patterns:
            for match in pattern.finditer(line):
                path = match.group(1)
                if path.startswith(("/api", "/")):
                    calls.append({
                        "path": path,
                        "line": line_num,
                        "source": file_path.as_posix(),
                        "raw": line.strip(),
                    })
    return calls


def audit_repository_routes(project_root: Path) -> dict[str, Any]:
    """Audit route connections between backend handlers, frontend callers, and tests."""
    root = project_root.resolve()
    discovery = discover_project(root)

    backend_routes = discovery.get("routes", [])
    registered_paths = {r["path"] for r in backend_routes}
    registered_functions = {r["function"] for r in backend_routes}

    # Gather frontend calls
    client_calls: list[dict[str, Any]] = []
    for rel_path in discovery.get("frontend_files", []):
        full_path = root / rel_path
        if full_path.is_file():
            client_calls.extend(extract_client_api_calls(full_path))

    # Read test contents to check route coverage
    test_contents: dict[str, str] = {}
    for test_rel in discovery.get("tests", []):
        test_path = root / test_rel
        try:
            test_contents[test_rel] = test_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    # Read doc contents
    doc_text = ""
    for doc_file in root.glob("*.md"):
        try:
            doc_text += doc_file.read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            pass

    missing_route_candidates: list[dict[str, Any]] = []
    for call in client_calls:
        endpoint = call["path"]
        # Exact match or prefix match for parameterized routes
        matched = any(
            reg == endpoint or (":" in reg or "<" in reg and endpoint.startswith(reg.split("<")[0].split(":")[0]))
            for reg in registered_paths
        )
        if not matched and endpoint.startswith("/api"):
            missing_route_candidates.append({
                "id": f"missing-route-{len(missing_route_candidates) + 1}",
                "category": "missing_route",
                "severity": "High",
                "confidence": "Medium",
                "evidence": call["raw"],
                "source": call["source"],
                "line": call["line"],
                "endpoint": endpoint,
                "explanation": f"Frontend client calls '{endpoint}', but no matching backend route handler was registered.",
                "potential_impact": "Client requests will likely receive HTTP 404.",
                "why_false_positive": "Endpoint may be served by an external microservice, reverse proxy, or dynamic route loader.",
                "recommended_action": "Verify if the route is implemented in another service or implement the missing endpoint.",
            })

    potentially_unused_endpoints: list[dict[str, Any]] = []
    uncovered_routes: list[dict[str, Any]] = []

    for route in backend_routes:
        path = route["path"]
        func = route["function"]

        # Check references in frontend
        frontend_refs = [c for c in client_calls if c["path"] == path]

        # Check references in tests
        test_refs = [
            test_rel
            for test_rel, content in test_contents.items()
            if path in content or func in content
        ]

        # Check references in docs
        in_docs = path in doc_text

        if not test_refs:
            uncovered_routes.append({
                "id": f"uncovered-route-{len(uncovered_routes) + 1}",
                "category": "uncovered_route",
                "severity": "Medium",
                "confidence": "High",
                "endpoint": path,
                "methods": route["methods"],
                "source": route["source"],
                "line": route["line"],
                "explanation": f"Route '{path}' ({func}) has no identified references in existing test suites.",
                "recommended_action": "Add an integration or unit test asserting the route's behavior.",
            })

        if not frontend_refs and not test_refs and not in_docs:
            potentially_unused_endpoints.append({
                "id": f"unused-endpoint-{len(potentially_unused_endpoints) + 1}",
                "category": "potentially_unused_endpoint",
                "severity": "Low",
                "confidence": "Low",
                "endpoint": path,
                "methods": route["methods"],
                "source": route["source"],
                "line": route["line"],
                "explanation": f"Endpoint '{path}' has no static callers in frontend, tests, or documentation.",
                "why_false_positive": "Endpoint may be consumed by external webhook, mobile client, or third-party integration.",
                "recommended_action": "Confirm with feature owner before deprecating or removing.",
            })

    return {
        "schema_version": "1.0",
        "total_routes_inspected": len(backend_routes),
        "total_frontend_calls_inspected": len(client_calls),
        "missing_route_candidates": missing_route_candidates,
        "potentially_unused_endpoints": potentially_unused_endpoints,
        "uncovered_routes": uncovered_routes,
        "limitations": [
            "Static regex and AST parsing cannot inspect runtime-constructed URLs or external API consumers.",
            "Potentially unused endpoints are candidates only and require owner confirmation before removal.",
            "Missing tests indicate testing gaps, not necessarily broken functionality.",
        ],
    }


def estimate_duplicate_blocks(python_files: list[Path]) -> list[dict[str, Any]]:
    """Conservative duplicate function detection without double-counting lines."""
    functions_by_name: dict[str, list[dict[str, Any]]] = {}

    for path in python_files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                # Calculate line span
                end_lineno = getattr(node, "end_lineno", node.lineno)
                line_count = end_lineno - node.lineno + 1
                if line_count >= 5:  # meaningful functions only
                    functions_by_name.setdefault(node.name, []).append({
                        "file": path.as_posix(),
                        "line": node.lineno,
                        "line_count": line_count,
                    })

    duplicate_candidates = []
    seen_locations: set[tuple[str, int]] = set()

    for name, occurrences in functions_by_name.items():
        if len(occurrences) > 1:
            # Check unique files
            files = {occ["file"] for occ in occurrences}
            if len(files) > 1:
                # Add without double counting
                new_occs = [occ for occ in occurrences if (occ["file"], occ["line"]) not in seen_locations]
                if len(new_occs) >= 2:
                    for occ in new_occs:
                        seen_locations.add((occ["file"], occ["line"]))
                    duplicate_candidates.append({
                        "name": name,
                        "occurrences": occurrences,
                        "estimated_waste_lines": sum(occ["line_count"] for occ in occurrences[1:]),
                    })

    return duplicate_candidates
