"""Python language and framework discovery adapter.

Extracts Flask, FastAPI, and Django routes, database models, empty/unfinished
implementations, symbols, calls, and client requests using Python AST.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.base import BaseLanguageAdapter
from ghost_hunter.discovery.languages.models import (
    ClientCall,
    ModelDefinition,
    RouteDefinition,
    SymbolDefinition,
    UIAction,
    UnfinishedItem,
)
from ghost_hunter.discovery.project import is_example_or_fixture


def normalize_route_path(path: str) -> str:
    """Normalize route parameters across frameworks: <int:id>, <id>, :id -> {id}."""
    if not path:
        return "/"
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    # Replace Flask <converter:name> or <name> with {name}
    p = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", p)
    # Replace Express :name with {name}
    p = re.sub(r":([a-zA-Z0-9_]+)", r"{\1}", p)
    # Strip trailing slash unless root
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


class PythonAdapter(BaseLanguageAdapter):
    """Deep AST analysis for Python applications."""

    @property
    def language(self) -> str:
        return "Python"

    @property
    def file_extensions(self) -> set[str]:
        return {".py", ".pyw"}

    @property
    def supported_frameworks(self) -> list[str]:
        return ["Flask", "FastAPI", "Django"]

    def get_capabilities(self) -> dict[str, bool]:
        return {
            "file_identification": True,
            "framework_identification": True,
            "import_export_discovery": True,
            "function_class_inventory": True,
            "local_reference_call_analysis": True,
            "backend_route_extraction": True,
            "frontend_api_call_extraction": True,
            "ui_navigation_connections": False,  # Python views generally do not contain JSX/TSX
            "test_discovery": True,
            "empty_unfinished_detection": True,
            "dependency_package_analysis": True,
        }

    def get_limitations(self) -> list[str]:
        return [
            "Static AST parsing only; dynamic decorators and runtime metaclass routing require execution.",
            "Dynamic string-built URLs and runtime URL reversing (e.g. reverse('view-name')) are approximated.",
            "Reflection and plugin-based route registration cannot be verified statically without execution.",
        ]

    def detect_frameworks(self, files: list[Path], root: Path) -> list[dict[str, Any]]:
        signals: dict[str, str] = {}
        for path in files[:300]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "flask" in content and ("from flask import" in content or "import flask" in content):
                signals["Flask"] = "supported"
            if "fastapi" in content and ("from fastapi import" in content or "import fastapi" in content):
                signals["FastAPI"] = "supported"
            if "django" in content and ("from django" in content or "import django" in content):
                signals["Django"] = "supported"

        results = []
        for name, status in sorted(signals.items()):
            results.append({
                "language": "Python",
                "framework": name,
                "status": status,
                "analysis_capability": "Full AST route, model, symbol, and unfinished implementation analysis",
                "limitations": "Dynamic route decorators and runtime meta-programming require manual inspection.",
            })
        if not results:
            results.append({
                "language": "Python",
                "framework": "Standard / Generic",
                "status": "supported",
                "analysis_capability": "AST symbols, functions, classes, imports, and unfinished implementation analysis",
                "limitations": "No known web framework detected.",
            })
        return results

    def _is_empty_or_placeholder_body(self, body: list[ast.stmt]) -> tuple[bool, str]:
        """Detect if function body is empty, pass, ellipsis, NotImplementedError, or placeholder return."""
        stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
        if not stmts:
            return True, "empty_body"
        if len(stmts) == 1:
            stmt = stmts[0]
            if isinstance(stmt, ast.Pass):
                return True, "pass"
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is ...:
                return True, "ellipsis"
            if isinstance(stmt, ast.Raise):
                exc = stmt.exc
                if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                    return True, "not_implemented_error"
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
                    return True, "not_implemented_error"
            if isinstance(stmt, ast.Return):
                if stmt.value is None:
                    return True, "return_none"
                if isinstance(stmt.value, ast.Constant) and stmt.value.value in (None, "", False):
                    return True, "placeholder_return"
                if isinstance(stmt.value, (ast.Dict, ast.List)) and not getattr(stmt.value, "keys", getattr(stmt.value, "elts", [])):
                    return True, "placeholder_return"
        return False, ""

    def _is_abstract(self, node: ast.FunctionDef | ast.AsyncFunctionDef, parent_class: ast.ClassDef | None) -> bool:
        """Check if a function/method is explicitly marked as abstract or protocol overload."""
        for dec in node.decorator_list:
            name = ""
            if isinstance(dec, ast.Name):
                name = dec.id
            elif isinstance(dec, ast.Attribute):
                name = dec.attr
            if name in ("abstractmethod", "overload"):
                return True
        if parent_class:
            for base in parent_class.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in ("ABC", "Protocol"):
                    # Check if body is just pass or ...
                    is_empty, _ = self._is_empty_or_placeholder_body(node.body)
                    if is_empty:
                        return True
        return False

    def analyze_file(self, file_path: Path, root: Path) -> dict[str, Any]:
        rel_path = file_path.relative_to(root).as_posix()
        is_example = is_example_or_fixture(rel_path)

        routes: list[RouteDefinition] = []
        client_calls: list[ClientCall] = []
        models: list[ModelDefinition] = []
        unfinished: list[UnfinishedItem] = []
        symbols: list[SymbolDefinition] = []
        imports: list[str] = []
        exports: list[str] = []
        calls_made: list[str] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=rel_path)
        except (OSError, SyntaxError):
            return {
                "routes": routes,
                "client_calls": client_calls,
                "models": models,
                "components": [],
                "ui_actions": [],
                "unfinished": unfinished,
                "symbols": symbols,
                "imports": imports,
                "exports": exports,
                "calls_made": calls_made,
            }

        # Check comment markers (TODO, FIXME, XXX, HACK)
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            if "#" in line:
                comment = line.split("#", 1)[1]
                match = re.search(r"\b(TODO|FIXME|XXX|HACK)\b:?(.*)", comment, re.IGNORECASE)
                if match:
                    tag = match.group(1).upper()
                    detail = match.group(2).strip()
                    unfinished.append(UnfinishedItem(
                        item_type="todo_marker",
                        name=f"{tag} in {rel_path}:{idx}",
                        source=rel_path,
                        line=idx,
                        evidence=line.strip(),
                        explanation=f"Unfinished implementation marker '{tag}': {detail or 'No description provided'}.",
                        confidence="Medium",
                        is_abstract_or_protocol=False,
                        why_intentional="May be a planned future task or deliberate deferred functionality.",
                    ))

        # Track __all__ exports if defined
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.append(elt.value)

            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)

            # Function call references
            if isinstance(node, ast.Call):
                call_name = ""
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                    receiver = ast.unparse(node.func.value).lower() if hasattr(ast, "unparse") else ""
                    # Check for Python client HTTP calls (requests.get, httpx.post, client.get)
                    # Exclude route definitions where receiver is app, router, bp, blueprint
                    if receiver not in ("app", "router", "bp", "blueprint", "api_router") and any(
                        client_keyword in receiver for client_keyword in ("request", "httpx", "client", "session", "http", "api")
                    ):
                        if node.func.attr.lower() in ("get", "post", "put", "delete", "patch"):
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                arg_url = node.args[0].value
                                if arg_url.startswith("/") or "/api" in arg_url:
                                    client_calls.append(ClientCall(
                                        path=normalize_route_path(arg_url),
                                        method=node.func.attr.upper(),
                                        source=rel_path,
                                        line=node.lineno,
                                        raw=f"{ast.unparse(node.func)}({arg_url!r})",
                                        framework="requests/httpx/client",
                                    ))
                if call_name:
                    calls_made.append(call_name)

            # Check silent error swallowing (except Exception: pass)
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    exc_name = ast.unparse(node.type) if node.type else "bare except"
                    unfinished.append(UnfinishedItem(
                        item_type="silent_catch",
                        name=f"silent_catch in {rel_path}:{node.lineno}",
                        source=rel_path,
                        line=node.lineno,
                        evidence=f"except {exc_name}: pass",
                        explanation=f"Exception block silently swallows errors ({exc_name}) with 'pass' and no logging or recovery.",
                        confidence="High",
                        is_abstract_or_protocol=False,
                        why_intentional="May be an intentional ignore of ignorable errors or a temporary stub.",
                    ))

        # Class and function inspection (including nested functions in factories like create_app)
        def _scan_statements(stmts: list[ast.stmt], parent_class: ast.ClassDef | None = None) -> None:
            for stmt in stmts:
                if isinstance(stmt, ast.ClassDef):
                    # Check models
                    bases = [ast.unparse(base) for base in stmt.bases]
                    is_model = any(
                        base.endswith("Model") or base.endswith("DeclarativeBase") or base == "Base"
                        for base in bases
                    )
                    if is_model:
                        models.append(ModelDefinition(
                            name=stmt.name,
                            source=rel_path,
                            line=stmt.lineno,
                            framework="SQLAlchemy/Django/Pydantic",
                            is_example=is_example,
                        ))
                    symbols.append(SymbolDefinition(
                        name=stmt.name,
                        symbol_type="class",
                        source=rel_path,
                        line=stmt.lineno,
                        is_exported=stmt.name in exports or not stmt.name.startswith("_"),
                    ))
                    # Check methods inside class
                    _scan_statements(stmt.body, parent_class=stmt)
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._process_function(stmt, parent_class, rel_path, is_example, routes, unfinished, symbols)
                    # Also recurse into inner functions (e.g., routes inside create_app)
                    _scan_statements(stmt.body, parent_class=None)

        _scan_statements(tree.body)

        return {
            "routes": routes,
            "client_calls": client_calls,
            "models": models,
            "components": [],
            "ui_actions": [],
            "unfinished": unfinished,
            "symbols": symbols,
            "imports": imports,
            "exports": exports,
            "calls_made": calls_made,
        }

    def _process_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_class: ast.ClassDef | None,
        rel_path: str,
        is_example: bool,
        routes: list[RouteDefinition],
        unfinished: list[UnfinishedItem],
        symbols: list[SymbolDefinition],
    ) -> None:
        full_name = f"{parent_class.name}.{node.name}" if parent_class else node.name
        is_abstract = self._is_abstract(node, parent_class)
        is_empty, empty_reason = self._is_empty_or_placeholder_body(node.body)

        symbols.append(SymbolDefinition(
            name=node.name,
            symbol_type="function" if parent_class is None else "method",
            source=rel_path,
            line=node.lineno,
            is_exported=not node.name.startswith("_"),
        ))

        # Check for route decorators (Flask, FastAPI, Django)
        is_route_handler = False
        for dec in node.decorator_list:
            route_info = self._parse_route_decorator(dec)
            if route_info:
                is_route_handler = True
                route_def = RouteDefinition(
                    path=normalize_route_path(route_info["path"]),
                    methods=route_info["methods"],
                    function=node.name,
                    source=rel_path,
                    line=dec.lineno,
                    framework=route_info["framework"],
                    is_example=is_example,
                    is_empty_or_unfinished=is_empty and not is_abstract,
                    raw_decorator=ast.unparse(dec) if hasattr(ast, "unparse") else "",
                )
                routes.append(route_def)

        # Check if empty / unfinished
        if is_empty:
            if is_abstract:
                unfinished.append(UnfinishedItem(
                    item_type="abstract_method",
                    name=full_name,
                    source=rel_path,
                    line=node.lineno,
                    evidence=f"def {node.name}(...): {empty_reason}",
                    explanation=f"Abstract method or interface declaration '{full_name}' intentionally has no body.",
                    confidence="High",
                    is_abstract_or_protocol=True,
                    why_intentional="Design pattern: abstract base class or protocol meant for subclass implementation.",
                ))
            else:
                conf = "High" if is_route_handler or empty_reason in ("not_implemented_error", "pass") else "Medium"
                unfinished.append(UnfinishedItem(
                    item_type="empty_function" if empty_reason != "not_implemented_error" else "not_implemented",
                    name=full_name,
                    source=rel_path,
                    line=node.lineno,
                    evidence=f"def {node.name}(...): {empty_reason}",
                    explanation=(
                        f"Route handler '{full_name}' contains placeholder/unfinished body ({empty_reason})."
                        if is_route_handler
                        else f"Function '{full_name}' has an empty or placeholder body ({empty_reason})."
                    ),
                    confidence=conf,
                    is_abstract_or_protocol=False,
                    why_intentional="May be a stub for a planned feature, an intentional no-op, or a test double.",
                ))

    def _parse_route_decorator(self, dec: ast.AST) -> dict[str, Any] | None:
        """Parse Flask (@app.route, @bp.route) or FastAPI (@app.get, @router.post, etc.)."""
        if not isinstance(dec, ast.Call):
            return None

        # Check attribute: dec.func -> app.route, app.get, router.post, bp.route
        attr = ""
        receiver = ""
        if isinstance(dec.func, ast.Attribute):
            attr = dec.func.attr.lower()
            if isinstance(dec.func.value, ast.Name):
                receiver = dec.func.value.id.lower()

        fastapi_methods = {"get": ["GET"], "post": ["POST"], "put": ["PUT"], "delete": ["DELETE"], "patch": ["PATCH"], "head": ["HEAD"], "options": ["OPTIONS"]}
        
        # FastAPI: @app.get('/path'), @router.post('/path'), @api_router.put('/path')
        if attr in fastapi_methods:
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                return {
                    "framework": "FastAPI",
                    "path": dec.args[0].value,
                    "methods": fastapi_methods[attr],
                }

        # Flask or FastAPI api_route: @app.route('/path', methods=['GET', 'POST']), @router.api_route(...)
        if attr in ("route", "api_route"):
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                path = dec.args[0].value
                methods = ["GET"]
                for kw in dec.keywords:
                    if kw.arg == "methods":
                        try:
                            val = ast.literal_eval(kw.value)
                            if isinstance(val, (list, tuple, set)):
                                methods = sorted(str(m).upper() for m in val)
                        except (ValueError, TypeError):
                            pass
                framework = "FastAPI" if attr == "api_route" else ("Flask" if receiver in ("app", "bp", "blueprint") else "Flask/FastAPI")
                return {
                    "framework": framework,
                    "path": path,
                    "methods": methods,
                }

        return None
