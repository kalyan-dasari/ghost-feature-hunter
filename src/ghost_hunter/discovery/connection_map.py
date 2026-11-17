"""End-to-End Feature Connection Map & Cross-Layer Contract Verification.

Traces and models the full execution chain of software features across 8 layers:
1. UI Action (Buttons, forms, links, navigation, callbacks)
2. Client/API Call (Methods, endpoints, parameters, payloads)
3. Backend Route (Path, methods, application/service boundary)
4. Controller / Handler (Receiving function, execution flow)
5. Business Service (Real function/method calls to service logic)
6. Database / Model (ORM models, persistence, queries, transactions)
7. Response / UI State (Return values, serialization, state consumption)
8. Tests & Verification (Route execution, assertions, test fixtures)

Identifies missing links, broken wiring, method mismatches, auth gaps,
unprotected multi-mutation transactions, and orphaned endpoints/services.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.audit import (
    _evaluate_route_test_coverage,
    _inspect_js_test_blocks,
    _inspect_polyglot_test_blocks,
    _inspect_python_test_functions,
)
from ghost_hunter.discovery.ghost_features import match_route
from ghost_hunter.discovery.languages.models import (
    ClientCall,
    ComponentDefinition,
    ModelDefinition,
    RouteDefinition,
    SymbolDefinition,
    UIAction,
    UnfinishedItem,
)
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.project import (
    IGNORED_DIRECTORIES,
    classify_source_role,
    detect_project_context,
)


@dataclass
class ConnectionNode:
    id: str
    layer: str  # "ui", "client_api", "route", "controller", "service", "database", "response", "test"
    name: str
    source_file: str
    line: int
    status: str  # "CONNECTED", "BROKEN", "MISSING", "ORPHANED", "UNFINISHED", "UNKNOWN"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionEdge:
    source_id: str
    target_id: str
    link_type: str  # "ui_to_client", "client_to_route", "route_to_controller", "controller_to_service", "service_to_db", "controller_to_db", "controller_to_response", "route_to_test", "response_to_ui"
    status: str  # "CONNECTED", "BROKEN", "MISSING"
    description: str = ""
    contract_issues: list[str] = field(default_factory=list)


@dataclass
class ContractVerificationFinding:
    severity: str  # "Critical", "High", "Medium", "Low"
    category: str  # "method_mismatch", "path_mismatch", "missing_auth", "transaction_boundary", "unimplemented_handler", "missing_service", "unfinished_service", "unconsumed_response", "passive_test_assertion", "testing_gap", "unattached_ui_handler"
    feature_or_route: str
    message: str
    failure_scenario: str
    evidence: str
    recommended_fix: str


def _extract_python_calls_and_returns(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    """Inspect AST of a Python handler function to extract called service functions, return statements, and DB operations."""
    calls_made: list[str] = []
    service_calls: list[str] = []
    returns: list[dict[str, Any]] = []
    has_json_return = False
    status_code = 200

    for child in ast.walk(func_node):
        if isinstance(child, ast.Call):
            call_name = ""
            if isinstance(child.func, ast.Name):
                call_name = child.func.id
            elif isinstance(child.func, ast.Attribute):
                if isinstance(child.func.value, ast.Name):
                    call_name = f"{child.func.value.id}.{child.func.attr}"
                else:
                    call_name = child.func.attr
            if call_name:
                calls_made.append(call_name)
                if any(k in call_name.lower() for k in ("service", "process", "calculate", "charge", "reserve", "validate", "billing", "inventory")):
                    service_calls.append(call_name)

        if isinstance(child, ast.Return) and child.value is not None:
            # Check for jsonify or dict return
            ret_text = ""
            try:
                ret_text = ast.unparse(child.value)
            except Exception:
                pass
            ret_status = 200
            ret_fmt = "HTML/Template" if "render_template" in ret_text else "JSON" if ("jsonify" in ret_text or "{" in ret_text) else "Data"
            if isinstance(child.value, ast.Tuple) and len(child.value.elts) >= 2:
                # E.g. return jsonify(...), 201
                second = child.value.elts[1]
                if isinstance(second, ast.Constant) and isinstance(second.value, int):
                    ret_status = second.value
            returns.append({"status": ret_status, "format": ret_fmt, "raw": ret_text, "line": child.lineno})
            if ret_status != 200:
                status_code = ret_status
            if ret_fmt == "JSON":
                has_json_return = True

    return {
        "calls_made": calls_made,
        "service_calls": service_calls,
        "returns": returns,
        "has_json_return": has_json_return,
        "status_code": status_code,
    }


def generate_feature_connection_map(
    project_root: Path,
    target_feature: str | None = None,
) -> dict[str, Any]:
    """Generate an end-to-end 8-layer Feature Connection Map with cross-layer contract verification."""
    root = project_root.resolve()
    context = detect_project_context(root)
    registry = LanguageRegistry()
    scan_data = registry.scan_repository(root)

    routes: list[RouteDefinition] = scan_data.get("routes", [])
    client_calls: list[ClientCall] = scan_data.get("client_calls", [])
    ui_actions: list[UIAction] = scan_data.get("ui_actions", [])
    components: list[ComponentDefinition] = scan_data.get("components", [])
    symbols: list[SymbolDefinition] = scan_data.get("symbols", [])
    models: list[ModelDefinition] = scan_data.get("models", [])
    unfinished: list[UnfinishedItem] = scan_data.get("unfinished", [])
    app_boundaries = context.get("application_boundaries", [])
    has_multiple_apps = len([b for b in app_boundaries if not b.get("is_root")]) > 1

    # Filter by target feature/route if provided
    filter_norm = target_feature.strip("/").lower() if target_feature else None

    nodes: list[ConnectionNode] = []
    edges: list[ConnectionEdge] = []
    contract_findings: list[ContractVerificationFinding] = []

    # Map symbols by name for fast resolution of services
    symbols_by_name: dict[str, list[SymbolDefinition]] = {}
    for s in symbols:
        symbols_by_name.setdefault(s.name, []).append(s)

    # Collect test files for route coverage inspection
    test_files_data: list[tuple[str, str]] = []
    for tfile in root.rglob("*"):
        if tfile.is_file() and not any(p in IGNORED_DIRECTORIES for p in tfile.parts):
            role = classify_source_role(tfile.relative_to(root).as_posix(), root)
            if role in ("test", "fixture"):
                try:
                    test_files_data.append((tfile.relative_to(root).as_posix(), tfile.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    pass

    # Check for application-level global auth middleware (to avoid false-positive auth warnings)
    has_global_auth_middleware = False
    for p in root.rglob("*"):
        if p.is_file() and p.name in ("app.py", "main.py", "server.js", "app.js", "index.ts", "Startup.cs", "Program.cs"):
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"""(?:before_request|authMiddleware|UseAuthentication|UseAuthorization|app\.use\([^)]*auth)""", txt):
                    has_global_auth_middleware = True
                    break
            except OSError:
                pass

    # --------------------------------------------------------------------------
    # 1. UI Layer Nodes (Layer 1)
    # --------------------------------------------------------------------------
    ui_nodes: list[ConnectionNode] = []
    ui_nodes_by_target: dict[str, list[ConnectionNode]] = {}
    for idx, act in enumerate(ui_actions, 1):
        if filter_norm and filter_norm not in act.target.lower() and filter_norm not in act.label.lower():
            continue
        status = "BROKEN" if (act.is_empty_handler or not act.has_handler) else "CONNECTED"
        node_id = f"ui_{act.action_type}_{idx}"
        node = ConnectionNode(
            id=node_id,
            layer="ui",
            name=f"{act.action_type.upper()}: {act.label or act.target}",
            source_file=act.source,
            line=act.line,
            status=status,
            details={
                "action_type": act.action_type,
                "target": act.target,
                "app_name": act.app_name,
                "has_handler": act.has_handler,
                "is_empty_handler": act.is_empty_handler,
            },
        )
        nodes.append(node)
        ui_nodes.append(node)
        ui_nodes_by_target.setdefault(act.target, []).append(node)
        ui_nodes_by_target.setdefault(normalize_route_path(act.target), []).append(node)

        if act.is_empty_handler or not act.has_handler:
            contract_findings.append(
                ContractVerificationFinding(
                    severity="Medium",
                    category="unattached_ui_handler",
                    feature_or_route=act.label or act.target,
                    message=f"UI {act.action_type} '{act.label}' has no functional event handler",
                    failure_scenario="User interaction will produce no response or trigger an unhandled UI state.",
                    evidence=f"{act.source}:{act.line} -> {act.raw}",
                    recommended_fix="Attach a functional event handler or callback to the UI element.",
                )
            )

    # --------------------------------------------------------------------------
    # 2. Client API Layer Nodes (Layer 2)
    # --------------------------------------------------------------------------
    client_nodes: list[ConnectionNode] = []
    client_nodes_by_path: dict[str, list[ConnectionNode]] = {}
    for idx, call in enumerate(client_calls, 1):
        if filter_norm and filter_norm not in call.path.lower():
            continue
        node_id = f"client_call_{idx}"
        node = ConnectionNode(
            id=node_id,
            layer="client_api",
            name=f"{call.method.upper()} {call.path}",
            source_file=call.source,
            line=call.line,
            status="CONNECTED",
            details={
                "method": call.method.upper(),
                "path": call.path,
                "app_name": call.app_name,
                "caller_function": call.caller_function,
                "raw": call.raw,
            },
        )
        nodes.append(node)
        client_nodes.append(node)
        client_nodes_by_path.setdefault(normalize_route_path(call.path), []).append(node)

        # Connect UI -> Client API
        # A. Direct path match: UI target matches endpoint path
        # B. Named callback match: UI target matches caller_function (e.g. onClick={handleCheckout})
        # C. In-file proximity: same source file
        norm_call_path = normalize_route_path(call.path)
        matched_ui = False
        for u_node in ui_nodes:
            u_target = u_node.details.get("target", "")
            is_direct_path = (u_target == norm_call_path or u_target == call.path)
            is_callback_match = (call.caller_function and u_target == call.caller_function)
            is_same_file = (u_node.source_file == call.source and u_node.layer == "ui" and not call.caller_function)

            if is_direct_path or is_callback_match or is_same_file:
                matched_ui = True
                edges.append(
                    ConnectionEdge(
                        source_id=u_node.id,
                        target_id=node.id,
                        link_type="named_callback" if is_callback_match else "ui_to_client",
                        status="CONNECTED" if u_node.status == "CONNECTED" else "BROKEN",
                        description=f"UI element invokes {call.method} {call.path}" + (f" via '{call.caller_function}()'" if is_callback_match else ""),
                    )
                )

    # --------------------------------------------------------------------------
    # 3. Route & Controller Layer Nodes (Layers 3 & 4)
    # --------------------------------------------------------------------------
    route_nodes: list[ConnectionNode] = []
    route_node_by_path: dict[str, ConnectionNode] = {}
    for idx, r in enumerate(routes, 1):
        if filter_norm and filter_norm not in r.path.lower() and filter_norm not in r.function.lower():
            continue
        r_status = "UNFINISHED" if r.is_empty_or_unfinished else "CONNECTED"
        r_id = f"route_{idx}"
        r_node = ConnectionNode(
            id=r_id,
            layer="route",
            name=f"{'/'.join(r.methods)} {r.path}",
            source_file=r.source,
            line=r.line,
            status=r_status,
            details={
                "methods": r.methods,
                "path": r.path,
                "function": r.function,
                "framework": r.framework,
                "app_name": r.app_name,
                "source_role": r.source_role,
            },
        )
        nodes.append(r_node)
        route_nodes.append(r_node)
        route_node_by_path[normalize_route_path(r.path)] = r_node

        # Controller / Handler Node (Layer 4)
        ctrl_id = f"ctrl_{idx}_{r.function}"
        ctrl_node = ConnectionNode(
            id=ctrl_id,
            layer="controller",
            name=f"def {r.function}()",
            source_file=r.source,
            line=r.line,
            status="UNFINISHED" if r.is_empty_or_unfinished else "CONNECTED",
            details={"function": r.function, "framework": r.framework, "route_id": r_id},
        )
        nodes.append(ctrl_node)

        # Route -> Controller Edge
        edges.append(
            ConnectionEdge(
                source_id=r_id,
                target_id=ctrl_id,
                link_type="route_to_controller",
                status="BROKEN" if r.is_empty_or_unfinished else "CONNECTED",
                description=f"Route dispatches to handler '{r.function}'",
            )
        )

        # Contract Check: Unimplemented handler
        if r.is_empty_or_unfinished:
            contract_findings.append(
                ContractVerificationFinding(
                    severity="High",
                    category="unimplemented_handler",
                    feature_or_route=r.path,
                    message=f"Route '{r.path}' handler '{r.function}' is an empty or placeholder stub",
                    failure_scenario="Incoming requests will return empty body or crash with NotImplementedError/panic.",
                    evidence=f"{r.source}:{r.line} -> def {r.function}()",
                    recommended_fix=f"Implement the business logic in '{r.function}'.",
                )
            )

        # Contract Check: Sensitive route lacking auth (taking global middleware into account)
        is_sensitive = any(
            t in r.path.lower()
            for t in ("/admin", "/delete", "/secure", "/payment", "/accounts", "/billing")
        )
        has_local_auth = bool(re.search(r"""(?i)\b(auth|login|permit|secure|role|protect)\b""", r.raw_decorator or ""))
        if is_sensitive and not has_local_auth and not has_global_auth_middleware:
            contract_findings.append(
                ContractVerificationFinding(
                    severity="High",
                    category="missing_auth",
                    feature_or_route=r.path,
                    message=f"Sensitive route '{r.path}' lacks declarative authorization check",
                    failure_scenario="Unauthenticated callers can access privileged endpoint operations.",
                    evidence=f"{r.source}:{r.line} -> {r.raw_decorator or r.function}",
                    recommended_fix="Apply an authentication or role-based check decorator/middleware.",
                )
            )

    # --------------------------------------------------------------------------
    # Connect Client API -> Route (Cross-Layer Contract Verification)
    # --------------------------------------------------------------------------
    for c_node in client_nodes:
        c_path = c_node.details["path"]
        c_method = c_node.details["method"]
        c_app = c_node.details["app_name"]

        if has_multiple_apps and c_app:
            candidate_routes = [
                r for r in routes
                if r.source_role == "application_source"
                and (r.app_name == c_app or r.app_name in ("primary", "", "root"))
            ]
        else:
            candidate_routes = [r for r in routes if r.source_role == "application_source"]

        matching_routes = [r for r in candidate_routes if match_route(c_path, r.path)]

        if not matching_routes:
            all_matching = [r for r in routes if r.source_role == "application_source" and match_route(c_path, r.path)]
            if all_matching:
                other_apps = sorted({r.app_name for r in all_matching if r.app_name})
                missing_id = f"missing_route_{c_node.id}"
                nodes.append(
                    ConnectionNode(
                        id=missing_id,
                        layer="route",
                        name=f"MISSING: {c_path}",
                        source_file=c_node.source_file,
                        line=c_node.line,
                        status="MISSING",
                        details={"note": f"Exists in unrelated app(s): {', '.join(other_apps)}, but not in '{c_app}'"},
                    )
                )
                edges.append(
                    ConnectionEdge(
                        source_id=c_node.id,
                        target_id=missing_id,
                        link_type="client_to_route",
                        status="BROKEN",
                        description=f"Client calls endpoint not registered in '{c_app}' (exists in {', '.join(other_apps)})",
                        contract_issues=[f"Route boundary mismatch: '{c_path}' not declared in application '{c_app}'"],
                    )
                )
                contract_findings.append(
                    ContractVerificationFinding(
                        severity="High",
                        category="path_mismatch",
                        feature_or_route=c_path,
                        message=f"Client calls endpoint '{c_path}' outside its application boundary '{c_app}'",
                        failure_scenario="Requests will receive HTTP 404 at runtime.",
                        evidence=f"{c_node.source_file}:{c_node.line} -> {c_node.details['raw']}",
                        recommended_fix=f"Register route handler in application '{c_app}' or configure an API gateway route.",
                    )
                )
            else:
                missing_id = f"missing_route_{c_node.id}"
                nodes.append(
                    ConnectionNode(
                        id=missing_id,
                        layer="route",
                        name=f"MISSING: {c_path}",
                        source_file=c_node.source_file,
                        line=c_node.line,
                        status="MISSING",
                    )
                )
                edges.append(
                    ConnectionEdge(
                        source_id=c_node.id,
                        target_id=missing_id,
                        link_type="client_to_route",
                        status="MISSING",
                        description=f"Client calls unregistered endpoint '{c_path}'",
                        contract_issues=[f"Endpoint '{c_path}' has no backend route handler in project"],
                    )
                )
                contract_findings.append(
                    ContractVerificationFinding(
                        severity="High",
                        category="path_mismatch",
                        feature_or_route=c_path,
                        message=f"Client calls unregistered endpoint '{c_path}'",
                        failure_scenario="Requests will fail with HTTP 404.",
                        evidence=f"{c_node.source_file}:{c_node.line} -> {c_node.details['raw']}",
                        recommended_fix=f"Register route handler for '{c_path}' in backend.",
                    )
                )
        else:
            target_route = matching_routes[0]
            norm_target_path = normalize_route_path(target_route.path)
            target_r_node = route_node_by_path.get(norm_target_path)
            target_node_id = target_r_node.id if target_r_node else f"route_{target_route.path}"

            supported_methods = {m.upper() for r in matching_routes for m in r.methods}
            is_method_compatible = "ALL" in supported_methods or c_method in supported_methods

            issues = []
            if not is_method_compatible:
                issues.append(f"HTTP Method mismatch: client calls {c_method}, but route only accepts {sorted(supported_methods)}")
                contract_findings.append(
                    ContractVerificationFinding(
                        severity="High",
                        category="method_mismatch",
                        feature_or_route=target_route.path,
                        message=f"HTTP method mismatch: Client sends {c_method}, backend only supports {sorted(supported_methods)}",
                        failure_scenario="HTTP request will fail with HTTP 405 Method Not Allowed.",
                        evidence=f"{c_node.source_file}:{c_node.line} ({c_method}) vs {target_route.source}:{target_route.line} ({sorted(supported_methods)})",
                        recommended_fix=f"Add '{c_method}' to route handler methods or update client request.",
                    )
                )

            edges.append(
                ConnectionEdge(
                    source_id=c_node.id,
                    target_id=target_node_id,
                    link_type="client_to_route",
                    status="CONNECTED" if is_method_compatible else "BROKEN",
                    description=f"Client {c_method} -> Route {target_route.path}",
                    contract_issues=issues,
                )
            )

    # --------------------------------------------------------------------------
    # 4. Service, Database & Response Layer Nodes (Layers 5, 6, 7)
    # --------------------------------------------------------------------------
    db_mutation_re = re.compile(
        r"""\b(?:db\.session\.(?:add|delete|commit)|objects\.(?:create|delete|update)|repository\.(?:save|delete)|\.save\(|\.delete\()\b"""
    )
    db_query_re = re.compile(
        r"""\b(?:db\.session\.query|\.query\.|\.objects\.all|\.objects\.filter|\.objects\.get|cursor\.execute\s*\(\s*['"]SELECT)\b""",
        re.IGNORECASE,
    )
    transaction_wrapper_re = re.compile(
        r"""\b(?:transaction\.atomic|db\.session\.begin|@transactional|@transaction\.atomic|TransactionScope|db\.Begin|DB::transaction)\b"""
    )

    for r_node in route_nodes:
        source_p = root / r_node.source_file
        if not source_p.is_file():
            continue
        try:
            content = source_p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        handler_name = r_node.details.get("function", "")
        ctrl_node_id = f"ctrl_{r_node.id.split('_')[1]}_{handler_name}"
        lines = content.splitlines()

        # Parse handler body
        handler_lines: list[str] = []
        in_handler = False
        func_pat = re.compile(rf"""(?:def|func|function)\s+{re.escape(handler_name)}\b""")
        for idx, l in enumerate(lines, 1):
            if func_pat.search(l):
                in_handler = True
                handler_lines.append(l)
                continue
            if in_handler:
                if (l.startswith("def ") or l.startswith("func ") or l.startswith("class ")) and not l.startswith("    "):
                    break
                handler_lines.append(l)

        handler_text = "\n".join(handler_lines)
        mutations = [l for l in handler_lines if db_mutation_re.search(l)]
        queries = [l for l in handler_lines if db_query_re.search(l)]
        has_tx = bool(transaction_wrapper_re.search(handler_text))

        # --- Layer 5: Business Service Logic Tracing ---
        service_node_id: str | None = None
        called_services: list[str] = []
        if source_p.suffix == ".py":
            try:
                tree = ast.parse(content)
                for node_stmt in ast.walk(tree):
                    if isinstance(node_stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and node_stmt.name == handler_name:
                        info = _extract_python_calls_and_returns(node_stmt)
                        called_services = info["service_calls"]
                        break
            except Exception:
                pass
        else:
            # Polyglot fallback: look for service.method calls
            service_call_pat = re.compile(r"""\b([a-zA-Z0-9_]+Service|[a-zA-Z0-9_]+Manager|[a-zA-Z0-9_]+Client)\.([a-zA-Z0-9_]+)\s*\(""")
            for sm in service_call_pat.finditer(handler_text):
                called_services.append(f"{sm.group(1)}.{sm.group(2)}")

        for s_call in called_services:
            base_s_name = s_call.split(".")[-1]
            matching_syms = symbols_by_name.get(base_s_name, [])
            if matching_syms:
                sym = matching_syms[0]
                s_id = f"service_{sym.name}_{r_node.id}"
                service_node_id = s_id
                is_unf = any(u.name == sym.name for u in unfinished)
                nodes.append(
                    ConnectionNode(
                        id=s_id,
                        layer="service",
                        name=f"Service: {sym.name}()",
                        source_file=sym.source,
                        line=sym.line,
                        status="UNFINISHED" if is_unf else "CONNECTED",
                        details={"service_call": s_call, "source_file": sym.source},
                    )
                )
                edges.append(
                    ConnectionEdge(
                        source_id=ctrl_node_id,
                        target_id=s_id,
                        link_type="controller_to_service",
                        status="BROKEN" if is_unf else "CONNECTED",
                        description=f"Controller calls service '{s_call}()'",
                        contract_issues=[f"Service '{sym.name}' has unfinished implementation"] if is_unf else [],
                    )
                )
                if is_unf:
                    contract_findings.append(
                        ContractVerificationFinding(
                            severity="High",
                            category="unfinished_service",
                            feature_or_route=r_node.details.get("path", ""),
                            message=f"Handler '{handler_name}' calls unfinished service '{sym.name}'",
                            failure_scenario="Execution will raise NotImplementedError or return unhandled placeholder.",
                            evidence=f"{sym.source}:{sym.line} -> def {sym.name}()",
                            recommended_fix=f"Implement required logic in service '{sym.name}'.",
                        )
                    )
            else:
                # Missing service implementation
                s_id = f"missing_service_{base_s_name}_{r_node.id}"
                service_node_id = s_id
                nodes.append(
                    ConnectionNode(
                        id=s_id,
                        layer="service",
                        name=f"MISSING: {s_call}()",
                        source_file=r_node.source_file,
                        line=r_node.line,
                        status="MISSING",
                        details={"service_call": s_call},
                    )
                )
                edges.append(
                    ConnectionEdge(
                        source_id=ctrl_node_id,
                        target_id=s_id,
                        link_type="controller_to_service",
                        status="MISSING",
                        description=f"Handler calls unregistered service '{s_call}()'",
                        contract_issues=[f"Service function '{s_call}' is not implemented in codebase"],
                    )
                )
                contract_findings.append(
                    ContractVerificationFinding(
                        severity="High",
                        category="missing_service",
                        feature_or_route=r_node.details.get("path", ""),
                        message=f"Handler '{handler_name}' invokes missing service function '{s_call}'",
                        failure_scenario="Invocation will fail with NameError, AttributeError, or unresolved dependency.",
                        evidence=f"{r_node.source_file}:{r_node.line} -> {s_call}()",
                        recommended_fix=f"Implement service function '{s_call}'.",
                    )
                )

        # --- Layer 6: Database / Model Tracing ---
        db_parent_id = service_node_id if service_node_id else ctrl_node_id

        # Check both handler_text and any called service implementations for model & db queries/mutations
        combined_db_text = handler_text
        if called_services:
            for s_call in called_services:
                base_s_name = s_call.split(".")[-1]
                matching_syms = symbols_by_name.get(base_s_name, [])
                for sym in matching_syms:
                    service_file = root / sym.source
                    if service_file.is_file():
                        try:
                            combined_db_text += "\n" + service_file.read_text(encoding="utf-8", errors="ignore")
                        except OSError:
                            pass

        matched_models = [m.name for m in models if m.name.lower() in combined_db_text.lower()]
        svc_mutations = re.findall(r"""(?:\.add\(|\.delete\(|\.update\(|\.insert\(|\.save\()""", combined_db_text)
        svc_queries = re.findall(r"""(?:\.query|\.filter\(|\.filter_by\(|\.find|\.get\(|\.all\(|\.first\()""", combined_db_text)
        all_mutations = list(set(mutations + svc_mutations))
        all_queries = list(set(queries + svc_queries))

        if all_mutations or all_queries or matched_models:
            db_node_id = f"db_{r_node.id}"
            has_db_risk = len(all_mutations) >= 2 and not has_tx
            db_status = "BROKEN" if has_db_risk else "CONNECTED"
            model_summary = f"Models: {', '.join(matched_models[:3])}" if matched_models else "DB Operations"
            nodes.append(
                ConnectionNode(
                    id=db_node_id,
                    layer="database",
                    name=f"{model_summary} ({len(all_mutations)} writes, {len(all_queries)} reads)",
                    source_file=r_node.source_file,
                    line=r_node.line,
                    status=db_status,
                    details={
                        "mutation_count": len(all_mutations),
                        "query_count": len(all_queries),
                        "has_transaction": has_tx,
                        "models": matched_models,
                    },
                )
            )
            edges.append(
                ConnectionEdge(
                    source_id=db_parent_id,
                    target_id=db_node_id,
                    link_type="service_to_db" if service_node_id else "controller_to_db",
                    status=db_status,
                    description=f"Modifies database state ({len(all_mutations)} writes, {len(all_queries)} reads)",
                    contract_issues=["Missing atomic transaction wrapper on multiple mutations"] if has_db_risk else [],
                )
            )

            if has_db_risk:
                contract_findings.append(
                    ContractVerificationFinding(
                        severity="Medium",
                        category="transaction_boundary",
                        feature_or_route=r_node.details.get("path", ""),
                        message=f"Handler '{handler_name}' performs {len(mutations)} database writes without atomic transaction",
                        failure_scenario="Partial commit if an intermediate write fails, resulting in database corruption.",
                        evidence=f"{r_node.source_file}:{r_node.line} -> def {handler_name}() ({len(mutations)} mutations)",
                        recommended_fix=f"Wrap mutations in '{handler_name}' inside an atomic transaction block.",
                    )
                )

        # --- Layer 7: Response / UI State Tracing ---
        # Detect return format and status code
        resp_status = 200
        resp_fmt = "JSON"
        if re.search(r"""(?:render_template|res\.render)\b""", handler_text):
            resp_fmt = "HTML/Template"
        elif re.search(r"""(?:jsonify|res\.json|Response\.json)\b""", handler_text) or "return {" in handler_text:
            resp_fmt = "JSON"

        status_match = re.search(r"""(?:,\s*([2-5][0-9]{2})|status(?:Code)?\s*=\s*([2-5][0-9]{2}))\b""", handler_text)
        if status_match:
            resp_status = int(status_match.group(1) or status_match.group(2))
        elif any(m in ("POST",) for m in r_node.details.get("methods", [])):
            resp_status = 201 if "create" in handler_name.lower() else 200

        resp_node_id = f"resp_{r_node.id}"
        nodes.append(
            ConnectionNode(
                id=resp_node_id,
                layer="response",
                name=f"Response: HTTP {resp_status} ({resp_fmt})",
                source_file=r_node.source_file,
                line=r_node.line,
                status="CONNECTED",
                details={"status_code": resp_status, "format": resp_fmt},
            )
        )
        edges.append(
            ConnectionEdge(
                source_id=ctrl_node_id,
                target_id=resp_node_id,
                link_type="controller_to_response",
                status="CONNECTED",
                description=f"Handler returns HTTP {resp_status} {resp_fmt}",
            )
        )

        # Connect Response back to UI (Layer 7 -> UI State Consumption)
        for c_node in client_nodes:
            if match_route(c_node.details.get("path", ""), r_node.details.get("path", "")):
                # Check if client consumes response
                raw_call = c_node.details.get("raw", "")
                source_client_p = root / c_node.source_file
                client_text = ""
                if source_client_p.is_file():
                    try:
                        client_text = source_client_p.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        pass

                consumes_response = bool(re.search(r"""(?:\.then\s*\([^)]*json|await\s+[^;]*\.json|setState|dispatch|\bdata\b)""", client_text))
                if not consumes_response and resp_fmt == "JSON":
                    contract_findings.append(
                        ContractVerificationFinding(
                            severity="Low",
                            category="unconsumed_response",
                            feature_or_route=r_node.details.get("path", ""),
                            message=f"Client calls '{r_node.details.get('path')}' but ignores returned response payload",
                            failure_scenario="Frontend UI state will not update with server-confirmed data.",
                            evidence=f"{c_node.source_file}:{c_node.line} -> {raw_call}",
                            recommended_fix="Parse response JSON and update UI state.",
                        )
                    )

        # ----------------------------------------------------------------------
        # 5. Tests & Verification Layer (Layer 8)
        # ----------------------------------------------------------------------
        route_cov = _evaluate_route_test_coverage(
            RouteDefinition(
                path=r_node.details["path"],
                methods=r_node.details["methods"],
                function=r_node.details["function"],
                source=r_node.source_file,
                line=r_node.line,
                framework=r_node.details["framework"],
            ),
            test_files_data,
        )

        test_node_id = f"test_{r_node.id}"
        if route_cov == "test_assertion_candidate":
            nodes.append(
                ConnectionNode(
                    id=test_node_id,
                    layer="test",
                    name=f"Verified Test Coverage for {r_node.details['path']}",
                    source_file="tests",
                    line=1,
                    status="CONNECTED",
                    details={"coverage": "test_assertion_candidate"},
                )
            )
            edges.append(
                ConnectionEdge(
                    source_id=r_node.id,
                    target_id=test_node_id,
                    link_type="route_to_test",
                    status="CONNECTED",
                    description=f"Route has verifiable test assertion coverage",
                )
            )
        elif route_cov == "test_reference_candidate":
            nodes.append(
                ConnectionNode(
                    id=test_node_id,
                    layer="test",
                    name=f"Passive Test Reference for {r_node.details['path']} (No Assertion)",
                    source_file="tests",
                    line=1,
                    status="BROKEN",
                    details={"coverage": "test_reference_candidate"},
                )
            )
            edges.append(
                ConnectionEdge(
                    source_id=r_node.id,
                    target_id=test_node_id,
                    link_type="route_to_test",
                    status="BROKEN",
                    description=f"Route is invoked in tests but lacks response assertion",
                    contract_issues=["Passive test mention without verified response assertion"],
                )
            )
            contract_findings.append(
                ContractVerificationFinding(
                    severity="Medium",
                    category="passive_test_assertion",
                    feature_or_route=r_node.details.get("path", ""),
                    message=f"Test calls route '{r_node.details.get('path')}' without asserting response status or body",
                    failure_scenario="Regressions in route behavior will go undetected despite test execution.",
                    evidence=f"Route: {r_node.details.get('path')} referenced in test files without assertion statement",
                    recommended_fix="Add explicit assertions (e.g. assert response.status_code == 200).",
                )
            )
        else:
            # testing_gap_candidate
            nodes.append(
                ConnectionNode(
                    id=test_node_id,
                    layer="test",
                    name=f"MISSING: Test Coverage for {r_node.details['path']}",
                    source_file="",
                    line=0,
                    status="MISSING",
                    details={"coverage": "testing_gap_candidate"},
                )
            )
            edges.append(
                ConnectionEdge(
                    source_id=r_node.id,
                    target_id=test_node_id,
                    link_type="route_to_test",
                    status="MISSING",
                    description="No automated test covers this endpoint",
                    contract_issues=["Testing gap: route lacks unit or integration test coverage"],
                )
            )

    # --------------------------------------------------------------------------
    # 6. Orphan Detection (Routes with 0 callers, Uncalled Services)
    # --------------------------------------------------------------------------
    connected_target_ids = {e.target_id for e in edges}
    for r_node in route_nodes:
        if r_node.id not in connected_target_ids:
            r_node.status = "ORPHANED"
            r_node.details["orphan_reason"] = "No identified frontend UI action or client API call invokes this endpoint."

    # Compute Summary Statistics
    broken_edges = [e for e in edges if e.status == "BROKEN"]
    missing_edges = [e for e in edges if e.status == "MISSING"]
    orphaned_nodes = [n for n in nodes if n.status == "ORPHANED"]
    broken_nodes = [n for n in nodes if n.status == "BROKEN"]
    missing_nodes = [n for n in nodes if n.status == "MISSING"]

    return {
        "project_context": context,
        "target_feature": target_feature,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "broken_edges_count": len(broken_edges),
        "missing_edges_count": len(missing_edges),
        "orphaned_nodes_count": len(orphaned_nodes),
        "contract_findings_count": len(contract_findings),
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "contract_findings": [asdict(c) for c in contract_findings],
        "mermaid": render_mermaid_diagram(nodes, edges),
        "ascii_diagram": render_ascii_connection_map(nodes, edges),
    }


def render_mermaid_diagram(nodes: list[ConnectionNode] | list[dict[str, Any]], edges: list[ConnectionEdge] | list[dict[str, Any]]) -> str:
    """Render a Mermaid flowchart diagram visualizing the 8-layer feature connection graph."""
    lines = ["graph LR", "    %% Ghost Hunt 8-Layer Feature Connection Map"]

    # Convert dicts to dataclass if needed
    node_objs = [n if isinstance(n, ConnectionNode) else ConnectionNode(**n) for n in nodes]
    edge_objs = [e if isinstance(e, ConnectionEdge) else ConnectionEdge(**e) for e in edges]

    # 8 Layer Subgraphs
    layers = ["ui", "client_api", "route", "controller", "service", "database", "response", "test"]
    layer_titles = {
        "ui": "1. UI Action",
        "client_api": "2. Client API",
        "route": "3. Backend Route",
        "controller": "4. Controller / Handler",
        "service": "5. Business Service",
        "database": "6. Database / Model",
        "response": "7. Response / UI State",
        "test": "8. Tests & Verification",
    }

    for layer in layers:
        layer_nodes = [n for n in node_objs if n.layer == layer]
        if not layer_nodes:
            continue
        lines.append(f"    subgraph {layer.upper()} [\"{layer_titles.get(layer, layer)}\"]")
        for n in layer_nodes:
            safe_name = n.name.replace('"', "'").replace("[", "(").replace("]", ")")
            lines.append(f"        {n.id}[\"{safe_name}\"]")
        lines.append("    end")

    # Edges
    for e in edge_objs:
        if e.status == "CONNECTED":
            lines.append(f"    {e.source_id} -->|Connected| {e.target_id}")
        elif e.status == "BROKEN":
            issue_text = e.contract_issues[0] if e.contract_issues else "Mismatch"
            safe_issue = issue_text.replace('"', "'").replace("[", "(").replace("]", ")")
            lines.append(f"    {e.source_id} -.->|BROKEN: {safe_issue}| {e.target_id}")
        elif e.status == "MISSING":
            lines.append(f"    {e.source_id} -.->|MISSING LINK| {e.target_id}")

    # Styles
    for n in node_objs:
        if n.status == "BROKEN":
            lines.append(f"    style {n.id} fill:#ffdddd,stroke:#e74c3c,stroke-width:2px")
        elif n.status == "MISSING":
            lines.append(f"    style {n.id} fill:#ffeaa7,stroke:#d63031,stroke-width:2px,stroke-dasharray: 5 5")
        elif n.status == "ORPHANED":
            lines.append(f"    style {n.id} fill:#fff3cd,stroke:#f39c12,stroke-width:1px")
        elif n.status == "UNFINISHED":
            lines.append(f"    style {n.id} fill:#ffcccc,stroke:#c0392b,stroke-width:2px")
        else:
            lines.append(f"    style {n.id} fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px")

    return "\n".join(lines)


def render_ascii_connection_map(nodes: list[ConnectionNode] | list[dict[str, Any]], edges: list[ConnectionEdge] | list[dict[str, Any]]) -> str:
    """Render a text-based representation of the 8-layer connection pipeline."""
    node_objs = [n if isinstance(n, ConnectionNode) else ConnectionNode(**n) for n in nodes]
    edge_objs = [e if isinstance(e, ConnectionEdge) else ConnectionEdge(**e) for e in edges]

    lines = [
        "Feature Connection Pipeline:",
        "UI Action ===> Client API ===> Route Handler ===> Controller ===> Service ===> Database ===> Response ===> Tests",
        "-----------------------------------------------------------------------------------------------------------------",
    ]
    for e in edge_objs:
        s_node = next((n for n in node_objs if n.id == e.source_id), None)
        t_node = next((n for n in node_objs if n.id == e.target_id), None)
        if s_node and t_node:
            symbol = "-->" if e.status == "CONNECTED" else "-X-"
            status_tag = f"[{e.status}]" if e.status != "CONNECTED" else "[OK]"
            issue = f" ({e.contract_issues[0]})" if e.contract_issues else ""
            lines.append(f"  {status_tag} {s_node.name} {symbol} {t_node.name}{issue}")

    return "\n".join(lines)
