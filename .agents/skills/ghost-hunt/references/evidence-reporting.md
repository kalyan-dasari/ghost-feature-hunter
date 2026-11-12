# Evidence Standards, Sanitization & Reporting

Ghost Hunt enforces strict evidentiary standards. A feature is never claimed as working because it looks correct in source code; it must be proven with runtime observations.

---

## 1. The Three-Status Truth Table

Every checkpoint must evaluate to exactly one of three statuses:

| Status | Verification Definition | Rules & Interpretation |
|---|---|---|
| **`PASS`** | The check executed and every configured assertion matched the observation. | Proves **only** the executed assertion. Does not prove coverage beyond that check. |
| **`FAIL`** | An observation directly contradicted an explicit expected behavior. | Proves the feature broke at this specific checkpoint. |
| **`UNKNOWN`** | A prerequisite, permission, runtime, network target, or evidence was unavailable. | **Never relabel as PASS or FAIL.** Indicates an unverified check. |

### Core Evidence Principles:
1. **Zero Fabrication:** Never invent, simulate, or assume test results. If a check was not run, its status is `UNKNOWN`.
2. **Source Code != Runtime Proof:** Static analysis and syntax reading do not prove runtime functionality.
3. **Requirement Integrity:** Never invent business rules; expectations must be anchored to explicit sources.

---

## 2. Evidence Sanitization & Redaction

Evidence logs often capture sensitive data. Ghost Hunt enforces automatic redaction rules:

- **Auth Tokens:** Bearer tokens, Basic auth, API keys, and session cookies are replaced with `[REDACTED]`.
- **Passwords & Secrets:** Any field named `password`, `secret`, `api_key`, `token`, `private_key` has its value redacted.
- **Personal Data:** Email addresses in headers and payloads are masked.
- **Database Paths:** Physical file paths for SQLite databases are omitted from evidence items.
- **URL Query Parameters:** Query strings containing tokens or credentials are stripped.

---

## 3. Reporting Formats

### Format A: Native Chat Executive Summary
When delivering results directly in chat, use this compact, high-signal format:

```markdown
### Ghost Hunt Verification: <feature_name>
- **Outcome:** <P> PASS | <F> FAIL | <U> UNKNOWN
- **Target:** `<base_url>` (`<environment>`)
- **Execution Mode:** Native Agent Tools (or Optional CLI Engine)

#### Verified Checkpoints:
- [PASS] `<checkpoint_id>`: <expected_behavior>
  *Observation:* <actual_observation> (Evidence: `<reference>`)

#### Confirmed Defects (FAIL):
- [FAIL] `<checkpoint_id>`: Expected `<expected>`, observed `<actual>`.
  *Root Cause:* `<file_path>:<line>` — <brief explanation>
  *Recommended Fix:* <proposed solution>

#### Unverified / Blocked (UNKNOWN):
- [UNKNOWN] `<checkpoint_id>`: <reason for lack of evidence>

#### Next Steps:
- <Actionable guidance or authorization request>
```

### Format B: Full Markdown Audit Report
For long-form artifacts or saved reports, use [templates/report-template.md](../templates/report-template.md).

