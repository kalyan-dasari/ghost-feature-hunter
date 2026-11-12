---
name: ghost-feature-hunter
description: Evidence-backed verification of software feature journeys across UI, API, persistence, and delivery. Use when checking whether a feature actually works end-to-end.
compatibility: Requires Python 3.11+ and the ghost-hunter CLI. Optional browser checks require Playwright and Chromium.
metadata:
  author: Ghost Feature Hunter contributors
  version: "0.2.0"
---

# Ghost Feature Hunter

> **DON'T TRUST THE FEATURE. VERIFY IT.**

Ghost Feature Hunter is an independent feature verification engine and Agent Skill. It validates software features against explicit, human-authored behavioral journeys across frontend, API, persistence, and delivery layers.

---

## The Three-Status Truth Table

The engine classifies every observation into exactly one of three states. Never deviate from this logic:

| Status | Verification Meaning | Permissible Interpretation |
|---|---|---|
| **`PASS`** | The configured assertion executed and matched observed behavior. | Proves **only** the executed assertion. Never infer unasserted behavior. |
| **`FAIL`** | An observation directly contradicted an explicit expected behavior. | Proves the feature broke at this checkpoint. |
| **`UNKNOWN`** | Prerequisites, runtimes, permissions, or evidence were unavailable. | **Never relabel as PASS or FAIL.** Unverified or ambiguous check. |

---

## Workflow Selector & Decision Tree

Follow this decision tree to select the appropriate workflow for your task:

```text
Starting an investigation?
│
├── 1. Unfamiliar codebase or unmapped endpoints?
│   └── Follow: Workflow 1 (Discovery) & Workflow 2 (Feature Understanding)
│
├── 2. Requirements or acceptance criteria ambiguous?
│   └── Follow: Workflow 3 (Requirement & Acceptance-Criteria Analysis)
│
├── 3. No journey definition exists yet?
│   └── Follow: Workflow 4 (Journey Generation) & Workflow 5 (Journey Validation)
│
├── 4. Ready to execute verification?
│   ├── Testing HTTP endpoints/contracts? ───────> Workflow 6 (API Verification)
│   ├── Testing DOM/browser interactions? ───────> Workflow 7 (Browser Verification)
│   ├── Testing database records/rollback? ──────> Workflow 8 (Database Verification)
│   ├── Testing roles/tenancy/auth tokens? ──────> Workflow 9 (Authorization Verification)
│   └── Testing bad inputs/error paths? ─────────> Workflow 10 (Error-Path Verification)
│
├── 5. Audit produced FAIL checkpoints?
│   └── Follow: Workflow 11 (Root-Cause Investigation)
│
└── 6. Approved fix applied?
    └── Follow: Workflow 12 (Regression Verification) -> Workflow 13 & 14 (Reporting)
```

For detailed adapter selection rules and safety gate logic, consult [references/decision-tree.md](references/decision-tree.md).

---

## The 14 Verification Workflows

### 1. Feature Discovery
Inspect the codebase to identify literal routes, database models, test files, and frontend components without executing application code:
```console
ghost-hunter discover --project-root <path>
```
*Details in [references/discovery-understanding.md](references/discovery-understanding.md).*

### 2. Feature Understanding
Trace data flow backwards from frontend action -> route -> controller -> business logic -> database -> response. Identify state transitions and integration boundaries.  
*Details in [references/discovery-understanding.md](references/discovery-understanding.md).*

### 3. Requirement & Acceptance-Criteria Analysis
Classify expectations by source:
1. `user_requirement`: Explicit prompt constraints.
2. `product_documentation`: Specifications in README or docs.
3. `api_contract`: Formal schema or endpoint contract.
4. `existing_test`: Assertions from passing test suites.
5. `inferred_assumption`: Hypothesized behavior (must be approved before execution).  
*Details in [references/discovery-understanding.md](references/discovery-understanding.md).*

### 4. Journey Generation
Draft an explicit journey JSON file containing discrete checkpoints. Never overwrite an existing journey without approval.  
*Details in [references/journey-generation.md](references/journey-generation.md).*

### 5. Journey Validation
Validate proposed journeys against `schemas/journey.schema.json`. Verify step ID uniqueness, adapter names, and assertion syntax.  
*Details in [references/journey-generation.md](references/journey-generation.md).*

### 6. API Verification (`adapter: "http"`)
Assert against HTTP status codes, JSON paths (`json_equals`, `json_exists`), and text phrases using HTTPX.  
*Details in [references/verification-adapters.md](references/verification-adapters.md).*

### 7. Browser Verification (`adapter: "browser"`)
Execute same-origin UI actions (`goto`, `click`, `fill`, `expect_visible`, `expect_text`) using headless Chromium.  
*Details in [references/verification-adapters.md](references/verification-adapters.md).*

### 8. Database Verification (`adapter: "database"`)
Verify persistence using read-only SELECT queries on SQLite. Protected by native SQLite authorizer and project root jailing.  
*Details in [references/verification-adapters.md](references/verification-adapters.md).*

### 9. Authorization Verification
Test authentication boundaries, expired tokens (expect 401), insufficient roles (expect 403), and tenant isolation (User A cannot read User B's order).  
*Details in [references/verification-adapters.md](references/verification-adapters.md).*

### 10. Error-Path Verification
Verify system behavior under failure: missing required fields (expect 400), repeated idempotency keys (expect 409), and partial transaction rollbacks.  
*Details in [references/verification-adapters.md](references/verification-adapters.md).*

### 11. Root-Cause Investigation
When an audit fails, trace the failure through source code. Cite exact file and line references. Distinguish confirmed facts from working hypotheses. Propose the minimal targeted fix. Never modify source code without user authorization.  
*Details in [references/investigation.md](references/investigation.md).*

### 12. Regression Verification
After an approved fix is applied, rerun the affected journey with `--force`. Compare before-and-after reports to confirm resolution and ensure no adjacent workflows broke.  
*Details in [references/regression-verification.md](references/regression-verification.md).*

### 13. Evidence Analysis
Inspect raw observations, UTC timestamps, redacted payloads, and reproducibility commands in `ghost-report.json`.  
*Details in [references/evidence-and-reporting.md](references/evidence-and-reporting.md).*

### 14. Report Generation
Render clean Markdown summaries from JSON reports:
```console
ghost-hunter report ghost-reports/ghost-report.json --force
```
*Details in [references/evidence-and-reporting.md](references/evidence-and-reporting.md).*

---

## Core Operational Commands

```console
# 1. Initialize configuration and sample health journey
ghost-hunter init --project-root .

# 2. Advisory static discovery of routes and models
ghost-hunter discover --project-root .

# 3. Execute feature verification journey
ghost-hunter audit <feature> --project-root .

# 4. Mutating actions require explicit write approval
ghost-hunter audit <feature> --project-root . --allow-writes

# 5. Render Markdown report from existing JSON report
ghost-hunter report ghost-reports/ghost-report.json --force
```

---

## Safety Defaults & Guardrails

- **Read-Only Defaults:** Mutating HTTP methods (`POST`, `PUT`, `DELETE`) and browser interactions (`click`, `fill`) are blocked unless `allow_writes: true` in config AND `--allow-writes` on CLI.
- **Production Guardrail:** Targets configured as `production` are blocked unless `production_approved: true` in config AND `--approve-production` on CLI.
- **Database Jailing:** SQLite connections are strictly read-only and denied access to paths outside the project root.
- **Automatic Redaction:** Passwords, API tokens, Bearer tokens, and emails are redacted from all evidence output.
- **Not a Sandbox:** The tool verifies real systems; run checks in isolated environments with synthetic test data.

For troubleshooting and common error remedies, consult [references/troubleshooting.md](references/troubleshooting.md).
