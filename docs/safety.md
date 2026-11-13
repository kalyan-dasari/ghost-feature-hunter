# Security & Safety Model

Ghost Hunt inspects and verifies application features in environments that may contain sensitive data, credentials, and source code. It is an empirical developer tool and Agent Skill, not an unrestricted sandbox.

---

## 1. The Four Operational Safety Levels

Whether executed directly by an AI coding agent or through the optional Python CLI engine, Ghost Hunt strictly adheres to four operational tiers:

### Level 1 — Source-Code Read-Only Inspection (Safe by default)
- Static file reading, AST parsing, and test inspection.
- Identifies routes, controllers, models, and test fixtures without importing or executing untrusted application code.
- No side effects on the environment or code files.

### Level 2 — Runtime Read-Only Checks (Safe in test environments)
- Non-mutating HTTP methods (`GET`, `HEAD`, `OPTIONS`) to inspect endpoints and responses.
- Read-only database queries (`SELECT` only). Queries are guarded at the SQLite C-engine level via connection authorizers and capped at 1,000 rows.
- Permitted against local test and development targets matching configured `base_url` or `allowed_hosts`.

### Level 3 — Runtime Mutating Operations (Requires User Authorization)
- State-altering HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) and browser form submissions.
- **Requires explicit user authorization.** In the Python CLI, this requires both `"allow_writes": true` in `ghost-hunter.json` and `--allow-writes` on the command line. In interactive chat, the agent must ask for user authorization before issuing mutating calls against running services.
- Must execute against disposable, isolated test targets with synthetic data.
- Must strictly isolate stateful scenarios to prevent state contamination between sequential checks.

### Level 4 — Database Write Operations (Strictly Isolated)
- Direct database mutations (`INSERT`, `UPDATE`, `DELETE`, `DROP`).
- **Strictly prohibited against production databases.**
- Restricted to disposable temporary databases (e.g. SQLite test copies or test containers).
- Must include explicit cleanup and re-seeding controls so test state from earlier runs does not contaminate subsequent verification outcomes.

---

## 2. Stateful Scenario Isolation & False PASS Prevention

Testing stateful application features (e.g., shopping cart checkout, order confirmation, inventory decrement, wallet balance deduction) introduces the risk of **test state contamination**.

When verification checks are executed sequentially against a shared database:
- Side effects from Check A (e.g., an earlier test with invalid negative quantities that erroneously decremented stock from 10 to 9) alter the initial conditions of Check B.
- If Check B then purchases 2 units and decrements stock from 9 to 8, a naive verification check asserting `stock == 8` evaluates to **`PASS`**.
- This produces a **false PASS**: it masks the critical bug that purchasing 2 units only decremented stock by 1 unit (`stock - 1`), simply because `9 - 1 == 8`!

### Mandatory Scenario Isolation Rules:
1. **Fresh Disposable Databases:** Every scenario must run against a fresh database copy or transaction rollback. Never share mutable state across independent verification scenarios.
2. **Deterministic Initial Seeding:** Tables must be seeded with known initial values before the scenario executes (e.g., product stock set to `10`).
3. **Explicit Before-and-After Baseline Measurements:**
   - **Before:** Query and record the baseline value (`initial_stock = 10`).
   - **Execute:** Perform the action (e.g., purchase 2 units).
   - **After:** Query and record the post-execution value (`final_stock`).
4. **Delta Evaluation:** Assertions must evaluate the delta (`final_stock == initial_stock - quantity`), never just an assumed absolute ending state.
5. **PASS Evidence Contract:** A `PASS` status is prohibited without recorded baseline and post-execution evidence. If baseline evidence is unavailable, the result must be reported as `UNKNOWN`.

---

## 3. Absolute Safety Guardrails

### Production Protection
- Any target environment configured as `production` is blocked by default.
- In the Python CLI, production runs are aborted unless `production_approved: true` is configured and `--approve-production` is explicitly passed on the CLI.
- AI agents in chat mode must block mutating actions against production systems.

### Credential & Sensitive Data Redaction
- Evidence logs automatically sanitize authorization headers (Bearer tokens, Basic auth), cookies, and API keys (`[REDACTED]`).
- Fields matching common secret names (`password`, `secret`, `api_key`, `token`, `private_key`) are masked.
- Email addresses and physical database file paths are masked in textual evidence.
- HTTP response bodies are capped at 2 MB; payloads are not copied wholesale into reports.

### No Code Modifications Without Approval
- Ghost Hunt diagnoses defects and isolates root causes, but **never modifies application source code without explicit user authorization**.
- Fixes are presented as minimal diffs with risk assessments.

### Report Path Containment
- Report generation strictly isolates files to the project root directory by default.
- The `--force` flag controls file overwrite permission and **never** bypasses filesystem containment.
- Writing reports outside the project root requires the explicit `--allow-external-output` flag. Overwriting an existing external file requires both `--allow-external-output` and `--force`.

### Browser Worker Process Isolation
- Browser checks execute in an isolated worker subprocess with OS-level process tree termination (Windows Job Objects / POSIX process groups) enforcing a configurable hard deadline (`timeout_seconds`).
- Deadlocked or hung browser drivers are cleanly terminated and return **`UNKNOWN`** with actionable diagnostic information.

---

## 4. Limits & User Responsibilities

- **Redaction is Best Effort:** Automatic redaction cannot guarantee detection of every proprietary string or secret. Never run verification journeys against production credentials.
- **Reports are Unsigned:** Saved Markdown and JSON reports are plain text developer artifacts and can be edited. Always review the journey steps and captured evidence before sharing.
- **Disposable Infrastructure:** When testing stateful flows (such as checkout, billing, or inventory), always point the agent or CLI to an isolated, disposable test database and ephemeral test server.

---

## 5. Reporting Security Issues

Please report security issues privately to the repository maintainers before public disclosure. Do not include live credentials or sensitive personal data in issue reports.
