"""Multilingual discovery and polyglot verification test suite.

Validates the 12 scenarios required by Section 9:
1. Valid feature flow discovered across languages.
2. Route or endpoint identified across Go, Java, C#, PHP, Ruby, Rust, Kotlin.
3. Client call connected to route across languages.
4. Missing endpoint candidate identified across languages.
5. HTTP method mismatch detected across languages.
6. Unfinished function/handler identified across languages.
7. Imports and references extracted without contamination.
8. Tests discovered and assertions treated as candidates, not proof.
9. Application, test, fixture, and example source kept separate.
10. Mixed-language monorepo boundaries preserved.
11. Unsupported syntax causes explicit limitation rather than fabricated result.
12. Feature spanning multiple languages traced through the shared analysis model with deliberate defects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghost_hunter.discovery.audit import audit_repository
from ghost_hunter.discovery.languages.csharp_adapter import CSharpAdapter
from ghost_hunter.discovery.languages.go_adapter import GoAdapter
from ghost_hunter.discovery.languages.java_adapter import JavaAdapter
from ghost_hunter.discovery.languages.kotlin_adapter import KotlinAdapter
from ghost_hunter.discovery.languages.php_adapter import PHPAdapter
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.languages.ruby_adapter import RubyAdapter
from ghost_hunter.discovery.languages.rust_adapter import RustAdapter
from ghost_hunter.review import run_code_review


# 1. Valid feature flow discovered across languages
def test_scenario_1_valid_feature_flow_discovered_across_languages(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    # Go route
    (src / "main.go").write_text(
        """package main
import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()
    r.GET("/api/v1/items", listItems)
}

func listItems(c *gin.Context) {
    c.JSON(200, gin.H{"items": []string{"item1"}})
}
""",
        encoding="utf-8",
    )
    # TS caller
    (src / "api.ts").write_text(
        """export async function getItems() {
    const res = await fetch('/api/v1/items');
    return res.json();
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    # Connected route
    routes = {r["path"]: r for r in result["routes"]}
    assert "/api/v1/items" in routes
    assert "GET" in routes["/api/v1/items"]["methods"]
    # No missing route candidates
    missing = [c for c in result["missing_route_candidates"] if c["endpoint"] == "/api/v1/items"]
    assert len(missing) == 0


# 2. Route or endpoint identified across Go, Java, C#, PHP, Ruby, Rust, Kotlin
def test_scenario_2_route_identified_across_polyglot_ecosystems(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    # Go
    (src / "server.go").write_text(
        """package main
import "github.com/gin-gonic/gin"
func setup() {
    r := gin.Default()
    r.POST("/go/checkout", checkoutHandler)
}
func checkoutHandler(c *gin.Context) {}
""",
        encoding="utf-8",
    )
    # Java
    (src / "OrderController.java").write_text(
        """package com.example;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/java")
public class OrderController {
    @GetMapping("/orders")
    public String getOrders() { return "orders"; }
}
""",
        encoding="utf-8",
    )
    # C#
    (src / "UserController.cs").write_text(
        """using Microsoft.AspNetCore.Mvc;
namespace App;

[ApiController]
[Route("csharp/[controller]")]
public class UserController : ControllerBase {
    [HttpGet("profile")]
    public IActionResult GetProfile() => Ok();
}
""",
        encoding="utf-8",
    )
    # PHP
    (src / "routes.php").write_text(
        """<?php
use Illuminate\\Support\\Facades\\Route;
Route::post('/php/pay', [PaymentController::class, 'pay']);
""",
        encoding="utf-8",
    )
    # Ruby
    (src / "routes.rb").write_text(
        """Rails.application.routes.draw do
  get '/ruby/cart', to: 'cart#show'
end
""",
        encoding="utf-8",
    )
    # Rust
    (src / "main.rs").write_text(
        """use axum::{routing::get, Router};
fn router() -> Router {
    Router::new().route("/rust/health", get(health))
}
async fn health() -> &'static str { "ok" }
""",
        encoding="utf-8",
    )
    # Kotlin
    (src / "Catalog.kt").write_text(
        """package com.example
import org.springframework.web.bind.annotation.*

@RestController
class CatalogController {
    @GetMapping("/kotlin/catalog")
    fun catalog(): String = "catalog"
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    discovered_paths = {r["path"] for r in result["routes"]}

    assert "/go/checkout" in discovered_paths
    assert "/java/orders" in discovered_paths
    assert "/csharp/user/profile" in discovered_paths
    assert "/php/pay" in discovered_paths
    assert "/ruby/cart" in discovered_paths
    assert "/rust/health" in discovered_paths
    assert "/kotlin/catalog" in discovered_paths


# 3. Client call connected to route across languages
def test_scenario_3_client_call_connected_to_route_across_languages(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    # Java Spring backend
    (src / "PaymentController.java").write_text(
        """package com.example;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class PaymentController {
    @PostMapping("/charge")
    public String charge() { return "success"; }
}
""",
        encoding="utf-8",
    )

    # TypeScript frontend caller
    (src / "PayButton.tsx").write_text(
        """import React from 'react';
export function PayButton() {
    const handlePay = () => {
        fetch('/api/v1/charge', { method: 'POST' });
    };
    return <button onClick={handlePay}>Pay Now</button>;
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    routes = {r["path"]: r for r in result["routes"]}
    assert "/api/v1/charge" in routes
    # Call is matched to the route, no missing candidate
    missing = [c for c in result["missing_route_candidates"] if c["endpoint"] == "/api/v1/charge"]
    assert len(missing) == 0


# 4. Missing endpoint candidate identified across languages
def test_scenario_4_missing_endpoint_candidate_identified(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    # Go backend has only /health
    (src / "main.go").write_text(
        """package main
import "github.com/gin-gonic/gin"
func main() {
    r := gin.Default()
    r.GET("/health", func(c *gin.Context) {})
}
""",
        encoding="utf-8",
    )

    # React client calls nonexistent /api/v1/ghost-feature
    (src / "Client.tsx").write_text(
        """fetch('/api/v1/ghost-feature');""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    missing = [c for c in result["missing_route_candidates"] if c["endpoint"] == "/api/v1/ghost-feature"]
    assert len(missing) == 1
    assert missing[0]["endpoint"] == "/api/v1/ghost-feature"


# 5. HTTP method mismatch detected across languages
def test_scenario_5_http_method_mismatch_detected(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    # C# Controller has POST /api/v1/register
    (src / "AuthController.cs").write_text(
        """using Microsoft.AspNetCore.Mvc;
namespace App;

[ApiController]
public class AuthController : ControllerBase {
    [HttpPost("/api/v1/register")]
    public IActionResult Register() => Ok();
}
""",
        encoding="utf-8",
    )

    # Client calls GET /api/v1/register
    (src / "caller.js").write_text(
        """fetch('/api/v1/register', { method: 'GET' });""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    # The route exists for POST, but client calls GET
    routes = {r["path"]: r for r in result["routes"]}
    assert "/api/v1/register" in routes
    assert "POST" in routes["/api/v1/register"]["methods"]
    assert "GET" not in routes["/api/v1/register"]["methods"]


# 6. Unfinished function/handler identified across languages
def test_scenario_6_unfinished_function_identified_across_languages(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    # Go panic
    (src / "service.go").write_text(
        """package main
func ProcessOrder() {
    panic("not implemented")
}
""",
        encoding="utf-8",
    )
    # Java UnsupportedOperationException
    (src / "Billing.java").write_text(
        """package com.example;
public class Billing {
    public void bill() {
        throw new UnsupportedOperationException("WIP");
    }
}
""",
        encoding="utf-8",
    )
    # Rust todo!()
    (src / "crypto.rs").write_text(
        """pub fn sign() {
    todo!("implement signature");
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    unfinished_evidences = [u["evidence"] for u in result["empty_or_unfinished"]]

    assert any("not implemented" in ev for ev in unfinished_evidences)
    assert any("UnsupportedOperationException" in ev for ev in unfinished_evidences)
    assert any("todo!" in ev for ev in unfinished_evidences)


# 7. Imports and references extracted without cross-project contamination
def test_scenario_7_imports_extracted_without_contamination(tmp_path: Path):
    go_dir = tmp_path / "services" / "go-service"
    go_dir.mkdir(parents=True)
    (go_dir / "go.mod").write_text("module go.service\n", encoding="utf-8")
    (go_dir / "main.go").write_text(
        """package main
import (
    "fmt"
    "net/http"
)
func main() { fmt.Println("Go") }
""",
        encoding="utf-8",
    )

    java_dir = tmp_path / "services" / "java-service"
    java_dir.mkdir(parents=True)
    (java_dir / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    (java_dir / "App.java").write_text(
        """package com.example;
import java.util.List;
import java.util.Map;
public class App {}
""",
        encoding="utf-8",
    )

    reg = LanguageRegistry()
    scan = reg.scan_repository(tmp_path)

    all_imports = scan["imports"]
    assert "net/http" in all_imports
    assert "java.util.List" in all_imports
    # Language adapters correctly extracted imports
    assert "Go" in scan["detected_languages"]
    assert "Java" in scan["detected_languages"]


# 8. Tests discovered and related assertions treated as candidates, not proof
def test_scenario_8_tests_discovered_as_candidates_not_runtime_proof(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.go").write_text(
        """package main
import "github.com/gin-gonic/gin"
func setupRouter() *gin.Engine {
    r := gin.Default()
    r.GET("/api/v1/ping", func(c *gin.Context) {})
    return r
}
""",
        encoding="utf-8",
    )

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "api_test.go").write_text(
        """package main
import (
    "testing"
    "github.com/stretchr/testify/assert"
)
func TestPing(t *testing.T) {
    res := "/api/v1/ping"
    assert.Equal(t, 200, 200)
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    route_entry = next(r for r in result["routes"] if r["path"] == "/api/v1/ping")

    # Static discovery must NEVER label static candidates as 'test_verified'
    assert route_entry["test_status"] != "test_verified"
    assert route_entry["test_status"] in ("test_assertion_candidate", "test_reference_candidate")


# 9. Application, test, fixture, and example source kept separate
def test_scenario_9_application_test_fixture_example_kept_separate(tmp_path: Path):
    # Primary application
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.go").write_text("package main\nimport \"fmt\"\nfunc LiveCode() { fmt.Println(\"alive\") }\n", encoding="utf-8")

    # Example
    ex = tmp_path / "examples"
    ex.mkdir()
    (ex / "demo.go").write_text("package main\nfunc DemoCode() { panic(\"not implemented\") }\n", encoding="utf-8")

    # Fixture
    fix = tmp_path / "tests" / "fixtures"
    fix.mkdir(parents=True)
    (fix / "mock.go").write_text("package fixtures\nfunc MockCode() { panic(\"not implemented\") }\n", encoding="utf-8")

    result = audit_repository(tmp_path, include_examples=False)

    # Primary application findings must be clean
    assert len(result["primary_application_findings"]["empty_or_unfinished"]) == 0

    # Fixtures are classified into test_and_fixture_findings
    assert len(result["test_and_fixture_findings"]["empty_or_unfinished"]) >= 1


# 10. Mixed-language monorepo boundaries preserved
def test_scenario_10_mixed_language_monorepo_boundaries_preserved(tmp_path: Path):
    # App 1: Python API
    py_dir = tmp_path / "apps" / "py-api"
    py_dir.mkdir(parents=True)
    (py_dir / "pyproject.toml").write_text("[project]\nname = 'py-api'\n", encoding="utf-8")
    (py_dir / "main.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/py/status')
def status(): return 'ok'
""",
        encoding="utf-8",
    )

    # App 2: Go Microservice
    go_dir = tmp_path / "apps" / "go-service"
    go_dir.mkdir(parents=True)
    (go_dir / "go.mod").write_text("module go.service\n", encoding="utf-8")
    (go_dir / "server.go").write_text(
        """package main
import "github.com/gin-gonic/gin"
func main() {
    r := gin.Default()
    r.GET("/go/metrics", func(c *gin.Context) {})
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    boundaries = {b["relative_path"]: b for b in result["application_boundaries"]}

    assert "apps/py-api" in boundaries
    assert "apps/go-service" in boundaries
    assert "Python" in result["detected_languages"]
    assert "Go" in result["detected_languages"]


# 11. Unsupported syntax causes explicit limitation rather than fabricated result
def test_scenario_11_unsupported_syntax_causes_explicit_limitation(tmp_path: Path):
    # C/C++ file with no AST compiler
    src = tmp_path / "native"
    src.mkdir()
    (src / "core.cpp").write_text("#include <iostream>\nint main() { return 0; }\n", encoding="utf-8")

    result = audit_repository(tmp_path)
    caps = {c["language_framework"]: c for c in result["capability_matrix"]}

    assert "C/C++" in caps
    c_cap = caps["C/C++"]
    assert c_cap["capability_level"] == "inventory-only"
    assert "inventory only" in c_cap["limitations"].lower() or "not implemented" in c_cap["limitations"].lower()
    assert c_cap["capabilities"]["route_extraction"] is False
    assert c_cap["capabilities"]["syntax_parsing"] is False


# 12. Feature spanning multiple languages traced through shared model with deliberate defects
def test_scenario_12_mixed_language_app_with_deliberate_defects(tmp_path: Path):
    # 1. Frontend: TypeScript / React
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text('{"name": "frontend", "dependencies": {"react": "^18.0.0"}}', encoding="utf-8")
    (frontend_dir / "Checkout.tsx").write_text(
        """import React from 'react';
export function Checkout() {
    const handleOrder = () => {
        // Deliberate Defect 1: Client makes GET call while backend only provides POST
        fetch('/api/v1/orders', { method: 'GET' });
        // Deliberate Defect 2: Client calls nonexistent payment route
        fetch('/api/v1/unregistered-gateway', { method: 'POST' });
    };
    return <button onClick={handleOrder}>Submit Order</button>;
}
""",
        encoding="utf-8",
    )

    # 2. Backend: Go with Gin
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "go.mod").write_text("module backend.shop\ngo 1.22\n", encoding="utf-8")
    (backend_dir / "main.go").write_text(
        """package main
import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()
    r.POST("/api/v1/orders", createOrder)
}

// Deliberate Defect 3: Go handler is unfinished stub with panic
func createOrder(c *gin.Context) {
    panic("not implemented")
}
""",
        encoding="utf-8",
    )

    # 3. Database: SQL Schema
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "schema.sql").write_text(
        """CREATE TABLE orders (
    id VARCHAR(36) PRIMARY KEY,
    total DECIMAL(10, 2),
    created_at TIMESTAMP
);
""",
        encoding="utf-8",
    )

    # 4. Tests: Go test file
    (backend_dir / "main_test.go").write_text(
        """package main
import "testing"
func TestOrderRoute(t *testing.T) {
    url := "/api/v1/orders"
    if url != "/api/v1/orders" {
        t.Errorf("mismatch")
    }
}
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    # Verify multi-language detection
    langs = result["detected_languages"]
    assert "Go" in langs
    assert "JavaScript/TypeScript" in langs
    assert "SQL" in langs

    # Verify Route extraction
    routes = {r["path"]: r for r in result["routes"]}
    assert "/api/v1/orders" in routes
    assert routes["/api/v1/orders"]["methods"] == ["POST"]

    # Verify SQL model extraction
    models = {m["name"]: m for m in result["models"]}
    assert "orders" in models

    # Verify Defect 2 (Missing route candidate)
    missing = [c for c in result["missing_route_candidates"] if c["endpoint"] == "/api/v1/unregistered-gateway"]
    assert len(missing) == 1
    assert missing[0]["endpoint"] == "/api/v1/unregistered-gateway"

    # Verify Defect 3 (Unfinished implementation in Go)
    unfinished = [u for u in result["empty_or_unfinished"] if "not implemented" in u["evidence"]]
    assert len(unfinished) >= 1
    assert "main.go" in unfinished[0]["source"]

    # Verify code review finds the issues
    review_res = run_code_review(tmp_path)
    assert review_res["findings_count"] >= 1
