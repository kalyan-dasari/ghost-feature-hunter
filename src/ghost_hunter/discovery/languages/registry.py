"""Language adapter registry and multi-language capability matrix generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.base import BaseLanguageAdapter
from ghost_hunter.discovery.languages.csharp_adapter import CSharpAdapter
from ghost_hunter.discovery.languages.go_adapter import GoAdapter
from ghost_hunter.discovery.languages.java_adapter import JavaAdapter
from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
from ghost_hunter.discovery.languages.kotlin_adapter import KotlinAdapter
from ghost_hunter.discovery.languages.models import FeatureFlagDefinition
from ghost_hunter.discovery.languages.php_adapter import PHPAdapter
from ghost_hunter.discovery.languages.polyglot_inventory import (
    CFamilyAdapter,
    SQLAdapter,
    SwiftAdapter,
)
from ghost_hunter.discovery.languages.python_adapter import PythonAdapter
from ghost_hunter.discovery.languages.ruby_adapter import RubyAdapter
from ghost_hunter.discovery.languages.rust_adapter import RustAdapter
from ghost_hunter.discovery.project import (
    IGNORED_DIRECTORIES,
    classify_source_role,
    detect_application_boundaries,
    is_example_or_fixture,
    resolve_file_scope,
)

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript/TypeScript",
    ".jsx": "JavaScript/TypeScript",
    ".ts": "JavaScript/TypeScript",
    ".tsx": "JavaScript/TypeScript",
    ".mjs": "JavaScript/TypeScript",
    ".cjs": "JavaScript/TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".c": "C/C++",
    ".h": "C/C++",
    ".cpp": "C/C++",
    ".hpp": "C/C++",
    ".cc": "C/C++",
    ".cxx": "C/C++",
    ".hh": "C/C++",
    ".swift": "Swift",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".json": "JSON",
    ".md": "Markdown",
}


class LanguageRegistry:
    """Registry of language adapters with fallback for unsupported ecosystems."""

    def __init__(self) -> None:
        self._adapters: list[BaseLanguageAdapter] = [
            PythonAdapter(),
            JavaScriptAdapter(),
            GoAdapter(),
            JavaAdapter(),
            CSharpAdapter(),
            PHPAdapter(),
            RubyAdapter(),
            RustAdapter(),
            KotlinAdapter(),
            CFamilyAdapter(),
            SwiftAdapter(),
            SQLAdapter(),
        ]
        self._extension_to_adapter: dict[str, BaseLanguageAdapter] = {}
        self._language_to_adapter: dict[str, BaseLanguageAdapter] = {}
        for adapter in self._adapters:
            self._language_to_adapter[adapter.language] = adapter
            for ext in adapter.file_extensions:
                self._extension_to_adapter[ext] = adapter

    def get_adapter(self, ext: str) -> BaseLanguageAdapter | None:
        return self._extension_to_adapter.get(ext.lower())

    def identify_language(self, path: Path) -> str:
        return LANGUAGE_EXTENSIONS.get(path.suffix.lower(), "Other")

    def build_capability_matrix(
        self,
        detected_languages: set[str],
        detected_frameworks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Construct a transparent capability matrix for all detected languages."""
        matrix: list[dict[str, Any]] = []
        framework_langs = {fw.get("language") for fw in detected_frameworks}

        # Add detected framework entries
        for fw in detected_frameworks:
            adapter = self._language_to_adapter.get(fw.get("language", ""))
            caps = adapter.get_capabilities() if adapter else {}
            level = getattr(adapter, "capability_level", "structural")
            declared_level = fw.get("capability_level", level)
            # Enforce honesty: parser-backed deep-static requires genuine syntax_parsing
            if not caps.get("syntax_parsing", False) and declared_level == "deep-static":
                declared_level = "structural"
            entry = {
                "language_framework": f"{fw['language']} / {fw['framework']}",
                "detected": True,
                "status": fw.get("status", "supported"),
                "capability_level": declared_level,
                "analysis_capability": fw.get("analysis_capability", f"Supported analysis for {fw['language']} ({fw['framework']})"),
                "capabilities": fw.get("capabilities", caps),
                "limitations": fw.get("limitations", "None specified"),
            }
            matrix.append(entry)

        # For detected languages, add base entries where needed
        for lang in sorted(detected_languages):
            if lang in {"JSON", "Markdown", "CSS", "HTML", "Other"}:
                continue

            has_fw = lang in framework_langs
            adapter = self._language_to_adapter.get(lang)

            if adapter is not None:
                # Always add base entry for Go (to satisfy existing capability queries), or when no framework is detected
                if lang == "Go" or not has_fw:
                    caps = adapter.get_capabilities()
                    level = adapter.capability_level
                    if not caps.get("syntax_parsing", False) and level == "deep-static":
                        level = "structural"
                    status = "supported" if level == "deep-static" else ("partial" if level == "structural" else "inventory-only")
                    analysis_cap = (
                        "Deep static AST analysis and symbol resolution"
                        if level == "deep-static"
                        else (
                            "Structural regex and lexical analysis with file inventory and package manifest inspection"
                            if level == "structural"
                            else "File inventory and package manifest inspection only"
                        )
                    )
                    lims = (
                        f"Full compiler execution and dynamic reflection for {lang} are not implemented in the current engine; structural parsing is supported."
                        if level == "structural"
                        else (
                            "None specified"
                            if level == "deep-static"
                            else f"AST parsing, route extraction, and reference graph analysis for {lang} are not implemented in the current engine."
                        )
                    )
                    matrix.append({
                        "language_framework": lang,
                        "detected": True,
                        "status": status,
                        "capability_level": level,
                        "analysis_capability": analysis_cap,
                        "capabilities": caps,
                        "limitations": lims,
                    })
            else:
                matrix.append({
                    "language_framework": lang,
                    "detected": True,
                    "status": "partial",
                    "capability_level": "inventory-only",
                    "analysis_capability": "File inventory and package manifest inspection only",
                    "capabilities": {
                        "route_extraction": False,
                        "symbol_analysis": False,
                        "ui_analysis": False,
                        "reference_analysis": False,
                        "duplicate_detection": False,
                        "unfinished_code_detection": False,
                        "dependency_analysis": True,
                    },
                    "limitations": f"AST parsing, route extraction, and reference graph analysis for {lang} are not implemented in the current engine.",
                })

        return matrix

    def scan_repository(self, project_root: Path, file_limit: int = 15000) -> dict[str, Any]:
        """Deep multi-language scan across the entire project root with application boundaries and source roles."""
        root = project_root.resolve()
        app_boundaries = detect_application_boundaries(root)

        files_by_lang: dict[str, list[Path]] = {}
        detected_languages: set[str] = set()

        all_routes = []
        all_client_calls = []
        all_models = []
        all_components = []
        all_ui_actions = []
        all_unfinished = []
        all_symbols = []
        all_imports = []
        all_exports = []
        all_calls_made = []
        production_calls_made = []
        test_calls_made = []
        example_calls_made = []
        all_feature_flags: list[FeatureFlagDefinition] = []
        all_feature_flag_consumers: set[str] = set()
        imports_by_app: dict[str, list[str]] = {}

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

        file_count = 0
        scan_truncated = False

        for path in root.rglob("*"):
            if path.is_symlink():
                continue
            if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
                continue
            if not path.is_file():
                continue

            file_count += 1
            if file_count > file_limit:
                scan_truncated = True
                break

            rel_posix = path.relative_to(root).as_posix()
            scope_info = resolve_file_scope(rel_posix, root, app_boundaries)
            role = scope_info["source_role"]
            app_name = scope_info["app_name"]
            scope = scope_info["scope"]
            role_counts[role] = role_counts.get(role, 0) + 1

            lang = self.identify_language(path)
            detected_languages.add(lang)
            files_by_lang.setdefault(lang, []).append(path)

            adapter = self.get_adapter(path.suffix)
            if adapter is not None:
                analysis = adapter.analyze_file(path, root)

                # Attach scope and boundary metadata to all extracted definitions
                file_routes = analysis.get("routes", [])
                for r in file_routes:
                    r.source_role = role
                    r.app_name = app_name
                    r.scope = scope
                all_routes.extend(file_routes)

                file_calls = analysis.get("client_calls", [])
                for c in file_calls:
                    c.source_role = role
                    c.app_name = app_name
                    c.scope = scope
                all_client_calls.extend(file_calls)

                file_models = analysis.get("models", [])
                for m in file_models:
                    m.source_role = role
                    m.app_name = app_name
                    m.scope = scope
                all_models.extend(file_models)

                file_components = analysis.get("components", [])
                for comp in file_components:
                    comp.source_role = role
                    comp.app_name = app_name
                    comp.scope = scope
                all_components.extend(file_components)

                file_actions = analysis.get("ui_actions", [])
                for a in file_actions:
                    a.source_role = role
                    a.app_name = app_name
                    a.scope = scope
                all_ui_actions.extend(file_actions)

                file_unfinished = analysis.get("unfinished", [])
                for u in file_unfinished:
                    u.source_role = role
                    u.app_name = app_name
                    u.scope = scope
                all_unfinished.extend(file_unfinished)

                file_symbols = analysis.get("symbols", [])
                for s in file_symbols:
                    s.source_role = role
                    s.app_name = app_name
                    s.scope = scope
                all_symbols.extend(file_symbols)

                file_imports = analysis.get("imports", [])
                all_imports.extend(file_imports)
                imports_by_app.setdefault(app_name, []).extend(file_imports)

                all_exports.extend(analysis.get("exports", []))

                calls_in_file = analysis.get("calls_made", [])
                all_calls_made.extend(calls_in_file)
                if role == "application_source":
                    production_calls_made.extend(calls_in_file)
                elif role in ("test", "fixture"):
                    test_calls_made.extend(calls_in_file)
                elif role in ("example", "demo", "benchmark"):
                    example_calls_made.extend(calls_in_file)

                file_flags = analysis.get("feature_flags", [])
                for f in file_flags:
                    f.source_role = role
                    f.app_name = app_name
                    f.scope = scope
                all_feature_flags.extend(file_flags)
                all_feature_flag_consumers.update(analysis.get("feature_flag_consumers", []))

        # Check manifests without cross-language contamination
        manifest_by_lang = {
            "Python": any((root / m).is_file() for m in ("pyproject.toml", "setup.py", "requirements.txt", "Pipfile")),
            "JavaScript/TypeScript": any((root / m).is_file() for m in ("package.json", "tsconfig.json", "jsconfig.json")),
            "Go": (root / "go.mod").is_file(),
            "Java": any((root / m).is_file() for m in ("pom.xml", "build.gradle", "build.gradle.kts")),
            "C#": bool(list(root.glob("*.csproj")) or list(root.glob("*.sln"))),
            "PHP": (root / "composer.json").is_file(),
            "Ruby": (root / "Gemfile").is_file(),
            "Rust": (root / "Cargo.toml").is_file(),
            "Kotlin": (root / "build.gradle.kts").is_file(),
        }

        detected_frameworks: list[dict[str, Any]] = []
        for adapter in self._adapters:
            relevant_files = []
            for ext in adapter.file_extensions:
                for f in files_by_lang.get(adapter.language, []):
                    if f.suffix.lower() == ext:
                        relevant_files.append(f)

            has_manifest = manifest_by_lang.get(adapter.language, False)
            if relevant_files or has_manifest:
                detected_frameworks.extend(adapter.detect_frameworks(relevant_files, root))

        capability_matrix = self.build_capability_matrix(detected_languages, detected_frameworks)

        return {
            "detected_languages": sorted(detected_languages),
            "files_by_language": {lang: len(paths) for lang, paths in files_by_lang.items()},
            "frameworks": detected_frameworks,
            "capability_matrix": capability_matrix,
            "application_boundaries": app_boundaries,
            "source_role_inventory": role_counts,
            "file_count": file_count,
            "file_limit": file_limit,
            "scan_truncated": scan_truncated,
            "routes": all_routes,
            "client_calls": all_client_calls,
            "models": all_models,
            "components": all_components,
            "ui_actions": all_ui_actions,
            "unfinished": all_unfinished,
            "symbols": all_symbols,
            "imports": sorted(set(all_imports)),
            "imports_by_app": imports_by_app,
            "exports": sorted(set(all_exports)),
            "calls_made": sorted(set(all_calls_made)),
            "production_calls_made": sorted(set(production_calls_made)),
            "test_calls_made": sorted(set(test_calls_made)),
            "example_calls_made": sorted(set(example_calls_made)),
            "feature_flags": all_feature_flags,
            "feature_flag_consumers": sorted(all_feature_flag_consumers),
        }
