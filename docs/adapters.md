# Adapter reference

Journeys are JSON. Each step names one adapter, states expected behavior, and provides explicit machine-checkable assertions. Unsupported assertions produce UNKNOWN; they are never silently ignored.

## HTTP

Settings: `method` (default GET), `url`, optional `headers`, `headers_env`, `params`, `json`, `timeout_seconds`, and `checks`. Checks support `status_code`, `json_equals` keyed by a dotted/list-index path, `json_exists`, and `text_contains`. Responses larger than 2 MB produce UNKNOWN. Request and response payloads are not copied wholesale into evidence. Write methods need both project and CLI approval.

## Database

Uses Python's standard-library SQLite driver; no ORM dependency is needed. A file-backed SQLite URL is supplied through `database_url_env` in config or a step. `query` must be one SELECT without comments or semicolons, complete within the configured query limit, and return at most 1,000 rows. `checks` supports `row_count_equals`, `row_count_at_least`, and `first_row_equals`. Use bound parameters via `parameters`; query results and database paths are not disclosed in evidence.

Database files must be contained within allowed roots:
- The project root directory.
- Temporary directories (`tempfile.gettempdir()`) in `development` and `test` environments only.
- Explicitly configured directories in `allowed_database_dirs` in `ghost-hunter.json`.
- Production targets require `production_approved: true` in config and `--approve-production` on CLI.

## Browser

Requires Playwright and its Chromium binary (`pip install ".[browser]"`), plus `base_url`. Browser verification executes in an isolated worker subprocess with OS-level process tree termination (Windows Job Objects / POSIX process groups) enforcing a configurable hard deadline (`timeout_seconds`), terminating unresponsive workers with `UNKNOWN`. `actions` supports `goto`, `click`, `fill`, `expect_visible`, `expect_text`, `expect_url_contains`, and `wait_for_network_idle`. Each step needs an explicit page or response assertion. Browser requests are restricted to the configured origin, and mutating HTTP methods require both write approvals. The adapter does not record screenshots. Page scripts still execute, so browser checks are not a sandbox.

## Deferred after v0.1

Test-suite execution needs a dedicated isolation design; a zero exit code alone can be misleading when no tests ran. A log phrase can be stale and does not establish a current runtime outcome. Neither adapter contributes to v0.1 verification status.
