"""HTTP helpers shared by the vendors."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import requests

from tradingagents.api_diagnostics import classify_api_failure

logger = logging.getLogger(__name__)

GET_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.2


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or "unknown"
    except ValueError:
        return "unknown"


def retry_transient_call(call, *, provider: str, host: str, attempts=GET_ATTEMPTS):
    """Retry a public idempotent fetch that uses a non-requests HTTP client."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as error:
            failure = classify_api_failure(error)
            retry = failure.retryable and failure.category in {
                "dns", "connection", "timeout", "provider_server",
            }
            logger.warning(
                "API request failed provider=%s host=%s category=%s attempt=%d/%d",
                provider,
                host,
                failure.category,
                attempt,
                attempts,
            )
            if not retry or attempt == attempts:
                raise
            time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))


def get_with_retry(
    url: str,
    *,
    timeout: float,
    provider: str,
    params: dict | None = None,
    headers: dict | None = None,
    secret: str = "",
    passthrough=(),
    attempts: int = GET_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
    request_options: dict | None = None,
    reject_redirects: bool = False,
):
    """GET with bounded retries for transient transport and server failures."""
    for attempt in range(1, attempts + 1):
        error = None
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=timeout, **(request_options or {})
            )
            if reject_redirects and 300 <= response.status_code < 400:
                raise requests.HTTPError("redirect refused", response=response)
            if response.status_code not in passthrough:
                response.raise_for_status()
        except requests.RequestException as exc:
            error = exc
        else:
            return response

        failure = classify_api_failure(error)
        if not failure.retryable or attempt == attempts:
            status = getattr(getattr(error, "response", None), "status_code", None)
            message = (
                str(error).replace(secret, "***")
                if secret
                else f"{type(error).__name__}: {failure.category}"
            )
            sanitized = type(error)(message)
            if status is not None:
                sanitized.status_code = status
            sanitized.failure = failure
            logger.warning(
                "API request failed provider=%s host=%s category=%s attempt=%d/%d status=%s",
                provider,
                _host(url),
                failure.category,
                attempt,
                attempts,
                status,
            )
            # Raise after leaving the except block so the raw request and URL are
            # not retained as the new exception's context.
            raise sanitized

        host = _host(url)
        logger.warning(
            "Transient API GET failure provider=%s host=%s category=%s attempt=%d/%d status=%s",
            provider,
            host,
            failure.category,
            attempt,
            attempts,
            getattr(getattr(error, "response", None), "status_code", None),
        )
        time.sleep(base_delay * (2 ** (attempt - 1)))

    raise RuntimeError("unreachable")  # pragma: no cover


def get_scrubbed(
    url: str,
    *,
    params: dict,
    timeout: float,
    secret: str,
    passthrough=(),
    provider: str = "API",
):
    """GET a query-authenticated endpoint without retaining its secret in errors."""
    return get_with_retry(
        url,
        params=params,
        timeout=timeout,
        secret=secret,
        passthrough=passthrough,
        provider=provider,
    )


def vendor_reachable(url: str, timeout: float = 5.0) -> bool:
    """Whether the vendor answers at all, for telling silence from an outage."""
    try:
        requests.head(url, timeout=timeout, allow_redirects=True)
        return True
    except requests.RequestException:
        return False
