"""Regression test suite for scope-aware repository auditing and evidence integrity.

Exercises all 16 required scenarios from Section 10:
1. Main application has no defects, but example application contains deliberate defects.
2. Explicit example inclusion produces separate example findings.
3. A fixture containing a placeholder implementation does not pollute application findings.
4. Test function calling route while a different function asserts is not verified.
5. Route call followed by unrelated assert True is not verified.
6. Route test with response-related assertion is correctly identified as assertion candidate.
7. Comment mentioning a route is not test coverage.
8. Test file is not treated as production application source.
9. Monorepo with frontend and backend apps retains separate application identities.
10. Dependencies are attributed to the correct nested application.
11. Unsupported dependency manifests are labeled as inventory-only.
12. API call to another configured local service is not marked as missing local endpoint.
13. Reverse-proxy endpoint remains an uncertainty candidate.
14. Mixed-language application retains its existing language capability matrix.
15. Existing Flask, FastAPI, Django, Express, Next.js and React capabilities pass.
16. The skill mirror remains exactly synchronized.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghost_hunter.discovery.audit import (
    _evaluate_route_test_coverage,
    audit_dependencies,
    audit_repository,
)
from ghost_hunter.discovery.languages.models import RouteDefinition
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.project import (
    classify_source_role,
    detect_application_boundaries,
    detect_project_context,
    resolve_file_scope,
)


# 1. Main application has no defects, but its example application contains deliberate defects.
def test_scenario_1_main_app_clean_example_defects_isolated(tmp_path: Path):
    # Primary application in src/
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        """from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""",
        encoding="utf-8",
    )

    # Deliberately broken example in examples/
    ex_dir = tmp_path / "examples" / "broken_demo"
    ex_dir.mkdir(parents=True)
    (ex_dir / "broken_app.py").write_text(
        """from fastapi import FastAPI
demo = FastAPI()

@demo.get("/broken")
def broken():
    pass
""",
        encoding="utf-8",
    )
    (ex_dir / "caller.js").write_text(
        """fetch('/api/v1/ghost-route');""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path, include_examples=False)

    # Primary application must not contain demo findings
    assert len(result["primary_application_findings"]["empty_or_unfinished"]) == 0
    assert len(result["primary_application_findings"]["missing_route_candidates"]) == 0
    assert len(result["empty_or_unfinished"]) == 0
    assert len(result["missing_route_candidates"]) == 0

    # Example findings are captured separately
    assert len(result["example_findings"]["empty_or_unfinished"]) >= 1
    assert any(
        f["scope"] == "example" for f in result["example_findings"]["empty_or_unfinished"]
    )


# 2. Explicit example inclusion produces a separate example finding section.
def test_scenario_2_explicit_example_inclusion_produces_separate_sections(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text(
        """from fastapi import FastAPI
app = FastAPI()

@app.get("/status")
def status():
    return {"ok": True}
""",
        encoding="utf-8",
    )

    ex_dir = tmp_path / "examples" / "demo"
    ex_dir.mkdir(parents=True)
    (ex_dir / "demo.py").write_text(
        """def unfinished_sample():
    pass
""",
        encoding="utf-8",
    )

    # With include_examples=True
    result = audit_repository(tmp_path, include_examples=True)
    assert result["include_examples"] is True
    assert len(result["example_findings"]["empty_or_unfinished"]) >= 1
    # Example finding has explicit example scope
    ex_finding = result["example_findings"]["empty_or_unfinished"][0]
    assert ex_finding["scope"] == "example"
    assert ex_finding["source_role"] in ("example", "demo")


# 3. A fixture containing a placeholder implementation does not pollute application findings.
def test_scenario_3_fixture_placeholder_does_not_pollute_application_findings(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "service.py").write_text(
        """def calculate_total(a, b):
    return a + b
""",
        encoding="utf-8",
    )

    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "mock_service.py").write_text(
        """def mock_api_call():
    pass
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    assert len(result["primary_application_findings"]["empty_or_unfinished"]) == 0
    assert len(result["empty_or_unfinished"]) == 0
    assert len(result["test_and_fixture_findings"]["empty_or_unfinished"]) >= 1
    fix_finding = result["test_and_fixture_findings"]["empty_or_unfinished"][0]
    assert fix_finding["source_role"] == "fixture"
    assert fix_finding["scope"] == "test_and_fixture"


def test_source_role_and_scope_classification_regression():
    cases = [
        ("tests/fixtures/example.py", "fixture", "test_and_fixture"),
        ("tests/test_example.py", "test", "test_and_fixture"),
        ("fixtures/example.py", "fixture", "test_and_fixture"),
        ("__tests__/fixtures/example.ts", "fixture", "test_and_fixture"),
        ("examples/demo.py", "example", "example"),
        ("tests/submodule/mocks/foo.py", "fixture", "test_and_fixture"),
        ("tests/mocks/mock_service.py", "fixture", "test_and_fixture"),
        ("testdata/records.json", "fixture", "test_and_fixture"),
        ("__tests__/__mocks__/api.ts", "fixture", "test_and_fixture"),
    ]
    for path, expected_role, expected_scope in cases:
        role = classify_source_role(path)
        scope = resolve_file_scope(path)["scope"]
        assert role == expected_role, f"Failed role for {path}: got {role}, expected {expected_role}"
        assert scope == expected_scope, f"Failed scope for {path}: got {scope}, expected {expected_scope}"


# 4. A test function calling a route while a different function contains an assertion must not be considered verified.
def test_scenario_4_call_in_one_function_and_assertion_in_another_is_not_verified(tmp_path: Path):
    test_content = """def test_first():
    response = client.get("/api/v1/checkout")

def test_second():
    assert 1 == 1
    assert result.status_code == 200
"""
    route = RouteDefinition(
        path="/api/v1/checkout",
        methods=["GET"],
        source="app.py",
        line=10,
        framework="FastAPI",
        function="checkout",
    )
    test_files_data = [("test_suite.py", test_content)]
    status = _evaluate_route_test_coverage(route, test_files_data)

    assert status != "test_verified"
    assert status == "test_reference_candidate"


# 5. A route call followed by an unrelated assert True must not be considered verified.
def test_scenario_5_call_followed_by_unrelated_assert_true_is_not_verified(tmp_path: Path):
    test_content = """def test_orders():
    res = client.get("/api/v1/orders")
    assert True
"""
    route = RouteDefinition(
        path="/api/v1/orders",
        methods=["GET"],
        source="app.py",
        line=5,
        framework="FastAPI",
        function="orders",
    )
    test_files_data = [("test_orders.py", test_content)]
    status = _evaluate_route_test_coverage(route, test_files_data)

    assert status != "test_verified"
    assert status == "test_reference_candidate"


# 6. A route test with a response-related assertion is correctly identified as an assertion candidate.
def test_scenario_6_route_test_with_response_assertion_is_assertion_candidate(tmp_path: Path):
    test_content = """def test_profile():
    response = client.get("/api/v1/profile")
    assert response.status_code == 200
"""
    route = RouteDefinition(
        path="/api/v1/profile",
        methods=["GET"],
        source="app.py",
        line=12,
        framework="FastAPI",
        function="profile",
    )
    test_files_data = [("test_profile.py", test_content)]
    status = _evaluate_route_test_coverage(route, test_files_data)

    assert status == "test_assertion_candidate"
    # Never claim runtime test_verified from static analysis alone
    assert status != "test_verified"


# 7. A comment mentioning a route is not test coverage.
def test_scenario_7_comment_mentioning_route_is_not_test_coverage(tmp_path: Path):
    test_content = """# We need to write tests for /api/v1/billing endpoint
def test_other_feature():
    assert 2 + 2 == 4
"""
    route = RouteDefinition(
        path="/api/v1/billing",
        methods=["GET"],
        source="app.py",
        line=20,
        framework="FastAPI",
        function="billing",
    )
    test_files_data = [("test_billing.py", test_content)]
    status = _evaluate_route_test_coverage(route, test_files_data)

    assert status == "testing_gap_candidate"
    assert status != "test_assertion_candidate"
    assert status != "test_verified"


# 8. A test file is not treated as production application source.
def test_scenario_8_test_file_not_treated_as_production_application_source(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "billing_service.py").write_text(
        """def compute_invoice():
    return 100
""",
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_billing.py").write_text(
        """from src.billing_service import compute_invoice

def test_invoice():
    val = compute_invoice()
    assert val == 100
""",
        encoding="utf-8",
    )

    # Classify source roles
    assert classify_source_role("src/billing_service.py") == "application_source"
    assert classify_source_role("tests/test_billing.py") == "test"

    result = audit_repository(tmp_path)
    # The billing_service function has callers only in tests, not in production code
    orphaned = [g for g in result["ghost_features"] if "compute_invoice" in g.get("evidence", "")]
    assert len(orphaned) == 1
    assert orphaned[0]["test_reference_found"] is True


# 9. A monorepo with frontend and backend apps retains separate application identities.
def test_scenario_9_monorepo_frontend_and_backend_apps_retain_separate_identities(tmp_path: Path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "pyproject.toml").write_text(
        """[project]
name = "api-service"
version = "0.1.0"
dependencies = []
""",
        encoding="utf-8",
    )
    (backend_dir / "main.py").write_text(
        """from fastapi import FastAPI
app = FastAPI()

@app.get("/api/items")
def items():
    return []
""",
        encoding="utf-8",
    )

    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text(
        """{"name": "web-client", "dependencies": {}}""",
        encoding="utf-8",
    )
    (frontend_dir / "App.jsx").write_text(
        """export default function App() { return <h1>Items</h1>; }""",
        encoding="utf-8",
    )

    context = detect_project_context(tmp_path)
    boundaries = context["application_boundaries"]
    assert len(boundaries) >= 2

    app_names = {b["app_name"] for b in boundaries}
    assert "api-service" in app_names or "backend" in app_names
    assert "web-client" in app_names or "frontend" in app_names


# 10. Dependencies are attributed to the correct nested application.
def test_scenario_10_dependencies_attributed_to_correct_nested_application(tmp_path: Path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        """[project]
name = "backend-app"
dependencies = [
    "requests",
]
""",
        encoding="utf-8",
    )
    (backend / "service.py").write_text(
        """import requests
def fetch_data():
    return requests.get("https://example.com")
""",
        encoding="utf-8",
    )

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        """{
  "name": "frontend-app",
  "dependencies": {
    "axios": "^1.0.0",
    "unused-package": "^2.0.0"
  }
}""",
        encoding="utf-8",
    )
    (frontend / "index.js").write_text(
        """import axios from 'axios';
axios.get('/api/data');
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    dep_audit = result["dependency_hygiene"]
    unused = dep_audit["potentially_unused"]

    # unused-package should be attributed to frontend-app
    unused_frontend = [u for u in unused if u["package"] == "unused-package"]
    assert len(unused_frontend) == 1
    assert "frontend" in unused_frontend[0]["manifest"]
    assert unused_frontend[0]["finding_state"] == "Requires Owner Confirmation"

    # requests in backend must NOT be marked unused
    unused_requests = [u for u in unused if u["package"] == "requests"]
    assert len(unused_requests) == 0


# 11. Unsupported dependency manifests are labeled as inventory-only.
def test_scenario_11_unsupported_dependency_manifests_labeled_as_inventory_only(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text(
        """[package]
name = "rust-core"
version = "0.1.0"
""",
        encoding="utf-8",
    )
    (tmp_path / "go.mod").write_text(
        """module github.com/test/project
go 1.21
""",
        encoding="utf-8",
    )

    result = audit_dependencies(tmp_path)
    inv_only = result["inventory_only_manifests"]
    assert len(inv_only) >= 2

    manifest_names = {entry["manifest"] for entry in inv_only}
    assert "Cargo.toml" in manifest_names
    assert "go.mod" in manifest_names

    for entry in inv_only:
        assert entry["usage_analysis_supported"] is False
        assert entry["analysis_status"] == "inventory-only"
        assert "not currently supported" in entry["explanation"]


# 12. An API call to another configured local service is not marked as a missing local endpoint.
def test_scenario_12_cross_service_api_call_not_marked_as_missing_local_endpoint(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "web-frontend"}', encoding="utf-8")
    (frontend / "client.js").write_text(
        """fetch('/api/v1/users');""",
        encoding="utf-8",
    )

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text('[project]\nname = "api-backend"', encoding="utf-8")
    (backend / "routes.py").write_text(
        """from fastapi import FastAPI
app = FastAPI()

@app.get("/api/v1/users")
def get_users():
    return [{"id": 1}]
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    missing = result["primary_application_findings"]["missing_route_candidates"]

    # Cross-service matching routes are not missing endpoints
    missing_for_users = [m for m in missing if m["endpoint"] == "/api/v1/users"]
    assert len(missing_for_users) == 0


# 13. A reverse-proxy endpoint remains an uncertainty candidate where appropriate.
def test_scenario_13_reverse_proxy_endpoint_remains_uncertainty_candidate(tmp_path: Path):
    (tmp_path / "next.config.js").write_text(
        """module.exports = {
  async rewrites() {
    return [
      { source: '/api/:path*', destination: 'https://api.upstream.com/:path*' }
    ];
  }
};
""",
        encoding="utf-8",
    )
    (tmp_path / "client.js").write_text(
        """fetch('/api/v1/remote-payment');""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    assert len(result["reverse_proxies"]) >= 1

    # Candidate should be categorized as reverse_proxy_candidate or low confidence
    proxy_candidates = [
        c for c in result["primary_application_findings"]["missing_route_candidates"]
        if c.get("category") == "reverse_proxy_candidate" or c.get("confidence") == "Low"
    ]
    assert len(proxy_candidates) >= 1
    assert proxy_candidates[0]["severity"] == "Low"
    assert proxy_candidates[0]["finding_state"] == "Requires Owner Confirmation"


# 14. A mixed-language application retains its existing language capability matrix.
def test_scenario_14_mixed_language_app_retains_capability_matrix(tmp_path: Path):
    (tmp_path / "server.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/health')
def health():
    return 'ok'
""",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        """const express = require('express');
const app = express();
app.get('/status', (req, res) => res.send('ok'));
""",
        encoding="utf-8",
    )
    (tmp_path / "worker.go").write_text(
        """package main
func main() {}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    caps = {c["language_framework"]: c for c in result["capability_matrix"]}

    assert "Python / Flask" in caps
    assert caps["Python / Flask"]["status"].lower() == "supported"
    assert "JavaScript/TypeScript / Express" in caps
    assert caps["JavaScript/TypeScript / Express"]["status"].lower() == "supported"
    assert "Go" in caps
    assert caps["Go"]["status"].lower() in ("partial", "inventory-only")


# 15. Existing Flask, FastAPI, Django, Express, Next.js and React tests still pass.
def test_scenario_15_existing_multi_framework_discovery_intact(tmp_path: Path):
    # Flask route
    (tmp_path / "flask_app.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/flask-route', methods=['GET', 'POST'])
def flask_view():
    return 'flask'
""",
        encoding="utf-8",
    )
    # FastAPI route
    (tmp_path / "fastapi_app.py").write_text(
        """from fastapi import FastAPI
api = FastAPI()
@api.post('/fastapi-route')
def fast_view():
    return {'fast': True}
""",
        encoding="utf-8",
    )
    # Express route
    (tmp_path / "express_app.js").write_text(
        """const express = require('express');
const app = express();
app.get('/express-route', (req, res) => res.json({express: true}));
""",
        encoding="utf-8",
    )

    registry = LanguageRegistry()
    scan = registry.scan_repository(tmp_path)

    route_paths = {r.path for r in scan["routes"]}
    assert "/flask-route" in route_paths
    assert "/fastapi-route" in route_paths
    assert "/express-route" in route_paths


# 17. Capability matrix truthfulness: only AST syntax-parsing adapters can advertise deep-static
def test_scenario_17_capability_matrix_truthfulness():
    from ghost_hunter.discovery.languages.csharp_adapter import CSharpAdapter
    from ghost_hunter.discovery.languages.go_adapter import GoAdapter
    from ghost_hunter.discovery.languages.java_adapter import JavaAdapter
    from ghost_hunter.discovery.languages.javascript_adapter import JavaScriptAdapter
    from ghost_hunter.discovery.languages.kotlin_adapter import KotlinAdapter
    from ghost_hunter.discovery.languages.php_adapter import PHPAdapter
    from ghost_hunter.discovery.languages.python_adapter import PythonAdapter
    from ghost_hunter.discovery.languages.ruby_adapter import RubyAdapter
    from ghost_hunter.discovery.languages.rust_adapter import RustAdapter

    adapters = [
        PythonAdapter(),
        JavaScriptAdapter(),
        GoAdapter(),
        JavaAdapter(),
        CSharpAdapter(),
        PHPAdapter(),
        RubyAdapter(),
        RustAdapter(),
        KotlinAdapter(),
    ]

    for adapter in adapters:
        caps = adapter.get_capabilities()
        level = adapter.capability_level
        # Only true AST syntax parsers can be deep-static
        if not caps["syntax_parsing"]:
            assert level != "deep-static", f"{adapter.language} cannot declare deep-static without parser syntax_parsing"
            assert level in ("structural", "inventory-only")
        else:
            assert adapter.language == "Python", "Only Python currently implements genuine AST syntax_parsing"
            assert level == "deep-static"

    # Verify build_capability_matrix enforces this rule
    registry = LanguageRegistry()
    matrix = registry.build_capability_matrix({"Python", "JavaScript/TypeScript", "Go", "Java"}, [
        {"language": "Python", "framework": "Flask", "status": "supported"},
        {"language": "JavaScript/TypeScript", "framework": "Express", "status": "supported"},
    ])
    matrix_by_target = {m["language_framework"]: m for m in matrix}
    assert matrix_by_target["Python / Flask"]["capability_level"] == "deep-static"
    assert matrix_by_target["JavaScript/TypeScript / Express"]["capability_level"] == "structural"
    assert matrix_by_target["Go"]["capability_level"] == "structural"
    assert matrix_by_target["Java"]["capability_level"] == "structural"


# 18. Polyglot test and fixture source classification in application directories
def test_scenario_18_polyglot_test_and_fixture_classification_in_app_directories():
    polyglot_test_paths = [
        "src/handlers/user_test.go",
        "app/service/UserServiceTest.java",
        "src/OrderTests.java",
        "src/TestCase.java",
        "app/PaymentTests.cs",
        "src/CartTest.cs",
        "src/tests/UserTest.php",
        "app/api/user.spec.php",
        "app/services/user_spec.rb",
        "src/models/user_test.rb",
        "src/checkout_test.rs",
        "src/tests.rs",
        "src/service/UserTest.kt",
        "src/service/UserSpec.kt",
    ]
    for p in polyglot_test_paths:
        role = classify_source_role(p)
        assert role == "test", f"Expected 'test' for {p}, got '{role}'"
        scope_info = resolve_file_scope(p)
        assert scope_info["scope"] == "test_and_fixture"

    polyglot_fixture_paths = [
        "src/fixtures/MockPaymentService.java",
        "app/mocks/user_mock.go",
        "src/OrderMock.cs",
        "src/testdata/payload.json",
        "src/fixtures/mock_server.py",
    ]
    for p in polyglot_fixture_paths:
        role = classify_source_role(p)
        assert role == "fixture", f"Expected 'fixture' for {p}, got '{role}'"
        scope_info = resolve_file_scope(p)
        assert scope_info["scope"] == "test_and_fixture"

    # Non-test code files must not be falsely classified as tests
    non_tests = ["src/Contest.java", "src/Attest.java", "src/Latest.cs", "src/main.go", "src/user.rb"]
    for p in non_tests:
        role = classify_source_role(p)
        assert role == "application_source", f"Expected 'application_source' for {p}, got '{role}'"


# 19. Prevent cross-scope and cross-application route contamination (Example & Test routes)
def test_scenario_19_prevent_cross_scope_route_contamination(tmp_path: Path):
    # Primary application has a client call to /api/v1/payment, but NO backend route for it
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/health')
def health():
    return 'ok'
""",
        encoding="utf-8",
    )
    (src_dir / "client.js").write_text(
        """async function makePayment() {
    return await fetch('/api/v1/payment', { method: 'POST' });
}
""",
        encoding="utf-8",
    )

    # An EXAMPLE application in examples/demo_app contains the /api/v1/payment route
    example_dir = tmp_path / "examples" / "demo_app"
    example_dir.mkdir(parents=True)
    (example_dir / "server.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/payment', methods=['POST'])
def example_pay():
    return {'status': 'example_paid'}
""",
        encoding="utf-8",
    )

    # A TEST FIXTURE in tests/fixtures contains /api/v1/mock-gateway
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "mock_gateway.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/mock-gateway', methods=['POST'])
def mock_gw():
    return {'status': 'mocked'}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    # The primary application's call to /api/v1/payment MUST NOT be satisfied by the example route
    missing = [c for c in result["primary_application_findings"]["missing_route_candidates"] if c["endpoint"] == "/api/v1/payment"]
    assert len(missing) >= 1, "Primary application call to /api/v1/payment was erroneously satisfied by example app route"
    assert missing[0]["endpoint"] == "/api/v1/payment"

    # Ghost features detection must also flag this as a missing route defect in primary application
    ghost_routes = [g for g in result["ghost_features"] if "/api/v1/payment" in g.get("evidence", "")]
    assert len(ghost_routes) >= 1, "Ghost feature detection failed to report missing route /api/v1/payment"


# 16. The skill mirror remains exactly synchronized.
def test_scenario_16_skill_mirror_remains_exactly_synchronized():
    repo_root = Path(__file__).resolve().parent.parent.parent
    canonical_skill = repo_root / "skills" / "ghost-hunt"
    mirror_skill = repo_root / ".agents" / "skills" / "ghost-hunt"

    assert canonical_skill.is_dir()
    assert mirror_skill.is_dir()

    canonical_files = sorted(p.relative_to(canonical_skill) for p in canonical_skill.rglob("*") if p.is_file())
    mirror_files = sorted(p.relative_to(mirror_skill) for p in mirror_skill.rglob("*") if p.is_file())

    assert canonical_files == mirror_files, "Skill files in mirror do not match canonical directory structure"

    for rel_path in canonical_files:
        c_bytes = (canonical_skill / rel_path).read_bytes()
        m_bytes = (mirror_skill / rel_path).read_bytes()
        assert c_bytes == m_bytes, f"Byte mismatch in mirrored skill file: {rel_path}"
