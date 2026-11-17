"""Adversarial regression test suite for Ghost Hunt.

Validates the 20 critical reliability scenarios:
1. HTTP Method Mismatch Detection
2. Cross-Application Route Boundary Isolation (Monorepo)
3. Passive Test Mention Rejection (No false positive test_assertion_candidate)
4. Valid Test Assertion Acceptance
5. Deletion-Only Diff Line Attribution
6. Mixed Diff Line Attribution
7. Multi-Function Database Transaction Isolation (No false positive across separate functions)
8. Unprotected Multi-Mutation in File with Unrelated Transaction (No false negative)
9. Injection Risk Calibration (Proven untrusted user input vs internal pattern)
10. Feature Connection Map End-to-End Tracing & Gap Detection
11. Full 8-Layer Feature Path Tracing with Evidence Across All Tiers
12. Missing Service Implementation Detection (Handler invokes undefined business service)
13. Unfinished Service Implementation Detection (Handler invokes stubbed service)
14. Database Operation Reached Through Service Layer
15. Response Serialization & Unconsumed Client Response Detection
16. UI Named Callback Event Handler Tracing
17. Global Middleware-Based Authorization Recognition
18. Static Graph Never Implies Runtime PASS (Strict unknown/fail enforcement)
19. Mermaid Diagram Structural Consistency Across 8 Layers
20. Target Feature Filtering Precision (Isolates targeted paths, suppresses unrelated routes)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.adapters.http import HTTPAdapter
from ghost_hunter.cli import app
from ghost_hunter.config import HunterConfig
from ghost_hunter.discovery.audit import (
    _evaluate_route_test_coverage,
    _inspect_polyglot_test_blocks,
    audit_repository,
)
from ghost_hunter.discovery.connection_map import (
    generate_feature_connection_map,
    render_ascii_connection_map,
    render_mermaid_diagram,
)
from ghost_hunter.discovery.languages.models import RouteDefinition
from ghost_hunter.journeys.generator import generate_feature_journey
from ghost_hunter.models import Journey, Status
from ghost_hunter.review import render_review_markdown, run_code_review


# ==============================================================================
# Scenario 1: HTTP Method Mismatch Detection
# ==============================================================================
def test_scenario_1_http_method_mismatch(tmp_path: Path):
    """Client calls POST on a route that only accepts GET -> HTTP 405 defect."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/profile', methods=['GET'])
def get_profile():
    return {'user': 'alice'}
""",
        encoding="utf-8",
    )
    (src / "api.js").write_text(
        """async function updateProfile(data) {
    return await fetch('/api/v1/profile', { method: 'POST', body: JSON.stringify(data) });
}
""",
        encoding="utf-8",
    )

    review_res = run_code_review(tmp_path)
    findings = [f for f in review_res["findings"] if f["category"] == "route_mismatch"]
    assert len(findings) == 1
    assert "POST" in findings[0]["title"]
    assert "405" in findings[0]["failure_scenario"]
    assert findings[0]["severity"] == "High"


# ==============================================================================
# Scenario 2: Cross-Application Route Boundary Isolation (Monorepo)
# ==============================================================================
def test_scenario_2_cross_app_route_isolation_in_monorepo(tmp_path: Path):
    """In a monorepo, App A's client call must NOT be satisfied by App B's route."""
    # App A: Customer Web App
    app_a = tmp_path / "apps" / "customer-portal"
    app_a.mkdir(parents=True)
    (app_a / "package.json").write_text('{"name": "customer-portal"}', encoding="utf-8")
    (app_a / "src").mkdir()
    (app_a / "src" / "api.ts").write_text(
        """fetch('/api/v1/billing/invoices');""",
        encoding="utf-8",
    )

    # App B: Admin Service (defines /api/v1/billing/invoices)
    app_b = tmp_path / "services" / "admin-service"
    app_b.mkdir(parents=True)
    (app_b / "pyproject.toml").write_text('[project]\nname = "admin-service"\n', encoding="utf-8")
    (app_b / "routes.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/billing/invoices', methods=['GET'])
def list_invoices():
    return []
""",
        encoding="utf-8",
    )

    review_res = run_code_review(tmp_path)
    # The client call in customer-portal should be flagged as an unregistered endpoint
    # because it is calling an endpoint not registered in customer-portal
    wiring_findings = [f for f in review_res["findings"] if f["category"] == "wiring"]
    assert len(wiring_findings) >= 1
    invoice_finding = next(f for f in wiring_findings if "/api/v1/billing/invoices" in f["title"])
    assert "unregistered endpoint" in invoice_finding["title"].lower()
    assert invoice_finding["file_path"].startswith("apps/customer-portal")


# ==============================================================================
# Scenario 3: Passive Test Mention Without Assertion
# ==============================================================================
def test_scenario_3_passive_test_mention_without_assertion():
    """Polyglot test merely logging or reading response property is NOT an assertion candidate."""
    # Go test merely logging w.Code
    go_content = """package main
import (
    "net/http/httptest"
    "testing"
    "log"
)
func TestLoggingOnly(t *testing.T) {
    req := httptest.NewRequest("GET", "/api/v1/users", nil)
    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)
    log.Println(w.Code)
}
"""
    has_assert, has_ref, has_code = _inspect_polyglot_test_blocks(go_content, "/api/v1/users", "user_test.go")
    assert has_assert is False
    assert has_ref is True

    route = RouteDefinition(path="/api/v1/users", methods=["GET"], function="getUsers", source="main.go", line=1, framework="Go")
    cov = _evaluate_route_test_coverage(route, [("user_test.go", go_content)])
    assert cov == "test_reference_candidate"
    assert cov != "test_assertion_candidate"

    # C# test merely writing to console
    cs_content = """using System;
using Xunit;
public class UserTests {
    [Fact]
    public async Task TestReadWithoutAssert() {
        var response = await client.GetAsync("/api/v1/users");
        Console.WriteLine(response.StatusCode);
    }
}
"""
    has_assert_cs, has_ref_cs, _ = _inspect_polyglot_test_blocks(cs_content, "/api/v1/users", "UserTests.cs")
    assert has_assert_cs is False
    assert has_ref_cs is True


# ==============================================================================
# Scenario 4: Valid Test Assertion Acceptance
# ==============================================================================
def test_scenario_4_valid_test_assertion_acceptance():
    """Polyglot tests with explicit assertions are accepted as test_assertion_candidate."""
    # Go conditional failure check
    go_content = """package main
import (
    "net/http/httptest"
    "testing"
)
func TestAssertValid(t *testing.T) {
    req := httptest.NewRequest("GET", "/api/v1/users", nil)
    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)
    if w.Code != 200 {
        t.Fatalf("expected 200, got %d", w.Code)
    }
}
"""
    has_assert, _, _ = _inspect_polyglot_test_blocks(go_content, "/api/v1/users", "user_test.go")
    assert has_assert is True

    # C# Xunit Assert.Equal
    cs_content = """using Xunit;
public class UserTests {
    [Fact]
    public async Task TestAssertValid() {
        var response = await client.GetAsync("/api/v1/users");
        Assert.Equal(200, (int)response.StatusCode);
    }
}
"""
    has_assert_cs, _, _ = _inspect_polyglot_test_blocks(cs_content, "/api/v1/users", "UserTests.cs")
    assert has_assert_cs is True


# ==============================================================================
# Scenario 5: Deletion-Only Diff Attribution
# ==============================================================================
def test_scenario_5_deletion_only_diff_attribution(tmp_path: Path):
    """When a commit only deletes code, findings on remaining code must be pre_existing_risks."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    # Initial commit with a stub function AND a deprecated function
    (src / "service.py").write_text(
        """def unfinished_stub():
    pass

def deprecated_function():
    return "old"
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, check=True, capture_output=True)

    # Now, delete ONLY deprecated_function()
    (src / "service.py").write_text(
        """def unfinished_stub():
    pass
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    # The unfinished_stub should NOT be reported as an introduced finding by the deletion!
    assert result["findings_count"] == 0
    assert result["pre_existing_risks_count"] >= 1
    pre = result["pre_existing_risks"][0]
    assert "unfinished_stub" in pre["title"]


# ==============================================================================
# Scenario 6: Mixed Diff Line Attribution
# ==============================================================================
def test_scenario_6_mixed_diff_line_attribution(tmp_path: Path):
    """In a mixed diff, pre-existing issues on untouched lines are pre_existing_risks."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    # Initial commit: line 1 has an unfinished stub
    (src / "util.py").write_text(
        """def old_stub():
    pass

def helper():
    return 42
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    # Edit: append a new stub at the bottom
    (src / "util.py").write_text(
        """def old_stub():
    pass

def helper():
    return 42

def new_stub():
    pass
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    # new_stub is introduced (lines 7-8)
    introduced = [f for f in result["findings"] if "new_stub" in f["title"]]
    assert len(introduced) == 1
    # old_stub is pre-existing (line 1)
    pre_existing = [f for f in result["pre_existing_risks"] if "old_stub" in f["title"]]
    assert len(pre_existing) == 1


# ==============================================================================
# Scenario 7: Multi-Function Database Transaction Isolation
# ==============================================================================
def test_scenario_7_multi_function_transaction_isolation(tmp_path: Path):
    """Two separate functions each performing 1 mutation must NOT trigger a missing transaction finding."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "handlers.py").write_text(
        """def create_user(user):
    db.session.add(user)

def remove_item(item):
    db.session.delete(item)
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    tx_findings = [f for f in result["findings"] if f["category"] == "data_risk"]
    assert len(tx_findings) == 0


# ==============================================================================
# Scenario 8: Unprotected Multi-Mutation in File with Unrelated Transaction
# ==============================================================================
def test_scenario_8_unprotected_multi_mutation_with_unrelated_transaction(tmp_path: Path):
    """Function A has 2 mutations without transaction; Function B has transaction -> Function A is flagged."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text(
        """def transfer_funds(account_a, account_b):
    db.session.delete(account_a)
    db.session.add(account_b)

def safe_batch():
    with transaction.atomic():
        db.session.add(x)
        db.session.add(y)
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    tx_findings = [f for f in result["findings"] if f["category"] == "data_risk"]
    assert len(tx_findings) == 1
    assert "transfer_funds" in tx_findings[0]["title"]
    assert tx_findings[0]["line_number"] == 2


# ==============================================================================
# Scenario 9: Injection Risk Calibration
# ==============================================================================
def test_scenario_9_injection_risk_calibration(tmp_path: Path):
    """Direct user input reaches SQL sink -> Critical; internal variable pattern -> Medium."""
    src = tmp_path / "src"
    src.mkdir()
    # Tainted query
    (src / "tainted.py").write_text(
        """def search(request):
    cursor.execute(f"SELECT * FROM items WHERE name = '{request.args.get('q')}'")
""",
        encoding="utf-8",
    )
    # Untainted query with internal variable
    (src / "internal.py").write_text(
        """def get_count(table_name):
    cursor.execute(f"SELECT count(*) FROM {table_name}")
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    findings = [f for f in result["findings"] if f["category"] == "security" and "Injection risk" in f["title"]]

    tainted_finding = next(f for f in findings if "tainted.py" in f["file_path"])
    assert tainted_finding["severity"] == "Critical"
    assert "direct SQL injection" in tainted_finding["title"]

    internal_finding = next(f for f in findings if "internal.py" in f["file_path"])
    assert internal_finding["severity"] == "Medium"
    assert "raw SQL query with f-string interpolation" in internal_finding["title"]


# ==============================================================================
# Scenario 10: Feature Connection Map End-to-End Tracing
# ==============================================================================
def test_scenario_10_feature_connection_map_tracing(tmp_path: Path):
    """Traces UI button -> Client Call -> Route -> Controller -> DB, highlighting gaps."""
    src = tmp_path / "src"
    src.mkdir()

    # Route with method mismatch vs client
    (src / "app.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/orders', methods=['GET'])
def get_orders():
    return []
""",
        encoding="utf-8",
    )
    # Client calling POST /api/v1/orders
    (src / "Checkout.jsx").write_text(
        """export function CheckoutButton() {
    return <button onClick={() => fetch('/api/v1/orders', { method: 'POST' })}>Submit</button>;
}
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    assert conn_map["nodes_count"] >= 3
    assert conn_map["broken_edges_count"] >= 1

    # Check contract findings
    findings = conn_map["contract_findings"]
    assert any(cf["category"] == "method_mismatch" for cf in findings)

    # Check Mermaid diagram generation
    mermaid = conn_map["mermaid"]
    assert "graph LR" in mermaid
    assert "subgraph" in mermaid

    # Check CLI map runner
    runner = CliRunner()
    res = runner.invoke(app, ["map", "-p", str(tmp_path)])
    assert res.exit_code == 0
    assert "Feature Connection Map" in res.stdout


# ==============================================================================
# Scenario 11: Full 8-Layer Feature Path Tracing
# ==============================================================================
def test_scenario_11_full_8_layer_feature_path(tmp_path: Path):
    """Verifies that an end-to-end connected feature touches all 8 layers:
    UI -> Client API -> Route -> Controller -> Service -> Database -> Response -> Test.
    """
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()

    # Layer 3 (Route), Layer 4 (Controller), Layer 7 (Response)
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
from services import charge_payment
app = Flask(__name__)

@app.route('/api/pay', methods=['POST'])
def pay_endpoint():
    charge_payment()
    return jsonify({'status': 'charged'}), 200
""",
        encoding="utf-8",
    )

    # Layer 5 (Service), Layer 6 (Database)
    (src / "services.py").write_text(
        """from models import Order
def charge_payment():
    Order.query.filter_by(status='pending').all()
""",
        encoding="utf-8",
    )
    (src / "models.py").write_text(
        """class Order(Base):
    pass
""",
        encoding="utf-8",
    )

    # Layer 1 (UI), Layer 2 (Client API)
    (src / "Checkout.jsx").write_text(
        """export function CheckoutForm() {
    async function handlePay() {
        const res = await fetch('/api/pay', { method: 'POST' });
        const data = await res.json();
        return data;
    }
    return <button onClick={handlePay}>Confirm Payment</button>;
}
""",
        encoding="utf-8",
    )

    # Layer 8 (Test)
    (tests / "test_pay.py").write_text(
        """def test_pay_flow(client):
    res = client.post('/api/pay')
    assert res.status_code == 200
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    layers = {n["layer"] for n in conn_map["nodes"]}
    expected_layers = {"ui", "client_api", "route", "controller", "service", "database", "response", "test"}
    assert expected_layers.issubset(layers), f"Missing layers: {expected_layers - layers}"


# ==============================================================================
# Scenario 12: Missing Service Implementation Detection
# ==============================================================================
def test_scenario_12_missing_service_detection(tmp_path: Path):
    """Controller invokes a service function that is never declared anywhere."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/api/inventory/reserve', methods=['POST'])
def reserve():
    reserve_inventory_stock()
    return jsonify({'status': 'reserved'})
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    findings = [f for f in conn_map["contract_findings"] if f["category"] == "missing_service"]
    assert len(findings) >= 1
    assert "reserve_inventory_stock" in findings[0]["message"]
    assert findings[0]["severity"] == "High"


# ==============================================================================
# Scenario 13: Unfinished Service Implementation Detection
# ==============================================================================
def test_scenario_13_unfinished_service_detection(tmp_path: Path):
    """Controller calls a declared service whose body is a NotImplementedError stub."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
from services import process_refund
app = Flask(__name__)

@app.route('/api/refund', methods=['POST'])
def refund_route():
    process_refund()
    return jsonify({'status': 'refunded'})
""",
        encoding="utf-8",
    )
    (src / "services.py").write_text(
        """def process_refund():
    raise NotImplementedError("TODO: Implement payment gateway refund call")
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    findings = [f for f in conn_map["contract_findings"] if f["category"] == "unfinished_service"]
    assert len(findings) >= 1
    assert "process_refund" in findings[0]["message"]
    assert findings[0]["severity"] == "High"


# ==============================================================================
# Scenario 14: Database Operation Reached Through Service Layer
# ==============================================================================
def test_scenario_14_database_operation_via_service(tmp_path: Path):
    """Route controller invokes service, which in turn queries/mutates the database model."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
from services import create_order_service
app = Flask(__name__)

@app.route('/api/orders', methods=['POST'])
def create_order():
    create_order_service()
    return jsonify({'id': 1}), 201
""",
        encoding="utf-8",
    )
    (src / "services.py").write_text(
        """from models import Order
def create_order_service():
    Order.query.all()
""",
        encoding="utf-8",
    )
    (src / "models.py").write_text(
        """class Order(Base):
    pass
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    db_nodes = [n for n in conn_map["nodes"] if n["layer"] == "database"]
    assert len(db_nodes) >= 1
    assert any("Order" in n["name"] for n in db_nodes)


# ==============================================================================
# Scenario 15: Response Serialization & Unconsumed Client Response Detection
# ==============================================================================
def test_scenario_15_unconsumed_response_detection(tmp_path: Path):
    """Backend route sends JSON payload, but frontend client drops/ignores the response."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    return jsonify({'cpu_load': 0.45, 'active_threads': 12})
""",
        encoding="utf-8",
    )
    (src / "client.js").write_text(
        """function checkHealth() {
    fetch('/api/metrics');
}
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    findings = [f for f in conn_map["contract_findings"] if f["category"] == "unconsumed_response"]
    assert len(findings) >= 1
    assert "/api/metrics" in findings[0]["feature_or_route"]


# ==============================================================================
# Scenario 16: UI Named Callback Event Handler Tracing
# ==============================================================================
def test_scenario_16_ui_named_callback_tracing(tmp_path: Path):
    """UI element onClick={submitForm} resolves to named client function calling endpoint."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "Checkout.jsx").write_text(
        """export function CheckoutPage() {
    function submitCheckout() {
        fetch('/api/checkout', { method: 'POST' });
    }
    return <button onClick={submitCheckout}>Submit Order</button>;
}
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    cb_edges = [e for e in conn_map["edges"] if e["link_type"] == "named_callback"]
    assert len(cb_edges) >= 1
    assert cb_edges[0]["status"] == "CONNECTED"


# ==============================================================================
# Scenario 17: Global Middleware-Based Authorization Recognition
# ==============================================================================
def test_scenario_17_global_middleware_auth_recognition(tmp_path: Path):
    """Sensitive route without route-level decorator does NOT trigger false missing_auth if global auth exists."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, request, abort
app = Flask(__name__)

@app.before_request
def auth_middleware():
    if not request.headers.get('Authorization'):
        abort(401)

@app.route('/api/admin/users', methods=['DELETE'])
def delete_user():
    return {'status': 'deleted'}
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    auth_findings = [f for f in conn_map["contract_findings"] if f["category"] == "missing_auth"]
    assert len(auth_findings) == 0


# ==============================================================================
# Scenario 18: Static Graph Never Implies Runtime PASS
# ==============================================================================
def test_scenario_18_static_graph_never_implies_runtime_pass(tmp_path: Path):
    """Even if an 8-layer map is statically connected, live verification without server returns UNKNOWN, never PASS."""
    journey = Journey(
        feature="orders",
        steps=[
            {
                "id": "order-check",
                "checkpoint": "Order service responds",
                "adapter": "http",
                "expected_behavior": "GET /api/orders returns HTTP 200",
                "settings": {"method": "GET", "url": "/api/orders", "checks": {"status_code": 200}},
            }
        ],
    )
    # Using dead port to ensure connection refusal
    context = AdapterContext(tmp_path, HunterConfig(base_url="http://127.0.0.1:59999"))
    adapter = HTTPAdapter()
    result = adapter.verify(context, journey, journey.steps[0])

    assert result.status == Status.UNKNOWN
    assert result.status != Status.PASS
    assert "could not be completed" in result.actual_observation


# ==============================================================================
# Scenario 19: Mermaid Diagram Structural Consistency Across 8 Layers
# ==============================================================================
def test_scenario_19_mermaid_diagram_consistency(tmp_path: Path):
    """Mermaid diagram contains subgraphs for all discovered layers and valid nodes."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
app = Flask(__name__)
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200
""",
        encoding="utf-8",
    )

    conn_map = generate_feature_connection_map(tmp_path)
    mermaid = conn_map["mermaid"]

    assert "graph LR" in mermaid
    assert "subgraph" in mermaid
    for node in conn_map["nodes"]:
        assert node["id"] in mermaid


# ==============================================================================
# Scenario 20: Target Feature Filtering Precision
# ==============================================================================
def test_scenario_20_target_feature_filtering_precision(tmp_path: Path):
    """Target feature filtering isolates targeted routes and suppresses unrelated endpoints."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/api/billing/invoice', methods=['GET'])
def get_invoice():
    return jsonify({'total': 100})

@app.route('/api/users/profile', methods=['GET'])
def get_profile():
    return jsonify({'user': 'alice'})
""",
        encoding="utf-8",
    )

    filtered_map = generate_feature_connection_map(tmp_path, target_feature="billing")
    route_paths = [n["details"].get("path") for n in filtered_map["nodes"] if n["layer"] == "route"]

    assert "/api/billing/invoice" in route_paths
    assert "/api/users/profile" not in route_paths

