# Multi-Language Detection & Capability Architecture

> **Language detection is not language support.**  
> Detecting a file extension (`.go`, `.rs`, `.java`, `.cs`) proves that files exist; it does not prove that deep AST, route, model, and caller analysis are supported.
>
> Ghost Hunt transparently discloses its analysis capabilities, capability levels, and limitations for every language present in a project.

---

## 1. The Four Honest Capability Levels

Ghost Hunt categorizes every ecosystem into one of four capability levels:

| Capability Level | Definition | Permitted Claims | Disclosed Limits |
|---|---|---|---|
| **`deep-static`** | Full parser-backed AST with symbols, imports, references, routes, models, and caller graph. | Statically proven symbols, callers, and syntax structures. | Dynamic runtime metaprogramming and reflection require execution. |
| **`structural`** | Syntax-aware structural tokenizer extracting functions, structs, annotations, routes, and tests. | Static route paths, methods, symbol signatures, test files, and unfinished items. | Metaprogrammed routing, dynamic dependency injection, and compiler plugins require toolchain execution. |
| **`inventory-only`** | File, path, and manifest identification only without syntax parsing. | Accurate file inventories and declared dependency lists. | AST parsing, route extraction, and reference graphs are not implemented in the engine. |
| **`runtime-verified`** | A real test or verification check was executed against live uncontaminated state and observed. | Confirmed feature behavior at the executed checkpoint. | Never infer unasserted behavior or state outside the checkpoint. |

> [!IMPORTANT]
> `deep-static` and `structural` analysis NEVER imply runtime verification. A static test reference or assertion candidate is not proof that the test executed or passed.

---

## 2. Granular Capability Flags

Ghost Hunt tracks 13 individual capability flags for every language adapter:

1. `syntax_parsing`: Syntax-aware AST or token parsing (not plain regex).
2. `symbol_analysis`: Extraction of functions, methods, classes, and exported interfaces.
3. `import_export_analysis`: Discovery of module imports, requires, and exports.
4. `reference_analysis`: Local caller graphs tracing function and symbol references.
5. `route_extraction`: Backend HTTP route, controller, and handler discovery.
6. `client_call_extraction`: Discovery of frontend `fetch`, `axios`, and HTTP client requests.
7. `ui_analysis`: Component tree, button click handler, and form submission tracing.
8. `model_schema_analysis`: Discovery of database models, ORM entities, and schemas.
9. `test_discovery`: Identification of test files and test methods.
10. `test_assertion_candidates`: Identification of response assertions within test functions.
11. `dependency_usage_analysis`: Cross-referencing declared manifest packages against imports.
12. `unfinished_code_detection`: Identification of stubs, `panic`, `TODO`, `pass`, and silent catches.
13. `duplicate_detection`: AST-based structural duplicate logic detection.

---

## 3. Priority 1 Ecosystems (Production Analyzers)

### Python (`deep-static`)
- **Frameworks:** Flask (Full), FastAPI (Full), Django (Partial AST).
- **Parser:** Python standard library `ast` module (application code is never imported or executed).
- **Capabilities:** Symbols, routes, callers, Pydantic schemas, SQLAlchemy models, Django models, unfinished items, AST-based duplicate detection.
- **Limitations:** Dynamic metaclass routing and runtime `reverse()` URL resolving require execution.

### JavaScript & TypeScript (`deep-static`)
- **Frameworks:** Express, Next.js (App & Pages Routers), React, Fastify, NestJS.
- **Parser:** Lexical and structural tokenizer scanning component trees and route files.
- **Capabilities:** App Router (`route.ts`) & Pages Router (`pages/api`), multiline JSX `<button>` and `<form>`, client API calls, unfinished items.
- **Limitations:** Higher-order components and dynamic runtime middleware chains are approximated.

### Go (`structural`)
- **Frameworks:** Gin, Echo, Fiber, Chi, `net/http`.
- **Parser:** Go structural syntax tokenizer.
- **Capabilities:** Route extraction (including group prefixes like `r.Group("/api/v1")`), exported symbols (capitalized functions/types), GORM/struct models, `panic("not implemented")` detection, `_test.go` test discovery with assertion candidates (`assert.`, `require.`, `t.Errorf`).
- **Limitations:** Full Go compiler execution, reflection, and interface dispatching require the Go toolchain.

### Java (`structural`)
- **Frameworks:** Spring MVC, Spring WebFlux, JAX-RS.
- **Parser:** Java structural annotation and class tokenizer.
- **Capabilities:** Class-level `@RequestMapping` / `@Path` prefixes, method annotations (`@GetMapping`, `@PostMapping`, `@Path`), JPA `@Entity` models, `UnsupportedOperationException` detection, JUnit `@Test` discovery.
- **Limitations:** Dynamic Spring DI bean wiring and runtime bytecode manipulation (CGLIB) require the JVM.

### C# (`structural`)
- **Frameworks:** ASP.NET Core Controllers and Minimal APIs.
- **Parser:** C# attribute and syntax tokenizer.
- **Capabilities:** Controller routes (`[HttpGet]`, `[Route]`), Minimal APIs (`app.MapGet`), EF Core models (`[Table]`, `DbContext`), `NotImplementedException` detection, xUnit/NUnit tests.
- **Limitations:** Roslyn compiler execution and runtime middleware pipelines require the dotnet SDK.

---

## 4. Priority 2 Ecosystems

### PHP (`structural`)
- **Frameworks:** Laravel (`Route::get`), Symfony (`#[Route]`), Slim (`$app->get`).
- **Capabilities:** Routes, Eloquent models, client calls (`Http::get`), `BadMethodCallException` detection, PHPUnit/Pest tests.
- **Limitations:** Service container reflection requires the PHP runtime.

### Ruby (`structural`)
- **Frameworks:** Rails (`routes.rb`, `resources`), Sinatra.
- **Capabilities:** Route verbs and REST resource expansion, ActiveRecord models, `NotImplementedError` detection, RSpec/Minitest tests.
- **Limitations:** Metaprogramming and `method_missing` dispatch require the Ruby VM.

### Rust (`structural`)
- **Frameworks:** Axum (`.route()`), Actix Web (`#[get]`), Rocket.
- **Capabilities:** Routes, structs, traits, `todo!()`/`unimplemented!()` detection, `#[test]` discovery.
- **Limitations:** Procedural macro expansion and trait monomorphization require `rustc` / `cargo`.

### Kotlin (`structural`)
- **Frameworks:** Spring Kotlin, Ktor routing DSL.
- **Capabilities:** Spring annotations, Ktor `routing { get(...) }`, data class models, `TODO()` detection, JUnit tests.
- **Limitations:** Inline reified functions and compiler plugins require `kotlinc`.

---

## 5. Foundation & Inventory Ecosystems

### C and C++ (`inventory-only`)
- **Extensions:** `.c`, `.h`, `.cpp`, `.hpp`, `.cc`, `.cxx`
- **Capabilities:** File inventory and manifest identification.
- **Toolchain Route:** Clang / libclang or compilation database (`compile_commands.json`).

### Swift (`inventory-only`)
- **Extensions:** `.swift`
- **Capabilities:** File inventory and SwiftPM manifest identification.
- **Toolchain Route:** `swift-syntax` parser or SwiftPM toolchain.

### SQL (`structural` / Inventory DDL)
- **Extensions:** `.sql`
- **Capabilities:** Schema table discovery (`CREATE TABLE` definitions).
- **Limitations:** Stored procedures, triggers, and dialect-specific procedural SQL require specialized database parsers.

---

## 6. Agent-Native Investigation Without the Python CLI

When Ghost Hunt operates as an Agent Skill inside an AI coding agent:
1. **Never Skip Languages:** The agent uses native tools (`read_file`, grep, terminal test runners) to investigate code in any language.
2. **Read Manifests Directly:** Inspect dependencies in `go.mod`, `pom.xml`, `Cargo.toml`, `package.json`.
3. **Trace Full-Stack Flows:** Follow handlers from entry points to database queries across language boundaries.
4. **Execute Safe Existing Checks:** Run project tests via terminal (`go test ./...`, `dotnet test`, `mvn test`, `pytest`) when safe.
5. **Report Honest Levels:** Distinguish static candidates from verified passes in the final report.
