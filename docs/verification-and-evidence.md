# Verification Discipline & Evidence Integrity

Ghost Hunt operates on an empirical verification philosophy: **software features are never assumed to work based on plausible code appearance.** A feature is only verified when executed against explicit checkpoints with uncontaminated, observable evidence.

---

## 1. The Three-Status Evidence Truth Table

Ghost Hunt classifies every verification checkpoint into exactly one of three states. Never infer unasserted behavior or convert uncertainty into a pass:

| Status | Exact Definition | Permissible Interpretation | Prohibited Interpretation |
|---|---|---|---|
| **`PASS`** | A check ran and its observed result affirmatively matched an explicit, authoritative requirement. | Proves **only** the executed assertion. | Never infer unasserted behavior or assume untested edge cases work. |
| **`FAIL`** | An executed check directly contradicted an explicit expected behavior. | Proves the feature broke at this specific checkpoint. | Never discard failures as "minor" or assume downstream code compensates. |
| **`UNKNOWN`** | Prerequisites, runtimes, clean databases, permissions, or evidence were unavailable. | Indicates an unverified checkpoint requiring developer attention. | **NEVER relabel UNKNOWN as PASS or FAIL.** |

---

## 2. The PASS Evidence Contract

A checkpoint may only receive a `PASS` rating if all of the following conditions are met:

1. **Uncontaminated State:** The check ran against a clean environment or recorded explicit baseline state.
2. **Authoritative Requirement:** The assertion was derived from a verified requirement source (`user_requirement`, `product_documentation`, `api_contract`, or `existing_test`).
3. **Affirmative Observation:** The observed status code, database row, or UI state directly matched the expected outcome.
4. **Verifiable Reference:** The result records a timestamped, sanitized evidence item (`http:POST:http://127.0.0.1:5000/api/checkout`, `database:sqlite:read-only-query`).

> [!WARNING]
> **Static Inspection Never Implies Runtime PASS:**
> Merely discovering that a route exists, that an 8-layer map is connected, or that a function contains logic can NEVER award a runtime `PASS`. Static analysis produces architectural candidates; runtime execution proves behavior.

---

## 3. Stateful Scenario Isolation & Baseline Evidence

Stateful features (e.g. inventory decrements, account balance transfers, cart checkouts) are highly vulnerable to **test state contamination**. If prior checks leave residue in the database, subsequent checks may produce false passes or false failures.

Ghost Hunt mandates the **Delta Verification Pattern**:

```mermaid
sequenceDiagram
    participant Runner as Verification Engine / Agent
    participant DB as Isolated Database
    participant App as Target Application

    Note over Runner,DB: 1. Baseline Observation
    Runner->>DB: Query initial value (e.g., initial_stock = 10)
    
    Note over Runner,App: 2. Target Execution
    Runner->>App: Execute check (purchase quantity = 2)
    App->>DB: Apply mutation
    
    Note over Runner,DB: 3. Final Observation & Delta
    Runner->>DB: Query final value (observed_stock = 8)
    Runner->>Runner: Evaluate delta: 10 - 2 = 8 (PASS)
```

If the baseline state cannot be established or if a prior check leaves the database in an undefined state, all subsequent checks must report **`UNKNOWN`** with a state contamination explanation.

---

## 4. Automatic Credential Redaction & Sanitization

Ghost Hunt guarantees that sensitive secrets never leak into generated reports, logs, or chat transcripts:

- **Redacted HTTP Headers:** `Authorization` (Bearer, Basic), `X-Api-Key`, `Cookie`, `Set-Cookie`.
- **Redacted JSON Fields:** Any field matching `(?i)(password|secret|token|api_key|credential|private_key|auth)`.
- **Redacted PII:** Email addresses and phone numbers in evidence payloads are masked.
- **URL Sanitization:** Embedded credentials in URLs (`https://user:pass@host/path`) are stripped before storage.
- **Evidence Byte Caps:** HTTP response bodies are capped at 2 MB to prevent memory exhaustion and log bloat.

---

## 5. Four Operational Safety Tiers

Ghost Hunt categorizes all operations into four strict tiers:

| Tier | Category | Safety Policy | Permitted Actions |
|---|---|---|---|
| **Level 1** | **Source Inspection** | **Safe by default.** | Static file discovery, AST parsing, test reading. Never imports or executes untrusted code. |
| **Level 2** | **Runtime Read-Only** | **Safe in test environments.** | Safe HTTP probes (`GET`, `HEAD`, `OPTIONS`) and read-only database queries (`SELECT` only, capped at 1,000 rows). |
| **Level 3** | **Runtime Mutations** | **Requires user authorization.** | State-altering HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) and browser form submissions. Must target disposable test environments with synthetic data. |
| **Level 4** | **Database Writes** | **Strictly isolated.** | Direct database mutations (`INSERT`, `UPDATE`, `DELETE`). Strictly prohibited against production databases. Restricted to disposable temporary databases with cleanup and re-seeding. |

### Absolute Safety Rules:
- **Production Guardrail:** All requests against production environments are blocked by default. Requires dual approval in config (`production_approved = true`) and CLI (`--approve-production`).
- **No Unapproved Code Modifications:** Never modify application source files without presenting the minimal patch diff and receiving explicit user approval.
