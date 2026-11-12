# Security Policy

Ghost Hunt is an open-source Agent Skill (v0.3.0) for AI coding agents, accompanied by an optional Python verification CLI (`ghost-feature-hunter` v0.2.0).

Always verify features against isolated test environments and synthetic data. Review [docs/safety.md](docs/safety.md) before running checks that access services, query databases, or execute browser automation.

## Supported Versions

| Component | Version | Supported |
|---|---|---|
| Agent Skill (`ghost-hunt`) | 0.3.0 | :white_check_mark: |
| Python CLI (`ghost-feature-hunter`) | 0.2.0 | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities privately using GitHub's **[Private Vulnerability Reporting](https://github.com/kalyan-dasari/ghost-feature-hunter/security/advisories/new)** feature on this repository.

If private vulnerability reporting is unavailable, contact a repository maintainer privately before public disclosure. Do not open public issues containing suspected vulnerabilities, credentials, API keys, or personal data.

When reporting an issue, please include:
- Affected component (Agent Skill or Python CLI) and version.
- Concise impact description.
- Safe, minimal reproduction steps.
- Any suggested mitigation or patch.

Do not perform security testing against systems or data you do not own or have explicit permission to assess.
