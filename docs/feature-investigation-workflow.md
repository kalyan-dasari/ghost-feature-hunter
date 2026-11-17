# Feature Investigation Workflow: The 11-Step Protocol

Ghost Hunt enforces an empirical, 11-step investigation protocol designed to determine whether a feature is genuinely functional, properly wired, and verifiable across all application layers.

```text
1. Feature Scope ──> 2. Static Discovery ──> 3. Flow Tracing ──> 4. Requirements
                                                                         │
7. Defect Isolation <── 6. Safe Execution <── 5. Journey Checkpoints <───┘
│
└──> 8. Root Cause ──> 9. Minimal Fix ──> 10. Regression ──> 11. Evidence Report
```

---

## 1. Feature Scope & Project Context Lock
Before inspecting any code, lock the target project:
- Identify project root, Git repository root, and application subpackages.
- Segregate primary application source (`src/`, `app/`, `lib/`) from examples, fixtures, and benchmarks (`examples/`, `tests/fixtures/`).
- Clarify feature intent, user personas, and entry points.

## 2. Static Discovery & Component Inventory
Statically inspect codebase files across all detected languages:
- Backend route definitions and controllers.
- Data models and database schemas.
- Frontend components, interactive buttons, and forms.
- Existing test suites and mocks.
- **Rule:** Never import or execute untrusted codebase files to discover architecture. Use parser-backed AST or structural lexical scanning.

## 3. End-to-End Data Flow Tracing
Trace the feature path across the 8-layer stack:
`UI Action -> Client API -> Backend Route -> Controller -> Service -> Database -> Response -> Tests`
Verify that parameters, data formats, and authentication tokens propagate consistently across each layer.

## 4. Requirement Analysis & Source Tagging
Every expectation must be tagged with an explicit requirement source:
- `user_requirement`: Constraints stated explicitly by the user in the prompt. Must quote user input.
- `product_documentation`: Specifications from README, design docs, or specs. Must cite file and section.
- `api_contract`: Formal schemas, OpenAPI specs, or TypeScript interface definitions. Must cite contract file.
- `existing_test`: Assertions verified by passing tests. Must cite test file and function.
- `inferred_assumption`: Hypotheses deduced from conventions or naming patterns.

> [!IMPORTANT]
> **The Critical Rule for Inferred Assumptions:**
> Hypotheses must NEVER silently become authoritative requirements. If code differs from an inferred assumption, report it as an observation with status **`UNKNOWN`** and request user confirmation. Never manufacture a `FAIL` simply because code differs from convention.

## 5. Journey Checkpoints Formulation
Formulate discrete, ordered checkpoints covering:
1. **Happy Path:** Expected successful execution flow.
2. **Authentication / Authorization:** Route access control and session verification.
3. **Storage Persistence:** Database rows created or updated.
4. **Validation & Error Handling:** Bad input rejection (HTTP 400/422) without leaking server internals.

## 6. Safe Execution & Baseline Isolation
Execute checks safely using native agent tools or the optional Python CLI:
- **Pre-action Baseline:** Record initial state (e.g. initial inventory count = 10).
- **Execution:** Dispatch HTTP request or test command targeting disposable test state.
- **Post-action Observation:** Record final observed state (e.g. final inventory count = 8).
- **Delta Verification:** Compare observed delta against expected change.
- **Contamination Guard:** If a prior check fails and leaves test state polluted, reset state or abort subsequent checks as **`UNKNOWN`**.

## 7. Defect Isolation
When an observation directly contradicts an authoritative expectation, mark the checkpoint **`FAIL`** and capture:
- The exact failure message or HTTP response code.
- Sanitized payload and headers.
- Timestamp and execution duration.

## 8. Root Cause Analysis
Trace backward from the observed failure to the responsible source file and line range:
- Pinpoint the exact file and lines (`src/services/checkout.py:L54-L62`).
- Explain the mechanism of failure (e.g., missing transaction commit, unhandled exception, inverted comparison).

## 9. Minimal Fix Proposal
Formulate a minimal, surgical fix:
- Follow the Ladder of Minimal Intervention: eliminate dead code first, reuse existing helpers, use platform standard library, and author the smallest complete patch.
- **Never apply code modifications without explicit user approval.**

## 10. Regression Verification
Upon user approval to apply the fix:
- Re-run failing checkpoints to confirm they now evaluate to **`PASS`**.
- Re-run adjacent test suites to ensure no regressions were introduced.

## 11. Evidence-Backed Reporting
Generate a structured Markdown report including:
- Project Context Summary.
- Language & Framework Capability Matrix.
- Checkpoint Results Table (Status, Expected, Observed, Requirement Source).
- Detailed Defect Analysis & Root Causes.
- Before / After Verification Measurements.
- Residual Limitations.
