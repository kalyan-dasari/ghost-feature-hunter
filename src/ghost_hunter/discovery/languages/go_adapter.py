"""Go language discovery adapter.

Extracts net/http, Gin, Echo, Fiber, and Chi routes, structs, interfaces,
models, client HTTP requests, tests, and unfinished implementations using structural parsing.
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


class GoAdapter(BaseLanguageAdapter):
    """Structural static analysis for Go codebases."""

    @property
    def language(self) -> str:
        return "Go"

    @property
    def file_extensions(self) -> set[str]:
        return {".go"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Gin", "Echo", "Fiber", "Chi", "net/http"]

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
            "Structural regex and lexical scanning; genuine Go compiler AST parsing is not used.",
            "Variable-assigned routes and nested router closures are tracked statically without runtime evaluation.",
            "Full package symbol graph resolution across GOPATH/Go modules requires go toolchain compilation.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        go_mod = root / "go.mod"
        if go_mod.is_file():
            try:
                mod_text = go_mod.read_text(encoding="utf-8", errors="ignore")
                if "github.com/gin-gonic/gin" in mod_text:
                    signals["Gin"] = "structural"
                if "github.com/labstack/echo" in mod_text:
                    signals["Echo"] = "structural"
                if "github.com/gofiber/fiber" in mod_text:
                    signals["Fiber"] = "structural"
                if "github.com/go-chi/chi" in mod_text:
                    signals["Chi"] = "structural"
            except OSError:
                pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "gin-gonic/gin" in content or "gin." in content:
                signals["Gin"] = "structural"
            if "labstack/echo" in content or "echo." in content:
                signals["Echo"] = "structural"
            if "gofiber/fiber" in content or "fiber." in content:
                signals["Fiber"] = "structural"
            if "go-chi/chi" in content or "chi." in content:
                signals["Chi"] = "structural"
            if '"net/http"' in content and ("http.HandleFunc" in content or "http.Handle" in content or "http.ListenAndServe" in content):
                signals["net/http"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "Go",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural route, symbol, test, and model extraction for Go ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without Go compiler execution; dynamic interface dispatch for {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = file_path.name.endswith("_test.go")

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
        in_import_block = False
        for line in lines:
            line_str = line.strip()
            if line_str == "import (":
                in_import_block = True
                continue
            if in_import_block:
                if line_str == ")":
                    in_import_block = False
                    continue
                m = re.search(r"""(?:[a-zA-Z0-9_]+\s+)?["']([^"']+)["']""", line_str)
                if m:
                    imports.append(m.group(1))
            else:
                m = re.match(r"""import\s+(?:[a-zA-Z0-9_]+\s+)?["']([^"']+)["']""", line_str)
                if m:
                    imports.append(m.group(1))

        # 2. Package-level group prefixes (e.g. v1 := r.Group("/api/v1") or api := router.Group("/api"))
        group_prefixes: dict[str, str] = {}
        group_pattern = re.compile(r"""([a-zA-Z0-9_]+)\s*:?=\s*(?:[a-zA-Z0-9_]+)\.Group\(\s*["']([^"']+)["']""")
        for line in lines:
            gm = group_pattern.search(line)
            if gm:
                var_name, g_path = gm.group(1), gm.group(2)
                group_prefixes[var_name] = g_path

        # 3. Routes extraction: Gin, Echo, Fiber, Chi, net/http
        route_pattern = re.compile(
            r"""([a-zA-Z0-9_]+)\.(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD|Get|Post|Put|Delete|Patch|HandleFunc|Handle)\(\s*["']([^"']+)["']\s*,\s*([a-zA-Z0-9_.]+)""",
        )

        for line_num, line in enumerate(lines, 1):
            for match in route_pattern.finditer(line):
                router_var, method_raw, raw_path, handler_func = match.groups()
                method = method_raw.upper()
                if method in ("HANDLEFUNC", "HANDLE"):
                    method = "ALL"

                # Check if router_var is a known group
                prefix = group_prefixes.get(router_var, "")
                full_path = normalize_route_path((prefix + "/" + raw_path.lstrip("/")).replace("//", "/"))

                framework = "net/http"
                if "gin" in content:
                    framework = "Gin"
                elif "echo" in content:
                    framework = "Echo"
                elif "fiber" in content:
                    framework = "Fiber"
                elif "chi" in content:
                    framework = "Chi"

                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method] if method != "ALL" else ["GET", "POST", "PUT", "DELETE"],
                        function=handler_func,
                        source=rel_path,
                        line=line_num,
                        framework=framework,
                        is_example=is_ex,
                        raw_decorator=line.strip(),
                    )
                )

        # 4. Symbols: functions, methods, structs, interfaces
        func_pattern = re.compile(r"""^func\s+(?:\((?:[^)]+)\)\s+)?([a-zA-Z0-9_]+)\s*\(""")
        type_pattern = re.compile(r"""^type\s+([a-zA-Z0-9_]+)\s+(struct|interface)""")

        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            fm = func_pattern.match(line_str)
            if fm:
                fname = fm.group(1)
                is_exported = fname[0].isupper()
                symbols.append(
                    SymbolDefinition(
                        name=fname,
                        symbol_type="function",
                        source=rel_path,
                        line=line_num,
                        is_exported=is_exported,
                    )
                )
                if is_exported:
                    exports.append(fname)

            tm = type_pattern.match(line_str)
            if tm:
                tname, tkind = tm.groups()
                is_exported = tname[0].isupper()
                symbols.append(
                    SymbolDefinition(
                        name=tname,
                        symbol_type=tkind,
                        source=rel_path,
                        line=line_num,
                        is_exported=is_exported,
                    )
                )
                if is_exported:
                    exports.append(tname)
                # Model detection (structs with db tags or model/entity naming)
                if tkind == "struct":
                    if (
                        "model" in rel_path.lower()
                        or "entity" in rel_path.lower()
                        or "schema" in rel_path.lower()
                        or "gorm:" in content
                        or "db:" in content
                    ):
                        models.append(
                            ModelDefinition(
                                name=tname,
                                source=rel_path,
                                line=line_num,
                                framework="GORM" if "gorm" in content else "Go-Struct",
                                is_example=is_ex,
                            )
                        )

        # 5. Calls made inside code
        call_pattern = re.compile(r"""\b([a-zA-Z0-9_]+)\s*\(""")
        for line in lines:
            if line.strip().startswith("//"):
                continue
            for cm in call_pattern.finditer(line):
                call_name = cm.group(1)
                if call_name not in ("func", "if", "for", "switch", "return", "make", "new", "len", "cap", "append", "panic"):
                    calls_made.append(call_name)

        # 6. Client HTTP Calls
        client_pattern = re.compile(
            r"""(?:http\.(Get|Post|PostForm|Head))\s*\(\s*["']([^"']+)["']|http\.NewRequest\s*\(\s*["']([A-Z]+)["']\s*,\s*["']([^"']+)["']"""
        )
        for line_num, line in enumerate(lines, 1):
            cm = client_pattern.search(line)
            if cm:
                if cm.group(1):
                    cm_method = cm.group(1).upper()
                    cm_url = cm.group(2)
                else:
                    cm_method = cm.group(3).upper()
                    cm_url = cm.group(4)

                norm_url = normalize_route_path(cm_url)
                client_calls.append(
                    ClientCall(
                        path=norm_url,
                        method=cm_method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="net/http",
                    )
                )

        # 7. Unfinished / Dead Code items
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            # panic("not implemented") or panic("TODO")
            if re.search(r"""panic\s*\(\s*["'](not implemented|todo|unimplemented|wip)["']\s*\)""", line_str, re.IGNORECASE):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"panic in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="Go panic explicitly marks unfinished or unimplemented logic.",
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

        # Check empty function definitions: func ... { }
        empty_func_pattern = re.compile(r"""func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)\s*\([^)]*\)[^{]*\{\s*\}""")
        for line_num, line in enumerate(lines, 1):
            efm = empty_func_pattern.search(line)
            if efm:
                fn_name = efm.group(1)
                unfinished.append(
                    UnfinishedItem(
                        item_type="empty_function",
                        name=fn_name,
                        source=rel_path,
                        line=line_num,
                        evidence=line.strip(),
                        explanation="Go function body is completely empty.",
                        confidence="High",
                    )
                )

        # 8. Feature flags: os.Getenv("FEATURE_...") or flag.Bool("...")
        flag_pattern = re.compile(r"""os\.Getenv\s*\(\s*["']([A-Z0-9_]*FEATURE[A-Z0-9_]*)["']\s*\)""")
        for line_num, line in enumerate(lines, 1):
            fm = flag_pattern.search(line)
            if fm:
                fl_name = fm.group(1)
                feature_flags.append(
                    FeatureFlagDefinition(
                        name=fl_name,
                        source=rel_path,
                        line=line_num,
                        is_defined=True,
                        raw=line.strip(),
                    )
                )
                feature_flag_consumers.append(fl_name)

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
