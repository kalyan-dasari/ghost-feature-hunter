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
| **Python / Django** | Yes | Route regex, model, and view structure analysis | Dynamic URL reversing and template-rendered URLs are approximated. |
| **JS/TS / Express** | Yes | Route extraction, middleware, client calls, and symbols | Dynamic router middleware chains and runtime mount points require inspection. |
| **JS/TS / Next.js** | Yes | App Router / Pages Router routes, pages, and components | Dynamic catch-all routes (`[...slug]`) are normalized. |
| **JS/TS / React** | Yes | Component inventory, UI buttons, handlers, form inputs | Higher-order components and complex context state updates require execution. |
| **Other (Go, Rust, Java, etc.)**| Yes | File inventory and package manifest inspection only | Deep AST route and caller analysis are not currently implemented. |

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

### Python (Full AST Support)
- **Supported Frameworks:** Flask, FastAPI, Django.
- **AST Parsing:** Uses Python's standard library `ast` module (safe; application code is never imported or executed).
- **Route Normalization:** Standardizes `<int:id>`, `<id>`, and `{id}` to `{id}` for cross-boundary matching.
- **Model Discovery:** Detects SQLAlchemy declarative models, Django models, and Pydantic schemas.
- **Abstract Method Handling:** Checks for `@abstractmethod`, `abc.ABC`, and `typing.Protocol` to prevent false defect reports for intentional interface stubs.

### JavaScript & TypeScript (Structural Parser Support)
- **Supported Frameworks:** Express, Next.js (App & Pages Routers), React, Node.js.
- **Structural Analysis:** Scans route declarations, React component trees, UI actions, and client requests.
- **Next.js Conventions:**
  - App Router: Maps `app/**/route.{ts,js}` and HTTP method exports (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`).
  - Pages Router: Maps `pages/api/**/*.ts` default exports.
  - UI Pages: Maps `app/**/page.tsx` and `pages/**/*.tsx` as navigation destinations.
- **React UI Connections:** Inspects `<button onClick={...}>`, `<Link href="...">`, and `<form>`.

---

## 4. Unsupported & Partially Analyzed Languages

When Ghost Hunt encounters languages without full AST adapter support (e.g., Go, Rust, Java, Kotlin, C#, PHP, Ruby):

1. **Inventory Files Honestly:** Report the exact file count, primary directories, and detected manifest files (`go.mod`, `Cargo.toml`, `pom.xml`, `composer.json`).
2. **Never Claim Unsupported Analysis:** Clearly declare the status as `partial` or `inventory-only`.
3. **Agent Native Tool Execution:** AI coding agents in interactive mode can use native grep, file reading, and test execution tools to investigate features in any language, following the same disciplined 11-step protocol.

