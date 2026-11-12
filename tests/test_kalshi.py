"""Kalshi vendor and routing tests use synthetic responses only."""

import copy
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import drain_source_failures
from tradingagents.dataflows.vendors import kalshi

SERIES = [
    {
        "ticker": "KXFED",
        "title": "Federal Reserve Rate Decisions",
        "category": "Economics",
        "categories": ["Economics"],
        "tags": ["interest rates", "Federal Reserve"],
    },
    {
        "ticker": "KXWEATHER",
        "title": "Daily Weather in New York",
        "category": "Weather",
        "categories": ["Weather"],
        "tags": ["temperature"],
    },
]


def _market(**overrides):
    return {
        "ticker": "KXFED-2030-CUT25",
        "title": "Will the Fed cut rates by 25 bps?",
        "status": "open",
        "last_price_dollars": "0.5600",
        "yes_bid_dollars": "0.5500",
        "yes_ask_dollars": "0.5700",
        "volume_fp": "1250.00",
        "close_time": "2030-12-31T00:00:00Z",
        **overrides,
    }


def _response(path, params):
    if path == "series":
        return {"series": SERIES}
    assert path == "markets"
    assert params["status"] == "open"
    assert params["limit"] == kalshi.MARKETS_PER_SERIES
    return {"markets": [_market()]}


@pytest.mark.unit
def test_kalshi_reports_a_sourced_open_market_and_bounded_search(monkeypatch):
    calls = []

    def request(path, params):
        calls.append((path, params))
        return _response(path, params)

    monkeypatch.setattr(kalshi, "_request", request)
    result = kalshi.get_prediction_markets("Fed rate cut")

    assert "Kalshi public market-data API" in result
    assert "YES 56% (YES bid-ask midpoint: bid $0.5500, ask $0.5700" in result
    assert "$0.5600 × 100 = 56%" in result
    assert "`KXFED-2030-CUT25`" in result
    assert "1,250 contracts traded" in result
    assert "up to 3 series and 100 open markets per series" in result
    assert len(calls) == 2
    assert calls[1][1]["series_ticker"] == "KXFED"


@pytest.mark.unit
def test_kalshi_uses_a_labeled_midpoint_when_no_last_trade_exists(monkeypatch):
    def request(path, params):
        if path == "series":
            return {"series": SERIES[:1]}
        return {
            "markets": [
                _market(
                    last_price_dollars=None,
                    yes_bid_dollars="0.40",
                    yes_ask_dollars="0.60",
                )
            ]
        }

    monkeypatch.setattr(kalshi, "_request", request)
    result = kalshi.get_prediction_markets("Fed rate cut")

    assert "YES 50% (YES bid-ask midpoint: bid $0.4000, ask $0.6000" in result


@pytest.mark.unit
def test_kalshi_withholds_current_prices_for_historical_runs(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("historical requests must not fetch live prices")

    monkeypatch.setattr(kalshi, "_request", unexpected_request)
    result = kalshi.get_prediction_markets("Fed rate cut", as_of_date="2025-06-01")

    assert "withheld" in result
    assert "historical vintage" in result


@pytest.mark.unit
def test_kalshi_no_match_does_not_claim_no_market_exists(monkeypatch):
    monkeypatch.setattr(kalshi, "_request", lambda path, params: {"series": []})
    result = kalshi.get_prediction_markets("obscure instrument")

    assert "No matching open markets" in result
    assert "does not establish that Kalshi has no market" in result
    assert "Do not estimate odds" in result


@pytest.mark.unit
def test_kalshi_connection_failure_trips_the_shared_prediction_circuit(monkeypatch):
    drain_source_failures()
    try:
        with mock.patch.object(
            kalshi,
            "_request",
            side_effect=[requests.ConnectionError("synthetic DNS failure"), AssertionError],
        ) as request:
            first = kalshi.get_prediction_markets("Fed rate cut")
            second = kalshi.get_prediction_markets("recession")

        assert "unavailable" in first.lower()
        assert "Do not write, invent, or estimate" in second
        assert request.call_count == 1
        assert [method for method, _ in drain_source_failures()] == [
            "get_prediction_markets",
            "get_prediction_markets",
        ]
    finally:
        drain_source_failures()


@pytest.mark.unit
def test_polymarket_is_default_and_kalshi_remains_selectable():
    assert default_config.DEFAULT_CONFIG["data_vendors"]["prediction_markets"] == "polymarket"
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    try:
        with mock.patch.dict(
            router.VENDOR_METHODS,
            {
                "get_prediction_markets": {
                    "kalshi": lambda *a, **k: "KALSHI_OK",
                    "polymarket": lambda *a, **k: "POLY_OK",
                }
            },
            clear=False,
        ):
            assert router.route_to_vendor("get_prediction_markets", "fed", 5) == "POLY_OK"
            set_config({"data_vendors": {"prediction_markets": "kalshi"}})
            assert router.route_to_vendor("get_prediction_markets", "fed", 5) == "KALSHI_OK"
    finally:
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
