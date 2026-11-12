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


def test_browser_worker_blocking_hang_is_terminated_within_bounded_time(tmp_path):
    from ghost_hunter.adapters.browser import BrowserAdapter
    import time

    journey = _journey(
        "browser",
        {
            "_simulate_blocking_hang": True,
            "timeout_seconds": 1.0,
            "actions": [
                {"action": "expect_text", "selector": "#title", "text": "Shop"},
            ],
        },
    )
    start_time = time.monotonic()
    result = BrowserAdapter().verify(
        AdapterContext(tmp_path, HunterConfig(base_url="http://localhost:8000")),
        journey,
        journey.steps[0],
    )
    duration = time.monotonic() - start_time

    assert result.status == "UNKNOWN"
    assert "exceeded hard deadline" in result.actual_observation
    assert "was terminated" in result.actual_observation
    assert duration < 4.0, f"Worker termination took too long: {duration}s"


def test_database_temp_dir_allowed_in_dev_and_test(tmp_path, monkeypatch):
    import tempfile
    from pathlib import Path

    temp_db = Path(tempfile.gettempdir()) / f"temp_test_hunter_{tmp_path.name}.sqlite3"
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE test_data (id INT)")
    conn.execute("INSERT INTO test_data VALUES (42)")
    conn.commit()
    conn.close()

    try:
        monkeypatch.setenv("TEMP_DB", f"sqlite:///{temp_db.as_posix()}")
        journey = _journey(
            "database",
            {"database_url_env": "TEMP_DB", "query": "SELECT id FROM test_data", "checks": {"row_count_equals": 1}},
        )
        res_test = DatabaseAdapter().verify(
            AdapterContext(tmp_path, HunterConfig(environment="test")),
            journey,
            journey.steps[0],
        )
        assert res_test.status == "PASS", res_test.actual_observation

        res_dev = DatabaseAdapter().verify(
            AdapterContext(tmp_path, HunterConfig(environment="development")),
            journey,
            journey.steps[0],
        )
        assert res_dev.status == "PASS", res_dev.actual_observation
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except OSError:
            pass


def test_database_temp_dir_rejected_in_production_and_staging(tmp_path, monkeypatch):
    import tempfile
    from pathlib import Path

    temp_db = Path(tempfile.gettempdir()) / f"temp_prod_hunter_{tmp_path.name}.sqlite3"
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE test_data (id INT)")
    conn.commit()
    conn.close()

    try:
        monkeypatch.setenv("TEMP_DB", f"sqlite:///{temp_db.as_posix()}")
        journey = _journey(
            "database",
            {"database_url_env": "TEMP_DB", "query": "SELECT 1", "checks": {"row_count_equals": 0}},
        )
        res_staging = DatabaseAdapter().verify(
            AdapterContext(tmp_path, HunterConfig(environment="staging")),
            journey,
            journey.steps[0],
        )
        assert res_staging.status == "UNKNOWN"
        assert "outside the allowed project directories" in res_staging.actual_observation

        res_prod = DatabaseAdapter().verify(
            AdapterContext(
                tmp_path,
                HunterConfig(environment="production", production_approved=True),
                approve_production=True,
            ),
            journey,
            journey.steps[0],
        )
        assert res_prod.status == "UNKNOWN"
        assert "outside the allowed project directories" in res_prod.actual_observation
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except OSError:
            pass


def test_database_allowed_database_dirs_config(tmp_path, monkeypatch):
    custom_dir = tmp_path.parent / "custom_dbs"
    custom_dir.mkdir(exist_ok=True)
    custom_db = custom_dir / "external.sqlite3"
    conn = sqlite3.connect(custom_db)
    conn.execute("CREATE TABLE ext_data (val TEXT)")
    conn.execute("INSERT INTO ext_data VALUES ('ok')")
    conn.commit()
    conn.close()

    try:
        monkeypatch.setenv("EXT_DB", f"sqlite:///{custom_db.as_posix()}")
        journey = _journey(
            "database",
            {"database_url_env": "EXT_DB", "query": "SELECT val FROM ext_data", "checks": {"row_count_equals": 1}},
        )

        # In staging environment, temp dirs are not allowed, so only project_root and allowed_database_dirs apply
        # Without allowed_database_dirs -> rejected
        res_rejected = DatabaseAdapter().verify(
            AdapterContext(tmp_path, HunterConfig(environment="staging", allowed_database_dirs=[])),
            journey,
            journey.steps[0],
        )
        assert res_rejected.status == "UNKNOWN"
        assert "outside the allowed project directories" in res_rejected.actual_observation

        # With allowed_database_dirs -> accepted
        res_accepted = DatabaseAdapter().verify(
            AdapterContext(
                tmp_path,
                HunterConfig(environment="staging", allowed_database_dirs=[str(custom_dir)]),
            ),
            journey,
            journey.steps[0],
        )
        assert res_accepted.status == "PASS", res_accepted.actual_observation
    finally:
        try:
            custom_db.unlink(missing_ok=True)
        except OSError:
            pass


def test_database_directory_traversal_rejected(tmp_path, monkeypatch):
    from pathlib import Path

    traversal_db = tmp_path / "subdir" / ".." / ".." / "traversal.sqlite3"
    monkeypatch.setenv("TRAVERSAL_DB", f"sqlite:///{traversal_db.as_posix()}")
    journey = _journey(
        "database",
        {"database_url_env": "TRAVERSAL_DB", "query": "SELECT 1", "checks": {"row_count_equals": 1}},
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


def test_database_symlink_escape_rejected(tmp_path, monkeypatch):
    import os
    import pytest
    from pathlib import Path

    outside_dir = tmp_path.parent / "symlink_outside_db_dir"
    outside_dir.mkdir(exist_ok=True)
    outside_db = outside_dir / "secret.sqlite3"
    with sqlite3.connect(outside_db) as conn:
        conn.execute("CREATE TABLE secret (val TEXT)")

    symlink_in_project = tmp_path / "symlink_db.sqlite3"
    try:
        os.symlink(str(outside_db), str(symlink_in_project))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated privileges on this environment")

    monkeypatch.setenv("SYMLINK_DB", f"sqlite:///{symlink_in_project.as_posix()}")
    journey = _journey(
        "database",
        {"database_url_env": "SYMLINK_DB", "query": "SELECT 1", "checks": {"row_count_equals": 1}},
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

