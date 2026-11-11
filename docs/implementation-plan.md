# v0.1 scope and review gate

## Vertical slice

The first release supports developer-authored JSON journeys, deterministic HTTP and read-only SQLite observations, optional same-origin browser checks, evidence-backed JSON/Markdown reports, and advisory static discovery. The Python engine owns execution, safety gates, status calculation, and report totals. An AI agent may help prepare a journey or interpret evidence; it cannot establish PASS or FAIL by assertion.

Static discovery parses source without importing or running it. Its routes and file lists are suggestions only and never become runtime checks or expected behavior automatically.

## Simplifications from the first design

- SQLite is supported with Python's standard-library driver; SQLAlchemy adds no needed capability for the file-backed SQLite scope.
- The v0.1 adapter set is HTTP, SQLite, and browser. The pytest adapter can execute arbitrary project code and a process exit code can be misleading if no tests ran. The log adapter can find stale phrases. Both are deferred until they have stronger isolation and evidence rules.
- PASS and FAIL model records require evidence. Report totals are recalculated and checked against result rows when reports are loaded.
- Unsupported HTTP and SQL assertions return UNKNOWN rather than being ignored. Browser steps require an explicit assertion, and unapproved mutating HTTP methods from page scripts are blocked.
- Reports are unsigned and editable. A saved report alone is not proof that the engine ran; operators and agents should run the CLI for the current investigation and review the evidence.

## Dependencies

- Core: Python 3.11+, Typer, Pydantic, HTTPX.
- Optional browser: Playwright and a separately installed Chromium binary.
- Optional demo: Flask.
- Development: pytest, build, and jsonschema.

The implementation does not need an ORM, YAML parser, shell, or agent framework.

## Security and evidence limits

HTTP targets must match the configured base origin or an explicit allowlist. HTTP redirects are disabled. Write requests require config and CLI approval. SQLite uses a read-only file URI, a query time limit, and a 1,000-row cap. Browser requests are constrained to the configured origin and mutating HTTP methods need both approvals, but page scripts execute and the browser is not a sandbox. Redaction is best effort. Reports do not carry cryptographic provenance.

## Current milestone gate

The v0.1 implementation and skeptical review are one milestone. Do not start another milestone until the relevant unit, integration, and benchmark tests pass and the complete Git diff has been reviewed. A failed or skipped check must be documented accurately. The CI workflow has not yet been exercised on GitHub; local test evidence only covers the available Python runtime.

Current status: 24 unit tests and the isolated benchmark metric test pass. Browser integration and the end-to-end benchmark remain unverified because the local Playwright sync driver did not start before the 15-second startup probe timed out. The release gate remains open; this is not a passing full-suite result.

## Deferred after v0.1

- Running project test suites, until isolation and proof that tests actually ran are addressed.
- Log phrase checks, until stale evidence can be distinguished from current runtime behavior.
- Other database engines and ORMs, frameworks, inferred journeys, automatic root-cause claims, agent plugins, parallel execution, and cryptographic report signing.
