"""Repository-wide static connection analysis, route audit, and code hygiene checks.

Performs conservative, evidence-backed inspection of routes, frontend callers,
ghost features, empty implementations, dependencies, and structural duplicates.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.ghost_features import detect_ghost_features, match_route
from ghost_hunter.discovery.languages.models import ClientCall, RouteDefinition
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.project import IGNORED_DIRECTORIES, detect_project_context, is_example_or_fixture


def extract_client_api_calls(file_path: Path) -> list[dict[str, Any]]:
    """Statically search for API paths in frontend/client files (backwards compatible)."""
    calls: list[dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return calls

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


def _normalize_ast_body(body: list[ast.stmt]) -> str:
    """Normalize Python AST statements for structural duplicate comparison.

    Strips docstrings and normalizes variable/constant names to compare logic structure.
    """
    stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    if not stmts:
        return ""

    class StructuralNormalizer(ast.NodeTransformer):
        def visit_Call(self, node: ast.Call) -> ast.AST:
            # Preserve called function names, operators, and constants; normalize arguments
            func = node.func
            new_args = [self.visit(arg) for arg in node.args]
            new_keywords = [self.visit(kw) for kw in node.keywords]
            return ast.copy_location(ast.Call(func=func, args=new_args, keywords=new_keywords), node)

        def visit_Name(self, node: ast.Name) -> ast.Name:
            return ast.copy_location(ast.Name(id="_VAR_", ctx=node.ctx), node)

        def visit_arg(self, node: ast.arg) -> ast.arg:
            return ast.copy_location(ast.arg(arg="_ARG_", annotation=None), node)

    normalized_stmts = []
    normalizer = StructuralNormalizer()
    for stmt in stmts:
        try:
            cloned = ast.parse(ast.unparse(stmt)).body[0]
            transformed = normalizer.visit(cloned)
            normalized_stmts.append(ast.unparse(transformed))
        except Exception:
            try:
                normalized_stmts.append(ast.dump(stmt))
            except Exception:
                pass

    return "\n".join(normalized_stmts)


def estimate_duplicate_blocks(python_files: list[Path]) -> list[dict[str, Any]]:
    """Structural duplicate detection comparing normalized implementations, not just names.

    Avoids reporting different implementations with matching names, detects identical
    implementations with different names, and strictly prevents double-counting lines.
    """
    # Map: structural_hash -> list of occurrences
    occurrences_by_hash: dict[str, list[dict[str, Any]]] = {}

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
                end_lineno = getattr(node, "end_lineno", node.lineno)
                line_count = end_lineno - node.lineno + 1
                if line_count < 4:  # Meaningful blocks only
                    continue

                body_sig = _normalize_ast_body(node.body)
                if not body_sig or len(body_sig) < 20:
                    continue

                occurrences_by_hash.setdefault(body_sig, []).append({
                    "name": node.name,
                    "file": path.as_posix(),
                    "line": node.lineno,
                    "end_line": end_lineno,
                    "line_count": line_count,
                    "line_set": set(range(node.lineno, end_lineno + 1)),
                })

    duplicate_candidates = []
    globally_counted_lines: dict[str, set[int]] = {}

    for body_sig, occurrences in occurrences_by_hash.items():
        if len(occurrences) > 1:
            # Must appear in either multiple files or multiple distinct positions
            unique_locs = {(occ["file"], occ["line"]) for occ in occurrences}
            if len(unique_locs) >= 2:
                # Calculate non-overlapping duplicate lines
                waste_lines = 0
                first_occ = occurrences[0]
                for occ in occurrences[1:]:
                    f = occ["file"]
                    seen_for_file = globally_counted_lines.setdefault(f, set())
                    # Only count lines not previously counted anywhere in waste
                    new_lines = occ["line_set"] - seen_for_file
                    waste_lines += len(new_lines)
                    seen_for_file.update(new_lines)

                names = sorted({occ["name"] for occ in occurrences})
                is_same_name = len(names) == 1
                duplicate_candidates.append({
                    "name": names[0] if is_same_name else f"{names[0]} / {names[1]}",
                    "names": names,
                    "duplicate_type": "exact_structural_duplication",
                    "explanation": (
                        f"Functions {', '.join(names)} share identical normalized implementation structure."
                        if not is_same_name
                        else f"Function '{names[0]}' is duplicated identically across {len(occurrences)} locations."
                    ),
                    "occurrences": [
                        {
                            "name": occ["name"],
                            "file": occ["file"],
                            "line": occ["line"],
                            "line_count": occ["line_count"],
                        }
                        for occ in occurrences
                    ],
                    "estimated_waste_lines": waste_lines,
                })

    return duplicate_candidates


def _evaluate_route_test_coverage(
    route: RouteDefinition,
    test_files_data: list[tuple[str, str]],
) -> str:
    """Evaluate whether a route is test_verified, test_reference_candidate, or testing_gap_candidate.

    test_verified: The route path or handler is actively invoked in a test and assertions are present.
    test_reference_candidate: The route is mentioned in text or comments but lacks execution/assertions.
    testing_gap_candidate: The route is completely absent from test files.
    """
    path = route.path
    func = route.function
    has_mention = False

    assertion_pattern = re.compile(r"""\b(?:assert\s+|self\.assert|expect\s*\(|\.toBe\(|\.toEqual\(|pytest\.raises)""")
    path_regex = re.escape(path.strip("/"))
    call_pattern = re.compile(
        rf"""(?:client\.(?:get|post|put|delete|patch)|requests\.(?:get|post|put|delete|patch)|fetch|axios)\s*\(\s*['"][^'"]*{path_regex}""",
        re.IGNORECASE,
    )

    for file_path, content in test_files_data:
        if path in content or (func and f"{func}(" in content):
            has_mention = True
            has_assertion = bool(assertion_pattern.search(content))
            has_call = bool(call_pattern.search(content)) or (func and f"{func}(" in content)
            if has_call and has_assertion:
                return "test_verified"

    if has_mention:
        return "test_reference_candidate"
    return "testing_gap_candidate"


def audit_dependencies(project_root: Path, detected_imports: list[str]) -> dict[str, Any]:
    """Inspect project package manifests against detected imports for dependency hygiene."""
    root = project_root.resolve()
    manifests_found: list[str] = []
    declared_dependencies: dict[str, str] = {}
    unused_candidates: list[dict[str, Any]] = []

    # 1. pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        manifests_found.append("pyproject.toml")
        try:
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            in_deps = False
            for line in content.splitlines():
                clean = line.strip()
                if clean in ("[project.dependencies]", "dependencies = ["):
                    in_deps = True
                    continue
                if in_deps:
                    if clean.startswith("[") or clean == "]":
                        in_deps = False
                        continue
                    m = re.match(r"""^['"]([a-zA-Z0-9_.-]+)""", clean)
                    if m:
                        pkg = m.group(1).lower().replace("-", "_")
                        declared_dependencies[pkg] = "pyproject.toml"
        except OSError:
            pass

    # 2. requirements.txt
    reqs = root / "requirements.txt"
    if reqs.is_file():
        manifests_found.append("requirements.txt")
        try:
            content = reqs.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    m = re.match(r"""^([a-zA-Z0-9_.-]+)""", clean)
                    if m:
                        pkg = m.group(1).lower().replace("-", "_")
                        declared_dependencies[pkg] = "requirements.txt"
        except OSError:
            pass

    # 3. package.json
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        manifests_found.append("package.json")
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            deps = data.get("dependencies", {})
            for d in deps.keys():
                declared_dependencies[d.lower()] = "package.json"
        except Exception:
            pass

    # 4. Other manifests (Go, Cargo, Java, C#, PHP, Ruby)
    other_manifests = [
        ("Cargo.toml", "Cargo"),
        ("go.mod", "Go Modules"),
        ("pom.xml", "Maven"),
        ("build.gradle", "Gradle"),
        ("composer.json", "Composer"),
        ("Gemfile", "Bundler"),
    ]
    for filename, kind in other_manifests:
        if (root / filename).is_file():
            manifests_found.append(filename)

    normalized_imports = {imp.lower().replace("-", "_") for imp in detected_imports}

    # Standard tool packages that shouldn't be flagged as unused
    common_tool_packages = {
        "pytest", "ruff", "mypy", "black", "flake8", "coverage",
        "playwright", "typer", "pydantic", "pip", "setuptools", "wheel",
        "typescript", "eslint", "prettier", "jest", "vitest", "webpack", "vite",
    }

    for pkg, manifest_source in declared_dependencies.items():
        if pkg in common_tool_packages:
            continue
        # Check if imported directly or subpackage
        is_imported = any(pkg == imp or imp.startswith(f"{pkg}.") or imp.startswith(f"{pkg}/") for imp in normalized_imports)
        if not is_imported:
            unused_candidates.append({
                "id": f"dep-unused-{len(unused_candidates) + 1}",
                "package": pkg,
                "manifest": manifest_source,
                "category": "potentially_unused_dependency",
                "severity": "Low",
                "confidence": "Medium",
                "finding_state": "Requires Owner Confirmation",
                "explanation": f"Package '{pkg}' is declared in {manifest_source} but has no direct import references in application code.",
                "why_false_positive": "Package may be a CLI tool, build utility, dev dependency, or imported dynamically via plugins.",
                "recommended_action": "Verify if this package is still required before removing it from dependencies.",
            })

    return {
        "manifests_found": manifests_found,
        "total_declared": len(declared_dependencies),
        "potentially_unused": unused_candidates,
    }


def audit_repository(project_root: Path) -> dict[str, Any]:
    """Comprehensive multi-language repository audit with ghost feature detection."""
    root = project_root.resolve()
    registry = LanguageRegistry()
    scan_data = registry.scan_repository(root)

    # 1. Project Context
    context = detect_project_context(root)

    # 2. Ghost Features
    ghost_features = detect_ghost_features(root, scan_data)

    # 3. Routes & Mismatches
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    client_calls: list[ClientCall] = scan_data.get("client_calls", [])

    missing_route_candidates = []
    method_mismatches = []
    potentially_unused_endpoints = []
    uncovered_routes = []

    # Check test files
    test_contents = ""
    for test_path in root.rglob("*"):
        if test_path.is_file() and ("test" in test_path.name.lower() or "test" in test_path.parts):
            try:
                test_contents += test_path.read_text(encoding="utf-8", errors="ignore") + "\n"
            except OSError:
                pass

    doc_text = ""
    for doc in root.glob("*.md"):
        try:
            doc_text += doc.read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            pass

    registered_paths = {r.path for r in routes}

    for call in client_calls:
        endpoint = call.path
        req_method = call.method.upper()
        matching = [r for r in routes if match_route(endpoint, r.path)]
        if not matching and (endpoint.startswith("/api") or endpoint.startswith("/v1")):
            missing_route_candidates.append({
                "id": f"missing-route-{len(missing_route_candidates) + 1}",
                "category": "missing_route",
                "severity": "High",
                "confidence": "Medium",
                "evidence": call.raw,
                "source": call.source,
                "line": call.line,
                "endpoint": endpoint,
                "method": req_method,
                "explanation": f"Client calls '{req_method} {endpoint}', but no backend route handler was registered.",
                "potential_impact": "Client requests will likely fail with HTTP 404.",
                "why_false_positive": "Endpoint may be served by an external microservice, reverse proxy, or dynamic route loader.",
                "recommended_action": "Verify if the route is implemented in another service or implement the missing endpoint.",
            })
        elif matching:
            supported = {m.upper() for r in matching for m in r.methods}
            if "ALL" not in supported and req_method not in supported:
                method_mismatches.append({
                    "id": f"mismatch-{len(method_mismatches) + 1}",
                    "category": "method_path_mismatch",
                    "severity": "High",
                    "confidence": "High",
                    "evidence": f"Client calls {req_method} | Route supports {sorted(supported)}",
                    "source": call.source,
                    "line": call.line,
                    "endpoint": endpoint,
                    "client_method": req_method,
                    "allowed_methods": sorted(supported),
                    "explanation": f"Client calls {req_method} on '{endpoint}', but route only accepts {sorted(supported)}.",
                    "potential_impact": "Requests will fail with HTTP 405 Method Not Allowed.",
                    "why_false_positive": "Method might be rewritten by gateway or middleware.",
                    "recommended_action": f"Add {req_method} to route handler or update client method.",
                })

    for route in routes:
        path = route.path
        func = route.function
        frontend_refs = [c for c in client_calls if match_route(c.path, path)]
        in_tests = path in test_contents or func in test_contents
        in_docs = path in doc_text

        if not in_tests:
            uncovered_routes.append({
                "id": f"uncovered-{len(uncovered_routes) + 1}",
                "category": "testing_gap",
                "severity": "Medium",
                "confidence": "High",
                "endpoint": path,
                "methods": route.methods,
                "source": route.source,
                "line": route.line,
                "explanation": f"Route '{path}' ({func}) has no identified assertions in the test suite.",
                "recommended_action": "Add an integration or unit test verifying this route.",
            })

        if not frontend_refs and not in_tests and not in_docs:
            potentially_unused_endpoints.append({
                "id": f"unused-{len(potentially_unused_endpoints) + 1}",
                "category": "potentially_unused_endpoint",
                "severity": "Low",
                "confidence": "Low",
                "finding_state": "Requires Owner Confirmation",
                "endpoint": path,
                "methods": route.methods,
                "source": route.source,
                "line": route.line,
                "explanation": f"Endpoint '{path}' has no static callers in frontend, tests, or documentation.",
                "why_false_positive": "Endpoint may be consumed by external webhooks, mobile apps, or public API clients.",
                "recommended_action": "Confirm with feature owner before deprecating or removing.",
            })

    # 4. Empty & Unfinished Implementations
    unfinished_items = scan_data.get("unfinished", [])
    empty_candidates = []
    for item in unfinished_items:
        # Separate intentional abstract methods from real candidates
        if item.is_abstract_or_protocol:
            continue
        empty_candidates.append({
            "id": f"unfinished-{len(empty_candidates) + 1}",
            "category": "empty_or_unfinished_implementation",
            "item_type": item.item_type,
            "name": item.name,
            "severity": "Medium",
            "confidence": item.confidence,
            "evidence": item.evidence,
            "source": item.source,
            "line": item.line,
            "explanation": item.explanation,
            "why_intentional": item.why_intentional,
            "recommended_action": "Complete the implementation or document intentional stub behavior.",
        })

    # 5. Dependency Hygiene
    dep_audit = audit_dependencies(root, scan_data.get("imports", []))

    # 6. Structural Duplicate Logic
    py_files = [root / p.source for p in scan_data.get("symbols", []) if p.source.endswith(".py")]
    # Deduplicate paths
    unique_py_files = list({root / Path(p): p for p in py_files if (root / Path(p)).is_file()}.keys())
    duplicates = estimate_duplicate_blocks(unique_py_files)

    # Calculate total non-overlapping waste
    total_waste_lines = sum(d.get("estimated_waste_lines", 0) for d in duplicates)

    return {
        "schema_version": "2.0",
        "project_context": context,
        "capability_matrix": scan_data.get("capability_matrix", []),
        "detected_languages": scan_data.get("detected_languages", []),
        "frameworks": scan_data.get("frameworks", []),
        "total_routes": len(routes),
        "total_client_calls": len(client_calls),
        "total_components": len(scan_data.get("components", [])),
        "total_ui_actions": len(scan_data.get("ui_actions", [])),
        "ghost_features": ghost_features,
        "empty_or_unfinished": empty_candidates,
        "missing_route_candidates": missing_route_candidates,
        "method_mismatches": method_mismatches,
        "potentially_unused_endpoints": potentially_unused_endpoints,
        "uncovered_routes": uncovered_routes,
        "dependency_hygiene": dep_audit,
        "duplicate_logic": duplicates,
        "code_waste_estimate": {
            "duplicate_lines": total_waste_lines,
            "explanation": "Calculated from non-overlapping duplicate function implementation lines only.",
        },
        "limitations": [
            "AST and structural regex analysis inspects static files without importing untrusted runtime code.",
            "Dynamic route registration, reverse proxying, and reflection cannot be statically proven and receive caveat tags.",
            "Potentially unused endpoints and dependencies require owner confirmation before removal.",
        ],
    }


def audit_repository_routes(project_root: Path) -> dict[str, Any]:
    """Backwards-compatible wrapper returning route connection findings."""
    full_audit = audit_repository(project_root)
    return {
        "schema_version": "1.0",
        "total_routes_inspected": full_audit["total_routes"],
        "total_frontend_calls_inspected": full_audit["total_client_calls"],
        "missing_route_candidates": full_audit["missing_route_candidates"],
        "potentially_unused_endpoints": full_audit["potentially_unused_endpoints"],
        "uncovered_routes": full_audit["uncovered_routes"],
        "limitations": full_audit["limitations"],
    }
