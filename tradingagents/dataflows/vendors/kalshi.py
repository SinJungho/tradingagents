"""Read-only public prediction-market data from Kalshi."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import requests

from tradingagents.api_diagnostics import classify_api_failure
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import (
    record_source_failure,
    source_circuit_error,
    trip_source_circuit,
)
from tradingagents.dataflows.net import get_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
REQUEST_TIMEOUT = 15
DEFAULT_LIMIT = 6
MAX_SERIES = 3
MARKETS_PER_SERIES = 100
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "will", "what", "when", "who"}


def _unavailable_message(topic: str) -> str:
    return (
        f"Kalshi data is unavailable for '{topic}'. Do not write, invent, or "
        "estimate prediction-market odds or numbers; explicitly state that this "
        "source is unavailable."
    )


def _request(path: str, params: dict) -> dict:
    response = get_with_retry(
        f"{BASE_URL}/{path}",
        params=params,
        timeout=REQUEST_TIMEOUT,
        provider="Kalshi",
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Kalshi returned an unexpected response")
    return payload


def _terms(value: str) -> set[str]:
    return {
        token for token in _TOKEN.findall(value.lower())
        if token not in _STOP_WORDS and (len(token) > 1 or token.isdigit())
    }


def _series_score(series: dict, query_terms: set[str]) -> int:
    text = " ".join([
        str(series.get("title", "")),
        str(series.get("category", "")),
        " ".join(str(tag) for tag in series.get("tags", []) if tag),
        " ".join(str(category) for category in series.get("categories", []) if category),
    ])
    return len(_terms(text) & query_terms)


def _price(market: dict) -> tuple[float, str, str] | None:
    """Return a YES price in dollars, preferring current quotes over last trade."""
    try:
        bid = float(market.get("yes_bid_dollars"))
        ask = float(market.get("yes_ask_dollars"))
    except (TypeError, ValueError):
        bid = ask = -1
    if 0 <= bid <= ask <= 1 and (bid > 0 or ask > 0):
        midpoint = (bid + ask) / 2
        return midpoint, "YES bid-ask midpoint", f"bid ${bid:.4f}, ask ${ask:.4f}"

    try:
        last = float(market.get("last_price_dollars"))
    except (TypeError, ValueError):
        return None
    if 0 <= last <= 1:
        return last, "last trade", f"last trade ${last:.4f}"
    return None


def _is_open(market: dict, now: datetime) -> bool:
    if market.get("status") not in (None, "open"):
        return False
    close_time = market.get("close_time") or market.get("expected_expiration_time")
    if not close_time:
        return True
    try:
        closes = datetime.fromisoformat(str(close_time).replace("Z", "+00:00"))
    except ValueError:
        return False
    if closes.tzinfo is None:
        closes = closes.replace(tzinfo=UTC)
    return closes > now


def _volume(market: dict) -> float:
    try:
        return float(market.get("volume_fp") or 0)
    except (TypeError, ValueError):
        return 0.0


def get_prediction_markets(
    topic: str,
    limit: int | None = None,
    as_of_date: str | None = None,
) -> str:
    """Return matching open Kalshi markets from a bounded set of series.

    Kalshi's public API supports series discovery and filtering by series
    ticker, but not arbitrary text search. We match the requested topic against
    series titles/tags, then inspect at most ``MAX_SERIES`` pages of markets.
    """
    if is_historical(as_of_date):
        return (
            f"Prediction-market prices are withheld for {as_of_date}. Kalshi "
            "serves current prices here; no historical vintage is queried, so "
            "current prices cannot be used in a past-date analysis."
        )

    if limit is None:
        limit = DEFAULT_LIMIT
    limit = max(1, min(int(limit), DEFAULT_LIMIT))

    circuit_error = source_circuit_error("get_prediction_markets")
    if circuit_error is not None:
        record_source_failure("get_prediction_markets", circuit_error)
        return _unavailable_message(topic)

    try:
        series_payload = _request("series", {})
        series_rows = series_payload.get("series")
        if not isinstance(series_rows, list):
            raise ValueError("Kalshi response did not contain a series list")
        query_terms = _terms(topic)
        ranked_series = sorted(
            (
                (score, series)
                for series in series_rows
                if isinstance(series, dict)
                and (score := _series_score(series, query_terms)) > 0
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:MAX_SERIES]

        markets = []
        for _, series in ranked_series:
            ticker = series.get("ticker")
            if not ticker:
                continue
            payload = _request(
                "markets",
                {"series_ticker": ticker, "status": "open", "limit": MARKETS_PER_SERIES},
            )
            market_rows = payload.get("markets")
            if not isinstance(market_rows, list):
                raise ValueError("Kalshi response did not contain a markets list")
            for market in market_rows:
                if isinstance(market, dict):
                    markets.append((series, market))
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning(
            "API fetch failed provider=Kalshi host=external-api.kalshi.com category=%s",
            classify_api_failure(error).category,
        )
        record_source_failure("get_prediction_markets", error)
        if isinstance(error, (requests.ConnectionError, requests.Timeout)):
            trip_source_circuit("get_prediction_markets", error)
        return _unavailable_message(topic)

    now = datetime.now(UTC)
    candidates = [
        (series, market)
        for series, market in markets
        if _is_open(market, now) and _price(market) is not None
    ]
    candidates.sort(
        key=lambda row: _volume(row[1]),
        reverse=True,
    )
    retrieved_at = now.strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f'## Kalshi prediction markets: "{topic}"\n'
        f"Displayed YES percentages are dollar prices multiplied by 100; they are "
        f"market-implied prices, not reliable forecasts. "
        f"Source: Kalshi public market-data API; retrieved {retrieved_at}.\n"
        f"Search scope: title/category/tag-matched series, up to {MAX_SERIES} "
        f"series and {MARKETS_PER_SERIES} open markets per series.\n\n"
    )
    if not candidates:
        return header + (
            "No matching open markets were found in the limited candidate "
            "series searched. This does not establish that Kalshi has no market "
            "on the topic. Do not estimate odds."
        )

    lines = []
    for series, market in candidates[:limit]:
        priced = _price(market)
        if priced is None:
            continue
        price, method, basis = priced
        percent = f"{price * 100:.4f}".rstrip("0").rstrip(".")
        title = market.get("title") or market.get("subtitle") or series.get("title") or "Untitled market"
        ticker = market.get("ticker", "unknown ticker")
        volume = market.get("volume_fp")
        volume_text = f", {_volume(market):,.0f} contracts traded" if volume is not None else ""
        closes = (market.get("close_time") or market.get("expected_expiration_time") or "")[:10]
        close_text = f", closes {closes}" if closes else ""
        lines.append(
            f"- **{title}** — YES {percent}% ({method}: {basis}; "
            f"${price:.4f} × 100 = {percent}%; Kalshi market `{ticker}`"
            f"{volume_text}{close_text})"
        )
    return header + "\n".join(lines) + "\n"
