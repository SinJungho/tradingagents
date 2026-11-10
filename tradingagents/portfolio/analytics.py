"""Deterministic portfolio summaries over normalized provider data."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from tradingagents.portfolio.models import BuyingPower, Holding, Holdings, Order, Orders

_DECIMAL_PRECISION = 28
_US_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.-]*$")
_TOSS_HOLDINGS_SCOPE_WARNING = (
    "Toss holdings cover KR and US stocks; overseas options and bonds are excluded."
)
_KR_EXCHANGE_SUFFIX = {
    "KRX": ".KS",
    "KOSPI": ".KS",
    "KSE": ".KS",
    "KOSDAQ": ".KQ",
    "KQ": ".KQ",
    "KSQ": ".KQ",
}


@dataclass(frozen=True)
class SourceMetadata:
    source: str
    retrieved_at: datetime | None
    as_of: datetime | None
    coverage_warnings: tuple[str, ...]
    available: bool


@dataclass(frozen=True)
class FXMetadata:
    rate: Decimal | None
    timestamp: datetime | None
    source_currency: str
    target_currency: str
    applied: bool
    stale: bool | None


@dataclass(frozen=True)
class PositionAnalytics:
    symbol: str
    provider_symbol: str | None
    market_country: str | None
    currency: str | None
    quantity: Decimal
    last_price: Decimal | None
    market_value: Decimal | None
    market_value_source: str | None
    purchase_amount: Decimal | None
    purchase_amount_source: str | None
    profit_loss: Decimal | None
    profit_loss_source: str | None
    profit_loss_after_cost: Decimal | None
    profit_loss_after_cost_source: str | None
    security_weight: Decimal | None
    currency_portfolio_weight: Decimal | None
    retrieved_at: datetime | None
    stale: bool | None
    included_in_totals: bool
    unknowns: tuple[str, ...]


@dataclass(frozen=True)
class BuyingPowerAnalytics:
    currency: str
    buying_power: Decimal
    currency_portfolio_weight: Decimal | None
    retrieved_at: datetime | None
    stale: bool | None
    included_in_totals: bool
    unknowns: tuple[str, ...]


@dataclass(frozen=True)
class CurrencyAnalytics:
    """Currency totals; completeness covers represented positions and supplied buying power."""

    currency: str
    market_value_total: Decimal | None
    purchase_amount_total: Decimal | None
    profit_loss_total: Decimal | None
    profit_loss_after_cost_total: Decimal | None
    buying_power_total: Decimal | None
    total_value_with_buying_power: Decimal | None
    market_value_complete: bool
    purchase_amount_complete: bool
    profit_loss_complete: bool
    profit_loss_after_cost_complete: bool
    buying_power_complete: bool
    represented_scope_complete: bool
    position_count: int
    market_value_missing_count: int
    purchase_amount_missing_count: int
    profit_loss_missing_count: int


@dataclass(frozen=True)
class Concentration:
    dimension: str
    key: str | None
    currency: str | None
    value: Decimal | None
    weight: Decimal | None


@dataclass(frozen=True)
class OrderStateSummary:
    status: str | None
    count: int
    ordered_quantity_total: Decimal | None
    ordered_quantity_missing_count: int
    filled_quantity_total: Decimal | None
    filled_quantity_missing_count: int


@dataclass(frozen=True)
class OrderSideSummary:
    side: str | None
    count: int


@dataclass(frozen=True)
class OrderAnalytics:
    count: int
    by_status: tuple[OrderStateSummary, ...]
    by_side: tuple[OrderSideSummary, ...]
    ordered_quantity_total: Decimal | None
    ordered_quantity_missing_count: int
    filled_quantity_total: Decimal | None
    filled_quantity_missing_count: int
    retrieved_at: datetime | None
    record_retrieved_at: tuple[datetime | None, ...]
    stale: bool | None
    has_more: bool
    coverage_warnings: tuple[str, ...]
    source_scope: str = "provider_returned_records"


@dataclass(frozen=True)
class ConvertedTotals:
    currency: str
    market_value_total: Decimal | None
    purchase_amount_total: Decimal | None
    profit_loss_total: Decimal | None
    buying_power_total: Decimal | None
    portfolio_value_total: Decimal | None


@dataclass(frozen=True)
class PortfolioAnalytics:
    positions: tuple[PositionAnalytics, ...]
    buying_power: tuple[BuyingPowerAnalytics, ...]
    currencies: tuple[CurrencyAnalytics, ...]
    concentration_by_symbol: tuple[Concentration, ...]
    concentration_by_market: tuple[Concentration, ...]
    concentration_by_currency: tuple[Concentration, ...]
    orders: OrderAnalytics | None
    converted_totals: ConvertedTotals | None
    fx: FXMetadata | None
    sources: tuple[SourceMetadata, ...]
    coverage_warnings: tuple[str, ...]
    account_wide_coverage: str
    unknowns: tuple[str, ...]


def map_market_symbol(symbol: str, market_country: str | None, exchange: str | None) -> str | None:
    """Map only recognized KR codes and syntactically safe US tickers."""
    raw = symbol.strip()
    country = (market_country or "").strip().upper()
    if country == "KR" and re.fullmatch(r"[0-9]{6}", raw):
        suffix = _KR_EXCHANGE_SUFFIX.get((exchange or "").strip().upper())
        return f"{raw}{suffix}" if suffix else None
    if country == "US":
        candidate = raw.upper()
        if _US_SYMBOL.fullmatch(candidate) and any(char.isalpha() for char in candidate):
            return candidate
    return None


def analyze_portfolio(
    holdings: Holdings | None = None,
    buying_power: Sequence[BuyingPower] | None = None,
    orders: Orders | None = None,
    *,
    fx_rate: Decimal | None = None,
    fx_timestamp: datetime | None = None,
    fx_source_currency: str = "KRW",
    fx_target_currency: str = "USD",
    as_of: datetime | None = None,
    stale_after: timedelta | None = None,
) -> PortfolioAnalytics:
    """Summarize known values without filling gaps or treating orders as a ledger.

    ``fx_rate`` is target-currency units per one source-currency unit. Currency
    defaults cover the broker's KRW/USD pair; callers can state another pair.
    Freshness is checked only when both ``as_of`` and ``stale_after`` are given.
    """
    if stale_after is not None and (as_of is None or stale_after < timedelta(0)):
        raise ValueError("stale_after requires as_of and cannot be negative")
    if fx_rate is not None and not isinstance(fx_rate, Decimal):
        raise TypeError("fx_rate must be a Decimal")
    if fx_rate is not None and (not fx_rate.is_finite() or fx_rate <= 0):
        raise ValueError("fx_rate must be finite and positive")
    if fx_timestamp is not None and not isinstance(fx_timestamp, datetime):
        raise TypeError("fx_timestamp must be a datetime")

    buying_power_inputs = tuple(buying_power or ())
    fx_source_currency = fx_source_currency.strip().upper()
    fx_target_currency = fx_target_currency.strip().upper()
    if (fx_rate is not None or fx_timestamp is not None) and not (
        fx_source_currency and fx_target_currency
    ):
        raise ValueError("FX source and target currencies must be non-empty")
    fx_stale = _stale(fx_timestamp, as_of, stale_after)
    fx_applied = (
        fx_rate is not None
        and fx_timestamp is not None
        and fx_source_currency != fx_target_currency
        and (stale_after is None or fx_stale is False)
    )
    fx = (
        FXMetadata(
            fx_rate,
            fx_timestamp,
            fx_source_currency,
            fx_target_currency,
            fx_applied,
            fx_stale,
        )
        if fx_rate is not None or fx_timestamp is not None
        else None
    )

    sources = (
        SourceMetadata(
            "holdings",
            holdings.retrieved_at if holdings else None,
            holdings.as_of if holdings else None,
            holdings.coverage_warnings if holdings else (),
            holdings is not None,
        ),
        *(
            SourceMetadata(
                f"buying_power:{item.currency}",
                item.retrieved_at,
                None,
                item.coverage_warnings,
                True,
            )
            for item in buying_power_inputs
        ),
        SourceMetadata(
            "orders",
            orders.retrieved_at if orders else None,
            None,
            orders.coverage_warnings if orders else (),
            orders is not None,
        ),
    )
    coverage_warnings = tuple(
        f"{source.source}: {warning}"
        for source in sources
        for warning in source.coverage_warnings
    )
    unknowns: list[str] = []
    if holdings is None:
        unknowns.append("Holdings were not supplied; position values and weights are unknown.")
    elif not holdings.holdings:
        unknowns.append("No positions were returned; this is not a numeric zero market value.")
    if not buying_power_inputs:
        unknowns.append("Buying power was not supplied; cash-like value and weights are unknown.")
    if orders is None:
        unknowns.append("Orders were not supplied; order activity is unknown.")
    else:
        unknowns.append(
            "Order summaries cover provider-returned records only; they do not establish intent, realized P&L, or a complete ledger."
        )
        if orders.has_more:
            unknowns.append("The provider reports more order records than were returned.")
    if fx is not None:
        if fx.rate is None or fx.timestamp is None:
            unknowns.append("FX conversion was not applied because both a rate and timestamp are required.")
        elif fx.source_currency == fx.target_currency:
            unknowns.append("FX conversion was not applied because source and target currencies match.")
        elif not fx.applied:
            unknowns.append("FX conversion was omitted because its timestamp is stale or unknown.")

    position_data: list[dict[str, object]] = []
    for item in holdings.holdings if holdings else ():
        market_value, market_value_source = _market_value(item)
        purchase_amount, purchase_amount_source = _purchase_amount(item)
        profit_loss, profit_loss_source = _profit_loss(item, market_value, purchase_amount)
        profit_loss_after_cost, after_cost_source = _profit_loss_after_cost(item, purchase_amount)
        timestamp = item.retrieved_at or (holdings.retrieved_at if holdings else None)
        stale = _stale(timestamp, as_of, stale_after)
        fresh_enough = stale_after is None or (timestamp is not None and stale is False)
        currency = _clean_currency(item.currency)
        provider_symbol = map_market_symbol(item.symbol, item.market_country, item.exchange)
        reasons: list[str] = []
        if provider_symbol is None:
            reasons.append("No supported market-symbol mapping is known.")
        if currency is None:
            reasons.append("Currency is missing; this position cannot be aggregated by currency.")
        if market_value is None:
            reasons.append("Market value is unknown because no reported value or price is available.")
        if purchase_amount is None:
            reasons.append("Purchase amount is unknown because no reported amount or average price is available.")
        if profit_loss is None:
            reasons.append("Profit/loss is unknown because its source values are incomplete.")
        if stale is True:
            reasons.append("Position values are stale for the requested as-of time.")
        elif stale_after is not None and timestamp is None:
            reasons.append("Freshness is unknown because the source timestamp is missing.")
        elif stale_after is not None and stale is None:
            reasons.append("Freshness is unknown because the source timestamp cannot be compared.")
        included = currency is not None and fresh_enough
        if not fresh_enough:
            reasons.append("Market value is retained but excluded from currency totals.")
        position_data.append(
            {
                "item": item,
                "market_value": market_value,
                "market_value_source": market_value_source,
                "purchase_amount": purchase_amount,
                "purchase_amount_source": purchase_amount_source,
                "profit_loss": profit_loss,
                "profit_loss_source": profit_loss_source,
                "profit_loss_after_cost": profit_loss_after_cost,
                "profit_loss_after_cost_source": after_cost_source,
                "timestamp": timestamp,
                "stale": stale,
                "fresh_enough": fresh_enough,
                "currency": currency,
                "provider_symbol": provider_symbol,
                "included": included,
                "unknowns": reasons,
            }
        )

    currency_keys = {
        data["currency"] for data in position_data if data["currency"] is not None
    } | {_clean_currency(item.currency) for item in buying_power_inputs}
    currency_keys.discard(None)
    holdings_warnings = holdings.coverage_warnings if holdings else ()
    account_wide_coverage = "partial" if holdings_warnings else "unknown"
    source_has_warnings = any(
        warning != _TOSS_HOLDINGS_SCOPE_WARNING for warning in holdings_warnings
    )
    unknown_market_positions = any(data["currency"] is None for data in position_data)

    bp_data: list[dict[str, object]] = []
    for item in buying_power_inputs:
        currency = _clean_currency(item.currency)
        stale = _stale(item.retrieved_at, as_of, stale_after)
        fresh_enough = stale_after is None or (item.retrieved_at is not None and stale is False)
        reasons = []
        if currency is None:
            reasons.append("Currency is missing; buying power cannot be aggregated.")
        if stale is True:
            reasons.append("Buying power is stale for the requested as-of time.")
        elif stale_after is not None and item.retrieved_at is None:
            reasons.append("Freshness is unknown because the source timestamp is missing.")
        elif stale_after is not None and stale is None:
            reasons.append("Freshness is unknown because the source timestamp cannot be compared.")
        included = currency is not None and fresh_enough
        if not included:
            reasons.append("Buying power is retained but excluded from currency totals.")
        bp_data.append(
            {
                "item": item,
                "currency": currency,
                "stale": stale,
                "included": included,
                "unknowns": reasons,
            }
        )

    currency_rows: list[CurrencyAnalytics] = []
    position_weights: dict[int, Decimal | None] = {}
    buying_power_weights: dict[int, Decimal | None] = {}
    for currency in sorted(currency_keys):
        positions = [data for data in position_data if data["currency"] == currency]
        cash_records = [data for data in bp_data if data["currency"] == currency]
        included_positions = [data for data in positions if data["included"]]
        included_cash = [data for data in cash_records if data["included"]]
        market_total = _sum_values(
            data["market_value"]
            for data in included_positions
            if data["market_value"] is not None
        )
        purchase_total = _sum_values(data["purchase_amount"] for data in included_positions)
        profit_total = _sum_values(data["profit_loss"] for data in included_positions)
        after_cost_total = _sum_values(
            data["profit_loss_after_cost"] for data in included_positions
        )
        bp_total = _sum_values(data["item"].cash_buying_power for data in included_cash)
        market_missing = sum(
            data["market_value"] is None or not data["fresh_enough"] for data in positions
        )
        purchase_missing = sum(
            data["purchase_amount"] is None or not data["fresh_enough"] for data in positions
        )
        profit_missing = sum(
            data["profit_loss"] is None or not data["fresh_enough"] for data in positions
        )
        bp_warnings = any(data["item"].coverage_warnings for data in cash_records)
        values_complete = (
            holdings is not None
            and not source_has_warnings
            and not unknown_market_positions
            and market_missing == 0
        )
        purchases_complete = (
            holdings is not None
            and not source_has_warnings
            and not unknown_market_positions
            and purchase_missing == 0
        )
        pnl_complete = (
            holdings is not None
            and not source_has_warnings
            and not unknown_market_positions
            and profit_missing == 0
        )
        after_cost_complete = (
            holdings is not None
            and not source_has_warnings
            and not unknown_market_positions
            and all(data["profit_loss_after_cost"] is not None and data["fresh_enough"] for data in positions)
        )
        bp_complete = (
            len(included_cash) == len(cash_records)
            and bool(cash_records)
            and not bp_warnings
        )
        if not cash_records:
            unknowns.append(
                f"No buying-power input was supplied for {currency}; cash-like value and portfolio weights are unknown."
            )
        elif not bp_complete:
            unknowns.append(
                f"Buying-power input for {currency} is incomplete or stale; portfolio weights are unknown."
            )
        total_complete = values_complete and bp_complete
        represented_scope_complete = total_complete
        portfolio_total = (
            _add(market_total, bp_total)
            if total_complete and (market_total is not None or not positions)
            else None
        )
        denom_security = market_total if values_complete else None
        denom_portfolio = portfolio_total if total_complete else None
        with localcontext() as context:
            context.prec = _DECIMAL_PRECISION
            for index, data in enumerate(position_data):
                if (
                    data["currency"] != currency
                    or not data["included"]
                    or data["market_value"] is None
                ):
                    continue
                position_weights[index] = _weight(data["market_value"], denom_security)
                # A reported empty holdings collection is known empty, not an unknown amount.
                position_weights[index + len(position_data)] = _weight(
                    data["market_value"], denom_portfolio
                )
            for index, data in enumerate(bp_data):
                if data["currency"] == currency and data["included"]:
                    buying_power_weights[index] = _weight(
                        data["item"].cash_buying_power, denom_portfolio
                    )
        currency_rows.append(
            CurrencyAnalytics(
                currency=currency,
                market_value_total=market_total,
                purchase_amount_total=purchase_total,
                profit_loss_total=profit_total,
                profit_loss_after_cost_total=after_cost_total,
                buying_power_total=bp_total,
                total_value_with_buying_power=portfolio_total,
                market_value_complete=values_complete,
                purchase_amount_complete=purchases_complete,
                profit_loss_complete=pnl_complete,
                profit_loss_after_cost_complete=after_cost_complete,
                buying_power_complete=bp_complete,
                represented_scope_complete=represented_scope_complete,
                position_count=len(positions),
                market_value_missing_count=market_missing,
                purchase_amount_missing_count=purchase_missing,
                profit_loss_missing_count=profit_missing,
            )
        )

    positions_out = tuple(
        PositionAnalytics(
            symbol=data["item"].symbol,
            provider_symbol=data["provider_symbol"],
            market_country=data["item"].market_country,
            currency=data["currency"],
            quantity=data["item"].quantity,
            last_price=data["item"].last_price,
            market_value=data["market_value"],
            market_value_source=data["market_value_source"],
            purchase_amount=data["purchase_amount"],
            purchase_amount_source=data["purchase_amount_source"],
            profit_loss=data["profit_loss"],
            profit_loss_source=data["profit_loss_source"],
            profit_loss_after_cost=data["profit_loss_after_cost"],
            profit_loss_after_cost_source=data["profit_loss_after_cost_source"],
            security_weight=position_weights.get(index),
            currency_portfolio_weight=position_weights.get(index + len(position_data)),
            retrieved_at=data["timestamp"],
            stale=data["stale"],
            included_in_totals=data["included"] and data["market_value"] is not None,
            unknowns=tuple(data["unknowns"]),
        )
        for index, data in enumerate(position_data)
    )
    buying_power_out = tuple(
        BuyingPowerAnalytics(
            currency=data["currency"] or data["item"].currency,
            buying_power=data["item"].cash_buying_power,
            currency_portfolio_weight=buying_power_weights.get(index),
            retrieved_at=data["item"].retrieved_at,
            stale=data["stale"],
            included_in_totals=data["included"],
            unknowns=tuple(data["unknowns"]),
        )
        for index, data in enumerate(bp_data)
    )

    concentration_by_symbol, concentration_by_market = _concentrations(
        position_data, currency_rows
    )
    usable_fx = fx if fx and fx.applied else None
    converted = _convert_totals(currency_rows, usable_fx)
    concentration_by_currency = _currency_concentrations(currency_rows, usable_fx)
    order_summary = _summarize_orders(orders, as_of, stale_after)

    if any(data["unknowns"] for data in position_data):
        unknowns.extend(
            f"{data['item'].symbol}: {reason}"
            for data in position_data
            for reason in data["unknowns"]
        )
    if any(data["unknowns"] for data in bp_data):
        unknowns.extend(
            f"buying_power:{data['item'].currency}: {reason}"
            for data in bp_data
            for reason in data["unknowns"]
        )

    return PortfolioAnalytics(
        positions=positions_out,
        buying_power=buying_power_out,
        currencies=tuple(currency_rows),
        concentration_by_symbol=concentration_by_symbol,
        concentration_by_market=concentration_by_market,
        concentration_by_currency=concentration_by_currency,
        orders=order_summary,
        converted_totals=converted,
        fx=fx,
        sources=sources,
        coverage_warnings=coverage_warnings,
        account_wide_coverage=account_wide_coverage,
        unknowns=tuple(unknowns),
    )


def _market_value(item: Holding) -> tuple[Decimal | None, str | None]:
    if item.market_value is not None:
        return item.market_value, "reported"
    if item.last_price is not None:
        with localcontext() as context:
            context.prec = _DECIMAL_PRECISION
            return item.quantity * item.last_price, "quantity_times_last_price"
    return None, None


def _purchase_amount(item: Holding) -> tuple[Decimal | None, str | None]:
    if item.purchase_amount is not None:
        return item.purchase_amount, "reported"
    if item.average_purchase_price is not None:
        with localcontext() as context:
            context.prec = _DECIMAL_PRECISION
            return item.quantity * item.average_purchase_price, "quantity_times_average_purchase_price"
    return None, None


def _profit_loss(
    item: Holding, market_value: Decimal | None, purchase_amount: Decimal | None
) -> tuple[Decimal | None, str | None]:
    if item.profit_loss is not None:
        return item.profit_loss, "reported"
    if market_value is not None and purchase_amount is not None:
        with localcontext() as context:
            context.prec = _DECIMAL_PRECISION
            return market_value - purchase_amount, "market_value_minus_purchase_amount"
    return None, None


def _profit_loss_after_cost(
    item: Holding, purchase_amount: Decimal | None
) -> tuple[Decimal | None, str | None]:
    if item.profit_loss_after_cost is not None:
        return item.profit_loss_after_cost, "reported"
    if item.market_value_after_cost is not None and purchase_amount is not None:
        with localcontext() as context:
            context.prec = _DECIMAL_PRECISION
            return item.market_value_after_cost - purchase_amount, "after_cost_value_minus_purchase_amount"
    return None, None


def _stale(
    timestamp: datetime | None, as_of: datetime | None, stale_after: timedelta | None
) -> bool | None:
    if as_of is None or stale_after is None or timestamp is None:
        return None
    try:
        return as_of - timestamp > stale_after
    except TypeError:
        return None


def _clean_currency(currency: str | None) -> str | None:
    return currency.strip().upper() if currency and currency.strip() else None


def _sum_values(values: Iterable[Decimal | None]) -> Decimal | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        return sum(known, Decimal(0))


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None and right is None:
        return None
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        return (left or Decimal(0)) + (right or Decimal(0))


def _weight(value: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if value is None or denominator in (None, Decimal(0)):
        return None
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        return value / denominator


def _concentrations(
    positions: list[dict[str, object]], currencies: Sequence[CurrencyAnalytics]
) -> tuple[tuple[Concentration, ...], tuple[Concentration, ...]]:
    rows_by_currency = {row.currency: row for row in currencies}
    symbol_totals: dict[tuple[str, str], list[Decimal]] = {}
    market_totals: dict[tuple[str | None, str], list[Decimal]] = {}
    for data in positions:
        if not data["included"]:
            continue
        currency = data["currency"]
        value = data["market_value"]
        if currency is None or value is None:
            continue
        item = data["item"]
        symbol_totals.setdefault((item.symbol, currency), []).append(value)
        market_totals.setdefault((item.market_country, currency), []).append(value)
    symbol_rows = tuple(
        Concentration(
            "symbol",
            symbol,
            currency,
            total := _sum_values(values),
            _weight(total, rows_by_currency[currency].market_value_total)
            if rows_by_currency[currency].market_value_complete
            else None,
        )
        for (symbol, currency), values in sorted(symbol_totals.items())
    )
    market_rows = tuple(
        Concentration(
            "market",
            market,
            currency,
            total := _sum_values(values),
            _weight(total, rows_by_currency[currency].market_value_total)
            if rows_by_currency[currency].market_value_complete
            else None,
        )
        for (market, currency), values in sorted(
            market_totals.items(), key=lambda pair: (pair[0][1], pair[0][0] or "")
        )
    )
    return symbol_rows, market_rows


def _currency_concentrations(
    currencies: Sequence[CurrencyAnalytics], fx: FXMetadata | None
) -> tuple[Concentration, ...]:
    weights = _converted_currency_weights(currencies, fx)
    return tuple(
        Concentration(
            "currency",
            row.currency,
            row.currency,
            row.total_value_with_buying_power,
            weights.get(row.currency),
        )
        for row in currencies
    )


def _converted_currency_weights(
    currencies: Sequence[CurrencyAnalytics], fx: FXMetadata | None
) -> dict[str, Decimal | None]:
    if fx is None or not fx.applied or fx.rate is None:
        return {}
    if len(currencies) < 2 or any(
        not row.represented_scope_complete for row in currencies
    ):
        return {}
    if any(row.total_value_with_buying_power is None for row in currencies):
        return {}
    if any(row.currency not in {fx.source_currency, fx.target_currency} for row in currencies):
        return {}
    converted_values: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        for row in currencies:
            value = row.total_value_with_buying_power
            if row.currency == fx.source_currency:
                value = value * fx.rate
            converted_values[row.currency] = value
        total = sum(converted_values.values(), Decimal(0))
        if total == 0:
            return {}
        return {currency: value / total for currency, value in converted_values.items()}


def _convert_totals(
    currencies: Sequence[CurrencyAnalytics], fx: FXMetadata | None
) -> ConvertedTotals | None:
    if fx is None or fx.rate is None or fx.timestamp is None:
        return None
    if len(currencies) < 2 or any(
        row.currency not in {fx.source_currency, fx.target_currency} for row in currencies
    ):
        return None
    by_currency = {row.currency: row for row in currencies}
    if any(not row.market_value_complete for row in currencies):
        market_total = None
    else:
        market_total = _convert_component(by_currency, fx, "market_value_total")
    if any(not row.purchase_amount_complete for row in currencies):
        purchase_total = None
    else:
        purchase_total = _convert_component(by_currency, fx, "purchase_amount_total")
    if any(not row.profit_loss_complete for row in currencies):
        profit_total = None
    else:
        profit_total = _convert_component(by_currency, fx, "profit_loss_total")
    all_buying_power = all(row.buying_power_complete for row in currencies)
    buying_total = (
        _convert_component(by_currency, fx, "buying_power_total") if all_buying_power else None
    )
    portfolio_total = (
        _convert_component(by_currency, fx, "total_value_with_buying_power")
        if all(row.total_value_with_buying_power is not None for row in currencies)
        else None
    )
    return ConvertedTotals(
        currency=fx.target_currency,
        market_value_total=market_total,
        purchase_amount_total=purchase_total,
        profit_loss_total=profit_total,
        buying_power_total=buying_total,
        portfolio_value_total=portfolio_total,
    )


def _convert_component(
    rows: dict[str, CurrencyAnalytics], fx: FXMetadata, field: str
) -> Decimal | None:
    values = [getattr(row, field) for row in rows.values()]
    if any(value is None for value in values):
        return None
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        total = Decimal(0)
        for currency, value in zip(rows, values, strict=True):
            total += value * fx.rate if currency == fx.source_currency else value
        return total


def _summarize_orders(
    orders: Orders | None, as_of: datetime | None, stale_after: timedelta | None
) -> OrderAnalytics | None:
    if orders is None:
        return None
    by_status: dict[str | None, list[Order]] = {}
    by_side: dict[str | None, int] = {}
    for order in orders.orders:
        by_status.setdefault(order.status, []).append(order)
        by_side[order.side] = by_side.get(order.side, 0) + 1

    def state_summary(status: str | None, group: Sequence[Order]) -> OrderStateSummary:
        ordered = _sum_values(order.quantity for order in group)
        filled = _sum_values(order.filled_quantity for order in group)
        return OrderStateSummary(
            status=status,
            count=len(group),
            ordered_quantity_total=ordered,
            ordered_quantity_missing_count=sum(order.quantity is None for order in group),
            filled_quantity_total=filled,
            filled_quantity_missing_count=sum(order.filled_quantity is None for order in group),
        )

    by_status_out = tuple(
        state_summary(status, group)
        for status, group in sorted(by_status.items(), key=lambda pair: pair[0] or "")
    )
    by_side_out = tuple(
        OrderSideSummary(side, count)
        for side, count in sorted(by_side.items(), key=lambda pair: pair[0] or "")
    )
    retrieved_at = orders.retrieved_at
    stale = _stale(retrieved_at, as_of, stale_after)
    if stale_after is not None and stale is not False:
        # Quantities remain auditable but callers can see the stale source through the warning.
        warnings = (*orders.coverage_warnings, "Order source is stale or has no timestamp.")
    else:
        warnings = orders.coverage_warnings
    return OrderAnalytics(
        count=len(orders.orders),
        by_status=by_status_out,
        by_side=by_side_out,
        ordered_quantity_total=_sum_values(order.quantity for order in orders.orders),
        ordered_quantity_missing_count=sum(order.quantity is None for order in orders.orders),
        filled_quantity_total=_sum_values(order.filled_quantity for order in orders.orders),
        filled_quantity_missing_count=sum(
            order.filled_quantity is None for order in orders.orders
        ),
        retrieved_at=retrieved_at,
        record_retrieved_at=tuple(order.retrieved_at for order in orders.orders),
        stale=stale,
        has_more=orders.has_more,
        coverage_warnings=warnings,
    )
