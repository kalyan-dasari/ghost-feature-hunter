"""HTTP API verification with explicit target and write safeguards."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from ghost_hunter.adapters.base import AdapterContext, make_result, unknown_result
from ghost_hunter.evidence.redaction import redact_text, redact_value, safe_url
from ghost_hunter.models import EvidenceItem, Journey, JourneyStep, Status, utc_now

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
_MAX_RESPONSE_BYTES = 2_000_000
_ALLOWED_CHECKS = {"status_code", "json_equals", "json_exists", "text_contains"}


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    default_port = 443 if parts.scheme == "https" else 80
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or default_port


def _resolve_url(context: AdapterContext, raw_url: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None, "HTTP setting `url` must be a non-empty string."
    base = context.base_url
    candidate = urljoin(base.rstrip("/") + "/", raw_url) if base else raw_url
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return None, "The target URL must use HTTP(S), include a host, and contain no embedded credentials."
    allowed_hosts = {h.lower() for h in context.config.allowed_hosts}
    base_origin = _origin(base) if base else None
    same_base = base_origin == _origin(candidate) if base_origin else False
    loopback = parts.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    if not same_base and parts.hostname.lower() not in allowed_hosts and not (loopback and base is None):
        return None, "Target host is not the configured base URL or an explicitly allowed host."
    return candidate, None


def _json_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    if not path:
        return True, current
    for token in path.replace("[", ".").replace("]", "").split("."):
        if not token:
            continue
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False, None
    return True, current


class HTTPAdapter:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def verify(self, context: AdapterContext, journey: Journey, step: JourneyStep):
        start = time.monotonic()
        settings = step.settings
        method = str(settings.get("method", "GET")).upper()
        if method not in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}:
            return unknown_result(journey, step, f"Unsupported HTTP method: {method}", start)
        if method not in _READ_METHODS:
            if not (context.config.allow_writes and context.allow_writes):
                return unknown_result(
                    journey,
                    step,
                    "Write request blocked; set allow_writes in project config and pass --allow-writes.",
                    start,
                )
        if context.config.environment == "production" and not (
            context.config.production_approved and context.approve_production
        ):
            return unknown_result(
                journey,
                step,
                "Production target blocked; production approval is required in config and on the CLI.",
                start,
            )

        url, url_error = _resolve_url(context, settings.get("url"))
        if url_error or url is None:
            return unknown_result(journey, step, url_error or "Invalid URL.", start)

        checks = settings.get("checks", {"status_code": 200})
        if not isinstance(checks, dict) or not checks:
            return unknown_result(journey, step, "HTTP step has no explicit assertions.", start)
        unsupported = set(checks) - _ALLOWED_CHECKS
        if unsupported:
            names = ", ".join(sorted(map(str, unsupported)))
            return unknown_result(journey, step, f"Unsupported HTTP assertion(s): {names}.", start)
        expected_status = checks.get("status_code", 200)
        if not isinstance(expected_status, int) or isinstance(expected_status, bool):
            return unknown_result(journey, step, "checks.status_code must be an integer.", start)
        json_equals = checks.get("json_equals", {})
        json_exists = checks.get("json_exists", [])
        if not isinstance(json_equals, dict) or not isinstance(json_exists, list) or not all(
            isinstance(path, str) for path in json_exists
        ):
            return unknown_result(journey, step, "json_equals must be an object and json_exists must be a list of strings.", start)
        if "text_contains" in checks and (not isinstance(checks["text_contains"], str) or not checks["text_contains"]):
            return unknown_result(journey, step, "checks.text_contains must be a non-empty string.", start)
        if not ("status_code" in checks or json_equals or json_exists or "text_contains" in checks):
            return unknown_result(journey, step, "HTTP step has no supported assertions.", start)

        try:
            timeout = float(settings.get("timeout_seconds", context.config.timeout_seconds))
            if not 0 < timeout <= 120:
                raise ValueError("timeout must be between 0 and 120 seconds")
            headers = settings.get("headers", {})
            if not isinstance(headers, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
            ):
                raise ValueError("headers must be a string-to-string object")
            headers = dict(headers)
            header_env = settings.get("headers_env", {})
            if not isinstance(header_env, dict):
                raise ValueError("headers_env must be an object")
            for header, env_name in header_env.items():
                env_value = os.environ.get(str(env_name))
                if not env_value:
                    return unknown_result(
                        journey, step, f"Required request credential environment variable {env_name!r} is unavailable.", start
                    )
                headers[str(header)] = env_value
            with httpx.Client(timeout=timeout, follow_redirects=False, transport=self._transport) as client:
                with client.stream(
                    method,
                    url,
                    headers=headers,
                    params=settings.get("params"),
                    json=settings.get("json"),
                ) as raw_response:
                    body = bytearray()
                    for chunk in raw_response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > _MAX_RESPONSE_BYTES:
                            return unknown_result(
                                journey,
                                step,
                                "HTTP response exceeded the 2 MB evidence limit.",
                                start,
                            )
                    response = httpx.Response(
                        status_code=raw_response.status_code,
                        headers=raw_response.headers,
                        content=bytes(body),
                        request=raw_response.request,
                    )
        except (ValueError, TypeError) as exc:
            return unknown_result(journey, step, f"Invalid HTTP step settings: {redact_text(str(exc))}", start)
        except httpx.TimeoutException:
            return unknown_result(journey, step, "HTTP request timed out.", start)
        except httpx.RequestError as exc:
            return unknown_result(
                journey,
                step,
                f"HTTP request could not be completed ({type(exc).__name__}).",
                start,
            )

        outcomes: list[tuple[bool, str]] = []
        outcomes.append((response.status_code == expected_status, f"status_code={response.status_code} (expected {expected_status})"))

        parsed_json: Any = None
        json_required = "json_equals" in checks or "json_exists" in checks
        if json_required:
            try:
                parsed_json = response.json()
            except (ValueError, UnicodeDecodeError):
                return unknown_result(
                    journey, step, "Response was not valid JSON for a JSON assertion.", start
                )
        for path, expected in json_equals.items():
            exists, actual = _json_path(parsed_json, str(path))
            safe_actual = redact_value(actual, str(path).split(".")[-1].split("[")[0])
            outcomes.append((exists and actual == expected, f"JSON {path} observed {redact_text(repr(safe_actual), 200) if exists else 'missing'}"))
        for path in json_exists:
            exists, _ = _json_path(parsed_json, str(path))
            outcomes.append((exists, f"JSON path {path} {'exists' if exists else 'is missing'}"))
        if "text_contains" in checks:
            needle = checks["text_contains"]
            outcomes.append((needle in response.text, f"response text {'contains' if needle in response.text else 'does not contain'} the configured phrase"))

        passed = all(ok for ok, _ in outcomes)
        actual = "; ".join(message for _, message in outcomes)
        evidence = [
            EvidenceItem(
                reference=f"http:{method}:{safe_url(url)}",
                observed_at=utc_now(),
                summary="HTTP response and explicit assertions were observed.",
                details={
                    "method": method,
                    "url": safe_url(url),
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "assertions": [redact_text(message, 300) for _, message in outcomes],
                },
            )
        ]
        return make_result(
            journey,
            step,
            Status.PASS if passed else Status.FAIL,
            actual,
            "Every explicit HTTP assertion matched the observed response."
            if passed
            else "An explicit HTTP assertion contradicted the observed response.",
            evidence=evidence,
            start_time=start,
        )
