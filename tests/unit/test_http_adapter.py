import json
import httpx
import pytest

from ghost_hunter.adapters.base import AdapterContext
from ghost_hunter.adapters.http import HTTPAdapter
from ghost_hunter.config import HunterConfig
from ghost_hunter.models import Journey


@pytest.fixture
def mock_api():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"order": {"status": "created", "email": "shopper@example.com", "api_token": "access-secret"}},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(201)

    return "https://api.example.test", httpx.MockTransport(handler)


def journey_for(settings):
    return Journey(
        feature="orders",
        steps=[
            {
                "id": "order-read",
                "checkpoint": "Order response is observable",
                "adapter": "http",
                "expected_behavior": "Order status is created",
                "settings": settings,
            }
        ],
    )


def test_http_api_passes_explicit_status_and_json_assertions(tmp_path, mock_api):
    api_server, transport = mock_api
    journey = journey_for(
        {"method": "GET", "url": "/orders/1", "checks": {"status_code": 200, "json_equals": {"order.status": "created"}}}
    )
    context = AdapterContext(tmp_path, HunterConfig(base_url=api_server))
    result = HTTPAdapter(transport).verify(context, journey, journey.steps[0])
    assert result.status == "PASS", result.actual_observation
    assert result.evidence[0].details["status_code"] == 200
    assert "shopper@example.com" not in str(result.model_dump())
    assert "access-secret" not in str(result.model_dump())


def test_http_api_fails_only_when_an_explicit_assertion_mismatches(tmp_path, mock_api):
    api_server, transport = mock_api
    journey = journey_for(
        {"method": "GET", "url": "/orders/1", "checks": {"status_code": 200, "json_equals": {"order.status": "paid"}}}
    )
    result = HTTPAdapter(transport).verify(AdapterContext(tmp_path, HunterConfig(base_url=api_server)), journey, journey.steps[0])
    assert result.status == "FAIL", result.actual_observation


def test_http_write_is_unknown_without_both_approvals(tmp_path, mock_api):
    api_server, transport = mock_api
    journey = journey_for({"method": "POST", "url": "/orders", "checks": {"status_code": 201}})
    result = HTTPAdapter(transport).verify(AdapterContext(tmp_path, HunterConfig(base_url=api_server)), journey, journey.steps[0])
    assert result.status == "UNKNOWN"
    assert "blocked" in result.actual_observation


def test_http_host_outside_allowlist_is_blocked(tmp_path):
    journey = journey_for({"url": "https://example.invalid/health", "checks": {"status_code": 200}})
    result = HTTPAdapter().verify(AdapterContext(tmp_path, HunterConfig()), journey, journey.steps[0])
    assert result.status == "UNKNOWN"


def test_http_rejects_unknown_assertions_before_sending_request(tmp_path):
    requested = []
    transport = httpx.MockTransport(lambda request: requested.append(request) or httpx.Response(200))
    journey = journey_for({"url": "/health", "checks": {"body_is_valid": True}})
    context = AdapterContext(tmp_path, HunterConfig(base_url="https://api.example.test"))
    result = HTTPAdapter(transport).verify(context, journey, journey.steps[0])
    assert result.status == "UNKNOWN"
    assert "Unsupported HTTP assertion" in result.actual_observation
    assert requested == []
