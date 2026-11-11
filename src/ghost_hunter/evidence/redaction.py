"""Best-effort redaction for report-safe evidence."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie)"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_SENSITIVE_KEY = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie)")


def redact_text(value: str, limit: int = 1000) -> str:
    safe = _BEARER.sub("Bearer [REDACTED]", value)
    safe = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", safe)
    safe = _EMAIL.sub("[REDACTED_EMAIL]", safe)
    return safe[:limit]


def redact_value(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value[:100]]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value))


def safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return "[INVALID_URL]"
