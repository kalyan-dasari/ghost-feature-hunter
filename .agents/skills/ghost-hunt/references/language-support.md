# Multi-Language Detection & Capability Architecture

> **Language detection is not language support.**  
> Detecting a file extension (`.go`, `.rs`, `.java`) proves that files exist; it does not prove that deep AST, route, model, and caller analysis are supported.

Ghost Hunt transparently discloses its analysis capabilities and limitations for every language present in a project.

---

## 1. The Language & Framework Capability Matrix

Every project discovery and repository audit report must begin with an explicit capability matrix:

| Language / Framework | Detected | Analysis Capability | Limitations |
|---|---|---|---|
| **Python / Flask** | Yes | Full AST route, model, caller, and unfinished detection | Dynamic decorators and runtime metaclass routing require manual verification. |
| **Python / FastAPI** | Yes | Full AST route, Pydantic model, and unfinished detection | Dynamic dependency injection and runtime middleware require execution. |
| **Python / Django** | Yes | Partial AST urlpatterns extraction (`path`, `re_path`, `include`), view references, and models | Dynamic class-based view dispatching, runtime `reverse()` URL resolution, and plugin-based routing require manual inspection. |
| **JS/TS / Express** | Yes | Route extraction, middleware, client calls, and symbols | Dynamic router middleware chains and runtime mount points require inspection. |
| **JS/TS / Next.js** | Yes | App Router / Pages Router routes, pages, and components | Dynamic catch-all routes (`[...slug]`) are normalized. |
| **JS/TS / React** | Yes | Multiline component tags, UI buttons, handlers, form inputs | Higher-order components and complex context state updates require execution. |
| **Other (Go, Rust, Java, etc.)**| Yes | File inventory and package manifest inspection only (inventory-only) | Deep AST route analysis and dependency usage analysis are not currently implemented; manifests are inventory-only. |

---

## 2. Core Language Adapter Capabilities

Language adapters declare the exact capabilities they implement:

1. **File & Language Identification:** Maps file extensions and paths to canonical languages.
2. **Framework Identification:** Detects framework signatures from imports, package manifests, and configuration files.
3. **Import & Export Discovery:** Maps module dependencies and exported public interfaces.
4. **Function, Class & Component Inventory:** Catalogs definitions across the codebase.
5. **Local Reference & Call Analysis:** Builds caller graphs to trace symbol usage and identify orphaned functions.
6. **Backend Route Extraction:** Discovers endpoints, HTTP methods, and path parameters.
7. **Frontend API Call Extraction:** Discovers `fetch`, `axios`, and `<form action>` requests with HTTP methods and target URLs.
8. **UI Navigation & Component Connections:** Traces `<Link href="...">`, `<button onClick="...">`, and `<form>` submission handlers.
9. **Test Discovery:** Identifies unit, integration, and e2e test files.
10. **Empty & Unfinished Detection:** Detects `pass`, `NotImplementedError`, empty functions, TODO markers, and silent error swallowing.
11. **Dependency & Package Analysis:** Cross-references declared manifest packages against actual code imports.

---

## 3. Supported Ecosystems in the Engine

### Python (Full AST Support & Partial Django)
- **Supported Frameworks:** Flask (Full), FastAPI (Full), Django (Partial).
- **AST Parsing:** Uses Python's standard library `ast` module (safe; application code is never imported or executed).
- **Django Extraction:** Static AST extraction of `urlpatterns` supporting `path()`, `re_path()`, `include()`, view functions, and view classes.
- **Route Normalization:** Standardizes `<int:id>`, `<id>`, and `{id}` to `{id}` for cross-boundary matching.
- **Model Discovery:** Detects SQLAlchemy declarative models, Django models, and Pydantic schemas.
- **Abstract Method Handling:** Checks for `@abstractmethod`, `abc.ABC`, and `typing.Protocol` to prevent false defect reports for intentional interface stubs.
- **Default Return Safeguard:** Legitimate default returns (`return None`, `return False`, `return []`, `return {}`, `return ""`) are recognized as valid implementations and are never flagged as unfinished stubs.
- **Feature Flag Detection:** Tracks `FEATURE_*`, `ENABLE_*`, and `FLAG_*` definitions and consumer conditionals.
- **Structural Duplication Analysis:** AST-based structural duplicate detection is Python-only and preserves external function calls, operators, and constants.

### JavaScript & TypeScript (Structural Parser Support)
- **Supported Frameworks:** Express, Next.js (App & Pages Routers), React, Node.js.
- **Structural Analysis:** Scans route declarations, React component trees, UI actions, and client requests.
- **Next.js Conventions:**
  - App Router: Maps `app/**/route.{ts,js}` and HTTP method exports (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`).
  - Pages Router: Maps `pages/api/**/*.ts` default exports.
  - UI Pages: Maps `app/**/page.tsx` and `pages/**/*.tsx` as navigation destinations.
- **React UI Connections & Multiline Scanning:**
  - Multiline tag scanning for `<button>` and `<form>`.
  - Buttons with named handlers (`onClick={handleClick}` or `onClick={(e) => ...}`) are recognized as valid handlers.
  - Buttons with `type="submit"` or enclosed in working `<form onSubmit={...}>` / `<form action="...">` are recognized as submit triggers and are never flagged as unhandled.
  - Forms are only flagged when containing input controls without any submission handler.
- **Feature Flag Detection:** Tracks `FEATURE_*`, `ENABLE_*`, and `FLAG_*` constants and conditional usages.

---

## 4. Unsupported & Partially Analyzed Languages

When Ghost Hunt encounters languages without full AST adapter support (e.g., Go, Rust, Java, Kotlin, C#, PHP, Ruby):

1. **Inventory Files Honestly:** Report the exact file count, primary directories, and detected manifest files (`go.mod`, `Cargo.toml`, `pom.xml`, `composer.json`).
2. **Never Claim Unsupported Analysis:** Clearly declare the status as `partial` or `inventory-only`.
3. **Agent Native Tool Execution:** AI coding agents in interactive mode can use native grep, file reading, and test execution tools to investigate features in any language, following the same disciplined 11-step protocol.

