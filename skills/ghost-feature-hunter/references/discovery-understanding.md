# Discovery & Feature Understanding

This guide covers **Workflow 1 (Feature Discovery)**, **Workflow 2 (Feature Understanding)**, and **Workflow 3 (Requirement Analysis)**.

---

## Workflow 1: Feature Discovery

Run the advisory static discovery command against the target project:

```console
ghost-hunter discover --project-root <path>
```

### Safety & Method:
- Discovery parses syntax trees using standard library Python `ast`.
- It **never imports application modules** or executes shell commands.
- It identifies:
  - Literal routes (`@app.route`, `@app.get`, `@app.post`, etc.).
  - Database models (declarative SQLAlchemy bases).
  - Test files (`test_*.py`, `*_test.py`).
  - Frontend assets (`.html`, `.js`, `.tsx`, `.vue`, etc.).
  - Service/controller modules.

### Output:
Outputs `ghost-reports/ghost-discovery.json` and `ghost-reports/ghost-discovery.md`.

---

## Workflow 2: Feature Understanding

Follow discovered references through the application stack from user action down to persistence:

1. **Frontend Trigger:** Locate the form, button, or client script dispatching the feature request (e.g. `static/shop.js` or React component).
2. **Route & Endpoint:** Map the route path and HTTP method in the controller (e.g. `@app.post("/api/checkout")`).
3. **Controller / Request Parsing:** Inspect how parameters, payloads, headers, and authentication are deserialized.
4. **Service & Business Rules:** Trace calculations, inventory checks, third-party calls, and domain validations.
5. **Persistence Layer:** Trace SQL transactions, session commits, and table mutations.
6. **Delivery & Confirmation:** Trace email/notification queues, background jobs, and the HTTP response payload returned to the client.

---

## Workflow 3: Requirement and Acceptance Criteria Analysis

A verification checkpoint is only valid if its expected behavior has an authoritative source.

### Expectation Hierarchy:
1. **User-Provided Requirement:** Explicit constraints defined by the developer or stakeholder in the prompt.
2. **Product Documentation:** Specifications in `README.md`, OpenAPI/Swagger specs, or user stories.
3. **Existing API Contract:** Explicit schema definitions, Pydantic/dataclass models, or TypeScript interfaces.
4. **Existing Tests:** Expectations codified in passing unit or integration tests.
5. **Explicitly Inferred Assumption:** Hypothesized behavior deduced from source code reading.

> [!IMPORTANT]
> **The Zero-Inference Rule:**
> Inferred expectations must be explicitly tagged as `"source_of_expectation": "inferred_assumption"` and presented to the operator for confirmation before being treated as an authoritative failure. Never convert discovered routes into expected behavior automatically.
