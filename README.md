# Ghost Feature Hunter

Ghost Feature Hunter checks whether a feature journey matches explicit, observable expectations. Its Python CLI runs independently of AI agents and produces evidence-backed JSON and Markdown reports.

**Status: beta, v0.2.0.** Ghost Feature Hunter is an open-source verification engine and standard Agent Skill. It validates software features against explicit, human-authored behavioral journeys across frontend, API, persistence, and delivery layers.

## Install

### 1. Install as an AI Agent Skill (Antigravity, Claude Code, Codex)

Using the Agent Skills open standard CLI:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-feature-hunter
```

Or copy `skills/ghost-feature-hunter/` to your agent's skill directory (`.agents/skills/` or `.claude/skills/`).

### 2. Install the Independent Python CLI

Python 3.11 or newer is required:

```console
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install .
```

Install optional capabilities only when needed:

```console
python -m pip install ".[browser]"     # Playwright package
python -m playwright install chromium  # Browser binary, installed separately
python -m pip install ".[demo]"        # Broken Flask shop benchmark
python -m pip install ".[dev,demo,browser]"  # Contributors and full test suite
```

## Quick start

```console
ghost-hunter init --project-root ./my-project
ghost-hunter discover --project-root ./my-project
```

Edit `my-project/ghost-hunter.json` and `my-project/journeys/health.json` to define a local base URL and explicit expected behavior, then run:

```console
ghost-hunter audit health --project-root ./my-project
ghost-hunter report ./my-project/ghost-reports/ghost-report.json --force
```

The audit writes `ghost-report.json` and `ghost-report.md` under the configured report directory. Existing reports are protected; pass `--force` to replace them. An audit with an explicit failed assertion exits with code 1.

## Safety defaults

- Discovery parses files statically; it does not import application code or execute commands found in files.
- HTTP calls use an explicitly configured target and host policy, do not follow redirects, and default to read methods. Write methods require `allow_writes: true` in project config and `--allow-writes` on the CLI.
- Production checks need `production_approved: true` in config and `--approve-production`.
- Database support is limited to bounded SELECT queries against file-backed SQLite using a read-only connection.
- Browser requests stay on the configured origin. Mutating HTTP methods and browser clicks/fills require write approval.
- Static discovery is advisory only; it never establishes runtime behavior.
- Sensitive values are redacted best-effort. Review reports before sharing.

Reports are unsigned files and can be edited. A PASS records that the configured assertion matched the observation captured by an adapter; it does not prove coverage beyond that assertion. Review the evidence and journey before treating a report as trustworthy.

Read [docs/safety.md](docs/safety.md) before pointing checks at real systems.

## Deliberately broken shop

The isolated [broken Flask shop](examples/broken-flask-shop/README.md) contains 15 documented defects and an explicit benchmark journey. Its scoring manifest is read only by benchmark tests after the journey runs; the engine never uses it to decide findings. Run it only on loopback with synthetic data.

## AI agent skill

The canonical Agent Skills entry point is [skills/ghost-feature-hunter/SKILL.md](skills/ghost-feature-hunter/SKILL.md), with supporting references in the same directory. Install that one skill for Codex, Claude Code, or Google Antigravity using [docs/installation.md](docs/installation.md). Platform notes point to the canonical source; they do not duplicate the engine.

## Supported adapters

| Capability | Dependency | Scope in v0.1 |
|---|---|---|
| HTTP API | HTTPX (core) | Explicit methods, response status, JSON path, and text assertions |
| Database | Python standard library | Bounded, read-only file-backed SQLite SELECT checks |
| Browser | Playwright (optional) | Same-origin Chromium actions and assertions |
| Discovery | Standard library | Static Flask route/model patterns, tests, frontend, likely services |

Test-suite execution and log phrase checks are deferred beyond v0.1. They do not contribute to release verification status.

See [docs/adapters.md](docs/adapters.md), [docs/architecture.md](docs/architecture.md), and [docs/installation.md](docs/installation.md) for details and limitations.

## Development

```console
python -m pip install -e ".[dev,demo,browser]"
python -m playwright install chromium
python -m pytest
```

GitHub Actions runs the suite on Python 3.11 through 3.14. Optional dependencies remain optional for normal CLI users.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md). The MIT license is in [LICENSE](LICENSE).
