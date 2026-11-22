# Installation & Setup Guide

Ghost Hunt is an open-source, **skill-first** software verification system.

You can install the Agent Skill into your coding agent with a single command and begin verifying features immediately using your agent's native tools. The Python CLI engine is an optional addition for deterministic CI pipelines and automated regression gates.

---

## 1. Install the Agent Skill (`ghost-hunt`)

### Prerequisites
- **Node.js 22.20.0+** (required by the Agent Skills CLI `skills@latest`).
- An active coding agent environment: **Google Antigravity**, **Anthropic Claude Code**, or **OpenAI Codex**.

### Quick Install via Skills CLI

Run the following command from your project root:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

The CLI will prompt you to choose your agent:
- **Google Antigravity:** `.agents/skills/ghost-hunt/`
- **Anthropic Claude Code:** `.claude/skills/ghost-hunt/`
- **OpenAI Codex:** `.agents/skills/ghost-hunt/`

### Direct Non-Interactive Installation

To skip interactive prompts and install directly for a specific agent, use the `--agent` flag with `--copy`:

```console
# Google Antigravity
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity

# Anthropic Claude Code
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent claude-code

# OpenAI Codex
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent codex

# All Supported Agents
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent '*'
```

### Global User Installation
To install the skill globally so it is accessible across all projects on your machine, pass `-g`:

```console
# Google Antigravity
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent antigravity

# Anthropic Claude Code
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent claude-code

# OpenAI Codex
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent codex
```

#### Skills CLI Installation Targets:
| Target Agent | Project-Level Path | Global User Path (`-g`) |
|---|---|---|
| **Google Antigravity** | `<project-root>/.agents/skills/ghost-hunt/` | `~/.gemini/config/skills/ghost-hunt/` |
| **Anthropic Claude Code** | `<project-root>/.claude/skills/ghost-hunt/` | `~/.claude/skills/ghost-hunt/` |
| **OpenAI Codex** | `<project-root>/.agents/skills/ghost-hunt/` | `~/.agents/skills/ghost-hunt/` |

### Manual Installation
If you prefer not to use `npx`, copy the canonical [`skills/ghost-hunt/`](../skills/ghost-hunt/) directory directly into your agent's configuration:

- **Google Antigravity:**
  - Workspace: `<project-root>/.agents/skills/ghost-hunt/` (recommended)
  - Global: `~/.gemini/antigravity/skills/ghost-hunt/` or `~/.gemini/config/skills/ghost-hunt/`
- **Anthropic Claude Code:**
  - Project: `<project-root>/.claude/skills/ghost-hunt/`
  - Global: `~/.claude/skills/ghost-hunt/`
- **OpenAI Codex:**
  - Project: `<project-root>/.agents/skills/ghost-hunt/`
  - Global: `~/.agents/skills/ghost-hunt/`

Ensure `SKILL.md`, `references/`, `templates/`, and `examples/` are preserved together in the directory.

---

## 2. Confirming & Managing the Installation

### Verify Installed Skills
Run the Skills CLI list command:
```console
# List project skills
npx skills list

# List global skills
npx skills list -g
```

You should see `ghost-hunt` listed under your target agent.

### Updating Ghost Hunt
To update Ghost Hunt to the latest version:
```console
# Project update
npx skills update ghost-hunt

# Global update
npx skills update ghost-hunt -g
```

### Removing Ghost Hunt
To uninstall the skill:
```console
# Remove from project
npx skills remove ghost-hunt

# Remove from global
npx skills remove ghost-hunt -g
```

---

## 3. Using the Skill in Chat

Open your coding agent in your project workspace and invoke Ghost Hunt using one of its six execution modes:

```text
# 1. Project & Feature Discovery
/ghost-hunt discover

# 2. 8-Layer Feature Connection Map (UI -> Client -> Route -> Service -> DB -> Response -> Tests)
/ghost-hunt map checkout

# 3. End-to-End Feature Investigation & Safe Active Verification
/ghost-hunt investigate checkout

# 4. Whole-Repository Static Audit (Ghost features, stubs, route mismatches, dead code)
/ghost-hunt audit

# 5. Code Change Review (Diff inspection against surrounding call graph)
/ghost-hunt review [target]

# 6. Fix Verification & Regression Check
/ghost-hunt verify checkout
```

*(For OpenAI Codex, replace `/ghost-hunt` with `$ghost-hunt`).*

### Bare Invocation Guard
If you run `/ghost-hunt` or `/ghost-hunt investigate` without parameters, Ghost Hunt will:
1. Detect and lock your project root and Git context.
2. Filter out bundled benchmark or example directories (such as `examples/broken-flask-shop`).
3. Display the Project Context Summary and ask you to select a feature to investigate.

You can also invoke in natural language:
- *"Investigate my checkout feature and verify whether inventory deduction works."*
- *"Show me the connection map for billing and identify any broken contracts."*
- *"Audit the repository for route mismatches, unused endpoints, and testing gaps."*
- *"Review my uncommitted changes for broken wiring, data risks, and test gaps."*
- *"Verify user registration: check password hashing, email uniqueness, and 400 validation responses."*

The skill executes immediately using your agent's native tools (file reading, terminal commands, `curl`, test runners, and browser).

### Troubleshooting Skill Visibility
- If `/ghost-hunt` does not appear in your agent's autocomplete:
  1. Restart your agent or reload the IDE window.
  2. Verify that `.agents/skills/ghost-hunt/SKILL.md` (or `.claude/skills/ghost-hunt/SKILL.md`) exists in your project root.
  3. Ensure the YAML frontmatter in `SKILL.md` begins with `name: ghost-hunt`.

---

## 4. How to Use Ghost Hunt in Your Other Projects (FAQ)

### Q: Do I need to copy the Python codebase (`src/`, `pyproject.toml`) into my other projects?
**No!** Ghost Hunt is **skill-first**. When you use Ghost Hunt inside an AI coding agent (like Google Antigravity, Claude Code, or Codex), the agent reads the skill instructions in `SKILL.md` and uses its own built-in tools (file reading, AST parsing, terminal execution, tests) to inspect and verify that project. You do **not** need Python installed, and you do **not** copy the Python engine.

### Q: What files need to be in my other project?
Only the **Agent Skill folder** (`skills/ghost-hunt/`):

```text
my-other-project/
├── .agents/
│   └── skills/
│       └── ghost-hunt/
│           ├── SKILL.md
│           ├── references/
│           ├── templates/
│           └── examples/
├── src/               <-- your other project's source code
├── package.json       (or go.mod, Cargo.toml, pyproject.toml, etc.)
└── ...
```

### Q: How do I add it to another project?

#### Method 1: Using the Skills CLI (One-Line Install)
In your other project directory, run:
```bash
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity
```

#### Method 2: Manual Copy
Simply copy `skills/ghost-hunt/` into `.agents/skills/ghost-hunt/`:
```bash
# On Linux / macOS:
cp -r /path/to/ghost-feature-hunter/skills/ghost-hunt my-other-project/.agents/skills/ghost-hunt

# On Windows (PowerShell):
Copy-Item -Path "K:\Big Things\ghost-feature-hunter\skills\ghost-hunt" -Destination "C:\path\to\my-other-project\.agents\skills\ghost-hunt" -Recurse -Force
```

### Q: Can I use Ghost Hunt across all my projects without copying files to each one?
**Yes! Use Global Installation.** Install the skill once into your agent's user directory:
- **Google Antigravity:** `~/.gemini/antigravity/builtin/skills/ghost-hunt/` or `~/.gemini/config/skills/ghost-hunt/`
- **Anthropic Claude Code:** `~/.claude/skills/ghost-hunt/`
- **OpenAI Codex:** `~/.agents/skills/ghost-hunt/`

```bash
# Or via CLI globally:
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent antigravity
```
Once installed globally, you can open **any project on your computer** and immediately use `/ghost-hunt` without creating any skill files in that project.

### Q: When do I need the Python package (`ghost-feature-hunter`)?
Only install the Python package (`pip install ghost-feature-hunter`) if you want to run automated terminal commands (`ghost-hunter map`, `ghost-hunter plan`, `ghost-hunter audit`) in headless scripts or CI/CD pipelines (such as GitHub Actions) without an interactive chat agent.

---

## 5. Optional Deterministic CLI Verification Engine

If you want hermetic, automated verification journeys for CI pipelines and schema-validated JSON reports, install the optional `ghost-feature-hunter` Python package.

### Prerequisites
- **Python 3.11+**
- `pip` or virtual environment manager

### Installation
```console
# From PyPI with all extras
pip install "ghost-feature-hunter[all]"

# Or from source checkout
git clone https://github.com/kalyan-dasari/ghost-feature-hunter.git
cd ghost-feature-hunter
python -m pip install -e ".[all]"

# Install Chromium browser for Playwright checks (optional)
python -m playwright install chromium
```

### Optional CLI Commands:
```console
# Initialize project configuration (creates ghost-hunter.json and starter journey)
ghost-hunter init --project-root .

# Advisory static discovery
ghost-hunter discover --project-root .

# 8-layer feature connection map and cross-layer contract verification
ghost-hunter map [feature] --project-root . [--mermaid] [--json]

# Plan an explicit verification journey from static analysis
ghost-hunter plan <feature> --project-root . [--output OUTPUT]

# Comprehensive multi-language repository & ghost feature audit
ghost-hunter audit-repo --project-root .

# Static route connection and hygiene audit
ghost-hunter audit-routes --project-root .

# Review code changes and call graph for wiring defects
ghost-hunter review [target]

# Execute verification journey
ghost-hunter audit <feature> --project-root .

# Audit with write permissions for mutating endpoints
ghost-hunter audit <feature> --project-root . --allow-writes

# Replace previous reports
ghost-hunter audit <feature> --project-root . --force
```
