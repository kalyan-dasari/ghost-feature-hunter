# Ghost Hunt Verification & Repository Audit Report

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
| `<Language / Framework 1>` | Yes | `<Full AST analysis | Partial | Inventory-only>` | `<Explicit limitations>` |
| `<Language / Framework 2>` | Yes | `<Full AST analysis | Partial | Inventory-only>` | `<Explicit limitations>` |

---

## 1. Executive Summary

| Total Checkpoints / Findings | PASS / Resolved | FAIL / Confirmed Defects | Ghost Features / Mismatches | UNKNOWN / Unfinished |
|---|---|---|---|---|
| `<total>` | `<pass_count>` | `<fail_count>` | `<ghost_feature_count>` | `<unknown_count>` |

**Summary Assessment:**  
<1-3 sentence summary of the feature's actual runtime behavior or repository health, and whether it is safe for release.>

---

## 2. Checkpoint Breakdown (Mode: `/ghost-hunt investigate` or `/ghost-hunt verify`)

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

### Ghost Feature Candidates (Broken or Disconnected Chains)
| ID | Chain Stage | Severity | Confidence | Evidence / Location | Summary |
|---|---|---|---|---|---|
| `ghost-1` | `UI Navigation -> Page` | Medium | High | `nav.tsx:L12` | Link to `/billing` has no matching page or route |
| `ghost-2` | `UI Action -> Handler` | Medium | High | `button.tsx:L45` | Button rendered with empty `onClick={() => {}}` |
| `ghost-3` | `Client -> API Mismatch` | High | High | `client.js:L30` | Client sends `POST /api/orders`, route only accepts `GET` |

### Empty & Unfinished Implementation Candidates
| ID | Item Type | Confidence | Location | Explanation | Why Intentional? |
|---|---|---|---|---|---|
| `unf-1` | `empty_function` | High | `api/reports.py:L20` | Handler contains only `pass` | Planned endpoint stub |
| `unf-2` | `silent_catch` | High | `client.ts:L88` | Catch block swallows error with `{}` | Ignoring benign network abort |

### Route & Testing Gap Candidates
| Finding ID | Category | Severity | Confidence | Location | Summary |
|---|---|---|---|---|---|
| `FIND-01` | `missing_route` | High | Medium | `frontend/shop.js:L42` | Calls `/api/users/profile`, no matching backend handler |
| `FIND-02` | `potentially_unused_endpoint` | Low | Low | `src/api/admin.py:L80` | Endpoint has 0 static callers (Requires Owner Confirmation) |
| `FIND-03` | `testing_gap` | Medium | High | `src/api/orders.py:L55` | Route has no corresponding test references in test suite |

### Structural Duplicate Logic & Code Waste
| Duplicate Block | Locations | Waste Lines | Type |
|---|---|---|---|
| `calc_tax_us / calc_tax_eu` | `tax_us.py:L10`, `tax_eu.py:L10` | 12 lines | Exact structural duplication |

*Total Measurable Code Waste: `<duplicate_lines>` non-overlapping lines.*

---

## 6. Unverified Areas & Inferred Assumptions

The following items could not be affirmatively proven and remain **UNKNOWN**:
- `<Inferred Assumption 1: Explanation of why it was inferred and request for confirmation>`
- `<Limitation 1: e.g. Deep AST analysis for Go/Rust is not implemented; inspected via file inventory>`
- `<Limitation 2: e.g. External webhooks require live signature verification and were evaluated statically>`

---

## 7. Verification Commands & Reproducibility

To independently reproduce this verification:
```bash
# Exact commands used during investigation
<command_1>
<command_2>
```
