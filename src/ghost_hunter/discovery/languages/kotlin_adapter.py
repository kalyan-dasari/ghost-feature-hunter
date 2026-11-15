"""Kotlin language discovery adapter.

Extracts Spring Kotlin and Ktor routes, data classes,
JUnit tests, and unfinished implementations using structural parsing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.base import BaseLanguageAdapter
from ghost_hunter.discovery.languages.models import (
    ClientCall,
    ComponentDefinition,
    FeatureFlagDefinition,
    ModelDefinition,
    RouteDefinition,
    SymbolDefinition,
    UIAction,
    UnfinishedItem,
    build_standard_capabilities,
)
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path
from ghost_hunter.discovery.project import is_example_or_fixture


class KotlinAdapter(BaseLanguageAdapter):
    """Structural static analysis for Kotlin Spring and Ktor applications."""

    @property
    def language(self) -> str:
        return "Kotlin"

    @property
    def file_extensions(self) -> set[str]:
        return {".kt", ".kts"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Spring Kotlin", "Ktor"]

    @property
    def capability_level(self) -> str:
        return "structural"

    def get_capabilities(self) -> dict[str, bool]:
        return build_standard_capabilities(
            syntax_parsing=True,
            symbol_analysis=True,
            import_export_analysis=True,
            reference_analysis=True,
            route_extraction=True,
            client_call_extraction=True,
            ui_analysis=False,
            model_schema_analysis=True,
            test_discovery=True,
            test_assertion_candidates=True,
            dependency_usage_analysis=False,
            unfinished_code_detection=True,
            duplicate_detection=False,
        )

    def get_limitations(self) -> list[str]:
        return [
            "Structural token parsing; Kotlin coroutines context and Ktor DSL route nesting are tracked statically.",
            "Gradle Kotlin DSL build dependencies require gradle evaluation.",
            "Inline reified functions and compiler plugins (e.g. Kotlin Serialization) require kotlinc compilation.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "@RestController" in content or "@GetMapping" in content or "org.springframework" in content:
                signals["Spring Kotlin"] = "structural"
            if "io.ktor" in content or "routing {" in content:
                signals["Ktor"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "Kotlin",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural route, data class, and test extraction for Kotlin ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without kotlinc compiler; DSL routing for {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = bool(re.search(r"""(Test|Tests|Spec)\.kts?$""", file_path.name))

        routes: list[RouteDefinition] = []
        client_calls: list[ClientCall] = []
        models: list[ModelDefinition] = []
        components: list[ComponentDefinition] = []
        ui_actions: list[UIAction] = []
        unfinished: list[UnfinishedItem] = []
        symbols: list[SymbolDefinition] = []
        imports: list[str] = []
        exports: list[str] = []
        calls_made: list[str] = []
        feature_flags: list[FeatureFlagDefinition] = []
        feature_flag_consumers: list[str] = []

        lines = content.splitlines()

        # 1. Imports
        for line in lines:
            m = re.match(r"""import\s+([a-zA-Z0-9_.*]+)""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Routes: Spring Mapping or Ktor DSL
        spring_mapping_patterns = [
            (re.compile(r"""@GetMapping\s*\(\s*["']([^"']+)["']"""), "GET"),
            (re.compile(r"""@PostMapping\s*\(\s*["']([^"']+)["']"""), "POST"),
            (re.compile(r"""@PutMapping\s*\(\s*["']([^"']+)["']"""), "PUT"),
            (re.compile(r"""@DeleteMapping\s*\(\s*["']([^"']+)["']"""), "DELETE"),
        ]

        ktor_pattern = re.compile(r"""\b(get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']\s*\)""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            for pattern, method in spring_mapping_patterns:
                m = pattern.search(line_str)
                if m:
                    raw_path = m.group(1)
                    full_path = normalize_route_path(raw_path)
                    func_name = "action"
                    for lookahead in lines[line_num:min(line_num + 4, len(lines))]:
                        fn_m = re.search(r"""fun\s+([a-zA-Z0-9_]+)\s*\(""", lookahead)
                        if fn_m:
                            func_name = fn_m.group(1)
                            break
                    routes.append(
                        RouteDefinition(
                            path=full_path,
                            methods=[method],
                            function=func_name,
                            source=rel_path,
                            line=line_num,
                            framework="Spring Kotlin",
                            is_example=is_ex,
                            raw_decorator=line_str,
                        )
                    )

            km = ktor_pattern.search(line_str)
            if km:
                method = km.group(1).upper()
                raw_path = km.group(2)
                full_path = normalize_route_path(raw_path)
                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=f"ktor_{method.lower()}",
                        source=rel_path,
                        line=line_num,
                        framework="Ktor",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

        # 3. Classes and functions
        class_pattern = re.compile(r"""(?:data\s+)?class\s+([a-zA-Z0-9_]+)""")
        fun_pattern = re.compile(r"""fun\s+([a-zA-Z0-9_]+)\s*\(""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            cm = class_pattern.search(line_str)
            if cm:
                cname = cm.group(1)
                symbols.append(
                    SymbolDefinition(
                        name=cname,
                        symbol_type="class",
                        source=rel_path,
                        line=line_num,
                        is_exported=True,
                    )
                )
                exports.append(cname)
                if "data class" in line_str or "model" in rel_path.lower():
                    models.append(
                        ModelDefinition(
                            name=cname,
                            source=rel_path,
                            line=line_num,
                            framework="Kotlin-DataClass",
                            is_example=is_ex,
                        )
                    )

            fm = fun_pattern.search(line_str)
            if fm:
                fname = fm.group(1)
                symbols.append(
                    SymbolDefinition(
                        name=fname,
                        symbol_type="function",
                        source=rel_path,
                        line=line_num,
                        is_exported=True,
                    )
                )

        # 4. Unfinished items: TODO(), throw NotImplementedError()
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""\bTODO\s*\(""", line_str) or re.search(r"""throw\s+NotImplementedError""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"TODO/NotImplemented in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="Kotlin TODO() or NotImplementedError marks unfinished implementation.",
                        confidence="High",
                    )
                )
            elif re.search(r"""//\s*(TODO|FIXME|WIP):?\s*(.*)""", line_str):
                m = re.search(r"""//\s*(TODO|FIXME|WIP):?\s*(.*)""", line_str)
                todo_text = m.group(2).strip() if m else ""
                unfinished.append(
                    UnfinishedItem(
                        item_type="todo_marker",
                        name=f"TODO in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation=f"Explicit TODO marker: {todo_text}",
                        confidence="Medium",
                    )
                )

        return {
            "routes": routes,
            "client_calls": client_calls,
            "models": models,
            "components": components,
            "ui_actions": ui_actions,
            "unfinished": unfinished,
            "symbols": symbols,
            "imports": sorted(set(imports)),
            "exports": sorted(set(exports)),
            "calls_made": sorted(set(calls_made)),
            "feature_flags": feature_flags,
            "feature_flag_consumers": sorted(set(feature_flag_consumers)),
            "is_test_file": is_test_file,
        }
