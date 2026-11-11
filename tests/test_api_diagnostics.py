import socket

import pytest
import requests

from tradingagents.api_diagnostics import (
    APIFailure,
    classify_api_failure,
    format_api_failure,
    probe_endpoint,
)


@pytest.mark.parametrize(
    ("error", "category", "retryable"),
    [
        (requests.Timeout("synthetic token"), "timeout", True),
        (requests.ConnectionError("synthetic endpoint"), "connection", True),
        (socket.gaierror("synthetic host"), "dns", True),
        (RuntimeError("synthetic private response"), "unknown", False),
    ],
)
def test_transport_failures_are_classified_without_echoing_exception(error, category, retryable):
    failure = classify_api_failure(error)

    assert failure == APIFailure(category, retryable)
    assert "synthetic" not in format_api_failure(error)


@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (401, "authentication", False),
        (403, "permission", False),
        (402, "quota", False),
        (429, "rate_limit", False),
        (503, "provider_server", True),
    ],
)
def test_http_status_errors_are_classified_without_response_text(status, category, retryable):
    response = requests.Response()
    response.status_code = status
    response._content = b"synthetic private response"
    error = requests.HTTPError("synthetic private response")
    error.response = response

    failure = classify_api_failure(error)

    assert failure == APIFailure(category, retryable)
    assert f"HTTP {status}" in format_api_failure(error)
    assert "synthetic" not in format_api_failure(error)


@pytest.mark.parametrize(
    ("name", "category", "retryable"),
    [
        ("AlphaVantageNotConfiguredError", "configuration", False),
        ("AuthenticationError", "authentication", False),
        ("PermissionDenied", "permission", False),
        ("RateLimitError", "rate_limit", False),
        ("InsufficientQuotaError", "quota", False),
        ("InternalServerError", "provider_server", True),
    ],
)
def test_provider_exception_types_are_classified_without_inspecting_messages(name, category, retryable):
    error = type(name, (Exception,), {})("synthetic private response")

    failure = classify_api_failure(error)

    assert failure == APIFailure(category, retryable)
    assert "synthetic" not in format_api_failure(error)


def test_probe_removes_credentials_and_query_and_does_not_follow_redirects(monkeypatch):
    seen = {}

    class FakeSession:
        trust_env = True

        def head(self, url, **kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return object()

        def close(self):
            seen["closed"] = True
            seen["auth"] = self.auth

    monkeypatch.setattr("tradingagents.api_diagnostics.requests.Session", FakeSession)

    result = probe_endpoint(
        "https://synthetic-user:synthetic-secret@example.test:8443/v1?token=synthetic-token"
    )

    assert result.reachable is True
    assert seen["url"] == "https://example.test:8443/"
    assert seen["kwargs"] == {"timeout": 3.0, "allow_redirects": False}
    assert seen["closed"] is True
    assert seen["auth"].__class__.__name__ == "_NoNetrcAuth"
