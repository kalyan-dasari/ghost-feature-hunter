# Installation and platform setup

## Install

The v0.1.0 source is not published to a package index yet. From a checkout, use Python 3.11 or newer in a virtual environment:

```console
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

From a source checkout, install the project with the capabilities you need:

```console
python -m pip install -e ".[dev,demo,browser]"
python -m playwright install chromium
```

The browser binary is managed by Playwright and is not included in the Python package. Basic CLI, HTTP, and SQLite checks do not require Flask or Playwright.

## First run

```console
ghost-hunter init --project-root .
# Edit ghost-hunter.json and journeys/health.json.
ghost-hunter discover --project-root .
ghost-hunter audit health --project-root .
ghost-hunter report ghost-reports/ghost-report.json --force
```

`init` refuses to replace an existing config or sample journey. Audit and discovery refuse to replace existing report files unless `--force` is passed. `audit` returns exit code 1 when an explicit assertion fails.

## Install the agent skill

### Quick install via Agent Skills CLI
Install the skill into your current workspace or global agent environment:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-feature-hunter
```

### Manual installation
Copy the canonical `skills/ghost-feature-hunter` directory:

- **Google Antigravity:** copy it to `.agents/skills/ghost-feature-hunter/` in the project or `<appDataDir>/skills/ghost-feature-hunter/` for global user availability. Keep `SKILL.md` and `references/` together.
- **Claude Code:** copy it to `.claude/skills/ghost-feature-hunter/` in the project or `~/.claude/skills/ghost-feature-hunter/` for user-wide availability.
- **Codex / OpenAI Agents:** copy it to `.agents/skills/ghost-feature-hunter/` in the project root.

The compatibility notes under `integrations/` point to the canonical skill. They do not contain separate verification engines. Install the CLI from the checkout root with `python -m pip install -e .` (or include the optional extras above).

## Supported discovery

Static discovery is implemented for Flask-style Python route decorators and common SQLAlchemy model bases. It is advisory and does not establish runtime behavior. Other framework route conventions are not currently supported. HTTP, SQLite read-only, and browser checks are executed only from explicit journey steps. Test-suite and log checks are deferred beyond v0.1.0.
