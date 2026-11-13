"""Language adapter registry and multi-language capability matrix generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.base import BaseLanguageAdapter
from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
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
            matrix.append({
                "language_framework": f"{fw['language']} / {fw['framework']}",
                "detected": True,
                "analysis_capability": fw.get("analysis_capability", "Supported analysis"),
                "status": fw.get("status", "supported"),
                "limitations": fw.get("limitations", "None specified"),
            })

        # Add entries for languages that were detected but have no specialized adapter
        supported_langs = {"Python", "JavaScript/TypeScript"}
        for lang in sorted(detected_languages):
            if lang not in supported_langs and lang not in {"JSON", "Markdown", "CSS"}:
                matrix.append({
                    "language_framework": lang,
                    "detected": True,
                    "analysis_capability": "File inventory and package manifest inspection only",
                    "status": "partial",
                    "limitations": f"AST parsing, route extraction, and reference graph analysis for {lang} are not implemented in the current engine.",
                })

        return matrix

    def scan_repository(self, project_root: Path) -> dict[str, Any]:
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

        file_count = 0
        for path in root.rglob("*"):
            if path.is_symlink():
                continue
            if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts):
                continue
            if not path.is_file():
                continue

            file_count += 1
            if file_count > 15000:
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

        # Detect frameworks across all adapters
        detected_frameworks: list[dict[str, Any]] = []
        for adapter in self._adapters:
            relevant_files = []
            for ext in adapter.file_extensions:
                for f in files_by_lang.get(adapter.language, []):
                    if f.suffix.lower() == ext:
                        relevant_files.append(f)
            if relevant_files or (root / "package.json").is_file() or (root / "pyproject.toml").is_file():
                detected_frameworks.extend(adapter.detect_frameworks(relevant_files, root))

        capability_matrix = self.build_capability_matrix(detected_languages, detected_frameworks)

        return {
            "detected_languages": sorted(detected_languages),
            "files_by_language": {lang: len(paths) for lang, paths in files_by_lang.items()},
            "frameworks": detected_frameworks,
            "capability_matrix": capability_matrix,
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
        }

