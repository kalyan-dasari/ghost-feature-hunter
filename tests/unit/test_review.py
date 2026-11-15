"""Unit tests for the Ghost Hunt review engine and CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from ghost_hunter.review import render_review_markdown, run_code_review


def test_review_detects_unfinished_code_and_secret_leak(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text(
        """def process_payment():
    api_key = "dummy_secret_token_abcdef123456"
    pass
""",
        encoding="utf-8",
    )

    review_result = run_code_review(tmp_path)
    findings = review_result["findings"]

    # Check that findings contain required 7 fields
    assert len(findings) >= 1
    for f in findings:
        assert "current_behavior" in f
        assert "failure_scenario" in f
        assert "evidence" in f
        assert "root_cause" in f
        assert "recommended_fix" in f
        assert "impact" in f
        assert "false_positive_risk" in f
        assert f["severity"] in ("Critical", "High", "Medium", "Low")
        assert f["confidence"] in ("High", "Medium", "Low")

    # Verify secret leak was identified as Critical
    secret_findings = [f for f in findings if f["category"] == "security"]
    assert len(secret_findings) >= 1
    assert secret_findings[0]["severity"] == "Critical"
    assert "[REDACTED SECRET]" in secret_findings[0]["evidence"]


def test_review_markdown_rendering(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        """def run():
    try:
        do_work()
    except Exception:
        pass
""",
        encoding="utf-8",
    )

    review_result = run_code_review(tmp_path)
    md = render_review_markdown(review_result)

    assert "# Ghost Hunt — Code Change Review Report" in md
    assert "### Project Context Summary" in md
    assert "## Detailed Findings" in md
    assert "What the code currently does" in md
    assert "What can go wrong" in md
    assert "Evidence" in md
    assert "Root Cause" in md
    assert "Minimal Recommended Fix" in md
    assert "Impact if Unresolved" in md
    assert "False Positive Risk" in md


def test_review_git_clean_working_tree_returns_no_changes(tmp_path: Path):
    import subprocess
    from typer.testing import CliRunner
    from ghost_hunter.cli import app

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def index():\n    return 'ok'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    # Review working tree when clean
    result = run_code_review(tmp_path)
    assert result["changed_files_count"] == 0
    assert result["changed_files"] == []
    assert result["findings_count"] == 0
    assert "No changes to review" in result["message"]

    # Test via CLI
    runner = CliRunner()
    cli_res = runner.invoke(app, ["review", "-p", str(tmp_path)])
    assert cli_res.exit_code == 0
    assert "No changes to review" in cli_res.output


def test_review_git_untracked_source_file_detection(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def index():\n    return 'ok'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    # Add untracked source file with an unfinished stub
    (src / "untracked_payment.py").write_text(
        "def process():\n    pass\n",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    assert result["changed_files_count"] == 1
    assert "src/untracked_payment.py" in result["changed_files"]
    assert result["findings_count"] >= 1
    assert any(f["category"] == "unfinished_code" for f in result["findings"])


def test_review_separates_pre_existing_risks_from_introduced_findings(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    # Initial commit has a pre-existing unfinished stub at line 2
    (src / "worker.py").write_text(
        "def old_task():\n    pass\n\ndef calculate():\n    return 42\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit with old pass"], cwd=tmp_path, check=True, capture_output=True)

    # Now modify ONLY the calculate function at line 5 to introduce a secret
    (src / "worker.py").write_text(
        "def old_task():\n    pass\n\ndef calculate():\n    token = 'dummy_secret_token_abcdef123456'\n    return 42\n",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    assert result["changed_files_count"] == 1

    # Finding on modified line must be in findings (introduced defect)
    secret_findings = [f for f in result["findings"] if f["category"] == "security"]
    assert len(secret_findings) >= 1
    assert secret_findings[0]["line_number"] == 5

    # Issue on unchanged line (pass on line 2, function at line 1) must be in pre_existing_risks
    pre_existing_unfinished = [f for f in result["pre_existing_risks"] if f["category"] == "unfinished_code"]
    assert len(pre_existing_unfinished) >= 1
    assert pre_existing_unfinished[0]["line_number"] == 1

    # And NOT present in the introduced findings list
    assert not any(f["category"] == "unfinished_code" for f in result["findings"])


def test_review_parameter_aware_route_matching(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "server.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/users/<int:user_id>')
def get_user(user_id):
    return {'id': user_id}
""",
        encoding="utf-8",
    )
    (src / "client.js").write_text(
        """async function fetchUser() {
    return await fetch('/api/v1/users/42');
}
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    # The client call to /api/v1/users/42 matches /api/v1/users/<int:user_id>
    # So there should be NO disconnected wiring finding for /api/v1/users/42
    wiring_findings = [f for f in result["findings"] if f["category"] == "wiring"]
    assert len(wiring_findings) == 0


def test_review_route_method_mismatch(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "server.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/api/v1/orders', methods=['GET'])
def get_orders():
    return []
""",
        encoding="utf-8",
    )
    (src / "client.js").write_text(
        """async function createOrder(data) {
    return await fetch('/api/v1/orders', { method: 'POST', body: JSON.stringify(data) });
}
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    mismatch_findings = [f for f in result["findings"] if f["category"] == "route_mismatch"]
    assert len(mismatch_findings) >= 1
    assert "POST" in mismatch_findings[0]["title"]
    assert mismatch_findings[0]["severity"] == "High"


def test_review_missing_auth_on_sensitive_route(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "admin.py").write_text(
        """from flask import Flask
app = Flask(__name__)
@app.route('/admin/delete-database', methods=['POST'])
def purge_all():
    return {'status': 'purged'}
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    auth_findings = [f for f in result["findings"] if f["category"] == "security" and "authorization" in f["title"].lower()]
    assert len(auth_findings) >= 1
    assert "/admin/delete-database" in auth_findings[0]["title"]


def test_review_unvalidated_input_injection(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "query.py").write_text(
        """def find_user(user_input):
    cursor.execute(f"SELECT * FROM users WHERE id = '{user_input}'")
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    injection_findings = [f for f in result["findings"] if "Injection risk" in f["title"]]
    assert len(injection_findings) >= 1
    assert injection_findings[0]["severity"] == "Critical"


def test_review_multiple_db_mutations_without_transaction(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "order_service.py").write_text(
        """def checkout(order, item):
    db.session.add(order)
    db.session.add(item)
    db.session.commit()
""",
        encoding="utf-8",
    )

    result = run_code_review(tmp_path)
    data_risk_findings = [f for f in result["findings"] if f["category"] == "data_risk"]
    assert len(data_risk_findings) >= 1
    assert "transaction" in data_risk_findings[0]["title"].lower()


def test_review_cli_runner_modes(tmp_path: Path):
    import subprocess
    from typer.testing import CliRunner
    from ghost_hunter.cli import app

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    # Modify app.py and stage it
    (src / "app.py").write_text(
        "def run():\n    api_key = 'dummy_secret_token_abcdef123456'\n    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    runner = CliRunner()

    # Mode 1: review --staged
    res_staged = runner.invoke(app, ["review", "--staged", "-p", str(tmp_path)])
    assert res_staged.exit_code == 0
    assert "Sensitive data exposure" in res_staged.output

    # Mode 2: review staged (positional)
    res_pos_staged = runner.invoke(app, ["review", "staged", "-p", str(tmp_path)])
    assert res_pos_staged.exit_code == 0
    assert "Sensitive data exposure" in res_pos_staged.output

    # Mode 3: review --json
    res_json = runner.invoke(app, ["review", "--staged", "-p", str(tmp_path), "--json"])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.output)
    assert parsed["findings_count"] >= 1

    # Mode 4: review --output
    out_file = tmp_path / "review_report.md"
    res_out = runner.invoke(app, ["review", "--staged", "-p", str(tmp_path), "-o", str(out_file)])
    assert res_out.exit_code == 0
    assert out_file.is_file()
    assert "Ghost Hunt — Code Change Review Report" in out_file.read_text(encoding="utf-8")

