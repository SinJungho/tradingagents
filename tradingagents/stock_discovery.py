"""Current deterministic style scores for supplied tickers or Nasdaq-100."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

import pandas as pd
import requests

from tradingagents import __version__
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.net import get_with_retry
from tradingagents.dataflows.vendors.yahoo.market import get_splits
from tradingagents.style_scores import StyleScore, StyleSignal, _closes, _facts, score_styles

MAX_TICKERS = 10
_TICKER = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?$")
NASDAQ100_SOURCE = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
_NASDAQ100_AS_OF = re.compile(
    r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the index comprised (\d+) securities issued by (\d+) companies"
)


class Nasdaq100UniverseError(ValueError):
    """The public Nasdaq-100 universe source could not be validated."""


@dataclass(frozen=True)
class DiscoveryUniverse:
    name: str
    source: str
    as_of: str
    tickers: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryFailure:
    ticker: str
    source: str
    reason: str


@dataclass(frozen=True)
class DiscoveredTicker:
    ticker: str
    scores: dict[str, StyleScore]


@dataclass(frozen=True)
class DiscoveryResult:
    as_of: str
    requested: int
    attempted: int
    returned: int
    tickers: tuple[DiscoveredTicker, ...]
    failures: tuple[DiscoveryFailure, ...]
    universe: DiscoveryUniverse | None = None

    def render(self) -> str:
        if self.universe:
            lines = [
                f"Deterministic style scores for {self.universe.name} constituents",
                f"Data as of: {self.as_of}",
                f"Universe: {self.universe.name}; membership as of {self.universe.as_of}; "
                f"securities={len(self.universe.tickers)}",
                f"Universe source: {self.universe.source}",
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
        return DiscoveryUniverse("Nasdaq-100", NASDAQ100_SOURCE, as_of, tuple(tickers))

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


def _score_tickers(
    names: tuple[str, ...], universe: DiscoveryUniverse | None = None
) -> DiscoveryResult:
    as_of = get_current_date()
    results: list[DiscoveredTicker] = []
    failures: list[DiscoveryFailure] = []
    attempted = 0

    for ticker in names:
        attempted += 1
        try:
            closes = _closes(ticker)
        except NoMarketDataError:
            closes = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        except Exception as exc:
            closes = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            failures.append(_failure(ticker, "Yahoo Finance price history", exc))

        try:
            facts = _facts(ticker, as_of)
        except NoMarketDataError:
            facts = None
        except Exception as exc:
            facts = None
            failures.append(_failure(ticker, "SEC EDGAR annual facts", exc))

        splits_available = True
        try:
            splits = get_splits(ticker)
        except NoMarketDataError:
            splits = None
            splits_available = False
        except Exception as exc:
            splits = None
            splits_available = False
            failures.append(_failure(ticker, "Yahoo Finance split history", exc))

        try:
            scores = score_styles(as_of, closes, facts, splits)
        except Exception as exc:
            failures.append(_failure(ticker, "style scoring", exc))
            continue

        if not splits_available:
            missing = tuple(dict.fromkeys((*scores["value"].missing, "split history")))
            scores["value"] = StyleScore(
                "value", StyleSignal.ABSTAIN, None, missing=missing
            )
        results.append(DiscoveredTicker(ticker, scores))

    return DiscoveryResult(
        as_of=as_of,
        requested=len(names),
        attempted=attempted,
        returned=len(results),
        tickers=tuple(results),
        failures=tuple(failures),
        universe=universe,
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
