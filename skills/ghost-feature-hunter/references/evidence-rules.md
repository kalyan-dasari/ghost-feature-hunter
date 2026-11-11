# Evidence and status rules

Every reported checkpoint needs its expected behavior, observed behavior, status, timestamp, evidence reference (when available), reproducibility guidance, and confidence rationale.

PASS and FAIL records from the engine must contain at least one evidence item. Reports are unsigned and can be edited; a saved report by itself does not prove that a current run occurred. Discovery output is static and cannot establish runtime success.

- **PASS** means the adapter ran and every configured assertion matched.
- **FAIL** means an observed result contradicted an explicit assertion.
- **UNKNOWN** means the adapter could not reliably establish the result. Examples include missing credentials, blocked target, timeouts, unavailable optional dependencies, invalid observations, or missing evidence.

Do not infer a pass from a 2xx response if the journey asked about persistence or ownership. Add a separate database or identity assertion. Do not infer a failure from a missing service, missing runtime, or absent evidence. Report these as UNKNOWN and explain the missing prerequisite.

Evidence is an observation, not a causal explanation. A failing HTTP status proves the response differed from the journey expectation; it does not, by itself, prove which source function caused the failure. Corroborate causes with code, logs, or further checks and mark unverified explanations as hypotheses.

Reports redact common credentials and email addresses, but redaction is not complete. Do not add raw tokens, passwords, payment data, or unnecessary personal information to journeys. Review report contents before sharing.
