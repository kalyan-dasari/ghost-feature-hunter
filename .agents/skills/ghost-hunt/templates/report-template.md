# Ghost Hunt: Feature Verification Report

**Feature:** `<feature_name>`  
**Date:** `<YYYY-MM-DDTHH:MM:SSZ>`  
**Environment:** `<development | test | staging | production>`  
**Target URL:** `<base_url>`  
**Execution Mode:** `<Native Agent Tools | Optional Deterministic CLI Engine>`  
**Overall Status:** `<PASS | FAIL | UNKNOWN>`

---

## 1. Executive Summary

| Total Checkpoints | PASS | FAIL | UNKNOWN | Pass Rate |
|---|---|---|---|---|
| `<total>` | `<pass_count>` | `<fail_count>` | `<unknown_count>` | `<percentage>%` |

**Summary Assessment:**  
<1-3 sentence summary of the feature's actual runtime behavior and whether it is safe for release.>

---

## 2. Checkpoint Breakdown

| # | Checkpoint ID | Expectation | Actual Observation | Status | Source of Expectation | Evidence Reference |
|---|---|---|---|---|---|---|
| 1 | `cp-1-endpoint` | Returns HTTP 200 with order payload | HTTP 200 observed | **PASS** | `api_contract` | `http:/api/checkout` |
| 2 | `cp-2-stock-deduct`| Stock decrements from 10 to 8 | Stock remained 10 | **FAIL** | `user_requirement` | `db:sqlite:products` |
| 3 | `cp-3-browser-flow`| User completes payment in UI | Browser runtime unavailable | **UNKNOWN** | `product_documentation` | `none` |

---

## 3. Confirmed Defects & Root-Cause Diagnosis

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

## 4. Unverified Areas & Limitations

The following aspects could not be definitively verified and remain **UNKNOWN**:
- `<Limitation 1: e.g. Browser runtime was unavailable in execution environment>`
- `<Limitation 2: e.g. Payment gateway webhooks were mocked and not verified live>`

---

## 5. Verification Commands & Reproducibility

To independently reproduce this verification:

```bash
# Checkpoint 1: API Check
curl -s -i "http://127.0.0.1:8000/api/checkout"

# Checkpoint 2: Database Check
sqlite3 data/app.sqlite3 "SELECT stock FROM products WHERE id = 1;"
```

