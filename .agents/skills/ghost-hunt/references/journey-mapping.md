# Journey Mapping & Checkpoint Design

This guide explains how to define and structure feature verification journeys, whether executing them directly in chat using native agent tools or compiling them into formal JSON journeys for the optional CLI engine.

---

## 1. What is a Verification Journey?

A **Verification Journey** is an ordered sequence of discrete checkpoints testing an end-to-end feature slice across all application layers:
- User interface presentation (DOM / HTML)
- API contract & HTTP response behavior
- Service logic & calculations
- Database persistence & state transitions
- Authorization boundaries
- Failure & validation handling (Error paths)

---

## 2. Checkpoint Anatomy

Every checkpoint must specify six core attributes:

```text
┌────────────────────────────────────────────────────────┐
│ Checkpoint: Order Stock Deduction                      │
├────────────────────────────────────────────────────────┤
│ 1. ID:                    checkout-stock-deduction     │
│ 2. Description:           Stock decreases after order  │
│ 3. Expected Behavior:     Product stock decrements by 2│
│ 4. Expectation Source:    user_requirement             │
│ 5. Verification Channel:  database (or API)            │
│ 6. Explicit Assertion:    inventory.count == 8         │
└────────────────────────────────────────────────────────┘
```

1. **`id`:** Unique, kebab-case identifier (e.g. `cart-tax`, `order-created`, `duplicate-rejected`).
2. **`checkpoint`:** Brief, human-readable summary of what is being verified.
3. **`expected_behavior`:** Unambiguous, testable assertion statement.
4. **`source_of_expectation`:**
   - `user_requirement` — Prompt instructions or user confirmation.
   - `product_documentation` — Docs, README, user stories.
   - `api_contract` — OpenAPI, GraphQL schema, TypeScript types.
   - `existing_test` — Verified behavior from existing test suites.
   - `inferred_assumption` — Hypothesized behavior requiring user validation.
5. **`channel` / `adapter`:** `http`, `browser`, `database`, or `test_runner`.
6. **`assertions`:** Machine-evaluable criteria (e.g. HTTP status 201, JSON path `total_cents == 1100`, SQLite row count == 1).

---

## 3. Journey Plan for Native Agent Execution

When working in chat without the optional CLI, structure your plan clearly before running commands:

```markdown
### Verification Journey: Checkout Feature
1. **Checkpoint 1: [UI] Cart Rendering**
   - Expected: Cart view displays item price of $10.00 and 10% tax rate.
   - Source: `product_documentation`
   - Method: Curl / Browser request to `GET /cart`
2. **Checkpoint 2: [API] Checkout Submission**
   - Expected: `POST /api/checkout` returns HTTP 200 with order ID and total $11.00.
   - Source: `api_contract`
   - Method: Curl request with valid cart payload
3. **Checkpoint 3: [DB] Order Persistence**
   - Expected: `orders` table has 1 new row with `status = 'confirmed'`.
   - Source: `user_requirement`
   - Method: Read-only SQLite query `SELECT status FROM orders WHERE id = :id`
4. **Checkpoint 4: [DB] Inventory Deduction**
   - Expected: `products.inventory` decreases from 10 to 8.
   - Source: `user_requirement`
   - Method: Read-only SQLite query `SELECT stock FROM products WHERE id = 1`
5. **Checkpoint 5: [Error] Out-of-Stock Protection**
   - Expected: `POST /api/checkout` with quantity exceeding stock returns HTTP 400.
   - Source: `user_requirement`
   - Method: Curl request with quantity 999
```

---

## 4. Structured Journey for Optional CLI (`journeys/<feature>.json`)

If running via `ghost-hunter audit`, define the journey in JSON conforming to `schemas/journey.schema.json`. See [templates/journey-template.json](../templates/journey-template.json).

### Validation Safeguards:
- Step IDs must be unique.
- Adapter must be one of `http`, `database`, `browser`.
- Mutating actions require explicit write permissions.
- Never overwrite existing journey files without user approval.

