"""The data tools the analysts call.

Each dated tool takes the run's ``trade_date`` from graph state (``InjectedState``)
and never serves data past it, whatever date the model asks for.
"""

from datetime import datetime, timedelta
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from tradingagents.dataflows.date_window import as_of, as_of_window, get_current_date
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.router import no_data_available, route_to_vendor, vendor_unavailable
from tradingagents.dataflows.vendors.yahoo.snapshot import build_verified_market_snapshot

_DEFAULT_TECHNICAL_INDICATORS = "close_50_sma,close_200_sma,macdh,rsi,atr"
_DEFAULT_MACRO_INDICATORS = "cpi,core_pce,unemployment,fed_funds_rate,10y_treasury,yield_curve"


def _run_date(requested: str | None, trade_date: str) -> str:
    reference = trade_date or get_current_date()
    return as_of(requested or reference, reference) or reference


def _run_window(
    start_date: str | None,
    end_date: str | None,
    trade_date: str,
    *,
    look_back_days: int,
) -> tuple[str, str]:
    reference = trade_date or get_current_date()
    end = _run_date(end_date, reference)
    if not start_date:
        start_date = (
            datetime.strptime(end, "%Y-%m-%d") - timedelta(days=look_back_days)
        ).strftime("%Y-%m-%d")
    return as_of_window(start_date, end, reference)


@tool
def get_stock_data(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    start_date: Annotated[str | None, "Start date in yyyy-mm-dd format; defaults to one year before the run date"] = None,
    end_date: Annotated[str | None, "End date in yyyy-mm-dd format; defaults to the run date"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve stock price data (OHLCV) for the instrument under analysis.
    Uses the configured core_stock_apis vendor.
    Args:
        start_date (str): Start date in yyyy-mm-dd format; defaults to one year before the run date
        end_date (str): End date in yyyy-mm-dd format; defaults to the run date
    Returns:
        str: A formatted dataframe containing the price data for the instrument over the date range.
    """
    try:
        start_date, end_date = _run_window(
            start_date, end_date, trade_date, look_back_days=365
        )
    except ValueError as e:
        return str(e)
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)


@tool
def get_indicators(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    indicator: Annotated[
        str | None, "Technical indicator names; omit to retrieve the standard indicator bundle"
    ] = None,
    curr_date: Annotated[str | None, "The current trading date, YYYY-mm-dd; defaults to the run date"] = None,
    look_back_days: Annotated[int, "how many days to look back"] = 30,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve a single technical indicator for the instrument under analysis.
    Uses the configured technical_indicators vendor.
    Args:
        indicator (str): A single technical indicator name, e.g. 'rsi', 'macd'. Call this tool once per indicator.
        curr_date (str): The run's analysis date; defaults to the injected trade date
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted dataframe containing the technical indicators for the instrument and indicator.
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    curr_date = _run_date(curr_date, trade_date)
    indicators = [i.strip().lower() for i in (indicator or _DEFAULT_TECHNICAL_INDICATORS).split(",") if i.strip()]
    if not indicators:
        indicators = _DEFAULT_TECHNICAL_INDICATORS.split(",")
    results = []
    for ind in indicators:
        try:
            results.append(route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)


@tool
def get_verified_market_snapshot(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str | None, "The current trading date, YYYY-mm-dd; defaults to the run date"] = None,
    look_back_days: Annotated[
        int, "number of recent trading rows to include for sanity-checking"
    ] = 30,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """Deterministic verification snapshot for exact market-data claims.

    Returns the latest OHLCV row on or before curr_date, common technical
    indicators, and recent closes. Call this before making exact claims about
    price levels, Bollinger bands, RSI, MACD, moving averages, support /
    resistance, or historical comparisons, and treat it as the source of truth.
    """
    # An exception out of a tool would end the run.
    try:
        return build_verified_market_snapshot(symbol, _run_date(curr_date, trade_date), look_back_days)
    except VendorUnavailableError as exc:
        return vendor_unavailable("get_verified_market_snapshot", exc)
    except NoMarketDataError as exc:
        return no_data_available(exc)


@tool
def get_fundamentals(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str | None, "Analysis date, yyyy-mm-dd; defaults to the run date"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve comprehensive fundamental data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        curr_date (str): Analysis date; defaults to the injected trade date
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    return route_to_vendor("get_fundamentals", ticker, _run_date(curr_date, trade_date))


@tool
def get_balance_sheet(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[Literal["annual", "quarterly"], "reporting frequency"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve balance sheet data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Analysis date; defaults to the injected trade date
    Returns:
        str: A formatted report containing balance sheet data
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, _run_date(curr_date, trade_date))


@tool
def get_cashflow(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[Literal["annual", "quarterly"], "reporting frequency"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve cash flow statement data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Analysis date; defaults to the injected trade date
    Returns:
        str: A formatted report containing cash flow statement data
    """
    return route_to_vendor("get_cashflow", ticker, freq, _run_date(curr_date, trade_date))


@tool
def get_income_statement(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[Literal["annual", "quarterly"], "reporting frequency"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve income statement data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    return route_to_vendor("get_income_statement", ticker, freq, _run_date(curr_date, trade_date))


@tool
def get_news(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    start_date: Annotated[str | None, "Start date in yyyy-mm-dd format; defaults to seven days before the run date"] = None,
    end_date: Annotated[str | None, "End date in yyyy-mm-dd format; defaults to the run date"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve news data for the instrument under analysis.
    Uses the configured news_data vendor.
    Args:
        start_date (str): Start date in yyyy-mm-dd format; defaults to seven days before the run date
        end_date (str): End date in yyyy-mm-dd format; defaults to the run date
    Returns:
        str: A formatted string containing news data
    """
    try:
        start_date, end_date = _run_window(
            start_date, end_date, trade_date, look_back_days=7
        )
    except ValueError as e:
        return str(e)
    return route_to_vendor("get_news", ticker, start_date, end_date)


@tool
def get_global_news(
    curr_date: Annotated[str | None, "Current date in yyyy-mm-dd format; defaults to the run date"] = None,
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format; defaults to the run date
        look_back_days (int): Number of days to look back; omit to inherit config
        limit (int): Maximum number of articles to return; omit to inherit config

    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", _run_date(curr_date, trade_date), look_back_days, limit)


@tool
def get_insider_transactions(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker, trade_date or None)


@tool
def get_macro_indicators(
    indicator: Annotated[
        str | None,
        "Macro indicator: a friendly alias such as 'cpi', 'core_pce', "
        "'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve', "
        "'real_gdp', 'vix'; omit to retrieve the standard US macro bundle; "
        "euro-area aliases include 'ecb_deposit_rate', "
        "'euro_hicp', 'euro_core_hicp', 'euro_real_gdp', 'germany_10y', "
        "'france_10y', 'eur_usd', or a raw FRED series ID such as 'CPIAUCSL'.",
    ] = None,
    curr_date: Annotated[str | None, "Current date in yyyy-mm-dd format; defaults to the run date"] = None,
    look_back_days: Annotated[
        int | None, "Trailing window length in days; omit for a 1-year window"
    ] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve a macroeconomic indicator time series from FRED (Federal Reserve
    Economic Data): policy rates, Treasury yields, inflation, labor, and growth,
    for the US and, through FRED's mirrored series, the euro area.
    Returns the series title, units, frequency, the latest value, the change
    over the window, and a recent observation table. Uses the configured
    macro_data vendor.

    Args:
        indicator (str): Friendly alias or raw FRED series ID; defaults to a standard US macro bundle
        curr_date (str): Current date in yyyy-mm-dd format; defaults to the run date
        look_back_days (int): Trailing window length; omit for a 1-year window

    Returns:
        str: A formatted markdown report of the macro series
    """
    indicators = [
        value.strip()
        for value in (indicator or _DEFAULT_MACRO_INDICATORS).split(",")
        if value.strip()
    ] or _DEFAULT_MACRO_INDICATORS.split(",")
    current = _run_date(curr_date, trade_date)
    return "\n\n".join(
        route_to_vendor("get_macro_indicators", name, current, look_back_days)
        for name in indicators
    )


@tool
def get_prediction_markets(
    topic: Annotated[
        str | None,
        "Event topic/keyword, e.g. 'Fed rate cut', 'recession 2026', "
        "'US election', or a sector/company event; defaults to Fed rate policy.",
    ] = None,
    limit: Annotated[int | None, "Max markets to return; omit for a default of 6"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve live, market-implied prices for forward-looking events from the
    configured prediction-market vendor (Kalshi by default, Polymarket when
    selected in config). Returns open markets matching the topic, with source,
    retrieval time, traded volume and close date. Search coverage is bounded;
    no matches do not establish that no market exists.

    Args:
        topic (str): Event keyword(s) to search; defaults to Fed rate policy
        limit (int): Max markets to return; omit for a default of 6

    Returns:
        str: A formatted markdown report of matching prediction markets
    """
    return route_to_vendor("get_prediction_markets", topic or "Fed rate cut", limit, trade_date or get_current_date())
