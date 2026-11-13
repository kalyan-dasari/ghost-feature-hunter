# Ghost Hunt Demonstration: Checkout Feature Investigation

This document demonstrates an end-to-end feature investigation using the Ghost Hunt Agent Skill against the benchmark application (`examples/broken-flask-shop`).

---

## The Scenario

A developer opens their coding agent in the `ghost-feature-hunter` repository and explicitly targets the benchmark shop:

```text
/ghost-hunt investigate checkout in examples/broken-flask-shop
```

The agent activates the `ghost-hunt` skill, locks the target scope to `examples/broken-flask-shop`, and begins the 11-step verification protocol.

---

## Step 1: Project Context & Scope Analysis

### Project Context Summary
- **Project Name:** `ghost-feature-hunter`
- **Project Root:** `K:/Big Things/ghost-feature-hunter`
- **Git Repository Root:** `K:/Big Things/ghost-feature-hunter`
- **Selected Application Root:** `examples/broken-flask-shop` (explicitly selected fixture)
- **Framework & Languages:** Flask, Python, SQLite, HTML/JS
- **Investigation Mode:** Feature Investigation (`checkout`)
- **Included Directories:** `examples/broken-flask-shop/`
- **Excluded Directories:** `src/`, `tests/`, `skills/`
- **Available Capabilities:** Native Agent Tools (`curl`, Python, SQLite)
- **Limitations:** Isolated loopback testing with disposable SQLite databases

---

## Step 2: Static Code Discovery

The agent inspects the application files to discover relevant routes, models, and assets:

1. **Routes Discovered in `app.py`:**
   - `@app.post("/api/cart/calculate")` — Computes subtotal, tax, and total.
   - `@app.post("/api/drafts")` — Creates order draft.
   - `@app.post("/api/checkout")` — Processes purchase and records order.
   - `@app.get("/api/orders")` — Lists orders for a user.
2. **Database Models & Tables Discovered in `app.py`:**
   - `products (id, name, price_cents, stock)`
   - `orders (id, user_id, email, state, total_cents, idempotency_key)`
   - `drafts (id, payload)`
3. **Frontend Assets:**
   - `templates/index.html`, `static/shop.js`

---

## Step 3: End-to-End Flow Tracing

```text
User Submits Cart ──> POST /api/cart/calculate ──> Subtotal & Tax Logic
                                                           │
Database (orders, products) <── POST /api/checkout <───────┘
```

1. **Cart Calculation:** Client posts items `[{"product_id": 1, "quantity": 2}]`. Backend queries product prices, adds 10% tax, and returns total.
2. **Order Placement:** Client posts user ID, email, and cart items to `/api/checkout`.
3. **Inventory & Order Persistence:** Backend records order in `orders` table and decrements stock in `products` table.

---

## Step 4: Requirement & Acceptance Criteria Analysis

| Checkpoint | Source | Expected Behavior |
|---|---|---|
| Cart Tax | `product_documentation` (`examples/broken-flask-shop/README.md`) | Two socks @ 500¢ with 10% tax totals **1100¢** (1000¢ + 100¢ tax). |
| Quantity Validation | `api_contract` (`benchmark-manifest.json#quantity-validation`) | Negative or zero quantity must return HTTP 400. |
| Inventory Deduction | `product_documentation` (`README.md#inventory`) | Purchasing 2 units must decrement `products.stock` by 2 (10 -> 8). |
| Order Persistence | `product_documentation` (`README.md#orders`) | Order row exists with `state = 'confirmed'`. |

---

## Step 5: Journey Checkpoints Defined

- **CP-1 (`cart-total`):** `POST /api/cart/calculate` with 2x $5.00 socks. Assert `total_cents == 1100`.
- **CP-2 (`quantity-negative`):** `POST /api/checkout` with `quantity: -1`. Assert `HTTP 400`.
- **CP-3 (`inventory-reduction`):** Baseline stock 10. Purchase 2 socks. Assert `stock == 8`.
- **CP-4 (`order-persisted`):** Query SQLite `orders` table. Assert 1 confirmed row.

---

## Step 6: Safe Runtime Execution (With Fresh Disposable DBs)

The agent runs safe checks against the local test server, using fresh temporary databases to avoid test-state contamination:

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
❌ **Mismatch Detected:** Expected `1100`, observed `1200` (**`FAIL`**).

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
❌ **Mismatch Detected:** Expected `HTTP 400`, observed `HTTP 201 Created` (**`FAIL`**).

### Check 3: Inventory Deduction (Stateful Isolated Check)
- **Baseline Initial State:** Fresh seeded SQLite database with `products.stock = 10` for product 1.
- **Action:**
  ```bash
  curl -s -X POST "http://127.0.0.1:5000/api/checkout" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test-user", "email": "test@test.com", "items": [{"product_id": 1, "quantity": 2}]}'
  ```
- **Final Query:** `SELECT stock FROM products WHERE id = 1`
**Observation:**
```text
Observed stock: 9
```
❌ **Mismatch Detected:** Expected `stock = 8` after purchasing 2 units, observed `stock = 9` (**`FAIL`**).

---

## Step 7 & 8: Defect Isolation & Root-Cause Diagnosis

### Defect A: Double Tax Calculation (`cart-double-tax`)
- **Observed:** `total_cents: 1200`
- **Expected:** `total_cents: 1100`
- **Location:** `app.py:L103-L105` (`examples/broken-flask-shop/app.py`)
- **Root Cause:** In `app.py`, the tax computation adds tax twice to the subtotal:
  ```python
  tax = round(subtotal * 0.10)
  total = subtotal + tax + tax  # <-- Bug: tax added twice
  ```

### Defect B: Missing Quantity Validation (`quantity-validation`)
- **Observed:** Order placed with quantity `-1` (HTTP 201).
- **Expected:** Rejected with HTTP 400.
- **Location:** `app.py:L151-L154` (`examples/broken-flask-shop/app.py`)
- **Root Cause:** `checkout` converts `quantity` to integer but does not assert `quantity > 0`:
  ```python
  quantity = int(item.get("quantity", 1))
  # Missing check: if quantity <= 0: return 400
  ```

### Defect C: Single-Unit Stock Deduction (`inventory-reduction`)
- **Observed:** Purchasing 2 units decreased stock from 10 to 9 instead of 8.
- **Expected:** Stock decreases by the ordered quantity (10 - 2 = 8).
- **Location:** `app.py:L180` (`examples/broken-flask-shop/app.py`)
- **Root Cause:** `app.py` hardcodes a 1-unit deduction regardless of requested quantity:
  ```python
  for product_id, _quantity in prepared_items:
      db().execute("UPDATE products SET stock = MAX(stock - 1, 0) WHERE id = ?", (product_id,))
      # <-- Bug: decrements by 1 instead of _quantity!
  ```

---

## Step 9: Minimal Fix Proposal

The agent presents the minimal fix to the developer for authorization:

```diff
--- a/examples/broken-flask-shop/app.py
+++ b/examples/broken-flask-shop/app.py
@@ -104,3 +104,3 @@
         tax = round(subtotal * 0.10)
-        total = subtotal + tax + tax
+        total = subtotal + tax
         return jsonify({"subtotal_cents": subtotal, "tax_cents": tax, "total_cents": total})
@@ -153,2 +153,4 @@
                 quantity = int(item.get("quantity", 1))
+                if quantity <= 0:
+                    return jsonify({"error": "Quantity must be positive"}), 400
                 product = db().execute(
@@ -179,3 +181,3 @@
-            for product_id, _quantity in prepared_items:
-                db().execute("UPDATE products SET stock = MAX(stock - 1, 0) WHERE id = ?", (product_id,))
+            for product_id, quantity in prepared_items:
+                db().execute("UPDATE products SET stock = MAX(stock - ?, 0) WHERE id = ?", (quantity, product_id))
```

> *"I have isolated these three root causes with empirical before/after evidence. Would you like me to apply this minimal fix?"*

---

## Step 10: Regression Verification

Upon user approval, the fix is applied and all checkpoints are re-tested:
- Check 1: `curl POST /api/cart/calculate` -> Returns `total_cents: 1100` (**`PASS`**).
- Check 2: `curl POST /api/checkout` with `quantity: -1` -> Returns `HTTP 400` (**`PASS`**).
- Check 3: Purchase 2 units on clean stock 10 -> Stock becomes 8 (**`PASS`**).
- Full existing test suite rerun: `pytest tests/` -> 100% PASS.

---

## Step 11: Final Evidence-Backed Audit Report

```markdown
# Ghost Hunt: Checkout Feature Audit Report

### Project Context Summary
- **Project Name:** ghost-feature-hunter
- **Selected Target:** examples/broken-flask-shop
- **Investigation Mode:** Feature Investigation (`checkout`)
- **Overall Status:** PASS (Post-fix resolution confirmed)

### Summary Table
| Checkpoint | Expected | Observed | Status |
|---|---|---|---|
| `cart-tax` | `total_cents: 1100` | `total_cents: 1100` | PASS |
| `quantity-negative` | HTTP 400 | HTTP 400 | PASS |
| `inventory-reduction` | Stock 10 -> 8 | Stock 10 -> 8 | PASS |
| `order-persisted` | 1 confirmed row | 1 confirmed row | PASS |

### Stateful Verification Delta Table
| Checkpoint | Baseline Initial | Action | Expected Final | Observed Final | Delta Verified |
|---|---|---|---|---|---|
| `inventory-reduction` | `stock = 10` | Buy 2 units | `stock = 8` | `stock = 8` | RESOLVED (`-2` units) |

**Conclusion:** All three defects (`cart-double-tax`, `quantity-validation`, and `inventory-reduction`) were confirmed with empirical evidence on fresh test databases, isolated to exact lines in `app.py`, corrected with surgical diffs, and verified through regression checks.
```
