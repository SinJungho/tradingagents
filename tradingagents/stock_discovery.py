"""Current deterministic style scores for a user-supplied ticker list."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo.market import get_splits
from tradingagents.style_scores import StyleScore, StyleSignal, _closes, _facts, score_styles

MAX_TICKERS = 10
_TICKER = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?$")


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

    def render(self) -> str:
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


def discover_stocks(tickers: Sequence[str]) -> DiscoveryResult:
    """Score up to ten supplied US stock tickers with the current style helpers.

    Inputs are fully validated before any provider is called. Provider failures
    are isolated by source and ticker; styles with unavailable inputs abstain.
    The returned ticker records keep the caller's order and are not ranked.
    """
    names = _validated_tickers(tickers)
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
    )
