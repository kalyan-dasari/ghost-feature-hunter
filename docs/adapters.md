# Adapter & Tool Verification Reference

Ghost Hunt supports verification through both **Native Agent Tools** (chat mode) and **Deterministic Adapters** (optional CLI mode).

---

## 1. Native Agent Tool Mapping

When running in chat mode, coding agents map verification checks to their available native environment tools:

| Verification Target | Native Agent Tools | Typical Command / Action | Safety Constraints |
|---|---|---|---|
| **API Endpoints** | `curl`, `httpx`, Python/Node scripts | `curl -s -i -X POST <url> -d '<json>'` | Mutating methods require user authorization. Response payloads sanitized. |
| **Database Persistence** | `sqlite3` CLI, Python `sqlite3` script | `sqlite3 <db_path> "SELECT ..."` | Strictly read-only queries during audits. Stateful tests use isolated temporary databases. |
| **Frontend / DOM Flow** | Agent browser tool, Playwright scripts | Click buttons, fill inputs, assert DOM text | Mutating browser actions require user authorization. |
| **Unit & Integration Tests** | `pytest`, `npm test`, `go test` | Run feature test files directly | Read-only test execution. |

---

## 2. Deterministic CLI Adapter Reference

For automated JSON journeys (`journeys/<feature>.json`), the optional Python CLI dispatches checkpoints to dedicated adapters conforming to `ghost_hunter.adapters.base.BaseAdapter`.

### HTTP Adapter (`adapter: "http"`)
- **Settings:**
  - `method`: HTTP method (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`). Default: `GET`.
  - `url`: Relative or absolute URL. Resolves against configured `base_url`.
  - `headers` / `headers_env`: Request headers or environment variable providing headers.
  - `params`: URL query parameters.
  - `json`: Request body payload.
  - `timeout_seconds`: Request timeout (default: 10.0s).
  - `checks`: List of assertions:
    - `status_code`: Expected integer status code (e.g. 200, 201, 400).
    - `json_equals`: Dotted path key match (`{"key": "total_cents", "value": 1100}`).
    - `json_exists`: Asserts key presence.
    - `text_contains`: Asserts string substring in response text.
- **Safety Gates:**
  - Write methods (`POST`, `PUT`, `DELETE`, `PATCH`) require both `"allow_writes": true` in `ghost-hunter.json` and `--allow-writes` on CLI.
  - Responses capped at 2 MB; exceeding 2 MB returns `UNKNOWN`.
  - Sensitive auth headers and credentials redacted from evidence.

### Database Adapter (`adapter: "database"`)
- **Settings:**
  - `query`: A single SQL SELECT query without comments or semicolons.
  - `parameters`: Bound parameters dictionary for parameterized queries.
  - `database_url_env`: Environment variable containing the database URL (default: `sqlite:///<path>`).
  - `checks`:
    - `row_count_equals`: Exact row count assertion.
    - `row_count_at_least`: Minimum row count assertion.
    - `first_row_equals`: Key-value assertions on the first returned record.
- **Safety Gates:**
  - Standard library SQLite with C-level query authorizer callback (`sqlite3.Connection.set_authorizer`).
  - Rejects comments, multiple statements, and any non-SELECT operation (`INSERT`, `UPDATE`, `DELETE`, `DROP`).
  - Result sets capped at 1,000 rows.
  - 4-tier path containment prevents directory traversal and unauthorized filesystem access.

### Browser Adapter (`adapter: "browser"`)
- **Settings:**
  - `actions`: Ordered list of browser actions (`goto`, `click`, `fill`, `expect_visible`, `expect_text`, `expect_url_contains`, `wait_for_network_idle`).
  - Requires Playwright Chromium binary (`pip install "ghost-feature-hunter[browser]"`).
- **Safety Gates:**
  - Isolated worker subprocess with OS-level process tree termination (Windows Job Objects / POSIX process groups) enforcing hard timeout deadlines.
  - Restricted to configured origin; cross-origin navigations blocked.
  - Mutating actions require write approval.
  - Unresponsive browser workers return `UNKNOWN` with actionable diagnostics.
