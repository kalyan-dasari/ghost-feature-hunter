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
    FeatureFlagDefinition,
    RouteDefinition,
    UIAction,
    UnfinishedItem,
)
from ghost_hunter.discovery.languages.python_adapter import normalize_route_path
from ghost_hunter.discovery.project import IGNORED_DIRECTORIES


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
    production_calls_made = set(scan_data.get("production_calls_made", []))
    test_calls_made = set(scan_data.get("test_calls_made", []))
    calls_made = set(scan_data.get("calls_made", []))

    ghost_candidates: list[dict[str, Any]] = []

    # Detect reverse-proxy or gateway configurations
    has_reverse_proxy = False
    for p in root.rglob("*"):
        if any(part in IGNORED_DIRECTORIES for part in p.parts):
            continue
        if p.is_file() and p.name.lower() in (
            "next.config.js", "next.config.mjs", "next.config.ts",
            "vite.config.js", "vite.config.ts", "nginx.conf", "default.conf",
        ):
            has_reverse_proxy = True
            break

    # Build known backend routes map
    registered_paths = {r.path for r in routes}
    routes_by_path: dict[str, list[RouteDefinition]] = {}
    for r in routes:
        routes_by_path.setdefault(normalize_route_path(r.path), []).append(r)

    # 1. Navigation items pointing to nonexistent pages or routes
    # Discover all known page paths (Next.js app/page, pages/, HTML files, and backend routes)
    known_destinations = set(registered_paths)
    for p in root.rglob("*"):
        if any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in p.parts):
            continue
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
                    "source_role": action.source_role,
                    "app_name": action.app_name,
                    "scope": action.scope,
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
                "source_role": action.source_role,
                "app_name": action.app_name,
                "scope": action.scope,
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
                "source_role": action.source_role,
                "app_name": action.app_name,
                "scope": action.scope,
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

        # External service calls are not missing local routes
        if endpoint.startswith(("http://", "https://", "//")) or any(
            domain in endpoint for domain in ("api.stripe.com", "auth0.com", "github.com", "googleapis.com", "paypal.com", "twilio.com")
        ):
            call.call_type = "external_service_call"
            continue

        matching_routes: list[RouteDefinition] = []
        for r_path, r_list in routes_by_path.items():
            if match_route(endpoint, r_path):
                matching_routes.extend(r_list)

        if not matching_routes:
            if has_reverse_proxy:
                call.call_type = "reverse_proxy_candidate"
                ghost_candidates.append({
                    "id": f"ghost-route-{len(ghost_candidates) + 1}",
                    "category": "reverse_proxy_candidate",
                    "chain_stage": "Client API Request -> Reverse Proxy Forwarding",
                    "severity": "Low",
                    "confidence": "Low",
                    "finding_state": "Requires Owner Confirmation",
                    "evidence": call.raw,
                    "source": call.source,
                    "line": call.line,
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
                    "present_links": [
                        f"Client requests '{req_method} {endpoint}' in {call.source}:{call.line}",
                        "Reverse proxy or gateway configuration exists in project",
                    ],
                    "missing_links": [
                        f"No local backend route registered for '{endpoint}'"
                    ],
                    "explanation": f"Client calls '{req_method} {endpoint}', which has no matching local route but may be proxied upstream by reverse proxy configuration.",
                    "potential_impact": "Request may succeed via proxy or fail if proxy rules are missing.",
                    "why_false_positive": "Endpoint is forwarded to an upstream service by reverse proxy.",
                    "recommended_action": "Verify upstream proxy destination.",
                })
            elif endpoint.startswith("/api") or endpoint.startswith("/v1") or endpoint.startswith("/v2"):
                ghost_candidates.append({
                    "id": f"ghost-route-{len(ghost_candidates) + 1}",
                    "category": "ghost_feature_candidate",
                    "chain_stage": "Client API Request -> Backend Route",
                    "severity": "High",
                    "confidence": "Medium",
                    "evidence": call.raw,
                    "source": call.source,
                    "line": call.line,
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
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
            local_matches = [r for r in matching_routes if r.app_name == call.app_name]
            cross_matches = [r for r in matching_routes if r.app_name != call.app_name]
            if not local_matches and cross_matches:
                call.call_type = "matching_service_route"
                call.target_service = cross_matches[0].app_name

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
                    "source_role": call.source_role,
                    "app_name": call.app_name,
                    "scope": call.scope,
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
                "source_role": r.source_role,
                "app_name": r.app_name,
                "scope": r.scope,
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
    # Tests must not silently mask uncalled production code
    for sym in symbols:
        if sym.symbol_type in ("function", "service") and not sym.name.startswith("_"):
            source_lower = sym.source.lower()
            if "service" in source_lower or "controller" in source_lower:
                effective_calls = production_calls_made
                if sym.name not in effective_calls:
                    in_tests = sym.name in test_calls_made
                    present_links = [
                        f"Service function '{sym.name}' implemented in {sym.source}:{sym.line}"
                    ]
                    if in_tests:
                        present_links.append(f"Referenced in test suite (not production wiring)")

                    ghost_candidates.append({
                        "id": f"ghost-orphaned-{len(ghost_candidates) + 1}",
                        "category": "ghost_feature_candidate",
                        "chain_stage": "Business Logic -> Application Entry Point",
                        "severity": "Low",
                        "confidence": "Medium",
                        "evidence": f"Function '{sym.name}' in {sym.source}:{sym.line}",
                        "source": sym.source,
                        "line": sym.line,
                        "source_role": sym.source_role,
                        "app_name": sym.app_name,
                        "scope": sym.scope,
                        "test_reference_found": in_tests,
                        "present_links": present_links,
                        "missing_links": [
                            "No route, CLI command, or background task invokes this service in production application code"
                        ],
                        "explanation": (
                            f"Service function '{sym.name}' exists and is referenced in tests, but has no identified callers in production application code."
                            if in_tests
                            else f"Service function '{sym.name}' exists but has no identified callers in the application."
                        ),
                        "potential_impact": "Dead code or unfinished integration of a backend feature.",
                        "why_false_positive": "May be called via dynamic string dispatch, reflection, or in unanalyzed tests.",
                        "recommended_action": "Connect the service to an entry point or verify if it is deprecated.",
                    })

    # 7. Feature Flag Analysis (Defined without consumers, or consumers without definitions)
    feature_flags: list[FeatureFlagDefinition] = scan_data.get("feature_flags", [])
    feature_flag_consumers: set[str] = set(scan_data.get("feature_flag_consumers", []))

    for flag in feature_flags:
        if flag.name not in feature_flag_consumers:
            ghost_candidates.append({
                "id": f"ghost-flag-{len(ghost_candidates) + 1}",
                "category": "ghost_feature_candidate",
                "chain_stage": "Feature Flag -> Conditional Consumer",
                "severity": "Low",
                "confidence": "Medium",
                "finding_state": "Requires Owner Confirmation",
                "evidence": flag.raw or f"{flag.name} defined in {flag.source}:{flag.line}",
                "source": flag.source,
                "line": flag.line,
                "source_role": flag.source_role,
                "app_name": flag.app_name,
                "scope": flag.scope,
                "flag_name": flag.name,
                "present_links": [
                    f"Feature flag '{flag.name}' defined in {flag.source}:{flag.line}"
                ],
                "missing_links": [
                    f"No conditional statements or feature consumers reference '{flag.name}' in the codebase"
                ],
                "explanation": f"Feature flag '{flag.name}' is defined in {flag.source}:{flag.line} but has no consumers.",
                "potential_impact": "Orphaned or dead feature flag configuration.",
                "why_false_positive": "Flag may be toggled externally via remote config, environment variables, or database flags.",
                "recommended_action": "Verify with feature owner whether this flag is deprecated, deferred, or dead code.",
            })

    defined_names = {f.name for f in feature_flags}
    for c_name in sorted(feature_flag_consumers):
        if c_name not in defined_names:
            ghost_candidates.append({
                "id": f"ghost-missing-flag-{len(ghost_candidates) + 1}",
                "category": "ghost_feature_candidate",
                "chain_stage": "Conditional Consumer -> Feature Flag Definition",
                "severity": "Medium",
                "confidence": "Medium",
                "finding_state": "Requires Owner Confirmation",
                "evidence": f"Conditional reference: {c_name}",
                "source": "codebase",
                "line": 0,
                "source_role": "application_source",
                "app_name": "primary",
                "scope": "primary_application",
                "flag_name": c_name,
                "present_links": [
                    f"Conditional logic branches on '{c_name}'"
                ],
                "missing_links": [
                    f"No static definition or default value found for '{c_name}' in the repository"
                ],
                "explanation": f"Feature flag '{c_name}' is consumed in conditional logic but has no static definition.",
                "potential_impact": "Flag may evaluate to false/undefined or fail at runtime if environment variable is missing.",
                "why_false_positive": "Flag may be injected dynamically via runtime environment variables or external configuration service.",
                "recommended_action": "Ensure a default value or schema definition is declared for this flag.",
            })

    return ghost_candidates

