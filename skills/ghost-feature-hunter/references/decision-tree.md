# Workflow & Adapter Decision Trees

Use these decision trees to determine the exact workflow and adapter required for an investigation.

---

## 1. Primary Workflow Selection

```text
Where are you in the investigation?
│
├── Feature is unknown or unmapped?
│   └── Go to: Workflow 1 (Feature discovery) & Workflow 2 (Feature understanding)
│
├── Requirements or acceptance criteria are vague?
│   └── Go to: Workflow 3 (Requirement & acceptance criteria analysis)
│
├── No journey JSON exists for this feature?
│   └── Go to: Workflow 4 (Journey generation) -> Workflow 5 (Journey validation)
│
├── Journey JSON exists and is validated?
│   └── Ready for execution! Select adapter:
│       ├── Validating REST/GraphQL endpoint? ─────────> Workflow 6 (API verification)
│       ├── Validating user-facing DOM/UI flow? ───────> Workflow 7 (Browser verification)
│       ├── Validating persistence or database state? ─> Workflow 8 (Database verification)
│       ├── Validating roles/tenancy/auth tokens? ─────> Workflow 9 (Authorization verification)
│       └── Validating edge cases/validation errors? ──> Workflow 10 (Error-path verification)
│
├── Audit ran and at least one checkpoint is FAIL?
│   └── Go to: Workflow 11 (Root-cause investigation)
│
└── Developer applied a fix?
    └── Go to: Workflow 12 (Regression verification) -> Workflow 13 (Evidence analysis) -> Workflow 14 (Report generation)
```

---

## 2. Adapter Selection Matrix

| Verification Target | Primary Adapter | Fallback / Complementary | Required Approvals |
|---|---|---|---|
| HTTP Status, Response Body, Headers | `http` | None | Read: None; Write: `--allow-writes` |
| Idempotency, Request Validation | `http` | `database` | Write: `--allow-writes` |
| DOM Elements, UI Form Submissions, Reactivity | `browser` | `http` | Read: None; Write: `--allow-writes` |
| Database Row Counts, Column Values, Persistence | `database` | `http` | Read: None (writes strictly blocked) |
| Multi-tenant Ownership Isolation | `http` | `database` | Read: None |
| Unauthenticated / Expired Token Behavior | `http` | None | Read: None |

---

## 3. Safety Gate Decision Tree

```text
Is the target environment configured as "production"?
│
├── YES ──> Are BOTH "production_approved: true" in config AND "--approve-production" passed?
│           ├── YES ──> Allow execution under strict audit log.
│           └── NO  ──> BLOCK immediately. Mark status UNKNOWN ("Production target blocked").
└── NO  ──> Proceed to method check.

Does the checkpoint require non-read HTTP (POST/PUT/PATCH/DELETE) or browser click/fill?
│
├── YES ──> Are BOTH "allow_writes: true" in config AND "--allow-writes" passed?
│           ├── YES ──> Allow mutating action.
│           └── NO  ──> BLOCK mutating action. Mark status UNKNOWN ("Write request blocked").
└── NO  ──> Allow read execution (GET/HEAD/OPTIONS).
```

