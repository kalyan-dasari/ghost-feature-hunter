"""Code change review engine.

Reviews uncommitted, staged, branch, or commit changes and their surrounding call paths
for broken wiring, missing validation, error handling risks, security leaks, and test gaps.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.languages.models import RouteDefinition
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.project import IGNORED_DIRECTORIES, detect_project_context


@dataclass
class ReviewFinding:
    title: str
    category: str  # "wiring", "route_mismatch", "error_handling", "security", "testing_gap", "unfinished_code", "data_risk"
    severity: str  # "Critical", "High", "Medium", "Low"
    confidence: str  # "High", "Medium", "Low"
    current_behavior: str
    failure_scenario: str
    evidence: str
    file_path: str
    line_number: int
    root_cause: str
    recommended_fix: str
    impact: str
    false_positive_risk: str


def _get_git_diff(
    root: Path,
    target: str = "uncommitted",
    branch: str | None = None,
    commit: str | None = None,
    staged: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Retrieve git diff and parse modified files and line ranges."""
    cmd = ["git"]
    if commit:
        cmd.extend(["show", commit, "--patch"])
    elif branch:
        cmd.extend(["diff", f"{branch}...HEAD"])
    elif staged:
        cmd.extend(["diff", "--cached"])
    else:
        # Uncommitted (working tree + unstaged)
        cmd.extend(["diff", "HEAD"])

    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
        diff_output = proc.stdout
        if proc.returncode != 0 or not diff_output.strip():
            # Fallback to unstaged diff
            proc2 = subprocess.run(["git", "diff"], cwd=root, capture_output=True, text=True, check=False)
            diff_output = proc2.stdout
    except (FileNotFoundError, OSError):
        diff_output = ""

    # Parse diff into modified files
    changed_files: list[dict[str, Any]] = []
    current_file = None
    current_lines: list[int] = []

    file_header_re = re.compile(r"^diff --git a/(.*) b/(.*)")
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_output.splitlines():
        fm = file_header_re.match(line)
        if fm:
            if current_file:
                changed_files.append({"path": current_file, "lines": current_lines})
            current_file = fm.group(2)
            current_lines = []
            continue

        hm = hunk_header_re.match(line)
        if hm and current_file:
            start_line = int(hm.group(1))
            count = int(hm.group(2)) if hm.group(2) else 1
            current_lines.extend(range(start_line, start_line + count))

    if current_file:
        changed_files.append({"path": current_file, "lines": current_lines})

    return diff_output, changed_files


def run_code_review(
    project_root: Path,
    target: str = "uncommitted",
    branch: str | None = None,
    commit: str | None = None,
    staged: bool = False,
) -> dict[str, Any]:
    """Inspect changes and surrounding call graph for defects, gaps, and risks."""
    root = project_root.resolve()
    context = detect_project_context(root)
    registry = LanguageRegistry()
    scan_data = registry.scan_repository(root)

    diff_text, changed_files = _get_git_diff(
        root=root,
        target=target,
        branch=branch,
        commit=commit,
        staged=staged,
    )

    findings: list[ReviewFinding] = []

    # If no git diff was available (e.g. non-git workspace or no changes),
    # review changed or top application source files
    if not changed_files:
        app_files = [
            f for f in root.rglob("*")
            if f.is_file() and not any(p in IGNORED_DIRECTORIES for p in f.parts)
            and f.suffix.lower() in registry._extension_to_adapter
        ]
        for f in app_files[:20]:
            changed_files.append({"path": f.relative_to(root).as_posix(), "lines": []})

    changed_paths = {cf["path"] for cf in changed_files}

    # 1. Unfinished code touched or introduced
    for item in scan_data.get("unfinished", []):
        if item.source in changed_paths:
            findings.append(
                ReviewFinding(
                    title=f"Unfinished implementation in modified code: {item.name}",
                    category="unfinished_code",
                    severity="High" if item.confidence == "High" else "Medium",
                    confidence=item.confidence,
                    current_behavior=f"Code contains incomplete placeholder or stub: {item.evidence}",
                    failure_scenario="Executing this code path will fail or raise NotImplemented/panic at runtime.",
                    evidence=f"{item.source}:{item.line} -> {item.evidence}",
                    file_path=item.source,
                    line_number=item.line,
                    root_cause=f"Placeholder logic was left incomplete ({item.explanation}).",
                    recommended_fix="Implement the required business logic or provide a safe fallback return.",
                    impact="Users or callers hitting this path will experience unexpected runtime errors or stubs.",
                    false_positive_risk="Could be intentional abstract method or development WIP on an unreleased branch.",
                )
            )

    # 2. Hardcoded secret or credential exposure in changes
    secret_patterns = [
        (re.compile(r"""(?:api_key|apikey|secret|password|passwd|token)\s*=\s*['"]([a-zA-Z0-9_\-]{16,})['"]""", re.IGNORECASE), "hardcoded credential"),
        (re.compile(r"""(?:bearer\s+[a-zA-Z0-9_\-\.]{20,})""", re.IGNORECASE), "hardcoded bearer token"),
        (re.compile(r"""['"]ghp_[a-zA-Z0-9]{36}['"]"""), "GitHub personal access token"),
    ]

    for cf in changed_files:
        p = root / cf["path"]
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            for spattern, sdesc in secret_patterns:
                sm = spattern.search(line)
                if sm:
                    findings.append(
                        ReviewFinding(
                            title=f"Sensitive data exposure: {sdesc}",
                            category="security",
                            severity="Critical",
                            confidence="High",
                            current_behavior=f"Hardcoded sensitive credential in source code line {line_num}.",
                            failure_scenario="Credentials committed to version control can be leaked or harvested by unauthorized parties.",
                            evidence=f"{cf['path']}:{line_num} -> [REDACTED SECRET]",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="Secret was hardcoded directly instead of reading from environment variables or secrets manager.",
                            recommended_fix="Move sensitive values to environment variables (.env) or a secret manager.",
                            impact="Security compromise and unauthorized system or data access.",
                            false_positive_risk="Could be a dummy or mock token in a test fixture.",
                        )
                    )

    # 3. Disconnected client calls in modified files
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    known_route_paths = {r.path for r in routes}

    for call in scan_data.get("client_calls", []):
        if call.source in changed_paths:
            norm_call_path = call.path
            matched = any(
                norm_call_path == r.path or norm_call_path.rstrip("/") == r.path.rstrip("/")
                for r in routes
            )
            if not matched and not norm_call_path.startswith("http"):
                findings.append(
                    ReviewFinding(
                        title=f"Client API call points to unregistered endpoint: {norm_call_path}",
                        category="wiring",
                        severity="High",
                        confidence="Medium",
                        current_behavior=f"Modified client code makes a {call.method} request to '{norm_call_path}'.",
                        failure_scenario="Requests will receive HTTP 404 Not Found at runtime if the backend route is missing.",
                        evidence=f"{call.source}:{call.line} -> {call.raw}",
                        file_path=call.source,
                        line_number=call.line,
                        root_cause=f"Endpoint '{norm_call_path}' is not declared in any registered backend route handler.",
                        recommended_fix=f"Register route handler for '{norm_call_path}' or correct the client request URL.",
                        impact="Feature operation will fail when the user triggers this action.",
                        false_positive_risk="Endpoint may be provided by an external microservice or reverse proxy.",
                    )
                )

    # 4. Silent exception swallowing
    silent_catch_pattern = re.compile(r"""(?:except\s*.*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\})""")
    for cf in changed_files:
        p = root / cf["path"]
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_num, line in enumerate(content.splitlines(), 1):
            if silent_catch_pattern.search(line):
                findings.append(
                    ReviewFinding(
                        title="Silent exception swallowing in modified code",
                        category="error_handling",
                        severity="Medium",
                        confidence="High",
                        current_behavior=f"Exceptions are caught and discarded silently: {line.strip()}",
                        failure_scenario="Failures in this block will be hidden, causing corrupted application state without diagnostic logging.",
                        evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                        file_path=cf["path"],
                        line_number=line_num,
                        root_cause="Empty catch block or 'except: pass' without logging or recovery.",
                        recommended_fix="Log the exception with details or raise a specific domain error.",
                        impact="Bugs in downstream execution become impossible to trace.",
                        false_positive_risk="Intended benign ignore in cleanup or optional cache probe.",
                    )
                )

    # 5. Missing test coverage for newly declared or modified routes
    for r in routes:
        if r.source in changed_paths:
            # Check if route has test assertion coverage
            from ghost_hunter.discovery.audit import _evaluate_route_test_coverage
            test_files_data = []
            for tfile in root.rglob("*"):
                if tfile.is_file() and any(k in tfile.name.lower() for k in ("test", "spec")):
                    try:
                        test_files_data.append((tfile.relative_to(root).as_posix(), tfile.read_text(encoding="utf-8", errors="ignore")))
                    except OSError:
                        pass

            test_status = _evaluate_route_test_coverage(r, test_files_data)
            if test_status == "testing_gap_candidate":
                findings.append(
                    ReviewFinding(
                        title=f"Modified route lacks test coverage: {r.methods} {r.path}",
                        category="testing_gap",
                        severity="Medium",
                        confidence="Medium",
                        current_behavior=f"Route '{r.path}' handler '{r.function}' is modified without matching test coverage.",
                        failure_scenario="Regressions or broken behavior in this route will not be caught by existing test suites.",
                        evidence=f"{r.source}:{r.line} -> {r.raw_decorator or r.function}",
                        file_path=r.source,
                        line_number=r.line,
                        root_cause=f"No test file asserts on route path '{r.path}'.",
                        recommended_fix=f"Add unit or integration test asserting response behavior for {r.methods[0]} {r.path}.",
                        impact="Undetected regressions may reach production.",
                        false_positive_risk="Tests may use parameterized or dynamic URL builders.",
                    )
                )

    # Sort findings by severity
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 4), f.file_path, f.line_number))

    return {
        "project_context": context,
        "target": target,
        "branch": branch,
        "commit": commit,
        "staged": staged,
        "diff_length": len(diff_text),
        "changed_files_count": len(changed_files),
        "changed_files": [cf["path"] for cf in changed_files],
        "findings_count": len(findings),
        "findings": [asdict(f) for f in findings],
    }


def render_review_markdown(result: dict[str, Any]) -> str:
    """Render code review results in structured GitHub-flavored Markdown."""
    ctx = result.get("project_context", {})
    findings = result.get("findings", [])
    target = result.get("target", "uncommitted")

    lines = [
        "# Ghost Hunt — Code Change Review Report",
        "",
        "### Project Context Summary",
        f"- **Project Name:** `{ctx.get('project_name', 'Unknown')}`",
        f"- **Project Root:** `{ctx.get('project_root', '.')}`",
        f"- **Review Target:** `{target}` (staged={result.get('staged')})",
        f"- **Changed Files Analyzed:** `{result.get('changed_files_count', 0)}`",
        f"- **Findings Identified:** `{len(findings)}`",
        "",
        "---",
        "",
        "## Review Findings Summary",
        "",
    ]

    if not findings:
        lines.append("> **NO CRITICAL OR HIGH SEVERITY DEFECTS DETECTED** in the inspected changes.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Severity | Category | Finding | Location | Confidence |")
    lines.append("|---|---|---|---|---|")
    for f in findings:
        loc = f"`{f['file_path']}:{f['line_number']}`"
        lines.append(f"| **{f['severity']}** | `{f['category']}` | {f['title']} | {loc} | {f['confidence']} |")
    lines.append("")

    lines.append("## Detailed Findings")
    lines.append("")

    for idx, f in enumerate(findings, 1):
        lines.extend([
            f"### {idx}. [{f['severity']}] {f['title']}",
            f"- **File & Line:** `{f['file_path']}:{f['line_number']}`",
            f"- **Category:** `{f['category']}`",
            f"- **Confidence:** `{f['confidence']}`",
            "",
            f"**1. What the code currently does:**  \n{f['current_behavior']}",
            "",
            f"**2. What can go wrong:**  \n{f['failure_scenario']}",
            "",
            f"**3. Evidence:**  \n```\n{f['evidence']}\n```",
            "",
            f"**4. Root Cause:**  \n{f['root_cause']}",
            "",
            f"**5. Minimal Recommended Fix:**  \n{f['recommended_fix']}",
            "",
            f"**6. Impact if Unresolved:**  \n{f['impact']}",
            "",
            f"**7. False Positive Risk:**  \n{f['false_positive_risk']}",
            "",
            "---",
            "",
        ])

    return "\n".join(lines)
