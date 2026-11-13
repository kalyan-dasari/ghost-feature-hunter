"""Ghost Feature Detection & Cross-Boundary Connection Graph.

Discovers features that appear to exist in one layer (navigation, UI, client calls, routes)
but have a missing, incomplete, or disconnected implementation path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.models import (
    ClientCall,
    ComponentDefinition,
    RouteDefinition,
    UIAction,
    UnfinishedItem,
)
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path


def match_route(endpoint: str, route_path: str) -> bool:
    """Check if a client endpoint matches a registered route path, accounting for parameters."""
    norm_ep = normalize_route_path(endpoint)
    norm_rp = normalize_route_path(route_path)

    if norm_ep == norm_rp:
        return True

    # Parameterized match: convert {param} to regex [^/]+
    regex_pattern = "^" + re.sub(r"\{[a-zA-Z0-9_]+\}", r"[^/]+", norm_rp) + "$"
    if re.match(regex_pattern, norm_ep):
        return True

    return False


def detect_ghost_features(
    project_root: Path,
    scan_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Construct a connection graph and surface disconnected or ghost feature chains."""
    root = project_root.resolve()
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    client_calls: list[ClientCall] = scan_data.get("client_calls", [])
    ui_actions: list[UIAction] = scan_data.get("ui_actions", [])
    unfinished: list[UnfinishedItem] = scan_data.get("unfinished", [])
    symbols = scan_data.get("symbols", [])
    calls_made = set(scan_data.get("calls_made", []))

    ghost_candidates: list[dict[str, Any]] = []

    # Build known backend routes map
    registered_paths = {r.path for r in routes}
    routes_by_path: dict[str, list[RouteDefinition]] = {}
    for r in routes:
        routes_by_path.setdefault(normalize_route_path(r.path), []).append(r)

    # 1. Navigation items pointing to nonexistent pages or routes
    # Discover all known page paths (Next.js app/page, pages/, HTML files, and backend routes)
    known_destinations = set(registered_paths)
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if "pages/" in rel or "app/" in rel:
                stem = p.stem
                if stem in ("page", "index") or p.suffix in (".html", ".htm"):
                    # Extract URL path from directory
                    parts = p.relative_to(root).parts
                    if "pages" in parts:
                        idx = parts.index("pages")
                        sub = parts[idx + 1:]
                        if sub:
                            dest = "/" + "/".join(sub[:-1] + (p.stem,)) if p.stem != "index" else "/" + "/".join(sub[:-1])
                            known_destinations.add(normalize_route_path(dest or "/"))
                    elif "app" in parts and stem == "page":
                        idx = parts.index("app")
                        sub = parts[idx + 1:-1]
                        dest = "/" + "/".join(sub)
                        known_destinations.add(normalize_route_path(dest or "/"))

    for action in ui_actions:
        if action.action_type == "link":
            target = action.target
            # Check if target matches any known route or page
            matched = any(match_route(target, kd) for kd in known_destinations)
            if not matched and not target.startswith(("#", "http://", "https://", "mailto:", "tel:")):
                ghost_candidates.append({
                    "id": f"ghost-nav-{len(ghost_candidates) + 1}",
                    "category": "ghost_feature_candidate",
                    "chain_stage": "UI Navigation -> Destination Page",
                    "severity": "Medium",
                    "confidence": "High",
                    "evidence": action.raw,
                    "source": action.source,
                    "line": action.line,
                    "present_links": [
                        f"UI navigation link '{action.label}' targeting '{target}' in {action.source}:{action.line}"
                    ],
                    "missing_links": [
                        f"No route handler or page file matching '{target}' exists in the repository"
                    ],
                    "explanation": f"Navigation link '{action.label}' points to '{target}', but no corresponding backend route or frontend page exists.",
                    "potential_impact": "Users clicking this navigation link will encounter an HTTP 404 or broken page.",
                    "why_false_positive": "The destination page may be served by an external application, reverse proxy, or dynamic route loader.",
                    "recommended_action": "Create the missing page/route or remove the orphaned navigation item.",
                })

    # 2. UI Buttons with empty or missing handlers
    for action in ui_actions:
        if action.action_type == "button" and (action.is_empty_handler or not action.has_handler):
            ghost_candidates.append({
                "id": f"ghost-btn-{len(ghost_candidates) + 1}",
                "category": "ghost_feature_candidate",
                "chain_stage": "UI Action -> Event Handler",
                "severity": "Medium",
                "confidence": "High",
                "evidence": action.raw,
                "source": action.source,
                "line": action.line,
                "present_links": [
                    f"UI action button '{action.label}' rendered in {action.source}:{action.line}"
                ],
                "missing_links": [
                    "Event handler is empty or unattached (onClick={() => {}} or missing handler)"
                ],
                "explanation": f"Button '{action.label}' is visible in the interface but has no functional handler.",
                "potential_impact": "Users clicking this button will experience no response, giving the appearance of a broken feature.",
                "why_false_positive": "May be a visual mockup awaiting backend integration or a button controlled via parent event delegation.",
                "recommended_action": "Attach a functional event handler or disable the button until implemented.",
            })

    # 3. Forms accepting input without submission handling
    for action in ui_actions:
        if action.action_type == "form" and action.is_empty_handler:
            ghost_candidates.append({
                "id": f"ghost-form-{len(ghost_candidates) + 1}",
                "category": "ghost_feature_candidate",
                "chain_stage": "UI Form -> Submission Pipeline",
                "severity": "High",
                "confidence": "Medium",
                "evidence": action.raw,
                "source": action.source,
                "line": action.line,
                "present_links": [
                    f"Form inputs rendered in {action.source}:{action.line}"
                ],
                "missing_links": [
                    "Form element lacks both 'action' attribute and 'onSubmit' handler"
                ],
                "explanation": "Form collects user input but provides no identifiable submission or processing pipeline.",
                "potential_impact": "Submitted user input is lost without processing or error feedback.",
                "why_false_positive": "Form submission might be wired externally via jQuery or custom document-level listeners.",
                "recommended_action": "Add an explicit onSubmit handler or form action attribute.",
            })

    # 4. Client API calls vs Backend routes (Missing routes & Method mismatches)
    for call in client_calls:
        endpoint = call.path
        req_method = call.method.upper()

        matching_routes: list[RouteDefinition] = []
        for r_path, r_list in routes_by_path.items():
            if match_route(endpoint, r_path):
                matching_routes.extend(r_list)

        if not matching_routes:
            if endpoint.startswith("/api") or endpoint.startswith("/v1") or endpoint.startswith("/v2"):
                ghost_candidates.append({
                    "id": f"ghost-route-{len(ghost_candidates) + 1}",
                    "category": "ghost_feature_candidate",
                    "chain_stage": "Client API Request -> Backend Route",
                    "severity": "High",
                    "confidence": "Medium",
                    "evidence": call.raw,
                    "source": call.source,
                    "line": call.line,
                    "present_links": [
                        f"Client requests '{req_method} {endpoint}' in {call.source}:{call.line}"
                    ],
                    "missing_links": [
                        f"No backend route registered for '{endpoint}'"
                    ],
                    "explanation": f"Client calls '{req_method} {endpoint}', but no backend route handler exists for this path.",
                    "potential_impact": "Runtime request will fail with HTTP 404.",
                    "why_false_positive": "Endpoint may be served by an external microservice or dynamic proxy.",
                    "recommended_action": "Verify if the route is hosted in another service or implement the missing endpoint.",
                })
        else:
            # Check method mismatch
            supported_methods = set()
            for r in matching_routes:
                for m in r.methods:
                    supported_methods.add(m.upper())

            if "ALL" not in supported_methods and req_method not in supported_methods:
                matched_route = matching_routes[0]
                ghost_candidates.append({
                    "id": f"ghost-mismatch-{len(ghost_candidates) + 1}",
                    "category": "ghost_feature_candidate",
                    "chain_stage": "Client Request -> Route Method Compatibility",
                    "severity": "High",
                    "confidence": "High",
                    "evidence": f"Client calls: {call.raw} | Backend route: {matched_route.raw_decorator or matched_route.path}",
                    "source": call.source,
                    "line": call.line,
                    "present_links": [
                        f"Client calls {req_method} '{endpoint}' in {call.source}:{call.line}",
                        f"Backend route '{matched_route.path}' handles {sorted(supported_methods)} in {matched_route.source}:{matched_route.line}",
                    ],
                    "missing_links": [
                        f"Backend route does not accept HTTP method '{req_method}'"
                    ],
                    "explanation": f"Client calls {req_method} '{endpoint}', but the matching route only supports {sorted(supported_methods)}.",
                    "potential_impact": "Request will fail with HTTP 405 Method Not Allowed.",
                    "why_false_positive": "A reverse proxy or middleware may rewrite the HTTP method.",
                    "recommended_action": f"Add '{req_method}' to the route's allowed methods list or update client call.",
                })

    # 5. Backend Routes with Empty or Unimplemented Handlers
    for r in routes:
        if r.is_empty_or_unfinished:
            ghost_candidates.append({
                "id": f"ghost-empty-route-{len(ghost_candidates) + 1}",
                "category": "ghost_feature_candidate",
                "chain_stage": "Backend Route -> Service Logic",
                "severity": "High",
                "confidence": "High",
                "evidence": f"Route '{r.path}' -> def {r.function}(...)",
                "source": r.source,
                "line": r.line,
                "present_links": [
                    f"Route '{r.path}' registered in {r.source}:{r.line}"
                ],
                "missing_links": [
                    "Handler body contains only pass, NotImplementedError, or placeholder return"
                ],
                "explanation": f"Route '{r.path}' is registered in {r.source}, but its handler function '{r.function}' has an unfinished/placeholder body.",
                "potential_impact": "Invoking this endpoint returns empty data or raises an unhandled error.",
                "why_false_positive": "May be a planned endpoint stub or scaffolded API route.",
                "recommended_action": "Complete the implementation of the route handler.",
            })

    # 6. Orphaned Business Services (Functions in service files with zero callers)
    for sym in symbols:
        if sym.symbol_type in ("function", "service") and not sym.name.startswith("_"):
            source_lower = sym.source.lower()
            if "service" in source_lower or "controller" in source_lower:
                if sym.name not in calls_made:
                    ghost_candidates.append({
                        "id": f"ghost-orphaned-{len(ghost_candidates) + 1}",
                        "category": "ghost_feature_candidate",
                        "chain_stage": "Business Logic -> Application Entry Point",
                        "severity": "Low",
                        "confidence": "Medium",
                        "evidence": f"Function '{sym.name}' in {sym.source}:{sym.line}",
                        "source": sym.source,
                        "line": sym.line,
                        "present_links": [
                            f"Service function '{sym.name}' implemented in {sym.source}:{sym.line}"
                        ],
                        "missing_links": [
                            "No route, CLI command, or background task invokes this service"
                        ],
                        "explanation": f"Service function '{sym.name}' exists but has no identified callers in the application.",
                        "potential_impact": "Dead code or unfinished integration of a backend feature.",
                        "why_false_positive": "May be called via dynamic string dispatch, reflection, or in unanalyzed tests.",
                        "recommended_action": "Connect the service to an entry point or verify if it is deprecated.",
                    })

    return ghost_candidates
