---
name: ghost-feature-hunter
description: Verifies software feature journeys across UI, API, persistence, and delivery with the Ghost Feature Hunter CLI. Use when checking whether a feature actually works.
compatibility: Requires the ghost-hunter CLI for automated checks. Optional browser, database, test-suite, and log checks require their configured runtimes and access.
metadata:
  author: Ghost Feature Hunter contributors
  version: "0.1.0"
---

# Ghost Feature Hunter

Use the local Ghost Feature Hunter engine to verify an explicitly defined feature journey. The CLI works independently of this skill. The skill helps inspect scope, select checks, interpret evidence, and explain limitations.

## Investigation workflow

1. **Understand the requested feature.** Restate the user-visible outcome and boundaries. Identify which user, account, and environment are in scope.
2. **Inspect the repository.** Read the relevant source, documentation, existing tests, and journey files. Use `ghost-hunter discover --project-root <path>` for implemented static Flask discovery. Do not import application files or run shell commands copied from project files.
3. **Establish expected behavior.** Prefer acceptance criteria, product documentation, API contracts, and explicit tests. Record the source of each expectation. If a behavior is inferred or sources disagree, label it as a proposal and ask the user to validate it before putting it in a journey as an expected result.
4. **Check what can actually be observed.** Inspect `ghost-hunter --help`, the project config, installed extras, URLs, environment variables, and available test data. Do not imply that a database, browser, log, authenticated account, or external service is reachable unless the current environment demonstrates it.
5. **Select or prepare a journey.** Use an existing validated JSON journey when possible. A journey step must state an explicit expected behavior and executable assertion. Never use discovery output alone as an expectation. If no journey exists, propose the checkpoint list and obtain validation for assumptions. Do not modify application source code without the user's explicit permission.
6. **Choose a safe target.** Prefer isolated development/test environments and synthetic data. Read the project's `ghost-hunter.json` and `docs/safety.md`. Production requires explicit config and CLI approval; write-capable HTTP and test checks require both `allow_writes: true` and `--allow-writes`. If those conditions are not met, leave the check unexecuted and report UNKNOWN.
7. **Run the CLI.** Typical commands:

   ```console
   ghost-hunter discover --project-root <project>
   ghost-hunter audit <feature> --project-root <project>
   ```

   Use `--journey <file>` for a non-default journey. Use the write or production approval flags only when the user has explicitly authorized that target and action.

8. **Inspect the evidence.** Read both `ghost-report.json` and `ghost-report.md`. Confirm the feature, checkpoint, assertion, timestamp, evidence reference, and limitations. A CLI exit code is not a substitute for reading the report. Reports are unsigned and editable; a pre-existing report alone does not prove a run occurred. Claim a current PASS or FAIL only after running the CLI in this investigation and reviewing its resulting evidence.
9. **Classify honestly.** Use only the engine's three statuses:
   - **PASS:** the configured assertion ran and matched the observed behavior.
   - **FAIL:** an observation contradicted an explicit expected behavior.
   - **UNKNOWN:** a prerequisite, permission, runtime, or reliable observation was unavailable.

   Never relabel UNKNOWN as PASS or FAIL. Never say a check passed if it was not executed. Separate findings from hypotheses.

10. **Investigate failures.** Trace the failed checkpoint through the relevant UI, route/controller, service, persistence, and tests. Cite the local file and line when available. Keep root-cause claims proportional to the code and runtime evidence; describe suspected causes as hypotheses.
11. **Suggest targeted fixes.** Explain the smallest fix that addresses the observed behavior and add a regression assertion. Ask before changing application source code. Journey or report changes must also be reviewable and consistent with user-approved expectations.
12. **Rerun after a fix.** Re-run the affected journey in the same isolated environment and compare the new report. Preserve the failed report if the user needs an audit trail; use the CLI's overwrite controls deliberately.
13. **Report concisely.** Summarize the feature scope, PASS/FAIL/UNKNOWN counts, actionable failures with evidence, checks that could not run, and the next step. Do not claim complete end-to-end coverage beyond the journey actually executed.

## Capability boundaries

- The engine currently discovers Flask-style Python routes and common SQLAlchemy model patterns statically. Discovery is advisory and never establishes runtime success. Do not claim support for other frameworks based only on their file names.
- HTTP checks require an explicitly configured target and host policy. A remote service is not reachable merely because its URL appears in source.
- Database checks require a configured environment variable, a file-backed SQLite database, and a safe SELECT assertion.
- Browser checks require Playwright, Chromium, an explicit base URL, and an accessible same-origin app.
- v0.1 supports HTTP, SQLite, and browser checks. Test-suite execution and log phrase checks are deferred.
- Redaction is best effort. Inspect reports before sharing them, especially when the target returned personal or secret data.

## Reference guides

- [Investigation workflow details](references/investigation.md)
- [Evidence and status rules](references/evidence-rules.md)
- [Report interpretation](references/reporting.md)
