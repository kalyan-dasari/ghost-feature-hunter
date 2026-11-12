# Ghost Hunt Demonstration: Checkout Feature Investigation

This document demonstrates a realistic, end-to-end investigation using the Ghost Hunt Agent Skill against the benchmark application (`examples/broken-flask-shop`).

---

## The Scenario

A developer opens their coding agent and types:

```text
/ghost-hunt investigate checkout
```

The agent activates the `ghost-hunt` skill and begins the 11-step verification protocol.

---

## Step 1: Feature Intent & Scope Analysis

- **Target Feature:** `checkout`
- **Goal:** Verify that a user can calculate cart totals, submit an order, persist state, deduct inventory, and handle error conditions.
- **Environment:** Local Flask application (`http://127.0.0.1:5000`) with SQLite database (`instance/shop.sqlite3`).
- **Execution Mode:** Native Agent Tools (Standard Skill Mode).

---

## Step 2: Static Code Discovery

The agent inspects the project files to discover relevant routes, models, and assets:

1. **Routes Discovered in `app.py`:**
   - `@app.post("/api/cart/calculate")` — Computes subtotal, tax, and total.
   - `@app.post("/api/drafts")` — Creates order draft.
   - `@app.post("/api/checkout")` — Processes purchase and records order.
   - `@app.get("/api/orders")` — Lists orders for a user.
2. **Database Models & Tables Discovered in `app.py`:**
   - `products (id, name, price_cents, stock)`
   - `orders (id, user_id, email, state, total_cents, idempotency_key)`
   - `drafts (id, title, created_at)`
3. **Frontend Assets:**
   - `templates/shop.html`, `templates/checkout.html`
   - `static/shop.js`

---

## Step 3: End-to-End Flow Tracing

```text
User Submits Cart ──> POST /api/cart/calculate ──> Subtotal & Tax Logic
                                                           │
Database (orders, products) <── POST /api/checkout <───────┘
```

1. **Cart Calculation:** Client posts items `[{"product_id": 1, "quantity": 2}]`. Backend queries product prices, adds 10% tax, and returns total.
2. **Order Placement:** Client posts idempotency key, user ID, email, and cart items to `/api/checkout`.
3. **Inventory & Order Persistence:** Backend verifies stock, records order in `orders` table, and decrements stock in `products` table.

---

## Step 4: Requirement & Acceptance Criteria Analysis

| Checkpoint | Source | Expected Behavior |
|---|---|---|
| Cart Tax | `product_documentation` | Two items at 500¢ with 10% tax totals **1100¢** (1000¢ + 100¢ tax). |
| Idempotency | `api_contract` | First request returns HTTP 201; immediate duplicate key returns HTTP 409. |
| Quantity Validation | `user_requirement` | Negative or zero quantity must return HTTP 400. |
| Inventory Deduction | `user_requirement` | Purchasing 2 units must decrement `products.stock` by 2. |
| Persistence | `product_documentation` | Order row exists with `state = 'confirmed'`. |

---

## Step 5: Journey Checkpoints Defined

- **CP-1 (`cart-total`):** `POST /api/cart/calculate` with 2x $5.00 socks. Assert `total_cents == 1100`.
- **CP-2 (`idempotency-first`):** `POST /api/checkout` with `Idempotency-Key: demo-uuid-1`. Assert `HTTP 201`.
- **CP-3 (`idempotency-duplicate`):** `POST /api/checkout` with same key. Assert `HTTP 409`.
- **CP-4 (`inventory-reduction`):** Read-only SQLite query on `products`. Assert stock decreased by 2.
- **CP-5 (`quantity-negative`):** `POST /api/checkout` with `quantity: -1`. Assert `HTTP 400`.

---

## Step 6: Safe Runtime Execution (Terminal Checks)

The agent runs safe checks against the local test server:

### Check 1: Cart Calculation
```bash
curl -s -X POST "http://127.0.0.1:5000/api/cart/calculate" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"product_id": 1, "quantity": 2}]}'
```
**Observation:**
```json
{"items_count": 2, "subtotal_cents": 1000, "tax_cents": 100, "total_cents": 1200}
```
❌ **Mismatch Detected:** Expected `1100`, observed `1200`.

### Check 2: Negative Quantity Check
```bash
curl -s -i -X POST "http://127.0.0.1:5000/api/checkout" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "email": "test@test.com", "items": [{"product_id": 1, "quantity": -1}]}'
```
**Observation:**
```http
HTTP/1.1 201 Created
{"order_id": "ord-883", "state": "confirmed", "total_cents": -500}
```
❌ **Mismatch Detected:** Expected `HTTP 400`, observed `HTTP 201 Created` with negative total!

---

## Step 7 & 8: Defect Isolation & Root-Cause Diagnosis

### Defect A: Double Tax Calculation (`cart-double-tax`)
- **Observed:** `total_cents: 1200`
- **Expected:** `total_cents: 1100`
- **Location:** `app.py:L83-L90` (`examples/broken-flask-shop/app.py`)
- **Root Cause:**
  In `app.py`, the tax computation adds tax twice to the subtotal:
  ```python
  tax = round(subtotal * 0.10)
  total = subtotal + tax + tax  # <-- Bug: tax added twice
  ```

### Defect B: Missing Quantity Validation (`quantity-validation`)
- **Observed:** Order placed with quantity `-1` (HTTP 201).
- **Expected:** Rejected with HTTP 400.
- **Location:** `app.py:L142-L148` (`examples/broken-flask-shop/app.py`)
- **Root Cause:**
  The checkout route checks that `quantity` is an integer, but does not assert `quantity > 0`:
  ```python
  if not isinstance(item.get("quantity"), int):
      return jsonify({"error": "Quantity must be an integer"}), 400
  # Missing check: if item["quantity"] <= 0: return 400
  ```

---

## Step 9: Minimal Fix Proposal

The agent presents the minimal fix to the developer for authorization:

```diff
--- a/app.py
+++ b/app.py
@@ -84,7 +84,7 @@ def calculate_cart():
     subtotal = sum(p["price_cents"] * item["quantity"] for p, item in resolved)
     tax = round(subtotal * 0.10)
-    total = subtotal + tax + tax
+    total = subtotal + tax
     return jsonify({"subtotal_cents": subtotal, "tax_cents": tax, "total_cents": total})

@@ -144,6 +144,8 @@ def checkout():
         for item in items:
             if not isinstance(item.get("quantity"), int):
                 return jsonify({"error": "Quantity must be an integer"}), 400
+            if item["quantity"] <= 0:
+                return jsonify({"error": "Quantity must be greater than zero"}), 400
```

> *"I have isolated these two root causes. Would you like me to apply this minimal fix?"*

---

## Step 10: Regression Verification

Upon user approval, the fix is applied and both checkpoints are re-tested:
- Check 1: `curl POST /api/cart/calculate` -> Returns `total_cents: 1100` (**PASS**).
- Check 2: `curl POST /api/checkout` with `quantity: -1` -> Returns `HTTP 400` (**PASS**).
- Full existing test suite rerun: `pytest tests/` -> 100% PASS.

---

## Step 11: Final Evidence-Backed Audit Report

```markdown
# Ghost Hunt: Checkout Feature Audit Report

- **Feature:** `checkout`
- **Status:** PASS (Post-fix resolution confirmed)
- **Initial Failures:** 2
- **Regressions:** 0

### Summary Table
| Checkpoint | Expected | Observed | Status |
|---|---|---|---|
| `cart-tax` | `total_cents: 1100` | `total_cents: 1100` | **PASS** |
| `idempotency-first` | HTTP 201 | HTTP 201 | **PASS** |
| `quantity-negative` | HTTP 400 | HTTP 400 | **PASS** |
| `order-persisted` | 1 confirmed row in SQLite | 1 confirmed row in SQLite | **PASS** |

**Conclusion:** Both defects (`cart-double-tax` and `quantity-validation`) were confirmed with empirical evidence, isolated to exact line numbers in `app.py`, corrected with minimal diffs, and verified through regression checks.
```

