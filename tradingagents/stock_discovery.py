"""Current deterministic style signals for supplied tickers or US market sections."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from time import perf_counter
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests

from tradingagents import __version__
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors.sec_edgar import company_index_session
from tradingagents.dataflows.vendors.yahoo.market import get_splits
from tradingagents.dataflows.vendors.yahoo.screener import market_cap_snapshot
from tradingagents.style_scores import StyleScore, StyleSignal, _closes, _facts, score_styles

MAX_TICKERS = 10
MAX_SECTION_CANDIDATES = 10
_TICKER = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?$")
NASDAQ100_SOURCE = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
NASDAQ_LISTED_SOURCE = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_SOURCE = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
ISHARES_IWM_SOURCE = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)
SPY_HOLDINGS_SOURCE = (
    "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/"
    "etfs/us/holdings-daily-us-en-spy.xlsx"
)
_NASDAQ100_AS_OF = re.compile(
    r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the index comprised (\d+) securities issued by (\d+) companies"
)
_AS_OF_DATE = re.compile(r"as of ([A-Z][a-z]+ \d{1,2}, \d{4})", re.IGNORECASE)
_NON_COMMON_SECURITY = re.compile(
    r"\b(?:WARRANTS?|RIGHTS?|PREFERRED|PREFERENCE|DEBENTURES?|NOTES?|BONDS?|UNITS?|FUNDS?)\b"
    r"|\bLIMITED PARTNERSHIP\b|\bNEXTSHARES\b",
    re.IGNORECASE,
)

INDEX_SOURCES = {
    "sp500": (
        "S&P 500",
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        490,
        510,
    ),
    "russell1000": (
        "Russell 1000",
        "https://en.wikipedia.org/wiki/List_of_Russell_1000_companies",
        950,
        1100,
    ),
    "sp400": (
        "S&P MidCap 400",
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        380,
        420,
    ),
    "sp600": (
        "S&P SmallCap 600",
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        580,
        620,
    ),
}
MARKET_CAP_BANDS = (
    ("largecap", "Large-cap", 10_000_000_000, None),
    ("midcap", "Mid-cap", 2_000_000_000, 10_000_000_000),
    ("smallcap", "Small-cap", 300_000_000, 2_000_000_000),
    ("microcap", "Micro-cap", 0, 300_000_000),
)


class Nasdaq100UniverseError(ValueError):
    """The public Nasdaq-100 universe source could not be validated."""


@dataclass(frozen=True)
class DiscoveryUniverse:
    name: str
    source: str
    as_of: str
    tickers: tuple[str, ...]
    as_of_label: str = "membership as of"
    note: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(), compare=False)

    @property
    def provenance(self) -> dict:
        kind = ('proxy' if 'ishares.com' in self.source or 'ssga.com' in self.source else
                'secondary' if 'wikipedia.org' in self.source or 'Yahoo' in self.source else 'official')
        urls = (self.source.split('; ') if self.source.startswith('https://') else
                ['https://finance.yahoo.com/screener/'])
        membership = None if 'retrieved' in self.as_of_label or 'snapshot' in self.as_of_label else self.as_of
        return {'source_urls': urls, 'retrieved_at': self.retrieved_at,
                'membership_as_of': membership, 'source_kind': kind}

    def render_provenance(self) -> str:
        info = self.provenance
        return (f"Source URLs: {', '.join(info['source_urls'])}; kind={info['source_kind']}; "
                f"retrieved_at={info['retrieved_at']}; membership_as_of={info['membership_as_of'] or 'unknown'}")


@dataclass(frozen=True)
class DiscoveryFailure:
    ticker: str
    source: str
    reason: str


@dataclass(frozen=True)
class DiscoveredTicker:
    ticker: str
    scores: dict[str, StyleScore]
    sections: tuple[str, ...] = ()
    market_cap: int | None = None
    market_cap_band: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    as_of: str
    requested: int
    attempted: int
    returned: int
    tickers: tuple[DiscoveredTicker, ...]
    failures: tuple[DiscoveryFailure, ...]
    universe: DiscoveryUniverse | None = None
    sections: tuple[DiscoveryUniverse, ...] = ()
    market_cap_as_of: str | None = None
    source_failures: tuple[tuple[str, str], ...] = ()

    timings: dict[str, float] = field(default_factory=dict, compare=False)
    calls: dict[str, int] = field(default_factory=dict, compare=False)

    def render(self) -> str:
        if self.sections:
            return self._render_sections()
        if self.universe:
            lines = [
                f"Deterministic style scores for {self.universe.name} constituents",
                f"Data as of: {self.as_of}",
                f"Universe: {self.universe.name}; membership as of {self.universe.as_of}; "
                f"securities={len(self.universe.tickers)}",
                f"Universe source: {self.universe.source}",
                self.universe.render_provenance(),
                "Universe note: secondary public list; not an official Nasdaq index data feed.",
                "Sources: Yahoo Finance (daily prices and splits); SEC EDGAR (annual facts)",
                f"Counts: requested={self.requested}, attempted={self.attempted}, returned={self.returned}",
                "Scope: sourced Nasdaq-100 constituents only; other US-listed securities were not assessed.",
            ]
        else:
            lines = [
                "Deterministic style scores for supplied tickers",
                f"As of: {self.as_of}",
                "Sources: Yahoo Finance (daily prices and splits); SEC EDGAR (annual facts)",
                f"Counts: requested={self.requested}, attempted={self.attempted}, returned={self.returned}",
                "Scope: supplied tickers only; market-wide coverage was not assessed.",
            ]
        failures_by_ticker: dict[str, list[DiscoveryFailure]] = {}
        for failure in self.failures:
            failures_by_ticker.setdefault(failure.ticker, []).append(failure)

        for ticker_result in self.tickers:
            lines.append("")
            lines.append(ticker_result.ticker)
            for style, score in ticker_result.scores.items():
                label = f"  {style.capitalize()}: {score.signal}"
                if score.score is not None:
                    label += f" (score {score.score:+.4f})"
                lines.append(label)
                for metric in score.metrics:
                    lines.append(
                        f"    {metric.name}={metric.value:g}; source={metric.source}; "
                        f"as_of={metric.period_end}"
                    )
                if score.missing:
                    lines.append(f"    Missing inputs: {', '.join(score.missing)}")
            for failure in failures_by_ticker.get(ticker_result.ticker, ()):
                lines.append(f"    Failure: {failure.source}: {failure.reason}")

        returned_tickers = {ticker.ticker for ticker in self.tickers}
        for failure in self.failures:
            if failure.ticker not in returned_tickers:
                lines.extend(("", failure.ticker, f"  Failure: {failure.source}: {failure.reason}"))
        if self.timings:
            lines.append("Stage seconds: " + ", ".join(f"{k}={v:.4f}" for k, v in self.timings.items()))
            lines.append("Provider calls: " + ", ".join(f"{k}={v}" for k, v in self.calls.items()))
        return "\n".join(lines)

    def _render_sections(self) -> str:
        lines = [
            "Deterministic US market discovery",
            f"Factor data as of: {self.as_of}",
            f"Counts: unique requested={self.requested}, attempted={self.attempted}, returned={self.returned}",
            "Factors: existing value, growth, quality and momentum signals; no combined rank or recommendation.",
        ]
        if self.market_cap_as_of:
            lines.append(f"Market-cap snapshot: Yahoo Finance, retrieved {self.market_cap_as_of}")
        scores = {entry.ticker: entry for entry in self.tickers}
        for section in self.sections:
            section_results = [scores[ticker] for ticker in section.tickers if ticker in scores]
            lines.extend(
                (
                    "",
                    f"{section.name}: securities={len(section.tickers)}, scored={len(section_results)}; "
                    f"{section.as_of_label} {section.as_of}",
                    f"  Source: {section.source}",
                    f"  {section.render_provenance()}",
                )
            )
            if section.note:
                lines.append(f"  Note: {section.note}")
            for style in ("value", "growth", "quality", "momentum"):
                counts = dict.fromkeys(StyleSignal, 0)
                for item in section_results:
                    counts[item.scores[style].signal] += 1
                tally = ", ".join(
                    f"{signal.value}={counts[signal]}" for signal in StyleSignal
                )
                lines.append(f"  {style}: {tally}")
                candidates = sorted(
                    (
                        (item.ticker, item.scores[style].score)
                        for item in section_results
                        if item.scores[style].signal is StyleSignal.BULLISH
                        and item.scores[style].score is not None
                    ),
                    key=lambda candidate: (-candidate[1], candidate[0]),
                )[:MAX_SECTION_CANDIDATES]
                if candidates:
                    rendered = ", ".join(f"{ticker} ({score:+.4f})" for ticker, score in candidates)
                    lines.append(f"    Bullish candidates by {style} score (up to 10): {rendered}")
        if self.source_failures:
            lines.extend(("", "Universe/source failures:"))
            lines.extend(f"  {source}: {reason}" for source, reason in self.source_failures)
        if self.failures:
            lines.extend(("", f"Ticker data failures: {len(self.failures)}"))
            lines.extend(
                f"  {failure.ticker}: {failure.source} ({failure.reason})"
                for failure in self.failures[:20]
            )
            if len(self.failures) > 20:
                lines.append(f"  … and {len(self.failures) - 20} more")
        lines.extend(
            (
                "",
                "Bullish signals are deterministic screens, not validated return predictions. "
                "No LLM was called; choose up to 10 symbols for separate TradingAgents analysis.",
            )
        )
        if self.timings:
            lines.append("Stage seconds: " + ", ".join(f"{k}={v:.4f}" for k, v in self.timings.items()))
            lines.append("Provider calls: " + ", ".join(f"{k}={v}" for k, v in self.calls.items()))
        return "\n".join(lines)


def _validated_tickers(tickers: Sequence[str]) -> tuple[str, ...]:
    if isinstance(tickers, (str, bytes)) or not isinstance(tickers, Sequence):
        raise ValueError("tickers must be a finite sequence of ticker symbols")
    if not 1 <= len(tickers) <= MAX_TICKERS:
        raise ValueError(f"provide between 1 and {MAX_TICKERS} tickers")
    return _normalize_tickers(tickers)


def _normalize_tickers(tickers: Sequence[str]) -> tuple[str, ...]:
    if isinstance(tickers, (str, bytes)) or not isinstance(tickers, Sequence):
        raise ValueError("tickers must be a finite sequence of ticker symbols")
    if not tickers:
        raise ValueError("provide at least one ticker")

    normalized = []
    seen = set()
    for raw in tickers:
        if not isinstance(raw, str):
            raise ValueError("each ticker must be a string")
        ticker = raw.strip().upper()
        if len(ticker) > 32 or not _TICKER.fullmatch(ticker):
            raise ValueError(f"invalid US stock ticker format: {raw!r}")
        if ticker in seen:
            raise ValueError(f"duplicate ticker: {ticker}")
        seen.add(ticker)
        normalized.append(ticker)
    return tuple(normalized)


def _failure(ticker: str, source: str, exc: Exception) -> DiscoveryFailure:
    # Avoid copying arbitrary provider exception text into a report; it may
    # contain request details. NoMarketDataError is handled as missing input.
    return DiscoveryFailure(ticker, source, type(exc).__name__)


class _Nasdaq100PageParser(HTMLParser):
    """Collect visible text and simple HTML tables without an HTML dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._table_depth == 0:
                self._table = []
            self._table_depth += 1
        elif self._table_depth == 1:
            if tag == "tr":
                self._row = []
            elif tag in {"th", "td"} and self._row is not None:
                self._cell = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._table_depth == 1 and self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 1 and tag in {"th", "td"} and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._table is not None:
                self.tables.append(self._table)
                self._table = None


def parse_nasdaq100_page(page: str) -> DiscoveryUniverse:
    """Parse the dated constituent table published on the public Wikipedia page."""
    parser = _Nasdaq100PageParser()
    parser.feed(page)
    text = " ".join(" ".join(parser.text).split())
    match = _NASDAQ100_AS_OF.search(text)
    if not match:
        raise Nasdaq100UniverseError("Nasdaq-100 source is missing its membership date or security count")
    try:
        as_of = datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
    except ValueError:
        raise Nasdaq100UniverseError("Nasdaq-100 source has an invalid membership date") from None
    expected_count = int(match.group(2))
    company_count = int(match.group(3))
    if company_count != 100 or expected_count < company_count:
        raise Nasdaq100UniverseError("Nasdaq-100 source has an unexpected company or security count")

    for table in parser.tables:
        if not table:
            continue
        ticker_column = next(
            (i for i, cell in enumerate(table[0]) if cell.casefold() == "ticker"), None
        )
        if ticker_column is None:
            continue
        tickers = []
        for row in table[1:]:
            if ticker_column >= len(row):
                continue
            ticker = row[ticker_column].strip().upper()
            if not ticker:
                continue
            if not _TICKER.fullmatch(ticker):
                raise Nasdaq100UniverseError("Nasdaq-100 source contains an invalid ticker")
            tickers.append(ticker)
        if len(tickers) != expected_count:
            raise Nasdaq100UniverseError(
                f"Nasdaq-100 source declares {expected_count} securities but lists {len(tickers)}"
            )
        if len(set(tickers)) != len(tickers):
            raise Nasdaq100UniverseError("Nasdaq-100 source contains duplicate tickers")
        return DiscoveryUniverse(
            "Nasdaq-100",
            NASDAQ100_SOURCE,
            as_of,
            tuple(tickers),
            "membership as of",
            "secondary public list; not an official Nasdaq index data feed",
        )

    raise Nasdaq100UniverseError("Nasdaq-100 source does not contain a ticker table")


def fetch_nasdaq100_universe() -> DiscoveryUniverse:
    """Fetch the current public Nasdaq-100 list, with its page-provided date."""
    try:
        response = get_with_retry(
            NASDAQ100_SOURCE,
            timeout=20,
            provider="Nasdaq-100 universe",
            headers={
                "User-Agent": (
                    f"TradingAgents/{__version__} (Nasdaq-100 discovery; "
                    "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies)"
                )
            },
        )
    except requests.RequestException as exc:
        raise Nasdaq100UniverseError(
            f"Nasdaq-100 source request failed ({type(exc).__name__})"
        ) from None
    try:
        return parse_nasdaq100_page(response.text)
    except Nasdaq100UniverseError:
        raise
    except Exception as exc:
        raise Nasdaq100UniverseError(
            f"Nasdaq-100 source could not be parsed ({type(exc).__name__})"
        ) from None


class MarketUniverseError(ValueError):
    """A current market or index universe could not be validated."""


def _fetch_text(source: str, name: str) -> str:
    try:
        response = get_with_retry(
            source,
            timeout=30,
            provider=f"{name} universe",
            headers={"User-Agent": f"TradingAgents/{__version__} (US market discovery)"},
        )
    except requests.RequestException as exc:
        raise MarketUniverseError(f"{name} source request failed ({type(exc).__name__})") from None
    return response.text


def _fetch_bytes(source: str, name: str) -> bytes:
    try:
        response = get_with_retry(
            source,
            timeout=30,
            provider=f"{name} universe",
            headers={"User-Agent": f"TradingAgents/{__version__} (US market discovery)"},
        )
    except requests.RequestException as exc:
        raise MarketUniverseError(f"{name} source request failed ({type(exc).__name__})") from None
    return response.content


def _source_as_of(text: str, *, fallback: str | None = None) -> tuple[str, str]:
    match = _AS_OF_DATE.search(text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat(), "source date"
        except ValueError:
            pass
    return fallback or get_current_date(), "source retrieved"


def parse_public_index_page(
    page: str,
    *,
    name: str,
    source: str,
    minimum: int,
    maximum: int,
) -> DiscoveryUniverse:
    """Parse and count-check a public constituent table without trusting saved lists."""
    parser = _Nasdaq100PageParser()
    parser.feed(page)
    as_of, date_label = _source_as_of(" ".join(parser.text))
    for table in parser.tables:
        if not table:
            continue
        headers = [cell.casefold().strip() for cell in table[0]]
        column = next((i for i, header in enumerate(headers) if header in {"symbol", "ticker"}), None)
        if column is None:
            continue
        tickers = []
        for row in table[1:]:
            if column >= len(row):
                continue
            ticker = row[column].strip().upper()
            if not ticker:
                continue
            if not _TICKER.fullmatch(ticker):
                raise MarketUniverseError(f"{name} source contains an invalid ticker")
            tickers.append(ticker)
        if not minimum <= len(tickers) <= maximum:
            raise MarketUniverseError(
                f"{name} source listed {len(tickers)} securities; expected {minimum}–{maximum}"
            )
        if len(set(tickers)) != len(tickers):
            raise MarketUniverseError(f"{name} source contains duplicate tickers")
        label = "membership as of" if date_label == "source date" else "list retrieved"
        return DiscoveryUniverse(
            name,
            source,
            as_of,
            tuple(tickers),
            label,
            "secondary public constituent list; not an official index-provider feed",
        )
    raise MarketUniverseError(f"{name} source does not contain a ticker table")


def parse_iwm_holdings(text: str, *, minimum: int = 1600, maximum: int = 2300) -> DiscoveryUniverse:
    """Use disclosed IWM holdings as a dated Russell 2000 membership proxy."""
    if text.lstrip().startswith("<"):
        raise MarketUniverseError("Russell 2000 source returned an HTML page instead of the holdings CSV")
    rows = list(csv.reader(io.StringIO(text)))
    header_index = next(
        (
            i
            for i, row in enumerate(rows)
            if {cell.strip().casefold() for cell in row} >= {"ticker", "name"}
        ),
        None,
    )
    if header_index is None:
        raise MarketUniverseError("Russell 2000 holdings are missing the Ticker/Name columns")
    headers = [cell.strip().casefold() for cell in rows[header_index]]
    ticker_column, name_column = headers.index("ticker"), headers.index("name")
    asset_column = headers.index("asset class") if "asset class" in headers else None
    tickers = []
    for row in rows[header_index + 1 :]:
        if max(ticker_column, name_column) >= len(row):
            continue
        ticker, security_name = row[ticker_column].strip().upper(), row[name_column].strip()
        asset_class = row[asset_column].strip().casefold() if asset_column is not None and asset_column < len(row) else ""
        if (
            not ticker
            or ticker in {"-", "TOTAL"}
            or _NON_COMMON_SECURITY.search(security_name)
            or re.search(r"\b(?:CASH|RECEIVABLES?|FUTURES?)\b", security_name, re.IGNORECASE)
            or security_name.casefold() in {"usd", "u.s. dollar", "united states dollar"}
            or asset_class and "equity" not in asset_class
        ):
            continue
        if _TICKER.fullmatch(ticker):
            tickers.append(ticker)
    if not minimum <= len(tickers) <= maximum:
        raise MarketUniverseError(
            f"Russell 2000 holdings listed {len(tickers)} securities; expected {minimum}–{maximum}"
        )
    if len(set(tickers)) != len(tickers):
        raise MarketUniverseError("Russell 2000 holdings contain duplicate tickers")
    as_of, label = _source_as_of(text)
    return DiscoveryUniverse(
        "Russell 2000",
        ISHARES_IWM_SOURCE,
        as_of,
        tuple(tickers),
        "holdings as of" if label == "source date" else "holdings retrieved",
        "iShares IWM holdings proxy; its basket can differ from official Russell 2000 membership",
    )


def _xlsx_column_index(reference: str) -> int | None:
    match = re.match(r"[A-Z]+", reference)
    if not match:
        return None
    index = 0
    for letter in match.group():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _xlsx_cell_value(cell, shared_strings: list[str]) -> str:
    value = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
    if cell.get("t") == "s":
        if value is None or value.text is None:
            return ""
        try:
            index = int(value.text)
        except ValueError:
            raise MarketUniverseError("SPY holdings workbook has an invalid shared string index") from None
        if not 0 <= index < len(shared_strings):
            raise MarketUniverseError("SPY holdings workbook has an invalid shared string index")
        return shared_strings[index]
    if cell.get("t") == "inlineStr":
        return "".join(
            item.text or ""
            for item in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
        )
    return value.text if value is not None and value.text else ""


def parse_spy_holdings_xlsx(
    content: bytes,
    *,
    minimum: int = 495,
    maximum: int = 510,
) -> DiscoveryUniverse:
    """Parse SPY's dated ETF holdings sheet without an Excel dependency."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with ZipFile(io.BytesIO(content)) as workbook:
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    except (BadZipFile, KeyError, ET.ParseError, OSError):
        raise MarketUniverseError("SPY holdings workbook could not be read") from None
    shared_strings = [
        "".join(item.text or "" for item in entry.iter(f"{namespace}t"))
        for entry in shared_root.findall(f"{namespace}si")
    ]
    rows = []
    for row in sheet_root.findall(f".//{namespace}row"):
        cells = {}
        for cell in row.findall(f"{namespace}c"):
            column = _xlsx_column_index(cell.get("r", ""))
            if column is not None:
                cells[column] = _xlsx_cell_value(cell, shared_strings)
        rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])

    date = next(
        (
            match.group(1)
            for row in rows
            for cell in row
            if (match := re.fullmatch(r"As of\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", cell.strip(), re.I))
        ),
        None,
    )
    if date is None:
        raise MarketUniverseError("SPY holdings workbook is missing its as-of date")
    try:
        as_of = datetime.strptime(date, "%d-%b-%Y").date().isoformat()
    except ValueError:
        raise MarketUniverseError("SPY holdings workbook has an invalid as-of date") from None

    header_index = next(
        (i for i, row in enumerate(rows) if {cell.strip().casefold() for cell in row} >= {"name", "ticker"}),
        None,
    )
    if header_index is None:
        raise MarketUniverseError("SPY holdings workbook is missing the Name/Ticker columns")
    headers = [cell.strip().casefold() for cell in rows[header_index]]
    name_column, ticker_column = headers.index("name"), headers.index("ticker")
    tickers = []
    for row in rows[header_index + 1 :]:
        if max(name_column, ticker_column) >= len(row):
            continue
        name, ticker = row[name_column].strip(), row[ticker_column].strip().upper()
        if (
            not ticker
            or ticker in {"-", "TOTAL"}
            or _NON_COMMON_SECURITY.search(name)
            or re.search(r"\b(?:CASH|RECEIVABLES?|FUTURES?)\b", name, re.IGNORECASE)
            or name.casefold() in {"usd", "u.s. dollar", "united states dollar"}
        ):
            continue
        if _TICKER.fullmatch(ticker):
            tickers.append(ticker)
    if not minimum <= len(tickers) <= maximum:
        raise MarketUniverseError(
            f"SPY holdings listed {len(tickers)} securities; expected {minimum}–{maximum}"
        )
    if len(set(tickers)) != len(tickers):
        raise MarketUniverseError("SPY holdings contain duplicate tickers")
    return DiscoveryUniverse(
        "S&P 500 SPY holdings proxy",
        SPY_HOLDINGS_SOURCE,
        as_of,
        tuple(tickers),
        "holdings as of",
        "SPDR SPY holdings proxy; not official S&P 500 index membership",
    )


def fetch_spy_holdings_universe() -> DiscoveryUniverse:
    return parse_spy_holdings_xlsx(_fetch_bytes(SPY_HOLDINGS_SOURCE, "SPY"))


def _listing_file_timestamp(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if "File Creation Time" not in line:
            continue
        match = re.search(r"(\d{8})(\d{2}):?(\d{2})?", line)
        if match:
            try:
                value = datetime.strptime(
                    "".join(part or "00" for part in match.groups()), "%m%d%Y%H%M"
                )
                return value.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return None
    return None


def parse_us_listed_files(
    nasdaq_text: str,
    other_text: str,
    *,
    minimum: int = 1000,
) -> DiscoveryUniverse:
    """Parse Nasdaq Trader's current Nasdaq and other-exchange symbol files."""
    selected: dict[str, None] = {}
    for content, symbol_fields in (
        (nasdaq_text, ("Symbol",)),
        (other_text, ("NASDAQ Symbol", "CQS Symbol", "ACT Symbol")),
    ):
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), delimiter="|")
        if not reader.fieldnames:
            raise MarketUniverseError("Nasdaq Trader listing file has no header")
        fields = {field.strip() for field in reader.fieldnames}
        if "Security Name" not in fields:
            raise MarketUniverseError("Nasdaq Trader listing file is missing Security Name")
        if not any(field in fields for field in symbol_fields):
            raise MarketUniverseError("Nasdaq Trader listing file is missing its symbol column")
        for row in reader:
            name = (row.get("Security Name") or "").strip()
            if not name or "File Creation Time" in name or _NON_COMMON_SECURITY.search(name):
                continue
            if (row.get("ETF") or "").strip().upper() == "Y":
                continue
            if (row.get("Test Issue") or "").strip().upper() == "Y":
                continue
            if (row.get("NextShares") or "").strip().upper() == "Y":
                continue
            symbol = next(
                (
                    candidate
                    for field in symbol_fields
                    if _TICKER.fullmatch(candidate := (row.get(field) or "").strip().upper())
                ),
                "",
            )
            if symbol:
                selected.setdefault(symbol, None)
    if len(selected) < minimum:
        raise MarketUniverseError(
            f"Nasdaq Trader listing files returned only {len(selected)} eligible symbols"
        )
    timestamps = [
        timestamp
        for timestamp in (_listing_file_timestamp(nasdaq_text), _listing_file_timestamp(other_text))
        if timestamp
    ]
    return DiscoveryUniverse(
        "US exchange-listed common stocks",
        f"{NASDAQ_LISTED_SOURCE}; {OTHER_LISTED_SOURCE}",
        max(timestamps) if timestamps else get_current_date(),
        tuple(selected),
        "file generated" if timestamps else "files retrieved",
        "Nasdaq Trader files; ETF, test issues and explicitly named non-common securities excluded; OTC excluded",
    )


def fetch_us_listed_universe() -> DiscoveryUniverse:
    nasdaq = _fetch_text(NASDAQ_LISTED_SOURCE, "Nasdaq-listed")
    other = _fetch_text(OTHER_LISTED_SOURCE, "other-exchange-listed")
    return parse_us_listed_files(nasdaq, other)


def fetch_market_cap_snapshot() -> tuple[dict[str, int], str]:
    """Return the Yahoo snapshot, mapping vendor-layer errors to universe errors."""
    try:
        return market_cap_snapshot()
    except Exception as exc:
        raise MarketUniverseError(
            f"Yahoo market-cap screener failed ({type(exc).__name__})"
        ) from None


def fetch_index_universe(key: str) -> DiscoveryUniverse:
    if key == "nasdaq100":
        return fetch_nasdaq100_universe()
    if key == "russell2000":
        return parse_iwm_holdings(_fetch_text(ISHARES_IWM_SOURCE, "Russell 2000"))
    name, source, minimum, maximum = INDEX_SOURCES[key]
    return parse_public_index_page(
        _fetch_text(source, name),
        name=name,
        source=source,
        minimum=minimum,
        maximum=maximum,
    )


_INDEX_ORDER = ("nasdaq100", "sp500", "russell1000", "russell2000", "sp400", "sp600")
_INDEX_KEYS = set(_INDEX_ORDER)
_UNIVERSE_KEYS = _INDEX_KEYS | {"us-listed", "all", *(band[0] for band in MARKET_CAP_BANDS)}


def _universe_selection(universes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(universes, (str, bytes)) or not isinstance(universes, Sequence) or not universes:
        raise ValueError("provide one or more --universe sections")
    selected = tuple(value.strip().lower() for value in universes if isinstance(value, str))
    if len(selected) != len(universes) or any(not value for value in selected):
        raise ValueError("universe sections must be non-empty strings")
    unknown = sorted(set(selected) - _UNIVERSE_KEYS)
    if unknown:
        raise ValueError(f"unknown universe section: {', '.join(unknown)}")
    if len(set(selected)) != len(selected):
        raise ValueError("universe sections must not be repeated")
    if "all" in selected and len(selected) > 1:
        raise ValueError("--universe all cannot be combined with other sections")
    return selected


def discover_market(
    universes: Sequence[str],
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> DiscoveryResult:
    """Score selected US market sections once per unique symbol; never calls an LLM."""
    universe_started = perf_counter()
    selected = _universe_selection(universes)
    all_sections = selected == ("all",)
    wants_market = all_sections or "us-listed" in selected or any(
        key in {band[0] for band in MARKET_CAP_BANDS} for key in selected
    )
    listing_universe = None
    market_caps: dict[str, int] = {}
    market_cap_as_of = None
    source_failures: list[tuple[str, str]] = []
    sections: list[DiscoveryUniverse] = []
    cap_keys = {band[0] for band in MARKET_CAP_BANDS}
    include_size_sections = all_sections or "us-listed" in selected
    requested_cap_keys = cap_keys if include_size_sections else cap_keys.intersection(selected)

    if wants_market:
        try:
            listing_universe = fetch_us_listed_universe()
            if include_size_sections or "us-listed" in selected:
                sections.append(listing_universe)
        except MarketUniverseError as exc:
            if all_sections or "us-listed" in selected or requested_cap_keys:
                raise
            source_failures.append(("US exchange listings", str(exc)))

        if listing_universe:
            try:
                market_caps, market_cap_as_of = fetch_market_cap_snapshot()
            except MarketUniverseError as exc:
                source_failures.append(("Yahoo Finance market-cap screener", str(exc)))
                if requested_cap_keys:
                    market_caps = {}
                    if not include_size_sections:
                        raise
            by_band: dict[str, list[str]] = {key: [] for key in cap_keys}
            unknown_cap: list[str] = []
            for ticker in listing_universe.tickers:
                cap = market_caps.get(_provider_symbol(ticker))
                band = _cap_band(cap)
                if band is None:
                    unknown_cap.append(ticker)
                else:
                    by_band[band].append(ticker)
            if include_size_sections:
                for key, label, minimum, maximum in MARKET_CAP_BANDS:
                    upper = "no upper limit" if maximum is None else f"below ${maximum:,}"
                    sections.append(
                        DiscoveryUniverse(
                            f"{label} (from ${minimum:,}; {upper})",
                            "Yahoo Finance equity screener",
                            market_cap_as_of or get_current_date(),
                            tuple(by_band[key]),
                            "market-cap snapshot",
                            "project-defined market-cap bands; not index membership",
                        )
                    )
                if unknown_cap:
                    sections.append(
                        DiscoveryUniverse(
                            "Market cap unknown",
                            "Yahoo Finance equity screener",
                            market_cap_as_of or get_current_date(),
                            tuple(unknown_cap),
                            "market-cap snapshot",
                            "missing or invalid market capitalization",
                        )
                    )
            else:
                for key, label, minimum, maximum in MARKET_CAP_BANDS:
                    if key not in requested_cap_keys:
                        continue
                    upper = "no upper limit" if maximum is None else f"below ${maximum:,}"
                    sections.append(
                        DiscoveryUniverse(
                            f"{label} (from ${minimum:,}; {upper})",
                            "Yahoo Finance equity screener",
                            market_cap_as_of or get_current_date(),
                            tuple(by_band[key]),
                            "market-cap snapshot",
                            "project-defined market-cap bands; not index membership",
                        )
                    )

    requested_indexes = (
        _INDEX_ORDER if all_sections else tuple(key for key in selected if key in _INDEX_KEYS)
    )
    for key in requested_indexes:
        try:
            sections.append(fetch_index_universe(key))
        except (MarketUniverseError, Nasdaq100UniverseError) as exc:
            # Universe errors carry fixed, credential-free text; show the cause, not just the type.
            source_failures.append((key, str(exc)))
            if not all_sections and len(selected) == 1:
                raise MarketUniverseError(f"{key} universe failed: {exc}") from None

    if not sections:
        raise MarketUniverseError("no requested market section could be loaded")
    tickers = tuple(dict.fromkeys(ticker for section in sections for ticker in section.tickers))
    if not tickers:
        raise MarketUniverseError("requested market sections contain no eligible tickers")
    if not market_caps:
        source_failures.extend(
            (section.name, "market capitalization unavailable")
            for section in sections
            if section.as_of_label == "market-cap snapshot"
        )
    universe_seconds = perf_counter() - universe_started
    result = _score_tickers(
        tickers,
        sections=tuple(sections),
        market_caps=market_caps,
        market_cap_as_of=market_cap_as_of,
        source_failures=tuple(source_failures),
        progress=progress,
    )

    return replace(result, timings={"universe": universe_seconds, **result.timings})


def _provider_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def _cap_band(market_cap: int | None) -> str | None:
    if market_cap is None:
        return None
    for key, _label, minimum, maximum in MARKET_CAP_BANDS:
        if market_cap >= minimum and (maximum is None or market_cap < maximum):
            return key
    return None


_SPLIT_WORKERS = 8


def _fetch_splits(symbol: str) -> tuple[pd.Series | None, Exception | None]:
    try:
        return get_splits(symbol), None
    except Exception as exc:  # handled per ticker, exactly as a sequential call would be
        return None, exc


@company_index_session()
def _score_tickers(
    names: tuple[str, ...],
    universe: DiscoveryUniverse | None = None,
    *,
    sections: tuple[DiscoveryUniverse, ...] = (),
    market_caps: dict[str, int] | None = None,
    market_cap_as_of: str | None = None,
    source_failures: tuple[tuple[str, str], ...] = (),
    progress: Callable[[int, int, str], None] | None = None,
) -> DiscoveryResult:
    as_of = get_current_date()
    results: list[DiscoveredTicker] = []
    failures: list[DiscoveryFailure] = []
    attempted = 0
    memberships: dict[str, list[str]] = {}
    for section in sections:
        for ticker in section.tickers:
            memberships.setdefault(ticker, []).append(section.name)

    started = perf_counter()
    timings = dict.fromkeys(('prices', 'sec', 'splits', 'scoring'), 0.0)
    calls = dict.fromkeys(('prices', 'sec', 'splits'), 0)
    reused = {}
    # Split history has no disk cache and dominated warm runs (266 of 288 s for 503 tickers),
    # so fetch it once per provider symbol up front, in parallel.
    stage = perf_counter()
    symbols = list(dict.fromkeys(_provider_symbol(ticker) for ticker in names))
    with ThreadPoolExecutor(max_workers=_SPLIT_WORKERS) as pool:
        split_results = dict(zip(symbols, pool.map(_fetch_splits, symbols), strict=True))
    timings['splits'] = perf_counter() - stage
    for ticker in names:
        attempted += 1
        if progress:
            progress(attempted, len(names), ticker)
        symbol = _provider_symbol(ticker)
        if symbol in reused:
            cached, prior_failures = reused[symbol]
            failures.extend(replace(failure, ticker=ticker) for failure in prior_failures)
            if cached is not None:
                results.append(replace(cached, ticker=ticker, sections=tuple(memberships.get(ticker, ()))))
            continue
        failure_start = len(failures)
        stage = perf_counter()
        calls['prices'] += 1
        try:
            closes = _closes(symbol)
        except NoMarketDataError:
            closes = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        except Exception as exc:
            closes = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            failures.append(_failure(ticker, "Yahoo Finance price history", exc))

        timings['prices'] += perf_counter() - stage
        stage = perf_counter()
        calls['sec'] += 1
        try:
            facts = _facts(symbol, as_of)
        except NoMarketDataError:
            facts = None
        except Exception as exc:
            facts = None
            failures.append(_failure(ticker, "SEC EDGAR annual facts", exc))

        timings['sec'] += perf_counter() - stage
        calls['splits'] += 1
        splits, split_error = split_results[symbol]
        splits_available = split_error is None
        if split_error is not None and not isinstance(split_error, NoMarketDataError):
            failures.append(_failure(ticker, "Yahoo Finance split history", split_error))

        stage = perf_counter()
        try:
            scores = score_styles(as_of, closes, facts, splits)
        except Exception as exc:
            failures.append(_failure(ticker, "style scoring", exc))
            reused[symbol] = (None, failures[failure_start:])
            timings['scoring'] += perf_counter() - stage
            continue

        timings['scoring'] += perf_counter() - stage
        if not splits_available:
            missing = tuple(dict.fromkeys((*scores["value"].missing, "split history")))
            scores["value"] = StyleScore(
                "value", StyleSignal.ABSTAIN, None, missing=missing
            )
        market_cap = (market_caps or {}).get(_provider_symbol(ticker))
        results.append(
            DiscoveredTicker(
                ticker,
                scores,
                tuple(memberships.get(ticker, ())),
                market_cap,
                _cap_band(market_cap),
            )
        )

        reused[symbol] = (results[-1], failures[failure_start:])

    timings['total_scoring'] = perf_counter() - started
    return DiscoveryResult(
        timings=timings,
        calls=calls,
        as_of=as_of,
        requested=len(names),
        attempted=attempted,
        returned=len(results),
        tickers=tuple(results),
        failures=tuple(failures),
        universe=universe,
        sections=sections,
        market_cap_as_of=market_cap_as_of,
        source_failures=source_failures,
    )


def discover_stocks(tickers: Sequence[str]) -> DiscoveryResult:
    """Score up to ten supplied US stock tickers with the current style helpers.

    Inputs are fully validated before any provider is called. Provider failures
    are isolated by source and ticker; styles with unavailable inputs abstain.
    The returned ticker records keep the caller's order and are not ranked.
    """
    return _score_tickers(_validated_tickers(tickers))


def discover_nasdaq100() -> DiscoveryResult:
    """Score the constituents in the current dated public Nasdaq-100 source."""
    universe = fetch_nasdaq100_universe()
    return _score_tickers(_normalize_tickers(universe.tickers), universe)
