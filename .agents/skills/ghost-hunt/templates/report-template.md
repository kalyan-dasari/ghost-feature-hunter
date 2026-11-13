# Ghost Hunt Verification Report

### Project Context Summary
- **Project Name:** `<project_name>`
- **Project Root:** `<path_to_project_root>`
- **Git Repository Root:** `<git_root_or_none>`
- **Selected Application Root:** `<app_root>`
- **Framework & Languages:** `<frameworks_and_languages>`
- **Investigation Mode:** `<discover | investigate | audit | verify>`
- **Included Directories:** `<included_directories>`
- **Excluded Directories:** `<excluded_directories (e.g. examples, vendor, tests)>`
- **Available Capabilities:** `<native_tools_available (file, shell, curl, browser)>`
- **Limitations:** `<unsupported_runtimes_or_mocked_services>`

---

## 1. Executive Summary

| Total Checkpoints | PASS | FAIL | UNKNOWN | Pass Rate |
|---|---|---|---|---|
| `<total>` | `<pass_count>` | `<fail_count>` | `<unknown_count>` | `<percentage>%` |

**Summary Assessment:**  
<1-3 sentence summary of the feature's actual runtime behavior or repository health, and whether it is safe for release.>

---

## 2. Checkpoint Breakdown

| # | Checkpoint ID | Expectation | Actual Observation | Status | Source of Expectation | Evidence Reference |
|---|---|---|---|---|---|---|
| 1 | `cp-1-endpoint` | Returns HTTP 200 with order payload | HTTP 200 observed | **PASS** | `api_contract` (`docs/api.json:L40`) | `http:/api/checkout` |
| 2 | `cp-2-stock-deduct`| Stock decrements from 10 to 8 | Stock became 9 | **FAIL** | `product_documentation` (`README.md#L45`) | `db:sqlite:products` |
| 3 | `cp-3-browser-flow`| User completes payment in UI | Browser runtime unavailable | **UNKNOWN** | `user_requirement` (prompt quote) | `none` |

### Expectation Provenance Key:
- `user_requirement`: Explicit user constraint from prompt (must quote prompt).
- `product_documentation`: Documented in README or docs (must cite file/section).
- `api_contract`: Formal schema or interface (must cite contract file).
- `existing_test`: Asserted in existing test suite (must cite test function).
- `inferred_assumption`: Inferred convention; unconfirmed assumptions evaluate to **`UNKNOWN`**.

---

## 3. Stateful Scenario Measurements (Before & After)

*Required for all persistence, stock, inventory, balance, or state-changing checks:*

| Checkpoint ID | Baseline Initial State | Test Input Action | Expected Final State | Observed Final State | Delta Verified | Isolation Status |
|---|---|---|---|---|---|---|
| `stock-deduct` | `stock = 10` (seeded) | Purchase 2 units | `stock = 8` | `stock = 9` | ❌ FAILED (`-1` instead of `-2`) | Fresh Disposable DB |

---

## 4. Confirmed Defects & Root-Cause Diagnosis

### Defect 1: `<checkpoint_id>` — `<short_description>`
- **Observed Behavior:** `<what actually happened>`
- **Expected Behavior:** `<what was supposed to happen according to requirements>`
- **Source Location:** `<file_path>:<line_range>` (e.g. `src/api/checkout.py:L42-L55`)
- **Root Cause Analysis:**
  `<Clear explanation of the exact code defect, missing commit, logic error, or race condition.>`
- **Recommended Minimal Fix:**
  ```diff
  - old_broken_code()
  + new_fixed_code()
  ```
- **Risk Assessment:** `<Low | Medium | High>` — `<Side effect analysis>`

---

## 5. Repository Audit Findings (Mode: `/ghost-hunt audit`)

*Include when running whole-repository audit mode:*

| Finding ID | Category | Severity | Confidence | Location | Summary |
|---|---|---|---|---|---|
| `FIND-01` | `missing_route` | High | Medium | `frontend/shop.js:L42` | Calls `/api/users/profile`, no matching backend handler |
| `FIND-02` | `potentially_unused_endpoint` | Low | Low | `src/api/admin.py:L80` | Endpoint has 0 static callers, tests, or doc references |
| `FIND-03` | `uncovered_route` | Medium | High | `src/api/orders.py:L55` | Route has no corresponding test references in test suite |

---

## 6. Unverified Areas & Inferred Assumptions

The following items could not be affirmatively proven and remain **UNKNOWN**:
- `<Inferred Assumption 1: Explanation of why it was inferred and request for confirmation>`
- `<Limitation 1: e.g. Browser runtime was unavailable in execution environment>`
- `<Limitation 2: e.g. Payment gateway webhooks were mocked and not verified live>`

---

## 7. Verification Commands & Reproducibility

To independently reproduce this verification:
```bash
# Exact commands used during investigation
<command_1>
<command_2>
```
