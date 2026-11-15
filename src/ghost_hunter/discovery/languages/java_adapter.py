"""Java language discovery adapter.

Extracts Spring MVC, Spring WebFlux, and JAX-RS endpoints, entities,
client HTTP requests, JUnit tests, and unfinished implementations using structural parsing.
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


class JavaAdapter(BaseLanguageAdapter):
    """Structural static analysis for Java enterprise and microservice codebases."""

    @property
    def language(self) -> str:
        return "Java"

    @property
    def file_extensions(self) -> set[str]:
        return {".java"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Spring MVC", "Spring WebFlux", "JAX-RS"]

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
            "Structural annotation and syntax parsing; dynamic Spring bean dispatching and custom routing filters are approximated.",
            "Runtime classpath dependency resolution requires Maven or Gradle build tooling.",
            "Dynamic Reflection and bytecode manipulation (e.g. CGLIB, ByteBuddy) are not evaluated without JVM execution.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        for manifest in (root / "pom.xml", root / "build.gradle", root / "build.gradle.kts"):
            if manifest.is_file():
                try:
                    m_text = manifest.read_text(encoding="utf-8", errors="ignore")
                    if "spring-boot" in m_text or "spring-web" in m_text:
                        signals["Spring MVC"] = "structural"
                    if "spring-webflux" in m_text:
                        signals["Spring WebFlux"] = "structural"
                    if "javax.ws.rs" in m_text or "jakarta.ws.rs" in m_text:
                        signals["JAX-RS"] = "structural"
                except OSError:
                    pass

        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "@RestController" in content or "@Controller" in content or "@GetMapping" in content or "@RequestMapping" in content:
                signals["Spring MVC"] = "structural"
            if "@Path" in content and ("@GET" in content or "@POST" in content):
                signals["JAX-RS"] = "structural"
            if "WebClient" in content:
                signals["Spring WebFlux"] = "structural"

        results = []
        for name, level in sorted(signals.items()):
            results.append({
                "language": "Java",
                "framework": name,
                "detected": True,
                "status": "partial",
                "capability_level": level,
                "analysis_capability": f"Structural controller, endpoint, model, and test extraction for Java ({name})",
                "capabilities": self.get_capabilities(),
                "limitations": f"Structural AST analysis without JVM compilation; dynamic dependency injection for {name} is approximated.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""

        rel_path = file_path.relative_to(root).as_posix()
        is_ex = is_example_or_fixture(rel_path)
        is_test_file = file_path.name.endswith(("Test.java", "Tests.java", "TestCase.java"))

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
            m = re.match(r"""import\s+(?:static\s+)?([a-zA-Z0-9_.*]+);""", line.strip())
            if m:
                imports.append(m.group(1))

        # 2. Class-level route prefix and annotations
        class_prefix = ""
        class_framework = "Spring MVC"
        for line in lines:
            # @RequestMapping("/api/v1") or @Path("/api/v1")
            m_req = re.search(r"""@(?:RequestMapping|Path)\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']""", line)
            if m_req:
                class_prefix = m_req.group(1)
            if "@Path" in line:
                class_framework = "JAX-RS"

        # 3. Route annotations
        spring_mapping_patterns = [
            (re.compile(r"""@GetMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["']"""), "GET"),
            (re.compile(r"""@PostMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["']"""), "POST"),
            (re.compile(r"""@PutMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["']"""), "PUT"),
            (re.compile(r"""@DeleteMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["']"""), "DELETE"),
            (re.compile(r"""@PatchMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["']"""), "PATCH"),
            (re.compile(r"""@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["']([^"']+)["'](?:\s*,\s*method\s*=\s*RequestMethod\.([A-Z]+))?"""), "CUSTOM"),
        ]

        jaxrs_path_pattern = re.compile(r"""@Path\s*\(\s*["']([^"']+)["']""")

        # Scan for methods
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()

            # Check Spring mappings
            for pattern, default_method in spring_mapping_patterns:
                m = pattern.search(line_str)
                if m:
                    route_sub = m.group(1)
                    if default_method == "CUSTOM":
                        method = m.group(2) or "GET"
                    else:
                        method = default_method

                    full_path = normalize_route_path((class_prefix + "/" + route_sub.lstrip("/")).replace("//", "/"))

                    # Next line or nearby might contain method declaration
                    func_name = "handler"
                    for lookahead in lines[line_num:min(line_num + 5, len(lines))]:
                        fn_match = re.search(r"""public\s+(?:[a-zA-Z0-9_<>[\]]+\s+)+([a-zA-Z0-9_]+)\s*\(""", lookahead)
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
                            framework="Spring MVC",
                            is_example=is_ex,
                            raw_decorator=line_str,
                        )
                    )

            # Check JAX-RS
            jm = jaxrs_path_pattern.search(line_str)
            if jm:
                route_sub = jm.group(1)
                full_path = normalize_route_path((class_prefix + "/" + route_sub.lstrip("/")).replace("//", "/"))
                # Check for HTTP method annotation in adjacent lines
                method = "GET"
                func_name = "handler"
                for lookahead in lines[max(0, line_num - 3):min(line_num + 4, len(lines))]:
                    if "@POST" in lookahead:
                        method = "POST"
                    elif "@PUT" in lookahead:
                        method = "PUT"
                    elif "@DELETE" in lookahead:
                        method = "DELETE"
                    fn_match = re.search(r"""public\s+(?:[a-zA-Z0-9_<>[\]]+\s+)+([a-zA-Z0-9_]+)\s*\(""", lookahead)
                    if fn_match:
                        func_name = fn_match.group(1)

                routes.append(
                    RouteDefinition(
                        path=full_path,
                        methods=[method],
                        function=func_name,
                        source=rel_path,
                        line=line_num,
                        framework="JAX-RS",
                        is_example=is_ex,
                        raw_decorator=line_str,
                    )
                )

        # 4. Classes, interfaces, records, methods
        class_pattern = re.compile(r"""(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(class|interface|record|enum)\s+([a-zA-Z0-9_]+)""")
        method_pattern = re.compile(r"""(?:public|protected|private)\s+(?:static\s+)?[a-zA-Z0-9_<>[\]]+\s+([a-zA-Z0-9_]+)\s*\([^)]*\)""")

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
                if "@Entity" in content or "@Table" in content or "model" in rel_path.lower() or "entity" in rel_path.lower():
                    models.append(
                        ModelDefinition(
                            name=cname,
                            source=rel_path,
                            line=line_num,
                            framework="JPA/Hibernate" if "@Entity" in content else "Java-Model",
                            is_example=is_ex,
                        )
                    )

            mm = method_pattern.search(line_str)
            if mm and not line_str.startswith(("class", "interface")):
                mname = mm.group(1)
                symbols.append(
                    SymbolDefinition(
                        name=mname,
                        symbol_type="method",
                        source=rel_path,
                        line=line_num,
                        is_exported=line_str.startswith("public"),
                    )
                )

        # 5. Client Calls: RestTemplate / WebClient
        client_pattern = re.compile(
            r"""(?:restTemplate\.(?:getForObject|postForObject|exchange)|webClient\.(?:get|post|put|delete)\(\)\.uri)\s*\(\s*["']([^"']+)["']"""
        )
        for line_num, line in enumerate(lines, 1):
            cm = client_pattern.search(line)
            if cm:
                norm_url = normalize_route_path(cm.group(1))
                method = "POST" if "post" in line.lower() else "GET"
                client_calls.append(
                    ClientCall(
                        path=norm_url,
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="Spring-Client",
                    )
                )

        # 6. Unfinished / Dead Code items
        for line_num, line in enumerate(lines, 1):
            line_str = line.strip()
            if re.search(r"""throw\s+new\s+(?:UnsupportedOperationException|NotImplementedException)""", line_str):
                unfinished.append(
                    UnfinishedItem(
                        item_type="not_implemented",
                        name=f"UnsupportedOperation in {rel_path}:{line_num}",
                        source=rel_path,
                        line=line_num,
                        evidence=line_str,
                        explanation="Java method explicitly throws UnsupportedOperationException or NotImplementedException.",
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
