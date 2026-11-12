---
name: ghost-hunt
description: Evidence-backed feature verification skill for AI coding agents. Discovers code flow, executes safe checks using native tools or optional CLI, isolates confirmed defects, pinpoints root causes, and verifies fixes end-to-end.
metadata:
  author: Ghost Feature Hunter contributors
  version: "0.3.0"
---

# Ghost Hunt (`ghost-hunt`)

> **DON'T TRUST THE FEATURE. VERIFY IT.**

Ghost Hunt is a skill-first software verification tool for AI coding agents. When a developer asks you to investigate, verify, or debug a feature, use this skill to trace how the feature works end-to-end, execute real safe checks, identify confirmed defects, isolate root causes, and verify fixes with reproducible evidence.

---

## Agent Invocations

- **Google Antigravity:** `/ghost-hunt [feature]` or `/ghost-hunt investigate <feature>`
- **Claude Code:** `/ghost-hunt [feature]` or `/ghost-hunt investigate <feature>`
- **OpenAI Codex:** `$ghost-hunt [feature]` or `$ghost-hunt investigate <feature>`
- **Direct Prompt:** "Investigate my checkout feature", "Verify that user registration works", "Check if billing properly deducts inventory"

---

## Dual Execution Modes

Ghost Hunt adapts to the agent's available environment:

| Mode | Prerequisites | How Checks Are Executed |
|---|---|---|
| **Native Agent Tools (Default)** | **None.** Works in any repo out of the box. | Uses the agent's native tools: file inspection, terminal commands (`curl`, test runners, Python/Node scripts), and browser tools. |
| **Deterministic CLI Engine (Optional)** | Python 3.11+ and `ghost-hunter` installed (`pip install ghost-feature-hunter[all]`). | Executes strict JSON journeys via `ghost-hunter audit <feature>` with automated schema validation and report rendering. |

*Rule:* If the Python CLI is installed, you may leverage it for deterministic execution. If it is not installed, **proceed immediately using your native agent tools**. Never claim a tool was executed if it was not available.

---

## The Three-Status Evidence Standard

Classify every verification checkpoint into exactly one of three states. Never deviate from this logic:

| Status | Exact Meaning | Permissible Interpretation |
|---|---|---|
| **`PASS`** | A real check ran and its observed result matched the explicit expected behavior. | Proves **only** the executed assertion. Never infer unasserted behavior. |
| **`FAIL`** | An executed check directly contradicted an explicit expected behavior. | Proves the feature broke at this specific checkpoint. |
| **`UNKNOWN`** | Prerequisites, permissions, runtimes, or evidence were unavailable. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

---

## The 11-Step Investigation Protocol

When invoked with `/ghost-hunt <feature>` or a feature request, execute these 11 steps:

```text
1. Feature Scope ──> 2. Static Discovery ──> 3. Flow Tracing ──> 4. Requirements
                                                                         │
7. Defect Isolation <── 6. Safe Execution <── 5. Journey Checkpoints <───┘
│
└──> 8. Root Cause ──> 9. Minimal Fix ──> 10. Regression ──> 11. Evidence Report
```

### 1. Understand Feature Scope
Extract the target feature name, user intent, affected personas, and entry points. Identify whether the user wants an exploratory audit, bug reproduction, or post-change regression check.

### 2. Discover Relevant Source Files
Statically inspect the codebase without executing untrusted code:
- Identify route definitions and API contracts.
- Find backend controllers, service functions, and middleware.
- Identify database models, migrations, and table schemas.
- Locate existing unit and integration tests for the feature.
- Locate relevant frontend templates, views, or UI components.  
*(Consult [references/discovery-understanding.md](references/discovery-understanding.md))*

### 3. Trace End-to-End Data Flow
Trace data across all application tiers:
`User Action / UI View -> HTTP Route -> Controller -> Service / Business Logic -> Database Query / Mutation -> Response -> UI State`.

### 4. Analyze Requirements & Tag Sources
Classify all behavioral expectations by their source:
1. `user_requirement`: Constraints stated explicitly in the prompt.
2. `product_documentation`: Specifications found in README or docs.
3. `api_contract`: Formal schema (OpenAPI, GraphQL, TypeScript types).
4. `existing_test`: Assertions verified by passing test suites.
5. `inferred_assumption`: Hypothesized behavior. **Always flag assumptions to the user; never treat them as authoritative requirements without approval.**

### 5. Define Journey Checkpoints
Draft discrete, ordered checkpoints covering the happy path, error paths, and edge cases:
- State the exact **checkpoint name**, **expected behavior**, and **source of expectation**.
- Choose the verification mechanism: API, UI/DOM, Database, or Test Runner.  
*(Use template in [templates/journey-template.json](templates/journey-template.json) or [references/journey-mapping.md](references/journey-mapping.md))*

### 6. Execute Relevant Safe Checks
Run checks using the best available tools:
- **API Checks:** Send HTTP requests with `curl`, `httpx`, or native terminal tools. Assert status codes, response headers, and JSON body keys.
- **Frontend / UI Checks:** Use the agent's browser tool or headless Playwright if available. Assert DOM visibility, form inputs, and expected text.
- **Database Persistence Checks:** Inspect database records using SQLite CLI, parameterized Python scripts, or query tools. Check row counts and column values. **Keep database checks strictly read-only.**
- **Auth & Authorization:** Test unauthenticated requests (expect 401), unauthorized roles (expect 403), and tenant isolation.
- **Error Paths:** Test invalid payloads (expect 400), duplicates (expect 409), and boundary conditions.  
*(Consult [references/verification-playbook.md](references/verification-playbook.md))*

### 7. Identify Confirmed Defects
Record every discrepancy between expected behavior and actual observation as a confirmed defect. Mark the checkpoint **`FAIL`**.

### 8. Investigate Root Cause
For every failing checkpoint:
- Trace backward from the symptom into the codebase.
- Cite exact file paths and line numbers: `path/to/file.py:L42-L55`.
- Distinguish confirmed code bugs from environmental misconfigurations or missing test data.
- Explain *why* the code fails (e.g., incorrect query filter, missing transaction commit, unhandled null).  
*(Consult [references/investigation-root-cause.md](references/investigation-root-cause.md))*

### 9. Recommend Targeted Fixes
Present a minimal, surgical fix addressing the root cause:
- Show the recommended diff.
- Explain side effects and risk assessment.
- **NEVER modify source code without user authorization.** Present the fix and ask for approval.

### 10. Verify Fixes & Prevent Regressions
Once the user authorizes the fix:
- Apply the code edit.
- Rerun the failing checkpoint to confirm it now passes (**`PASS`**).
- Rerun adjacent feature checks and existing unit test suites to confirm no regressions.  
*(Consult [references/regression-verification.md](references/regression-verification.md))*

### 11. Produce an Evidence-Backed Report
Deliver a structured Markdown audit report:
- Summary table: Total checks, PASS, FAIL, UNKNOWN.
- Checkpoint breakdown with expected vs actual observation, timestamps, and evidence references.
- Confirmed defects with root-cause analysis and citations.
- Explicit limitations and unverified areas.  
*(Use template in [templates/report-template.md](templates/report-template.md) and guide in [references/evidence-reporting.md](references/evidence-reporting.md))*

---

## Safety Defaults & Operation Categories

Ghost Hunt categorizes every verification action into four explicit safety levels:

1. **Source-Code Read-Only Inspection:** Safe. Parsing files, AST, and configurations. Never imports or runs untrusted application code.
2. **Runtime GET / Read-Only Checks:** Safe in test environments. Non-mutating HTTP methods (`GET`, `HEAD`, `OPTIONS`) and read-only `SELECT` queries.
3. **Runtime Mutating Operations:** State-altering HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) and browser clicks/submits. **Requires explicit user authorization.** Must use synthetic test data.
4. **Database Write Operations:** Direct database mutations (`INSERT`, `UPDATE`, `DELETE`, `DROP`). Strictly prohibited during read-only audits. When benchmarking stateful flows, always execute against disposable temporary databases; clean up and reseed to prevent previous run contamination.

### Absolute Safety Guardrails:
- **Production Guardrail:** Block all checks against production environments unless explicit user authorization is provided.
- **Credential Redaction:** Automatically redact passwords, API keys, Bearer tokens, and personal email addresses from evidence logs.
- **No Code Edits Without Approval:** Always present proposed fixes for user approval before modifying code.

---

## Progressive Disclosure & Reference Index

Load only the reference documents needed for your specific investigation:

- [references/decision-tree.md](references/decision-tree.md) — Workflow selection, native vs CLI tools, and safety gates.
- [references/discovery-understanding.md](references/discovery-understanding.md) — Codebase inspection and data flow tracing.
- [references/journey-mapping.md](references/journey-mapping.md) — Designing discrete journey checkpoints and expectation sources.
- [references/verification-playbook.md](references/verification-playbook.md) — Detailed testing guides for API, Browser, Database, Auth, and Error paths.
- [references/investigation-root-cause.md](references/investigation-root-cause.md) — Root cause diagnosis, stack tracing, and minimal fix design.
- [references/regression-verification.md](references/regression-verification.md) — Post-fix regression verification procedures.
- [references/evidence-reporting.md](references/evidence-reporting.md) — Evidence sanitization, redaction, and reporting standards.
- [references/troubleshooting.md](references/troubleshooting.md) — Environment blockers, permissions, and tool recovery.
- [references/optional-cli.md](references/optional-cli.md) — Advanced usage of the optional Python verification CLI engine.
- [templates/report-template.md](templates/report-template.md) — Reusable Markdown report template.
- [templates/journey-template.json](templates/journey-template.json) — Reusable JSON journey schema template.
- [examples/checkout-investigation.md](examples/checkout-investigation.md) — Real-world example investigation of a checkout feature.
