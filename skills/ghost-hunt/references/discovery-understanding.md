# Discovery & Feature Understanding

This guide covers **Project Context & Scope Locking**, **Feature Discovery**, **End-to-End Flow Tracing**, and **Requirement Provenance Analysis**.

---

## 0. Project Context & Scope Locking

Before discovering routes or tracing features:
1. **Detect Project Bounds:** Identify workspace root, Git root, and package manifests (`pyproject.toml`, `package.json`).
2. **Isolate Primary Application Source from Examples:**
   - Categorize `src/`, `lib/`, `app/` as primary application source.
   - Categorize `examples/`, `fixtures/`, `benchmarks/`, `demos/` as supporting non-production targets.
   - **Never silently choose an example or benchmark directory as the primary application.**
   - If auditing Ghost Hunt itself, the target is `ghost-feature-hunter`, not `examples/broken-flask-shop`.
3. **Explicit Paths Over Inferred Roots:** If the user specifies an explicit application path, that path overrides any inferred root.

---

## 1. Feature Discovery

Feature discovery builds a concrete map of all code assets involved in a feature.

### Native Agent Discovery (Default)
When using the Ghost Hunt skill in chat, inspect the project structure directly using native file search, globbing, and syntax inspection:

1. **Find Routes & Endpoints:** Search for routing decorators and handlers across frameworks:
   - Flask / FastAPI: `@app.route`, `@app.get`, `@app.post`, `@router.get`, `APIRouter()`
   - Django: `urlpatterns = [path(...)]`, `views.py`
   - Express / Node: `app.get()`, `app.post()`, `router.use()`
   - Next.js: `app/api/.../route.ts`, `pages/api/...`
2. **Find Models & Schema:** Search for ORM definitions:
   - SQLAlchemy / SQLModel: `class ... (Base)`, `Column(...)`, `relationship(...)`
   - Prisma: `schema.prisma`
   - Mongoose / TypeORM / Django: `models.Model`, `@Entity()`
3. **Find Existing Tests:** Identify existing assertions and fixtures:
   - `tests/test_*.py`, `*.spec.ts`, `*.test.js`
4. **Find Frontend Views & Assets:** Identify templates and components dispatching requests:
   - `templates/*.html`, `src/components/**/*.tsx`, `static/**/*.js`

### Optional Deterministic CLI Discovery
If the optional `ghost-hunter` CLI is installed in the environment:
```console
ghost-hunter discover --project-root .
```
This runs AST-based static analysis against Flask routes and models without executing application code, outputting `ghost-reports/ghost-discovery.json`.

---

## 2. End-to-End Flow Tracing

Once relevant files are located, trace the data flow backwards and forwards across the complete application lifecycle:

```text
1. User Action ──> 2. Route & HTTP ──> 3. Controller / Validation
                                                │
6. Client Response <── 5. DB Mutation <── 4. Service / Business Rules
```

1. **User Action / UI Trigger:** Locate the form, button click, or client-side fetch triggering the interaction (e.g. `templates/checkout.html` submitting to `/checkout`).
2. **Route & HTTP Method:** Identify the exact HTTP path, allowed methods, and routing constraints.
3. **Controller & Input Validation:** Inspect how request parameters, headers, cookies, and JSON payloads are deserialized and validated.
4. **Service & Business Rules:** Trace calculations (e.g., pricing, discounts, tax), inventory checks, permissions, and third-party API calls.
5. **Database Queries & Mutations:** Trace SQL SELECT queries, transactions (`BEGIN`, `COMMIT`, `ROLLBACK`), and state persistence.
6. **Response & Side Effects:** Trace status codes, JSON response shapes, flash messages, email dispatch, and event logging.

---

## 3. Requirement & Acceptance Criteria Analysis

Every verification checkpoint must be anchored to an authoritative source of expectation. Never manufacture requirements.

### The Five Sources of Expectation:
1. **`user_requirement`:** Constraints explicitly stated by the developer in the chat prompt (e.g., "orders over $50 should have free shipping"). **Must quote or cite the relevant user instruction.** Never assign this tag to assumptions made by the agent.
2. **`product_documentation`:** Specifications documented in `README.md`, docs, OpenAPI/Swagger specifications, or user stories. **Must include document path, section, and line reference.**
3. **`api_contract`:** Formal schemas, TypeScript interfaces, Pydantic models, or proto definitions. **Must include the exact contract file and line location.**
4. **`existing_test`:** Behavioral assertions codified in passing unit, integration, or e2e test suites. **Must cite test file and test function.** Note: Passing tests are evidence of an existing assertion, not proof that the underlying business rule is correct.
5. **`inferred_assumption`:** Hypotheses deduced from source code reading, variable names, or conventions.

> [!IMPORTANT]
> **The Critical Rule for Inferred Assumptions:**
> When an expectation is an inferred assumption:
> - Clearly label it as `inferred_assumption`.
> - Explain why it was inferred.
> - Ask for user confirmation before classifying a discrepancy as a confirmed business defect.
> - An unconfirmed assumption must evaluate to **`UNKNOWN`**, never a fabricated `FAIL` or `PASS`.
> - Do not manufacture a `FAIL` simply because the code differs from conventional behavior.
