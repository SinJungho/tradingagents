"""Yahoo Finance market-cap snapshots used to divide the US equity universe."""

from __future__ import annotations

from datetime import UTC, datetime

import yfinance as yf
from yfinance import EquityQuery

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo.common import yf_retry

# Yahoo serves at most 10,000 screener rows; offsets past that repeat the last page. All US
# equities (OTC included) now exceed it, so screen only the exchanges the listing universe uses.
LISTED_EXCHANGES = ("NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS")
SCREENER_ROW_LIMIT = 10_000


def market_cap_snapshot() -> tuple[dict[str, int], str]:
    """Fetch current US equity market caps in bounded 250-row pages."""
    query = EquityQuery("and", [EquityQuery("eq", ["region", "us"]),
                                EquityQuery("is-in", ["exchange", *LISTED_EXCHANGES])])
    caps: dict[str, int] = {}
    seen: set[str] = set()
    offset = 0
    total = None
    as_of = datetime.now(UTC).isoformat(timespec="seconds")
    while total is None or offset < total:
        try:
            page = yf_retry(lambda offset=offset: yf.screen(
                query,
                offset=offset,
                size=250,
                sortField="ticker",
                sortAsc=True,
            ))
        except Exception as exc:
            raise VendorUnavailableError(
                f"Yahoo market-cap screener failed ({type(exc).__name__})"
            ) from None
        quotes = page.get("quotes") if isinstance(page, dict) else None
        page_total = page.get("total") if isinstance(page, dict) else None
        if not isinstance(quotes, list) or type(page_total) is not int or page_total <= 0:
            raise VendorUnavailableError("Yahoo market-cap screener returned an invalid page")
        if total is None:
            total = page_total
            if total > SCREENER_ROW_LIMIT:
                raise VendorUnavailableError(
                    f"Yahoo market-cap screener has {total} rows, above its {SCREENER_ROW_LIMIT} row paging limit"
                )
        elif page_total != total:
            raise VendorUnavailableError("Yahoo market-cap screener changed during pagination")
        if not quotes:
            raise VendorUnavailableError("Yahoo market-cap screener ended before all pages were read")
        for quote in quotes:
            if not isinstance(quote, dict) or not isinstance(quote.get("symbol"), str):
                raise VendorUnavailableError("Yahoo market-cap screener returned an invalid quote")
            symbol = quote["symbol"].strip().upper()
            if not symbol or symbol in seen:
                raise VendorUnavailableError("Yahoo market-cap screener repeated a symbol")
            seen.add(symbol)
            value = quote.get("marketCap")
            if value is None:
                value = quote.get("intradayMarketCap")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                caps[symbol.replace(".", "-")] = int(value)
        offset += len(quotes)
        if len(quotes) > 250 or (offset < total and len(quotes) < 250):
            raise VendorUnavailableError("Yahoo market-cap screener returned an incomplete page")
    return caps, as_of
