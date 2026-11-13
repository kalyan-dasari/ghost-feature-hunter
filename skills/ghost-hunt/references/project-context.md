# Project Context Detection & Scope Locking

Before investigating any feature or auditing any codebase, Ghost Hunt must establish the **exact project boundaries** and lock the target scope.

---

## 1. Project Detection Protocol

When invoked, the agent inspects the environment using native tools:

1. **Current Working Directory & Workspace:** Identify the path where the coding agent was launched.
2. **Git Root Detection:** Locate `.git` directory in current or parent folders to establish repository bounds.
3. **Project Manifests:** Read `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, or build files to determine project name and ecosystem.
4. **Primary Languages & Frameworks:** Detect extensions (`.py`, `.ts`, `.js`, `.go`, `.rs`, `.html`) and framework dependencies (Flask, FastAPI, Django, Next.js, Express, React).
5. **Language Detection vs Analysis Support:** Distinguish between detected languages and implemented analysis capabilities. *(See [references/language-support.md](language-support.md))*
6. **Directory Classification:**
   - **Primary Application Source:** `src/`, `lib/`, `app/`, `skills/`, `integrations/`, root modules.
   - **Test Suites:** `tests/`, `test/`, `spec/`, `__tests__/`.
   - **Documentation:** `docs/`, `*.md`.
   - **Examples, Fixtures & Benchmarks:** `examples/`, `fixtures/`, `benchmarks/`, `demos/`, `samples/`.
   - **Ignored / Vendor:** `node_modules/`, `.git/`, `.venv/`, `dist/`, `build/`.

---

## 2. Distinguishing Product Source from Examples

> [!IMPORTANT]
> **The Scope Isolation Rule:**
> Never automatically select an example, demo, or benchmark directory as the primary target of an investigation.

When auditing Ghost Hunt itself:
- **Primary Product:** `src/` (Python engine), `skills/` (Agent Skill), `tests/`, `docs/`, `integrations/`.
- **Supporting Example / Benchmark:** `examples/broken-flask-shop/` (a deliberately broken test application used only for benchmarks).
- **Rule:** When the user runs `/ghost-hunt investigate` in the `ghost-feature-hunter` repository, the target is `ghost-feature-hunter`, NOT `broken-flask-shop`.

For any repository:
- Classify `examples/`, `fixtures/`, and `benchmarks/` separately.
- Only investigate an example application if the user **explicitly** names it (e.g. `/ghost-hunt investigate checkout in examples/broken-flask-shop`).

---

## 3. Handling Invocations Consistently

| Invocation | Action |
|---|---|
| `/ghost-hunt discover` | Run static architecture and boundary discovery without mutations. |
| `/ghost-hunt investigate <feature>` | Investigate the named feature in the primary target application. |
| `/ghost-hunt audit` | Perform whole-repository architecture, ghost feature, and connection audit. |
| `/ghost-hunt verify <feature>` | Re-verify approved code fixes and run regression checks. |
| `/ghost-hunt investigate` (bare) | **Do not guess a feature or pick an example app.** Display detected project context, summarize primary structure, and ask the user which feature they want to investigate or offer whole-repo audit. |

---

## 4. Project Context Summary Block

Every Ghost Hunt audit report must begin with this standardized block:

```markdown
### Project Context Summary
- **Project Name:** `<project_name>`
- **Project Root:** `<path_to_project_root>`
- **Git Repository Root:** `<git_root_or_none>`
- **Selected Application Root:** `<app_root>`
- **Framework & Languages:** `<frameworks_and_languages>`
- **Investigation Mode:** `<discover | investigate | audit | verify>`
- **Included Directories:** `<included_dirs>`
- **Excluded Directories:** `<excluded_dirs (e.g. examples, vendor, tests)>`
- **Available Capabilities:** `<native_tools_available (file, shell, curl, browser)>`
- **Limitations:** `<unsupported_runtimes_or_mocked_services>`
```
