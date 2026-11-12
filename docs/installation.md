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
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent claude-code
```

### Manual Installation
If you prefer not to use `npx`, copy the canonical [`skills/ghost-hunt/`](../skills/ghost-hunt/) directory directly into your agent's configuration:

- **Google Antigravity:**
  - Workspace: `.agents/skills/ghost-hunt/`
  - Global: `~/.gemini/antigravity/skills/ghost-hunt/`
- **Anthropic Claude Code:**
  - Project: `.claude/skills/ghost-hunt/`
  - Global: `~/.claude/skills/ghost-hunt/`
- **OpenAI Codex:**
  - Project: `.agents/skills/ghost-hunt/`
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

Open your coding agent in your project workspace and invoke:

- **Google Antigravity:** `/ghost-hunt` or `/ghost-hunt investigate checkout`
- **Anthropic Claude Code:** `/ghost-hunt` or `/ghost-hunt investigate checkout`
- **OpenAI Codex:** `$ghost-hunt` or `$ghost-hunt investigate checkout`
- **Natural Language:** *"Investigate my checkout feature and verify whether inventory deduction works."*

The skill executes immediately using your agent's native tools (file reading, terminal commands, `curl`, test runners, and browser).

### Troubleshooting Skill Visibility
- If `/ghost-hunt` does not appear in your agent's autocomplete:
  1. Restart your agent or reload the IDE window.
  2. Verify that `.agents/skills/ghost-hunt/SKILL.md` (or `.claude/skills/ghost-hunt/SKILL.md`) exists in your project root.
  3. Ensure the YAML frontmatter in `SKILL.md` begins with `name: ghost-hunt`.

---

## 4. Optional Deterministic CLI Verification Engine

If you want hermetic, automated verification journeys for CI pipelines and schema-validated JSON reports, install the optional `ghost-hunter` Python package.

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

# Execute verification journey
ghost-hunter audit <feature> --project-root .

# Audit with write permissions for mutating endpoints
ghost-hunter audit <feature> --project-root . --allow-writes

# Replace previous reports
ghost-hunter audit <feature> --project-root . --force
```
