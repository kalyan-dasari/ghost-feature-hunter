"""JavaScript and TypeScript discovery adapter.

Extracts Express routes, Next.js routes/pages, React components, client API calls,
UI buttons, empty handlers, and unfinished implementations using structural regex and lexical parsing.
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
)
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path
from ghost_hunter.discovery.project import is_example_or_fixture


class JavaScriptAdapter(BaseLanguageAdapter):
    """Static analysis for JavaScript and TypeScript codebases."""

    @property
    def language(self) -> str:
        return "JavaScript/TypeScript"

    @property
    def file_extensions(self) -> set[str]:
        return {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Express", "Next.js", "React"]

    def get_capabilities(self) -> dict[str, bool]:
        return {
            "route_extraction": True,
            "symbol_analysis": True,
            "ui_analysis": True,
            "reference_analysis": True,
            "duplicate_detection": False,  # Duplicate detection is Python AST only
            "unfinished_code_detection": True,
            "dependency_analysis": True,
            # Backwards compatibility flags
            "file_identification": True,
            "framework_identification": True,
            "import_export_discovery": True,
            "function_class_inventory": True,
            "local_reference_call_analysis": True,
            "backend_route_extraction": True,
            "frontend_api_call_extraction": True,
            "ui_navigation_connections": True,
            "test_discovery": True,
            "empty_unfinished_detection": True,
            "dependency_package_analysis": True,
        }

    def get_limitations(self) -> list[str]:
        return [
            "Lexical and structural regex analysis; dynamic middleware chains and higher-order components are approximated.",
            "Runtime client wrappers (e.g. dynamic tRPC or GraphQL queries) require schema/introspection.",
            "Dynamic Next.js catch-all routes ([...slug]) are normalized to standard parameter representations.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        # Check root and nested package.json files for dependencies
        pkg_paths = [root / "package.json"]
        for p in root.rglob("package.json"):
            if not any(part in (".next", "node_modules", "vendor", "dist", "build", "coverage", ".git") for part in p.parts):
                if p not in pkg_paths:
                    pkg_paths.append(p)

        import json
        for pkg_path in pkg_paths:
            if pkg_path.is_file():
                try:
                    pkg = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "next" in deps:
                        signals["Next.js"] = "supported"
                    if "express" in deps:
                        signals["Express"] = "supported"
                    if "react" in deps:
                        signals["React"] = "supported"
                except Exception:
                    pass

        # Code content scan
        for path in files[:200]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "express" in content and ("require('express')" in content or 'from "express"' in content or "from 'express'" in content):
                signals["Express"] = "supported"
            if "next" in content and ("from 'next" in content or 'from "next' in content):
                signals["Next.js"] = "supported"
            if "react" in content and ("from 'react'" in content or 'from "react"' in content or "React." in content):
                signals["React"] = "supported"

        results = []
        for name, status in sorted(signals.items()):
            results.append({
                "language": "JavaScript/TypeScript",
                "framework": name,
                "status": status,
                "analysis_capability": "Express routes, Next.js App/Pages routes, React components, client calls, and UI event connections",
                "limitations": "Dynamic higher-order components and runtime plugin middleware require manual review.",
            })
        if not results:
            results.append({
                "language": "JavaScript/TypeScript",
                "framework": "Standard / Node.js",
                "status": "supported",
                "analysis_capability": "Node.js entry points, exported symbols, client API calls, and unfinished implementation markers",
                "limitations": "No known web framework detected in package.json.",
            })
        return results

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        rel_path = file_path.relative_to(root).as_posix()
        is_example = is_example_or_fixture(rel_path)

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
        feature_flag_consumers: set[str] = set()

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {
                "routes": routes,
                "client_calls": client_calls,
                "models": models,
                "components": components,
                "ui_actions": ui_actions,
                "unfinished": unfinished,
                "symbols": symbols,
                "imports": imports,
                "exports": exports,
                "calls_made": calls_made,
                "feature_flags": feature_flags,
                "feature_flag_consumers": list(feature_flag_consumers),
            }

        lines = content.splitlines()

        # 1. Unfinished comment markers (TODO, FIXME, XXX, HACK)
        for idx, line in enumerate(lines, 1):
            if "//" in line or "/*" in line:
                match = re.search(r"(?://|/\*|\*)\s*\b(TODO|FIXME|XXX|HACK)\b:?(.*)", line, re.IGNORECASE)
                if match:
                    tag = match.group(1).upper()
                    detail = match.group(2).strip().rstrip("*/").strip()
                    unfinished.append(UnfinishedItem(
                        item_type="todo_marker",
                        name=f"{tag} in {rel_path}:{idx}",
                        source=rel_path,
                        line=idx,
                        evidence=line.strip(),
                        explanation=f"Unfinished implementation marker '{tag}': {detail or 'No description provided'}.",
                        confidence="Medium",
                        is_abstract_or_protocol=False,
                        why_intentional="May be a planned backlog item or deliberate deferred feature.",
                    ))

        # 2. Imports and Exports
        for line in lines:
            # Imports
            imp_match = re.search(r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""", line)
            if imp_match:
                pkg = imp_match.group(1) or imp_match.group(2)
                if pkg:
                    imports.append(pkg)
            # Exports
            exp_match = re.search(r"""export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([a-zA-Z0-9_$]+)""", line)
            if exp_match:
                exports.append(exp_match.group(1))

        # 3. Next.js App Router API Route Detection: app/api/**/route.ts
        if ("app/api/" in rel_path or "src/app/api/" in rel_path) and file_path.stem == "route":
            # Extract route path from directory
            parts = Path(rel_path).parts
            api_idx = -1
            for i, p in enumerate(parts):
                if p == "api":
                    api_idx = i
                    break
            if api_idx != -1:
                route_dir_parts = parts[api_idx:-1]
                inferred_path = "/" + "/".join(route_dir_parts)
                # Next.js parameter normalization: [id] -> {id}
                inferred_path = re.sub(r"\[([a-zA-Z0-9_]+)\]", r"{\1}", inferred_path)

                # Look for exported HTTP methods (GET, POST, PUT, DELETE, PATCH)
                for line_num, line in enumerate(lines, 1):
                    for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                        pattern = rf"""export\s+(?:async\s+)?function\s+{method}\b"""
                        if re.search(pattern, line):
                            routes.append(RouteDefinition(
                                path=normalize_route_path(inferred_path),
                                methods=[method],
                                function=f"{method} handler",
                                source=rel_path,
                                line=line_num,
                                framework="Next.js App Router",
                                is_example=is_example,
                            ))

        # 4. Next.js Pages Router API Route Detection: pages/api/**/*.ts
        elif ("pages/api/" in rel_path or "src/pages/api/" in rel_path) and not file_path.name.startswith("_"):
            parts = Path(rel_path).parts
            api_idx = -1
            for i, p in enumerate(parts):
                if p == "api":
                    api_idx = i
                    break
            if api_idx != -1:
                route_parts = parts[api_idx:-1] + (file_path.stem,)
                if route_parts[-1] == "index":
                    route_parts = route_parts[:-1]
                inferred_path = "/" + "/".join(route_parts)
                inferred_path = re.sub(r"\[([a-zA-Z0-9_]+)\]", r"{\1}", inferred_path)
                routes.append(RouteDefinition(
                    path=normalize_route_path(inferred_path),
                    methods=["ALL"],  # Pages router default export handles any method
                    function="handler",
                    source=rel_path,
                    line=1,
                    framework="Next.js Pages Router",
                    is_example=is_example,
                ))

        # 5. Express Route Detection: app.get('/api/...', ...), router.post(...)
        express_pattern = re.compile(
            r"""\b(?:app|router|server)\.(get|post|put|delete|patch|options|head|all)\s*\(\s*['"]([^'"]+)['"]""",
            re.IGNORECASE,
        )
        for line_num, line in enumerate(lines, 1):
            for m in express_pattern.finditer(line):
                method = m.group(1).upper()
                raw_path = m.group(2)
                methods = ["ALL"] if method == "ALL" else [method]
                routes.append(RouteDefinition(
                    path=normalize_route_path(raw_path),
                    methods=methods,
                    function=f"express_{method.lower()}",
                    source=rel_path,
                    line=line_num,
                    framework="Express",
                    is_example=is_example,
                    raw_decorator=line.strip(),
                ))

        # 6. Client API Calls (fetch, axios, $.ajax, form action, client.get)
        fetch_pattern = re.compile(
            r"""fetch\s*\(\s*['"]([^'"]+)['"](?:\s*,\s*\{[^}]*?method\s*:\s*['"]([a-zA-Z]+)['"])?""",
            re.IGNORECASE | re.DOTALL,
        )
        axios_method_pattern = re.compile(
            r"""(?:axios|api|client|apiClient)\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]""",
            re.IGNORECASE,
        )
        axios_call_pattern = re.compile(
            r"""(?:axios|api|client)\s*\(\s*['"]([^'"]+)['"](?:\s*,\s*\{[^}]*?method\s*:\s*['"]([a-zA-Z]+)['"])?""",
            re.IGNORECASE | re.DOTALL,
        )

        for line_num, line in enumerate(lines, 1):
            # fetch
            for m in fetch_pattern.finditer(line):
                url = m.group(1)
                method = (m.group(2) or "GET").upper()
                if url.startswith("/") or "/api" in url:
                    client_calls.append(ClientCall(
                        path=normalize_route_path(url),
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="fetch",
                    ))
            # axios.get / axios.post
            for m in axios_method_pattern.finditer(line):
                method = m.group(1).upper()
                url = m.group(2)
                if url.startswith("/") or "/api" in url:
                    client_calls.append(ClientCall(
                        path=normalize_route_path(url),
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="axios",
                    ))
            # axios(url, {method})
            for m in axios_call_pattern.finditer(line):
                url = m.group(1)
                method = (m.group(2) or "GET").upper()
                if url.startswith("/") or "/api" in url:
                    client_calls.append(ClientCall(
                        path=normalize_route_path(url),
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="axios",
                    ))
            # HTML form action
            form_action_match = re.search(r"""<form[^>]*\baction\s*=\s*['"]([^'"]+)['"](?:[^>]*\bmethod\s*=\s*['"]([a-zA-Z]+)['"])?""", line, re.IGNORECASE)
            if form_action_match:
                url = form_action_match.group(1)
                method = (form_action_match.group(2) or "POST").upper()
                if url.startswith("/") or "/api" in url:
                    client_calls.append(ClientCall(
                        path=normalize_route_path(url),
                        method=method,
                        source=rel_path,
                        line=line_num,
                        raw=line.strip(),
                        framework="HTML Form",
                    ))

        # 7. UI Actions, Buttons & Form Connections (React / JSX / HTML)
        # Parse multiline forms to identify working forms and unhandled forms
        working_form_spans: list[tuple[int, int]] = []
        form_pattern = re.compile(r"""<form\b([\s\S]*?)>([\s\S]*?)</form>""", re.IGNORECASE)
        for form_match in form_pattern.finditer(content):
            form_attrs = form_match.group(1)
            form_body = form_match.group(2)
            start_pos = form_match.start()
            end_pos = form_match.end()
            line_num = content.count("\n", 0, start_pos) + 1

            has_action = bool(re.search(r"""\baction\s*=""", form_attrs, re.IGNORECASE))
            has_onsubmit = bool(re.search(r"""\bon(?:S|s)ubmit\s*=""", form_attrs, re.IGNORECASE))

            if has_action or has_onsubmit:
                working_form_spans.append((start_pos, end_pos))
            else:
                has_inputs = bool(re.search(r"""<(?:input|select|textarea|button|Button)\b""", form_body, re.IGNORECASE))
                if has_inputs:
                    ui_actions.append(UIAction(
                        action_type="form",
                        label="Form",
                        target="none",
                        source=rel_path,
                        line=line_num,
                        raw=content[start_pos:min(start_pos + 200, end_pos)].strip(),
                        is_empty_handler=True,
                        has_handler=False,
                    ))

        # Parse multiline buttons
        btn_pattern = re.compile(r"""<(?:button|Button)\b([\s\S]*?)>([\s\S]*?)</(?:button|Button)>""", re.IGNORECASE)
        for btn_match in btn_pattern.finditer(content):
            btn_attrs = btn_match.group(1)
            btn_body = btn_match.group(2)
            start_pos = btn_match.start()
            line_num = content.count("\n", 0, start_pos) + 1

            label = re.sub(r"<[^>]+>", "", btn_body).strip() or "Button"
            is_submit_type = bool(re.search(r"""\btype\s*=\s*['"]submit['"]""", btn_attrs, re.IGNORECASE))
            in_working_form = any(f_start <= start_pos <= f_end for f_start, f_end in working_form_spans)
            is_button_type = bool(re.search(r"""\btype\s*=\s*['"]button['"]""", btn_attrs, re.IGNORECASE))

            has_click_attr = "onclick" in btn_attrs.lower()
            empty_click = bool(re.search(
                r"""onClick\s*=\s*\{(?:\(\s*\)\s*=>\s*\{|\s*function\s*\(\s*\)\s*\{)\s*\}""",
                btn_attrs
            ))

            if empty_click:
                ui_actions.append(UIAction(
                    action_type="button",
                    label=label,
                    target="empty_inline_handler",
                    source=rel_path,
                    line=line_num,
                    raw=content[start_pos:min(start_pos + 150, btn_match.end())].strip(),
                    is_empty_handler=True,
                    has_handler=True,
                ))
                unfinished.append(UnfinishedItem(
                    item_type="empty_handler",
                    name=f"Button '{label}' empty onClick",
                    source=rel_path,
                    line=line_num,
                    evidence=content[start_pos:min(start_pos + 150, btn_match.end())].strip(),
                    explanation=f"UI button '{label}' has an empty or no-op inline handler (onClick={{() => {{}}}}).",
                    confidence="High",
                    is_abstract_or_protocol=False,
                    why_intentional="May be a UI mockup or placeholder waiting for backend integration.",
                ))
            elif has_click_attr:
                ui_actions.append(UIAction(
                    action_type="button",
                    label=label,
                    target="handler",
                    source=rel_path,
                    line=line_num,
                    raw=content[start_pos:min(start_pos + 150, btn_match.end())].strip(),
                    is_empty_handler=False,
                    has_handler=True,
                ))
            elif is_submit_type or (in_working_form and not is_button_type):
                ui_actions.append(UIAction(
                    action_type="button",
                    label=label,
                    target="form_submit",
                    source=rel_path,
                    line=line_num,
                    raw=content[start_pos:min(start_pos + 150, btn_match.end())].strip(),
                    is_empty_handler=False,
                    has_handler=True,
                ))
            else:
                ui_actions.append(UIAction(
                    action_type="button",
                    label=label,
                    target="none",
                    source=rel_path,
                    line=line_num,
                    raw=content[start_pos:min(start_pos + 150, btn_match.end())].strip(),
                    is_empty_handler=False,
                    has_handler=False,
                ))

        # Navigation links: <Link href="/..."> or <a href="/...">
        link_pattern = re.compile(r"""<(?:Link|a)\s+[^>]*\bhref\s*=\s*['"]([^'"]+)['"][^>]*>([\s\S]*?)</(?:Link|a)>""", re.IGNORECASE)
        for link_match in link_pattern.finditer(content):
            target_url = link_match.group(1).strip()
            link_body = link_match.group(2)
            link_label = re.sub(r"<[^>]+>", "", link_body).strip() or target_url
            start_pos = link_match.start()
            line_num = content.count("\n", 0, start_pos) + 1
            if target_url.startswith("/") and not target_url.startswith(("//", "/#", "/_")):
                ui_actions.append(UIAction(
                    action_type="link",
                    label=link_label,
                    target=normalize_route_path(target_url),
                    source=rel_path,
                    line=line_num,
                    raw=content[start_pos:min(start_pos + 150, link_match.end())].strip(),
                    has_handler=True,
                ))

        # 8. Placeholder Rendering (e.g. <div>TODO</div>, <div>Coming Soon</div>)
        placeholder_render_pattern = re.compile(
            r"""<(?:div|p|h[1-6]|span)[^>]*>\s*(TODO|Coming Soon|Under Construction|Placeholder|Work in Progress)\s*</(?:div|p|h[1-6]|span)>""",
            re.IGNORECASE,
        )
        for line_num, line in enumerate(lines, 1):
            m = placeholder_render_pattern.search(line)
            if m:
                ph_text = m.group(1)
                components.append(ComponentDefinition(
                    name=file_path.stem,
                    source=rel_path,
                    line=line_num,
                    framework="React",
                    has_render=True,
                    is_placeholder_render=True,
                    placeholder_text=ph_text,
                ))
                unfinished.append(UnfinishedItem(
                    item_type="placeholder_component",
                    name=f"Placeholder render in {file_path.stem}",
                    source=rel_path,
                    line=line_num,
                    evidence=line.strip(),
                    explanation=f"Component renders static placeholder text ('{ph_text}') instead of functional UI.",
                    confidence="High",
                    is_abstract_or_protocol=False,
                    why_intentional="May be a temporary stub for an upcoming screen.",
                ))

        # 9. Empty Functions and Methods in JS/TS
        empty_func_pattern = re.compile(
            r"""(?:function\s+([a-zA-Z0-9_$]+)\s*\([^)]*\)|const\s+([a-zA-Z0-9_$]+)\s*=\s*(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*=>)\s*\{\s*\}"""
        )
        for line_num, line in enumerate(lines, 1):
            m = empty_func_pattern.search(line)
            if m:
                func_name = m.group(1) or m.group(2) or "anonymous"
                symbols.append(SymbolDefinition(
                    name=func_name,
                    symbol_type="function",
                    source=rel_path,
                    line=line_num,
                    is_exported=func_name in exports,
                ))
                unfinished.append(UnfinishedItem(
                    item_type="empty_function",
                    name=func_name,
                    source=rel_path,
                    line=line_num,
                    evidence=line.strip(),
                    explanation=f"Function '{func_name}' has an empty body ({{}}).",
                    confidence="Medium",
                    is_abstract_or_protocol=False,
                    why_intentional="May be an intentional no-op callback or interface implementation stub.",
                ))

        # 10. throw new Error("Not implemented") or throw new Error("TODO")
        not_impl_pattern = re.compile(r"""throw\s+new\s+Error\s*\(\s*['"](?:Not implemented|TODO|unimplemented)['"]\s*\)""", re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            if not_impl_pattern.search(line):
                unfinished.append(UnfinishedItem(
                    item_type="not_implemented",
                    name=f"unimplemented in {rel_path}:{line_num}",
                    source=rel_path,
                    line=line_num,
                    evidence=line.strip(),
                    explanation="Code explicitly throws 'Not implemented' or 'TODO' Error.",
                    confidence="High",
                    is_abstract_or_protocol=False,
                    why_intentional="Developer left an explicit placeholder exception.",
                ))

        # 11. Silent catch blocks: catch (err) {} or catch {}
        silent_catch_pattern = re.compile(r"""catch\s*(?:\([^)]*\))?\s*\{\s*\}""")
        for line_num, line in enumerate(lines, 1):
            if silent_catch_pattern.search(line):
                unfinished.append(UnfinishedItem(
                    item_type="silent_catch",
                    name=f"silent_catch in {rel_path}:{line_num}",
                    source=rel_path,
                    line=line_num,
                    evidence=line.strip(),
                    explanation="Catch block silently swallows error with an empty body ({}).",
                    confidence="High",
                    is_abstract_or_protocol=False,
                    why_intentional="May be intentionally ignoring a benign or expected exception.",
                ))

        # 12. Feature flag detection (FEATURE_*, ENABLE_*, FLAG_*)
        flag_pattern = re.compile(r"\b((?:FEATURE_|ENABLE_|FLAG_)[A-Z0-9_]+)\b")
        for idx, line in enumerate(lines, 1):
            def_match = re.search(r"""(?:const|let|var)\s+((?:FEATURE_|ENABLE_|FLAG_)[A-Z0-9_]+)\s*=""", line)
            if def_match:
                flag_name = def_match.group(1)
                feature_flags.append(FeatureFlagDefinition(
                    name=flag_name,
                    source=rel_path,
                    line=idx,
                    is_defined=True,
                    raw=line.strip(),
                ))
            if re.search(r"""\b(?:if\s*\(|switch\s*\(|\?|&&|\|\|)""", line):
                for flag_m in flag_pattern.finditer(line):
                    fname = flag_m.group(1)
                    if def_match and fname == def_match.group(1):
                        continue
                    feature_flag_consumers.add(fname)

        return {
            "routes": routes,
            "client_calls": client_calls,
            "models": models,
            "components": components,
            "ui_actions": ui_actions,
            "unfinished": unfinished,
            "symbols": symbols,
            "imports": imports,
            "exports": exports,
            "calls_made": calls_made,
            "feature_flags": feature_flags,
            "feature_flag_consumers": list(feature_flag_consumers),
        }
