# Root-Cause Investigation & Minimal Fix Proposal

When a verification checkpoint yields a **`FAIL`** status, follow this disciplined diagnostic protocol to isolate the root cause, cite exact source locations, and propose a minimal, targeted fix.

---

## 1. Dissect the Observed Failure

Do not jump immediately to solutions. First establish the exact empirical boundary of the defect:
1. **Checkpoint ID & Target:** What specific contract or behavior broke?
2. **Authoritative Expectation:** What was expected (and why is it expected: user prompt, API contract, documentation)?
3. **Actual Empirical Observation:** What did the check observe? (e.g., HTTP 500 instead of 200, calculated total 1200 instead of 1100, row count 0 instead of 1).
4. **Captured Evidence:** Relevant payloads, status codes, query outputs, or console logs.

---

## 2. Reverse Execution Tracing

Trace backward from the failure point into the application source code:

```text
[Failure Observed]
  │
  ├── Browser DOM Assertion Failed?
  │   └── Inspect frontend template/component -> JavaScript fetch handler -> client state.
  │
  ├── HTTP Status / Body Mismatch?
  │   ├── Controller / Route Handler: Inspect request parsing and response building.
  │   ├── Service Layer / Business Logic: Inspect calculations, conditionals, and validation branches.
  │   └── Exception Handlers: Look for swallowed exceptions or generic 500 error blocks.
  │
  └── Database State Mismatch?
      ├── Transaction Handling: Was `db.commit()` omitted, or was there an unhandled rollback?
      ├── Field Mapping: Were payload values mapped to wrong columns or overwritten?
      └── Concurrency / Locking: Did a race condition or stale cache cause the mismatch?
```

Always cite the **exact source file and line number**:
`src/services/billing.py:L142-L149`

---

## 3. Distinguish Confirmed Facts from Hypotheses

Maintain rigorous scientific discipline:
- **Confirmed Fact:** An empirically verified truth backed by observable code and runtime outputs.
  - *Example:* "Line 84 of `app.py` computes `tax = subtotal * tax_rate` without rounding, and line 92 adds tax twice."
- **Working Hypothesis:** An unconfirmed suspicion or theory.
  - *Example:* "The checkout may also fail if multiple items have different tax rates, but this was not yet tested."

> [!WARNING]
> Never state a hypothesis as a proven fact in your diagnosis. Clearly label hypotheses as things to verify.

---

## 4. Minimal Targeted Fix Proposal

Follow the principle of surgical intervention:
1. **Propose the Smallest Effective Diff:** Fix *only* the specific defect that caused the failure. Do not combine the fix with aesthetic refactoring, variable renaming, or unrelated dependency updates.
2. **Preserve Surrounding Invariants:** Ensure the fix does not break adjacent functions or modify public function signatures unexpectedly.
3. **Show Before & After Code Blocks:** Present the exact proposed diff clearly to the user.
4. **Strict Authorization Gate:** **NEVER edit code files without explicit user consent.** Always ask:
   > "I have identified the root cause in `app.py:L84`. Would you like me to apply this minimal fix?"

