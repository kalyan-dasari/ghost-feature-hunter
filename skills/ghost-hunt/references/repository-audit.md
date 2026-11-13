# Whole-Repository Audit Playbook

When invoked with `/ghost-hunt audit`, Ghost Hunt performs a comprehensive architectural, connection, and code health audit across the entire selected project.

Unlike single-feature investigations, a repository audit operates globally across all application layers using static analysis and native agent inspection tools.

---

## 1. The 6-Part Audit Workflow

```text
1. Architecture Inventory ──> 2. Route Connection Analysis ──> 3. Unused Code Candidates
                                                                          │
6. Code Waste Estimates <── 5. Duplicate Logic & Complexity <── 4. Dependencies
```

### Part 1: Project Architecture Inventory
Map all repository components into discrete categories:
- **Applications & Services:** Entry points (`main.py`, `app.py`, `index.ts`, `server.js`).
- **Route Handlers:** API routes, controllers, middleware.
- **Data Models:** Schemas, ORM models, migrations.
- **Frontend Assets:** Pages, templates, components, styles.
- **Test Suites:** Unit, integration, e2e test files.
- **Configuration:** Manifests, environment variables, CI workflows.

### Part 2: Route & Endpoint Connection Analysis
Cross-reference backend route handlers against frontend callers and tests:
1. **Missing Route Candidates:** Frontend calls an endpoint (e.g. `fetch('/api/users/profile')`) that matches no registered backend route.
2. **Method / Path Mismatches:** Client dispatches a `GET` where the backend route strictly requires `POST`, or uses a differing parameter name.
3. **Potentially Unused Endpoints:** Backend registers a route, but no static callers exist in frontend, tests, or documentation. (Always label as *candidates*—they may serve external webhooks or mobile clients).
4. **Uncovered Routes:** Registered endpoints with zero matching tests in the test suite. (Testing gaps, not necessarily broken code).

### Part 3: Unused Code Candidates
Build a static reference graph across source files:
- **Files with no incoming imports.**
- **Exported functions with no identified callers.**
- **Classes with no identifiable instantiations.**
- **Unreferenced template components or styles.**

> [!CAUTION]
> **Dynamic Loading Caveats:**
> Before reporting any file or symbol as unused, evaluate dynamic imports, reflection, framework auto-discovery (e.g. Flask blueprints, Next.js app router), plugin registries, and CLI entry points.
> Classify candidates as: `Confirmed Referenced`, `No Static References Found`, or `Requires Owner Confirmation`. Never delete code automatically.

### Part 4: Dependency Audit
Inspect manifests (`pyproject.toml`, `package.json`, `requirements.txt`):
- Declared dependencies with no static imports in source.
- Dev/test dependencies mistakenly placed in production manifests.
- Duplicate or overlapping packages.

### Part 5: Duplicate Logic & Complexity Hotspots
Identify structural duplication:
- Identical or near-identical business calculations in multiple controllers.
- Repeated validation routines that should be unified into schema models.
- Redundant API client wrappers.
- Note: Never recommend refactoring purely for stylistic preference; justify with concrete maintenance or correctness benefits.

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
- **Category:** `<missing_route | mismatched_endpoint | potentially_unused_endpoint | uncovered_route | unused_code | duplicate_logic | dependency>`
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

