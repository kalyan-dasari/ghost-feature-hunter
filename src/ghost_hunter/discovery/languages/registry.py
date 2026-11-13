"""Language adapter registry and multi-language capability matrix generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.base import BaseLanguageAdapter
from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
from ghost_hunter.discovery.languages.models import FeatureFlagDefinition
from ghost_hunter.discovery.languages.python_adapter import PythonAdapter
from ghost_hunter.discovery.project import IGNORED_DIRECTORIES, is_example_or_fixture

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
        ]
        self._extension_to_adapter: dict[str, BaseLanguageAdapter] = {}
        for adapter in self._adapters:
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

        # Add detected framework entries
        for fw in detected_frameworks:
            adapter = next((a for a in self._adapters if a.language == fw.get("language")), None)
            caps = adapter.get_capabilities() if adapter else {}
            entry = {
                "language_framework": f"{fw['language']} / {fw['framework']}",
                "detected": True,
                "status": fw.get("status", "supported"),
                "analysis_capability": fw.get("analysis_capability", "Supported analysis"),
                "capabilities": fw.get("capabilities", caps),
                "limitations": fw.get("limitations", "None specified"),
            }
            matrix.append(entry)

        # Add entries for languages that were detected but have no specialized adapter
        supported_langs = {"Python", "JavaScript/TypeScript"}
        for lang in sorted(detected_languages):
            if lang not in supported_langs and lang not in {"JSON", "Markdown", "CSS"}:
                matrix.append({
                    "language_framework": lang,
                    "detected": True,
                    "status": "partial",
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
        """Deep multi-language scan across the entire project root."""
        root = project_root.resolve()

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
        all_feature_flags: list[FeatureFlagDefinition] = []
        all_feature_flag_consumers: set[str] = set()

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

            lang = self.identify_language(path)
            detected_languages.add(lang)
            files_by_lang.setdefault(lang, []).append(path)

            adapter = self.get_adapter(path.suffix)
            if adapter is not None:
                analysis = adapter.analyze_file(path, root)
                all_routes.extend(analysis.get("routes", []))
                all_client_calls.extend(analysis.get("client_calls", []))
                all_models.extend(analysis.get("models", []))
                all_components.extend(analysis.get("components", []))
                all_ui_actions.extend(analysis.get("ui_actions", []))
                all_unfinished.extend(analysis.get("unfinished", []))
                all_symbols.extend(analysis.get("symbols", []))
                all_imports.extend(analysis.get("imports", []))
                all_exports.extend(analysis.get("exports", []))
                all_calls_made.extend(analysis.get("calls_made", []))
                all_feature_flags.extend(analysis.get("feature_flags", []))
                all_feature_flag_consumers.update(analysis.get("feature_flag_consumers", []))

        # Check manifests without cross-language contamination
        has_py_manifest = (
            (root / "pyproject.toml").is_file()
            or (root / "setup.py").is_file()
            or (root / "requirements.txt").is_file()
            or any(p.name in ("pyproject.toml", "setup.py", "requirements.txt") for p in root.rglob("*.txt") if not any(part in IGNORED_DIRECTORIES for part in p.parts))
        )
        has_js_manifest = (
            (root / "package.json").is_file()
            or (root / "tsconfig.json").is_file()
            or any(p.name == "package.json" for p in root.rglob("package.json") if not any(part in IGNORED_DIRECTORIES for part in p.parts))
        )

        detected_frameworks: list[dict[str, Any]] = []
        for adapter in self._adapters:
            relevant_files = []
            for ext in adapter.file_extensions:
                for f in files_by_lang.get(adapter.language, []):
                    if f.suffix.lower() == ext:
                        relevant_files.append(f)

            if adapter.language == "Python":
                if relevant_files or has_py_manifest:
                    detected_frameworks.extend(adapter.detect_frameworks(relevant_files, root))
            elif adapter.language == "JavaScript/TypeScript":
                if relevant_files or has_js_manifest:
                    detected_frameworks.extend(adapter.detect_frameworks(relevant_files, root))

        capability_matrix = self.build_capability_matrix(detected_languages, detected_frameworks)

        return {
            "detected_languages": sorted(detected_languages),
            "files_by_language": {lang: len(paths) for lang, paths in files_by_lang.items()},
            "frameworks": detected_frameworks,
            "capability_matrix": capability_matrix,
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
            "exports": sorted(set(all_exports)),
            "calls_made": sorted(set(all_calls_made)),
            "feature_flags": all_feature_flags,
            "feature_flag_consumers": sorted(all_feature_flag_consumers),
        }
