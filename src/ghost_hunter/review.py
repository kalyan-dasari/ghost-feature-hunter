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
                    changed_files.append({
                        "path": rel,
                        "lines": list(range(1, num_lines + 1)),
                        "is_deletion_only": False,
                        "has_additions": True,
                        "deleted_count": 0,
                        "is_untracked": True,
                    })
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
    deleted_count = 0
    added_count = 0

    file_header_re = re.compile(r"^diff --git a/(.*) b/(.*)")
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_output.splitlines():
        fm = file_header_re.match(line)
        if fm:
            if current_file:
                is_del_only = (deleted_count > 0 and added_count == 0)
                changed_files.append({
                    "path": current_file,
                    "lines": sorted(set(current_lines)),
                    "is_deletion_only": is_del_only,
                    "has_additions": added_count > 0,
                    "deleted_count": deleted_count,
                    "is_untracked": False,
                })
            current_file = fm.group(2)
            current_lines = []
            cur_line_num = 0
            deleted_count = 0
            added_count = 0
            continue

        hm = hunk_header_re.match(line)
        if hm and current_file:
            cur_line_num = int(hm.group(1))
            continue

        if current_file and cur_line_num > 0:
            if line.startswith("+") and not line.startswith("+++"):
                current_lines.append(cur_line_num)
                added_count += 1
                cur_line_num += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted_count += 1
            else:
                cur_line_num += 1

    if current_file:
        is_del_only = (deleted_count > 0 and added_count == 0)
        changed_files.append({
            "path": current_file,
            "lines": sorted(set(current_lines)),
            "is_deletion_only": is_del_only,
            "has_additions": added_count > 0,
            "deleted_count": deleted_count,
            "is_untracked": False,
        })

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
                            changed_files.append({
                                "path": untracked_rel,
                                "lines": list(range(1, count + 1)),
                                "is_deletion_only": False,
                                "has_additions": True,
                                "deleted_count": 0,
                                "is_untracked": True,
                            })
        except (FileNotFoundError, OSError):
            pass

    return is_git_repo, diff_output, changed_files


def _inspect_function_transactions(
    content: str,
    file_path: str,
) -> list[tuple[int, str, list[int]]]:
    """Inspect database mutations within individual function/method bodies.

    Returns:
        List of (function_line, function_name, mutation_lines) for functions having
        2+ database mutations without a transaction boundary in that function's scope.
    """
    db_mutation_re = re.compile(
        r"""\b(?:db\.session\.(?:add|delete|commit)|objects\.(?:create|delete|update)|repository\.(?:save|delete)|\.save\(|\.delete\()\b"""
    )
    transaction_wrapper_re = re.compile(
        r"""\b(?:transaction\.atomic|db\.session\.begin|@transactional|@transaction\.atomic|TransactionScope|db\.Begin|DB::transaction)\b"""
    )

    unprotected_functions: list[tuple[int, str, list[int]]] = []

    # 1. Python AST parsing for .py files
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                # Check decorators
                has_tx_decorator = False
                for dec in node.decorator_list:
                    try:
                        dec_text = ast.unparse(dec)
                        if transaction_wrapper_re.search(dec_text):
                            has_tx_decorator = True
                            break
                    except Exception:
                        pass
                if has_tx_decorator:
                    continue

                # Find mutations within this function (excluding nested functions)
                mutation_lines: list[int] = []
                has_tx_context = False

                for child in ast.walk(node):
                    if child is node:
                        continue
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue

                    if isinstance(child, (ast.With, ast.AsyncWith)):
                        for item in child.items:
                            try:
                                ctx_text = ast.unparse(item.context_expr)
                                if transaction_wrapper_re.search(ctx_text):
                                    has_tx_context = True
                            except Exception:
                                pass

                    if isinstance(child, ast.Call):
                        try:
                            call_text = ast.unparse(child)
                            if db_mutation_re.search(call_text):
                                mutation_lines.append(getattr(child, "lineno", node.lineno))
                        except Exception:
                            pass

                mutation_lines = sorted(set(mutation_lines))
                if len(mutation_lines) >= 2 and not has_tx_context:
                    unprotected_functions.append((node.lineno, node.name, mutation_lines))

            return unprotected_functions
        except SyntaxError:
            pass

    # 2. Block-level parsing for non-Python or syntax-fallback
    lines = content.splitlines()
    func_pattern = re.compile(
        r"""^\s*(?:(?:public|private|protected|async|static|def|func|function)\s+)+([a-zA-Z0-9_]+)\s*\([^)]*\)"""
    )
    current_func: str | None = None
    func_start_line = 0
    func_lines: list[str] = []
    func_mutations: list[int] = []

    for idx, line in enumerate(lines, 1):
        fm = func_pattern.search(line)
        if fm:
            if current_func and len(func_mutations) >= 2:
                func_text = "\n".join(func_lines)
                if not transaction_wrapper_re.search(func_text):
                    unprotected_functions.append((func_start_line, current_func, func_mutations))
            current_func = fm.group(1)
            func_start_line = idx
            func_lines = [line]
            func_mutations = []
            if db_mutation_re.search(line):
                func_mutations.append(idx)
        else:
            if current_func:
                func_lines.append(line)
                if db_mutation_re.search(line):
                    func_mutations.append(idx)

    if current_func and len(func_mutations) >= 2:
        func_text = "\n".join(func_lines)
        if not transaction_wrapper_re.search(func_text):
            unprotected_functions.append((func_start_line, current_func, func_mutations))

    return unprotected_functions


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
    file_meta_by_path: dict[str, dict[str, Any]] = {cf["path"]: cf for cf in changed_files}

    def record_finding(f: ReviewFinding):
        meta = file_meta_by_path.get(f.file_path)
        if not meta:
            # File was not modified in this diff
            pre_existing_risks.append(f)
            return

        added_lines = set(meta.get("lines", []))
        is_del_only = meta.get("is_deletion_only", False)

        if is_del_only:
            # Commit only deleted code from this file; findings on existing lines are pre-existing
            pre_existing_risks.append(f)
        elif meta.get("is_untracked", False):
            # Brand new untracked file: all contents are introduced
            findings.append(f)
        elif f.line_number in added_lines:
            # Line was explicitly added in this change
            findings.append(f)
        else:
            # Line is outside the added lines of the diff
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

    # 3. Disconnected client calls in modified files (parameter-aware matching with boundary isolation)
    routes: list[RouteDefinition] = scan_data.get("routes", [])
    valid_routes = [r for r in routes if r.source_role == "application_source"]
    app_boundaries = context.get("application_boundaries", [])
    has_multiple_apps = len([b for b in app_boundaries if not b.get("is_root")]) > 1

    for call in scan_data.get("client_calls", []):
        if call.source in changed_paths:
            norm_call_path = call.path
            if norm_call_path.startswith(("http://", "https://", "//")):
                continue

            # Candidate routes must belong to the same application boundary unless explicit cross-service target
            if has_multiple_apps and call.app_name:
                candidate_routes = [
                    r for r in valid_routes
                    if (r.app_name == call.app_name)
                    or (r.app_name in ("primary", "", "root"))
                    or (call.target_service and call.target_service == r.app_name)
                ]
            else:
                candidate_routes = valid_routes

            matching = [r for r in candidate_routes if match_route(norm_call_path, r.path)]
            if not matching:
                unrelated_routes = [r for r in valid_routes if match_route(norm_call_path, r.path)]
                unrelated_note = ""
                if unrelated_routes:
                    other_apps = sorted({r.app_name for r in unrelated_routes if r.app_name})
                    unrelated_note = f" (Route exists in unrelated application(s): {', '.join(other_apps)}, but not in '{call.app_name}')"

                record_finding(
                    ReviewFinding(
                        title=f"Client API call points to unregistered endpoint: {norm_call_path}",
                        category="wiring",
                        severity="High",
                        confidence="High" if not unrelated_routes else "Medium",
                        current_behavior=f"Modified client code in '{call.app_name or 'primary'}' makes a {call.method} request to '{norm_call_path}'.",
                        failure_scenario="Requests will receive HTTP 404 Not Found at runtime if the backend route is missing.",
                        evidence=f"{call.source}:{call.line} -> {call.raw}{unrelated_note}",
                        file_path=call.source,
                        line_number=call.line,
                        root_cause=f"Endpoint '{norm_call_path}' is not declared in application '{call.app_name or 'primary'}' backend route handlers.",
                        recommended_fix=f"Register route handler for '{norm_call_path}' in application '{call.app_name or 'primary'}' or correct client request URL.",
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

            if has_multiple_apps and call.app_name:
                candidate_routes = [
                    r for r in valid_routes
                    if (r.app_name == call.app_name)
                    or (r.app_name in ("primary", "", "root"))
                    or (call.target_service and call.target_service == r.app_name)
                ]
            else:
                candidate_routes = valid_routes

            matching = [r for r in candidate_routes if match_route(norm_call_path, r.path)]
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
    sql_sink_re = re.compile(
        r"""(?:cursor\.execute|\.execute)\s*\(\s*f(?:"[^"\n]*(?:SELECT|INSERT|UPDATE|DELETE)[^"\n]*\{|'[^'\n]*(?:SELECT|INSERT|UPDATE|DELETE)[^'\n]*\{)""",
        re.IGNORECASE,
    )
    cmd_sink_re = re.compile(
        r"""(?:os\.system|subprocess\.(?:Popen|call|run))\s*\(\s*f(?:"[^"\n]*\{|'[^'\n]*\{)"""
    )
    user_input_re = re.compile(
        r"""\b(?:request\.(?:args|form|values|json|GET|POST|query_params|data)|req\.(?:query|body|params)|params|query_params|user_input|userInput|cmd_input|raw_input)\b"""
    )
    for cf in changed_files:
        p = root / cf["path"]
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_num, line in enumerate(content.splitlines(), 1):
            if sql_sink_re.search(line):
                is_tainted = bool(user_input_re.search(line))
                if is_tainted:
                    record_finding(
                        ReviewFinding(
                            title="Injection risk: direct SQL injection from unvalidated user input",
                            category="security",
                            severity="Critical",
                            confidence="High",
                            current_behavior=f"User-controlled request parameter is directly interpolated into raw SQL query: {line.strip()}",
                            failure_scenario="External input can alter query syntax, bypass authentication, or dump/modify database tables.",
                            evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="User-controlled input was formatted directly into SQL query instead of using parameterized arguments.",
                            recommended_fix="Use parameterized queries (e.g. cursor.execute(query, (params,))).",
                            impact="Critical data breach or unauthorized database modification.",
                            false_positive_risk="Input may have been sanitized prior to line execution.",
                        )
                    )
                else:
                    record_finding(
                        ReviewFinding(
                            title="Injection risk: raw SQL query with f-string interpolation",
                            category="security",
                            severity="Medium",
                            confidence="Medium",
                            current_behavior=f"SQL query is constructed using f-string interpolation: {line.strip()}",
                            failure_scenario="If the interpolated variable is ever influenced by external input, it introduces a SQL injection vulnerability.",
                            evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="SQL query was constructed with raw string formatting instead of parameterized arguments.",
                            recommended_fix="Use parameterized queries or validate identifiers against an allowlist.",
                            impact="Potential security risk if variable provenance changes in future revisions.",
                            false_positive_risk="Interpolated values may be compile-time constants or internally trusted variables.",
                        )
                    )
            elif cmd_sink_re.search(line):
                is_tainted = bool(user_input_re.search(line))
                if is_tainted:
                    record_finding(
                        ReviewFinding(
                            title="Injection risk: arbitrary command execution from user input",
                            category="security",
                            severity="Critical",
                            confidence="High",
                            current_behavior=f"User-controlled input is directly interpolated into shell command: {line.strip()}",
                            failure_scenario="External input can inject shell metacharacters and execute arbitrary system commands.",
                            evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="Untrusted input was interpolated into shell command string instead of passing an argument list.",
                            recommended_fix="Pass command arguments as an array/list (e.g. subprocess.run(['cmd', arg])) without shell=True.",
                            impact="Remote code execution and total system compromise.",
                            false_positive_risk="Input may have been validated against strict allowlist before execution.",
                        )
                    )
                else:
                    record_finding(
                        ReviewFinding(
                            title="Injection risk: shell command execution with f-string interpolation",
                            category="security",
                            severity="Medium",
                            confidence="Medium",
                            current_behavior=f"Shell command is constructed using f-string interpolation: {line.strip()}",
                            failure_scenario="If this variable is ever influenced by external parameters, it creates a command injection risk.",
                            evidence=f"{cf['path']}:{line_num} -> {line.strip()}",
                            file_path=cf["path"],
                            line_number=line_num,
                            root_cause="Shell command was constructed with string formatting instead of an argument list.",
                            recommended_fix="Pass arguments as a list without shell=True, or sanitize arguments with shlex.quote.",
                            impact="Potential code execution if variable source changes.",
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

    # 8. Mutating database operations without transaction boundary (function-scoped inspection)
    for cf in changed_files:
        p = root / cf["path"]
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        unprotected_funcs = _inspect_function_transactions(content, cf["path"])
        lines = content.splitlines()
        for func_line, func_name, mutation_lines in unprotected_funcs:
            first_mut = mutation_lines[0]
            mut_text = lines[first_mut - 1].strip() if 0 < first_mut <= len(lines) else ""
            record_finding(
                ReviewFinding(
                    title=f"Multiple database mutations without transaction boundary in '{func_name}'",
                    category="data_risk",
                    severity="Medium",
                    confidence="High" if cf["path"].endswith(".py") else "Medium",
                    current_behavior=f"Function '{func_name}' performs {len(mutation_lines)} database mutating operations without an atomic transaction boundary.",
                    failure_scenario="If an intermediate write fails or crashes, partial data is committed, corrupting database consistency.",
                    evidence=f"{cf['path']}:{first_mut} -> {mut_text} ({len(mutation_lines)} mutations in '{func_name}')",
                    file_path=cf["path"],
                    line_number=first_mut,
                    root_cause=f"Function '{func_name}' executes multiple mutations sequentially without an atomic transaction wrapper or rollback handler.",
                    recommended_fix=f"Wrap mutations in '{func_name}' in an atomic transaction block (e.g. 'with transaction.atomic():' or @transactional).",
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
