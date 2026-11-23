"""Raw Yahoo daily bars for deterministic chart-zone calculations."""

from datetime import timedelta

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.errors import NoMarketDataError, record_source_failure
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry


def get_chart_history(symbol: str, *, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV without dividend adjustment or gap filling."""
    canonical = normalize_symbol(symbol)
    end_exclusive = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        frame = yf_retry(lambda: yf.Ticker(canonical).history(
            start=start, end=end_exclusive, interval="1d", auto_adjust=False, actions=True
        ))
        if frame is None or frame.empty:
            raise_for_empty(symbol, canonical, "daily chart bars")
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
        frame.index.name = "Date"
        if frame.index.has_duplicates:
            raise NoMarketDataError(symbol, canonical, "duplicate daily bars")
        return frame.sort_index()
    except Exception as exc:
        record_source_failure("get_chart_history", exc)
        raise


def get_earnings_dates(symbol: str) -> list[pd.Timestamp]:
    """Recent Yahoo earnings timestamps in US/Eastern, newest first."""
    canonical = normalize_symbol(symbol)
    try:
        frame = yf_retry(lambda: yf.Ticker(canonical).get_earnings_dates(limit=12))
        if frame is None or frame.empty:
            raise_for_empty(symbol, canonical, "earnings dates")
        index = pd.to_datetime(frame.index)
        index = index.tz_localize("America/New_York") if index.tz is None else index.tz_convert("America/New_York")
        return sorted(index, reverse=True)
    except Exception as exc:
        record_source_failure("get_earnings_dates", exc)
        raise
