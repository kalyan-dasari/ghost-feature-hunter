"""Unit and integration tests for multi-language intelligence, ghost features,
empty implementations, structural duplicates, and language capability matrix.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from ghost_hunter.discovery.audit import (
    audit_repository,
    estimate_duplicate_blocks,
)
from ghost_hunter.discovery.languages.python_adapter import PythonAdapter
from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
from ghost_hunter.discovery.languages.registry import LanguageRegistry


# 1. Python Flask Project
def test_python_flask_project_discovery(tmp_path: Path):
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """
from flask import Flask, jsonify, request
app = Flask(__name__)

@app.route("/api/items", methods=["GET", "POST"])
def items():
    return jsonify({"status": "ok"})
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    fws = {f["framework"] for f in result["frameworks"]}
    assert "Flask" in fws
    assert result["total_routes"] == 1
    # Check capability matrix
    caps = [c for c in result["capability_matrix"] if "Flask" in c["language_framework"]]
    assert len(caps) >= 1
    assert caps[0]["status"] == "supported"


# 2. Python FastAPI Project
def test_python_fastapi_project_discovery(tmp_path: Path):
    main_py = tmp_path / "main.py"
    main_py.write_text(
        """
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}

@app.post("/api/users")
async def create_user():
    return {"created": True}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    fws = {f["framework"] for f in result["frameworks"]}
    assert "FastAPI" in fws
    assert result["total_routes"] == 2
    caps = [c for c in result["capability_matrix"] if "FastAPI" in c["language_framework"]]
    assert len(caps) >= 1
    assert caps[0]["status"] == "supported"


# 3. JavaScript Express Project
def test_javascript_express_project_discovery(tmp_path: Path):
    server_js = tmp_path / "server.js"
    server_js.write_text(
        """
const express = require('express');
const app = express();

app.get('/api/v1/orders', (req, res) => {
    res.json({ orders: [] });
});

app.post('/api/v1/orders', (req, res) => {
    res.status(201).json({ created: true });
});
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    fws = {f["framework"] for f in result["frameworks"]}
    assert "Express" in fws
    assert result["total_routes"] == 2
    caps = [c for c in result["capability_matrix"] if "Express" in c["language_framework"]]
    assert len(caps) >= 1
    assert caps[0]["status"] == "supported"


# 4. TypeScript Next.js and React Project
def test_typescript_nextjs_and_react_project_discovery(tmp_path: Path):
    api_dir = tmp_path / "src" / "app" / "api" / "products"
    api_dir.mkdir(parents=True)
    route_ts = api_dir / "route.ts"
    route_ts.write_text(
        """
export async function GET() {
    return Response.json({ products: [] });
}
export async function POST() {
    return Response.json({ success: true });
}
""",
        encoding="utf-8",
    )

    pkg = tmp_path / "package.json"
    pkg.write_text('{"name": "my-next-app", "dependencies": {"next": "^14.0.0", "react": "^18.0.0"}}', encoding="utf-8")

    result = audit_repository(tmp_path)
    fws = {f["framework"] for f in result["frameworks"]}
    assert "Next.js" in fws
    assert result["total_routes"] == 2


# 5. Page and button with no meaningful handler
def test_page_with_button_no_meaningful_handler(tmp_path: Path):
    comp_tsx = tmp_path / "ButtonView.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function ButtonView() {
    return (
        <div>
            <h2>Dashboard</h2>
            <button onClick={() => {}}>Export CSV Report</button>
        </div>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Action -> Event Handler"]
    assert len(ghosts) >= 1
    assert "Export CSV Report" in ghosts[0]["present_links"][0]
    assert ghosts[0]["confidence"] == "High"

    # Also appears in empty/unfinished
    unf = [u for u in result["empty_or_unfinished"] if u["item_type"] == "empty_handler"]
    assert len(unf) >= 1


# 6. Placeholder or unfinished backend handler
def test_placeholder_or_unfinished_backend_handler(tmp_path: Path):
    api_py = tmp_path / "api.py"
    api_py.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.get("/api/reports/quarterly")
def quarterly_report():
    pass
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    # Check ghost features: Route -> Service Logic
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "Backend Route -> Service Logic"]
    assert len(ghosts) >= 1
    assert "/api/reports/quarterly" in ghosts[0]["present_links"][0]

    # Check empty_or_unfinished
    unf = [u for u in result["empty_or_unfinished"] if "quarterly_report" in u["name"]]
    assert len(unf) >= 1
    assert unf[0]["item_type"] == "empty_function"


# 7. Navigation item pointing to a missing page
def test_navigation_item_pointing_to_missing_page(tmp_path: Path):
    nav_tsx = tmp_path / "Nav.tsx"
    nav_tsx.write_text(
        """
import React from 'react';

export function Navigation() {
    return (
        <nav>
            <a href="/settings/billing">Billing Settings</a>
        </nav>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Navigation -> Destination Page"]
    assert len(ghosts) >= 1
    assert "/settings/billing" in ghosts[0]["present_links"][0]
    assert "No route handler or page file matching" in ghosts[0]["missing_links"][0]


# 8. UI API request with no matching backend route
def test_ui_api_request_with_no_matching_backend_route(tmp_path: Path):
    client_js = tmp_path / "client.js"
    client_js.write_text(
        """
async function submitFeedback(data) {
    const res = await fetch('/api/v1/feedback', { method: 'POST', body: JSON.stringify(data) });
    return res.json();
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    # Appears in missing route candidates
    missing = result["missing_route_candidates"]
    assert len(missing) >= 1
    assert missing[0]["endpoint"] == "/api/v1/feedback"
    assert missing[0]["method"] == "POST"

    # Appears in ghost features
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "Client API Request -> Backend Route"]
    assert len(ghosts) >= 1
    assert "/api/v1/feedback" in ghosts[0]["explanation"]


# 9. API method/path mismatch
def test_api_method_path_mismatch(tmp_path: Path):
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.route("/api/orders", methods=["GET"])
def get_orders():
    return {"orders": []}
""",
        encoding="utf-8",
    )
    client_js = tmp_path / "client.js"
    client_js.write_text(
        """
fetch('/api/orders', { method: 'POST' });
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    mismatches = result["method_mismatches"]
    assert len(mismatches) >= 1
    assert mismatches[0]["client_method"] == "POST"
    assert mismatches[0]["allowed_methods"] == ["GET"]

    ghosts = [g for g in result["ghost_features"] if "Method Compatibility" in g["chain_stage"]]
    assert len(ghosts) >= 1
    assert "POST" in ghosts[0]["explanation"]


# 10. Service that exists but has no detected caller
def test_orphaned_service_with_no_detected_caller(tmp_path: Path):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    svc_py = services_dir / "payment_service.py"
    svc_py.write_text(
        """
def process_manual_reversal(transaction_id, amount_cents):
    # complex reversal business logic
    fee = amount_cents * 0.02
    return {"reversed": True, "fee": fee}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "Business Logic -> Application Entry Point"]
    assert len(ghosts) >= 1
    assert "process_manual_reversal" in ghosts[0]["evidence"]


# 11. Endpoint with no local caller includes external webhook caveat
def test_endpoint_with_no_local_caller_includes_external_caveat(tmp_path: Path):
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.post("/api/stripe/webhook")
def stripe_webhook():
    return {"received": True}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    unused = result["potentially_unused_endpoints"]
    assert len(unused) >= 1
    assert unused[0]["endpoint"] == "/api/stripe/webhook"
    assert "webhook" in unused[0]["why_false_positive"].lower()
    assert unused[0]["finding_state"] == "Requires Owner Confirmation"


# 12. Exported symbol with no local references
def test_exported_symbol_with_no_local_references(tmp_path: Path):
    dep_file = tmp_path / "requirements.txt"
    dep_file.write_text("redis>=5.0.0\ncelery>=5.3.0\n", encoding="utf-8")
    app_py = tmp_path / "app.py"
    app_py.write_text("import os\nprint('hello')\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    dep_audit = result["dependency_hygiene"]
    assert dep_audit["total_declared"] >= 2
    unused_deps = dep_audit["potentially_unused"]
    assert len(unused_deps) >= 2
    assert unused_deps[0]["finding_state"] == "Requires Owner Confirmation"
    assert "CLI tool" in unused_deps[0]["why_false_positive"]


# 13. Dynamically registered route caveat
def test_dynamically_registered_route_caveat(tmp_path: Path):
    result = audit_repository(tmp_path)
    limits = " ".join(result["limitations"]).lower()
    assert "dynamic" in limits
    assert "proxy" in limits or "reflection" in limits


# 14. Two functions with the same name but different bodies (NOT duplicate)
def test_same_function_name_different_bodies_not_reported_as_duplicate(tmp_path: Path):
    file1 = tmp_path / "math_a.py"
    file1.write_text(
        """
def compute_total(a, b):
    subtotal = a + b
    tax = subtotal * 0.10
    return subtotal + tax
""",
        encoding="utf-8",
    )
    file2 = tmp_path / "math_b.py"
    file2.write_text(
        """
def compute_total(a, b):
    import json
    payload = {"items": [a, b]}
    serialized = json.dumps(payload)
    return len(serialized)
""",
        encoding="utf-8",
    )
    dups = estimate_duplicate_blocks([file1, file2])
    # Different implementations must NOT be reported as duplicates just because the name is compute_total
    assert len(dups) == 0


# 15. Two functions with different names but identical bodies (ARE duplicate)
def test_different_function_names_identical_bodies_detected_as_duplicate(tmp_path: Path):
    file1 = tmp_path / "tax_us.py"
    file1.write_text(
        """
def calculate_us_tax(subtotal_cents, rate_basis):
    adjusted = subtotal_cents * 1.05
    tax_cents = int(adjusted * rate_basis)
    final_amount = adjusted + tax_cents
    return final_amount
""",
        encoding="utf-8",
    )
    file2 = tmp_path / "tax_eu.py"
    file2.write_text(
        """
def compute_vat_total(subtotal_cents, rate_basis):
    adjusted = subtotal_cents * 1.05
    tax_cents = int(adjusted * rate_basis)
    final_amount = adjusted + tax_cents
    return final_amount
""",
        encoding="utf-8",
    )
    dups = estimate_duplicate_blocks([file1, file2])
    assert len(dups) >= 1
    assert dups[0]["duplicate_type"] == "exact_structural_duplication"
    assert dups[0]["estimated_waste_lines"] >= 4


# 16. Intentionally empty abstract method not classified as defect
def test_intentionally_empty_abstract_method_not_classified_as_defect(tmp_path: Path):
    model_py = tmp_path / "base_adapter.py"
    model_py.write_text(
        """
from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    @abstractmethod
    def process_record(self, record_id: str) -> bool:
        pass

    @abstractmethod
    def validate_schema(self, data: dict) -> bool:
        ...
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    # Abstract methods must NOT appear as defect candidates in empty_or_unfinished
    defects = [u for u in result["empty_or_unfinished"] if "process_record" in u["name"] or "validate_schema" in u["name"]]
    assert len(defects) == 0


# 17. Mixed-language monorepo with separate application roots
def test_mixed_language_monorepo_separate_application_roots(tmp_path: Path):
    backend = tmp_path / "apps" / "backend"
    backend.mkdir(parents=True)
    (backend / "main.py").write_text(
        """
from fastapi import FastAPI
app = FastAPI()
@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
""",
        encoding="utf-8",
    )

    frontend = tmp_path / "apps" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text('{"dependencies": {"react": "^18.0.0", "next": "^14.0.0"}}', encoding="utf-8")
    (frontend / "page.tsx").write_text(
        """
import React from 'react';
export default function Page() {
    return <h1>Welcome</h1>;
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    langs = result["detected_languages"]
    assert "Python" in langs
    assert "JavaScript/TypeScript" in langs
    fws = {f["framework"] for f in result["frameworks"]}
    assert "FastAPI" in fws
    assert "Next.js" in fws or "React" in fws


# 18. Unsupported language reported as partial coverage
def test_unsupported_language_reported_as_partial_coverage(tmp_path: Path):
    go_main = tmp_path / "main.go"
    go_main.write_text("package main\nimport \"fmt\"\nfunc main() { fmt.Println(\"Hello\") }", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/mygoapp\ngo 1.22\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    assert "Go" in result["detected_languages"]
    caps = [c for c in result["capability_matrix"] if c["language_framework"] == "Go"]
    assert len(caps) >= 1
    assert caps[0]["status"] == "partial"
    assert "file inventory" in caps[0]["analysis_capability"].lower()
    assert "not implemented" in caps[0]["limitations"].lower()
