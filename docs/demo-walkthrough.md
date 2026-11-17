# Ghost Hunt — Demonstration Walkthrough: Broken Flask Shop

This walkthrough demonstrates how Ghost Hunt discovers architecture, builds an 8-layer Feature Connection Map, identifies cross-layer contract defects, generates verification journeys, and evaluates live execution paths.

The target repository is `examples/broken-flask-shop`, a realistic e-commerce application containing intentional wiring defects, unhandled state transitions, and contract mismatches.

---

## 1. Discovery & Architecture Mapping

Run the discovery engine to identify languages, frameworks, backend routes, frontend client calls, and application boundaries:

```bash
ghost-hunter discover -p examples/broken-flask-shop
```

### Observed Output:
```text
Languages: HTML, JSON, JavaScript/TypeScript, Markdown, Other, Python; routes: 10; models: 0; applications: 1
Flask compatibility view: 8 routes
JSON: examples/broken-flask-shop/ghost-reports/ghost-discovery.json
Markdown: examples/broken-flask-shop/ghost-reports/ghost-discovery.md
```

Ghost Hunt automatically catalogs endpoints, identifies client callers, and classifies source files into roles (`application_source`, `fixture`, `test`).

---

## 2. 8-Layer Feature Connection Map

To understand how the checkout feature is wired across all application tiers, run the `map` command targeting `checkout`:

```bash
ghost-hunter map checkout -p examples/broken-flask-shop
```

### Observed Output:
```text
Feature Connection Map for 'broken-flask-shop':
- Nodes: 6
- Edges: 5
- Broken Edges: 1
- Missing Edges: 1
- Orphaned Nodes: 0
- Contract Findings: 1

Feature Connection Pipeline:
UI Action ===> Client API ===> Route Handler ===> Controller ===> Service ===> Database ===> Response ===> Tests
-----------------------------------------------------------------------------------------------------------------
  [OK] POST /api/checkout --> def checkout()
  [BROKEN] GET /api/checkout -X- POST /api/checkout (HTTP Method mismatch: client calls GET, but route only accepts ['POST'])
  [OK] def checkout() --> DB Operations (0 writes, 1 reads)
  [OK] def checkout() --> Response: HTTP 201 (JSON)
  [MISSING] POST /api/checkout -X- MISSING: Test Coverage for /api/checkout (Testing gap: route lacks unit or integration test coverage)

Cross-Layer Contract Findings:
  [High] method_mismatch: HTTP method mismatch: Client sends GET, backend only supports ['POST']
    Evidence: static/shop.js:7 (GET) vs app.py:140 (['POST'])
    Fix: Add 'GET' to route handler methods or update client request.
```

### Visualizing the 8-Layer Graph (Mermaid)

Generate the Mermaid flowchart directly from the connection graph:

```bash
ghost-hunter map checkout -p examples/broken-flask-shop --mermaid
```

```mermaid
graph LR
    %% Ghost Hunt 8-Layer Feature Connection Map
    subgraph CLIENT_API ["2. Client API"]
        client_call_1["GET /api/checkout"]
    end
    subgraph ROUTE ["3. Backend Route"]
        route_8["POST /api/checkout"]
    end
    subgraph CONTROLLER ["4. Controller / Handler"]
        ctrl_8_checkout["def checkout()"]
    end
    subgraph DATABASE ["6. Database / Model"]
        db_route_8["DB Operations (0 writes, 1 reads)"]
    end
    subgraph RESPONSE ["7. Response / UI State"]
        resp_route_8["Response: HTTP 201 (JSON)"]
    end
    subgraph TEST ["8. Tests & Verification"]
        test_route_8["MISSING: Test Coverage for /api/checkout"]
    end
    route_8 -->|Connected| ctrl_8_checkout
    client_call_1 -.->|BROKEN: HTTP Method mismatch: client calls GET, but route only accepts ('POST')| route_8
    ctrl_8_checkout -->|Connected| db_route_8
    ctrl_8_checkout -->|Connected| resp_route_8
    route_8 -.->|MISSING LINK| test_route_8
    style client_call_1 fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px
    style route_8 fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px
    style ctrl_8_checkout fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px
    style db_route_8 fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px
    style resp_route_8 fill:#e8f8f5,stroke:#2ecc71,stroke-width:1px
    style test_route_8 fill:#ffeaa7,stroke:#d63031,stroke-width:2px,stroke-dasharray: 5 5
```

---

## 3. Automated Journey Planning

Using the connection map's discovered endpoints, parameters, and expected response codes, plan a testable verification journey:

```bash
ghost-hunter plan checkout -p examples/broken-flask-shop
```

### Observed Output:
```text
Generated journey for feature 'checkout':
- Steps generated: 1
- Adapters: http: 1
- Sources of expectation: api_contract: 1
- Journey file saved to: examples/broken-flask-shop/journeys/checkout.json

To audit this feature run:
  ghost-hunter audit checkout -p examples/broken-flask-shop
```

The generated journey step tags expectations with verifiable sources (`api_contract`, `existing_test`, `inferred_assumption`):
```json
{
  "schema_version": "1.0",
  "feature": "checkout",
  "description": "Generated verification journey for checkout feature.",
  "steps": [
    {
      "id": "http-post-api-checkout",
      "checkpoint": "POST /api/checkout returns HTTP 201",
      "adapter": "http",
      "expected_behavior": "POST request to /api/checkout is handled and returns status 201 (JSON)",
      "source_of_expectation": "api_contract",
      "settings": {
        "method": "POST",
        "url": "/api/checkout",
        "checks": {
          "status_code": 201
        },
        "json": {}
      }
    }
  ]
}
```

---

## 4. Live Runtime Verification & Evidence Evaluation

With the application running locally on `http://127.0.0.1:5000`, run the developer audit to execute the journey against live endpoints:

```bash
ghost-hunter audit checkout -p examples/broken-flask-shop --allow-writes
```

### Safety Principles in Action:
1. **Never Assume PASS**: If the server is offline or unreachable, Ghost Hunt records `UNKNOWN`, refusing to guess.
2. **Strict Evidence Attribution**: Every result points to timestamped, redacted HTTP responses or database queries.
3. **Write Protection**: Mutation requests (POST, PUT, DELETE) require `--allow-writes` on the CLI and explicit configuration in `ghost-hunter.json`.

---

## 5. Agent Skill Mode Invocations

When working in an AI coding agent (Antigravity, Claude Code, or Codex), Ghost Hunt runs natively using tool calls without requiring CLI dependencies:

- `/ghost-hunt discover`: Map project architecture, tech stack, and entry points.
- `/ghost-hunt map checkout`: Generate the 8-layer Feature Connection Map and find contract gaps.
- `/ghost-hunt investigate checkout`: Trace the feature from UI to Database, review surrounding code, and propose targeted, test-backed fixes.
- `/ghost-hunt verify`: Re-run tests and journey checkpoints to confirm the defect is resolved without regression.
