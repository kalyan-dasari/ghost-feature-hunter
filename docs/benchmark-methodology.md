# Ghost Hunt — Benchmark Methodology & Evaluation Framework

This document outlines the evaluation methodology, benchmark suite, and comparative scoring system used to validate Ghost Hunt against real-world defect discovery and verification tasks.

---

## 1. Objective & Evaluation Principles

The goal of this benchmark is to quantify whether coding agents can:
1. **Accurately identify disconnected or broken feature paths** across multi-tier applications.
2. **Distinguish superficial static mentions from genuine runtime execution**.
3. **Avoid false PASS claims** when tests or verification steps fail or are incomplete.
4. **Preserve application safety** by refusing unapproved database writes or production mutations.

---

## 2. Benchmark Suite: `broken-flask-shop`

The primary benchmark harness is located in `examples/broken-flask-shop/` and orchestrated via `tests/benchmark/test_broken_shop_benchmark.py`.

It contains **15 deliberately injected real-world defects**:

| Defect ID | Category | Description | Primary Checkpoint |
|---|---|---|---|
| `cart-double-tax` | Calculation / Logic | Cart total calculates and applies sales tax twice. | `cart-total` |
| `draft-not-persisted` | Persistence / Mocking | Draft creation endpoint returns HTTP 201 but fails to write a row to storage. | `draft-persistence` |
| `duplicate-order` | Idempotency | Checkout accepts identical idempotency keys repeatedly, generating duplicate charges. | `duplicate-order` |
| `quantity-validation` | Input Validation | Checkout accepts negative or zero quantities. | `quantity-validation` |
| `payment-failure` | Gateway / State | Payment failure is mishandled, marking order as successfully paid. | `payment-failure` |
| `missing-authentication` | Security / Access | Order history listing is accessible without auth token. | `authentication-required` |
| `order-ownership` | Security / Tenancy | Order detail endpoint fails to verify customer ownership before serving records. | `order-ownership` |
| `state-transition` | State Machine | Order status allows invalid state transitions (e.g., `cancelled` -> `shipped`). | `state-transition` |
| `required-fields` | Input Validation | Missing required shipping address fields accepted without 400 Bad Request. | `required-fields` |
| `notification-missing` | Event / Worker | Order completion acknowledges email dispatch without queueing notification. | `notification-delivery` |
| `empty-cart` | Business Rules | Checkout succeeds on an empty cart. | `empty-cart` |
| `inventory-reduction` | Data Integrity | Inventory decrements by 1 regardless of order quantity purchased. | `inventory-reduction` |
| `partial-transaction` | Data Integrity | Order row commits even when subsequent inventory reduction raises an exception. | `partial-transaction` |
| `error-handling` | Reliability / Debug | Internal server errors leak stack trace in 200 OK wrapper. | `error-handling` |
| `stale-frontend-state` | Contract / Client | Client callback drops response payload and fails to update frontend UI state. | `stale-order-state` |

---

## 3. Comparative Evaluation Framework

We evaluate three operational modes:

### Mode 1: No Skill (Baseline AI Agent)
- The agent is given only the user bug report without structured investigation methodology.
- **Typical Failure Modes**:
  - Checks if code "looks right" statically without tracing callers.
  - Mistakenly claims feature works because endpoint exists.
  - Suggests superficial edits that fix symptoms without fixing database transaction or client state.
  - High rate of **False PASS** (assumes mock response means feature works).

### Mode 2: Generic Quality / Review Prompt
- The agent is instructed with generic engineering checklists (e.g., "check tests, inspect types, verify error handling").
- **Typical Failure Modes**:
  - Overwhelmed by false positives in fixtures, test mocks, and examples.
  - Fails to trace multi-file boundaries (e.g. React JSX button -> fetch -> Flask route -> service -> SQLite).
  - Assumes test presence implies test assertion of the specific route.

### Mode 3: Ghost Hunt (8-Layer Feature Investigation)
- The agent runs `/ghost-hunt` or uses `ghost-hunter` CLI.
- **Key Differentiators**:
  - **8-Layer Connection Mapping**: Explicitly links `UI -> Client API -> Route -> Controller -> Service -> Database -> Response -> Test`.
  - **Source-Role Classification**: Disregards fixtures and examples when reporting repository defects.
  - **Adversarial Test Assertion Inspection**: Confirms tests actually assert response status or body, discarding passive mentions.
  - **Safe Execution Boundary**: Strict write permissions, timeouts, and redaction.
  - **No Assumption Policy**: Returns `UNKNOWN` with limitation notes rather than false `PASS`.

---

## 4. Benchmark Scoring Criteria

For each defect:
1. **Detection Accuracy**: Was the defect correctly isolated to the responsible layer and file?
2. **False Positive Rate**: Did the investigation invent non-existent defects in working code?
3. **Evidence Integrity**: Was the finding accompanied by verifiable source line references and contract issues?
4. **Fix Precision**: Did the proposed patch resolve the root cause without side effects?
5. **Regression Verification**: Did post-fix verification confirm all checkpoints pass while preserving untouched functionality?

The benchmark suite in `tests/benchmark/test_broken_shop_benchmark.py` runs programmatically against live server instances with ephemeral database state, verifying that Ghost Hunt produces reproducible, deterministic results.
