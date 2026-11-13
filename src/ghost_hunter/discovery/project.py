"""Project context detection, scope locking, and component classification.

Distinguishes primary application source from examples, demos, and fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

IGNORED_DIRECTORIES = {
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
    ".eggs",
}

EXAMPLE_AND_FIXTURE_NAMES = {
    "example",
    "examples",
    "fixture",
    "fixtures",
    "demo",
    "demos",
    "sample",
    "samples",
    "benchmark",
    "benchmarks",
    "mock",
    "mocks",
}


def find_git_root(start_dir: Path) -> Path | None:
    current = start_dir.resolve()
    for directory in [current, *current.parents]:
        if (directory / ".git").is_dir():
            return directory
    return None


def detect_project_name(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.strip().startswith("name ="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "name" in data:
                return str(data["name"])
        except (OSError, json.JSONDecodeError):
            pass

    return root.name


def is_example_or_fixture(rel_path: Path | str) -> bool:
    parts = Path(rel_path).parts
    return any(part.lower() in EXAMPLE_AND_FIXTURE_NAMES for part in parts)


def detect_frameworks(python_files: list[Path], root: Path) -> list[dict[str, str]]:
    frameworks: list[dict[str, str]] = []
    signals: dict[str, str] = {}

    for path in python_files[:500]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "from flask import" in content or "import flask" in content:
            signals["Flask"] = "supported"
        if "from fastapi import" in content or "import fastapi" in content:
            signals["FastAPI"] = "partial"
        if "from django" in content or "import django" in content:
            signals["Django"] = "partial"

    if (root / "package.json").is_file():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                signals["Next.js"] = "partial"
            if "express" in deps:
                signals["Express"] = "partial"
            if "react" in deps:
                signals["React"] = "detected"
        except (OSError, json.JSONDecodeError):
            pass

    for name, status in sorted(signals.items()):
        frameworks.append({"name": name, "status": status})

    if not frameworks:
        frameworks.append({"name": "Generic / Static", "status": "partial"})

    return frameworks


def detect_project_context(
    project_root: Path,
    *,
    explicit_app_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect and classify the project context and application boundaries."""
    root = project_root.resolve()
    git_root = find_git_root(root)
    project_name = detect_project_name(root)

    primary_source: list[str] = []
    test_files: list[str] = []
    doc_files: list[str] = []
    example_fixtures: list[str] = []
    python_files: list[Path] = []
    languages_seen: set[str] = set()

    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue

        rel = path.relative_to(root)
        rel_posix = rel.as_posix()

        # Track language
        suffix = path.suffix.lower()
        if suffix in {".py", ".pyw"}:
            languages_seen.add("Python")
            python_files.append(path)
        elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            languages_seen.add("JavaScript")
        elif suffix in {".ts", ".tsx"}:
            languages_seen.add("TypeScript")
        elif suffix in {".html", ".htm"}:
            languages_seen.add("HTML")
        elif suffix == ".css":
            languages_seen.add("CSS")
        elif suffix == ".json":
            languages_seen.add("JSON")
        elif suffix == ".md":
            languages_seen.add("Markdown")

        # Classify directory
        if is_example_or_fixture(rel):
            example_fixtures.append(rel_posix)
        elif path.name.startswith("test_") or path.name.endswith("_test.py") or "test" in rel.parts:
            test_files.append(rel_posix)
        elif rel.parts[0] in {"docs", "doc"} or suffix in {".md", ".rst"}:
            doc_files.append(rel_posix)
        elif rel.parts[0] in {"src", "lib", "app", "skills", "integrations"} or (len(rel.parts) == 1 and suffix in {".py", ".ts", ".js"}):
            primary_source.append(rel_posix)

    # Determine selected application root
    if explicit_app_root is not None:
        selected_root = explicit_app_root.resolve()
    else:
        # Default to root or src/ if it exists
        if (root / "src").is_dir():
            selected_root = root / "src"
        else:
            selected_root = root

    frameworks = detect_frameworks(python_files, root)

    return {
        "project_name": project_name,
        "project_root": str(root),
        "git_root": str(git_root) if git_root else None,
        "selected_app_root": str(selected_root),
        "explicit_app_root_provided": explicit_app_root is not None,
        "languages": sorted(languages_seen),
        "frameworks": frameworks,
        "primary_source_count": len(primary_source),
        "test_count": len(test_files),
        "doc_count": len(doc_files),
        "example_fixture_count": len(example_fixtures),
        "example_fixture_dirs": sorted({Path(p).parts[0] for p in example_fixtures}),
        "limitations": [
            "Examples and benchmarks are classified separately from primary application source.",
            "Static discovery does not infer authoritative user requirements from code patterns.",
            "Dynamic imports, reflection, and runtime plugin hooks require manual verification.",
        ],
    }
