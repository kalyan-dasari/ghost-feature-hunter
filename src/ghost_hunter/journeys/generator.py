"""Automated journey planning and generation from Feature Connection Map."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.connection_map import generate_feature_connection_map
from ghost_hunter.models import AdapterName, Journey, JourneyStep


def _sanitize_id(raw_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw_id).strip("-.")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"step-{cleaned}".strip("-.")
    return cleaned or "step-1"


def generate_feature_journey(
    project_root: Path,
    feature: str,
    base_url: str = "http://127.0.0.1:5000",
) -> Journey:
    """Generate an explicit Journey for a given feature using connection map analysis."""
    root = project_root.resolve()
    clean_feature = feature.strip()

    # Generate 8-layer connection map for the target feature
    cmap = generate_feature_connection_map(root, target_feature=clean_feature)
    nodes: list[dict[str, Any]] = cmap.get("nodes", [])
    edges: list[dict[str, Any]] = cmap.get("edges", [])

    steps: list[JourneyStep] = []
    used_ids: set[str] = set()

    def add_step(
        raw_id: str,
        checkpoint: str,
        adapter: AdapterName,
        expected_behavior: str,
        source_of_expectation: str,
        settings: dict[str, Any],
    ) -> None:
        base_id = _sanitize_id(raw_id)
        candidate_id = base_id
        counter = 1
        while candidate_id in used_ids:
            counter += 1
            candidate_id = f"{base_id}-{counter}"
        used_ids.add(candidate_id)
        steps.append(
            JourneyStep(
                id=candidate_id,
                checkpoint=checkpoint,
                adapter=adapter,
                expected_behavior=expected_behavior,
                source_of_expectation=source_of_expectation,
                settings=settings,
            )
        )

    # 1. Inspect Route & Response nodes to build HTTP steps
    route_nodes = [n for n in nodes if n.get("layer") == "route"]
    response_nodes = {n.get("id"): n for n in nodes if n.get("layer") == "response"}
    db_nodes = [n for n in nodes if n.get("layer") == "database"]
    ui_nodes = [n for n in nodes if n.get("layer") == "ui"]

    # Edges mapping
    # route -> controller -> response
    # route -> test
    route_to_resp: dict[str, list[dict[str, Any]]] = {}
    route_has_test: dict[str, bool] = {}
    for edge in edges:
        s_id = str(edge.get("source_id", ""))
        t_id = str(edge.get("target_id", ""))
        l_type = edge.get("link_type")
        if l_type == "route_to_test" and edge.get("status") == "CONNECTED":
            route_has_test[s_id] = True
        elif l_type == "controller_to_response" and t_id in response_nodes:
            # find route that points to this controller
            for r_edge in edges:
                if r_edge.get("link_type") == "route_to_controller" and r_edge.get("target_id") == s_id:
                    route_to_resp.setdefault(str(r_edge.get("source_id", "")), []).append(response_nodes[t_id])

    for r_node in route_nodes:
        r_details = r_node.get("details", {})
        path = str(r_details.get("path", ""))
        methods = r_details.get("methods", ["GET"])
        resps = route_to_resp.get(str(r_node.get("id", "")), [])

        expected_status = 200
        resp_format = "JSON"
        if resps:
            r_info = resps[0].get("details", {})
            expected_status = r_info.get("status_code", 200)
            resp_format = r_info.get("format", "JSON")
        elif "POST" in methods:
            expected_status = 201

        has_test = route_has_test.get(str(r_node.get("id", "")), False)
        source_expectation = "existing_test" if has_test else ("api_contract" if resps else "inferred_assumption")

        for m in methods:
            method_upper = str(m).upper()
            step_id = f"http-{method_upper.lower()}-{path.strip('/').replace('/', '-') or 'root'}"
            checkpoint = f"{method_upper} {path} returns HTTP {expected_status}"
            expected_behavior = (
                f"{method_upper} request to {path} is handled and returns status {expected_status} ({resp_format})"
            )
            settings: dict[str, Any] = {
                "method": method_upper,
                "url": path,
                "checks": {"status_code": expected_status},
            }
            if method_upper in ("POST", "PUT", "PATCH"):
                settings["json"] = {}

            add_step(
                raw_id=step_id,
                checkpoint=checkpoint,
                adapter=AdapterName.HTTP,
                expected_behavior=expected_behavior,
                source_of_expectation=source_expectation,
                settings=settings,
            )

    # 2. Database verification steps for any linked models/tables
    for d_node in db_nodes:
        model_name = str(d_node.get("name", "Record"))
        table_match = re.search(r"Model:\s*(\w+)", model_name)
        raw_name = table_match.group(1) if table_match else model_name.replace(" ", "_")
        table_name = raw_name.lower()
        if not table_name.endswith("s"):
            table_name = f"{table_name}s"

        step_id = f"db-{raw_name.lower()}-persistence"
        checkpoint = f"Storage persistence for {raw_name}"
        expected_behavior = f"Database stores {raw_name} records created during journey"
        settings = {
            "query": f"SELECT count(*) AS count FROM {table_name}",
            "checks": {"first_row_non_empty": True},
        }
        add_step(
            raw_id=step_id,
            checkpoint=checkpoint,
            adapter=AdapterName.DATABASE,
            expected_behavior=expected_behavior,
            source_of_expectation="inferred_assumption",
            settings=settings,
        )

    # 3. UI interaction steps if UI nodes are present
    for u_node in ui_nodes:
        action_name = str(u_node.get("name", "UI Element"))
        step_id = f"ui-{action_name.lower()}"
        checkpoint = f"UI interaction for {action_name}"
        expected_behavior = f"Interacting with {action_name} triggers associated client call"
        settings = {"action": "click", "element": action_name}
        add_step(
            raw_id=step_id,
            checkpoint=checkpoint,
            adapter=AdapterName.BROWSER,
            expected_behavior=expected_behavior,
            source_of_expectation="inferred_assumption",
            settings=settings,
        )

    # 4. Fallback if no steps were generated
    if not steps:
        norm_path = f"/{clean_feature.strip('/')}"
        add_step(
            raw_id=f"http-get-{clean_feature.strip('/').replace('/', '-') or 'feature'}",
            checkpoint=f"Endpoint {norm_path} is reachable",
            adapter=AdapterName.HTTP,
            expected_behavior=f"GET {norm_path} returns HTTP 200",
            source_of_expectation="inferred_assumption",
            settings={"method": "GET", "url": norm_path, "checks": {"status_code": 200}},
        )

    return Journey(
        schema_version="1.0",
        feature=clean_feature,
        description=f"Generated verification journey for {clean_feature} feature.",
        steps=steps[:100],
    )
