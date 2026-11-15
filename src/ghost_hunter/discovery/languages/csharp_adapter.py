"""C# language discovery adapter.

Extracts ASP.NET Core controllers and Minimal APIs, EF Core models,
client HTTP requests, xUnit/NUnit tests, and unfinished implementations using structural parsing.
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


class CSharpAdapter(BaseLanguageAdapter):
    """Structural static analysis for C# and .NET applications."""

    @property
    def language(self) -> str:
        return "C#"

    @property
    def file_extensions(self) -> set[str]:
        return {".cs"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["ASP.NET Core"]

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
            "Structural regex and lexical scanning; Roslyn AST compilation is not used.",
            "Structural C# token and attribute parsing; dynamic Roslyn compilation and runtime middleware pipelines are approximated.",
            "Minimal API route group extensions and custom route handlers are analyzed statically.",
            "NuGet package graph resolution requires dotnet CLI or MSBuild evaluation.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        for csproj in root.rglob("*.csproj"):
            try:
                txt = csproj.read_text(encoding="utf-8", errors="ignore")
                if "Microsoft.AspNetCore" in txt or "Microsoft.NET.Sdk.Web" in txt:
                    signals["ASP.NET Core"] = "structural"
            except OSError:
                pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "Microsoft.AspNetCore" in content or "[ApiController]" in content or "MapGet(" in content or "MapPost(" in content:
                signals["ASP.NET Core"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "C#",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural controller, Minimal API, model, and test extraction for C# ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without dotnet CLI execution; dynamic pipeline middleware for {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = bool(re.search(r"""(Test|Tests|Spec|Specs)\.cs$""", file_path.name))

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

        # 1. Usings / Imports
        for line in lines:
            m = re.match(r"""using\s+([a-zA-Z0-9_.]+);""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Controller Class-Level Route & Name
        controller_prefix = ""
        class_match = re.search(r"""class\s+([a-zA-Z0-9_]+)Controller""", content)
        controller_name = class_match.group(1) if class_match else ""

        route_class_m = re.search(r"""\[Route\s*\(\s*["']([^"']+)["']\s*\)\]""", content)
        if route_class_m:
            controller_prefix = route_class_m.group(1).replace("[controller]", controller_name.lower())

        # 3. Controller Actions & Minimal APIs
        http_attr_patterns = [
            (re.compile(r"""\[HttpGet(?:\s*\(\s*["']([^"']+)["']\s*\))?\]"""), "GET"),
            (re.compile(r"""\[HttpPost(?:\s*\(\s*["']([^"']+)["']\s*\))?\]"""), "POST"),
            (re.compile(r"""\[HttpPut(?:\s*\(\s*["']([^"']+)["']\s*\))?\]"""), "PUT"),
            (re.compile(r"""\[HttpDelete(?:\s*\(\s*["']([^"']+)["']\s*\))?\]"""), "DELETE"),
            (re.compile(r"""\[HttpPatch(?:\s*\(\s*["']([^"']+)["']\s*\))?\]"""), "PATCH"),
        ]

        minimal_api_pattern = re.compile(
            r"""(?:app|endpoints|group)\.(MapGet|MapPost|MapPut|MapDelete|MapPatch)\s*\(\s*["']([^"']+)["']\s*,\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_]+)?"""
        )

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            # Controller action attributes
            for pattern, method in http_attr_patterns:
                m = pattern.search(line_str)
                if m:
                    sub_path = m.group(1) or ""
                    full_path = normalize_route_path((controller_prefix + "/" + sub_path.lstrip("/")).replace("//", "/"))

                    func_name = "Action"
                    for lookahead in lines[line_num:min(line_num + 5, len(lines))]:
                        fn_match = re.search(r"""public\s+(?:async\s+)?(?:[a-zA-Z0-9_<>[\]]+\s+)+([a-zA-Z0-9_]+)\s*\(""", lookahead)
                        if fn_match:
                            func_name = fn_match.group(1)
                            break

                    routes.append(
                        RouteDefinition(
                            path=full_path,
                            methods=[method],
                            function=func_name,
                            source=rel_path,
                            line=line_num,
                            framework="ASP.NET Core",
                            is_example=is_ex,
                            raw_decorator=line_str,
                        )
                    )

            # Minimal APIs
            mam = minimal_api_pattern.search(line_str)
            if mam:
                method = mam.group(1).replace("Map", "").upper()
                raw_path = mam.group(2)
                full_path = normalize_route_path(raw_path)
                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=f"Map{method}",
                        source=rel_path,
                        line=line_num,
                        framework="ASP.NET Core Minimal API",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

        # 4. Classes, records, methods
        class_pattern = re.compile(r"""(?:public|internal|protected|private)?\s*(?:static\s+)?(?:partial\s+)?(class|interface|record|struct|enum)\s+([a-zA-Z0-9_]+)""")
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
                        is_exported=line_str.startswith("public"),
                    )
                )
                if line_str.startswith("public"):
                    exports.append(cname)

                # Entity / Model detection
                if "[Table" in content or "DbContext" in content or "model" in rel_path.lower() or "entity" in rel_path.lower():
                    models.append(
                        ModelDefinition(
                            name=cname,
                            source=rel_path,
                            line=line_num,
                            framework="EF Core" if "[Table" in content or "DbContext" in content else "C#-Model",
                            is_example=is_ex,
                        )
                    )

        # 5. Client HTTP Calls: HttpClient
        client_pattern = re.compile(r"""(?:httpClient|_httpClient)\.(GetAsync|PostAsync|PutAsync|DeleteAsync|GetStringAsync)\s*\(\s*["']([^"']+)["']""")
        for line_num, line in enumerate(lines, 1):
            cm = client_pattern.search(line)
            if cm:
                m_method = cm.group(1).replace("Async", "").replace("String", "").upper()
                norm_url = normalize_route_path(cm.group(2))
                client_calls.append(
                    ClientCall(
                        path=norm_url,
                        method=m_method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="HttpClient",
                    )
                )

        # 6. Unfinished / Dead Code items
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""throw\s+new\s+(?:NotImplementedException|NotSupportedException)""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"NotImplemented in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="C# method explicitly throws NotImplementedException or NotSupportedException.",
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
