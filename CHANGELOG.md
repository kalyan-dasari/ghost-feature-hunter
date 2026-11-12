# Changelog

All notable changes to the Ghost Hunt verification tool and Agent Skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - Unreleased

### Added
- **Skill-First Architecture:** Rebranded and refactored the canonical skill to `skills/ghost-hunt/` conforming to the Agent Skills open standard.
- **Native Agent Execution:** The skill now runs immediately out of the box using an AI agent's native tools (`curl`, terminal commands, file search, test runners, browser) without requiring installation of the Python CLI.
- **The 11-Step Investigation Protocol:** Standardized end-to-end feature verification covering scope, static discovery, data flow tracing, requirement source tagging, journey checkpoints, safe execution, defect isolation, root-cause diagnosis, minimal fix proposal, regression verification, and evidence-backed reporting.
- **Four-Tier Operation Safety Levels:** Clearly demarcated source inspection, runtime read-only checks, runtime mutating operations (requiring user authorization), and database write operations.
- **Playwright Process Tree Termination:** Killable worker subprocess isolation using Win32 Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) on Windows and POSIX process groups (`os.killpg`) to eliminate driver deadlocks and enforce configurable hard timeouts.
- **Report Path Containment:** Strict decoupling of `--force` (overwrite permission) from `--allow-external-output` (external filesystem write permission), preventing directory traversal and symlink escapes.
- **One-Line Distribution:** Supported direct distribution via `npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt`.
- **Mirror Synchronization CI Check:** Automated test verifying that `.agents/skills/ghost-hunt/` and canonical `skills/ghost-hunt/` remain synchronized.
- **Templates & Walkthroughs:** Added `templates/report-template.md`, `templates/journey-template.json`, and `examples/checkout-investigation.md`.

### Fixed
- Fixed foreign Windows drive path parsing on POSIX (`sqlite:///C:/Windows/...`) so it is immediately rejected as outside allowed roots rather than silently converted to an invalid relative path.
- Fixed Bearer and Basic auth header redaction regex in evidence logging.
- Removed artificial `database = []` dependency extra from `pyproject.toml` and documentation.

---

## [0.2.0] - 2026-11-12

### Added
- Standard library SQLite read-only connection authorizer (`sqlite3.Connection.set_authorizer`).
- Four-tier database path authorization policy (`project_root`, `tempfile.gettempdir()`, `allowed_database_dirs`, and production dual-approval).
- Automated benchmark test suite verifying 15 injected defects in `examples/broken-flask-shop`.

---

## [0.1.2] - 2026-11-11
- Initial public alpha release with Python CLI, Flask AST discovery, HTTP adapter, and basic report rendering.

---

## Public Release Checklist

Before tagging and publishing `v0.3.0`:

- [ ] All unit, integration, and benchmark tests pass across Python 3.11, 3.12, 3.13, and 3.14 on Linux and Windows.
- [ ] Public `npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt` succeeds in clean consumer project.
- [ ] Working tree is clean and `main` branch contains all verified fixes.
- [ ] GitHub release notes correspond to `[0.3.0]` changelog entry.
- [ ] Maintainer approval obtained before pushing git tags or publishing packages.
