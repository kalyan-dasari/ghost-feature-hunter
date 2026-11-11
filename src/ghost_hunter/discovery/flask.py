"""Read-only Python/Flask discovery using syntax trees; application files are never imported."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "ghost-reports",
    "node_modules",
    "venv",
}
FRONTEND_SUFFIXES = {".html", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _call_attribute(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _route_from_decorator(node: ast.AST) -> dict[str, Any] | None:
    attribute = _call_attribute(node)
    method_defaults = {
        "get": ["GET"],
        "post": ["POST"],
        "put": ["PUT"],
        "patch": ["PATCH"],
        "delete": ["DELETE"],
        "options": ["OPTIONS"],
        "head": ["HEAD"],
    }
    if attribute != "route" and attribute not in method_defaults:
        return None
    assert isinstance(node, ast.Call)
    route = _literal(node.args[0]) if node.args else None
    if not isinstance(route, str):
        return None
    methods = method_defaults.get(attribute, ["GET"])
    for keyword in node.keywords:
        if keyword.arg == "methods":
            raw_methods = _literal(keyword.value)
            if isinstance(raw_methods, (list, tuple, set)):
                methods = sorted(str(method).upper() for method in raw_methods)
    return {"path": route, "methods": methods}


def discover_project(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    routes: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    tests: list[str] = []
    frontend: list[str] = []
    service_files: list[str] = []
    python_files: list[Path] = []
    parse_errors: list[dict[str, str]] = []
    file_count = 0

    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        file_count += 1
        if file_count > 20000:
            return {
                "schema_version": "1.0",
                "analysis_mode": "static",
                "runtime_verified": False,
                "project_path": str(root),
                "framework_support": "partial",
                "routes": routes,
                "models": models,
                "tests": tests,
                "frontend_files": frontend,
                "service_files": service_files,
                "parse_errors": parse_errors,
                "limitations": ["Discovery stopped after 20,000 files to bound traversal."],
            }
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() in FRONTEND_SUFFIXES:
            frontend.append(relative)
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            tests.append(relative)
        if any(tag in path.stem.lower() for tag in ("service", "controller", "route", "endpoint", "api")):
            service_files.append(relative)
        if path.suffix == ".py":
            python_files.append(path)

    flask_signal = False
    for path in python_files:
        relative = path.relative_to(root).as_posix()
        try:
            if path.stat().st_size > 1_000_000:
                parse_errors.append({"path": relative, "reason": "Skipped Python file larger than 1 MB."})
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            parse_errors.append({"path": relative, "reason": type(exc).__name__})
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                flask_signal |= any(alias.name == "flask" or alias.name.startswith("flask.") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                flask_signal |= bool(node.module and (node.module == "flask" or node.module.startswith("flask.")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route = _route_from_decorator(decorator)
                    if route is not None:
                        flask_signal = True
                        routes.append(
                            {
                                **route,
                                "function": node.name,
                                "path": route["path"],
                                "source": relative,
                                "line": decorator.lineno,
                            }
                        )
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(base) for base in node.bases]
                if any(
                    base.endswith("Model") or base.endswith("DeclarativeBase") or base == "Base"
                    for base in bases
                ):
                    models.append({"class": node.name, "source": relative, "line": node.lineno})

    routes.sort(key=lambda item: (item["source"], item["line"]))
    return {
        "schema_version": "1.0",
        "analysis_mode": "static",
        "runtime_verified": False,
        "project_path": str(root),
        "framework_support": "Flask static route conventions" if flask_signal else "not detected",
        "routes": routes,
        "models": models,
        "tests": sorted(tests),
        "frontend_files": sorted(frontend),
        "service_files": sorted(service_files),
        "parse_errors": parse_errors,
        "limitations": [
            "Static analysis only; files are not imported or executed.",
            "Only literal Flask-style route paths and common SQLAlchemy model base names are detected.",
            "Discovery is advisory and does not define expected feature behavior.",
        ],
    }


def render_discovery_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Ghost Feature Hunter discovery",
        "",
        f"- Project: `{result['project_path']}`",
        "- Analysis: static syntax scan; runtime behavior was not verified.",
        f"- Framework support: {result['framework_support']}",
        "",
        "## Routes",
        "",
    ]
    if result["routes"]:
        lines.extend(
            f"- `{', '.join(route['methods'])} {route['path']}` → `{route['function']}` "
            f"({route['source']}:{route['line']})"
            for route in result["routes"]
        )
    else:
        lines.append("No literal Flask routes detected.")
    for title, key in (("Database models", "models"), ("Existing tests", "tests"), ("Frontend files", "frontend_files"), ("Service/controller files", "service_files")):
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- `{item if isinstance(item, str) else item['class'] + ' (' + item['source'] + ')'}`" for item in result[key])
        if not result[key]:
            lines.append("None detected.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def write_discovery(result: dict[str, Any], output_dir: Path, *, force: bool = False) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ghost-discovery.json"
    markdown_path = output_dir / "ghost-discovery.md"
    existing = [path for path in (json_path, markdown_path) if path.exists()]
    if existing and not force:
        raise FileExistsError(f"Refusing to overwrite discovery file(s): {', '.join(map(str, existing))}; use --force")
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_discovery_markdown(result), encoding="utf-8")
    return json_path, markdown_path
