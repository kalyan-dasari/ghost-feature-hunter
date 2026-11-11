import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest
from werkzeug.serving import make_server

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.adapters.browser import BrowserAdapter
from ghost_hunter.adapters.http import HTTPAdapter
from ghost_hunter.config import HunterConfig
from ghost_hunter.models import Journey

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "examples" / "broken-flask-shop"


def test_live_api_and_real_browser_journey_against_isolated_demo(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    database_path = tmp_path / "live-shop.sqlite3"
    monkeypatch.setenv("GHOST_SHOP_DB", str(database_path))
    spec = importlib.util.spec_from_file_location("ghost_hunter_live_shop", DEMO / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    application = module.create_app(database_path)
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            response = httpx.get(f"{base_url}/api/products", timeout=2)
        except httpx.RequestError as exc:
            pytest.skip(f"This execution environment blocks loopback HTTP: {type(exc).__name__}")
        assert response.status_code == 200

        api_journey = Journey(
            feature="live-shop",
            steps=[
                {
                    "id": "products-api",
                    "checkpoint": "Product API returns a product",
                    "adapter": "http",
                    "expected_behavior": "GET /api/products returns a product named Trail Socks",
                    "settings": {"method": "GET", "url": "/api/products", "checks": {"status_code": 200, "json_equals": {"0.name": "Trail Socks"}}},
                }
            ],
        )
        config = HunterConfig(environment="test", base_url=base_url, allow_writes=True)
        context = AdapterContext(tmp_path, config, allow_writes=True)
        api_result = HTTPAdapter().verify(context, api_journey, api_journey.steps[0])
        assert api_result.status == "PASS", api_result.actual_observation

        cli_project = tmp_path / "cli-project"
        (cli_project / "journeys").mkdir(parents=True)
        (cli_project / "ghost-hunter.json").write_text(
            json.dumps(
                {
                    "environment": "test",
                    "base_url": base_url,
                    "allow_writes": False,
                    "report_dir": "reports",
                }
            ),
            encoding="utf-8",
        )
        (cli_project / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "@app.get('/status')\n"
            "def status(): return {'ok': True}\n",
            encoding="utf-8",
        )
        (cli_project / "journeys" / "products.json").write_text(
            json.dumps(api_journey.model_dump(mode="json")), encoding="utf-8"
        )
        child_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "PROGRAMDATA",
                "PYTHONPATH",
                "PLAYWRIGHT_BROWSERS_PATH",
            }
        }
        discover_process = subprocess.run(
            [sys.executable, "-m", "ghost_hunter.cli", "discover", "--project-root", str(cli_project)],
            cwd=cli_project,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert discover_process.returncode == 0, discover_process.stderr
        discovery = json.loads((cli_project / "reports" / "ghost-discovery.json").read_text(encoding="utf-8"))
        assert discovery["routes"][0]["path"] == "/status"
        audit_process = subprocess.run(
            [sys.executable, "-m", "ghost_hunter.cli", "audit", "products", "--project-root", str(cli_project)],
            cwd=cli_project,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert audit_process.returncode == 0, audit_process.stderr
        cli_report = json.loads((cli_project / "reports" / "ghost-report.json").read_text(encoding="utf-8"))
        assert cli_report["summary"]["pass_count"] == 1
        markdown_process = subprocess.run(
            [
                sys.executable,
                "-m",
                "ghost_hunter.cli",
                "report",
                str(cli_project / "reports" / "ghost-report.json"),
                "--output",
                str(cli_project / "reports" / "from-cli.md"),
            ],
            cwd=cli_project,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert markdown_process.returncode == 0, markdown_process.stderr
        assert (cli_project / "reports" / "from-cli.md").exists()

        demo_cli_project = tmp_path / "demo-cli-project"
        shutil.copytree(
            DEMO,
            demo_cli_project,
            ignore=shutil.ignore_patterns("__pycache__", "instance", "ghost-reports"),
        )
        demo_config_path = demo_cli_project / "ghost-hunter.json"
        demo_config = json.loads(demo_config_path.read_text(encoding="utf-8"))
        demo_config.update({"base_url": base_url, "allow_writes": True, "report_dir": "reports"})
        demo_config_path.write_text(json.dumps(demo_config, indent=2), encoding="utf-8")
        demo_env = dict(child_env)
        demo_env["GHOST_SHOP_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        discovery_process = subprocess.run(
            [sys.executable, "-m", "ghost_hunter.cli", "discover", "--project-root", str(demo_cli_project)],
            cwd=demo_cli_project,
            env=demo_env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert discovery_process.returncode == 0, discovery_process.stderr
        demo_discovery = json.loads((demo_cli_project / "reports" / "ghost-discovery.json").read_text(encoding="utf-8"))
        assert any(route["path"] == "/api/checkout" for route in demo_discovery["routes"])
        demo_audit_process = subprocess.run(
            [
                sys.executable,
                "-m",
                "ghost_hunter.cli",
                "audit",
                "checkout",
                "--project-root",
                str(demo_cli_project),
                "--allow-writes",
            ],
            cwd=demo_cli_project,
            env=demo_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert demo_audit_process.returncode == 1, demo_audit_process.stderr
        demo_report = json.loads((demo_cli_project / "reports" / "ghost-report.json").read_text(encoding="utf-8"))
        assert demo_report["summary"] == {"total": 19, "pass_count": 4, "fail_count": 15, "unknown_count": 0}

        browser_journey = Journey(
            feature="live-shop",
            steps=[
                {
                    "id": "stale-order-state",
                    "checkpoint": "Checkout updates the confirmation state",
                    "adapter": "browser",
                    "expected_behavior": "Checkout confirmation displays the newly returned order id",
                    "settings": {
                        "actions": [
                            {"action": "goto", "url": "/"},
                            {"action": "click", "selector": "#checkout-button", "wait_for_response": "/api/checkout", "response_status": 201},
                            {"action": "wait_for_network_idle"},
                            {"action": "expect_text", "selector": "#order-state", "text": "Order #"},
                        ]
                    },
                }
            ],
        )
        browser_result = BrowserAdapter().verify(context, browser_journey, browser_journey.steps[0])
        assert browser_result.status == "FAIL", browser_result.actual_observation
        assert browser_result.evidence
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_browser_blocks_page_script_post_without_write_approval(tmp_path):
    pytest.importorskip("playwright")
    from flask import Flask

    app = Flask(__name__)
    state = {"writes": 0}

    @app.get("/")
    def index():
        return (
            "<p id='status'>ready</p>"
            "<script>fetch('/mutate', {method: 'POST'}).catch(() => {});</script>"
        )

    @app.post("/mutate")
    def mutate():
        state["writes"] += 1
        return "written"

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    journey = Journey(
        feature="browser-safety",
        steps=[
            {
                "id": "page-script-write",
                "checkpoint": "Page loads without an unapproved POST",
                "adapter": "browser",
                "expected_behavior": "The page is observable and its POST request is blocked",
                "settings": {
                    "actions": [
                        {"action": "goto", "url": "/"},
                        {"action": "expect_text", "selector": "#status", "text": "ready"},
                    ]
                },
            }
        ],
    )
    try:
        result = BrowserAdapter().verify(
            AdapterContext(
                tmp_path,
                HunterConfig(environment="test", base_url=base_url, timeout_seconds=30),
            ),
            journey,
            journey.steps[0],
        )
        assert result.status == "PASS", result.actual_observation
        assert state["writes"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
