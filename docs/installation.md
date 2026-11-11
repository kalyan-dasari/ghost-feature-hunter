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

The canonical skill is `skills/ghost-feature-hunter/SKILL.md`; its supporting references are next to it. Copy the complete `ghost-feature-hunter` directory to the corresponding skill location:

- **Codex:** copy it to `.agents/skills/ghost-feature-hunter/` in the project or `~/.agents/skills/ghost-feature-hunter/` for the user. See the [official Codex installation guidance](https://developers.openai.com/api/reference/cli).
- **Claude Code:** copy it to `.claude/skills/ghost-feature-hunter/` in the project or `~/.claude/skills/ghost-feature-hunter/` for the user. The directory should contain `SKILL.md` and `references/`; see [Claude Code skills documentation](https://code.claude.com/docs/en/skills).
- **Google Antigravity:** copy it to `.agents/skills/ghost-feature-hunter/` in the project or `~/.gemini/config/skills/ghost-feature-hunter/` for the user. Keep `SKILL.md` and `references/` together; see [Antigravity skills documentation](https://antigravity.google/docs/skills).

The compatibility notes under `integrations/` point to the canonical skill. They do not contain separate verification engines. Install the CLI from the checkout root with `python -m pip install -e .` (or include the optional extras above).

## Supported discovery

Static discovery is implemented for Flask-style Python route decorators and common SQLAlchemy model bases. It is advisory and does not establish runtime behavior. Other framework route conventions are not currently supported. HTTP, SQLite read-only, and browser checks are executed only from explicit journey steps. Test-suite and log checks are deferred beyond v0.1.0.
