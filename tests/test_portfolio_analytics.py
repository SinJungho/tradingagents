from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingagents.portfolio.analytics import analyze_portfolio, map_market_symbol
from tradingagents.portfolio.models import BuyingPower, Holding, Holdings, Order, Orders

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)


def _holding(
    symbol="SYNUS",
    *,
    market_country="US",
    exchange="NASDAQ",
    currency="USD",
    quantity="1",
    last_price=None,
    average_purchase_price=None,
    purchase_amount=None,
    market_value=None,
    market_value_after_cost=None,
    profit_loss=None,
    profit_loss_after_cost=None,
    retrieved_at=NOW,
):
    return Holding(
        symbol=symbol,
        name=None,
        market_country=market_country,
        exchange=exchange,
        currency=currency,
        quantity=Decimal(quantity),
        last_price=Decimal(last_price) if last_price is not None else None,
        average_purchase_price=(
            Decimal(average_purchase_price) if average_purchase_price is not None else None
        ),
        purchase_amount=Decimal(purchase_amount) if purchase_amount is not None else None,
        market_value=Decimal(market_value) if market_value is not None else None,
        market_value_after_cost=(
            Decimal(market_value_after_cost) if market_value_after_cost is not None else None
        ),
        profit_loss=Decimal(profit_loss) if profit_loss is not None else None,
        profit_loss_after_cost=(
            Decimal(profit_loss_after_cost) if profit_loss_after_cost is not None else None
        ),
        retrieved_at=retrieved_at,
    )


def _buying_power(currency, amount, *, retrieved_at=NOW, warnings=()):
    return BuyingPower(currency, Decimal(amount), retrieved_at, tuple(warnings))


def _order(
    order_id,
    *,
    status,
    side="BUY",
    quantity=None,
    filled_quantity=None,
    retrieved_at=NOW,
):
    return Order(
        order_id=order_id,
        symbol="SYNUS",
        market_country="US",
        exchange="NASDAQ",
        currency="USD",
        side=side,
        order_type="LIMIT",
        status=status,
        price=None,
        quantity=Decimal(quantity) if quantity is not None else None,
        order_amount=None,
        filled_quantity=(
            Decimal(filled_quantity) if filled_quantity is not None else None
        ),
        average_filled_price=None,
        filled_amount=None,
        ordered_at=None,
        canceled_at=None,
        filled_at=None,
        retrieved_at=retrieved_at,
    )


def _currency(result, code):
    return next(row for row in result.currencies if row.currency == code)


def test_symbol_mapping_is_market_aware_and_keeps_unknowns_explicit():
    assert map_market_symbol("005930", "KR", "KRX") == "005930.KS"
    assert map_market_symbol("035720", "KR", "KOSDAQ") == "035720.KQ"
    assert map_market_symbol("005930", "KR", "UNKNOWN") is None
    assert map_market_symbol("synus", "US", "NASDAQ") == "SYNUS"
    assert map_market_symbol("ABC", "CA", "TSX") is None

    result = analyze_portfolio(
        Holdings((_holding("ODD", market_country="CA", currency="CAD"),), NOW)
    )

    assert result.positions[0].provider_symbol is None
    assert any("No supported market-symbol mapping" in item for item in result.positions[0].unknowns)


def test_decimal_values_weights_concentration_and_fx_are_currency_separated():
    holdings = Holdings(
        (
            _holding(
                "005930",
                market_country="KR",
                exchange="KRX",
                currency="KRW",
                quantity="0.125",
                last_price="100.05",
                average_purchase_price="90",
            ),
            _holding(
                "SYNUS",
                quantity="1.5",
                last_price="12.34",
                average_purchase_price="10",
            ),
        ),
        NOW,
        coverage_warnings=(
            "Toss holdings cover KR and US stocks; overseas options and bonds are excluded.",
        ),
    )
    result = analyze_portfolio(
        holdings,
        (_buying_power("KRW", "1.25"), _buying_power("USD", "1.49")),
        fx_rate=Decimal("0.00075"),
        fx_timestamp=NOW,
    )

    kr = result.positions[0]
    us = result.positions[1]
    assert kr.provider_symbol == "005930.KS"
    assert kr.quantity == Decimal("0.125")
    assert kr.market_value == Decimal("12.50625")
    assert kr.purchase_amount == Decimal("11.250")
    assert kr.profit_loss == Decimal("1.25625")
    assert kr.market_value_source == "quantity_times_last_price"
    assert kr.profit_loss_source == "market_value_minus_purchase_amount"
    assert us.market_value == Decimal("18.510")
    assert _currency(result, "KRW").market_value_total == Decimal("12.50625")
    assert _currency(result, "USD").market_value_total == Decimal("18.510")
    assert _currency(result, "KRW").purchase_amount_total == Decimal("11.250")
    assert _currency(result, "USD").purchase_amount_total == Decimal("15.0")
    assert _currency(result, "KRW").buying_power_total == Decimal("1.25")
    assert _currency(result, "USD").buying_power_total == Decimal("1.49")
    assert _currency(result, "KRW").represented_scope_complete
    assert _currency(result, "USD").represented_scope_complete
    assert result.account_wide_coverage == "partial"
    assert result.coverage_warnings == (
        "holdings: Toss holdings cover KR and US stocks; overseas options and bonds are excluded.",
    )
    assert kr.security_weight == Decimal("1")
    assert kr.currency_portfolio_weight == Decimal("12.50625") / Decimal("13.75625")
    assert result.buying_power[1].currency_portfolio_weight == Decimal("1.49") / Decimal("20.000")
    assert result.concentration_by_symbol[0].weight == Decimal("1")
    assert {row.key for row in result.concentration_by_market} == {"KR", "US"}
    assert {row.key: row.weight for row in result.concentration_by_currency} == {
        "KRW": Decimal("13.75625") * Decimal("0.00075") / Decimal("20.0103171875"),
        "USD": Decimal("20.000") / Decimal("20.0103171875"),
    }
    assert {row.key: row.value for row in result.concentration_by_currency} == {
        "KRW": Decimal("13.75625"),
        "USD": Decimal("20.000"),
    }
    assert result.fx is not None and result.fx.applied
    assert result.fx.rate == Decimal("0.00075")
    assert result.fx.timestamp == NOW
    assert result.converted_totals is not None
    assert result.converted_totals.market_value_total == Decimal("18.5193796875")
    assert result.converted_totals.purchase_amount_total == Decimal("15.0084375")
    assert result.converted_totals.profit_loss_total == Decimal("3.5109421875")
    assert result.converted_totals.buying_power_total == Decimal("1.4909375")
    assert result.converted_totals.portfolio_value_total == Decimal("20.0103171875")


def test_missing_values_and_partial_coverage_never_become_zero_or_complete_weights():
    holdings = Holdings(
        (
            _holding(
                "GOOD",
                market_value="10",
                purchase_amount="8",
                profit_loss="2",
            ),
            _holding(
                "NO_VALUE",
                market_value=None,
                last_price=None,
                average_purchase_price=None,
                purchase_amount=None,
            ),
        ),
        NOW,
        coverage_warnings=("Provider omitted some positions.",),
    )
    result = analyze_portfolio(holdings, (_buying_power("USD", "3"),))

    summary = _currency(result, "USD")
    assert result.positions[1].market_value is None
    assert result.positions[1].purchase_amount is None
    assert result.positions[1].profit_loss is None
    assert summary.market_value_total == Decimal("10")  # known subtotal only
    assert summary.market_value_missing_count == 1
    assert summary.purchase_amount_total == Decimal("8")
    assert summary.profit_loss_total == Decimal("2")
    assert not summary.market_value_complete
    assert result.positions[0].security_weight is None
    assert result.positions[0].currency_portfolio_weight is None
    assert result.buying_power[0].currency_portfolio_weight is None
    assert result.coverage_warnings == (
        "holdings: Provider omitted some positions.",
    )


def test_absent_inputs_and_partial_fx_keep_values_unknown_and_skip_conversion():
    missing = analyze_portfolio()
    assert missing.positions == ()
    assert missing.currencies == ()
    assert missing.converted_totals is None
    assert any("Holdings were not supplied" in value for value in missing.unknowns)
    assert any("Buying power was not supplied" in value for value in missing.unknowns)

    partial_fx = analyze_portfolio(
        Holdings((_holding(market_value="10", purchase_amount="8"),), NOW),
        (_buying_power("USD", "2"),),
        fx_rate=Decimal("1.2"),
    )
    assert partial_fx.fx is not None
    assert partial_fx.fx.rate == Decimal("1.2")
    assert partial_fx.fx.timestamp is None
    assert not partial_fx.fx.applied
    assert partial_fx.converted_totals is None
    assert partial_fx.concentration_by_currency[0].weight is None

    partial_cash = analyze_portfolio(
        Holdings((_holding("005930", market_country="KR", exchange="KRX", currency="KRW", market_value="10"),), NOW),
        (_buying_power("USD", "2"),),
    )
    assert _currency(partial_cash, "KRW").buying_power_total is None
    assert partial_cash.positions[0].currency_portfolio_weight is None
    assert any("No buying-power input was supplied for KRW" in item for item in partial_cash.unknowns)


def test_stale_positions_and_fx_are_retained_but_excluded_from_totals():
    old = NOW - timedelta(days=2)
    result = analyze_portfolio(
        Holdings((_holding(market_value="10", retrieved_at=old),), old),
        (_buying_power("USD", "2", retrieved_at=old),),
        fx_rate=Decimal("0.001"),
        fx_timestamp=old,
        as_of=NOW,
        stale_after=timedelta(hours=1),
    )

    assert result.positions[0].market_value == Decimal("10")
    assert result.positions[0].stale is True
    assert not result.positions[0].included_in_totals
    assert _currency(result, "USD").market_value_total is None
    assert _currency(result, "USD").buying_power_total is None
    assert result.converted_totals is None
    assert any("FX conversion was omitted" in value for value in result.unknowns)


def test_missing_timestamps_make_freshness_unknown_when_max_age_is_requested():
    result = analyze_portfolio(
        Holdings((_holding(market_value="10", retrieved_at=None),), None),
        (_buying_power("USD", "2", retrieved_at=None),),
        as_of=NOW,
        stale_after=timedelta(hours=1),
    )

    assert result.positions[0].retrieved_at is None
    assert result.positions[0].stale is None
    assert not result.positions[0].included_in_totals
    assert _currency(result, "USD").market_value_total is None
    assert result.buying_power[0].retrieved_at is None
    assert not result.buying_power[0].included_in_totals
    assert any("Freshness is unknown" in value for value in result.unknowns)


def test_order_status_counts_keep_ordered_and_filled_quantities_separate():
    orders = Orders(
        (
            _order("synthetic-1", status="PARTIAL_FILLED", quantity="3", filled_quantity="1.25"),
            _order("synthetic-2", status="OPEN", quantity="2", filled_quantity=None),
            _order("synthetic-3", status="CANCELED", side="SELL", quantity=None, filled_quantity="0.5"),
        ),
        NOW,
        has_more=True,
        coverage_warnings=("Provider history is paginated.",),
    )
    result = analyze_portfolio(orders=orders)

    assert result.orders is not None
    assert result.orders.count == 3
    assert result.orders.ordered_quantity_total == Decimal("5")
    assert result.orders.ordered_quantity_missing_count == 1
    assert result.orders.filled_quantity_total == Decimal("1.75")
    assert result.orders.filled_quantity_missing_count == 1
    by_status = {row.status: row for row in result.orders.by_status}
    assert by_status["PARTIAL_FILLED"].ordered_quantity_total == Decimal("3")
    assert by_status["PARTIAL_FILLED"].filled_quantity_total == Decimal("1.25")
    assert by_status["OPEN"].ordered_quantity_total == Decimal("2")
    assert by_status["OPEN"].filled_quantity_total is None
    assert by_status["CANCELED"].ordered_quantity_total is None
    assert by_status["CANCELED"].filled_quantity_total == Decimal("0.5")
    assert {row.side: row.count for row in result.orders.by_side} == {"BUY": 2, "SELL": 1}
    assert result.orders.has_more
    assert result.orders.source_scope == "provider_returned_records"
    assert result.orders.record_retrieved_at == (NOW, NOW, NOW)
    assert any("complete ledger" in value for value in result.unknowns)
    assert "synthetic-1" not in repr(result.orders)


def test_stale_order_state_is_marked_and_keeps_its_source_timestamp():
    old = NOW - timedelta(days=1)
    result = analyze_portfolio(
        orders=Orders((_order("synthetic-old", status="OPEN", quantity="2", retrieved_at=old),), old),
        as_of=NOW,
        stale_after=timedelta(hours=1),
    )

    assert result.orders is not None
    assert result.orders.retrieved_at == old
    assert result.orders.record_retrieved_at == (old,)
    assert result.orders.stale is True
    assert result.orders.ordered_quantity_total == Decimal("2")
    assert result.orders.coverage_warnings == ("Order source is stale or has no timestamp.",)
