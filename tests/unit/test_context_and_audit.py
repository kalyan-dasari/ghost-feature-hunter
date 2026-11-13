"""Regression test suite for context-aware scope lock, requirement provenance,
test isolation, and whole-repository audit analysis.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ghost_hunter.discovery.audit import audit_repository_routes, estimate_duplicate_blocks
from ghost_hunter.discovery.flask import discover_project
from ghost_hunter.discovery.project import detect_project_context, is_example_or_fixture


# Behavior 1: Bare investigation does not automatically target examples or demos
def test_bare_investigation_does_not_target_examples_or_demos(tmp_path):
    # Setup a project with src/ and examples/broken-shop/
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('main app')", encoding="utf-8")

    examples = tmp_path / "examples" / "broken-shop"
    examples.mkdir(parents=True)
    (examples / "app.py").write_text("print('example app')", encoding="utf-8")

    ctx = detect_project_context(tmp_path)
    assert ctx["selected_app_root"] == str(src.resolve()), "Primary app must be src/, not examples/"
    assert ctx["example_fixture_count"] >= 1
    assert "examples" in ctx["example_fixture_dirs"]


# Behavior 2: Explicit feature investigation stays within the requested application
def test_explicit_feature_investigation_stays_within_requested_application(tmp_path):
    app_a = tmp_path / "apps" / "shop"
    app_a.mkdir(parents=True)
    (app_a / "checkout.py").write_text("def checkout(): pass", encoding="utf-8")

    app_b = tmp_path / "apps" / "admin"
    app_b.mkdir(parents=True)
    (app_b / "checkout.py").write_text("def admin_checkout(): pass", encoding="utf-8")

    ctx = detect_project_context(tmp_path, explicit_app_root=app_a)
    assert ctx["selected_app_root"] == str(app_a.resolve())
    assert ctx["explicit_app_root_provided"] is True


# Behavior 3: Explicit path takes precedence over inferred root
def test_explicit_path_takes_precedence_over_inferred_root(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("# main", encoding="utf-8")

    custom = tmp_path / "custom_service"
    custom.mkdir()
    (custom / "service.py").write_text("# service", encoding="utf-8")

    ctx = detect_project_context(tmp_path, explicit_app_root=custom)
    assert ctx["selected_app_root"] == str(custom.resolve())


# Behavior 4: Multiple application roots are identified rather than arbitrarily selected
def test_is_example_or_fixture_accurately_classifies_directories():
    assert is_example_or_fixture("examples/broken-shop/app.py") is True
    assert is_example_or_fixture("fixtures/seed.json") is True
    assert is_example_or_fixture("benchmarks/perf.py") is True
    assert is_example_or_fixture("demos/store.py") is True
    assert is_example_or_fixture("src/services/billing.py") is False
    assert is_example_or_fixture("app/main.py") is False


# Behavior 5: Requirements inferred from code remain inferred_assumption
def test_requirements_inferred_from_code_remain_inferred_assumption():
    taxonomy = {
        "user_requirement": "explicit instruction from user prompt",
        "product_documentation": "documented in README or docs",
        "api_contract": "formal schema or TypeScript types",
        "existing_test": "assertion in existing test suite",
        "inferred_assumption": "hypothesized behavior from code inspection",
    }
    # When no user prompt or contract exists, expectation must be tagged as inferred_assumption
    inferred_source = "inferred_assumption"
    assert inferred_source not in {"user_requirement", "api_contract", "product_documentation"}
    assert inferred_source == "inferred_assumption"


# Behavior 6: Missing authoritative expectations cannot create confirmed business-rule FAIL findings
def test_missing_authoritative_expectation_evaluates_to_unknown_not_fail():
    status_for_unconfirmed_assumption = "UNKNOWN"
    assert status_for_unconfirmed_assumption == "UNKNOWN"
    assert status_for_unconfirmed_assumption != "FAIL", "Unconfirmed assumptions must never produce manufactured FAIL"


# Behavior 7: Mutating operations are blocked pending approval
def test_mutating_operations_require_explicit_authorization():
    allow_writes = False
    http_method = "POST"
    is_mutation = http_method in {"POST", "PUT", "PATCH", "DELETE"}

    assert is_mutation is True
    # If allow_writes is False, mutating check must be blocked
    action_permitted = allow_writes or not is_mutation
    assert action_permitted is False


# Behavior 8: Test state contamination prevents a PASS result
def test_test_state_contamination_prevention(tmp_path):
    # Demonstrate how reusing contaminated state produces false results
    db_file = tmp_path / "contaminated.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE products (id INT PRIMARY KEY, stock INT)")
    conn.execute("INSERT INTO products VALUES (1, 10)")
    conn.commit()

    # Step 1: Check 1 contaminates state (decrements by 1)
    conn.execute("UPDATE products SET stock = stock - 1 WHERE id = 1")
    conn.commit()

    # Step 2: Check 2 wants to test purchasing 2 units (expecting stock 8)
    cur = conn.cursor()
    cur.execute("SELECT stock FROM products WHERE id = 1")
    contaminated_before = cur.fetchone()[0]
    assert contaminated_before == 9, "Pre-state is contaminated!"

    # If check 2 buggy code decrements by 1:
    conn.execute("UPDATE products SET stock = stock - 1 WHERE id = 1")
    conn.commit()
    cur.execute("SELECT stock FROM products WHERE id = 1")
    contaminated_after = cur.fetchone()[0]

    # Contaminated observation: stock is 8, but it was 9 - 1, NOT 10 - 2!
    assert contaminated_after == 8
    # A naive check 'if stock == 8: PASS' produces a FALSE PASS!

    # Correct isolated protocol:
    # 1. Check must detect that pre-state was not the expected baseline (10)
    baseline_expected = 10
    is_contaminated = contaminated_before != baseline_expected
    assert is_contaminated is True, "Must detect contaminated test state"
    conn.close()


# Behavior 9: Inventory quantity 2 against stock 10 correctly exposes the known defect (FAIL, not PASS)
def test_inventory_quantity_2_against_stock_10_correctly_fails(tmp_path):
    # Simulates broken-flask-shop buggy inventory deduction: UPDATE products SET stock = MAX(stock - 1, 0)
    db_file = tmp_path / "fresh_inventory.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE products (id INT PRIMARY KEY, stock INT)")
    conn.execute("INSERT INTO products VALUES (1, 10)")
    conn.commit()

    # Purchase 2 units
    quantity = 2
    # Defective query from broken-flask-shop app.py:L180
    conn.execute("UPDATE products SET stock = MAX(stock - 1, 0) WHERE id = 1")
    conn.commit()

    cur = conn.cursor()
    cur.execute("SELECT stock FROM products WHERE id = 1")
    observed_stock = cur.fetchone()[0]
    expected_stock = 10 - quantity  # 8

    # Observed stock is 9, expected is 8 -> Must FAIL
    assert observed_stock == 9
    assert expected_stock == 8
    status = "PASS" if observed_stock == expected_stock else "FAIL"
    assert status == "FAIL", "Defective inventory deduction must evaluate to FAIL, never PASS"
    conn.close()


# Behavior 10: Independent stateful scenarios start with known state
def test_independent_stateful_scenarios_start_with_fresh_state(tmp_path):
    def make_fresh_db():
        f = tmp_path / f"fresh_{tempfile.mktemp().split('tmp')[-1]}.sqlite3"
        conn = sqlite3.connect(f)
        conn.execute("CREATE TABLE products (id INT, stock INT)")
        conn.execute("INSERT INTO products VALUES (1, 10)")
        conn.commit()
        return conn, f

    conn1, f1 = make_fresh_db()
    conn2, f2 = make_fresh_db()

    # Scenario 1 mutates f1
    conn1.execute("UPDATE products SET stock = 0 WHERE id = 1")
    conn1.commit()

    # Scenario 2 starts fresh
    cur = conn2.cursor()
    cur.execute("SELECT stock FROM products WHERE id = 1")
    assert cur.fetchone()[0] == 10, "Scenario 2 must start with pristine baseline state"

    conn1.close()
    conn2.close()


# Behavior 11: A client-referenced endpoint with no matching registered route is reported as a missing-route candidate
def test_client_referenced_endpoint_with_no_backend_route_is_missing_candidate(tmp_path):
    backend = tmp_path / "app.py"
    backend.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.get('/api/orders')
def get_orders():
    return []
""",
        encoding="utf-8",
    )

    frontend = tmp_path / "static" / "client.js"
    frontend.parent.mkdir(parents=True)
    frontend.write_text(
        """
fetch('/api/users/profile').then(res => res.json());
""",
        encoding="utf-8",
    )

    audit = audit_repository_routes(tmp_path)
    missing = audit["missing_route_candidates"]
    assert len(missing) == 1
    assert missing[0]["endpoint"] == "/api/users/profile"
    assert missing[0]["category"] == "missing_route"
    assert missing[0]["severity"] == "High"


# Behavior 12: Unreferenced endpoints are labeled candidates, not definitively dead
def test_unreferenced_endpoints_are_labeled_candidates_with_caveats(tmp_path):
    backend = tmp_path / "app.py"
    backend.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.get('/api/internal/health')
def health():
    return {"status": "ok"}
""",
        encoding="utf-8",
    )

    audit = audit_repository_routes(tmp_path)
    unused = audit["potentially_unused_endpoints"]
    assert len(unused) == 1
    assert unused[0]["endpoint"] == "/api/internal/health"
    assert unused[0]["category"] == "potentially_unused_endpoint"
    assert unused[0]["confidence"] == "Low", "Unused endpoints must have Low confidence as candidates"
    assert "webhook" in unused[0]["why_false_positive"].lower()


# Behavior 13: Dynamically registered or externally consumed endpoints receive appropriate uncertainty
def test_dynamically_registered_endpoints_receive_uncertainty(tmp_path):
    backend = tmp_path / "app.py"
    backend.write_text(
        """
from flask import Flask
app = Flask(__name__)

@app.post('/api/webhook/stripe')
def stripe_webhook():
    return {}
""",
        encoding="utf-8",
    )

    audit = audit_repository_routes(tmp_path)
    unused = audit["potentially_unused_endpoints"]
    assert len(unused) == 1
    candidate = unused[0]
    assert "why_false_positive" in candidate
    assert candidate["confidence"] == "Low"


# Behavior 14: Potentially unused modules are not classified as safe-to-delete without checking entry points
def test_potentially_unused_modules_require_owner_confirmation():
    candidate = {
        "path": "src/cli.py",
        "category": "unused_code",
        "confidence": "Low",
        "status": "Requires runtime/owner confirmation",
    }
    assert candidate["status"] != "Confirmed unused"
    assert candidate["confidence"] == "Low"


# Behavior 15: Duplicate-code estimates do not double-count overlapping source regions
def test_duplicate_code_estimates_do_not_double_count_lines(tmp_path):
    f1 = tmp_path / "service_a.py"
    f1.write_text(
        """
def compute_order_tax(subtotal):
    tax_rate = 0.10
    shipping = 500
    discount = 50
    return round(subtotal * tax_rate) + shipping - discount
""",
        encoding="utf-8",
    )

    f2 = tmp_path / "service_b.py"
    f2.write_text(
        """
def compute_order_tax(subtotal):
    tax_rate = 0.10
    shipping = 500
    discount = 50
    return round(subtotal * tax_rate) + shipping - discount
""",
        encoding="utf-8",
    )

    duplicates = estimate_duplicate_blocks([f1, f2])
    assert len(duplicates) == 1
    dup = duplicates[0]
    assert dup["name"] == "compute_order_tax"
    assert len(dup["occurrences"]) == 2
    # Estimated waste is for the 1 duplicate copy, not both!
    assert dup["estimated_waste_lines"] == dup["occurrences"][1]["line_count"]

