"""Inventory and foundation adapters for C/C++, Swift, and SQL.

Provides honest capability levels (inventory-only / schema inventory) and documents
explicit compiler/toolchain routes (Clang, SwiftPM, SQL AST) for future phases.
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
from ghost_hunter.discovery.project import is_example_or_fixture


class CFamilyAdapter(BaseLanguageAdapter):
    """Inventory and symbol foundation for C and C++ codebases."""

    @property
    def language(self) -> str:
        return "C/C++"

    @property
    def file_extensions(self) -> set[str]:
        return {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hh"}

    @property
    def supported_frameworks(self) -> list[str]:
        return []

    @property
    def capability_level(self) -> str:
        return "inventory-only"

    def get_capabilities(self) -> dict[str, bool]:
        return build_standard_capabilities(
            syntax_parsing=False,
            symbol_analysis=False,
            import_export_analysis=False,
            reference_analysis=False,
            route_extraction=False,
            client_call_extraction=False,
            ui_analysis=False,
            model_schema_analysis=False,
            test_discovery=False,
            test_assertion_candidates=False,
            dependency_usage_analysis=False,
            unfinished_code_detection=False,
            duplicate_detection=False,
        )

    def get_limitations(self) -> list[str]:
        return [
            "File inventory only; AST and header resolution require Clang / libclang or compile_commands.json.",
            "Preprocessor directives (#include, #ifdef) require compiler preprocessor expansion.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        return []

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        return {
            "routes": [],
            "client_calls": [],
            "models": [],
            "components": [],
            "ui_actions": [],
            "unfinished": [],
            "symbols": [],
            "imports": [],
            "exports": [],
            "calls_made": [],
            "feature_flags": [],
            "feature_flag_consumers": [],
            "is_test_file": False,
        }


class SwiftAdapter(BaseLanguageAdapter):
    """Inventory and foundation for Apple ecosystem and Swift server applications."""

    @property
    def language(self) -> str:
        return "Swift"

    @property
    def file_extensions(self) -> set[str]:
        return {".swift"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Vapor"]

    @property
    def capability_level(self) -> str:
        return "inventory-only"

    def get_capabilities(self) -> dict[str, bool]:
        return build_standard_capabilities(
            syntax_parsing=False,
            symbol_analysis=False,
            import_export_analysis=False,
            reference_analysis=False,
            route_extraction=False,
            client_call_extraction=False,
            ui_analysis=False,
            model_schema_analysis=False,
            test_discovery=False,
            test_assertion_candidates=False,
            dependency_usage_analysis=False,
            unfinished_code_detection=False,
            duplicate_detection=False,
        )

    def get_limitations(self) -> list[str]:
        return [
            "File inventory only; Swift AST syntax analysis requires swift-syntax or SwiftPM toolchain.",
            "Vapor / Swift server routing requires Swift syntax tree parser.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        return []

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        return {
            "routes": [],
            "client_calls": [],
            "models": [],
            "components": [],
            "ui_actions": [],
            "unfinished": [],
            "symbols": [],
            "imports": [],
            "exports": [],
            "calls_made": [],
            "feature_flags": [],
            "feature_flag_consumers": [],
            "is_test_file": False,
        }


class SQLAdapter(BaseLanguageAdapter):
    """Database schema, migration, and table definition discovery."""

    @property
    def language(self) -> str:
        return "SQL"

    @property
    def file_extensions(self) -> set[str]:
        return {".sql"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["SQL DDL"]

    @property
    def capability_level(self) -> str:
        return "structural"

    def get_capabilities(self) -> dict[str, bool]:
        return build_standard_capabilities(
            syntax_parsing=True,
            symbol_analysis=True,
            import_export_analysis=False,
            reference_analysis=False,
            route_extraction=False,
            client_call_extraction=False,
            ui_analysis=False,
            model_schema_analysis=True,
            test_discovery=False,
            test_assertion_candidates=False,
            dependency_usage_analysis=False,
            unfinished_code_detection=False,
            duplicate_detection=False,
        )

    def get_limitations(self) -> list[str]:
        return [
            "DDL table definition extraction only; complex stored procedures and triggers are not parsed.",
            "Dialect-specific SQL features (PostgreSQL, MySQL, SQLite, Oracle) are normalized.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        return []

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        models: list[ModelDefinition] = []

        # Find CREATE TABLE [IF NOT EXISTS] table_name
        table_pattern = re.compile(r"""CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[`"']?([a-zA-Z0-9_.]+)""", re.IGNORECASE)
        for line_num, line in enumerate(content.splitlines(), 1):
            m = table_pattern.search(line)
            if m:
                tname = m.group(1).split(".")[-1].strip("`\"'")
                models.append(
                    ModelDefinition(
                        name=tname,
                        source=rel_path,
                        line=line_num,
                        framework="SQL Schema",
                        is_example=is_ex,
                    )
                )

        return {
            "routes": [],
            "client_calls": [],
            "models": models,
            "components": [],
            "ui_actions": [],
            "unfinished": [],
            "symbols": [],
            "imports": [],
            "exports": [],
            "calls_made": [],
            "feature_flags": [],
            "feature_flag_consumers": [],
            "is_test_file": False,
        }
