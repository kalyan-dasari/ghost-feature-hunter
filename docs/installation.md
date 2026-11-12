# Installation & Setup Guide

Ghost Hunt is a **skill-first** open-source verification system.

You can install the Agent Skill into your coding agent with a single command and begin verifying features immediately using your agent's native tools. The Python CLI engine is an optional addition for deterministic CI pipelines.

---

## 1. Install the Agent Skill (`ghost-hunt`)

### One-Line Install via Agent Skills CLI
Install the skill into your current project or user profile:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

The CLI will prompt you to choose your agent:
- **Google Antigravity:** `.agents/skills/ghost-hunt/`
- **Anthropic Claude Code:** `.claude/skills/ghost-hunt/`
- **OpenAI Codex:** `.agents/skills/ghost-hunt/`

### Manual Installation
Copy the canonical `skills/ghost-hunt/` directory into your agent's skills location:

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

## 2. Using the Skill in Chat

Open your coding agent in the target application repository and invoke:

- **Antigravity:** `/ghost-hunt` or `/ghost-hunt investigate checkout`
- **Claude Code:** `/ghost-hunt` or `/ghost-hunt investigate checkout`
- **OpenAI Codex:** `$ghost-hunt` or `$ghost-hunt investigate checkout`
- **Natural Language:** *"Investigate my checkout feature and verify whether inventory deduction works."*

The skill executes immediately using your agent's native tools (file reading, terminal commands, `curl`, test runners, and browser).

---

## 3. Optional Deterministic CLI Verification Engine

If you want hermetic, automated verification journeys for CI pipelines and schema-validated JSON reports, install the optional `ghost-hunter` Python package:

```console
# From source checkout
python -m pip install -e ".[dev,demo,browser]"

# Install Chromium browser for Playwright checks
python -m playwright install chromium
```

### Optional CLI Commands:
```console
# Initialize project configuration
ghost-hunter init --project-root .

# Advisory static discovery
ghost-hunter discover --project-root .

# Execute verification journey
ghost-hunter audit <feature> --project-root .

# Replace previous reports
ghost-hunter audit <feature> --project-root . --force
```
