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
    ".next",
    "vendor",
    "coverage",
    ".turbo",
    ".nuxt",
    ".cache",
    "out",
    "target",
    "bin",
    "obj",
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


def classify_source_role(rel_path: Path | str, root: Path | None = None) -> str:
    """Classify any file into an explicit source role category."""
    path = Path(rel_path)
    parts_lower = [p.lower() for p in path.parts]
    name_lower = path.name.lower()
    suffix_lower = path.suffix.lower()

    # 1. Vendor
    if any(p in {"vendor", "node_modules", "site-packages", "third_party", "bower_components"} for p in parts_lower):
        return "vendor"

    # 2. Build output
    if any(p in {"build", "dist", "out", "target", ".next", "bin", "obj", ".turbo", ".nuxt", ".cache"} for p in parts_lower):
        return "build_output"

    # 3. Generated
    if (
        name_lower.endswith((".min.js", ".min.css", ".bundle.js", ".bundle.css"))
        or name_lower in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "cargo.lock", "poetry.lock"}
        or name_lower.endswith(("_pb2.py", "_pb2_grpc.py", ".generated.ts", ".generated.js"))
        or any(p in {".eggs", "egg-info"} or p.endswith(".egg-info") for p in parts_lower)
    ):
        return "generated"

    # 4. Test
    if (
        any(p in {"tests", "test", "__tests__", "spec", "specs", "e2e"} for p in parts_lower)
        or name_lower.startswith(("test_", "test-"))
        or name_lower.endswith(("_test.py", "-test.py", ".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"))
    ):
        return "test"

    # 5. Fixture
    if any(p in {"fixture", "fixtures", "mock", "mocks", "testdata", "test_data", "__mocks__"} for p in parts_lower):
        return "fixture"

    # 6. Benchmark
    if any(p in {"benchmark", "benchmarks", "perf", "perfs"} for p in parts_lower):
        return "benchmark"

    # 7. Demo
    if any(p in {"demo", "demos"} for p in parts_lower):
        return "demo"

    # 8. Example
    if any(p in {"example", "examples", "sample", "samples"} for p in parts_lower):
        return "example"

    # 9. API Contract
    if (
        name_lower in {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml"}
        or suffix_lower in {".proto", ".graphql", ".gql"}
        or (name_lower.endswith(".schema.json") and "schema" in parts_lower)
    ):
        return "api_contract"

    # 10. Documentation
    if (
        any(p in {"docs", "doc"} for p in parts_lower)
        or suffix_lower in {".md", ".rst"}
        or name_lower in {"license", "license.txt", "notice", "contributing", "changelog", "readme"}
    ):
        return "documentation"

    # 11. Configuration
    if (
        name_lower in {
            "pyproject.toml", "package.json", "tsconfig.json", "jsconfig.json",
            "setup.py", "setup.cfg", "pipfile", "gemfile", "cargo.toml", "go.mod",
            "pom.xml", "build.gradle", "composer.json", "dockerfile", "docker-compose.yml",
            "docker-compose.yaml", "ghost-hunter.json", ".gitignore", ".env", ".env.example",
            "pytest.ini", "tox.ini", ".flake8", "ruff.toml", ".eslintrc", ".eslintrc.json",
            ".prettierrc", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
            "webpack.config.js", "tailwind.config.js", "tailwind.config.ts"
        }
        or (suffix_lower in {".toml", ".ini", ".cfg", ".conf"} and len(parts_lower) == 1)
        or (name_lower.startswith("requirements") and suffix_lower == ".txt")
    ):
        return "configuration"

    # 12. Application Source
    code_suffixes = {
        ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".php", ".rb",
        ".vue", ".svelte"
    }
    if suffix_lower in code_suffixes:
        return "application_source"

    return "unknown"


def detect_application_boundaries(root: Path) -> list[dict[str, Any]]:
    """Detect independent application and package roots within a project or monorepo."""
    resolved_root = root.resolve()
    boundaries: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()

    manifest_names = {
        "pyproject.toml": "Python (pyproject.toml)",
        "package.json": "JavaScript/TypeScript (package.json)",
        "setup.py": "Python (setup.py)",
        "requirements.txt": "Python (requirements.txt)",
        "go.mod": "Go (go.mod)",
        "Cargo.toml": "Rust (Cargo.toml)",
        "pom.xml": "Java (Maven)",
        "build.gradle": "Java/Kotlin (Gradle)",
        "composer.json": "PHP (Composer)",
    }

    # Root application
    root_manifests = [m for m in manifest_names if (resolved_root / m).is_file()]
    root_name = detect_project_name(resolved_root)
    boundaries.append({
        "app_name": root_name or "root",
        "relative_path": ".",
        "absolute_path": str(resolved_root),
        "manifests": root_manifests,
        "is_root": True,
        "primary_role": "application_source",
    })
    seen_dirs.add(".")

    # Search subdirectories for nested application boundaries
    for path in sorted(resolved_root.rglob("*")):
        if path.is_symlink():
            continue
        if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.is_file() and path.name in manifest_names:
            app_dir = path.parent
            rel_dir = app_dir.relative_to(resolved_root).as_posix()
            if rel_dir in seen_dirs:
                for b in boundaries:
                    if b["relative_path"] == rel_dir and path.name not in b["manifests"]:
                        b["manifests"].append(path.name)
                continue

            seen_dirs.add(rel_dir)
            role = classify_source_role(rel_dir)
            if role not in {"example", "demo", "benchmark", "fixture", "test"}:
                role = "application_source"

            app_name = app_dir.name
            if (app_dir / "package.json").is_file():
                try:
                    pkg_data = json.loads((app_dir / "package.json").read_text(encoding="utf-8"))
                    if isinstance(pkg_data, dict) and "name" in pkg_data:
                        app_name = str(pkg_data["name"])
                except Exception:
                    pass
            elif (app_dir / "pyproject.toml").is_file():
                try:
                    for line in (app_dir / "pyproject.toml").read_text(encoding="utf-8").splitlines():
                        if line.strip().startswith("name ="):
                            app_name = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                except Exception:
                    pass

            boundaries.append({
                "app_name": app_name,
                "relative_path": rel_dir,
                "absolute_path": str(app_dir),
                "manifests": [path.name],
                "is_root": False,
                "primary_role": role,
            })

    return boundaries


def resolve_file_scope(
    rel_path: Path | str,
    root: Path | None = None,
    application_boundaries: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Map a file to its source role, owning application, and audit scope."""
    posix_path = Path(rel_path).as_posix()
    role = classify_source_role(posix_path, root)

    if role == "application_source":
        scope = "primary_application"
    elif role in ("example", "demo", "benchmark"):
        scope = "example"
    elif role in ("test", "fixture"):
        scope = "test_and_fixture"
    elif role in ("documentation", "api_contract"):
        scope = "documentation_and_contract"
    else:
        scope = "tooling_and_config"

    app_name = "primary"
    if application_boundaries:
        matched_boundary = None
        for b in sorted(application_boundaries, key=lambda x: len(x["relative_path"]), reverse=True):
            b_path = b["relative_path"]
            if b_path != "." and (posix_path == b_path or posix_path.startswith(f"{b_path}/")):
                matched_boundary = b
                break
        if matched_boundary:
            app_name = matched_boundary["app_name"]
            if matched_boundary.get("primary_role") in ("example", "demo", "benchmark") and scope == "primary_application":
                scope = "example"
                role = matched_boundary.get("primary_role", "example")
        else:
            root_boundary = next((b for b in application_boundaries if b.get("is_root")), None)
            if root_boundary:
                app_name = root_boundary["app_name"]

    return {
        "source_role": role,
        "app_name": app_name,
        "scope": scope,
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
    app_boundaries = detect_application_boundaries(root)

    primary_source: list[str] = []
    test_files: list[str] = []
    doc_files: list[str] = []
    example_fixtures: list[str] = []
    python_files: list[Path] = []
    languages_seen: set[str] = set()

    role_counts: dict[str, int] = {
        "application_source": 0,
        "example": 0,
        "demo": 0,
        "benchmark": 0,
        "fixture": 0,
        "test": 0,
        "documentation": 0,
        "api_contract": 0,
        "configuration": 0,
        "generated": 0,
        "vendor": 0,
        "build_output": 0,
        "unknown": 0,
    }

    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue

        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        role = classify_source_role(rel_posix, root)
        role_counts[role] = role_counts.get(role, 0) + 1

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
        if role in ("example", "demo", "benchmark", "fixture"):
            example_fixtures.append(rel_posix)
        elif role == "test":
            test_files.append(rel_posix)
        elif role in ("documentation", "api_contract"):
            doc_files.append(rel_posix)
        elif role == "application_source":
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
        "application_boundaries": app_boundaries,
        "source_role_inventory": role_counts,
        "primary_source_count": len(primary_source),
        "test_count": len(test_files),
        "doc_count": len(doc_files),
        "example_fixture_count": len(example_fixtures),
        "example_fixture_dirs": sorted({Path(p).parts[0] for p in example_fixtures}),
        "limitations": [
            "Examples, demos, and benchmarks are classified separately from primary application source.",
            "Static discovery does not infer authoritative user requirements from code patterns.",
            "Dynamic imports, reflection, and runtime plugin hooks require manual verification.",
        ],
    }

