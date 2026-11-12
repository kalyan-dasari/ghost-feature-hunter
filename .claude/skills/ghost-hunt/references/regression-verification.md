# Regression Verification: Proving Fixes End-to-End

After an approved fix is applied to the application code, execute this workflow to confirm the defect is resolved and verify that adjacent functionality remains intact.

---

## 1. Re-run Verification Checks

Re-execute the exact failing checkpoint under identical conditions:
- **Native Agent Mode:** Rerun the specific `curl`, browser interaction, or database query that previously failed. Confirm the observation now matches the expected behavior.
- **Optional CLI Mode:**
  ```console
  ghost-hunter audit <feature> --force
  ```
  *(Include `--allow-writes` if mutating actions are involved).*

---

## 2. Before-and-After Evidence Comparison

Evaluate the verification outcome across the 4 regression states:

| Outcome State | Status Before | Status After | Meaning & Required Action |
|---|---|---|---|
| **RESOLVED** | `FAIL` | `PASS` | **Success:** The fix is verified with empirical evidence. |
| **PERSISTING** | `FAIL` | `FAIL` | **Ineffective:** The defect remains unresolved. Re-examine root cause. |
| **REGRESSION** | `PASS` | `FAIL` | **Critical:** The fix introduced a regression in previously working behavior. Revert immediately. |
| **UNVERIFIED** | Any | `UNKNOWN` | **Indeterminate:** Rerun was blocked by missing tools, credentials, or target unavailability. |

---

## 3. Adjacent Test Suite Execution

Always run the project's existing test suite to ensure the fix did not break surrounding modules:
```bash
# Python
pytest

# Node / TypeScript
npm test

# Go / Rust
go test ./... / cargo test
```

---

## 4. Document Resolution Evidence

Include the before-and-after comparison in your final report:
- Name the checkpoint ID.
- Show what changed in the empirical observation (e.g. `total_cents: 1200` -> `total_cents: 1100`).
- Cite the git diff or modified file lines.
