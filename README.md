# Ghost Hunt (`ghost-hunt`)

> **DON'T TRUST THE FEATURE. VERIFY IT.**

**Ghost Hunt** is an open-source Agent Skill that helps AI coding agents investigate software features, trace end-to-end data flow, run safe verification checks, identify confirmed defects, explain root causes, and verify fixes using evidence.

---

## 💡 Why Ghost Hunt?

AI coding agents are remarkably good at generating code that *looks* correct. However, code that looks plausible often fails in production due to broken data flow, missing validations, silent transaction rollbacks, or mismatched assumptions between frontend, backend, and database.

When asked to test a feature, coding agents often default to superficial code reviews, or write unit tests that encode the same flawed assumptions as the implementation.

**Ghost Hunt gives your agent an empirical verification discipline.** It teaches your coding agent to:
1. Map full-stack data flow across routes, controllers, services, database models, and UI templates.
2. Formulate discrete, testable checkpoints anchored to explicit requirement sources.
3. Execute real, safe runtime checks using its native tools.
4. Classify observations under a strict truth table (**`PASS`**, **`FAIL`**, **`UNKNOWN`**).
5. Isolate confirmed defects to exact source lines and explain root causes.
6. Propose surgical, minimal fixes for user approval and verify them against regressions.

---

## 🤖 Supported Coding Agents

Ghost Hunt is designed around the open [Agent Skills specification](https://skills.sh/) and works with leading AI coding agents:

| Agent | Invocation Syntax | Project Installation Directory |
|---|---|---|
| **Google Antigravity** | `/ghost-hunt` or `/ghost-hunt investigate <feature>` | `<project-root>/.agents/skills/ghost-hunt/` |
| **Anthropic Claude Code** | `/ghost-hunt` or `/ghost-hunt investigate <feature>` | `<project-root>/.claude/skills/ghost-hunt/` |
| **OpenAI Codex** | `$ghost-hunt` or `$ghost-hunt investigate <feature>` | `<project-root>/.agents/skills/ghost-hunt/` |

---

## ⚡ Quick Install

Install the canonical Agent Skill directly into your workspace with one command using the official Skills CLI (requires **Node.js 22.20.0+**):

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

The CLI will prompt you to choose your agent. You can also specify your target agent directly:

```console
# Google Antigravity
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity

# Anthropic Claude Code
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent claude-code

# OpenAI Codex
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent codex
```

### Manual Installation
If you prefer not to use `npx`, copy the canonical [`skills/ghost-hunt/`](skills/ghost-hunt/) directory into your project:
- **Google Antigravity:** `.agents/skills/ghost-hunt/`
- **Anthropic Claude Code:** `.claude/skills/ghost-hunt/`
- **OpenAI Codex:** `.agents/skills/ghost-hunt/`

Keep `SKILL.md`, `references/`, `templates/`, and `examples/` together in the directory.

---

## 🚀 How to Invoke in Chat

Once installed, open your coding agent in your project workspace and invoke Ghost Hunt using one of its four modes:

| Mode | Command | What It Does |
|---|---|---|
| **Feature Discovery** | `/ghost-hunt discover` | Statically inspects the project, detects frameworks, maps route architecture, and presents available features without executing code. |
| **Feature Investigation** | `/ghost-hunt investigate <feature>` | Performs deep, end-to-end data flow tracing and active verification of a specific feature across frontend, API, services, and database. |
| **Repository Audit** | `/ghost-hunt audit` | Performs a whole-repository static audit: maps route connections, detects missing route candidates, identifies potentially unused endpoints, flags duplicate code, and discovers testing gaps. |
| **Verification & Fix** | `/ghost-hunt verify <feature>` | Runs targeted regression checks for a previously identified defect, reviews proposed surgical fixes, and verifies fix efficacy. |

*(Codex users: use `$ghost-hunt` prefix).*

### Bare Invocation Safety Guard
If you invoke `/ghost-hunt investigate` without specifying a feature target:
1. Ghost Hunt locks scope to your **actual active project** (reading `git rev-parse --show-toplevel`, project manifests, and package names).
2. It explicitly ignores bundled example fixtures (such as `examples/`, `fixtures/`, `benchmarks/`).
3. It presents a standardized **Project Context Summary**, performs lightweight discovery, and prompts you to select a feature to investigate. **It never arbitrarily picks a benchmark or demo application.**

You can also ask in natural language:
- *"Investigate my checkout feature and verify whether inventory deduction works."*
- *"Audit the repository for disconnected routes, unused endpoints, and untested core logic."*
- *"Verify user registration: check password hashing, email uniqueness, and 400 validation responses."*

---

## 🌟 The Three Core Capabilities

1. **Multi-Language Discovery & Scope Lock:** Understands project structure before selecting targets. Distinguishes monorepo workspaces and benchmark fixtures from primary application code. Declares transparent analysis capabilities for Python, JavaScript/TypeScript, and unsupported ecosystems.
2. **Individual Feature Investigation:** Traces cross-boundary data flow, isolates stateful test scenarios to prevent contamination, and validates expectations against authoritative requirement sources.
3. **Ghost Feature Detection & Whole-Repository Audit:** Constructs a feature connection graph across 8 architectural layers to unmask disconnected features, missing routes, method mismatches, empty implementations, orphaned services, and structural code duplication.

---

## 🔍 Clear Finding Classifications

Ghost Hunt clearly distinguishes between different classes of findings so developers can act with confidence:

| Finding Category | Meaning | Confidence | Required Action |
|---|---|---|---|
| **Confirmed Defect (`FAIL`)** | Real runtime check failed against an authoritative requirement. | High / Evidence-backed | Propose surgical fix diff with line references. |
| **Ghost Feature Candidate** | Feature appears in one layer (UI, link, button, route) but has a missing, disconnected, or incomplete implementation path. | High / Medium | Complete the broken link in the feature chain or remove dead interface elements. |
| **Empty / Unfinished Candidate** | Function, route handler, or button has only `pass`, `...`, `NotImplementedError`, or `onClick={() => {}}` (excluding abstract methods/interfaces). | High / Medium | Complete implementation or document intentional stub behavior. |
| **Missing Route Candidate** | Frontend or client code calls an endpoint (`fetch`, `axios`) that has no matching backend route. | Medium / Static Candidate | Confirm whether route is handled externally or missing. |
| **Method / Path Mismatch** | Client requests an endpoint with an HTTP method (e.g. `POST`) not accepted by the backend route (e.g. `GET`). | High / Static Candidate | Align allowed route methods or update client request. |
| **Potentially Unused Route / Dep** | Backend route or package declared but no references found in codebase. | Low / Heuristic Candidate | Verify against external webhooks, mobile clients, and dynamic dispatch before removal (`Requires Owner Confirmation`). |
| **Structural Duplicate Code** | Functions with different or identical names sharing identical normalized syntax bodies. | High / Measurable | Unify duplicate logic and eliminate redundant maintenance lines. |
| **Testing Gap** | Critical business logic or mutation route has zero test coverage in the existing test suite. | High / Measurable | Author targeted regression tests. |
| **Inferred Assumption** | Expected behavior deduced from code patterns or naming rather than explicit specs. | Unconfirmed Hypothesis | **Evaluates to UNKNOWN, never PASS or FAIL.** Must be confirmed by project owner. |

---

## 🛠️ Dual Execution Modes

Ghost Hunt separates the universal Agent Skill from the optional Python engine:

| Mode | Prerequisites | When to Use | Capabilities |
|---|---|---|---|
| **Native Agent Tools (Default)** | **None.** Works in any repo immediately. | Interactive chat, ad-hoc feature debugging, rapid exploration. | The agent uses its built-in file search, terminal commands (`curl`, test runners, Python/Node scripts), and browser tools. |
| **Deterministic CLI Engine (Optional)** | Python 3.11+ (`pip install "ghost-feature-hunter[all]"`) | CI/CD automated gates, reproducible JSON audit artifacts. | Executes hermetic JSON journeys via `ghost-hunter audit <feature>` with schema validation, path containment, and automated report rendering. |

*Crucial Rule:* Never claim a tool was executed if it was not available. Missing tools or unreachable services always produce **`UNKNOWN`**.

---

## 🧭 The 11-Step Investigation Protocol

When invoked, Ghost Hunt executes this disciplined verification workflow:

```text
1. Feature Scope ──> 2. Static Discovery ──> 3. Flow Tracing ──> 4. Requirements
                                                                         │
7. Defect Isolation <── 6. Safe Execution <── 5. Journey Checkpoints <───┘
│
└──> 8. Root Cause ──> 9. Minimal Fix ──> 10. Regression ──> 11. Evidence Report
```

1. **Feature Scope:** Parse user intent, personas, and entry points.
2. **Static Discovery:** Statically inspect routes, controllers, DB models, templates, and existing tests without running untrusted code.
3. **Flow Tracing:** Trace data flow: UI -> API endpoint -> controller -> service logic -> database -> response.
4. **Requirement Analysis:** Anchor expectations to explicit sources (`user_requirement`, `product_documentation`, `api_contract`, `existing_test`). Hypotheses are flagged as `inferred_assumption` and require user confirmation.
5. **Journey Checkpoints:** Structure discrete checkpoints covering happy path, auth, persistence, and error paths.
6. **Safe Execution:** Run safe checks using `curl`, test commands, read-only DB queries, and browser tools.
7. **Defect Isolation:** Record discrepancies as confirmed defects (**`FAIL`**).
8. **Root Cause Analysis:** Trace backward to exact source files and line ranges (`path/to/file.py:L42-L55`).
9. **Minimal Fix Proposal:** Present the smallest surgical patch for user approval. **Never modify code without authorization.**
10. **Regression Verification:** Re-verify failing checkpoints and adjacent test suites after fix approval.
11. **Evidence-Backed Report:** Output a structured Markdown report with pass/fail breakdown and evidence references.

---

## ⚖️ The Three-Status Evidence Truth Table

Ghost Hunt classifies every verification checkpoint into exactly one of three states. Never infer unasserted behavior:

| Status | Exact Definition | Permissible Interpretation |
|---|---|---|
| **`PASS`** | A check ran and its observed result matched the explicit expectation. | Proves **only** the executed assertion. Never infer unasserted behavior. |
| **`FAIL`** | An executed check directly contradicted an explicit expected behavior. | Proves the feature broke at this specific checkpoint. |
| **`UNKNOWN`** | Prerequisites, runtimes, permissions, or evidence were unavailable. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

---

## 📊 Example Evidence-Backed Result

Every Ghost Hunt report begins with a mandatory **Project Context Summary** locking the target scope, followed by checkpoint findings and isolated defects:

```markdown
# Ghost Hunt: Feature Audit Report

### Project Context Summary
| Property | Value |
|---|---|
| **Detected Project Name** | `broken-flask-shop` |
| **Project Root** | `examples/broken-flask-shop` |
| **Git Root** | `/workspace/ghost-feature-hunter` |
| **Application Type** | `Flask (Python)` |
| **Investigation Target** | `checkout` (`/api/checkout`, `POST`) |
| **Target Classification** | `Benchmark / Example Application` |

---

### Verification Summary
- **Feature:** checkout
- **Status:** FAIL (3 confirmed defects isolated)
- **Checkpoints:** 5 Total | 2 PASS | 3 FAIL | 0 UNKNOWN

### Checkpoint Breakdown
| Checkpoint | Expected | Observed | Status | Source | Evidence |
|---|---|---|---|---|---|
| `cart-tax` | `total_cents: 1100` | `total_cents: 1200` | FAIL | `api_contract` | HTTP 200 response |
| `idempotency` | HTTP 201 on first, 409 on replay | HTTP 201, then HTTP 409 | PASS | `product_documentation` | HTTP responses |
| `quantity-val` | HTTP 400 on negative qty | HTTP 201 Created (ord-883) | FAIL | `product_documentation` | HTTP 201 response |
| `persistence` | 1 confirmed row in SQLite | 1 row, state='confirmed' | PASS | `api_contract` | sqlite3 query |
| `inventory-qty`| Stock decremented by 2 (10 -> 8) | Stock decremented by 1 (10 -> 9) | FAIL | `product_documentation` | sqlite3 before/after delta |

### Confirmed Defect: Inadequate Inventory Deduction (`inventory-qty`)
- **Location:** `app.py:L180-L184`
- **Root Cause:** The SQL update unconditionally decrements stock by 1 unit (`stock = MAX(stock - 1, 0)`) instead of subtracting the cart item's actual requested quantity.
- **Recommended Minimal Fix:**
  ```diff
  - UPDATE products SET stock = MAX(stock - 1, 0) WHERE id = ?
  + UPDATE products SET stock = MAX(stock - ?, 0) WHERE id = ?
  ```
```

👉 **[Read the Full Checkout Investigation Walkthrough](skills/ghost-hunt/examples/checkout-investigation.md)**

---

## 🔒 Stateful Scenario Isolation & False PASS Prevention

Testing stateful workflows (e.g., checkout, order processing, inventory decrement) introduces a critical failure mode: **test state contamination**.

If test steps run sequentially against the same database, mutations from earlier checks can contaminate the initial state of subsequent checks. In a naive test run, an earlier negative-quantity check unexpectedly decremented stock from 10 to 9. A subsequent check requesting 2 units then reduced stock from 9 to 8. A naive assertion checking only `stock == 8` evaluated to `PASS`—falsely masking that purchasing 2 units had only decremented 1 unit!

Ghost Hunt eliminates false PASS results through four isolation rules:
1. **Fresh Disposable State:** Every stateful scenario starts with a freshly seeded database copy or transaction rollback.
2. **Explicit Baseline Measurement:** The agent measures the baseline state *before* execution (e.g., `initial_stock = 10`), executes the action (quantity = 2), and measures the delta *after* execution (`final_stock = 9`).
3. **Delta Assertions:** Assertions verify the exact transition (`final == initial - quantity`), never just the ending absolute value.
4. **PASS Evidence Contract:** `PASS` requires verifiable before/after data proving the expected transition occurred. Missing baseline evidence degrades the status to `UNKNOWN`.

---

## 🛡️ Safety Defaults & Operational Tiers

Ghost Hunt is designed to run safely inside existing codebases by enforcing four operational safety levels:

| Tier | Category | Safety Policy | Permitted Actions |
|---|---|---|---|
| **Level 1** | **Source Inspection** | **Safe by default.** | Static file discovery, AST parsing, test file reading. Never imports or runs untrusted application code to discover structure. |
| **Level 2** | **Runtime Read-Only** | **Safe in test environments.** | Safe HTTP probes (`GET`, `HEAD`, `OPTIONS`) and read-only database queries (`SELECT` only, capped at 1,000 rows). |
| **Level 3** | **Runtime Mutations** | **Requires user authorization.** | State-altering HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) and browser form submissions. Must target disposable test environments with synthetic data. |
| **Level 4** | **Database Writes** | **Strictly isolated.** | Direct database mutations (`INSERT`, `UPDATE`, `DELETE`). Strictly prohibited against production databases. Restricted to disposable temporary databases with cleanup and re-seeding. |

### Absolute Guardrails:
- **Production Guardrail:** All checks against production environments are blocked by default.
- **Credential Redaction:** Passwords, API keys, Bearer tokens, and email addresses are automatically redacted from evidence logs.
- **No Code Edits Without Approval:** Proposed fixes are always presented as diffs for user authorization before applying changes.

---

## 🔧 Optional Deterministic Python CLI

For automated CI/CD pipelines, regression test suites, and schema-validated JSON reports, the optional Python CLI is available:

```bash
# Install with all extras (Python 3.11+)
pip install "ghost-feature-hunter[all]"

# Initialize project configuration (creates ghost-hunter.json)
ghost-hunter init --project-root .

# Advisory static discovery
ghost-hunter discover --project-root .

# Static route connection and hygiene audit
ghost-hunter audit-routes --project-root .

# Execute verification journey
ghost-hunter audit checkout --project-root .

# Audit with write permissions for mutating endpoints
ghost-hunter audit checkout --project-root . --allow-writes

# Overwrite previous reports
ghost-hunter audit checkout --project-root . --force
```

See [docs/installation.md](docs/installation.md) and [docs/safety.md](docs/safety.md) for CLI options and security configurations.

---

## ⚠️ Prerequisites & Limitations

- **Agent Skill Prerequisites:** Installing via `npx skills add` requires **Node.js 22.20.0+**. Using the skill in chat requires no runtime dependencies; the agent uses its native tools.
- **Optional CLI Prerequisites:** Requires **Python 3.11+**. Browser checks require Playwright and Chromium (`playwright install chromium`).
- **Browser Automation:** Browser checks depend on the agent's available browser capabilities or headless Playwright. If unavailable in the host environment, checks are honestly reported as **`UNKNOWN`** with actionable diagnostics.
- **Database Scope:** The optional CLI database adapter currently supports file-backed SQLite with C-level read-only query authorizers. Agents using native tools can inspect other databases using native CLI clients, following Level 2/4 safety rules.
- **Honest Evidence:** Ghost Hunt never converts assumptions into facts or claims tests passed when tools were unavailable.

---

## 🏷️ Version Mapping

| Component | Current Version | Role |
|---|---|---|
| **Agent Skill (`ghost-hunt`)** | `0.3.0` | Canonical Agent Skill for AI coding agents |
| **Python CLI Engine (`ghost-feature-hunter`)** | `0.2.0` | Optional deterministic verification engine and CI companion |
| **Public Repository Release** | `v0.3.0` | GitHub project release tag |

---

## 📂 Repository Structure

```text
ghost-feature-hunter/
├── skills/ghost-hunt/               # Canonical Agent Skill (Agent Skills standard)
│   ├── SKILL.md                     # Skill instructions for coding agents (<200 lines)
│   ├── references/                  # Specialized workflow references (progressive disclosure)
│   ├── templates/                   # Reusable report and journey templates
│   └── examples/                    # Real-world investigation walkthroughs
├── .agents/skills/ghost-hunt/       # Synchronized mirror for local agent execution
├── src/ghost_hunter/                # Optional Python verification engine
│   ├── adapters/                    # HTTP, SQLite, and isolated Playwright adapters
│   ├── discovery/                   # Static AST discovery
│   └── reporting/                   # JSON and Markdown report rendering
├── examples/broken-flask-shop/      # 15-defect benchmark application
├── integrations/                    # Platform integration guides (Antigravity, Claude, Codex)
├── docs/                            # Architectural, safety, and installation documentation
└── tests/                           # Unit, integration, and benchmark test suites
```

---

## 🤝 Contributing & Community

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

```bash
# Clone and install development dependencies
git clone https://github.com/kalyan-dasari/ghost-feature-hunter.git
cd ghost-feature-hunter
python -m pip install -e ".[all]"

# Run test suite
python -m pytest
```

---

## License

MIT © Ghost Feature Hunter contributors.
