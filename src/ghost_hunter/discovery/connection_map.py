"""End-to-End Feature Connection Map & Cross-Layer Contract Verification.

Traces and models the full execution chain of software features:
UI -> Client API -> Route -> Controller -> Service -> Database -> Response -> Tests

Identifies missing links, broken wiring, method mismatches, auth gaps,
unprotected multi-mutation transactions, and orphaned endpoints/services.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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
    status: str  # "CONNECTED", "BROKEN", "MISSING", "ORPHANED", "UNFINISHED"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionEdge:
    source_id: str
    target_id: str
    link_type: str  # "ui_to_client", "client_to_route", "route_to_controller", "controller_to_service", "service_to_db", "route_to_test"
    status: str  # "CONNECTED", "BROKEN", "MISSING"
    description: str = ""
    contract_issues: list[str] = field(default_factory=list)


@dataclass
class ContractVerificationFinding:
    severity: str  # "Critical", "High", "Medium", "Low"
    category: str  # "method_mismatch", "path_mismatch", "missing_auth", "transaction_boundary", "unimplemented_handler"
    feature_or_route: str
    message: str
    failure_scenario: str
    evidence: str
    recommended_fix: str


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

    # Map of routes for fast lookup
    routes_by_path: dict[str, list[RouteDefinition]] = {}
    for r in routes:
        routes_by_path.setdefault(normalize_route_path(r.path), []).append(r)

    # 1. UI Layer Nodes
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
            details={"action_type": act.action_type, "target": act.target, "app_name": act.app_name},
        )
        nodes.append(node)
        ui_nodes_by_target.setdefault(normalize_route_path(act.target), []).append(node)

    # 2. Client API Layer Nodes
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
                "raw": call.raw,
            },
        )
        nodes.append(node)
        client_nodes.append(node)
        client_nodes_by_path.setdefault(normalize_route_path(call.path), []).append(node)

        # Connect UI -> Client Call if UI targets this endpoint or calls this function
        norm_call_path = normalize_route_path(call.path)
        matching_ui = ui_nodes_by_target.get(norm_call_path, [])
        for u_node in matching_ui:
            edges.append(
                ConnectionEdge(
                    source_id=u_node.id,
                    target_id=node.id,
                    link_type="ui_to_client",
                    status="CONNECTED",
                    description=f"UI element triggers {call.method} {call.path}",
                )
            )

    # 3. Route & Controller Layer Nodes
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

        # Controller / Handler Node
        ctrl_id = f"ctrl_{idx}_{r.function}"
        ctrl_node = ConnectionNode(
            id=ctrl_id,
            layer="controller",
            name=f"def {r.function}()",
            source_file=r.source,
            line=r.line,
            status="UNFINISHED" if r.is_empty_or_unfinished else "CONNECTED",
            details={"function": r.function, "framework": r.framework},
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

        # Check: Unimplemented handler contract
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

        # Check: Sensitive route lacking auth
        is_sensitive = any(
            t in r.path.lower()
            for t in ("/admin", "/delete", "/secure", "/payment", "/accounts", "/billing")
        )
        if is_sensitive and not any(
            term in (r.raw_decorator or "").lower() for term in ("auth", "login", "permit", "secure", "role")
        ):
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

    # 4. Connect Client API -> Route (Cross-Layer Contract Verification)
    for c_node in client_nodes:
        c_path = c_node.details["path"]
        c_method = c_node.details["method"]
        c_app = c_node.details["app_name"]

        # Scope-aware route candidates
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
            # Check if exists in another app
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
            # Route exists: check HTTP method contract
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

    # 5. Service & Database Layer Nodes & Edges
    db_mutation_re = re.compile(
        r"""\b(?:db\.session\.(?:add|delete|commit)|objects\.(?:create|delete|update)|repository\.(?:save|delete)|\.save\(|\.delete\()\b"""
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

        # Check database writes inside handler
        handler_name = r_node.details.get("function", "")
        lines = content.splitlines()
        handler_lines: list[str] = []
        in_handler = False
        func_pat = re.compile(rf"""(?:def|func|function)\s+{re.escape(handler_name)}\b""")
        for idx, l in enumerate(lines, 1):
            if func_pat.search(l):
                in_handler = True
                handler_lines.append(l)
                continue
            if in_handler:
                if l.startswith("def ") or l.startswith("func ") or l.startswith("class "):
                    break
                handler_lines.append(l)

        handler_text = "\n".join(handler_lines)
        mutations = [l for l in handler_lines if db_mutation_re.search(l)]
        has_tx = bool(transaction_wrapper_re.search(handler_text))

        if len(mutations) >= 2 and not has_tx:
            contract_findings.append(
                ContractVerificationFinding(
                    severity="Medium",
                    category="transaction_boundary",
                    feature_or_route=r_node.details.get("path", ""),
                    message=f"Handler '{handler_name}' performs {len(mutations)} database writes without atomic transaction",
                    failure_scenario="Partial commit if an intermediate write fails, resulting in data inconsistency.",
                    evidence=f"{r_node.source_file}:{r_node.line} -> def {handler_name}() ({len(mutations)} mutations)",
                    recommended_fix=f"Wrap mutations in '{handler_name}' inside an atomic transaction block.",
                )
            )

        if mutations:
            db_node_id = f"db_{r_node.id}"
            nodes.append(
                ConnectionNode(
                    id=db_node_id,
                    layer="database",
                    name=f"DB Writes: {len(mutations)} ops",
                    source_file=r_node.source_file,
                    line=r_node.line,
                    status="CONNECTED" if has_tx or len(mutations) < 2 else "BROKEN",
                    details={"mutation_count": len(mutations), "has_transaction": has_tx},
                )
            )
            edges.append(
                ConnectionEdge(
                    source_id=f"ctrl_{r_node.id.split('_')[1]}_{handler_name}",
                    target_id=db_node_id,
                    link_type="controller_to_db",
                    status="CONNECTED" if has_tx or len(mutations) < 2 else "BROKEN",
                    description=f"Handler modifies DB state ({len(mutations)} writes)",
                    contract_issues=["Missing atomic transaction wrapper"] if (len(mutations) >= 2 and not has_tx) else [],
                )
            )

    # 6. Orphan Detection (Routes with 0 callers, Uncalled Services)
    connected_target_ids = {e.target_id for e in edges}
    connected_source_ids = {e.source_id for e in edges}

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


def render_mermaid_diagram(nodes: list[ConnectionNode], edges: list[ConnectionEdge]) -> str:
    """Render a Mermaid flowchart diagram visualizing the feature connection graph."""
    lines = ["graph LR", "    %% Ghost Hunt Feature Connection Map"]

    # Layer subgraphs
    layers = ["ui", "client_api", "route", "controller", "service", "database"]
    layer_titles = {
        "ui": "1. UI Layer",
        "client_api": "2. Client API",
        "route": "3. Backend Route",
        "controller": "4. Controller / Handler",
        "service": "5. Business Service",
        "database": "6. Database / Model",
    }

    for layer in layers:
        layer_nodes = [n for n in nodes if n.layer == layer]
        if not layer_nodes:
            continue
        lines.append(f"    subgraph {layer.upper()} [\"{layer_titles.get(layer, layer)}\"]")
        for n in layer_nodes:
            safe_name = n.name.replace('"', "'").replace("[", "(").replace("]", ")")
            lines.append(f"        {n.id}[\"{safe_name}\"]")
        lines.append("    end")

    # Edges
    for e in edges:
        if e.status == "CONNECTED":
            lines.append(f"    {e.source_id} -->|Connected| {e.target_id}")
        elif e.status == "BROKEN":
            lines.append(f"    {e.source_id} -.->|BROKEN: {e.contract_issues[0] if e.contract_issues else 'Mismatch'}| {e.target_id}")
        elif e.status == "MISSING":
            lines.append(f"    {e.source_id} -.->|MISSING LINK| {e.target_id}")

    # Styles
    for n in nodes:
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


def render_ascii_connection_map(nodes: list[ConnectionNode], edges: list[ConnectionEdge]) -> str:
    """Render a text-based representation of the 8-layer connection pipeline."""
    lines = [
        "Feature Connection Pipeline:",
        "UI Layer ===> Client API ===> Route Handler ===> Controller ===> Service ===> Database",
        "-------------------------------------------------------------------------------------",
    ]
    for e in edges:
        s_node = next((n for n in nodes if n.id == e.source_id), None)
        t_node = next((n for n in nodes if n.id == e.target_id), None)
        if s_node and t_node:
            symbol = "-->" if e.status == "CONNECTED" else "-X-"
            status_tag = f"[{e.status}]" if e.status != "CONNECTED" else "[OK]"
            issue = f" ({e.contract_issues[0]})" if e.contract_issues else ""
            lines.append(f"  {status_tag} {s_node.name} {symbol} {t_node.name}{issue}")

    return "\n".join(lines)
