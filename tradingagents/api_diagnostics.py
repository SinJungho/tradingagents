"""Safe API failure classification and no-auth endpoint probes."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import requests
from requests.auth import AuthBase

FailureCategory = Literal[
    "dns",
    "connection",
    "timeout",
    "tls",
    "authentication",
    "permission",
    "rate_limit",
    "quota",
    "configuration",
    "provider_server",
    "provider_response",
    "unknown",
]


@dataclass(frozen=True)
class APIFailure:
    category: FailureCategory
    retryable: bool


@dataclass(frozen=True)
class EndpointProbe:
    reachable: bool
    failure: APIFailure | None = None


class _NoNetrcAuth(AuthBase):
    """Keep normal proxy/CA settings while refusing ambient .netrc credentials."""

    def __call__(self, request):
        request.headers.pop("Authorization", None)
        return request


_FAILURE_LABELS: dict[FailureCategory, str] = {
    "dns": "DNS 오류",
    "connection": "연결 오류",
    "timeout": "시간 초과",
    "tls": "TLS 오류",
    "authentication": "인증 거부",
    "permission": "권한 거부",
    "rate_limit": "요청 제한",
    "quota": "계정 한도 초과",
    "configuration": "인증 설정 누락",
    "provider_server": "제공자 서버 오류",
    "provider_response": "제공자 응답 오류",
    "unknown": "분류되지 않은 API 오류",
}


def classify_http_status(status: int) -> APIFailure:
    if status == 401:
        return APIFailure("authentication", False)
    if status == 403:
        return APIFailure("permission", False)
    if status in {402, 507}:
        return APIFailure("quota", False)
    if status == 429:
        return APIFailure("rate_limit", False)
    if status == 408:
        return APIFailure("timeout", True)
    if 500 <= status < 600:
        return APIFailure("provider_server", True)
    return APIFailure("provider_response", False)


def _status_from_error(error: BaseException) -> int | None:
    response = getattr(error, "response", None)
    response_status = None
    if isinstance(response, dict):
        metadata = response.get("ResponseMetadata")
        if isinstance(metadata, dict):
            response_status = metadata.get("HTTPStatusCode")
    for value in (
        getattr(error, "status", None),
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(response, "status_code", None),
        response_status,
    ):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _error_chain(error: BaseException):
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for nested in (
            current.__cause__,
            current.__context__,
            getattr(current, "reason", None),
            *current.args,
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)


def classify_api_failure(error: BaseException) -> APIFailure:
    """Classify an exception without reading its message or response body."""
    known_failure = getattr(error, "failure", None)
    if isinstance(known_failure, APIFailure):
        return known_failure
    category = getattr(error, "category", None)
    retryable = getattr(error, "retryable", None)
    if category in _FAILURE_LABELS and isinstance(retryable, bool):
        return APIFailure(category, retryable)
    status = _status_from_error(error)
    if status is not None:
        return classify_http_status(status)

    chain = tuple(_error_chain(error))
    names = {type(item).__name__.lower() for item in chain}
    if any("notconfigured" in name or "missingcredential" in name for name in names):
        return APIFailure("configuration", False)
    if any("authenticationerror" in name or "unauthenticated" in name for name in names):
        return APIFailure("authentication", False)
    if any("permissiondenied" in name or "forbidden" in name for name in names):
        return APIFailure("permission", False)
    if any("ratelimit" in name or "toomanyrequests" in name for name in names):
        return APIFailure("rate_limit", False)
    if any("quota" in name or "insufficientcredits" in name for name in names):
        return APIFailure("quota", False)
    if any("internalserver" in name or "serviceunavailable" in name for name in names):
        return APIFailure("provider_server", True)
    if any(isinstance(item, socket.gaierror) for item in chain) or any(
        "dns" in name or "nameresolution" in name or "gaierror" in name
        for name in names
    ):
        return APIFailure("dns", True)
    if any(isinstance(item, (ssl.SSLError, requests.exceptions.SSLError)) for item in chain) or any(
        "sslerror" in name or "tls" in name or "certificateverifyfailed" in name
        for name in names
    ):
        return APIFailure("tls", False)
    if any(
        isinstance(item, (TimeoutError, requests.Timeout))
        or "timeout" in type(item).__name__.lower()
        or "deadlineexceeded" in type(item).__name__.lower()
        for item in chain
    ):
        return APIFailure("timeout", True)
    if any(
        isinstance(item, (requests.ConnectionError, ConnectionError))
        or "connectionerror" in type(item).__name__.lower()
        or "connecterror" in type(item).__name__.lower()
        for item in chain
    ):
        return APIFailure("connection", True)
    return APIFailure("unknown", False)


def format_api_failure(error: BaseException | APIFailure) -> str:
    """Return a user-facing category and retry hint with no exception details."""
    failure = error if isinstance(error, APIFailure) else classify_api_failure(error)
    if failure.category not in _FAILURE_LABELS:
        failure = APIFailure("unknown", False)
    retry = "예" if failure.retryable else "아니요"
    status = _status_from_error(error) if isinstance(error, BaseException) else None
    status_label = f"HTTP {status}: " if status is not None else ""
    # The class name alone is a safe clue for unclassified failures; never the message.
    type_label = (
        f" [{type(error).__name__}]"
        if failure.category == "unknown" and isinstance(error, BaseException)
        else ""
    )
    return f"{status_label}{_FAILURE_LABELS[failure.category]}{type_label} (재시도 가능: {retry})"


def _origin(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        hostname = parts.hostname
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = f":{parts.port}" if parts.port is not None else ""
        return f"{parts.scheme}://{hostname}{port}/"
    except (TypeError, ValueError):
        return None


def probe_endpoint(url: str, *, timeout: float = 3.0) -> EndpointProbe:
    """Check host HTTPS/HTTP reachability without credentials, redirects or bodies."""
    origin = _origin(url)
    if origin is None:
        return EndpointProbe(False, APIFailure("provider_response", False))

    session = requests.Session()
    session.auth = _NoNetrcAuth()
    try:
        response = session.head(origin, timeout=timeout, allow_redirects=False)
        # Any HTTP response proves host reachability; no body or status is retained.
        del response
        return EndpointProbe(True)
    except requests.RequestException as exc:
        return EndpointProbe(False, classify_api_failure(exc))
    finally:
        session.close()
