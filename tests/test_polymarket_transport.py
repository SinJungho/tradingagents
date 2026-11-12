"""Synthetic transport tests: never contact DNS, a broker or an LLM."""
from unittest.mock import Mock, patch

import pytest
import requests

from tradingagents.dataflows.config import run_config, set_config
from tradingagents.dataflows.errors import drain_source_failures
from tradingagents.dataflows.vendors import polymarket as poly
from tradingagents.default_config import build_default_config
from tradingagents.runtime_diagnostics import diagnose_runtime, worker_network_policy

ALIAS = "synthetic.cloudfront.net"
CONFIG = {"polymarket_transport": "cloudfront_alias"}


def records(name=ALIAS):
    return [(2, 1, 6, name, ("192.0.2.1", 443))]


def response(status=200):
    result = requests.Response()
    result.status_code = status
    result._content = b'{"events":[]}'
    return result


def test_default_env_and_programmatic_validation(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_POLYMARKET_TRANSPORT", raising=False)
    assert build_default_config()["polymarket_transport"] == "direct"
    monkeypatch.setenv("TRADINGAGENTS_POLYMARKET_TRANSPORT", "cloudfront_alias")
    assert build_default_config()["polymarket_transport"] == "cloudfront_alias"
    monkeypatch.setenv("TRADINGAGENTS_POLYMARKET_TRANSPORT", "typo")
    with pytest.raises(ValueError, match="polymarket_transport"):
        build_default_config()
    with pytest.raises(ValueError):
        set_config({"polymarket_transport": "typo"})
    with pytest.raises(ValueError), run_config({"polymarket_transport": "typo"}):
        pass


@pytest.mark.parametrize("mode", ["direct", "cloudfront_alias"])
def test_url_host_tls_no_redirects_and_no_ambient_auth(mode):
    with run_config({"polymarket_transport": mode}), patch.object(
        poly.socket, "getaddrinfo", return_value=records()
    ) as dns, patch("tradingagents.dataflows.net.requests.get", return_value=response()) as get:
        assert poly._request("public-search", {"q": "synthetic"}) == {"events": []}
    url = get.call_args.args[0]
    kwargs = get.call_args.kwargs
    assert url == f"https://{ALIAS if mode == 'cloudfront_alias' else 'gamma-api.polymarket.com'}/public-search"
    assert kwargs["headers"] == ({"Host": "gamma-api.polymarket.com"} if mode == "cloudfront_alias" else {})
    assert kwargs["verify"] is True
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 30
    prepared = requests.Request("GET", url, headers={"Authorization": "synthetic"}).prepare()
    assert "Authorization" not in kwargs["auth"](prepared).headers
    assert dns.call_count == (1 if mode == "cloudfront_alias" else 0)


@pytest.mark.parametrize("name", [
    "", "gamma-api.polymarket.com", "cloudfront.net", "evilcloudfront.net",
    "synthetic.cloudfront.net.evil.test", "-bad.cloudfront.net", "bad/path.cloudfront.net",
])
def test_alias_rejected_without_http(name):
    with patch.object(poly.socket, "getaddrinfo", return_value=records(name)), patch(
        "tradingagents.dataflows.net.requests.get"
    ) as get, run_config(CONFIG), pytest.raises(requests.ConnectionError):
        poly._request("public-search", {})
    get.assert_not_called()


def test_dns_error_is_safe_and_trips_run_circuit():
    drain_source_failures()
    try:
        with run_config(CONFIG), patch.object(
            poly.socket, "getaddrinfo", side_effect=poly.socket.gaierror("private details")
        ) as dns:
            assert "unavailable" in poly.get_prediction_markets("synthetic")
            assert "unavailable" in poly.get_prediction_markets("another")
            assert dns.call_count == 1
    finally:
        drain_source_failures()


@pytest.mark.parametrize("failure,attempts", [
    (requests.exceptions.SSLError("synthetic"), 1),
    (requests.Timeout("synthetic"), 3),
    (requests.ConnectionError("synthetic"), 3),
])
def test_retry_bound_and_circuit(failure, attempts, caplog):
    drain_source_failures()
    try:
        with run_config(CONFIG), patch.object(poly.socket, "getaddrinfo", return_value=records()), patch(
            "tradingagents.dataflows.net.requests.get", side_effect=failure
        ) as get, patch("tradingagents.dataflows.net.time.sleep"):
            assert "unavailable" in poly.get_prediction_markets("PRIVATE_QUERY")
            assert "unavailable" in poly.get_prediction_markets("SECOND_PRIVATE_QUERY")
            assert get.call_count == attempts
        assert "PRIVATE_QUERY" not in caplog.text
        assert "cloudfront_alias" in caplog.text
    finally:
        drain_source_failures()


@pytest.mark.parametrize("status,attempts", [(301, 1), (302, 1), (307, 1), (308, 1), (503, 3), (403, 1)])
def test_http_rejection_and_server_retry(status, attempts):
    with run_config(CONFIG), patch.object(poly.socket, "getaddrinfo", return_value=records()), patch(
        "tradingagents.dataflows.net.requests.get", return_value=response(status)
    ) as get, patch("tradingagents.dataflows.net.time.sleep"):
        with pytest.raises(requests.HTTPError) as error:
            poly._request("public-search", {})
        assert error.value.status_code == status
        assert get.call_count == attempts


def test_bad_json_structure():
    bad = response()
    bad._content = b'{"unexpected":[]}'
    with (
        run_config({}),
        patch("tradingagents.dataflows.net.requests.get", return_value=bad),
        pytest.raises(requests.RequestException),
    ):
        poly._request("public-search", {})


def test_doctor_and_policy_separate_official_from_alias():
    from tradingagents.api_diagnostics import APIFailure, EndpointProbe

    def official_probe(url):
        return EndpointProbe(False, APIFailure("tls", False))
    with patch.object(poly.socket, "getaddrinfo", return_value=records()), patch.object(
        poly.requests, "Session"
    ) as session:
        session.return_value.__enter__.return_value.head.return_value = response()
        report = diagnose_runtime(config=CONFIG, environ={}, probe=official_probe)
        policy = worker_network_policy(config=CONFIG, environ={})
        kwargs = session.return_value.__enter__.return_value.head.call_args.kwargs
        assert kwargs["headers"]["Host"] == "gamma-api.polymarket.com"
        assert kwargs["verify"] is True
        assert kwargs["allow_redirects"] is False
    assert "Polymarket: 도달 실패" in report
    assert "Polymarket cloudfront_alias: HEAD" in report
    assert "검색 GET 미검증" in report
    assert ALIAS in {item["hostname"] for item in policy["destinations"]}


def test_policy_and_doctor_alias_failure_is_explicit():
    with patch.object(poly.socket, "getaddrinfo", return_value=records("")):
        policy = worker_network_policy(config=CONFIG, environ={})
        report = diagnose_runtime(config=CONFIG, environ={}, probe=Mock(return_value=poly.EndpointProbe(True)))
    assert any("Polymarket cloudfront_alias" in item for item in policy["unresolved"])
    assert "cloudfront_alias: HEAD 연결 오류" in report
