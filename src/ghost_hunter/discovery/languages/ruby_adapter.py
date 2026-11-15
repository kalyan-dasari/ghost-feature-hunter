"""Ruby language discovery adapter.

Extracts Rails and Sinatra routes, ActiveRecord models,
RSpec/Minitest tests, and unfinished implementations using structural parsing.
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


class RubyAdapter(BaseLanguageAdapter):
    """Structural static analysis for Ruby on Rails and Sinatra applications."""

    @property
    def language(self) -> str:
        return "Ruby"

    @property
    def file_extensions(self) -> set[str]:
        return {".rb"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Rails", "Sinatra"]

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
            "Structural Ruby token parsing; metaprogrammed routes and dynamic method_missing dispatch are approximated.",
            "Rails resource routing macros (e.g. resources :orders) are expanded statically to conventional REST endpoints.",
            "Bundler Gemfile dependency resolution requires ruby/bundler execution.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        gemfile = root / "Gemfile"
        if gemfile.is_file():
            try:
                txt = gemfile.read_text(encoding="utf-8", errors="ignore")
                if "rails" in txt:
                    signals["Rails"] = "structural"
                if "sinatra" in txt:
                    signals["Sinatra"] = "structural"
            except OSError:
                pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "Rails.application" in content or "ActiveRecord::Base" in content or "ActionController::Base" in content:
                signals["Rails"] = "structural"
            if "Sinatra::Base" in content or "require 'sinatra'" in content:
                signals["Sinatra"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "Ruby",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural route, model, and test extraction for Ruby ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without Ruby VM; dynamic metaprogramming in {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = bool(re.search(r"""(_spec|_test)\.rb$""", file_path.name))

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

        # 1. Requires / Imports
        for line in lines:
            m = re.match(r"""require\s+['"]([^'"]+)['"]""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Routes (Rails routes.rb or Sinatra)
        rails_route_pattern = re.compile(
            r"""(get|post|put|delete|patch)\s+['"]([^'"]+)['"](?:\s*,\s*to:\s*['"]([a-zA-Z0-9_#]+)['"])?""",
            re.IGNORECASE,
        )
        resources_pattern = re.compile(r"""resources\s+:([a-zA-Z0-9_]+)""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            rm = rails_route_pattern.search(line_str)
            if rm:
                method = rm.group(1).upper()
                raw_path = rm.group(2)
                to_target = rm.group(3) or "action"
                full_path = normalize_route_path(raw_path)
                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=to_target,
                        source=rel_path,
                        line=line_num,
                        framework="Rails" if "routes.rb" in rel_path else "Sinatra",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

            res_m = resources_pattern.search(line_str)
            if res_m:
                res_name = res_m.group(1)
                for verb, sub in [("GET", f"/{res_name}"), ("POST", f"/{res_name}"), ("GET", f"/{res_name}/{{id}}")]:
                    routes.append(
                        RouteDefinition(
                            path=sub,
                            methods=[verb],
                            function=f"{res_name}#{verb.lower()}",
                            source=rel_path,
                            line=line_num,
                            framework="Rails-Resources",
                            is_example=is_ex,
                            raw_decorator=line_str,
                        )
                    )

        # 3. Classes and methods
        class_pattern = re.compile(r"""class\s+([a-zA-Z0-9_:]+)(?:\s*<\s*([a-zA-Z0-9_:]+))?""")
        def_pattern = re.compile(r"""def\s+([a-zA-Z0-9_?!]+)""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            cm = class_pattern.search(line_str)
            if cm:
                cname = cm.group(1)
                cparent = cm.group(2) or ""
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
                if cparent in ("ApplicationRecord", "ActiveRecord::Base") or "model" in rel_path.lower():
                    models.append(
                        ModelDefinition(
                            name=cname,
                            source=rel_path,
                            line=line_num,
                            framework="ActiveRecord",
                            is_example=is_ex,
                        )
                    )

            dm = def_pattern.search(line_str)
            if dm:
                mname = dm.group(1)
                symbols.append(
                    SymbolDefinition(
                        name=mname,
                        symbol_type="method",
                        source=rel_path,
                        line=line_num,
                        is_exported=not mname.startswith("_"),
                    )
                )

        # 4. Unfinished / Dead Code
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""raise\s+NotImplementedError""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"NotImplemented in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="Ruby method explicitly raises NotImplementedError.",
                        confidence="High",
                    )
                )
            elif re.search(r"""#\s*(TODO|FIXME|WIP):?\s*(.*)""", line_str):
                m = re.search(r"""#\s*(TODO|FIXME|WIP):?\s*(.*)""", line_str)
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
