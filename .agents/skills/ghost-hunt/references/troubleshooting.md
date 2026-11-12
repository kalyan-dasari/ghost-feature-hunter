# Troubleshooting & Operational Guidance

Common errors, diagnostic procedures, and recovery actions when running Ghost Hunt.

---

## 0. CLI Engine Not Installed

**Symptom:** `ghost-hunter: command not found` or module not found.

**Cause:** The optional Python verification engine is not installed in the current environment.

**Remedy:**
Ghost Hunt **does not require the Python CLI** to investigate features.
1. Use your agent's native tools: inspect code with file tools, execute requests with `curl`, test persistence with `sqlite3` CLI, and run test suites directly.
2. If you specifically desire the deterministic CLI engine (e.g. for CI pipelines), install it via `pip install "ghost-feature-hunter[all]"`.

---

## 1. Browser Adapter Startup Timeout

**Symptom:** Checkpoint returns `UNKNOWN` with:  
`"Playwright browser runtime could not be initialized in this environment (startup probe timed out). Ensure loopback socketpair permissions and browser binaries are configured."`

**Cause:** The execution environment (sandboxed shell, minimal container, or restricted Windows profile) blocks loopback socket connections required by Playwright's sync event loop.

**Remedy:**
1. Ensure the Python environment has Chromium installed:  
   `python -m playwright install chromium`
2. If running inside a sandboxed subshell or runner that isolates network loopback, run with bypass sandbox approval or run directly on the host console.
3. For environments without browser capability, test API and persistence checkpoints via `http` and `database` adapters.

---

## 2. Write Requests Blocked

**Symptom:** Checkpoint returns `UNKNOWN` with:  
`"Write request blocked; set allow_writes in project config and pass --allow-writes."`

**Cause:** The journey includes an HTTP mutating method (`POST`, `PUT`, `PATCH`, `DELETE`) or browser interaction (`click`, `fill`), but write approval was not granted.

**Remedy:**
1. Verify the target environment is a disposable, isolated test environment with synthetic data.
2. In `ghost-hunter.json`, set `"allow_writes": true`.
3. Pass `--allow-writes` on the CLI command:  
   `ghost-hunter audit <feature> --allow-writes`

---

## 3. Production Target Blocked

**Symptom:** Checkpoint returns `UNKNOWN` with:  
`"Production target blocked; production approval is required in config and on the CLI."`

**Cause:** `ghost-hunter.json` has `"environment": "production"`, triggering strict safety guardrails.

**Remedy:**
1. Ensure checks are directed at a development, test, or staging target rather than production.
2. If production verification is explicitly authorized, set `"production_approved": true` in `ghost-hunter.json` AND pass `--approve-production` on the CLI.

---

## 4. Database Path Jailing Error

**Symptom:** Checkpoint returns `UNKNOWN` with:  
`"Database file path ... is outside the allowed project directories."`

**Cause:** Security guardrail prevented access to a database file located outside the project root, outside system temp in non-production, or outside explicitly approved directories.

**Remedy:**
1. Point `database_url_env` to an SQLite database located within the project directory (e.g. `instance/app.sqlite3`).
2. Relative paths in `sqlite:///` automatically resolve relative to the project root.
3. If an external database is required, add its directory to `allowed_database_dirs` in `ghost-hunter.json`.

---

## 5. Report Overwrite Protection

**Symptom:** CLI exits with error:  
`"Refusing to overwrite existing report(s) ... pass --force to replace them"`

**Cause:** Ghost Feature Hunter preserves historical audit reports by default to prevent accidental loss of evidence.

**Remedy:**
Pass `--force` when executing the audit or report command to replace existing reports:  
`ghost-hunter audit <feature> --force`

---

## 6. Report External Output Jailing

**Symptom:** CLI exits with error:  
`"Refusing to write report outside project root (...) to (...). Pass --allow-external-output to permit writing outside the project root."`

**Cause:** By default, report output is strictly jailed to the project root directory. Overwrite permission (`--force`) does not bypass filesystem containment.

**Remedy:**
To permit rendering reports to an external directory outside the project root, explicitly provide `--allow-external-output`:  
`ghost-hunter report ghost-reports/ghost-report.json --output /external/path/report.md --allow-external-output`  
If the target external file already exists, pass both flags:  
`ghost-hunter report ghost-reports/ghost-report.json --output /external/path/report.md --allow-external-output --force`


