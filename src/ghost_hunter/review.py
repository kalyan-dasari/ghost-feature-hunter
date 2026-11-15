"""Code change review engine.

Reviews uncommitted, staged, branch, or commit changes and their surrounding call paths
for broken wiring, route and method mismatches, missing validation, authorization risks,
error handling risks, data loss risks, security leaks, and test gaps.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ghost_hunter.discovery.ghost_features import match_route
from ghost_hunter.discovery.languages.models import RouteDefinition
from ghost_hunter.discovery.languages.registry import LanguageRegistry
from ghost_hunter.discovery.project import (
    IGNORED_DIRECTORIES,
    classify_source_role,
    detect_project_context,
)


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
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Retrieve git diff and parse modified files and line ranges.

    Returns:
        (is_git_repo, diff_text, changed_files)
    """
    # 1. Check if inside git repo
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        is_git_repo = proc.returncode == 0 and proc.stdout.strip() == "true"
    except (FileNotFoundError, OSError):
        is_git_repo = False

    if not is_git_repo:
        # Non-git folder: inspect application source files
        changed_files: list[dict[str, Any]] = []
        for f in sorted(root.rglob("*")):
            if f.is_file() and not any(p in IGNORED_DIRECTORIES for p in f.parts):
                rel = f.relative_to(root).as_posix()
                role = classify_source_role(rel, root)
                if role in ("application_source", "test", "configuration"):
                    try:
                        num_lines = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                    except OSError:
                        num_lines = 1
                    changed_files.append({"path": rel, "lines": list(range(1, num_lines + 1))})
        return False, "", changed_files

    # 2. Resolve target for git repo
    effective_target = target or "uncommitted"
    if staged or effective_target == "staged":
        staged = True
        cmd = ["git", "diff", "--cached"]
    elif commit:
        cmd = ["git", "show", commit, "--patch"]
    elif branch:
        cmd = ["git", "diff", f"{branch}...HEAD"]
    elif effective_target not in ("uncommitted", "staged"):
        if re.match(r"^[0-9a-fA-F]{7,40}$", effective_target):
            commit = effective_target
            cmd = ["git", "show", commit, "--patch"]
        else:
            branch = effective_target
            cmd = ["git", "diff", f"{branch}...HEAD"]
    else:
        # Default uncommitted: working tree vs HEAD
        cmd = ["git", "diff", "HEAD"]

    diff_output = ""
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
        diff_output = proc.stdout
        # Fallback to unstaged git diff if HEAD diff was empty
        if not diff_output.strip() and effective_target == "uncommitted" and not staged and not branch and not commit:
            proc2 = subprocess.run(["git", "diff"], cwd=root, capture_output=True, text=True, check=False)
            if proc2.stdout.strip():
                diff_output = proc2.stdout
    except (FileNotFoundError, OSError):
        diff_output = ""

    # Parse diff into modified files with exact added line numbers
    changed_files = []
    current_file = None
    current_lines: list[int] = []
    cur_line_num = 0

    file_header_re = re.compile(r"^diff --git a/(.*) b/(.*)")
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_output.splitlines():
        fm = file_header_re.match(line)
        if fm:
            if current_file:
                changed_files.append({"path": current_file, "lines": sorted(set(current_lines))})
            current_file = fm.group(2)
            current_lines = []
            cur_line_num = 0
            continue

        hm = hunk_header_re.match(line)
        if hm and current_file:
            cur_line_num = int(hm.group(1))
            continue

        if current_file and cur_line_num > 0:
            if line.startswith("+") and not line.startswith("+++"):
                current_lines.append(cur_line_num)
                cur_line_num += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass
            else:
                cur_line_num += 1

    if current_file:
        changed_files.append({"path": current_file, "lines": sorted(set(current_lines))})

    # 3. If reviewing working tree (uncommitted and not staged), detect untracked new source files
    if effective_target == "uncommitted" and not staged and not branch and not commit:
        try:
            status_proc = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            for sline in status_proc.stdout.splitlines():
                if sline.startswith("?? "):
                    untracked_rel = sline[3:].strip().strip('"')
                    upath = root / untracked_rel
                    if upath.is_file() and not any(p in IGNORED_DIRECTORIES for p in upath.parts):
                        role = classify_source_role(untracked_rel, root)
                        if role in ("application_source", "test", "configuration"):
                            try:
                                count = len(upath.read_text(encoding="utf-8", errors="ignore").splitlines())
                            except OSError:
                                count = 1
                            changed_files.append({"path": untracked_rel, "lines": list(range(1, count + 1))})
        except (FileNotFoundError, OSError):
            pass

    return is_git_repo, diff_output, changed_files


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

    is_git_repo, diff_text, changed_files = _get_git_diff(
        root=root,
        target=target,
        branch=branch,
        commit=commit,
        staged=staged,
    )

    # When there are no changes to review, state clearly and return empty result
    if not changed_files:
        return {
            "project_context": context,
            "target": target,
            "branch": branch,
            "commit": commit,
            "staged": staged,
            "diff_length": 0,
            "changed_files_count": 0,
            "changed_files": [],
            "findings_count": 0,
            "findings": [],
            "pre_existing_risks_count": 0,
            "pre_existing_risks": [],
            "message": "No changes to review. Working tree / target diff is clean.",
        }

    findings: list[ReviewFinding] = []
    pre_existing_risks: list[ReviewFinding] = []

    changed_paths = {cf["path"] for cf in changed_files}
    changed_lines_by_file: dict[str, set[int]] = {cf["path"]: set(cf["lines"]) for cf in changed_files}

    def record_finding(f: ReviewFinding):
        file_lines = changed_lines_by_file.get(f.file_path, set())
        if not file_lines or f.line_number in file_lines:
            findings.append(f)
        else:
            pre_existing_risks.append(f)

    # 1. Unfinished code touched or introduced
    for item in scan_data.get("unfinished", []):
        if item.source in changed_paths:
            record_finding(
                ReviewFinding(
                    title=f"Unfinished implementation: {item.name}",
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
                if spattern.search(line):
                    record_finding(
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

    # 3. Disconnected client calls in modified files (parameter-aware matching)
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    valid_routes = [r for r in routes if r.source_role == "application_source"]

    for call in scan_data.get("client_calls", []):
        if call.source in changed_paths:
            norm_call_path = call.path
            if norm_call_path.startswith(("http://", "https://", "//")):
                continue
            matched = any(match_route(norm_call_path, r.path) for r in valid_routes)
            if not matched:
                record_finding(
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

    # 4. Route and HTTP method mismatch
    for call in scan_data.get("client_calls", []):
        if call.source in changed_paths:
            norm_call_path = call.path
            if norm_call_path.startswith(("http://", "https://", "//")):
                continue
            matching = [r for r in valid_routes if match_route(norm_call_path, r.path)]
            if matching:
                supported_methods = {m.upper() for r in matching for m in r.methods}
                req_method = call.method.upper()
                if "ALL" not in supported_methods and req_method not in supported_methods:
                    record_finding(
                        ReviewFinding(
                            title=f"HTTP method mismatch on route '{norm_call_path}': client sends {req_method}",
                            category="route_mismatch",
                            severity="High",
                            confidence="High",
                            current_behavior=f"Client calls {req_method} on '{norm_call_path}', but matching backend route only supports {sorted(supported_methods)}.",
                            failure_scenario=f"HTTP request will fail with HTTP 405 Method Not Allowed.",
                            evidence=f"{call.source}:{call.line} -> {call.raw} (backend supports: {sorted(supported_methods)})",
                            file_path=call.source,
                            line_number=call.line,
                            root_cause=f"Route handler was registered with {sorted(supported_methods)}, but client requests {req_method}.",
                            recommended_fix=f"Add '{req_method}' to route handler methods or change client request method to match.",
                            impact="Client cannot complete operation due to HTTP 405 error.",
                            false_positive_risk="Method may be converted by an upstream gateway or middleware.",
                        )
                    )

    # 5. Missing authorization on sensitive route boundaries
    auth_decorator_pattern = re.compile(
        r"""(?i)@(login_required|roles_accepted|requires_auth|auth|authorize|PreAuthorize|Secured)|"""
        r"""\b(?:Depends\s*\([^)]*current_user|verify_token|require_admin|is_authenticated|check_permission|authMiddleware|before_action\s+:authenticate)\b"""
    )
    for r in routes:
        if r.source in changed_paths:
            is_sensitive = any(term in r.path.lower() for term in ("/admin", "/manage", "/secure", "/delete", "/payment", "/accounts", "/billing", "/users/delete"))
            is_destructive = any(m.upper() in ("DELETE", "PUT", "PATCH") for m in r.methods) and any(term in r.path.lower() for term in ("/user", "/account", "/order", "/payment", "/item"))
            if is_sensitive or is_destructive:
                p = root / r.source
                content = ""
                if p.is_file():
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        pass
                lines = content.splitlines()
                start_l = max(0, r.line - 15)
                end_l = min(len(lines), r.line + 25)
                route_context = "\n".join(lines[start_l:end_l])
                if not auth_decorator_pattern.search(r.raw_decorator or "") and not auth_decorator_pattern.search(route_context):
                    record_finding(
                        ReviewFinding(
                            title=f"Missing authorization on sensitive route: {r.methods} {r.path}",
                            category="security",
                            severity="High",
                            confidence="Medium",
                            current_behavior=f"Privileged or state-mutating route '{r.path}' does not declare an authorization check or auth middleware.",
                            failure_scenario="Unauthenticated callers or unauthorized users can invoke this privileged endpoint.",
                            evidence=f"{r.source}:{r.line} -> {r.raw_decorator or r.function}",
                            file_path=r.source,
                            line_number=r.line,
                            root_cause="Route handler lacks authentication/authorization decorator or middleware enforcement.",
                            recommended_fix=f"Apply authentication and role-based authorization check (e.g. @login_required, @roles_accepted) to '{r.path}'.",
                            impact="Privilege escalation or unauthorized access to sensitive functionality.",
                            false_positive_risk="Auth check may be enforced globally in application-level middleware.",
                        )
                    )

    # 6. Unvalidated user input directly interpolated into SQL or commands
    injection_patterns = [
        (re.compile(r"""(?:cursor\.execute|\.execute)\s*\(\s*f(?:"[^"\n]*(?:SELECT|INSERT|UPDATE|DELETE)[^"\n]*\{|'[^'\n]*(?:SELECT|INSERT|UPDATE|DELETE)[^'\n]*\{)""", re.IGNORECASE), "raw SQL query with f-string interpolation"),
        (re.compile(r"""(?:os\.system|subprocess\.(?:Popen|call|run))\s*\(\s*f(?:"[^"\n]*\{|'[^'\n]*\{)"""), "shell command execution with unvalidated f-string interpolation"),
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
            for ipattern, idesc in injection_patterns:
                if ipattern.search(line):
                    record_finding(
                        ReviewFinding(
                            title=f"Injection risk: {idesc}",
                            category="security",
                            severity="Critical",
                            confidence="High",
                            current_behavior=f"Unsanitized string interpolation in SQL or system command execution: {line.strip()}",
                            failure_scenario="External input can alter query syntax or execute arbitrary system commands.",
                            evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="SQL query or command was constructed with raw string formatting instead of parameterized arguments.",
                            recommended_fix="Use parameterized queries (e.g. cursor.execute(query, (params,))) or safe subprocess arguments.",
                            impact="Critical data breach or remote code execution.",
                            false_positive_risk="Interpolated values may be compile-time constants or internally trusted variables.",
                        )
                    )

    # 7. Silent exception swallowing
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
                record_finding(
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

    # 8. Mutating database operations without transaction boundary
    db_mutation_re = re.compile(r"""\b(?:db\.session\.(?:add|delete|commit)|objects\.(?:create|delete|update)|repository\.(?:save|delete))\b""")
    transaction_wrapper_re = re.compile(r"""\b(?:transaction\.atomic|db\.session\.begin|@transactional|TransactionScope)\b""")
    for cf in changed_files:
        p = root / cf["path"]
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = content.splitlines()
        mutation_lines = [idx + 1 for idx, l in enumerate(lines) if db_mutation_re.search(l)]
        if len(mutation_lines) >= 2 and not transaction_wrapper_re.search(content):
            record_finding(
                ReviewFinding(
                    title="Multiple database mutations without transaction boundary",
                    category="data_risk",
                    severity="Medium",
                    confidence="Medium",
                    current_behavior="Multiple database mutating operations occur without an atomic transaction boundary.",
                    failure_scenario="If an intermediate write fails or crashes, partial data is committed, corrupting database consistency.",
                    evidence=f"{cf['path']}:{mutation_lines[0]} -> {lines[mutation_lines[0]-1].strip()}",
                    file_path=cf["path"],
                    line_number=mutation_lines[0],
                    root_cause="Mutations are executed sequentially without an atomic transaction wrapper or rollback handler.",
                    recommended_fix="Wrap multiple database mutations in an atomic transaction block (e.g. 'with transaction.atomic():').",
                    impact="Partial state commitment and database inconsistency.",
                    false_positive_risk="Framework or session may have auto-commit/transaction middleware configured.",
                )
            )

    # 9. Missing test coverage for newly declared or modified routes
    from ghost_hunter.discovery.audit import _evaluate_route_test_coverage
    test_files_data = []
    for tfile in root.rglob("*"):
        if tfile.is_file() and not any(p in IGNORED_DIRECTORIES for p in tfile.parts):
            role = classify_source_role(tfile.relative_to(root).as_posix(), root)
            if role in ("test", "fixture"):
                try:
                    test_files_data.append((tfile.relative_to(root).as_posix(), tfile.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    pass

    for r in routes:
        if r.source in changed_paths:
            test_status = _evaluate_route_test_coverage(r, test_files_data)
            if test_status == "testing_gap_candidate":
                record_finding(
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

    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 4), f.file_path, f.line_number))
    pre_existing_risks.sort(key=lambda f: (severity_order.get(f.severity, 4), f.file_path, f.line_number))

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
        "pre_existing_risks_count": len(pre_existing_risks),
        "pre_existing_risks": [asdict(f) for f in pre_existing_risks],
    }


def render_review_markdown(result: dict[str, Any]) -> str:
    """Render code review results in structured GitHub-flavored Markdown."""
    ctx = result.get("project_context", {})
    findings = result.get("findings", [])
    pre_existing = result.get("pre_existing_risks", [])
    target = result.get("target", "uncommitted")
    changed_count = result.get("changed_files_count", 0)

    lines = [
        "# Ghost Hunt — Code Change Review Report",
        "",
        "### Project Context Summary",
        f"- **Project Name:** `{ctx.get('project_name', 'Unknown')}`",
        f"- **Project Root:** `{ctx.get('project_root', '.')}`",
        f"- **Review Target:** `{target}` (staged={result.get('staged')})",
        f"- **Changed Files Analyzed:** `{changed_count}`",
        f"- **Introduced Findings:** `{len(findings)}`",
        f"- **Pre-Existing Risks in Surrounding Code:** `{len(pre_existing)}`",
        "",
        "---",
        "",
    ]

    if changed_count == 0:
        lines.append("> **No changes to review.** Working tree / target diff is clean.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Review Findings Summary")
    lines.append("")

    if not findings:
        lines.append("> **NO CRITICAL OR HIGH SEVERITY DEFECTS DETECTED** in the inspected changes.")
        lines.append("")
    else:
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

    if pre_existing:
        lines.append("## Pre-Existing Risks in Surrounding Code")
        lines.append("")
        lines.append("> The following issues were discovered in modified files, but on lines that were not changed by the current diff.")
        lines.append("")
        lines.append("| Severity | Category | Issue | Location | Confidence |")
        lines.append("|---|---|---|---|---|")
        for p in pre_existing:
            loc = f"`{p['file_path']}:{p['line_number']}`"
            lines.append(f"| **{p['severity']}** | `{p['category']}` | {p['title']} | {loc} | {p['confidence']} |")
        lines.append("")

    return "\n".join(lines)
