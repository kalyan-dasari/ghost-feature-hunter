import pytest
from ghost_hunter.evidence.redaction import redact_text, redact_value, safe_url


def test_redact_bearer_token():
    text = "Authorization: Bearer secret-jwt-token-value-12345"
    redacted = redact_text(text)
    assert "secret-jwt-token" not in redacted
    assert "Bearer [REDACTED]" in redacted


def test_redact_email_address():
    text = "User email is shopper@example.com in confirmation"
    redacted = redact_text(text)
    assert "shopper@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_redact_key_value_assignments():
    text = "password = my-super-secret-password; token: abc-xyz-123"
    redacted = redact_text(text)
    assert "my-super-secret-password" not in redacted
    assert "abc-xyz-123" not in redacted
    assert "password=[REDACTED]" in redacted or "password = [REDACTED]" in redacted or "password =[REDACTED]" in redacted


def test_redact_value_with_nested_structures():
    data = {
        "user": {
            "name": "Alice",
            "api_key": "live_key_9999",
            "metadata": ["safe_tag", "secret_pass_1234"],
        },
        "password": "secret_field",
    }
    redacted = redact_value(data)
    assert redacted["user"]["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["user"]["name"] == "Alice"


def test_safe_url_strips_credentials_and_query():
    raw = "https://user:pass@api.example.test:8443/orders?token=secret#frag"
    cleaned = safe_url(raw)
    assert "user" not in cleaned
    assert "pass" not in cleaned
    assert "secret" not in cleaned
    assert "frag" not in cleaned
    assert cleaned == "https://api.example.test:8443/orders"


def test_safe_url_handles_invalid_url():
    assert safe_url("http://[invalid-ipv6") == "[INVALID_URL]"

