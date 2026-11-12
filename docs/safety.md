# Security model

Ghost Feature Hunter inspects projects that may contain secrets, private data, or executable code. It is a developer tool, not a sandbox.

## Defaults

- Discovery reads source files and parses Python syntax trees. It never imports application modules or runs commands found in project files.
- HTTP checks default to GET and do not follow redirects. A non-read method runs only when `allow_writes` is `true` in `ghost-hunter.json` and the operator passes `--allow-writes`.
- Targets must match the configured `base_url` or an entry in `allowed_hosts`. Loopback targets are permitted when no base URL is configured.
- A project configured for `production` is blocked unless `production_approved` is true in config and `--approve-production` is passed. This is a guardrail, not a guarantee that a host is non-production.
- Database checks currently support only file-backed SQLite, require the database file to reside within the project root, and execute restricted SELECT queries guarded at the SQLite C-engine level via connection authorizer callbacks. Queries are limited to 1,000 returned rows. No migration, write, or destructive operation is offered.
- Browser checks require an explicit base URL, allow at most 25 actions per checkpoint, and block cross-origin requests. Mutating HTTP methods require both write approvals. Page scripts still execute and may have effects through read methods or unsupported browser channels; this is not a sandbox.
- HTTP responses are capped at 2 MB. Reports omit request headers and request bodies. Common credentials and email addresses are redacted from textual evidence.

## Limits

Redaction is best effort and cannot identify every secret or personal detail. Avoid pointing checks at production data, use synthetic accounts, and review reports before sharing. HTTP adapters can reach services on hosts explicitly configured by the user. Reports are unsigned and can be edited; review the evidence and journey, and do not treat a report file alone as proof that a run occurred. Use disposable, isolated environments for these checks.

No automated payment, external notification, database write, or application-source modification is offered by the v0.1 verification engine.

## Reporting vulnerabilities

Please report security issues privately to the repository maintainers before public disclosure. Do not include live credentials or personal data in issue reports. Maintainers should add a security contact address before publishing a release.
