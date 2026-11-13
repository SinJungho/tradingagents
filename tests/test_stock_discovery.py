"""Stock discovery uses only patched providers and synthetic style inputs."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
import pytest
import requests

from tradingagents import stock_discovery
from tradingagents.dataflows.vendors.yahoo import screener as yahoo_screener
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


def _spy_xlsx(rows: list[list[object]]) -> bytes:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    strings = []
    indices = {}
    shared_root = ET.Element(f"{namespace}sst", count="0", uniqueCount="0")
    sheet_root = ET.Element(f"{namespace}worksheet")
    sheet_data = ET.SubElement(sheet_root, f"{namespace}sheetData")

    def column_name(index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(ord("A") + remainder) + result
        return result

    for row_number, values in enumerate(rows, 1):
        row_node = ET.SubElement(sheet_data, f"{namespace}row", r=str(row_number))
        for column, value in enumerate(values, 1):
            if value in (None, ""):
                continue
            cell = ET.SubElement(row_node, f"{namespace}c", r=f"{column_name(column)}{row_number}")
            if isinstance(value, str):
                if value not in indices:
                    indices[value] = len(strings)
                    strings.append(value)
                cell.set("t", "s")
                ET.SubElement(cell, f"{namespace}v").text = str(indices[value])
            else:
                ET.SubElement(cell, f"{namespace}v").text = str(value)
    for value in strings:
        item = ET.SubElement(shared_root, f"{namespace}si")
        ET.SubElement(item, f"{namespace}t").text = value
    shared_root.set("count", str(len(strings)))
    shared_root.set("uniqueCount", str(len(strings)))
    output = io.BytesIO()
    with ZipFile(output, "w") as workbook:
        workbook.writestr("xl/sharedStrings.xml", ET.tostring(shared_root))
        workbook.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet_root))
    return output.getvalue()


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


@pytest.mark.unit
def test_public_index_parser_checks_dated_large_constituent_table():
    tickers = [f"ZX{i:03}" for i in range(490)]
    rows = "".join(f"<tr><td>{ticker}</td><td>Company</td></tr>" for ticker in tickers)
    page = (
        "<p>Current components as of October 22, 2026</p>"
        "<table><tr><th>Symbol</th><th>Company</th></tr>" + rows + "</table>"
    )

    universe = stock_discovery.parse_public_index_page(
        page,
        name="S&P 500",
        source="https://example.test/sp500",
        minimum=490,
        maximum=510,
    )

    assert universe.as_of == "2026-10-22"
    assert universe.as_of_label == "membership as of"
    assert universe.tickers == tuple(tickers)
    assert "secondary public constituent list" in universe.note
    with pytest.raises(stock_discovery.MarketUniverseError, match="expected 490–510"):
        stock_discovery.parse_public_index_page(
            page.replace(rows, "<tr><td>AAA</td><td>Only one</td></tr>"),
            name="S&P 500",
            source="https://example.test/sp500",
            minimum=490,
            maximum=510,
        )


@pytest.mark.unit
def test_iwm_holdings_parser_marks_russell_2000_as_proxy():
    text = (
        "As of November 11, 2026\n"
        "Ticker,Name,Weight (%)\n"
        "AAA,Alpha Company,0.2\n"
        "BBB,Beta Company,0.1\n"
        "BAD,Preferred Stock Example,0.0\n"
        "CASH,Cash and Derivatives,0.0\n"
    )

    universe = stock_discovery.parse_iwm_holdings(text, minimum=2, maximum=3)

    assert universe.tickers == ("AAA", "BBB")
    assert universe.as_of == "2026-11-11"
    assert universe.as_of_label == "holdings as of"
    assert "proxy" in universe.note


@pytest.mark.unit
def test_iwm_holdings_parser_reports_html_instead_of_csv():
    with pytest.raises(
        stock_discovery.MarketUniverseError,
        match="^Russell 2000 source returned an HTML page instead of the holdings CSV$",
    ):
        stock_discovery.parse_iwm_holdings(" \n<!DOCTYPE html><html></html>")

    with pytest.raises(
        stock_discovery.MarketUniverseError,
        match="^Russell 2000 holdings are missing the Ticker/Name columns$",
    ):
        stock_discovery.parse_iwm_holdings("Date,Weight\n2026-11-11,0.2\n")


@pytest.mark.unit
def test_spy_holdings_xlsx_parser_uses_dated_equity_tickers_only():
    rows = [
        ["Fund Name:", "State Street SPDR S&P 500 ETF Trust"],
        ["Ticker Symbol:", "SPY"],
        ["Holdings:", "As of 11-Nov-2026"],
        ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"],
    ]
    rows.extend([f"Synthetic Company {i}", f"AA{i:04}", str(i), "", 1.25, "-", 1000.0, "USD"]
                for i in range(495))
    rows.extend([
        ["Berkshire Hathaway Class B", "BRK.B", "", "", 1.0, "Financials", 1, "USD"],
        ["Brown-Forman Class B", "BF.B", "", "", 1.0, "Consumer Staples", 1, "USD"],
        ["Cash", "-", "", "", 0.0, "-", 1, "USD"],
        ["Contingent Value Right", "2602335D", "", "", 0.0, "-", 1, "USD"],
        ["Treasury Future", "ES", "", "", 0.0, "-", 1, "USD"],
        [],
    ])

    universe = stock_discovery.parse_spy_holdings_xlsx(_spy_xlsx(rows))

    assert len(universe.tickers) == 497
    assert universe.tickers[-2:] == ("BRK.B", "BF.B")
    assert universe.as_of == "2026-11-11"
    assert universe.as_of_label == "holdings as of"
    assert universe.source == stock_discovery.SPY_HOLDINGS_SOURCE
    assert universe.provenance["source_kind"] == "proxy"
    assert "not official S&P 500 index membership" in universe.note


@pytest.mark.unit
@pytest.mark.parametrize("count", [494, 511])
def test_spy_holdings_xlsx_parser_rejects_ticker_counts_outside_range(count):
    rows = [
        ["Holdings:", "As of 11-Nov-2026"],
        ["Name", "Ticker"],
        *[[f"Company {i}", f"AA{i:04}"] for i in range(count)],
    ]

    with pytest.raises(stock_discovery.MarketUniverseError, match=f"listed {count} securities; expected 495–510"):
        stock_discovery.parse_spy_holdings_xlsx(_spy_xlsx(rows))


@pytest.mark.unit
def test_us_listing_parser_excludes_funds_non_common_and_test_issues():
    nasdaq = (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "AAA|Alpha Common Stock|Q|N|N|100|N|N\n"
        "ETFQ|Example Fund|Q|N|N|100|Y|N\n"
        "WARR|Example Warrants|Q|N|N|100|N|N\n"
        "TEST|Test Company|Q|Y|N|100|N|N\n"
        "File Creation Time: 1112202610:30|||||||\n"
    )
    other = (
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol|NextShares\n"
        "BBB|Beta Common Stock|N|BBB|N|100|N|BBB|N\n"
        "File Creation Time: 1112202610:30||||||||\n"
    )

    universe = stock_discovery.parse_us_listed_files(nasdaq, other, minimum=2)

    assert universe.tickers == ("AAA", "BBB")
    assert universe.as_of == "2026-11-12 10:30"
    assert universe.as_of_label == "file generated"


@pytest.mark.unit
def test_market_cap_screener_reads_all_pages_and_normalizes_class_symbols(monkeypatch):
    first = [
        {"symbol": f"AA{i:03}", "marketCap": 10_000_000_000 + i}
        for i in range(250)
    ]
    screen = Mock(
        side_effect=[
            {"total": 251, "quotes": first},
            {"total": 251, "quotes": [{"symbol": "BRK.B", "marketCap": 40_000_000_000}]},
        ]
    )
    monkeypatch.setattr(yahoo_screener.yf, "screen", screen)

    caps, as_of = stock_discovery.fetch_market_cap_snapshot()

    assert len(caps) == 251
    assert caps["BRK-B"] == 40_000_000_000
    assert as_of.endswith("+00:00")
    assert [call.kwargs["offset"] for call in screen.call_args_list] == [0, 250]


@pytest.mark.unit
def test_market_discovery_scores_overlap_once_and_reports_sections(monkeypatch):
    sections = {
        "sp500": stock_discovery.DiscoveryUniverse(
            "S&P 500", "fixture://sp500", "2026-11-11", ("AAA", "BBB")
        ),
        "russell2000": stock_discovery.DiscoveryUniverse(
            "Russell 2000", "fixture://russell", "2026-11-11", ("AAA", "CCC"),
            note="synthetic proxy fixture",
        ),
    }
    calls = []
    monkeypatch.setattr(stock_discovery, "fetch_index_universe", lambda key: sections[key])
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2026-11-12")
    monkeypatch.setattr(stock_discovery, "_closes", lambda ticker: calls.append(ticker) or _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda _ticker, _as_of: FACTS)
    monkeypatch.setattr(stock_discovery, "get_splits", lambda _ticker: pd.Series(dtype=float))

    result = stock_discovery.discover_market(["sp500", "russell2000"])

    assert (result.requested, result.attempted, result.returned) == (3, 3, 3)
    assert calls == ["AAA", "BBB", "CCC"]
    assert result.tickers[0].sections == ("S&P 500", "Russell 2000")
    output = result.render()
    assert "S&P 500: securities=2" in output
    assert "Russell 2000: securities=2" in output
    assert "Bullish candidates by momentum score" in output
    assert "No LLM was called" in output


@pytest.mark.unit
def test_us_market_discovery_assigns_explicit_market_cap_bands(monkeypatch):
    listing = stock_discovery.DiscoveryUniverse(
        "US exchange-listed common stocks",
        "fixture://listing",
        "2026-11-12 10:30",
        ("LARGE", "MID", "SMALL", "MICRO", "UNKNOWN"),
        "file generated",
    )
    caps = {
        "LARGE": 10_000_000_000,
        "MID": 2_000_000_000,
        "SMALL": 300_000_000,
        "MICRO": 299_999_999,
    }
    monkeypatch.setattr(stock_discovery, "fetch_us_listed_universe", lambda: listing)
    monkeypatch.setattr(
        stock_discovery, "fetch_market_cap_snapshot", lambda: (caps, "2026-11-12T10:31:00+00:00")
    )
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2026-11-12")
    monkeypatch.setattr(stock_discovery, "_closes", lambda _ticker: _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda _ticker, _as_of: FACTS)
    monkeypatch.setattr(stock_discovery, "get_splits", lambda _ticker: pd.Series(dtype=float))

    result = stock_discovery.discover_market(["us-listed"])
    members_by_section = {section.name: section.tickers for section in result.sections}

    assert members_by_section["Large-cap (from $10,000,000,000; no upper limit)"] == ("LARGE",)
    assert members_by_section["Mid-cap (from $2,000,000,000; below $10,000,000,000)"] == ("MID",)
    assert members_by_section["Small-cap (from $300,000,000; below $2,000,000,000)"] == ("SMALL",)
    assert members_by_section["Micro-cap (from $0; below $300,000,000)"] == ("MICRO",)
    assert members_by_section["Market cap unknown"] == ("UNKNOWN",)
    assert result.tickers[0].market_cap_band == "largecap"
    assert "Market-cap snapshot: Yahoo Finance, retrieved 2026-11-12T10:31:00+00:00" in result.render()


@pytest.mark.unit
def test_combined_market_discovery_keeps_loaded_sections_when_one_source_fails(monkeypatch):
    sp500 = stock_discovery.DiscoveryUniverse(
        "S&P 500", "fixture://sp500", "2026-11-11", ("AAA",)
    )

    def fetch_index(key):
        if key == "russell2000":
            raise stock_discovery.MarketUniverseError("synthetic source failure")
        return sp500

    monkeypatch.setattr(stock_discovery, "fetch_index_universe", fetch_index)
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2026-11-12")
    monkeypatch.setattr(stock_discovery, "_closes", lambda _ticker: _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda _ticker, _as_of: FACTS)
    monkeypatch.setattr(stock_discovery, "get_splits", lambda _ticker: pd.Series(dtype=float))

    result = stock_discovery.discover_market(["sp500", "russell2000"])

    assert [section.name for section in result.sections] == ["S&P 500"]
    assert result.source_failures == (("russell2000", "synthetic source failure"),)
    assert "russell2000: synthetic source failure" in result.render()
    assert [entry.ticker for entry in result.tickers] == ["AAA"]


@pytest.mark.unit
def test_single_market_section_failure_reports_its_cause(monkeypatch):
    def fetch_index(_key):
        return stock_discovery.parse_iwm_holdings("<!DOCTYPE html><html></html>")

    monkeypatch.setattr(stock_discovery, "fetch_index_universe", fetch_index)
    with pytest.raises(stock_discovery.MarketUniverseError,
                       match="russell2000 universe failed: Russell 2000 source returned an HTML page"):
        stock_discovery.discover_market(["russell2000"])


@pytest.mark.unit
def test_all_market_discovery_records_russell_html_failure_and_continues(monkeypatch):
    listing = stock_discovery.DiscoveryUniverse(
        "US exchange-listed common stocks", "fixture://listing", "2026-11-12", ("AAA",)
    )
    other_sections = {
        key: stock_discovery.DiscoveryUniverse(key, f"fixture://{key}", "2026-11-11", ("BBB",))
        for key in stock_discovery._INDEX_ORDER
        if key != "russell2000"
    }

    def fetch_index(key):
        if key == "russell2000":
            return stock_discovery.parse_iwm_holdings("<!DOCTYPE html><html></html>")
        return other_sections[key]

    monkeypatch.setattr(stock_discovery, "fetch_us_listed_universe", lambda: listing)
    monkeypatch.setattr(stock_discovery, "fetch_market_cap_snapshot", lambda: ({"AAA": 12_000_000_000}, "2026-11-12"))
    monkeypatch.setattr(stock_discovery, "fetch_index_universe", fetch_index)
    monkeypatch.setattr(stock_discovery, "get_current_date", lambda: "2026-11-12")
    monkeypatch.setattr(stock_discovery, "_closes", lambda _ticker: _closes())
    monkeypatch.setattr(stock_discovery, "_facts", lambda _ticker, _as_of: FACTS)
    monkeypatch.setattr(stock_discovery, "get_splits", lambda _ticker: pd.Series(dtype=float))

    result = stock_discovery.discover_market(["all"])

    assert result.source_failures == (("russell2000", "Russell 2000 source returned an HTML page instead of the holdings CSV"),)
    assert "russell2000: Russell 2000 source returned an HTML page instead of the holdings CSV" in result.render()
    assert "Russell 2000" not in [section.name for section in result.sections]
    assert "sp600" in [section.name for section in result.sections]
    assert [entry.ticker for entry in result.tickers] == ["AAA", "BBB"]


@pytest.mark.unit
def test_market_discovery_rejects_invalid_combinations_before_fetching(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(stock_discovery, "fetch_index_universe", fetch)

    with pytest.raises(ValueError, match="cannot be combined"):
        stock_discovery.discover_market(["all", "sp500"])
    with pytest.raises(ValueError, match="unknown universe"):
        stock_discovery.discover_market(["russell5000"])

    fetch.assert_not_called()
