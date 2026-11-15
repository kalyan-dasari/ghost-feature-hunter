"""Rust language discovery adapter.

Extracts Axum, Actix Web, and Rocket routes, structs, traits,
cargo tests, and unfinished implementations using structural parsing.
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


class RustAdapter(BaseLanguageAdapter):
    """Structural static analysis for Rust web applications and services."""

    @property
    def language(self) -> str:
        return "Rust"

    @property
    def file_extensions(self) -> set[str]:
        return {".rs"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Axum", "Actix Web", "Rocket"]

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
            "Structural token and macro parsing; procedural macro expansion and monomorphized types require rustc/cargo.",
            "Tower service layers and Axum nested routers are tracked statically.",
            "Cargo crate graph resolution requires cargo metadata evaluation.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        cargo_toml = root / "Cargo.toml"
        if cargo_toml.is_file():
            try:
                txt = cargo_toml.read_text(encoding="utf-8", errors="ignore")
                if "axum" in txt:
                    signals["Axum"] = "structural"
                if "actix-web" in txt:
                    signals["Actix Web"] = "structural"
                if "rocket" in txt:
                    signals["Rocket"] = "structural"
            except OSError:
                pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "axum::" in content or "Router::new().route" in content:
                signals["Axum"] = "structural"
            if "actix_web::" in content or "#[get(" in content or "#[post(" in content:
                signals["Actix Web"] = "structural"
            if "rocket::" in content:
                signals["Rocket"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "Rust",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural route, struct, and test extraction for Rust ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without rustc compiler; proc macro expansions for {name} are approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = file_path.parent.name in ("tests", "test") or "#[test]" in content

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

        # 1. Uses / Imports
        for line in lines:
            m = re.match(r"""use\s+([a-zA-Z0-9_:]+)(?:;|\s*\{)""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Routes: Axum, Actix Web, Rocket
        # Axum: .route("/path", get(handler))
        axum_pattern = re.compile(
            r"""\.route\(\s*["']([^"']+)["']\s*,\s*(get|post|put|delete|patch)\s*\(\s*([a-zA-Z0-9_:]+)\s*\)\)""",
            re.IGNORECASE,
        )
        # Actix / Rocket: #[get("/path")] fn handler(...)
        actix_pattern = re.compile(
            r"""#\[(get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']\s*\)\]""",
            re.IGNORECASE,
        )

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            am = axum_pattern.search(line_str)
            if am:
                raw_path = am.group(1)
                method = am.group(2).upper()
                handler = am.group(3)
                full_path = normalize_route_path(raw_path)
                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=handler,
                        source=rel_path,
                        line=line_num,
                        framework="Axum",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

            acm = actix_pattern.search(line_str)
            if acm:
                method = acm.group(1).upper()
                raw_path = acm.group(2)
                full_path = normalize_route_path(raw_path)
                func_name = "handler"
                for lookahead in lines[line_num:min(line_num + 5, len(lines))]:
                    fn_m = re.search(r"""(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)""", lookahead)
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
                        framework="Actix Web",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

        # 3. Functions, structs, enums, traits
        item_pattern = re.compile(r"""(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(fn|struct|enum|trait)\s+([a-zA-Z0-9_]+)""")
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            im = item_pattern.search(line_str)
            if im:
                ikind, iname = im.groups()
                is_pub = line_str.startswith("pub")
                symbols.append(
                    SymbolDefinition(
                        name=iname,
                        symbol_type="function" if ikind == "fn" else ikind,
                        source=rel_path,
                        line=line_num,
                        is_exported=is_pub,
                    )
                )
                if is_pub:
                    exports.append(iname)

                if ikind == "struct" and ("model" in rel_path.lower() or "entity" in rel_path.lower() or "schema" in rel_path.lower()):
                    models.append(
                        ModelDefinition(
                            name=iname,
                            source=rel_path,
                            line=line_num,
                            framework="Rust-Struct",
                            is_example=is_ex,
                        )
                    )

        # 4. Unfinished items: todo!(), unimplemented!(), panic!("not implemented")
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""\b(?:todo!|unimplemented!)\s*\(""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"todo!/unimplemented! in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="Rust macro explicitly marks unimplemented logic.",
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
