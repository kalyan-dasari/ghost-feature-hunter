# Decision Trees: Execution Mode, Workflows & Safety Gates

Use these decision trees to determine the appropriate execution mode, workflow steps, and safety constraints for any feature investigation.

---

## 1. Tooling & Execution Mode Decision Tree

```text
Starting a Ghost Hunt investigation:
│
├── Is the optional "ghost-hunter" CLI installed in the environment?
│   ├── YES ──> Does the project have a ghost-hunter.json and journey definition?
│   │           ├── YES ──> Use Deterministic Engine:
│   │           │           Run: ghost-hunter audit <feature>
│   │           └── NO  ──> Can generate journey with Workflow 4, or use Native Agent Tools directly.
│   │
│   └── NO  ──> Use Native Agent Tools (Standard Skill Mode):
│               ├── Code Discovery: Inspect files, AST, grep, ripgrep, find
│               ├── API Checks: curl, httpx, test runner, terminal commands
│               ├── UI Checks: Agent browser tool, Playwright scripts
│               ├── Database Checks: sqlite3 CLI, read-only Python scripts
│               └── Reporting: Render structured Markdown directly in chat/artifacts
```

---

## 2. Investigation Workflow Decision Tree

```text
Where are you in the investigation?
│
├── Feature is unfamiliar or code paths unmapped?
│   └── Step 1 (Scope) ──> Step 2 (Discovery) ──> Step 3 (Flow Tracing)
│
├── Requirements or acceptance criteria are vague?
│   └── Step 4 (Requirement & Acceptance Criteria Analysis)
│
├── Ready to execute checks?
│   ├── Testing HTTP endpoints / contracts? ────────> Step 6 (API Verification)
│   ├── Testing user-facing DOM / UI flow? ─────────> Step 6 (Browser Verification)
│   ├── Testing persistence or database state? ─────> Step 6 (Database Verification)
│   ├── Testing roles / tenancy / auth tokens? ─────> Step 6 (Authorization Verification)
│   └── Testing bad inputs / edge cases? ───────────> Step 6 (Error-Path Verification)
│
├── An executed check produces a FAIL status?
│   └── Step 7 (Defect Isolation) ──> Step 8 (Root-Cause Investigation)
│
└── Minimal fix proposed and approved by user?
    └── Step 9 (Fix Implementation) ──> Step 10 (Regression Verification) ──> Step 11 (Report)
```

---

## 3. Capability & Tool Selection Matrix

| Verification Target | Native Agent Tools (Default) | Optional CLI Adapter | Required Approvals |
|---|---|---|---|
| HTTP Status, Response Body, Headers | `curl`, `httpx`, Python script | `adapter: "http"` | Read: None; Write: User authorization / `--allow-writes` |
| Form Submissions, DOM Visibility | Agent browser tool, Playwright script | `adapter: "browser"` | Read: None; Write: User authorization / `--allow-writes` |
| Database Persistence, Row Counts | `sqlite3` CLI, read-only Python script | `adapter: "database"` | Strictly read-only SELECT queries |
| Multi-tenant Ownership Isolation | `curl` with auth tokens / headers | `adapter: "http"` | Read: None |
| Validation Errors & Error Paths | `curl` with malformed payloads | `adapter: "http"` | User authorization for mutating endpoints |

---

## 4. Safety Gate Decision Tree

```text
Is the target environment configured as "production"?
│
├── YES ──> Has the user explicitly approved production testing?
│           ├── YES ──> Allow read-only execution under strict audit log.
│           └── NO  ──> BLOCK immediately. Mark status UNKNOWN ("Production target blocked").
└── NO  ──> Proceed to mutation check.

Does the check perform a mutating action (POST, PUT, DELETE, PATCH, DB mutation)?
│
├── YES ──> Has the user explicitly approved writes in this environment?
│           ├── YES ──> Execute mutating check against disposable/test environment.
│           └── NO  ──> BLOCK mutating action. Mark status UNKNOWN ("Write approval required").
└── NO  ──> Allow safe read execution (GET, HEAD, read-only SELECT).
```
