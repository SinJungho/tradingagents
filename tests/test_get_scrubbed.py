"""``get_scrubbed``: the vendor key must not survive into an error.

FRED and Alpha Vantage authenticate with a query parameter, so requests quotes
the key back in the text of HTTP, connection and timeout errors, and in the
``request`` and ``response`` it attaches (#1324).
"""

from unittest import mock

import pytest
import requests

from tradingagents.dataflows import net
from tradingagents.dataflows.net import get_scrubbed, get_with_retry

# A fabricated value in the shape of a FRED key.
_KEY = "deadbeefdeadbeefdeadbeefdeadbeef"
_LEAK = (
    "HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Max retries "
    f"exceeded with url: /fred/series?series_id=DGS10&api_key={_KEY}&file_type=json"
)


def _response(status_code):
    response = mock.Mock(spec=requests.Response)
    response.status_code = status_code
    response.raise_for_status.side_effect = requests.HTTPError(_LEAK) if status_code >= 400 else None
    return response


def _call(**kwargs):
    return get_scrubbed("https://api.stlouisfed.org/fred/series",
                        params={"api_key": _KEY}, timeout=5, secret=_KEY, **kwargs)


@pytest.mark.unit
@pytest.mark.parametrize("failure", [
    {"side_effect": requests.ConnectionError(_LEAK)},
    {"return_value": _response(500)},
], ids=["transport", "status"])
def test_the_key_is_masked_in_the_error(failure):
    with mock.patch.object(requests, "get", **failure), pytest.raises(requests.RequestException) as caught:
        _call()
    assert _KEY not in str(caught.value) and _KEY not in repr(caught.value.args)
    assert "api_key=***" in str(caught.value)


@pytest.mark.unit
def test_nothing_that_holds_the_url_travels_with_the_error():
    """The request, the response and a chained original each carry the full URL."""
    leaky = requests.ConnectionError(_LEAK)
    leaky.request = mock.Mock(url=f"https://x.invalid/?api_key={_KEY}")
    leaky.response = mock.Mock(url=f"https://x.invalid/?api_key={_KEY}")
    with mock.patch.object(requests, "get", side_effect=leaky), pytest.raises(requests.ConnectionError) as caught:
        _call()
    error = caught.value
    assert error.request is None and error.response is None
    assert error.__cause__ is None and error.__context__ is None


@pytest.mark.unit
def test_a_passthrough_status_is_returned_for_the_caller():
    response = _response(400)
    with mock.patch.object(requests, "get", return_value=response):
        assert _call(passthrough=(400,)) is response
    response.raise_for_status.assert_not_called()


@pytest.mark.unit
def test_transient_get_retries_with_safe_attempt_log(monkeypatch, caplog):
    response = _response(200)
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise requests.ConnectionError("synthetic secret and private URL")
        return response

    monkeypatch.setattr(net.requests, "get", get)
    monkeypatch.setattr(net.time, "sleep", lambda _delay: None)

    result = get_with_retry(
        "https://api.example.test/query",
        params={"api_key": _KEY},
        secret=_KEY,
        timeout=1,
        provider="Synthetic API",
    )

    assert result is response
    assert len(calls) == 2
    assert "provider=Synthetic API host=api.example.test category=connection attempt=1/3" in caplog.text
    assert "synthetic secret" not in caplog.text
    assert _KEY not in caplog.text


@pytest.mark.unit
def test_provider_server_error_retries_but_http_authentication_does_not(monkeypatch):
    overloaded = requests.Response()
    overloaded.status_code = 503
    success = _response(200)
    calls = []

    def get(*_args, **_kwargs):
        calls.append(True)
        return overloaded if len(calls) == 1 else success

    monkeypatch.setattr(net.requests, "get", get)
    monkeypatch.setattr(net.time, "sleep", lambda _delay: None)

    assert get_with_retry("https://api.example.test/query", timeout=1, provider="Synthetic API") is success
    assert len(calls) == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure",
    [
        requests.HTTPError(
            "synthetic auth response",
            response=requests.Response(),
        ),
        requests.exceptions.SSLError("synthetic certificate details"),
    ],
    ids=["authentication", "tls"],
)
def test_permanent_get_failures_are_not_retried(monkeypatch, failure):
    if isinstance(failure, requests.HTTPError):
        failure.response.status_code = 401
    calls = []

    def get(*_args, **_kwargs):
        calls.append(True)
        raise failure

    monkeypatch.setattr(net.requests, "get", get)
    monkeypatch.setattr(net.time, "sleep", lambda _delay: None)

    with pytest.raises(requests.RequestException):
        get_with_retry("https://api.example.test/query", timeout=1, provider="Synthetic API")

    assert len(calls) == 1
