"""Stock discovery uses only patched providers and synthetic style inputs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from tradingagents import stock_discovery
from tradingagents.style_scores import StyleSignal


def _fact(end: str, value: float, filed: str) -> dict:
    return {"end": end, "val": value, "filed": filed}


FACTS = {
    "Diluted EPS": [_fact("2024-12-31", 5.0, "2025-02-10")],
    "Revenue": [
        _fact("2023-12-31", 100.0, "2024-02-10"),
        _fact("2024-12-31", 120.0, "2025-02-10"),
    ],
    "Net Income": [_fact("2024-12-31", 20.0, "2025-02-10")],
    "Stockholders Equity": [_fact("2024-12-31", 100.0, "2025-02-10")],
}


def _closes() -> pd.Series:
    index = pd.bdate_range("2024-01-01", "2025-06-02")
    return pd.Series([50.0 + i / 10 for i in range(len(index))], index=index)


def _wiki_page(tickers: list[str], *, declared_count: int | None = None) -> str:
    count = len(tickers) if declared_count is None else declared_count
    rows = "".join(
        f"<tr><td>{ticker}</td><td>Company {i}</td></tr>"
        for i, ticker in enumerate(tickers)
    )
    return (
        f"<p>As of October 22, 2026, the index comprised {count} securities issued by 100 companies.</p>"
        f"<table><tr><th>Ticker</th><th>Company</th></tr>{rows}</table>"
    )


@pytest.mark.unit
def test_discovery_keeps_input_order_and_returns_partial_abstains(monkeypatch):
    closes = _closes()
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2025-06-02")
    monkeypatch.setattr(stock_discovery, "_closes", lambda ticker: closes)
    monkeypatch.setattr(stock_discovery, "_facts", lambda ticker, as_of: FACTS if ticker == "AAA" else None)
    monkeypatch.setattr(
        stock_discovery, "get_splits", lambda ticker: pd.Series(dtype=float)
    )

    result = stock_discovery.discover_stocks(["aaa", "BBB"])

    assert (result.requested, result.attempted, result.returned) == (2, 2, 2)
    assert [ticker.ticker for ticker in result.tickers] == ["AAA", "BBB"]
    assert result.tickers[0].scores["growth"].signal is StyleSignal.BULLISH
    assert result.tickers[1].scores["value"].signal is StyleSignal.ABSTAIN
    assert result.tickers[1].scores["momentum"].signal is not StyleSignal.ABSTAIN
    output = result.render()
    assert "SEC EDGAR" in output and "Yahoo Finance" in output
    assert "as_of=2024-12-31" in output
    assert "Missing inputs: Diluted EPS" in output
    assert "market-wide coverage was not assessed" in output


@pytest.mark.unit
def test_provider_failure_is_local_to_ticker_and_does_not_leak_exception_text(monkeypatch):
    closes = _closes()

    def get_closes(ticker):
        if ticker == "BAD":
            raise RuntimeError("synthetic-provider-detail-with-secret-like-text")
        return closes

    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2025-06-02")
    monkeypatch.setattr(stock_discovery, "_closes", get_closes)
    monkeypatch.setattr(stock_discovery, "_facts", lambda ticker, as_of: FACTS)
    monkeypatch.setattr(
        stock_discovery, "get_splits", lambda ticker: pd.Series(dtype=float)
    )

    result = stock_discovery.discover_stocks(["BAD", "AAA"])

    assert (result.requested, result.attempted, result.returned) == (2, 2, 2)
    assert [ticker.ticker for ticker in result.tickers] == ["BAD", "AAA"]
    assert result.tickers[0].scores["value"].signal is StyleSignal.ABSTAIN
    assert result.tickers[1].scores["value"].signal is not StyleSignal.ABSTAIN
    output = result.render()
    assert "BAD" in output and "RuntimeError" in output
    assert "synthetic-provider-detail-with-secret-like-text" not in output


@pytest.mark.unit
def test_split_history_failure_makes_value_abstain_but_keeps_other_styles(monkeypatch):
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2025-06-02")
    monkeypatch.setattr(stock_discovery, "_closes", lambda ticker: _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda ticker, as_of: FACTS)
    monkeypatch.setattr(
        stock_discovery,
        "get_splits",
        Mock(side_effect=RuntimeError("synthetic failure")),
    )

    result = stock_discovery.discover_stocks(["AAA"])
    scores = result.tickers[0].scores

    assert scores["value"].signal is StyleSignal.ABSTAIN
    assert scores["value"].score is None
    assert scores["value"].missing == ("split history",)
    assert scores["growth"].signal is StyleSignal.BULLISH
    assert result.failures[0].source == "Yahoo Finance split history"


@pytest.mark.unit
@pytest.mark.parametrize(
    "tickers",
    [[], ["AAPL", "aapl"], ["AAPL,,NVDA"], ["GC=F"], ["123"], ["AAPL"] * 11],
)
def test_bad_inputs_are_rejected_before_any_provider_calls(monkeypatch, tickers):
    close_call = Mock()
    fact_call = Mock()
    split_call = Mock()
    monkeypatch.setattr(stock_discovery, "_closes", close_call)
    monkeypatch.setattr(stock_discovery, "_facts", fact_call)
    monkeypatch.setattr(stock_discovery, "get_splits", split_call)

    with pytest.raises(ValueError):
        stock_discovery.discover_stocks(tickers)

    close_call.assert_not_called()
    fact_call.assert_not_called()
    split_call.assert_not_called()


@pytest.mark.unit
def test_ticker_count_is_checked_before_validating_or_fetching_members(monkeypatch):
    close_call = Mock()
    monkeypatch.setattr(stock_discovery, "_closes", close_call)

    with pytest.raises(ValueError, match="between 1 and 10"):
        stock_discovery.discover_stocks([" "] * 11)

    close_call.assert_not_called()


@pytest.mark.unit
def test_nasdaq100_parser_reads_dated_source_order_and_validates_security_count():
    tickers = [f"ZZ{i:03}" for i in range(101)]

    universe = stock_discovery.parse_nasdaq100_page(_wiki_page(tickers))

    assert universe.name == "Nasdaq-100"
    assert universe.source == stock_discovery.NASDAQ100_SOURCE
    assert universe.as_of == "2026-10-22"
    assert universe.tickers == tuple(tickers)

    with pytest.raises(stock_discovery.Nasdaq100UniverseError, match="lists 101"):
        stock_discovery.parse_nasdaq100_page(_wiki_page(tickers, declared_count=100))


@pytest.mark.unit
def test_nasdaq100_parser_rejects_missing_membership_date_or_invalid_table():
    with pytest.raises(stock_discovery.Nasdaq100UniverseError, match="missing its membership date"):
        stock_discovery.parse_nasdaq100_page(
            "<p>Constituents</p><table><tr><th>Ticker</th></tr><tr><td>AAA</td></tr></table>"
        )


@pytest.mark.unit
def test_nasdaq100_fetch_uses_public_source_and_scores_partial_results(monkeypatch):
    universe_tickers = ("AAA", "BBB")
    page = _wiki_page([f"ZZ{i:03}" for i in range(101)])
    fetch = Mock(return_value=SimpleNamespace(text=page))
    monkeypatch.setattr(stock_discovery, "get_with_retry", fetch)
    universe = stock_discovery.fetch_nasdaq100_universe()
    assert universe.as_of == "2026-10-22"
    fetch.assert_called_once()
    assert fetch.call_args.args == (stock_discovery.NASDAQ100_SOURCE,)
    assert fetch.call_args.kwargs["timeout"] == 20
    assert "User-Agent" in fetch.call_args.kwargs["headers"]

    monkeypatch.setattr(stock_discovery, "fetch_nasdaq100_universe", lambda: stock_discovery.DiscoveryUniverse(
        "Nasdaq-100", stock_discovery.NASDAQ100_SOURCE, "2026-10-22", universe_tickers
    ))
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2026-11-12")
    monkeypatch.setattr(stock_discovery, "_closes", lambda _ticker: _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda ticker, _as_of: FACTS if ticker == "AAA" else None)
    monkeypatch.setattr(stock_discovery, "get_splits", lambda _ticker: pd.Series(dtype=float))

    result = stock_discovery.discover_nasdaq100()
    output = result.render()

    assert (result.requested, result.attempted, result.returned) == (2, 2, 2)
    assert [entry.ticker for entry in result.tickers] == ["AAA", "BBB"]
    assert result.tickers[1].scores["value"].signal is StyleSignal.ABSTAIN
    assert "Data as of: 2026-11-12" in output
    assert "membership as of 2026-10-22" in output
    assert stock_discovery.NASDAQ100_SOURCE in output
    assert "secondary public list" in output
    assert "other US-listed securities were not assessed" in output


@pytest.mark.unit
def test_nasdaq100_fetch_reports_sanitized_source_failure(monkeypatch):
    monkeypatch.setattr(
        stock_discovery,
        "get_with_retry",
        Mock(side_effect=requests.Timeout("synthetic private request detail")),
    )

    with pytest.raises(stock_discovery.Nasdaq100UniverseError, match="Timeout") as error:
        stock_discovery.fetch_nasdaq100_universe()

    assert "synthetic private request detail" not in str(error.value)
