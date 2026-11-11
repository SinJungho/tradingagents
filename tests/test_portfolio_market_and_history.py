import json
import stat
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tradingagents.portfolio.analytics import analyze_portfolio
from tradingagents.portfolio.history import append_portfolio_snapshot
from tradingagents.portfolio.models import (
    BuyingPower,
    Candle,
    CandlePage,
    Holding,
    Holdings,
    MarketPrice,
    Transaction,
    Transactions,
)
from tradingagents.portfolio.reporting import RequestScope, build_portfolio_report
from tradingagents.portfolio.technical import analyze_daily_candles

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def _trade(kind, *, quantity, amount, net_amount, at, symbol="SYNUS"):
    return Transaction(
        transaction_type=kind,
        asset_class="STOCK",
        settled=True,
        is_cancellation=False,
        symbol=symbol,
        currency="USD",
        quantity=Decimal(quantity),
        amount=Decimal(amount),
        commission=Decimal("1"),
        tax=Decimal("0"),
        net_amount=Decimal(net_amount),
        transaction_time=at,
    )


def _current_holding(symbol="SYNUS", quantity="10"):
    return Holding(
        symbol=symbol, name=None, market_country="US", exchange="NASDAQ",
        currency="USD", quantity=Decimal(quantity), last_price=None,
        average_purchase_price=None, purchase_amount=None, market_value=None,
        market_value_after_cost=None, profit_loss=None,
        profit_loss_after_cost=None, retrieved_at=NOW,
    )


def test_realized_profit_loss_uses_weighted_average_cost_and_hides_trade_rows():
    transactions = Transactions(
        (
            _trade("BUY", quantity="10", amount="100", net_amount="101", at=NOW - timedelta(days=3)),
            _trade("BUY", quantity="10", amount="200", net_amount="201", at=NOW - timedelta(days=2)),
            _trade("SELL", quantity="10", amount="250", net_amount="249", at=NOW - timedelta(days=1)),
            Transaction("DIVIDEND", "STOCK", True, False, currency="USD", amount=Decimal("5")),
        ),
        NOW,
    )

    summary = analyze_portfolio(
        Holdings((_current_holding(),), NOW), transactions=transactions
    ).transactions

    assert summary is not None
    pnl = summary.realized_profit_loss[0]
    assert pnl.complete
    assert pnl.before_cost == Decimal("100")
    assert pnl.after_cost == Decimal("98")
    assert "SYNUS" not in repr(summary)
    assert "249" not in repr(summary)


def test_realized_profit_loss_reconciles_a_fully_closed_position_to_zero_holdings():
    transactions = Transactions(
        (
            _trade("BUY", quantity="2", amount="20", net_amount="21", at=NOW - timedelta(days=1)),
            _trade("SELL", quantity="2", amount="30", net_amount="29", at=NOW),
        ),
        NOW,
    )

    summary = analyze_portfolio(Holdings((), NOW), transactions=transactions).transactions

    assert summary is not None and summary.realized_profit_loss[0].complete
    assert summary.realized_profit_loss[0].before_cost == Decimal("10")


def test_realized_profit_loss_is_unknown_when_ledger_is_truncated_or_basis_missing():
    trade = _trade("SELL", quantity="2", amount="50", net_amount="49", at=NOW)
    truncated = analyze_portfolio(
        transactions=Transactions((trade,), NOW, has_more=True)
    ).transactions
    missing_basis = analyze_portfolio(
        transactions=Transactions((trade,), NOW, has_more=False)
    ).transactions

    assert truncated is not None and truncated.realized_profit_loss[0].before_cost is None
    assert missing_basis is not None and missing_basis.realized_profit_loss[0].complete is False


def test_report_contains_only_transaction_aggregates_not_trade_rows():
    row = _trade("BUY", quantity="3", amount="30", net_amount="31", at=NOW, symbol="SENSITIVE-SYNTHETIC")
    analytics = analyze_portfolio(transactions=Transactions((row,), NOW))
    report = build_portfolio_report(
        mode="live",
        generated_at=NOW,
        request=RequestScope(
            orders_from=date(2026, 11, 1),
            orders_to=date(2026, 11, 9),
            max_pages_per_status=3,
            max_symbols=10,
            selected_symbols=[],
            symbol_selection="all_returned_holdings",
        ),
        analytics=analytics,
        holdings=None,
        scenarios=None,
    )

    serialized = report.model_dump_json()

    assert "SENSITIVE-SYNTHETIC" not in serialized
    assert '"amount"' not in serialized
    assert "31" not in serialized


def test_daily_technical_indicators_use_sorted_candles_and_report_data_times():
    candles = tuple(
        Candle(
            timestamp=NOW - timedelta(days=199 - index),
            open_price=Decimal(100 + index),
            high_price=Decimal(102 + index),
            low_price=Decimal(98 + index),
            close_price=Decimal(100 + index),
            volume=Decimal(100 + index),
            currency="USD",
        )
        for index in range(200)
    )
    page = CandlePage("SYNUS", "1d", tuple(reversed(candles)), NOW)
    quote = MarketPrice("SYNUS", "USD", Decimal("301"), NOW, NOW)

    technical = analyze_daily_candles("SYNUS", page, quote)

    assert technical.price == Decimal("301")
    assert technical.latest_close == Decimal("299")
    assert technical.candle_count == 200
    assert technical.candle_as_of == candles[-1].timestamp
    assert technical.sma_20 == Decimal("289.5")
    assert technical.sma_200 == Decimal("199.5")
    assert technical.return_1d == Decimal(299) / Decimal(298) - 1
    assert technical.rsi_14 == Decimal(100)
    assert technical.macd is not None and technical.macd_signal is not None
    assert technical.atr_14 == Decimal(4)
    assert technical.volume_ratio_20 is not None


def test_private_snapshot_compares_same_ordinal_and_uses_restricted_permissions(tmp_path):
    path = tmp_path / "portfolio" / "history.jsonl"
    holding = Holding(
        symbol="SYNUS", name=None, market_country="US", exchange=None,
        currency="USD", quantity=Decimal("2"), last_price=Decimal("50"),
        average_purchase_price=Decimal("40"), purchase_amount=Decimal("80"),
        market_value=Decimal("100"), market_value_after_cost=None,
        profit_loss=None, profit_loss_after_cost=None, retrieved_at=NOW,
    )
    holdings = Holdings((holding,), NOW)
    first = append_portfolio_snapshot(
        holdings, [BuyingPower("USD", Decimal("10"), NOW)], account_ordinal=1,
        captured_at=NOW, path=path,
    )
    updated = Holding(
        **{**holding.__dict__, "market_value": Decimal("110")}
    )
    second = append_portfolio_snapshot(
        Holdings((updated,), NOW), [BuyingPower("USD", Decimal("10"), NOW)],
        account_ordinal=1, captured_at=NOW + timedelta(days=1), path=path,
    )

    assert first.previous_at is None
    assert second.change_by_currency == {"USD": Decimal("10")}
    assert second.previous_at == NOW
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert "account_seq" not in records[0]
    assert "SYNUS" in path.read_text()
