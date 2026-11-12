# Ghost Hunt (`ghost-hunt`)

> **DON'T TRUST THE FEATURE. VERIFY IT.**

**Ghost Hunt** is an open-source, skill-first software verification tool for AI coding agents.

Instead of assuming a feature works because its code looks plausible, Ghost Hunt teaches your coding agent (Google Antigravity, Anthropic Claude Code, OpenAI Codex) to trace feature data flows end-to-end, run real safe checks, detect confirmed behavioral failures, pinpoint exact root causes, and verify fixes with reproducible evidence.

---

## ⚡ Quick Install

Install the canonical Agent Skill directly into your agent with one command (requires Node.js 18+):

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

The CLI will prompt you to select your target agent:
- **Google Antigravity** (`.agents/skills/ghost-hunt/`)
- **Anthropic Claude Code** (`.claude/skills/ghost-hunt/`)
- **OpenAI Codex** (`.agents/skills/ghost-hunt/`)

*Manual install:* Simply copy [`skills/ghost-hunt/`](skills/ghost-hunt/) into your agent's skill directory.

---

## 🚀 How to Invoke in Chat

Once installed, open your coding agent in any application project and invoke:

| Agent | Invocation |
|---|---|
| **Google Antigravity** | `/ghost-hunt` or `/ghost-hunt investigate <feature>` |
| **Anthropic Claude Code** | `/ghost-hunt` or `/ghost-hunt investigate <feature>` |
| **OpenAI Codex** | `$ghost-hunt` or `$ghost-hunt investigate <feature>` |
| **Natural Language** | *"Investigate my checkout feature and verify whether inventory deduction works."* |

---

## 🛠️ Dual Execution Modes

Ghost Hunt is architected to work immediately out of the box with zero runtime dependencies:

| Mode | Prerequisites | Capabilities |
|---|---|---|
| **Native Agent Tools (Default)** | **None.** Works in any repo immediately. | The agent uses its built-in file search, terminal commands (`curl`, test runners, Python/Node scripts), and browser automation tools. |
| **Deterministic CLI Engine (Optional)** | Python 3.11+ and `pip install "ghost-feature-hunter[all]"` | Executes hermetic JSON journeys via `ghost-hunter audit <feature>` with strict schema validation and report rendering for CI/CD pipelines. |

*Crucial Rule:* Never claim a tool was executed if it was not available.

---

## 🧭 The 11-Step Investigation Protocol

When you ask Ghost Hunt to investigate a feature, it executes this disciplined 11-step protocol:

```text
1. Feature Scope ──> 2. Static Discovery ──> 3. Flow Tracing ──> 4. Requirements
                                                                         │
7. Defect Isolation <── 6. Safe Execution <── 5. Journey Checkpoints <───┘
│
└──> 8. Root Cause ──> 9. Minimal Fix ──> 10. Regression ──> 11. Evidence Report
```

1. **Feature Scope:** Parse user intent, personas, and entry points.
2. **Static Discovery:** Find routes, controllers, database models, templates, and existing tests.
3. **Flow Tracing:** Trace data from frontend UI -> API endpoint -> service logic -> DB persistence.
4. **Requirement Analysis:** Classify expectations by source (`user_requirement`, `product_documentation`, `api_contract`, `existing_test`, `inferred_assumption`). Never invent requirements.
5. **Journey Checkpoints:** Structure discrete checkpoints covering happy path, auth, persistence, and error paths.
6. **Safe Execution:** Run safe checks using `curl`, test commands, read-only DB queries, and browser tools.
7. **Defect Isolation:** Record discrepancies as confirmed defects.
8. **Root Cause Analysis:** Trace backward into code and cite exact file and line numbers (`path/to/file.py:L42-L55`).
9. **Minimal Fix Proposal:** Present the smallest surgical patch for user approval. Never edit code without authorization.
10. **Regression Verification:** Re-verify the failing checkpoint and adjacent test suites after fix approval.
11. **Evidence-Backed Report:** Output a structured Markdown report with pass/fail breakdown and evidence references.

---

## ⚖️ The Three-Status Evidence Truth Table

Ghost Hunt classifies every verification checkpoint into exactly one of three states:

| Status | Exact Definition | Permissible Interpretation |
|---|---|---|
| **`PASS`** | A check ran and its observed result matched the explicit expectation. | Proves **only** the executed assertion. Never infer unasserted behavior. |
| **`FAIL`** | An executed check directly contradicted an explicit expected behavior. | Proves the feature broke at this specific checkpoint. |
| **`UNKNOWN`** | Prerequisites, runtimes, permissions, or evidence were unavailable. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

---

## 📖 Real-World Demonstration

See a complete walkthrough of `/ghost-hunt investigate checkout` executed against our 15-defect benchmark store:  
👉 **[Read the Checkout Investigation Walkthrough](skills/ghost-hunt/examples/checkout-investigation.md)**

---

## 🔧 Optional Deterministic Python CLI

For automated CI/CD test gates and machine-validated JSON artifacts, the optional Python CLI is available:

```bash
# Install with all extras
pip install "ghost-feature-hunter[all]"

# Initialize project configuration
ghost-hunter init --project-root .

# Advisory static discovery
ghost-hunter discover --project-root .

# Execute verification journey
ghost-hunter audit checkout --project-root .

# Overwrite previous reports
ghost-hunter audit checkout --project-root . --force
```

See [docs/installation.md](docs/installation.md) and [docs/safety.md](docs/safety.md) for CLI security policies and options.

---

## 📂 Repository Structure

```text
ghost-feature-hunter/
├── skills/ghost-hunt/               # The Primary Canonical Agent Skill
│   ├── SKILL.md                     # Skill instructions for coding agents (<200 lines)
│   ├── references/                  # Specialized workflow references (progressive disclosure)
│   ├── templates/                   # Reusable report and journey templates
│   └── examples/                    # Real-world investigation walkthroughs
├── src/ghost_hunter/                # Optional Python verification engine
│   ├── adapters/                    # HTTP, SQLite, and killable Playwright adapters
│   ├── discovery/                   # Static AST discovery
│   └── reporting/                   # JSON and Markdown report rendering
├── examples/broken-flask-shop/      # 15-defect benchmark application
├── integrations/                    # Platform integration guides (Antigravity, Claude, Codex)
└── tests/                           # Unit, integration, and benchmark test suites
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/safety.md](docs/safety.md).

```bash
# Run test suite
python -m pip install -e ".[dev,demo,browser]"
python -m pytest
```

---

## License

MIT © Ghost Feature Hunter contributors.
