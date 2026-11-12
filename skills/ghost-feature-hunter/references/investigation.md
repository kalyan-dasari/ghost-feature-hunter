# Root-Cause Investigation (Workflow 11)

When an audit produces a `FAIL` checkpoint, follow this disciplined root-cause investigation procedure.

---

## 1. Dissect the Observed Failure

Inspect both `ghost-reports/ghost-report.json` and `ghost-reports/ghost-report.md`.
Identify:
1. **Checkpoint ID & Description:** Exactly what behavior was being verified.
2. **Authoritative Expectation:** What outcome was expected and the source of that requirement.
3. **Actual Observation:** What the adapter actually observed (status code, returned JSON, query count, DOM state).
4. **Captured Evidence:** Reference URL, timestamp, sanitized parameters, and response headers.

---

## 2. Trace the Failure Through the Codebase

Trace backwards from the failure point to find the origin of the discrepancy:

```text
[Failure Observed]
  │
  ├── Browser DOM failed assertion?
  │   └── Inspect frontend script, component render logic, or API response handling.
  │
  ├── HTTP Status / Body unexpected?
  │   ├── Route Handler / Controller: Did validation fail, or did it catch an internal exception?
  │   ├── Service Layer / Business Logic: Where was the computation or business rule applied?
  │   └── External Integrations: Did a third-party dependency return an error?
  │
  └── Database state mismatch?
      ├── Transaction Rollback: Was db.commit() called prematurely or omitted?
      ├── Data Mapping: Were fields correctly mapped from payload to schema?
      └── Partial Commit: Did failure occur after an earlier non-atomic commit?
```

Always cite the **exact source file and line number** in your diagnosis (e.g. `app.py:104`).

---

## 3. Classify Hypotheses vs. Confirmed Facts

- **Confirmed Fact:** An objective observation backed by verifiable evidence (e.g., "The HTTP response status was 200, but line 195 of app.py catches all exceptions and returns HTTP 200").
- **Working Hypothesis:** An unproven suspicion (e.g., "The database row was likely not inserted because the connection pool timed out").

> [!WARNING]
> Keep root-cause claims strictly proportional to code and runtime evidence. Label unverified explanations as hypotheses.

---

## 4. Recommend Minimal Targeted Fixes

1. Propose the **smallest possible change** that resolves the contradiction between expected and observed behavior.
2. Avoid broad refactorings, unrelated cleanups, or dependency upgrades during a defect fix.
3. Add or update a regression assertion in the journey file to prevent recurrence.
4. **Safety Rule:** Never modify application source code without explicit user authorization. Propose the patch and ask the operator to approve it.
