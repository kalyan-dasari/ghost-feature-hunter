"""Unit and integration tests for multi-language intelligence, ghost features,
empty implementations, structural duplicates, and language capability matrix.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from ghost_hunter.cli import app
from ghost_hunter.discovery.audit import (
    audit_repository,
    estimate_duplicate_blocks,
)
from ghost_hunter.discovery.languages.python_adapter import PythonAdapter
from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
from ghost_hunter.discovery.languages.registry import LanguageRegistry


# -----------------------------------------------------------------------------
# Section 12 Required Tests: 20 Specific Regression Tests
# -----------------------------------------------------------------------------

# 1. Pure Python repo does not detect JavaScript/TypeScript or Node.js
def test_pure_python_repo_does_not_detect_javascript(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pure-py"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "main.py").write_text("def run():\n    print('pure python')\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    assert "Python" in result["detected_languages"]
    assert "JavaScript/TypeScript" not in result["detected_languages"]
    fw_names = {f["framework"] for f in result["frameworks"]}
    assert "Express" not in fw_names
    assert "Next.js" not in fw_names
    assert "React" not in fw_names
    assert "Standard / Node.js" not in fw_names


# 2. Pure JavaScript repo does not detect Python or Flask/FastAPI/Django
def test_pure_javascript_repo_does_not_detect_python(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "pure-js", "dependencies": {"express": "^4.18.0"}}', encoding="utf-8")
    (tmp_path / "server.js").write_text("const express = require('express');\nconst app = express();\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    assert "JavaScript/TypeScript" in result["detected_languages"]
    assert "Python" not in result["detected_languages"]
    fw_names = {f["framework"] for f in result["frameworks"]}
    assert "Flask" not in fw_names
    assert "FastAPI" not in fw_names
    assert "Django" not in fw_names
    assert "Standard / Generic" not in fw_names


# 3. Monorepo detects both Python and JavaScript
def test_monorepo_detects_both_python_and_javascript(tmp_path: Path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text('[project]\nname = "backend"\n', encoding="utf-8")
    (backend / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "frontend", "dependencies": {"react": "^18.0.0"}}', encoding="utf-8")
    (frontend / "index.jsx").write_text("import React from 'react';\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    langs = result["detected_languages"]
    assert "Python" in langs
    assert "JavaScript/TypeScript" in langs
    fws = {f["framework"] for f in result["frameworks"]}
    assert "Flask" in fws
    assert "React" in fws


# 4. Django urlpatterns extraction: path() and re_path()
def test_django_urlpatterns_extraction_path_and_re_path(tmp_path: Path):
    urls_py = tmp_path / "urls.py"
    urls_py.write_text(
        """
from django.urls import path, re_path
from . import views

urlpatterns = [
    path("api/v1/users/", views.user_list, name="user-list"),
    re_path(r"^api/v1/items/(?P<item_id>[0-9]+)/$", views.item_detail, name="item-detail"),
]
""",
        encoding="utf-8",
    )
    adapter = PythonAdapter()
    analysis = adapter.analyze_file(urls_py, tmp_path)
    routes = analysis["routes"]
    assert len(routes) == 2
    paths = {r.path for r in routes}
    assert "/api/v1/users" in paths
    assert "/api/v1/items/{item_id}" in paths
    assert all(r.framework == "Django" for r in routes)


# 5. Django urlpatterns extraction: include() and view references
def test_django_urlpatterns_include_and_view_references(tmp_path: Path):
    urls_py = tmp_path / "urls.py"
    urls_py.write_text(
        """
from django.urls import path, include
from .views import DashboardView

urlpatterns = [
    path("api/v1/auth/", include("auth.urls")),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
""",
        encoding="utf-8",
    )
    adapter = PythonAdapter()
    analysis = adapter.analyze_file(urls_py, tmp_path)
    routes = analysis["routes"]
    assert len(routes) == 2
    funcs = {r.function for r in routes}
    assert any("include(" in f for f in funcs)
    assert any("DashboardView.as_view" in f for f in funcs)


# 6. Django capability status is 'partial' with explicit limitations
def test_django_capability_status_is_partial_with_limitations(tmp_path: Path):
    app_py = tmp_path / "urls.py"
    app_py.write_text("import django\nfrom django.urls import path\nurlpatterns = []\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    django_caps = [c for c in result["capability_matrix"] if "Django" in c["language_framework"]]
    assert len(django_caps) >= 1
    cap = django_caps[0]
    assert cap["status"] == "partial"
    assert "urlpatterns" in cap["analysis_capability"].lower()
    assert "reverse" in cap["limitations"].lower() or "dispatch" in cap["limitations"].lower()


# 7. Multiline JSX button with named handler (onClick={handleClick}) is not flagged
def test_multiline_jsx_button_with_named_handler_not_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "Checkout.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function Checkout({ onProcess }) {
    const handleCheckout = () => { onProcess(); };
    return (
        <div>
            <button
                onClick={handleCheckout}
                className="btn btn-primary"
            >
                Complete Purchase
            </button>
        </div>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    # Must NOT appear as an empty handler defect
    empty_handlers = [u for u in result["empty_or_unfinished"] if u["item_type"] == "empty_handler"]
    assert len(empty_handlers) == 0
    ghost_buttons = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Action -> Event Handler"]
    assert len(ghost_buttons) == 0


# 8. Multiline JSX button with type="submit" is not flagged
def test_multiline_jsx_button_type_submit_not_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "SubmitButton.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function SubmitButton() {
    return (
        <button
            type="submit"
            className="w-full text-white"
        >
            Save Changes
        </button>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghost_buttons = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Action -> Event Handler"]
    assert len(ghost_buttons) == 0
    empty_handlers = [u for u in result["empty_or_unfinished"] if u["item_type"] == "empty_handler"]
    assert len(empty_handlers) == 0


# 9. Multiline JSX button inside working form is not flagged
def test_multiline_jsx_button_inside_form_not_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "FormView.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function FormView({ onSubmit }) {
    return (
        <form
            onSubmit={onSubmit}
            className="space-y-4"
        >
            <input name="email" type="email" />
            <button
                className="btn"
            >
                Subscribe
            </button>
        </form>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghost_buttons = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Action -> Event Handler"]
    assert len(ghost_buttons) == 0


# 10. Multiline JSX button with empty inline handler is flagged
def test_multiline_jsx_button_empty_inline_handler_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "EmptyBtn.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function EmptyBtn() {
    return (
        <button
            onClick={() => {}}
            className="btn btn-secondary"
        >
            Export All Records
        </button>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    empty_handlers = [u for u in result["empty_or_unfinished"] if u["item_type"] == "empty_handler"]
    assert len(empty_handlers) >= 1
    assert "Export All Records" in empty_handlers[0]["name"]
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "UI Action -> Event Handler"]
    assert len(ghosts) >= 1


# 11. Multiline form with onSubmit is not flagged
def test_multiline_form_with_onsubmit_not_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "WorkingForm.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function WorkingForm() {
    const handleFormSubmit = (e) => { e.preventDefault(); };
    return (
        <form
            onSubmit={handleFormSubmit}
            method="post"
        >
            <input name="name" />
            <button type="submit">Submit</button>
        </form>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghost_forms = [g for g in result["ghost_features"] if "Form" in g["chain_stage"]]
    assert len(ghost_forms) == 0


# 12. Multiline form without handler is flagged
def test_multiline_form_without_handler_flagged(tmp_path: Path):
    comp_tsx = tmp_path / "BrokenForm.tsx"
    comp_tsx.write_text(
        """
import React from 'react';

export function BrokenForm() {
    return (
        <form
            className="flex flex-col gap-2"
        >
            <input name="feedback" />
            <textarea name="details" />
            <button type="button">Send</button>
        </form>
    );
}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghost_forms = [g for g in result["ghost_features"] if "Form" in g["chain_stage"]]
    assert len(ghost_forms) >= 1
    assert "lacks both" in ghost_forms[0]["missing_links"][0].lower() or "pipeline" in ghost_forms[0]["explanation"].lower()


# 13. Legitimate default returns not flagged as unfinished
def test_legitimate_default_returns_not_flagged_as_unfinished(tmp_path: Path):
    api_py = tmp_path / "defaults.py"
    api_py.write_text(
        """
def find_user_by_id(user_id: int):
    return None

def is_account_active(user_id: int) -> bool:
    return False

def list_active_tags() -> list:
    return []

def get_empty_metadata() -> dict:
    return {}

def get_default_prefix() -> str:
    return ""
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    unfinished_names = {u["name"] for u in result["empty_or_unfinished"]}
    assert "find_user_by_id" not in unfinished_names
    assert "is_account_active" not in unfinished_names
    assert "list_active_tags" not in unfinished_names
    assert "get_empty_metadata" not in unfinished_names
    assert "get_default_prefix" not in unfinished_names


# 14. Definite stubs (pass, ..., NotImplementedError) are flagged as unfinished
def test_definite_stubs_pass_and_ellipsis_flagged_as_unfinished(tmp_path: Path):
    stubs_py = tmp_path / "stubs.py"
    stubs_py.write_text(
        """
def stub_pass_handler():
    pass

def stub_ellipsis_handler():
    ...

def stub_not_implemented_handler():
    raise NotImplementedError("Feature in development")
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    unfinished_names = {u["name"] for u in result["empty_or_unfinished"]}
    assert "stub_pass_handler" in unfinished_names
    assert "stub_ellipsis_handler" in unfinished_names
    assert "stub_not_implemented_handler" in unfinished_names


# 15. Feature flag defined without consumers is flagged (Requires Owner Confirmation)
def test_feature_flag_defined_without_consumers_flagged(tmp_path: Path):
    config_py = tmp_path / "config.py"
    config_py.write_text(
        """
FEATURE_NEW_BILLING_SYSTEM = True
ENABLE_ANALYTICS_V2 = False
""",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("print('running without flags')\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    ghost_flags = [g for g in result["ghost_features"] if "Feature Flag" in g["chain_stage"]]
    assert len(ghost_flags) >= 2
    flag_names = {g.get("flag_name") for g in ghost_flags}
    assert "FEATURE_NEW_BILLING_SYSTEM" in flag_names
    assert ghost_flags[0]["finding_state"] == "Requires Owner Confirmation"


# 16. Feature flag with consumers is not flagged as dead
def test_feature_flag_with_consumers_not_flagged_as_dead(tmp_path: Path):
    config_py = tmp_path / "config.py"
    config_py.write_text("FEATURE_CHECKOUT_EXPERIMENT = True\n", encoding="utf-8")
    service_py = tmp_path / "service.py"
    service_py.write_text(
        """
from .config import FEATURE_CHECKOUT_EXPERIMENT

def process_order():
    if FEATURE_CHECKOUT_EXPERIMENT:
        return {"experiment": True}
    return {"experiment": False}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghost_flags = [g for g in result["ghost_features"] if g.get("flag_name") == "FEATURE_CHECKOUT_EXPERIMENT"]
    assert len(ghost_flags) == 0


# 17. Route test coverage requires assertions, not just path string
def test_route_test_coverage_requires_assertions_not_just_path_string(tmp_path: Path):
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.route("/api/v1/checkout", methods=["POST"])
def checkout():
    return {"status": "ok"}
""",
        encoding="utf-8",
    )

    test_file = tmp_path / "test_notes.py"
    test_file.write_text(
        """
# Notes for checkout:
# We should eventually test /api/v1/checkout
checkout_endpoint = "/api/v1/checkout"
def dummy_placeholder():
    pass
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    # The route /api/v1/checkout must NOT be classified as test_verified
    uncovered = [r for r in result["uncovered_routes"] if r["endpoint"] == "/api/v1/checkout"]
    assert len(uncovered) == 1
    assert uncovered[0]["coverage_status"] == "test_reference_candidate"


# 18. AST duplicate detection preserves external function calls
def test_ast_duplicate_detection_preserves_external_function_calls(tmp_path: Path):
    file1 = tmp_path / "tax_service.py"
    file1.write_text(
        """
def compute_total(base_amount, factor):
    adjusted = calculate_tax_api(base_amount)
    total = adjusted * factor
    return total + 5
""",
        encoding="utf-8",
    )

    file2 = tmp_path / "shipping_service.py"
    file2.write_text(
        """
def compute_total(base_amount, factor):
    adjusted = calculate_shipping_api(base_amount)
    total = adjusted * factor
    return total + 5
""",
        encoding="utf-8",
    )

    # Calling calculate_tax_api vs calculate_shipping_api means different external calls
    dups = estimate_duplicate_blocks([file1, file2])
    assert len(dups) == 0


# 19. Scan file limit and truncation status reported
def test_scan_file_limit_and_truncation_reported(tmp_path: Path):
    # Create 10 python files
    for i in range(10):
        (tmp_path / f"file_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")

    registry = LanguageRegistry()
    # Scan with limit of 4 files
    scan_data = registry.scan_repository(tmp_path, file_limit=4)
    assert scan_data["file_count"] > 4
    assert scan_data["scan_truncated"] is True
    assert scan_data["file_limit"] == 4


# 20. Audit repo CLI outputs valid JSON and Markdown reports
def test_audit_repo_cli_outputs_valid_json_and_markdown(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")

    runner = CliRunner()
    # Test JSON output via --output
    json_dest = tmp_path / "report.json"
    res_json = runner.invoke(app, ["audit-repo", "--project-root", str(tmp_path), "--output", str(json_dest)])
    assert res_json.exit_code == 0
    assert json_dest.is_file()
    parsed_json = json.loads(json_dest.read_text(encoding="utf-8"))
    assert parsed_json["schema_version"] == "2.0"
    assert "capability_matrix" in parsed_json

    # Test Markdown output via --output
    md_dest = tmp_path / "report.md"
    res_md = runner.invoke(app, ["audit-repo", "--project-root", str(tmp_path), "--output", str(md_dest)])
    assert res_md.exit_code == 0
    assert md_dest.is_file()
    md_content = md_dest.read_text(encoding="utf-8")
    assert "# Ghost Hunt Repository Audit" in md_content
    assert "## Capability Matrix" in md_content

    # Test stdout JSON via --json
    res_stdout = runner.invoke(app, ["audit-repo", "--project-root", str(tmp_path), "--json"])
    assert res_stdout.exit_code == 0
    stdout_parsed = json.loads(res_stdout.output)
    assert stdout_parsed["schema_version"] == "2.0"


# -----------------------------------------------------------------------------
# Additional Feature & Framework Integration Tests
# -----------------------------------------------------------------------------

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
    caps = [c for c in result["capability_matrix"] if "Flask" in c["language_framework"]]
    assert len(caps) >= 1
    assert caps[0]["status"] == "supported"


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
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "Backend Route -> Service Logic"]
    assert len(ghosts) >= 1
    assert "/api/reports/quarterly" in ghosts[0]["present_links"][0]

    unf = [u for u in result["empty_or_unfinished"] if "quarterly_report" in u["name"]]
    assert len(unf) >= 1
    assert unf[0]["item_type"] == "empty_function"


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
    missing = result["missing_route_candidates"]
    assert len(missing) >= 1
    assert missing[0]["endpoint"] == "/api/v1/feedback"
    assert missing[0]["method"] == "POST"


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


def test_orphaned_service_with_no_detected_caller(tmp_path: Path):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    svc_py = services_dir / "payment_service.py"
    svc_py.write_text(
        """
def process_manual_reversal(transaction_id, amount_cents):
    fee = amount_cents * 0.02
    return {"reversed": True, "fee": fee}
""",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    ghosts = [g for g in result["ghost_features"] if g["chain_stage"] == "Business Logic -> Application Entry Point"]
    assert len(ghosts) >= 1
    assert "process_manual_reversal" in ghosts[0]["evidence"]


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


def test_dynamically_registered_route_caveat(tmp_path: Path):
    result = audit_repository(tmp_path)
    limits = " ".join(result["limitations"]).lower()
    assert "dynamic" in limits
    assert "proxy" in limits or "reflection" in limits


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
    assert len(dups) == 0


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
    defects = [u for u in result["empty_or_unfinished"] if "process_record" in u["name"] or "validate_schema" in u["name"]]
    assert len(defects) == 0


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
