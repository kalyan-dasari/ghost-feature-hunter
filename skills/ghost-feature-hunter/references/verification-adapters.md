# Verification Adapters Reference

This guide covers **Workflow 6 (API Verification)**, **Workflow 7 (Browser Verification)**, **Workflow 8 (Database Verification)**, **Workflow 9 (Authorization Verification)**, and **Workflow 10 (Error-Path Verification)**.

---

## Workflow 6: API Verification (`adapter: "http"`)

Uses HTTPX to send explicit requests and assert against status codes, headers, and JSON structures.

### Supported Settings:
- `method`: `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, `DELETE`. Defaults to `GET`.
- `url`: Path relative to configured `base_url` or fully qualified same-origin URL.
- `headers`: Static string-to-string dictionary.
- `headers_env`: Map of header name to environment variable (e.g. `{"Authorization": "AUTH_TOKEN"}`).
- `params`: Query parameters dictionary.
- `json`: JSON payload dictionary or list.
- `timeout_seconds`: Per-step timeout (0 to 120s).

### Supported Checks:
- `status_code`: Integer HTTP status code (e.g. `200`, `201`, `400`, `404`).
- `json_equals`: Dictionary of dotted/bracket path to expected value (e.g. `{"order.status": "confirmed", "items[0].id": 1}`).
- `json_exists`: List of JSON path strings expected to exist.
- `text_contains`: Substring expected to exist in response body text.

### Guards:
- Mutating methods (`POST`, `PUT`, `PATCH`, `DELETE`) require `allow_writes: true` in config and `--allow-writes` on CLI.
- Redirects are disabled by default.
- Responses exceeding 2 MB produce `UNKNOWN`.

---

## Workflow 7: Browser Verification (`adapter: "browser"`)

Uses Playwright and headless Chromium for same-origin client-side UI verification.

### Supported Actions:
- `goto`: `{"action": "goto", "url": "/checkout"}`
- `click`: `{"action": "click", "selector": "#submit-btn"}`
- `fill`: `{"action": "fill", "selector": "#email", "value": "shopper@test.com"}`
- `expect_visible`: `{"action": "expect_visible", "selector": "#confirmation-card"}`
- `expect_text`: `{"action": "expect_text", "selector": "#order-id", "text": "ORD-"}`
- `expect_url_contains`: `{"action": "expect_url_contains", "text": "/success"}`
- `wait_for_network_idle`: `{"action": "wait_for_network_idle"}`

### Guards:
- Maximum 25 actions per step.
- Must include at least one explicit page or response assertion.
- Restricted strictly to configured `base_url` origin.
- Interaction actions (`click`, `fill`) require write approval.

---

## Workflow 8: Database Verification (`adapter: "database"`)

Executes bounded, read-only SELECT queries against SQLite using standard library Python.

### Supported Settings:
- `database_url_env`: Environment variable storing the SQLite database URI.
- `query`: Strictly read-only single `SELECT` query without comments or semicolons.
- `parameters`: Bound parameter dictionary or list (e.g. `{"user_id": "alice"}`).

### Supported Checks:
- `row_count_equals`: Non-negative integer.
- `row_count_at_least`: Non-negative integer.
- `first_row_equals`: Column name to expected value dictionary.

### Guards:
- Enforced by native SQLite `set_authorizer` at the C-engine level: all mutations, PRAGMAs, and extension loads are denied.
- File path must reside within the project root.
- Results capped at 1,000 rows.

---

## Workflow 9: Authorization Verification

Verify authentication gates and tenant isolation:

1. **Unauthenticated Check:** Verify unauthenticated requests return `HTTP 401`.
2. **Forbidden Check:** Verify insufficient role/permissions return `HTTP 403`.
3. **Multi-Tenant Isolation Check:** Request User A's resource (e.g. `GET /api/orders/order-alice`) while authenticated as User B. Assert the response returns `HTTP 404` (not disclosing resource existence) or `HTTP 403`.

---

## Workflow 10: Error-Path Verification

Features must handle bad inputs deterministically:

1. **Schema Validation:** Send missing required fields, negative quantities, or invalid types. Assert `HTTP 400` or `422`.
2. **Idempotency Check:** Send the same `Idempotency-Key` twice. Assert the second request returns `HTTP 409` or returns the original cached result without duplicating database rows.
3. **Partial Transaction Failure:** Simulate downstream failure (e.g. payment decline or stock error). Assert the transaction rolled back and no orphaned records exist in the database.

