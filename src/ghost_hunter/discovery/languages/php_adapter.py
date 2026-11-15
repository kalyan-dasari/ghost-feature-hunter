"""PHP language discovery adapter.

Extracts Laravel, Symfony, and Slim routes, Eloquent models,
client requests, PHPUnit/Pest tests, and unfinished implementations using structural parsing.
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


class PHPAdapter(BaseLanguageAdapter):
    """Structural static analysis for PHP applications."""

    @property
    def language(self) -> str:
        return "PHP"

    @property
    def file_extensions(self) -> set[str]:
        return {".php"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Laravel", "Symfony", "Slim"]

    @property
    def capability_level(self) -> str:
        return "structural"

    def get_capabilities(self) -> dict[str, bool]:
        return build_standard_capabilities(
            syntax_parsing=False,
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
            "Structural regex and lexical scanning; PHP parser AST is not used.",
            "Structural token parsing; dynamic service container bindings and runtime reflection are approximated.",
            "Dynamic Route macros and runtime controller dispatching are evaluated statically.",
            "Composer package autoloading requires composer environment execution.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        composer = root / "composer.json"
        if composer.is_file():
            try:
                txt = composer.read_text(encoding="utf-8", errors="ignore")
                if "laravel/framework" in txt:
                    signals["Laravel"] = "structural"
                if "symfony/framework-bundle" in txt or "symfony/" in txt:
                    signals["Symfony"] = "structural"
                if "slim/slim" in txt:
                    signals["Slim"] = "structural"
            except OSError:
                pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "Route::get" in content or "Route::post" in content or "Illuminate\\" in content:
                signals["Laravel"] = "structural"
            if "#[Route" in content or "Symfony\\" in content:
                signals["Symfony"] = "structural"
            if "$app->get(" in content and "Slim" in content:
                signals["Slim"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "PHP",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural route, model, and test extraction for PHP ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without PHP runtime; dynamic DI container resolution for {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = bool(re.search(r"""(Test|TestCase|Spec)\.php$""", file_path.name))

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
            m = re.match(r"""use\s+([a-zA-Z0-9_\\]+);""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Routes: Laravel, Symfony, Slim
        # Laravel: Route::get('/path', [Controller::class, 'method'])
        laravel_route_pattern = re.compile(
            r"""Route::(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]\s*,\s*(?:\[?\s*([a-zA-Z0-9_]+)::class)?(?:,\s*['"]([a-zA-Z0-9_]+)['"])?""",
            re.IGNORECASE,
        )
        symfony_route_pattern = re.compile(
            r"""#\[Route\s*\(\s*['"]([^'"]+)['"](?:\s*,\s*(?:name:\s*['"][^'"]*['"]\s*,\s*)?methods:\s*\[([^\]]+)\])?""",
            re.IGNORECASE,
        )

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            lm = laravel_route_pattern.search(line_str)
            if lm:
                method = lm.group(1).upper()
                raw_path = lm.group(2)
                func_name = lm.group(4) or lm.group(3) or "action"
                full_path = normalize_route_path(raw_path)
                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=func_name,
                        source=rel_path,
                        line=line_num,
                        framework="Laravel",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

            sm = symfony_route_pattern.search(line_str)
            if sm:
                raw_path = sm.group(1)
                methods_raw = sm.group(2)
                methods = [m.strip().strip("'\"").upper() for m in methods_raw.split(",")] if methods_raw else ["GET"]
                full_path = normalize_route_path(raw_path)

                func_name = "action"
                for lookahead in lines[line_num:min(line_num + 5, len(lines))]:
                    fn_match = re.search(r"""public\s+function\s+([a-zA-Z0-9_]+)\s*\(""", lookahead)
                    if fn_match:
                        func_name = fn_match.group(1)
                        break

                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=methods,
                        function=func_name,
                        source=rel_path,
                        line=line_num,
                        framework="Symfony",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

        # 3. Classes and functions
        class_pattern = re.compile(r"""(?:abstract\s+)?(class|interface|trait|enum)\s+([a-zA-Z0-9_]+)""")
        func_pattern = re.compile(r"""(?:public|protected|private)?\s*(?:static\s+)?function\s+([a-zA-Z0-9_]+)\s*\(""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            cm = class_pattern.search(line_str)
            if cm:
                ckind, cname = cm.groups()
                symbols.append(
                    SymbolDefinition(
                        name=cname,
                        symbol_type=ckind,
                        source=rel_path,
                        line=line_num,
                        is_exported=True,
                    )
                )
                exports.append(cname)
                if "extends Model" in line_str or "extends Eloquent" in line_str or "model" in rel_path.lower():
                    models.append(
                        ModelDefinition(
                            name=cname,
                            source=rel_path,
                            line=line_num,
                            framework="Eloquent",
                            is_example=is_ex,
                        )
                    )

            fm = func_pattern.search(line_str)
            if fm:
                fname = fm.group(1)
                symbols.append(
                    SymbolDefinition(
                        name=fname,
                        symbol_type="function",
                        source=rel_path,
                        line=line_num,
                        is_exported=not fname.startswith("_"),
                    )
                )

        # 4. Client HTTP Calls: Http::get / Http::post
        client_pattern = re.compile(r"""Http::(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]""")
        for line_num, line in enumerate(lines, 1):
            cm = client_pattern.search(line)
            if cm:
                method = cm.group(1).upper()
                norm_url = normalize_route_path(cm.group(2))
                client_calls.append(
                    ClientCall(
                        path=norm_url,
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="Laravel-Http",
                    )
                )

        # 5. Unfinished / Dead Code
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""throw\s+new\s+\\?(?:BadMethodCallException|LogicException)""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"Unimplemented in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="PHP method explicitly throws BadMethodCallException or LogicException.",
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
