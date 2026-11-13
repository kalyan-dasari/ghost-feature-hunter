# Whole-Repository Audit Playbook

When invoked with `/ghost-hunt audit`, Ghost Hunt performs a comprehensive architectural, connection, and code health audit across the entire selected project.

Unlike single-feature investigations, a repository audit operates globally across all application layers using static analysis and native agent inspection tools.

---

## 1. The 6-Part Audit Workflow

```text
1. Architecture Inventory ──> 2. Route Connection Analysis ──> 3. Ghost Features & Unfinished
                                                                           │
6. Code Waste Estimates <── 5. Structural Duplication <── 4. Reference Graph & Hygiene
```

### Part 1: Architecture & Capability Inventory
Map all repository components and declare explicit analysis capabilities:
- **Language / Framework Capability Matrix:** Detail detected ecosystems, supported capabilities, and explicit limitations. *(See [references/language-support.md](language-support.md))*
- **Applications & Services:** Entry points (`main.py`, `app.py`, `index.ts`, `server.js`).
- **Route Handlers:** API routes, controllers, middleware.
- **Data Models:** Schemas, ORM models, migrations.
- **Frontend Assets:** Pages, templates, components, styles.
- **Test Suites:** Unit, integration, e2e test files.
- **Configuration:** Manifests, environment variables, CI workflows.

### Part 2: Route & Endpoint Connection Analysis
Cross-reference backend route handlers against frontend callers and tests:
1. **Missing Route Candidates:** Frontend calls an endpoint with no registered backend route in its local application or across services.
   - **Cross-Service Matching:** If an API client in `frontend` calls `/api/users` and `backend` registers `/api/users`, classify as `matching_service_route` (not missing).
   - **External Service Calls:** Calls targeting external origins (`http://`, `https://`, `api.stripe.com`, etc.) are recognized as external calls and never flagged as missing local routes.
   - **Reverse-Proxy Candidates:** When reverse-proxy or gateway configurations (`next.config.js` rewrites, Vite proxy, Nginx `proxy_pass`) exist, unmatched endpoints are reported as low-confidence reverse-proxy candidates rather than confirmed missing routes.
2. **Method / Path Mismatches:** Client dispatches an HTTP method or parameterized path incompatible with the route handler.
3. **Potentially Unused Endpoints:** Backend registers a route, but no static callers exist in frontend, tests, or documentation. (Always label as *candidates*—they may serve external webhooks or mobile clients).
4. **Route Test Coverage Evaluation (Function-Level):**
   - **`test_assertion_candidate`:** A single test function/case calls the route AND asserts on response attributes (`status_code`, `json()`, `data`, `text`).
   - **`test_reference_candidate`:** Route is mentioned in a test file, string literal, fixture, or call without response assertion (or call in one test and assertion in another).
   - **`testing_gap_candidate`:** Route is absent from tests or mentioned only in comments.
   - **Critical Rule:** Static analysis NEVER claims `test_verified`. That status is reserved exclusively for runtime verified journey execution.

### Part 3: Ghost Feature & Unfinished Implementation Detection
Discover features that appear to exist in one layer but have missing or incomplete implementation paths:
- **Ghost Feature Candidates:**
  - Navigation link pointing to a missing page or route (`<Link href="/billing">`).
  - Action button with empty or missing event handler (`onClick={() => {}}`).
  - Form collecting user inputs without an `onSubmit` handler or `action` pipeline.
  - Route with an empty, pass, or `NotImplementedError` body.
  - Orphaned business service functions with zero callers in production application code (test references are recognized but do not disguise dead production code).
  *(See [references/ghost-features.md](ghost-features.md))*
- **Empty / Unfinished Implementation Candidates:**
  - Empty functions or methods (`pass`, `...`, `placeholder return`).
  - Explicit `throw new Error("TODO")` or `raise NotImplementedError`.
  - Silent exception swallowing (`except Exception: pass`, `catch (e) {}`).
  - Active `TODO`, `FIXME`, `XXX` markers.
  - **Context Filter:** Never report abstract methods (`@abstractmethod`, `abc.ABC`, `typing.Protocol`), interface declarations, or test mocks as defects!

### Part 4: Reference Graph & Dependency Hygiene
Build a static reference graph across source files and package manifests per application boundary:
- **Application Attribution:** Associate manifests with their owning application (e.g. `backend/pyproject.toml` vs `frontend/package.json`).
- **Dependency Classification:** Distinguish `runtime`, `dev`, `test`, `build`, and `optional` dependencies. Only runtime dependencies without application imports are flagged as potentially unused.
- **Inventory-Only Manifests:** For unsupported dependency ecosystems (`Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `composer.json`, `Gemfile`), disclose them as `inventory-only` with `usage_analysis_supported: False`. Do not falsely claim import usage analysis.
- **Finding States:** Classify unused dependencies as `Requires Owner Confirmation` with severity `Low`. Never delete packages automatically.

### Part 5: Structural Duplicate Logic
Identify redundant implementation logic comparing normalized syntax bodies, **not matching names**:
- **Normalized Structure Matching:** Strip docstrings and compare normalized AST statement sequences.
- **Name Invariance:** Two functions with different names (`format_usd` and `render_currency`) sharing identical normalized statements are detected as duplicate logic.
- **Different Implementations with Same Name:** Functions sharing the same name but possessing different implementation logic are **not** reported as duplicates.
- **Line Deduplication:** Calculate non-overlapping line counts. Overlapping sub-blocks are never counted twice.

### Part 6: Estimated Code Waste
Compute conservative, evidence-backed metrics:
- Number of candidate unused files and non-overlapping lines of code.
- Number of potentially unused endpoints.
- Uncovered route count.
- Lines of duplicated logic.
- **Strict Constraint:** Never count the same source lines multiple times. Never invent monetary, performance, or time-saving figures.

---

## 2. Structured Finding Schema

Every repository audit finding must adhere to this schema:

```markdown
### Finding [`<FINDING_ID>`]: `<short_title>`
- **Category:** `<ghost_feature_candidate | missing_route | method_path_mismatch | empty_or_unfinished_implementation | potentially_unused_endpoint | testing_gap | duplicate_logic | dependency_hygiene>`
- **Severity:** `<Critical | High | Medium | Low | Informational>`
- **Confidence:** `<High | Medium | Low>`
- **Evidence:** `<exact_code_quote_or_search_command>`
- **Source Location:** `<file_path>:<line_number>`
- **Related Reference:** `<caller_file>:<line>` (or `None identified`)
- **Explanation:** `<Clear description of the disconnection or issue>`
- **Potential Impact:** `<What breaks or maintenance cost>`
- **Why It Might Be a False Positive:** `<Dynamic loading, external webhook, planned feature, etc.>`
- **Recommended Action:** `<Actionable guidance for maintainers>`
```
