# Transparent Limitations & Boundaries

Ghost Hunt prioritizes honesty and reliability above marketing claims. When an analysis or verification cannot be performed deterministically, Ghost Hunt explicitly discloses the boundary and reports **`UNKNOWN`** rather than improvising guesses.

---

## 1. Static Analysis Boundaries

Static analysis operates without executing code and has inherent theoretical and practical boundaries:

- **Dynamic Dispatch & Reflection:** Endpoint routes constructed via dynamic metaprogramming (e.g., Python `getattr(obj, route_name)()`, Ruby `send()`, PHP variable variables) cannot be fully resolved statically. They are reported as dynamic route candidates.
- **Microservices & Reverse Proxies:** In complex distributed architectures where API routing is managed via Nginx, Traefik, Kong, or Kubernetes Ingress rather than code decorators, backend endpoints may appear uncalled by local frontend code. Ghost Hunt classifies these as "External / Proxy Route Candidates" requiring owner confirmation.
- **Third-Party SDKs & Webhooks:** Endpoints meant exclusively for third-party webhook delivery (Stripe, GitHub, Twilio) have zero in-repo callers. Ghost Hunt flags them as `Potentially Unused` with a mandatory `Requires Owner Confirmation` label to prevent accidental deletion.

---

## 2. Language Capability Matrix

Ghost Hunt declares transparent, honest capability levels across programming language ecosystems:

| Ecosystem | Declared Level | What Works | What Is Limited |
|---|---|---|---|
| **Python** | `deep-static` | Parser-backed Python standard AST. Comprehensive route extraction (Flask, FastAPI, Django), model inspection, exception handling analysis, transaction boundaries, and AST normalization. | Dynamic route registration inside arbitrary runtime loops. |
| **JavaScript / TypeScript** | `structural` | AST-aware lexical scanning. Route extraction (Express, Next.js), client calls (`fetch`, `axios`), UI actions (JSX/TSX button onClick callbacks), component mapping. | Complex higher-order component factories and type-level routing tricks. |
| **Go** | `structural` | Regex and structural token scanning for `net/http`, Gin, Chi, Fiber routes, struct models, and test functions. | Interface-based dynamic handlers without literal route paths. |
| **Java / Kotlin** | `structural` | Spring Boot `@GetMapping`, `@PostMapping`, controller mapping, JPA `@Entity` models, and JUnit test blocks. | Runtime reflection and dynamic dependency injection containers. |
| **C# / .NET** | `structural` | ASP.NET Core controller attributes (`[HttpGet]`, `[Route]`), Minimal API calls, and Entity Framework model classes. | Dynamic assembly loading and middleware pipelines without literal paths. |
| **PHP / Ruby / Rust** | `structural` | Structural route matching across Laravel, Symfony, Rails, Sinatra, Actix, and Axum. | Macro-generated routes and dynamic method dispatch. |
| **Swift / C / C++ / SQL** | `inventory-only` | File identification, line counts, and basic symbol inventory. | Deep semantic data flow and route analysis not supported. |

---

## 3. Database Adapter Scope

- The Python CLI's built-in `DatabaseAdapter` natively targets **file-backed SQLite databases** using Python's standard library `sqlite3` and C-level authorizer callbacks.
- **PostgreSQL, MySQL, and Oracle:** The CLI database adapter does not include external drivers by default to maintain zero external C-dependencies. When investigating features on PostgreSQL or MySQL, AI coding agents use native terminal tools (`psql`, `mysql`, application CLI commands) in Level 2 read-only mode, or developers run the tests through the application's native test suite.

---

## 4. Browser Verification Scope

- The optional browser adapter requires **Playwright** (`pip install "ghost-feature-hunter[browser]"`).
- In constrained headless environments without browser binaries or graphical displays, browser checks evaluate to **`UNKNOWN`** with a clear explanation rather than crashing.
- AI coding agents with built-in browser subagents execute UI checks natively without requiring local Playwright installation.

---

## 5. When Ghost Hunt Reports `UNKNOWN`

Ghost Hunt strictly reports **`UNKNOWN`** in the following circumstances:

1. **Unreachable Server:** The target application is offline or connection is refused.
2. **Missing Permissions:** Write operations attempted without `--allow-writes` or production access without dual approval.
3. **Contaminated Test State:** A preceding step left the test database in an undefined or unresettable state.
4. **Inferred Assumptions:** Behavioral expectations deduced from conventions or naming patterns rather than explicit requirement documentation.
5. **Missing Tooling:** Runtimes or drivers required to execute a check are not installed on the system.

Ghost Hunt will **never relabel an UNKNOWN outcome as PASS or FAIL.**
