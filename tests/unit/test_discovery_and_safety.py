import json
import sqlite3

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.adapters.database import DatabaseAdapter
from ghost_hunter.config import HunterConfig
from ghost_hunter.discovery.flask import discover_project
from ghost_hunter.models import Journey


def _journey(adapter, settings):
    return Journey(
        feature="safety",
        steps=[
            {
                "id": "check",
                "checkpoint": "Check behavior",
                "adapter": adapter,
                "expected_behavior": "Configured assertion holds",
                "settings": settings,
            }
        ],
    )


def test_discovery_parses_flask_without_executing_application(tmp_path):
    marker = tmp_path / "should-not-exist.txt"
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "app = Flask(__name__)\n"
        "@app.route('/orders/<int:order_id>', methods=['GET', 'POST'])\n"
        "def order(order_id): return {}\n"
        "@app.post('/checkout')\n"
        "def checkout(): return {}\n",
        encoding="utf-8",
    )
    (tmp_path / "test_orders.py").write_text("def test_order(): pass\n", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "shop.html").write_text("<button>Buy</button>", encoding="utf-8")

    result = discover_project(tmp_path)
    assert result["routes"][0]["path"] == "/orders/<int:order_id>"
    assert result["routes"][0]["methods"] == ["GET", "POST"]
    assert any(route["path"] == "/checkout" and route["methods"] == ["POST"] for route in result["routes"])
    assert result["tests"] == ["test_orders.py"]
    assert result["analysis_mode"] == "static"
    assert result["runtime_verified"] is False
    assert "templates/shop.html" in result["frontend_files"]
    assert not marker.exists()


def test_database_rejects_mutating_query_before_database_access(tmp_path):
    journey = _journey("database", {"query": "DELETE FROM orders", "checks": {"row_count_equals": 0}})
    result = DatabaseAdapter().verify(AdapterContext(tmp_path, HunterConfig()), journey, journey.steps[0])
    assert result.status == "UNKNOWN"
    assert "read-only SQL guard" in result.actual_observation


def test_database_rejects_unsupported_assertions(tmp_path):
    journey = _journey("database", {"query": "SELECT 1", "checks": {"rows_match": True}})
    result = DatabaseAdapter().verify(AdapterContext(tmp_path, HunterConfig()), journey, journey.steps[0])
    assert result.status == "UNKNOWN"
    assert "Unsupported database assertion" in result.actual_observation


def test_database_runs_bounded_select_with_standard_library_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "db with spaces" / "shop.sqlite3"
    db_path.parent.mkdir()
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO orders DEFAULT VALUES")
    monkeypatch.setenv("GHOST_HUNTER_DB", f"sqlite:///{db_path.as_posix()}")
    journey = _journey(
        "database",
        {
            "database_url_env": "GHOST_HUNTER_DB",
            "query": "SELECT id FROM orders",
            "checks": {"row_count_equals": 1},
        },
    )
    result = DatabaseAdapter().verify(AdapterContext(tmp_path, HunterConfig()), journey, journey.steps[0])
    assert result.status == "PASS", result.actual_observation
    assert result.evidence[0].details["row_count"] == 1


def test_database_authorizer_allows_string_literal_keywords(tmp_path, monkeypatch):
    db_path = tmp_path / "app.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, action TEXT)")
        connection.execute("INSERT INTO audit_logs (action) VALUES ('create')")
    monkeypatch.setenv("AUDIT_DB", f"sqlite:///{db_path.as_posix()}")
    journey = _journey(
        "database",
        {
            "database_url_env": "AUDIT_DB",
            "query": "SELECT id FROM audit_logs WHERE action = 'create'",
            "checks": {"row_count_equals": 1},
        },
    )
    result = DatabaseAdapter().verify(AdapterContext(tmp_path, HunterConfig()), journey, journey.steps[0])
    assert result.status == "PASS", result.actual_observation


def test_database_path_outside_allowed_roots_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("UNSAFE_DB", "sqlite:///C:/Windows/System32/sensitive.db")
    journey = _journey(
        "database",
        {
            "database_url_env": "UNSAFE_DB",
            "query": "SELECT 1",
            "checks": {"row_count_equals": 1},
        },
    )
    result = DatabaseAdapter().verify(
        AdapterContext(
            tmp_path,
            HunterConfig(environment="production", production_approved=True),
            approve_production=True,
        ),
        journey,
        journey.steps[0],
    )
    assert result.status == "UNKNOWN"
    assert "outside the allowed project directories" in result.actual_observation


def test_database_observation_is_blocked_for_production_without_approval(tmp_path):
    journey = _journey("database", {"query": "SELECT 1", "checks": {"row_count_equals": 1}})
    result = DatabaseAdapter().verify(
        AdapterContext(tmp_path, HunterConfig(environment="production", database_url_env="DB_URL")),
        journey,
        journey.steps[0],
    )
    assert result.status == "UNKNOWN"
    assert "Production database" in result.actual_observation


def test_browser_click_is_unknown_without_write_approval(tmp_path):
    from ghost_hunter.adapters.browser import BrowserAdapter, _allow_request, _origin

    journey = _journey(
        "browser",
        {
            "actions": [
                {"action": "click", "selector": "#submit"},
                {"action": "expect_text", "selector": "#status", "text": "saved"},
            ]
        },
    )
    result = BrowserAdapter().verify(AdapterContext(tmp_path, HunterConfig(base_url="http://localhost")), journey, journey.steps[0])
    assert result.status == "UNKNOWN"
    assert "write" in result.actual_observation
    base_origin = _origin("http://localhost:8000")
    assert _allow_request("http://localhost:8000/api", "GET", base_origin, False)
    assert not _allow_request("http://localhost:8000/api", "POST", base_origin, False)
    assert _allow_request("http://localhost:8000/api", "POST", base_origin, True)
    assert not _allow_request("http://other.test/api", "GET", base_origin, True)


def test_browser_navigation_without_assertion_is_unknown(tmp_path):
    from ghost_hunter.adapters.browser import BrowserAdapter

    journey = _journey("browser", {"actions": [{"action": "goto", "url": "/"}]})
    result = BrowserAdapter().verify(
        AdapterContext(tmp_path, HunterConfig(base_url="http://localhost")),
        journey,
        journey.steps[0],
    )
    assert result.status == "UNKNOWN"
    assert "explicit page or response assertion" in result.actual_observation
