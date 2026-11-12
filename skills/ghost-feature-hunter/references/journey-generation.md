# Journey Generation & Validation

This guide covers **Workflow 4 (Journey Generation)** and **Workflow 5 (Journey Validation)**.

---

## Workflow 4: Journey Generation

A verification journey is an explicit JSON sequence of checkpoints spanning the entire user journey.

### Step-by-Step Generation:
1. Break down the user journey into discrete, observable steps.
2. For each checkpoint, define:
   - `id`: Stable, lowercase identifier (e.g. `cart-tax`, `order-persisted`).
   - `checkpoint`: Plain-language description.
   - `adapter`: `http`, `database`, or `browser`.
   - `expected_behavior`: Exact, testable behavioral expectation.
   - `source_of_expectation`: `user_requirement`, `product_documentation`, `api_contract`, `existing_test`, or `inferred_assumption`.
   - `settings`: Adapter-specific execution arguments and explicit assertions.

### Canonical Journey Template (`journeys/<feature>.json`):

```json
{
  "schema_version": "1.0",
  "feature": "checkout",
  "description": "End-to-end checkout verification journey.",
  "steps": [
    {
      "id": "cart-calculation",
      "checkpoint": "Cart applies single tax rate",
      "adapter": "http",
      "expected_behavior": "Two items at 500 cents with 10% tax total 1100 cents",
      "source_of_expectation": "user_requirement",
      "settings": {
        "method": "POST",
        "url": "/api/cart/calculate",
        "json": {"items": [{"product_id": 1, "quantity": 2}]},
        "checks": {
          "status_code": 200,
          "json_equals": {"total_cents": 1100}
        }
      }
    },
    {
      "id": "order-persistence",
      "checkpoint": "Confirmed order exists in database",
      "adapter": "database",
      "expected_behavior": "Order row exists with status confirmed",
      "source_of_expectation": "product_documentation",
      "settings": {
        "database_url_env": "APP_DATABASE_URL",
        "query": "SELECT state FROM orders WHERE user_id = :user_id",
        "parameters": {"user_id": "alice"},
        "checks": {
          "row_count_equals": 1,
          "first_row_equals": {"state": "confirmed"}
        }
      }
    }
  ]
}
```

---

## Workflow 5: Journey Validation

Every generated journey must be validated before execution:

1. **Schema Check:** Ensure conformance with `schemas/journey.schema.json`.
   - Unique step IDs.
   - Valid adapter name (`http`, `database`, `browser`).
   - Non-empty `expected_behavior`.
   - Bounded steps (1 to 100).
2. **Safety Review:**
   - Are write methods (`POST`, `PUT`, `DELETE`, `click`, `fill`) properly guarded?
   - Is `database_url_env` pointing to a file-backed SQLite database inside the project?
   - Are URLs restricted to `base_url` or `allowed_hosts`?
3. **Save Safeguard:**
   - Never overwrite an existing journey file without explicit operator confirmation.
