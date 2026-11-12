import importlib.util
import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.config import HunterConfig
from ghost_hunter.journeys.loader import load_journey
from ghost_hunter.runner import run_journey

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "examples" / "broken-flask-shop"


def _load_demo_app(monkeypatch, database_path):
    monkeypatch.setenv("GHOST_SHOP_DB", str(database_path))
    spec = importlib.util.spec_from_file_location("ghost_hunter_broken_shop", DEMO / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.create_app(database_path)


def _manifest_score(manifest, results):
    by_id = {
        result.checkpoint_id: getattr(result.status, "value", result.status)
        for result in results
    }
    defect_ids = [
        checkpoint_id
        for defect in manifest["defects"]
        for checkpoint_id in defect["checkpoint_ids"]
    ]
    control_ids = manifest["control_checkpoint_ids"]
    return {
        "true_positives": sum(by_id.get(checkpoint_id) == "FAIL" for checkpoint_id in defect_ids),
        "false_negatives": sum(by_id.get(checkpoint_id) == "PASS" for checkpoint_id in defect_ids),
        "unresolved_defects": sum(by_id.get(checkpoint_id) == "UNKNOWN" for checkpoint_id in defect_ids),
        "false_positives": sum(by_id.get(checkpoint_id) == "FAIL" for checkpoint_id in control_ids),
        "true_negatives": sum(by_id.get(checkpoint_id) == "PASS" for checkpoint_id in control_ids),
        "statuses": by_id,
    }


def test_demo_journey_detects_injected_defects_without_manifest_guidance(tmp_path, monkeypatch):
    db_path = tmp_path / "shop.sqlite3"
    app = _load_demo_app(monkeypatch, db_path)
    app.config.update(TESTING=True)
    database_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("GHOST_SHOP_DATABASE_URL", database_url)
    journey = load_journey(DEMO / "journeys" / "checkout.json")
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = AdapterContext(
        project_root=DEMO,
        config=HunterConfig(
            environment="test",
            base_url=f"http://127.0.0.1:{server.server_port}",
            allow_writes=True,
            database_url_env="GHOST_SHOP_DATABASE_URL",
        ),
        allow_writes=True,
    )

    try:
        # The runner receives only the journey and adapters. The manifest is read after execution for scoring.
        results = run_journey(context, journey)
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    manifest = json.loads((DEMO / "benchmark-manifest.json").read_text(encoding="utf-8"))
    scores = _manifest_score(manifest, results)

    from ghost_hunter.adapters.browser import probe_playwright
    has_browser = probe_playwright()

    assert len(manifest["defects"]) == 15
    if has_browser:
        assert scores["true_positives"] == 15, scores
        assert scores["unresolved_defects"] == 0, scores
    else:
        assert scores["true_positives"] == 14, scores
        assert scores["unresolved_defects"] == 1, scores
    assert scores["false_positives"] == 0, scores
    assert scores["true_negatives"] == 4, scores
    assert scores["false_negatives"] == 0, scores


def test_benchmark_metric_counts_known_statuses_separately():
    class Result:
        def __init__(self, checkpoint_id, status):
            self.checkpoint_id = checkpoint_id
            self.status = status

    manifest = {
        "defects": [{"checkpoint_ids": ["broken-a", "broken-b"]}],
        "control_checkpoint_ids": ["clean-a"],
    }
    scores = _manifest_score(
        manifest,
        [Result("broken-a", "FAIL"), Result("broken-b", "UNKNOWN"), Result("clean-a", "PASS")],
    )
    assert scores["true_positives"] == 1
    assert scores["false_negatives"] == 0
    assert scores["unresolved_defects"] == 1
    assert scores["false_positives"] == 0
    assert scores["true_negatives"] == 1
