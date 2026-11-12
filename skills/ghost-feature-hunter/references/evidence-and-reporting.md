# Evidence Analysis & Reporting (Workflows 13 & 14)

This guide covers **Workflow 13 (Evidence Analysis)** and **Workflow 14 (Report Generation)**.

---

## Workflow 13: Evidence Analysis

Ghost Feature Hunter enforces strict three-status logic backed by verifiable evidence.

### The Three-Status Truth Table:

| Status | Exact Definition | Permissible Inferences |
|---|---|---|
| **`PASS`** | The adapter ran and every configured assertion matched the observation. | Proves **only** the executed assertion. Does not prove coverage beyond that check. |
| **`FAIL`** | An observation directly contradicted an explicit expected behavior. | Proves the feature journey broke at this checkpoint. |
| **`UNKNOWN`** | Prerequisite, permission, runtime, network target, or evidence was unavailable. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

### Evidence Sanitization Rules:
- **Redaction:** Bearer tokens, passwords, secrets, API keys, and email addresses are automatically redacted from text and JSON evidence.
- **URL Sanitization:** Query parameters and basic auth credentials are automatically stripped from evidence reference URLs.
- **Unsigned Reports:** Reports are unsigned JSON/Markdown files. A pre-existing report alone does not prove a run occurred. Claim a current PASS or FAIL only after executing the CLI during the current investigation.

---

## Workflow 14: Report Generation & Summary

The CLI writes two reports into the configured `report_dir` (`ghost-reports/` by default):
- `ghost-report.json`: Machine-readable, schema-validated report conforming to `schemas/report.schema.json`.
- `ghost-report.md`: Human-readable Markdown summary with tables, evidence details, and limitations.

### Recommended Compact Summary Format for Chat:

```markdown
### Feature Verification: <feature_name>
- **Results:** <PASS_count> PASS, <FAIL_count> FAIL, <UNKNOWN_count> UNKNOWN
- **Run ID:** `<run_id>`
- **Failures Identified:**
  - `<checkpoint_id>`: Expected `<expected>`, observed `<actual>`. Evidence: `<reference>`
- **Unverified (UNKNOWN):**
  - `<checkpoint_id>`: Missing prerequisite or blocked target: `<reason>`
- **Next Steps:**
  - <Targeted recommendation or regression verification>
```
