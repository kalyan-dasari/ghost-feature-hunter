---
name: ghost-hunt
description: Context-aware codebase investigator and feature verification skill for AI coding agents. Discovers architecture, traces multi-language data flow, executes safe checks, audits whole repositories for ghost features and code hygiene, isolates confirmed defects, and verifies fixes end-to-end.
metadata:
  author: Ghost Feature Hunter contributors
  version: "0.3.0"
---

# Ghost Hunt (`ghost-hunt`)

> **DON'T TRUST THE FEATURE. VERIFY IT.**

Ghost Hunt is an open-source, context-aware Agent Skill for AI coding agents. When asked to inspect a project, audit a repository, or verify a feature, Ghost Hunt first locks the correct project scope, detects actual languages and frameworks, traces full-stack data flow, detects ghost features and unfinished implementations, executes safe checks, isolates confirmed defects with empirical evidence, and recommends targeted fixes.

---

## 🧭 Investigation Modes & Invocations

Ghost Hunt operates in four distinct skill modes:

| Mode | Invocation Syntax | Purpose |
|---|---|---|
| **Project Discovery** | `/ghost-hunt discover` | Static architecture inventory, language capability matrix, boundary detection. Zero runtime mutations. |
| **Feature Investigation** | `/ghost-hunt investigate <feature>` | End-to-end verification of a specific feature in the target application. |
| **Repository-Wide Audit** | `/ghost-hunt audit` | Whole-repository audit for ghost features, empty implementations, route mismatches, unused code, and duplication. |
| **Post-Fix Verification** | `/ghost-hunt verify <feature>` | Re-verifies approved code fixes and runs regression checks against test suites. |

### Bare Invocation Protocol (`/ghost-hunt investigate` or `/ghost-hunt`)
When invoked without a feature argument:
1. **Identify Project Root:** Detect workspace root, Git root, and package manifests.
2. **Display Project Context:** Report project name, primary languages, and detected application roots.
3. **Isolate Examples & Fixtures:** Categorize `src/`, `lib/`, `app/` as primary application source; classify `examples/`, `fixtures/`, and `benchmarks/` separately. **Never silently choose an example or benchmark directory as the primary target.**
4. **Clarify Intent:** Ask one concise question to determine which feature to investigate, while explaining that a whole-project investigation is available via `/ghost-hunt audit`.

---

## 📋 Mandatory Project Context & Capability Summary

Every Ghost Hunt audit report must begin with this standardized block:

```markdown
### Project Context Summary
- **Project Name:** `<project_name>`
- **Project Root:** `<path_to_project_root>`
- **Git Repository Root:** `<git_root_or_none>`
- **Selected Application Root:** `<app_root>`
- **Investigation Mode:** `<discover | investigate | audit | verify>`
- **Included Directories:** `<included_directories>`
- **Excluded Directories:** `<excluded_directories (e.g. examples, vendor, tests)>`
- **Available Capabilities:** `<native_tools_available (file, shell, curl, browser)>`
- **Limitations:** `<unsupported_runtimes_or_mocked_services>`

### Language & Framework Capability Matrix
| Language / Framework | Detected | Analysis Capability | Limitations |
|---|---|---|---|
| `<Language / Framework>` | Yes | `<Supported analysis | Partial | Inventory-only>` | `<Explicit limitations>` |
```

*(Consult [references/language-support.md](references/language-support.md) for ecosystem capability specifications).*

---

## ⚖️ The Three-Status Evidence Standard

Classify every verification checkpoint into exactly one of three states. Never deviate from this logic:

| Status | Exact Meaning | Permissible Interpretation |
|---|---|---|
| **`PASS`** | A real check ran against uncontaminated state and its observed result affirmatively matched an authoritative expectation. | Proves **only** the executed assertion. Never infer unasserted behavior. |
| **`FAIL`** | An executed check directly contradicted an authoritative expected behavior. | Proves the feature broke at this specific checkpoint. |
| **`UNKNOWN`** | Prerequisites, permissions, runtimes, clean databases, or evidence were unavailable; or an inferred assumption is unconfirmed. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

---

## 🔬 The 11-Step Feature Investigation Protocol

When investigating a feature (`/ghost-hunt investigate <feature>`), execute these 11 steps:

```text
1. Scope & Project Lock ──> 2. Static Discovery ──> 3. Flow Tracing ──> 4. Requirements
                                                                               │
7. Defect Isolation <── 6. Safe Execution <── 5. Journey Checkpoints <─────────┘
│
└──> 8. Root Cause ──> 9. Minimal Fix ──> 10. Regression ──> 11. Evidence Report
```

### 1. Scope & Project Context Lock
Detect project root, git root, and target application. Distinguish application source from examples/fixtures. Explicit user paths take precedence over inferred roots. *(Consult [references/project-context.md](references/project-context.md))*

### 2. Discover Relevant Source Files
Statically inspect route definitions, backend controllers, database models, templates, and existing tests across the project's actual languages without importing or executing untrusted code. *(Consult [references/discovery-understanding.md](references/discovery-understanding.md))*

### 3. Trace End-to-End Data Flow
Trace data across all tiers: `User Action -> Route -> Controller -> Service Logic -> DB Mutation -> Response -> UI State`.

### 4. Analyze Requirements & Tag Sources
Classify all behavioral expectations into the 5-source taxonomy:
1. `user_requirement`: Constraints stated explicitly by the user in the prompt. **Must quote prompt.**
2. `product_documentation`: Specifications in README or docs. **Must cite file and section.**
3. `api_contract`: Formal schema, OpenAPI, or TypeScript types. **Must cite contract file.**
4. `existing_test`: Assertions verified by passing tests. **Must cite test file and function.**
5. `inferred_assumption`: Hypotheses deduced from code or patterns.

> [!IMPORTANT]
> **The Critical Rule for Inferred Assumptions:**
> Hypotheses must NEVER silently become authoritative requirements. If code differs from an inferred assumption, report it as an observation with status **`UNKNOWN`** and ask for confirmation. Never manufacture a `FAIL` simply because code differs from convention.

### 5. Define Journey Checkpoints
Structure discrete, ordered checkpoints covering happy paths, auth boundaries, persistence, and error paths. *(Use [templates/journey-template.json](templates/journey-template.json) or [references/journey-mapping.md](references/journey-mapping.md))*

### 6. Execute Relevant Safe Checks
- **Side-Effect Classification:** Inspect actual handler behavior before execution; do not assume GET is safe or POST is mutating.
- **Authorization Gate:** Request explicit user authorization before Level 3 runtime mutations.
- **Stateful Scenario Isolation:** Run state-dependent checks against fresh disposable databases (`tempfile`). Seed known initial state, record baseline initial values, execute approved actions, and record final observed values.
- **Contamination Guard:** Never continue on contaminated test state. If clean state cannot be established, mark **`UNKNOWN`**.
- **PASS Evidence Contract:** PASS requires affirmative match against authoritative expectation with uncontaminated evidence. Static inspection alone can NEVER prove runtime PASS. *(Consult [references/verification-playbook.md](references/verification-playbook.md))*

### 7. Identify Confirmed Defects
Record every discrepancy between authoritative expected behavior and actual observation as a confirmed defect (**`FAIL`**).

### 8. Investigate Root Cause
Trace backward from observed failure to exact source files and line ranges (`path/to/file.py:L42-L55`). Explain *why* the defect occurs. *(Consult [references/investigation-root-cause.md](references/investigation-root-cause.md))*

### 9. Recommend Targeted Fixes
Present the smallest surgical patch addressing the root cause. **NEVER modify source code without user authorization.**

### 10. Verify Fixes & Prevent Regressions
Upon user approval, apply the edit, rerun failing checkpoints to confirm resolution (**`PASS`**), and rerun adjacent test suites to prevent regressions. *(Consult [references/regression-verification.md](references/regression-verification.md))*

### 11. Produce an Evidence-Backed Report
Deliver a structured Markdown audit report starting with the Project Context Summary, capability matrix, checkpoint breakdown, before/after measurements, root causes, and limitations. *(Use [templates/report-template.md](templates/report-template.md) and [references/evidence-reporting.md](references/evidence-reporting.md))*

---

## 🏛️ The Whole-Repository Audit Protocol (`/ghost-hunt audit`)

When invoked with `/ghost-hunt audit`, inspect the complete repository:
1. **Architecture & Capability Inventory:** Map applications, services, routes, models, frontend assets, tests, configurations, and the Language/Framework Capability Matrix.
2. **Route Connection Analysis:**
   - **Missing Route Candidates:** Frontend calls an endpoint with no registered backend handler.
   - **Method / Path Mismatches:** Client dispatches an HTTP method or path differing from the registered handler.
   - **Potentially Unused Endpoints:** Routes with 0 callers in frontend, tests, or docs (candidates only; check external webhooks).
   - **Uncovered Routes:** Registered endpoints with zero matching tests in test suites.
3. **Ghost Feature Detection:** Identify broken chains across UI navigation, buttons, forms, client calls, routes, and services. *(Consult [references/ghost-features.md](references/ghost-features.md))*
4. **Empty & Unfinished Implementations:** Surface empty functions, placeholder handlers, unhandled exceptions, and silent error catches (excluding abstract methods and interface declarations).
5. **Reference Graph & Dependency Hygiene:** Identify unreferenced exported symbols and unused manifest packages with dynamic loading caveats.
6. **Structural Duplicate Logic:** Detect identical normalized function bodies across different names without double-counting lines. *(Consult [references/repository-audit.md](references/repository-audit.md))*

---

## 🛡️ Safety Defaults & Operational Tiers

Ghost Hunt strictly enforces four operational safety levels:

| Tier | Category | Safety Policy | Permitted Actions |
|---|---|---|---|
| **Level 1** | **Source Inspection** | **Safe by default.** | Static file discovery, AST parsing, test reading. Never imports or executes untrusted code to discover structure. |
| **Level 2** | **Runtime Read-Only** | **Safe in test environments.** | Safe HTTP probes (`GET`, `HEAD`, `OPTIONS`) and read-only database queries (`SELECT` only, capped at 1,000 rows). |
| **Level 3** | **Runtime Mutations** | **Requires user authorization.** | State-altering HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) and browser form submissions. Must target disposable test environments with synthetic data. |
| **Level 4** | **Database Writes** | **Strictly isolated.** | Direct database mutations (`INSERT`, `UPDATE`, `DELETE`). Strictly prohibited against production databases. Restricted to disposable temporary databases with cleanup and re-seeding. |

### Absolute Safety Guardrails:
- **Production Guardrail:** Block all checks against production environments by default.
- **Credential Redaction:** Automatically redact passwords, API keys, Bearer tokens, and email addresses from evidence logs.
- **No Code Edits Without Approval:** Always present proposed fixes as diffs for user approval before modifying code.

---

## 📚 Progressive Disclosure & Reference Index

Load only the reference documents needed for your specific task:

- [references/project-context.md](references/project-context.md) — Project detection, scope locking, and example isolation.
- [references/language-support.md](references/language-support.md) — Multi-language detection vs analysis support and capability matrix.
- [references/ghost-features.md](references/ghost-features.md) — Ghost feature detection playbook and 8-layer connection graph.
- [references/repository-audit.md](references/repository-audit.md) — Playbook for `/ghost-hunt audit` whole-repository inspections.
- [references/decision-tree.md](references/decision-tree.md) — Mode selection, native vs CLI tools, and safety gates.
- [references/discovery-understanding.md](references/discovery-understanding.md) — Codebase inspection and data flow tracing.
- [references/journey-mapping.md](references/journey-mapping.md) — Designing discrete journey checkpoints and expectation sources.
- [references/verification-playbook.md](references/verification-playbook.md) — Testing guides, scenario isolation, and PASS evidence contract.
- [references/investigation-root-cause.md](references/investigation-root-cause.md) — Root cause diagnosis, stack tracing, and minimal fix design.
- [references/regression-verification.md](references/regression-verification.md) — Post-fix regression verification procedures.
- [references/evidence-reporting.md](references/evidence-reporting.md) — Evidence sanitization, redaction, and reporting standards.
- [references/troubleshooting.md](references/troubleshooting.md) — Environment blockers, permissions, and tool recovery.
- [references/optional-cli.md](references/optional-cli.md) — Usage of the optional Python verification CLI engine.
- [templates/report-template.md](templates/report-template.md) — Reusable Markdown report template.
- [templates/journey-template.json](templates/journey-template.json) — Reusable JSON journey schema template.
- [examples/checkout-investigation.md](examples/checkout-investigation.md) — Real-world example investigation of a checkout feature.
