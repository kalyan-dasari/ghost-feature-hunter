# Optional Deterministic CLI Verification Engine

While the Ghost Hunt Agent Skill works immediately out-of-the-box using the agent's native tools, it can also leverage the `ghost-hunter` Python CLI when installed for hermetic, deterministic verification in CI pipelines and automated test runs.

---

## 1. CLI Installation

Install the Python CLI package with desired extras:

```bash
# Core verification engine
pip install ghost-feature-hunter

# With browser automation support (Playwright Chromium)
pip install "ghost-feature-hunter[browser]"

# With all extras (dev, demo, browser)
pip install "ghost-feature-hunter[all]"
```

Verify installation:
```bash
ghost-hunter --help
```

---

## 2. Core CLI Commands

### 1. Initialize Configuration
```bash
ghost-hunter init --project-root .
```
Creates `ghost-hunter.json` and a starter journey in `journeys/health.json`.

### 2. Static Discovery
```bash
ghost-hunter discover --project-root .
```
Statically analyzes Flask routes and models, outputting `ghost-reports/ghost-discovery.json` and `ghost-reports/ghost-discovery.md`.

### 3. Run Verification Journey
```bash
# Read-only audit
ghost-hunter audit <feature> --project-root .

# Audit with write approval (POST/PUT/DELETE, browser interactions)
ghost-hunter audit <feature> --project-root . --allow-writes

# Replace previous audit reports
ghost-hunter audit <feature> --project-root . --force
```
Outputs:
- `ghost-reports/ghost-report.json`: Machine-readable report conforming to `schemas/report.schema.json`.
- `ghost-reports/ghost-report.md`: Formatted Markdown report.

### 4. Render Markdown from Saved JSON Report
```bash
# Render to default location inside project
ghost-hunter report ghost-reports/ghost-report.json --force

# Render to external location (requires explicit authorization)
ghost-hunter report ghost-reports/ghost-report.json --output /external/report.md --allow-external-output --force
```

---

## 3. Configuration File (`ghost-hunter.json`)

```json
{
  "schema_version": "1.0",
  "environment": "development",
  "base_url": "http://127.0.0.1:8000",
  "allowed_hosts": ["127.0.0.1", "localhost"],
  "timeout_seconds": 10.0,
  "allow_writes": false,
  "production_approved": false,
  "report_dir": "ghost-reports",
  "database_url_env": "APP_DATABASE_URL",
  "allowed_database_dirs": []
}
```

---

## 4. When to Use the CLI vs Native Agent Tools

| Scenario | Recommended Approach |
|---|---|
| Developer asks from chat: *"Check my checkout feature"* | **Native Agent Tools** (Instant, zero installation required) |
| Ad-hoc debugging of a specific broken endpoint | **Native Agent Tools** (`curl`, inline test script) |
| CI/CD automated regression gate on PRs | **Optional CLI Engine** (`ghost-hunter audit checkout`) |
| Strict compliance / machine-validated JSON artifacts | **Optional CLI Engine** (Generates schema-validated reports) |

