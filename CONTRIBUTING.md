# Contributing

Contributions are welcome. Keep behavior evidence-based, defaults safe, and unsupported capabilities clearly identified.

## Development setup

```console
python -m venv .venv
python -m pip install -e ".[dev,database,demo,browser]"
python -m playwright install chromium
python -m pytest
```

The package supports Python 3.11+. Tests should be deterministic, use temporary project/data directories, and avoid production services or real credentials.

## Pull requests

- Describe the user problem and the observable behavior added or changed.
- Add or update tests for models, adapter behavior, security boundaries, and reports as applicable.
- Keep adapters behind the common result model and preserve PASS/FAIL/UNKNOWN semantics.
- Never turn inferred behavior into an assertion without documenting its source.
- Never run commands discovered from project files.
- Document optional dependencies, platform constraints, and unverified behavior.
- Review generated evidence for accidental secrets or personal data.

## Style

Use type hints, small functions, explicit error handling, and standard library facilities when they are sufficient. Avoid broad framework claims and fabricated benchmark results.
