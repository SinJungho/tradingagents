"""Synthetic CLI/report integration checks for portfolio commands."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from typer.testing import CliRunner

import cli.portfolio as portfolio_cli
from cli.main import app
from tradingagents.portfolio.analytics import analyze_portfolio
from tradingagents.portfolio.models import Accounts, BuyingPower, Holding, Holdings, Order, Orders
from tradingagents.portfolio.reporting import PortfolioReport, RequestScope, build_portfolio_report

runner = CliRunner()


def _holding(now):
    return Holding(
        symbol="SYNTH",
        name="Synthetic Corp",
        market_country="US",
        exchange="NASDAQ",
        currency="USD",
        quantity=Decimal("2"),
        last_price=Decimal("12.5"),
        average_purchase_price=Decimal("10"),
        purchase_amount=Decimal("20"),
        market_value=Decimal("25"),
        market_value_after_cost=Decimal("24.8"),
        profit_loss=Decimal("5"),
        profit_loss_after_cost=Decimal("4.8"),
        retrieved_at=now,
    )


def _order(now):
    return Order(
        order_id="synthetic-order-id-must-not-be-saved",
        symbol="SYNTH",
        market_country="US",
        exchange="NASDAQ",
        currency="USD",
        side="BUY",
        order_type="LIMIT",
        status="OPEN",
        price=Decimal("12"),
        quantity=Decimal("1"),
        order_amount=Decimal("12"),
        filled_quantity=Decimal("0"),
        average_filled_price=None,
        filled_amount=None,
        ordered_at=now,
        canceled_at=None,
        filled_at=None,
        retrieved_at=now,
    )


def test_demo_writes_schema_valid_json_and_korean_markdown_without_live_dependencies(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("TOSS_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOSS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TOSS_BROKER_READ_ONLY_VERIFIED", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("demo must not initialize a network or LLM client")

    monkeypatch.setattr("requests.Session", forbidden)
    monkeypatch.setattr(portfolio_cli, "_make_scenario_workflow", forbidden)

    result = runner.invoke(app, ["portfolio", "demo", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    json_path = next(tmp_path.glob("*.json"))
    markdown_path = next(tmp_path.glob("*.md"))
    report = PortfolioReport.model_validate_json(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert report.mode == "demo"
    assert report.request.orders_from <= report.request.orders_to
    assert report.orders.count == 1
    assert report.sources
    assert "합성 데모 데이터" in " ".join(report.caveats)
    assert "## 출처와 조회 시각" in markdown
    assert "## 요청 범위" in markdown
    assert "촉매" in markdown and "주요 위험" in markdown
    assert "논리 무효화 조건" in markdown
    assert "KRW" in markdown and "USD" in markdown
    assert "synthetic-order-id-must-not-be-saved" not in json_path.read_text(encoding="utf-8")


def test_live_requires_acknowledgement_before_constructing_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.delenv("TOSS_BROKER_READ_ONLY_VERIFIED", raising=False)
    constructed = []

    class ForbiddenAdapter:
        def __init__(self, *_args, **_kwargs):
            constructed.append(True)

    monkeypatch.setattr("tradingagents.portfolio.toss.TossPortfolioAdapter", ForbiddenAdapter)

    result = runner.invoke(
        app,
        ["portfolio", "live", "--account-ordinal", "1", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert "TOSS_BROKER_READ_ONLY_VERIFIED" in result.output
    assert constructed == []
    assert list(tmp_path.iterdir()) == []


def test_live_retains_partial_sources_and_never_writes_account_or_order_ids(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    calls = []

    class SyntheticAdapter:
        def __init__(self, client_id, client_secret):
            assert client_id == "synthetic-client"
            assert client_secret == "synthetic-secret"

        def get_accounts(self):
            return Accounts(
                accounts=(
                    portfolio_cli.Account(account_seq=987654321, account_type="synthetic"),
                    portfolio_cli.Account(account_seq=876543210, account_type="synthetic"),
                ),
                retrieved_at=now,
            )

        def get_holdings(self, account_seq):
            calls.append(("holdings", account_seq))
            return Holdings((_holding(now),), retrieved_at=now)

        def get_buying_power(self, account_seq, currency):
            calls.append(("buying_power", account_seq, currency))
            if currency == "USD":
                raise RuntimeError("synthetic private response")
            return BuyingPower(currency, Decimal("100"), now)

        def get_orders(self, account_seq, status, *, from_date, to_date):
            calls.append(("orders", account_seq, status, from_date, to_date))
            if status == "CLOSED":
                raise RuntimeError("synthetic raw broker response")
            return Orders((_order(now),), retrieved_at=now)

    monkeypatch.setenv("TOSS_BROKER_READ_ONLY_VERIFIED", "I_ACKNOWLEDGE_READ_ONLY")
    monkeypatch.setenv("TOSS_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setattr("tradingagents.portfolio.toss.TossPortfolioAdapter", SyntheticAdapter)
    monkeypatch.setattr(portfolio_cli, "_make_scenario_workflow", lambda *_args: None)

    result = runner.invoke(
        app,
        [
            "portfolio",
            "live",
            "--account-ordinal",
            "2",
            "--orders-from",
            "2026-10-01",
            "--orders-to",
            "2026-11-01",
            "--no-scenarios",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "987654321" not in result.output and "876543210" not in result.output
    assert calls[0] == ("holdings", 876543210)
    order_calls = [row for row in calls if row[0] == "orders"]
    assert all(row[3].isoformat() == "2026-10-01" for row in order_calls)
    assert all(row[4].isoformat() == "2026-11-01" for row in order_calls)

    json_path = next(tmp_path.glob("*.json"))
    markdown_path = next(tmp_path.glob("*.md"))
    raw_json = json_path.read_text(encoding="utf-8")
    report = PortfolioReport.model_validate_json(raw_json)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert report.status == "partial"
    assert report.request.orders_from.isoformat() == "2026-10-01"
    assert report.request.orders_to.isoformat() == "2026-11-01"
    assert report.orders.count == 1
    assert report.source_failures == [
        "buying-power retrieval failed for USD",
        "closed order-history retrieval failed",
    ]
    assert any(source.source == "Toss Securities holdings API" for source in report.sources)
    assert any(source.source == "Toss Securities order history API" for source in report.sources)
    assert "synthetic private response" not in raw_json
    assert "synthetic raw broker response" not in raw_json
    assert "987654321" not in raw_json and "876543210" not in raw_json
    assert "synthetic-order-id-must-not-be-saved" not in raw_json
    assert "누락과 실패" in markdown
    assert "주문 기간: 2026-10-01 ~ 2026-11-01" in markdown


def test_held_korean_ticker_and_unheld_us_ticker_can_be_selected_separately():
    now = datetime.now(UTC)
    korean = portfolio_cli.Holding(
        symbol="005930",
        name="Synthetic Korean Corp",
        market_country="KR",
        exchange="KRX",
        currency="KRW",
        quantity=Decimal("1"),
        last_price=Decimal("10"),
        average_purchase_price=Decimal("8"),
        purchase_amount=Decimal("8"),
        market_value=Decimal("10"),
        market_value_after_cost=None,
        profit_loss=Decimal("2"),
        profit_loss_after_cost=None,
        retrieved_at=now,
    )
    selected, omissions, watchlist = portfolio_cli._selected_holdings(
        Holdings((korean,), now), ["005930.KS", "MSFT"]
    )

    assert [row.symbol for row in selected.holdings] == ["005930"]
    assert omissions == []
    assert watchlist == [("MSFT", "US")]


def test_open_and_closed_order_overlap_is_deduplicated_using_newest_record():
    now = datetime.now(UTC)
    later = replace(_order(now), status="FILLED", retrieved_at=now + timedelta(seconds=1))

    combined = portfolio_cli._combine_orders(
        [Orders((_order(now),), now), Orders((later,), later.retrieved_at)], []
    )

    assert combined is not None
    assert len(combined.orders) == 1
    assert combined.orders[0].status == "FILLED"
    assert any("across status queries" in warning for warning in combined.coverage_warnings)


def test_holdings_failure_keeps_successful_order_and_buying_power_as_partial():
    now = datetime.now(UTC)
    order_data = Orders((_order(now),), now)
    analytics = analyze_portfolio(
        None,
        (BuyingPower("USD", Decimal("25"), now),),
        order_data,
        as_of=now,
    )
    report = build_portfolio_report(
        mode="live",
        generated_at=now,
        request=RequestScope(
            orders_from=now.date(),
            orders_to=now.date(),
            max_pages_per_status=3,
            max_symbols=10,
            selected_symbols=[],
            symbol_selection="all_returned_holdings",
        ),
        analytics=analytics,
        holdings=None,
        scenarios=None,
        source_failures=["holdings retrieval failed"],
    )

    assert report.status == "partial"
    assert report.orders.available is True
    assert report.orders.count == 1


def test_symbol_research_graph_runs_configured_analysts_and_tools_without_debates():
    calls = []

    def market_analyst(state):
        calls.append("market")
        if len([call for call in calls if call == "market"]) == 1:
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "synthetic_tool", "args": {}, "id": "call-1", "type": "tool_call"}
                        ],
                    )
                ]
            }
        return {"messages": [AIMessage(content="done")], "market_report": "synthetic market report"}

    def market_tools(_state):
        calls.append("tool")
        return {"messages": [ToolMessage(content="synthetic data", tool_call_id="call-1")]}

    def news_analyst(state):
        calls.append("news")
        assert len(state["messages"]) == 1
        return {"messages": [AIMessage(content="news done")], "news_report": "synthetic news"}

    graph = portfolio_cli._build_symbol_research_graph(
        (("market", market_analyst, market_tools), ("news", news_analyst, market_tools))
    )
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="synthetic symbol")],
            "company_of_interest": "SYNTH",
            "asset_type": "stock",
            "instrument_context": "Synthetic US equity SYNTH",
            "trade_date": "2026-11-09",
        }
    )

    assert calls == ["market", "tool", "market", "news"]
    assert result["market_report"] == "synthetic market report"
    assert result["news_report"] == "synthetic news"


def test_portfolio_horizons_can_be_configured_and_invalid_ranges_fail(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PORTFOLIO_SHORT_DAYS", "2-12")
    monkeypatch.setenv("TRADINGAGENTS_PORTFOLIO_MEDIUM_MONTHS", "2-9")
    monkeypatch.setenv("TRADINGAGENTS_PORTFOLIO_LONG_MONTHS", "9-36")

    horizons = portfolio_cli._scenario_horizons_from_env()

    assert [(row.minimum, row.maximum) for row in horizons] == [(2, 12), (2, 9), (9, 36)]
    monkeypatch.setenv("TRADINGAGENTS_PORTFOLIO_SHORT_DAYS", "20-1")
    with pytest.raises(portfolio_cli.typer.BadParameter, match="Invalid TRADINGAGENTS_PORTFOLIO_SHORT_DAYS"):
        portfolio_cli._scenario_horizons_from_env()
