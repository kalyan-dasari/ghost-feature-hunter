# Verification Playbook: Executing Real Checks

This playbook provides actionable instructions for executing safe verification checks across **API**, **Frontend / Browser**, **Database Persistence**, **Authorization**, and **Error Paths**.

---

## 1. API & Contract Verification

Verify HTTP response status codes, payload structures, headers, and response latency.

### Native Agent Execution
Use `curl` or inline terminal requests:
```bash
# Read check (safe, non-mutating)
curl -s -i "http://127.0.0.1:8000/api/cart"

# Mutating check (requires user approval for writes)
curl -s -i -X POST "http://127.0.0.1:8000/api/checkout" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"product_id": 1, "quantity": 2}]}'
```
Inspect:
- Status code matches expectation (e.g. `200 OK` or `201 Created`).
- JSON keys and values match schema (e.g. `total_cents: 1100`).
- Error responses return appropriate error envelopes without leaking stack traces.

### Optional CLI Adapter (`adapter: "http"`)
```json
{
  "id": "checkout-api-success",
  "checkpoint": "Checkout endpoint returns HTTP 200 with order confirmation",
  "adapter": "http",
  "expected_behavior": "Returns 200 with order id prefix ORD-",
  "source_of_expectation": "api_contract",
  "settings": {
    "method": "POST",
    "url": "/api/checkout",
    "json": {"items": [{"product_id": 1, "quantity": 2}]},
    "checks": {
      "status_code": 200,
      "json_exists": ["order_id", "total_cents"],
      "text_contains": "ORD-"
    }
  }
}
```

---

## 2. Frontend & Browser Verification

Verify DOM element visibility, form interactions, client-side validation, and UI state changes.

### Native Agent Execution
If the agent has browser automation tools available:
1. Open `http://127.0.0.1:8000/checkout`.
2. Assert form inputs exist (e.g. `#email`, `#address`, `#submit-order`).
3. Fill inputs with synthetic test data.
4. Click submission button.
5. Assert success banner or redirected URL (`/order-success`).

*If browser tools are not available:* Fall back to checking rendered server-side HTML via `curl` and inspecting HTML markup for required elements. Mark interactive client-rendered checks as `UNKNOWN` if no browser runtime exists.

### Optional CLI Adapter (`adapter: "browser"`)
```json
{
  "id": "checkout-ui-success",
  "checkpoint": "User completes checkout in browser",
  "adapter": "browser",
  "expected_behavior": "Success card is visible with Order Placed message",
  "source_of_expectation": "product_documentation",
  "settings": {
    "actions": [
      {"action": "goto", "url": "/checkout"},
      {"action": "fill", "selector": "#email", "value": "test@example.com"},
      {"action": "click", "selector": "#btn-submit"},
      {"action": "expect_visible", "selector": "#order-success-card"},
      {"action": "expect_text", "selector": "#order-status", "text": "Confirmed"}
    ]
  }
}
```

---

## 3. Database Persistence Verification

Verify that application operations actually commit the expected records and state transitions into the database.

> [!CAUTION]
> **Database Safety & Isolation:**
> Always execute read-only `SELECT` queries during audits. Never execute `UPDATE`, `DELETE`, `DROP`, or `ALTER` during an audit.
> When testing stateful or benchmark flows, always execute against disposable temporary databases (`tempfile.mkdtemp()`) with synthetic test data. Clean up and reseed databases between runs so that residual data does not contaminate subsequent verification outcomes.

### Native Agent Execution
Use the database CLI or a one-line Python script:
```bash
# SQLite inspection
sqlite3 data/app.sqlite3 "SELECT id, status, total_cents FROM orders ORDER BY id DESC LIMIT 1;"

# Or using Python standard library
python -c "
import sqlite3
conn = sqlite3.connect('data/app.sqlite3')
cur = conn.cursor()
cur.execute('SELECT count(*) FROM orders WHERE status = ?', ('confirmed',))
print('Count:', cur.fetchone()[0])
conn.close()
"
```
Assert:
- Expected row count matches.
- Specific columns match computed values (e.g. `total_cents == 1100`).
- Associated child records exist (e.g. `order_items` count equals cart items).

### Optional CLI Adapter (`adapter: "database"`)
```json
{
  "id": "order-persisted-db",
  "checkpoint": "Order is persisted in SQLite with confirmed status",
  "adapter": "database",
  "expected_behavior": "Exactly 1 order exists for customer with state confirmed",
  "source_of_expectation": "product_documentation",
  "settings": {
    "database_url_env": "APP_DB_URL",
    "query": "SELECT state, total_cents FROM orders WHERE id = :order_id",
    "parameters": {"order_id": 101},
    "checks": {
      "row_count_equals": 1,
      "first_row_equals": {"state": "confirmed", "total_cents": 1100}
    }
  }
}
```

---

## 4. Authorization & Security Verification

Verify that security gates protect resources against unauthorized access or cross-tenant tampering:

1. **Unauthenticated Access:** Call protected endpoint without credentials.
   - Assert: Returns `HTTP 401 Unauthorized`.
2. **Insufficient Roles:** Call admin endpoint with customer token.
   - Assert: Returns `HTTP 403 Forbidden`.
3. **Tenant / Identity Isolation:** Request User A's order (`GET /api/orders/ORD-101`) while authenticated as User B.
   - Assert: Returns `HTTP 404 Not Found` (preferred to avoid information disclosure) or `HTTP 403 Forbidden`. Must NOT disclose User A's data.

---

## 5. Error Paths & Resiliency Verification

Verify how the feature behaves under adverse, invalid, or boundary conditions:

1. **Input Validation:** Submit missing required fields (e.g. empty `items` array or missing `shipping_address`).
   - Assert: Returns `HTTP 400 Bad Request` or `422 Unprocessable Entity` with structured validation errors.
2. **Business Rule Violation:** Submit quantity exceeding current inventory (e.g. stock=5, requested=10).
   - Assert: Request rejected with `HTTP 400 Out of stock`; inventory is NOT modified; no order is created.
3. **Transaction Rollback:** If payment gateway simulation fails or an exception occurs halfway through order creation:
   - Assert: Entire database transaction rolls back; no orphan rows in `orders` or `order_items`.

