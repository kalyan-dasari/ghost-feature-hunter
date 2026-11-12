"""Read-only, bounded SQLite observations using Python's standard library."""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from ghost_hunter.adapters.base import AdapterContext, make_result, unknown_result
from ghost_hunter.models import EvidenceItem, Journey, JourneyStep, Status, utc_now

_DANGEROUS_SQL_START = re.compile(
    r"(?is)^\s*(insert|update|delete|replace|create|drop|alter|attach|detach|pragma|vacuum|reindex|analyze)\b"
)
_ALLOWED_CHECKS = {"row_count_equals", "row_count_at_least", "first_row_equals"}


def _sqlite_read_only_authorizer(action_code: int, arg1: str | None, arg2: str | None, db_name: str | None, trigger_name: str | None) -> int:
    """Enforce read-only execution at the SQLite engine level."""
    allowed_actions = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    }
    if action_code == sqlite3.SQLITE_FUNCTION:
        func = (arg2 or "").lower()
        if func in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return sqlite3.SQLITE_OK if action_code in allowed_actions else sqlite3.SQLITE_DENY


def _database_path(database_url: str, project_root: Path, environment: str = "development") -> Path:
    parsed = urlsplit(database_url)
    if (
        parsed.scheme not in {"sqlite", "sqlite+pysqlite"}
        or parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only file-backed SQLite URLs without extra URI options are supported.")
    raw_path = unquote(parsed.path)
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    elif raw_path.startswith("/") and not Path(raw_path).is_absolute():
        raw_path = raw_path[1:]
    if not raw_path or raw_path == ":memory:":
        raise ValueError("Only file-backed SQLite databases are supported.")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    resolved = path.resolve()
    root = project_root.resolve()

    allowed_roots = [root]
    if environment in {"test", "development"}:
        try:
            allowed_roots.append(Path(tempfile.gettempdir()).resolve())
        except OSError:
            pass

    in_allowed = any(resolved == r or r in resolved.parents for r in allowed_roots)
    if not in_allowed:
        raise ValueError(f"Database file path {resolved} is outside the allowed project directories.")

    return resolved


class DatabaseAdapter:
    def verify(self, context: AdapterContext, journey: Journey, step: JourneyStep):
        start = time.monotonic()
        if context.config.environment == "production" and not (
            context.config.production_approved and context.approve_production
        ):
            return unknown_result(
                journey,
                step,
                "Production database observation is blocked without explicit config and CLI approval.",
                start,
            )
        settings = step.settings
        query = settings.get("query")
        checks = settings.get("checks", {})
        if not isinstance(query, str) or not query.strip():
            return unknown_result(journey, step, "Database step must include a read-only SELECT query.", start)
        if (
            not re.match(r"(?is)^\s*select\b", query)
            or ";" in query
            or _DANGEROUS_SQL_START.match(query)
        ):
            return unknown_result(journey, step, "Database query rejected by the read-only SQL guard.", start)
        if not isinstance(checks, dict) or not checks:
            return unknown_result(journey, step, "Database step has no explicit assertions.", start)
        unsupported = set(checks) - _ALLOWED_CHECKS
        if unsupported:
            names = ", ".join(sorted(map(str, unsupported)))
            return unknown_result(journey, step, f"Unsupported database assertion(s): {names}.", start)
        env_name = settings.get("database_url_env") or context.config.database_url_env
        if not isinstance(env_name, str) or not env_name:
            return unknown_result(journey, step, "Set database_url_env in config or this journey step.", start)
        database_url = os.environ.get(env_name)
        if not database_url:
            return unknown_result(journey, step, f"Database environment variable {env_name!r} is unavailable.", start)

        try:
            db_path = _database_path(database_url, context.project_root, context.config.environment)
            if not db_path.is_file():
                return unknown_result(journey, step, "Configured SQLite database file does not exist.", start)
            sqlite_uri = f"file:{quote(db_path.as_posix(), safe='/:')}?mode=ro"
            connection = sqlite3.connect(
                sqlite_uri,
                uri=True,
                timeout=context.config.timeout_seconds,
            )
            connection.row_factory = sqlite3.Row
            connection.set_authorizer(_sqlite_read_only_authorizer)
            deadline = time.monotonic() + context.config.timeout_seconds
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            try:
                parameters = settings.get("parameters", {})
                if not isinstance(parameters, (dict, list, tuple)):
                    return unknown_result(journey, step, "Database parameters must be an object or array.", start)
                cursor = connection.execute(query, parameters)
                rows = cursor.fetchmany(1001)
            finally:
                connection.close()
        except ValueError as exc:
            return unknown_result(journey, step, str(exc), start)
        except (OSError, sqlite3.Error, TypeError) as exc:
            return unknown_result(
                journey,
                step,
                f"Database observation could not be completed ({type(exc).__name__}).",
                start,
            )
        if len(rows) > 1000:
            return unknown_result(journey, step, "Database query returned more than 1,000 rows; narrow the observation.", start)

        outcomes: list[tuple[bool, str]] = []
        if "row_count_equals" in checks:
            expected = checks["row_count_equals"]
            if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
                return unknown_result(journey, step, "checks.row_count_equals must be a non-negative integer.", start)
            outcomes.append((len(rows) == expected, f"row count={len(rows)} (expected {expected})"))
        if "row_count_at_least" in checks:
            expected = checks["row_count_at_least"]
            if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
                return unknown_result(journey, step, "checks.row_count_at_least must be a non-negative integer.", start)
            outcomes.append((len(rows) >= expected, f"row count={len(rows)} (expected at least {expected})"))
        column_checks = checks.get("first_row_equals", {})
        if not isinstance(column_checks, dict) or not column_checks:
            if "first_row_equals" in checks:
                return unknown_result(journey, step, "checks.first_row_equals must be a non-empty object.", start)
        else:
            first = dict(rows[0]) if rows else {}
            for column, expected in column_checks.items():
                outcomes.append((first.get(column) == expected, f"first row column {column} assertion evaluated"))
        if not outcomes:
            return unknown_result(journey, step, "No supported database assertion was provided.", start)

        passed = all(ok for ok, _ in outcomes)
        evidence = [
            EvidenceItem(
                reference="database:sqlite:read-only-query",
                observed_at=utc_now(),
                summary="A SELECT query ran against a read-only SQLite connection.",
                details={
                    "row_count": len(rows),
                    "assertions": [message for _, message in outcomes],
                    "database_path_omitted": True,
                },
            )
        ]
        return make_result(
            journey,
            step,
            Status.PASS if passed else Status.FAIL,
            "; ".join(message for _, message in outcomes),
            "The configured read-only query produced observations that were evaluated against explicit assertions."
            if passed
            else "The query result contradicted an explicit database assertion.",
            evidence=evidence,
            start_time=start,
        )
