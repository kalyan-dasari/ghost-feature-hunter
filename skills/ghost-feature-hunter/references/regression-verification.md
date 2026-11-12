# Regression Verification (Workflow 12)

After an approved fix is applied to the application code, execute this workflow to prove the defect is resolved and verify that adjacent functionality remains intact.

---

## 1. Re-run the Verification Journey

Run the affected journey using the same configuration and test environment:

```console
ghost-hunter audit <feature> --project-root <path> --force
```

*(Pass `--allow-writes` if the journey includes mutating HTTP or browser actions).*

---

## 2. Compare Before-and-After Evidence

Examine the new `ghost-report.json` against the initial audit report:

| State | Checkpoint Status Before | Checkpoint Status After | Interpretation |
|---|---|---|---|
| **RESOLVED** | `FAIL` | `PASS` | Defect is confirmed fixed with verifiable evidence. |
| **PERSISTING** | `FAIL` | `FAIL` | Fix was ineffective; continue investigation. |
| **REGRESSION** | `PASS` | `FAIL` | Fix broke previously working functionality! Immediate rollback needed. |
| **UNVERIFIED** | Any | `UNKNOWN` | Prerequisite missing or network issue during rerun. |

---

## 3. Run Adjacent Automated Tests

Run existing unit and integration test suites covering adjacent modules to ensure no regressions were introduced:

```console
pytest tests/
```

Confirm all existing test suites pass.

---

## 4. Archive Audit History

When preserving an audit trail:
- Avoid clobbering historical reports: copy the original `ghost-report.json` to `ghost-reports/baseline-<feature>.json` before re-running with `--force`.
- Include the before-and-after evidence comparison in your final summary to the operator.
