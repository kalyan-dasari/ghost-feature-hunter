# Verification Playbook: Executing Real Checks

This playbook provides actionable instructions for executing safe verification checks across **API**, **Frontend / Browser**, **Database Persistence**, **Authorization**, and **Error Paths**.

---

## 0. Side-Effect Classification & Authorization Gate

### Classify Actual Side Effects
Never assume an operation is safe solely based on its HTTP method:
- A `GET` endpoint may trigger background writes, state changes, or queue jobs.
- A `POST` endpoint may be a non-mutating search query.
- Browser button clicks and form navigations frequently trigger mutations.
- Running a test suite or importing application modules may initialize or mutate persistent databases.

### Authorization Gate for Level 3 Mutations
Before executing any state-altering request (`POST`, `PUT`, `DELETE`, `PATCH`, or browser form submissions):
1. **Explain the target environment** (must be a local, isolated test server).
2. **Explain the endpoint or action** to be invoked.
3. **Explain what data will change.**
4. **Explain the isolation & cleanup strategy.**
5. **Request explicit user authorization.**

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

## 3. Database Persistence & Stateful Scenario Isolation

Verify that application operations actually commit the expected records and state transitions into the database.

> [!CAUTION]
> **State Contamination & The False PASS Trap:**
> Reusing a modified test database across checks creates contaminated state that can produce false `PASS` results.
> *Example (The Inventory Trap):* If an order check previously decremented product stock from 10 to 9, a subsequent check purchasing 2 units that expects stock 8 will erroneously see stock 8 if the implementation has a defect subtracting 1 unit (`9 - 1 = 8`). This falsely masks a critical bug!
>
> **Mandatory Isolation Protocol:**
> 1. **Disposable Database Per Scenario:** Point the test target to a fresh temporary SQLite database (`tempfile.NamedTemporaryFile`) or test container.
> 2. **Seed Known Initial State:** Populate clean seed rows with known initial quantities.
> 3. **Record Initial Value:** Execute a read-only query to record `initial_value` before the check.
> 4. **Execute Only Approved Check:** Trigger the authorized mutation.
> 5. **Record Final Value:** Execute a read-only query to record `actual_final_value`.
> 6. **Assert Exact Delta:** Verify `expected_final_value` against `actual_final_value`.
> 7. **Clean Up Test Database:** Delete temporary files immediately after execution.
> 8. **Uncontaminated Invariant:** If clean database isolation cannot be established, mark state-dependent assertions **`UNKNOWN`**. Never continue on contaminated state.

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

---

## 6. The PASS Evidence Contract

A checkpoint may evaluate to **`PASS`** if and only if all of the following conditions are met:
1. **Authoritative Expectation:** The expected behavior is backed by `user_requirement`, `product_documentation`, `api_contract`, or `existing_test`. Inferred assumptions require explicit user confirmation.
2. **Actual Execution:** The exact verification check was actually dispatched and observed.
3. **Recorded Observation:** Concrete empirical outputs (status codes, payloads, row values) are captured.
4. **Preconditions Established:** Baseline initial states were confirmed prior to the check.
5. **No State Contamination:** Test state was not contaminated by preceding checks.
6. **Affirmative Match:** Observed output affirmatively matches the authoritative expectation.

> [!WARNING]
> Static source inspection alone can NEVER prove runtime `PASS`. Source inspection can prove code structure or suspected defects, but runtime behavior requires empirical runtime execution. If evidence is incomplete or unverified, the status MUST be **`UNKNOWN`**.

