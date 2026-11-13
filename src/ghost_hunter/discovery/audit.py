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
from ghost_hunter.discovery.project import (
    IGNORED_DIRECTORIES,
    classify_source_role,
    detect_application_boundaries,
    detect_project_context,
    is_example_or_fixture,
    resolve_file_scope,
)


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
        role = classify_source_role(path)
        if role != "application_source":
            continue
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


def _inspect_python_test_functions(
    content: str,
    route_path: str,
    route_func: str,
) -> tuple[bool, bool, bool]:
    """Inspect Python test file using AST at individual function level.

    Returns (has_assertion_candidate, has_reference_candidate, has_code_mention).
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return (False, False, False)

    norm_route = normalize_route_path(route_path)
    clean_path = route_path.strip("/")

    # Check all string literals in the AST to distinguish code from comments
    all_ast_strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            all_ast_strings.append(node.value)

    has_code_mention = any(
        norm_route == normalize_route_path(s) or (clean_path and clean_path in s)
        for s in all_ast_strings
    ) or any(
        isinstance(node, ast.Name) and node.id == route_func
        for node in ast.walk(tree)
    )

    has_assertion_candidate = False
    has_reference_candidate = False

    def is_matching_url(val: str) -> bool:
        norm_val = normalize_route_path(val)
        return norm_val == norm_route or match_route(val, route_path)

    # Check function definitions
    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_has_call = False
        func_has_response_assertion = False
        response_var_names: set[str] = {"response", "res", "resp", "r", "result"}

        for node in ast.walk(func_node):
            # Check for route invocation
            if isinstance(node, ast.Call):
                method_name = ""
                if isinstance(node.func, ast.Attribute):
                    method_name = node.func.attr.lower()
                elif isinstance(node.func, ast.Name):
                    method_name = node.func.id.lower()

                if method_name in ("get", "post", "put", "delete", "patch", "head", "options", "request"):
                    url_val = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        url_val = node.args[0].value
                    for kw in node.keywords:
                        if kw.arg in ("url", "path") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            url_val = kw.value.value

                    if url_val and is_matching_url(url_val):
                        func_has_call = True

            # Track variable assignment to HTTP response
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    call = node.value
                    call_method = ""
                    if isinstance(call.func, ast.Attribute):
                        call_method = call.func.attr.lower()
                    if call_method in ("get", "post", "put", "delete", "patch", "head", "options", "request"):
                        url_val = None
                        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                            url_val = call.args[0].value
                        for kw in call.keywords:
                            if kw.arg in ("url", "path") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                url_val = kw.value.value
                        if url_val and is_matching_url(url_val):
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    response_var_names.add(target.id)

            # Check for response assertions within this same function
            if isinstance(node, ast.Assert):
                test_node = node.test
                # Ignore constant asserts like assert True or assert 1
                if not (isinstance(test_node, ast.Constant) and test_node.value is True):
                    assert_text = ""
                    try:
                        assert_text = ast.unparse(test_node)
                    except Exception:
                        pass
                    if any(v in assert_text for v in response_var_names) or any(
                        attr in assert_text for attr in ("status_code", "status", "json()", "data", "text", "content")
                    ):
                        func_has_response_assertion = True

            # Check for unittest style assertions: self.assertEqual(res.status_code, 200)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Attribute) and (
                    call.func.attr.startswith("assert") or call.func.attr in ("expect",)
                ):
                    call_text = ""
                    try:
                        call_text = ast.unparse(call)
                    except Exception:
                        pass
                    if any(v in call_text for v in response_var_names) or any(
                        attr in call_text for attr in ("status_code", "status", "json()", "data", "text", "content")
                    ):
                        func_has_response_assertion = True

        if func_has_call and func_has_response_assertion:
            has_assertion_candidate = True
        elif func_has_call:
            has_reference_candidate = True

    if not has_assertion_candidate and has_code_mention:
        has_reference_candidate = True

    return (has_assertion_candidate, has_reference_candidate, has_code_mention)


def _inspect_js_test_blocks(
    content: str,
    route_path: str,
) -> tuple[bool, bool, bool]:
    """Inspect JavaScript/TypeScript test files at individual test block level."""
    clean_path = route_path.strip("/")
    path_regex = re.escape(clean_path)

    # Strip JS comments to distinguish code from comments
    stripped = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    stripped = re.sub(r"/\*[\s\S]*?\*/", "", stripped)

    has_code_mention = bool(re.search(rf"""['"][^'"]*{path_regex}['"]""", stripped))
    has_assertion_candidate = False
    has_reference_candidate = False

    test_block_pattern = re.compile(
        r"""(?:test|it)\s*\(\s*['"][^'"]*['"]\s*,\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_]+)\s*=>\s*\{([\s\S]*?)\n\s*\}\s*\)""",
        re.MULTILINE,
    )

    for block_match in test_block_pattern.finditer(stripped):
        block = block_match.group(1)
        block_has_call = bool(
            re.search(rf"""(?:fetch|axios(?:\.[a-z]+)?|request\([^)]*\)\.[a-z]+|\$\.ajax)\s*\(\s*['"][^'"]*{path_regex}""", block)
        )
        block_has_assert = bool(
            re.search(r"""(?:expect\s*\(|\.toBe\(|\.toEqual\(|assert\.)""", block)
            and re.search(r"""\b(?:res|response|status|body|data)\b""", block)
        )
        if block_has_call and block_has_assert:
            has_assertion_candidate = True
            break
        elif block_has_call:
            has_reference_candidate = True

    if not has_assertion_candidate and has_code_mention:
        has_reference_candidate = True

    return (has_assertion_candidate, has_reference_candidate, has_code_mention)


def _evaluate_route_test_coverage(
    route: RouteDefinition,
    test_files_data: list[tuple[str, str]],
) -> str:
    """Evaluate whether a route is test_assertion_candidate, test_reference_candidate, or testing_gap_candidate.

    NOTE: Static analysis NEVER returns 'test_verified'; that status is reserved
    exclusively for runtime journey execution with verified assertions.
    """
    path = route.path
    func = route.function

    any_assertion_candidate = False
    any_reference_candidate = False

    for file_path, content in test_files_data:
        if file_path.endswith(".py"):
            has_assert, has_ref, has_code = _inspect_python_test_functions(content, path, func)
        else:
            has_assert, has_ref, has_code = _inspect_js_test_blocks(content, path)

        if has_assert:
            any_assertion_candidate = True
            break
        if has_ref:
            any_reference_candidate = True

    if any_assertion_candidate:
        return "test_assertion_candidate"
    if any_reference_candidate:
        return "test_reference_candidate"
    return "testing_gap_candidate"


def audit_dependencies(
    project_root: Path,
    detected_imports: list[str] | None = None,
    application_boundaries: list[dict[str, Any]] | None = None,
    imports_by_app: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Inspect project package manifests against detected imports for dependency hygiene.

    Attributes dependencies to owning application boundary and distinguishes
    runtime, dev, test, build, and unsupported inventory-only manifests.
    """
    root = project_root.resolve()
    boundaries = application_boundaries or detect_application_boundaries(root)
    all_imports = detected_imports or []
    by_app_imports = imports_by_app or {}

    manifests_found: list[dict[str, Any]] = []
    inventory_only_manifests: list[dict[str, Any]] = []
    declared_dependencies: list[dict[str, Any]] = []
    unused_candidates: list[dict[str, Any]] = []

    # Common tooling that should not be flagged as unused runtime dependencies
    common_tool_packages = {
        "pytest", "ruff", "mypy", "black", "flake8", "coverage", "tox",
        "playwright", "typer", "pydantic", "pip", "setuptools", "wheel",
        "typescript", "eslint", "prettier", "jest", "vitest", "webpack", "vite",
        "babel", "postcss", "tailwindcss",
    }

    # Helper to find owning application for a manifest file
    def get_owning_app(rel_manifest_path: str) -> str:
        for b in sorted(boundaries, key=lambda x: len(x["relative_path"]), reverse=True):
            b_path = b["relative_path"]
            if b_path != "." and (rel_manifest_path == b_path or rel_manifest_path.startswith(f"{b_path}/")):
                return b["app_name"]
        root_b = next((b for b in boundaries if b.get("is_root")), None)
        return root_b["app_name"] if root_b else "primary"

    # Walk repository for manifests
    for path in root.rglob("*"):
        if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue

        name_lower = path.name.lower()
        rel_posix = path.relative_to(root).as_posix()
        app_name = get_owning_app(rel_posix)

        # 1. pyproject.toml
        if name_lower == "pyproject.toml":
            manifest_info = {
                "manifest": rel_posix,
                "ecosystem": "Python (pyproject.toml)",
                "app_name": app_name,
                "usage_analysis_supported": True,
            }
            manifests_found.append(manifest_info)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                current_section = ""
                for line in content.splitlines():
                    clean = line.strip()
                    if clean.startswith("["):
                        current_section = clean
                        continue
                    if "[project.dependencies]" in current_section or current_section == "dependencies = [":
                        m = re.match(r"""^['"]([a-zA-Z0-9_.-]+)""", clean)
                        if m:
                            pkg = m.group(1).lower().replace("-", "_")
                            declared_dependencies.append({
                                "package": pkg,
                                "raw_package": m.group(1),
                                "manifest": rel_posix,
                                "app_name": app_name,
                                "dependency_type": "runtime",
                            })
                    elif "optional-dependencies" in current_section or "dev" in current_section:
                        m = re.match(r"""^['"]([a-zA-Z0-9_.-]+)""", clean)
                        if m:
                            pkg = m.group(1).lower().replace("-", "_")
                            declared_dependencies.append({
                                "package": pkg,
                                "raw_package": m.group(1),
                                "manifest": rel_posix,
                                "app_name": app_name,
                                "dependency_type": "dev" if "dev" in current_section else "optional",
                            })
                    elif "build-system" in current_section:
                        m = re.match(r"""^['"]([a-zA-Z0-9_.-]+)""", clean)
                        if m:
                            pkg = m.group(1).lower().replace("-", "_")
                            declared_dependencies.append({
                                "package": pkg,
                                "raw_package": m.group(1),
                                "manifest": rel_posix,
                                "app_name": app_name,
                                "dependency_type": "build",
                            })
            except OSError:
                pass

        # 2. requirements.txt / requirements-*.txt
        elif (name_lower.startswith("requirements") or name_lower.endswith("requirements.txt")) and path.suffix == ".txt":
            is_dev = "dev" in name_lower or "test" in name_lower
            manifest_info = {
                "manifest": rel_posix,
                "ecosystem": "Python (requirements.txt)",
                "app_name": app_name,
                "usage_analysis_supported": True,
            }
            manifests_found.append(manifest_info)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith(("#", "-", "http://", "https://")):
                        m = re.match(r"""^([a-zA-Z0-9_.-]+)""", clean)
                        if m:
                            pkg = m.group(1).lower().replace("-", "_")
                            declared_dependencies.append({
                                "package": pkg,
                                "raw_package": m.group(1),
                                "manifest": rel_posix,
                                "app_name": app_name,
                                "dependency_type": "dev" if is_dev else "runtime",
                            })
            except OSError:
                pass

        # 3. package.json
        elif name_lower == "package.json":
            manifest_info = {
                "manifest": rel_posix,
                "ecosystem": "JavaScript/TypeScript (package.json)",
                "app_name": app_name,
                "usage_analysis_supported": True,
            }
            manifests_found.append(manifest_info)
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                # Runtime dependencies
                for d in data.get("dependencies", {}).keys():
                    declared_dependencies.append({
                        "package": d.lower(),
                        "raw_package": d,
                        "manifest": rel_posix,
                        "app_name": app_name,
                        "dependency_type": "runtime",
                    })
                # Dev dependencies
                for d in data.get("devDependencies", {}).keys():
                    declared_dependencies.append({
                        "package": d.lower(),
                        "raw_package": d,
                        "manifest": rel_posix,
                        "app_name": app_name,
                        "dependency_type": "dev",
                    })
                # Peer/Optional
                for d in data.get("peerDependencies", {}).keys():
                    declared_dependencies.append({
                        "package": d.lower(),
                        "raw_package": d,
                        "manifest": rel_posix,
                        "app_name": app_name,
                        "dependency_type": "optional",
                    })
            except Exception:
                pass

        # 4. Inventory-only manifests (Rust, Go, Java, PHP, Ruby)
        elif name_lower in ("cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json", "gemfile"):
            ecosystem_names = {
                "cargo.toml": "Rust (Cargo.toml)",
                "go.mod": "Go (go.mod)",
                "pom.xml": "Java (Maven pom.xml)",
                "build.gradle": "Java/Kotlin (Gradle build.gradle)",
                "composer.json": "PHP (Composer composer.json)",
                "gemfile": "Ruby (Bundler Gemfile)",
            }
            ecosystem = ecosystem_names.get(name_lower, name_lower)
            inv_entry = {
                "manifest": rel_posix,
                "ecosystem": ecosystem,
                "app_name": app_name,
                "usage_analysis_supported": False,
                "analysis_status": "inventory-only",
                "explanation": f"Manifest detected for inventory purposes. Dependency import usage analysis is not currently supported for {ecosystem}.",
            }
            manifests_found.append(inv_entry)
            inventory_only_manifests.append(inv_entry)

    # Evaluate runtime dependencies against detected imports per application
    for dep in declared_dependencies:
        if dep["dependency_type"] != "runtime":
            continue
        pkg = dep["package"]
        if pkg in common_tool_packages:
            continue

        app_name = dep["app_name"]
        app_imports = by_app_imports.get(app_name, all_imports)
        normalized_imports = {imp.lower().replace("-", "_") for imp in app_imports}

        is_imported = any(
            pkg == imp or imp.startswith(f"{pkg}.") or imp.startswith(f"{pkg}/")
            for imp in normalized_imports
        )
        if not is_imported:
            scope_info = resolve_file_scope(dep["manifest"], root, boundaries)
            unused_candidates.append({
                "id": f"dep-unused-{len(unused_candidates) + 1}",
                "package": dep["raw_package"],
                "manifest": dep["manifest"],
                "app_name": app_name,
                "source_role": scope_info["source_role"],
                "scope": scope_info["scope"],
                "category": "potentially_unused_dependency",
                "dependency_type": "runtime",
                "severity": "Low",
                "confidence": "Medium",
                "finding_state": "Requires Owner Confirmation",
                "explanation": f"Package '{dep['raw_package']}' is declared as a runtime dependency in {dep['manifest']} ({app_name}) but has no direct import references in application code.",
                "why_false_positive": "Package may be a CLI tool, build utility, dev dependency, or imported dynamically via plugins.",
                "recommended_action": "Verify if this package is still required before removing it from dependencies.",
            })

    return {
        "manifests_found": [m["manifest"] for m in manifests_found],
        "manifest_details": manifests_found,
        "total_declared": len(declared_dependencies),
        "inventory_only_manifests": inventory_only_manifests,
        "potentially_unused": unused_candidates,
    }


def _detect_reverse_proxies(root: Path) -> list[dict[str, Any]]:
    """Detect reverse proxy, gateway, and rewrite configurations across the repository."""
    proxies: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if not path.is_file():
            continue

        name_lower = path.name.lower()
        rel_posix = path.relative_to(root).as_posix()

        # Next.js rewrites
        if name_lower in ("next.config.js", "next.config.mjs", "next.config.ts"):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if "rewrites" in content or "redirects" in content:
                    proxies.append({
                        "file": rel_posix,
                        "type": "Next.js Rewrites/Redirects",
                        "confidence": "Medium",
                    })
            except OSError:
                pass

        # Vite proxy
        elif name_lower in ("vite.config.js", "vite.config.ts", "vite.config.mjs"):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if "proxy" in content:
                    proxies.append({
                        "file": rel_posix,
                        "type": "Vite Dev Proxy",
                        "confidence": "Medium",
                    })
            except OSError:
                pass

        # Nginx
        elif name_lower in ("nginx.conf", "default.conf") or path.suffix == ".conf":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if "proxy_pass" in content:
                    proxies.append({
                        "file": rel_posix,
                        "type": "Nginx Reverse Proxy",
                        "confidence": "High",
                    })
            except OSError:
                pass

    return proxies


def audit_repository(project_root: Path, include_examples: bool = False) -> dict[str, Any]:
    """Comprehensive multi-language repository audit with ghost feature detection and scope awareness."""
    root = project_root.resolve()
    registry = LanguageRegistry()
    scan_data = registry.scan_repository(root)

    # 1. Project Context & Application Boundaries
    context = detect_project_context(root)
    app_boundaries = scan_data.get("application_boundaries", [])
    reverse_proxies = _detect_reverse_proxies(root)
    has_reverse_proxy = len(reverse_proxies) > 0

    # 2. Ghost Features (Already tagged with source_role, app_name, and scope)
    ghost_features = detect_ghost_features(root, scan_data)

    # 3. Routes & Mismatches
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    client_calls: list[ClientCall] = scan_data.get("client_calls", [])

    missing_route_candidates = []
    method_mismatches = []
    potentially_unused_endpoints = []
    uncovered_routes = []

    # Check test files with AST assertion and invocation awareness
    test_files_data: list[tuple[str, str]] = []
    for test_path in root.rglob("*"):
        if any(part in IGNORED_DIRECTORIES for part in test_path.parts):
            continue
        if test_path.is_file():
            role = classify_source_role(test_path.relative_to(root).as_posix(), root)
            if role in ("test", "fixture") or "test" in test_path.name.lower():
                try:
                    test_files_data.append((test_path.as_posix(), test_path.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    pass

    # Recursively scan all markdown and restructured text documentation
    doc_text = ""
    for ext in ("*.md", "*.rst"):
        for doc in root.rglob(ext):
            if any(part in IGNORED_DIRECTORIES for part in doc.parts):
                continue
            if doc.is_file():
                try:
                    doc_text += doc.read_text(encoding="utf-8", errors="ignore") + "\n"
                except OSError:
                    pass

    for call in client_calls:
        endpoint = call.path
        req_method = call.method.upper()

        # Recognize external service calls
        if endpoint.startswith(("http://", "https://", "//")) or any(
            domain in endpoint for domain in ("api.stripe.com", "auth0.com", "github.com", "googleapis.com", "paypal.com", "twilio.com")
        ):
            call.call_type = "external_service_call"
            continue

        matching = [r for r in routes if match_route(endpoint, r.path)]
        local_matching = [r for r in matching if r.app_name == call.app_name]
        cross_service_matching = [r for r in matching if r.app_name != call.app_name]

        if not matching:
            # Check if this endpoint is candidate for reverse-proxy handling
            if has_reverse_proxy:
                call.call_type = "reverse_proxy_candidate"
                missing_route_candidates.append({
                    "id": f"missing-route-{len(missing_route_candidates) + 1}",
                    "category": "reverse_proxy_candidate",
                    "severity": "Low",
                    "confidence": "Low",
                    "finding_state": "Requires Owner Confirmation",
                    "evidence": call.raw,
                    "source": call.source,
                    "line": call.line,
                    "endpoint": endpoint,
                    "method": req_method,
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
                    "explanation": f"Client calls '{req_method} {endpoint}', which has no matching local backend route, but reverse-proxy configurations were detected ({', '.join(p['file'] for p in reverse_proxies)}).",
                    "potential_impact": "Request may be handled by an upstream service or fail if proxy rules are incomplete.",
                    "why_false_positive": "Endpoint is forwarded to an external microservice or upstream API by reverse proxy rules.",
                    "recommended_action": "Verify upstream proxy target in reverse proxy configuration.",
                })
            elif endpoint.startswith(("/api", "/v1", "/v2")):
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
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
                    "explanation": f"Client calls '{req_method} {endpoint}', but no backend route handler was registered.",
                    "potential_impact": "Client requests will likely fail with HTTP 404.",
                    "why_false_positive": "Endpoint may be served by an external microservice, reverse proxy, or dynamic route loader.",
                    "recommended_action": "Verify if the route is implemented in another service or implement the missing endpoint.",
                })
        else:
            # If cross-service matching
            if not local_matching and cross_service_matching:
                call.call_type = "matching_service_route"
                call.target_service = cross_service_matching[0].app_name

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
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
                    "explanation": f"Client calls {req_method} on '{endpoint}', but route only accepts {sorted(supported)}.",
                    "potential_impact": "Requests will fail with HTTP 405 Method Not Allowed.",
                    "why_false_positive": "Method might be rewritten by gateway or middleware.",
                    "recommended_action": f"Add {req_method} to route handler or update client method.",
                })

    for route in routes:
        path = route.path
        func = route.function
        frontend_refs = [c for c in client_calls if match_route(c.path, path)]
        cov_status = _evaluate_route_test_coverage(route, test_files_data)
        in_docs = path in doc_text

        if cov_status != "test_assertion_candidate":
            uncovered_routes.append({
                "id": f"uncovered-{len(uncovered_routes) + 1}",
                "category": "testing_gap",
                "coverage_status": cov_status,
                "severity": "Medium",
                "confidence": "High",
                "endpoint": path,
                "methods": route.methods,
                "source": route.source,
                "line": route.line,
                "source_role": route.source_role,
                "app_name": route.app_name,
                "scope": route.scope,
                "explanation": (
                    f"Route '{path}' ({func}) is mentioned in test files but lacks verified test execution and assertions."
                    if cov_status == "test_reference_candidate"
                    else f"Route '{path}' ({func}) has no identified assertions in the test suite."
                ),
                "recommended_action": "Add an integration or unit test verifying this route.",
            })

        if not frontend_refs and cov_status == "testing_gap_candidate" and not in_docs:
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
                "source_role": route.source_role,
                "app_name": route.app_name,
                "scope": route.scope,
                "explanation": f"Endpoint '{path}' has no static callers in frontend, tests, or documentation.",
                "why_false_positive": "Endpoint may be consumed by external webhooks, mobile apps, or public API clients.",
                "recommended_action": "Confirm with feature owner before deprecating or removing.",
            })

    # 4. Empty & Unfinished Implementations
    unfinished_items = scan_data.get("unfinished", [])
    empty_candidates = []
    for item in unfinished_items:
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
            "source_role": item.source_role,
            "app_name": item.app_name,
            "scope": item.scope,
            "explanation": item.explanation,
            "why_intentional": item.why_intentional,
            "recommended_action": "Complete the implementation or document intentional stub behavior.",
        })

    # 5. Dependency Hygiene
    dep_audit = audit_dependencies(
        root,
        detected_imports=scan_data.get("imports", []),
        application_boundaries=app_boundaries,
        imports_by_app=scan_data.get("imports_by_app", {}),
    )

    # 6. Structural Duplicate Logic (application source files only)
    py_files = [
        root / p.source for p in scan_data.get("symbols", [])
        if p.source.endswith(".py") and p.source_role == "application_source"
    ]
    unique_py_files = list({root / Path(p): p for p in py_files if (root / Path(p)).is_file()}.keys())
    duplicates = estimate_duplicate_blocks(unique_py_files)
    for d in duplicates:
        d["scope"] = "primary_application"
        d["source_role"] = "application_source"

    total_waste_lines = sum(d.get("estimated_waste_lines", 0) for d in duplicates)

    # 7. Scope Segregation
    primary_app_findings = {
        "ghost_features": [f for f in ghost_features if f.get("scope") == "primary_application"],
        "empty_or_unfinished": [f for f in empty_candidates if f.get("scope") == "primary_application"],
        "missing_route_candidates": [f for f in missing_route_candidates if f.get("scope") == "primary_application"],
        "method_mismatches": [f for f in method_mismatches if f.get("scope") == "primary_application"],
        "potentially_unused_endpoints": [f for f in potentially_unused_endpoints if f.get("scope") == "primary_application"],
        "uncovered_routes": [f for f in uncovered_routes if f.get("scope") == "primary_application"],
        "duplicate_logic": [f for f in duplicates if f.get("scope") == "primary_application"],
        "potentially_unused_dependencies": [f for f in dep_audit.get("potentially_unused", []) if f.get("scope") == "primary_application"],
    }

    example_findings = {
        "ghost_features": [f for f in ghost_features if f.get("scope") == "example"],
        "empty_or_unfinished": [f for f in empty_candidates if f.get("scope") == "example"],
        "missing_route_candidates": [f for f in missing_route_candidates if f.get("scope") == "example"],
        "method_mismatches": [f for f in method_mismatches if f.get("scope") == "example"],
        "potentially_unused_endpoints": [f for f in potentially_unused_endpoints if f.get("scope") == "example"],
        "uncovered_routes": [f for f in uncovered_routes if f.get("scope") == "example"],
        "duplicate_logic": [f for f in duplicates if f.get("scope") == "example"],
        "potentially_unused_dependencies": [f for f in dep_audit.get("potentially_unused", []) if f.get("scope") == "example"],
    }

    test_and_fixture_findings = {
        "ghost_features": [f for f in ghost_features if f.get("scope") == "test_and_fixture"],
        "empty_or_unfinished": [f for f in empty_candidates if f.get("scope") == "test_and_fixture"],
        "duplicate_logic": [f for f in duplicates if f.get("scope") == "test_and_fixture"],
    }

    doc_and_contract_findings = {
        "ghost_features": [f for f in ghost_features if f.get("scope") == "documentation_and_contract"],
        "empty_or_unfinished": [f for f in empty_candidates if f.get("scope") == "documentation_and_contract"],
    }

    # Determine top-level lists: by default, show primary_application findings unless include_examples is True
    if include_examples:
        effective_ghost = ghost_features
        effective_empty = empty_candidates
        effective_missing = missing_route_candidates
        effective_mismatches = method_mismatches
        effective_unused_endpoints = potentially_unused_endpoints
        effective_uncovered = uncovered_routes
    else:
        effective_ghost = primary_app_findings["ghost_features"]
        effective_empty = primary_app_findings["empty_or_unfinished"]
        effective_missing = primary_app_findings["missing_route_candidates"]
        effective_mismatches = primary_app_findings["method_mismatches"]
        effective_unused_endpoints = primary_app_findings["potentially_unused_endpoints"]
        effective_uncovered = primary_app_findings["uncovered_routes"]

    return {
        "schema_version": "2.0",
        "project_context": context,
        "capability_matrix": scan_data.get("capability_matrix", []),
        "detected_languages": scan_data.get("detected_languages", []),
        "frameworks": scan_data.get("frameworks", []),
        "application_boundaries": app_boundaries,
        "source_role_inventory": scan_data.get("source_role_inventory", {}),
        "reverse_proxies": reverse_proxies,
        "include_examples": include_examples,
        "file_count": scan_data.get("file_count", 0),
        "file_limit": scan_data.get("file_limit", 15000),
        "scan_truncated": scan_data.get("scan_truncated", False),
        "total_routes": len(routes),
        "total_client_calls": len(client_calls),
        "total_components": len(scan_data.get("components", [])),
        "total_ui_actions": len(scan_data.get("ui_actions", [])),
        "primary_application_findings": primary_app_findings,
        "example_findings": example_findings,
        "test_and_fixture_findings": test_and_fixture_findings,
        "documentation_and_contract_findings": doc_and_contract_findings,
        "ghost_features": effective_ghost,
        "empty_or_unfinished": effective_empty,
        "missing_route_candidates": effective_missing,
        "method_mismatches": effective_mismatches,
        "potentially_unused_endpoints": effective_unused_endpoints,
        "uncovered_routes": effective_uncovered,
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
            "Static analysis identifies candidate assertions only; test_verified requires runtime journey execution.",
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
