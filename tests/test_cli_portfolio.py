"""Synthetic CLI/report integration checks for portfolio commands."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from typer.testing import CliRunner

import cli.portfolio as portfolio_cli
from cli.main import app
from tradingagents.portfolio.analytics import analyze_portfolio
from tradingagents.portfolio.models import (
    Accounts,
    BuyingPower,
    ExchangeRate,
    Holding,
    Holdings,
    Order,
    Orders,
    Transaction,
    Transactions,
)
from tradingagents.portfolio.reporting import (
    PortfolioReport,
    RequestScope,
    build_portfolio_report,
    render_markdown,
)
from tradingagents.portfolio.scenarios import (
    PortfolioScenarioReport,
    SymbolResearchResult,
    TradingDecisionResult,
)

runner = CliRunner()


def test_portfolio_research_budget_allows_market_snapshot_round():
    assert portfolio_cli._portfolio_tool_round_limit(20, 24, 3) == 3


def test_decision_context_contains_normalized_positions_but_not_buying_power():
    now = datetime.now(UTC)
    holdings = Holdings(
        (
            _holding(now),
            replace(
                _holding(now),
                symbol="005930",
                market_country="KR",
                exchange="KRX",
                currency="KRW",
                quantity=Decimal("1.25"),
                average_purchase_price=Decimal("70000"),
            ),
        ),
        now,
    )

    context = portfolio_cli._portfolio_decision_context(holdings)

    assert context is not None
    assert context.cash is None
    assert [(row.ticker, row.quantity, row.average_price, row.currency) for row in context.positions] == [
        ("SYNTH", 2.0, 10.0, "USD"),
        ("005930.KS", 1.25, 70000.0, "KRW"),
    ]
    assert "average price 70,000.00 KRW" in context.render("005930.KS")
    assert "SYNTH 2 units, average price 10.00 USD" in context.render("005930.KS")


def test_full_workflow_builder_uses_existing_graph_without_persisting_memory(monkeypatch):
    calls = []

    class FakeCompiledGraph:
        def compile(self):
            return self

        def invoke(self, initial_state, *, config):
            calls.append(("invoke", initial_state, config))
            return {
                "market_report": "Synthetic market research",
                "sentiment_report": "Synthetic sentiment research",
                "news_report": "Synthetic news research",
                "fundamentals_report": "Synthetic fundamentals research",
                "trader_investment_plan": "Synthetic trader plan",
                "risk_debate_state": {"history": "Synthetic risk debate"},
                "final_trade_decision": "Synthetic final decision",
                "final_rating": "Buy",
            }

    class FakeGraphSetup:
        def setup_graph(self, analysts, *, memory_node):
            calls.append(("setup", analysts, memory_node))
            return FakeCompiledGraph()

    class FakeTradingAgentsGraph:
        def __init__(self, *, selected_analysts, config):
            self.config = config
            self.graph_setup = FakeGraphSetup()
            self.quick_thinking_llm = object()

        def create_run_state(self, ticker, trade_date, *, asset_type, portfolio):
            state = {
                "ticker": ticker,
                "trade_date": trade_date,
                "asset_type": asset_type,
                "portfolio": portfolio,
            }
            calls.append(("initial", state))
            return state

    class FakeScenarioWorkflow:
        def __init__(self, analyzer, _llm, _config):
            self.analyzer = analyzer

    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph", FakeTradingAgentsGraph
    )
    monkeypatch.setattr(portfolio_cli, "PortfolioScenarioWorkflow", FakeScenarioWorkflow)
    monkeypatch.setattr(portfolio_cli, "_today_kst", lambda: date(2026, 11, 10))
    portfolio_context = portfolio_cli.PortfolioContext(
        positions=[portfolio_cli.Position(ticker="SYNTH", quantity=2, currency="USD")]
    )

    workflow, decisions = portfolio_cli._make_scenario_workflow(
        4,
        full_workflow=True,
        portfolio_context=portfolio_context,
    )
    research = workflow.analyzer(type("Input", (), {"symbol": "SYNTH"})())

    assert "Synthetic sentiment research" in research
    assert calls[0] == (
        "setup",
        ("market", "social", "news", "fundamentals"),
        None,
    )
    initial = next(row[1] for row in calls if row[0] == "initial")
    assert initial["portfolio"] is portfolio_context
    assert decisions == [
        TradingDecisionResult(
            "SYNTH",
            "Synthetic trader plan",
            "Synthetic risk debate",
            "Synthetic final decision",
            "Buy",
        )
    ]


def test_run_scenarios_attaches_full_decisions_and_passes_whole_book(monkeypatch):
    now = datetime.now(UTC)
    holdings = Holdings((_holding(now),), now)
    analytics = analyze_portfolio(holdings, (), None, as_of=now)
    captured = {}
    decision = TradingDecisionResult(
        "SYNTH", "Synthetic trader", "Synthetic risk", "Synthetic final", "Hold"
    )

    class FakeScenarioWorkflow:
        def invoke(self, selected_holdings, *, portfolio_analysis, watchlist_symbols):
            captured["selected"] = selected_holdings
            captured["analytics"] = portfolio_analysis
            captured["watchlist"] = watchlist_symbols
            return PortfolioScenarioReport(
                status="complete",
                portfolio_analysis_status="partial",
                summary="Synthetic summary",
                horizons=(),
                symbol_research=(),
                symbols_researched=1,
                unmapped_holdings=0,
                omitted_symbols=0,
            )

    def build(_max_symbols, _horizons, *, full_workflow, portfolio_context):
        captured["full"] = full_workflow
        captured["context"] = portfolio_context
        return FakeScenarioWorkflow(), [decision]

    monkeypatch.setattr(portfolio_cli, "_make_scenario_workflow", build)

    report, omissions = portfolio_cli._run_scenarios(
        holdings,
        analytics,
        4,
        [],
        full_workflow=True,
    )

    assert report is not None
    assert omissions == []
    assert captured["full"] is True
    assert captured["context"].cash is None
    assert captured["context"].positions[0].ticker == "SYNTH"
    assert report.trading_decisions == (decision,)


def test_full_workflow_decisions_render_and_sensitive_text_is_redacted():
    now = datetime.now(UTC)
    holdings = Holdings((_holding(now),), now)
    analytics = analyze_portfolio(holdings, (), None, as_of=now)
    scenarios = PortfolioScenarioReport(
        status="complete",
        portfolio_analysis_status="partial",
        summary="Synthetic portfolio summary",
        horizons=(),
        symbol_research=(),
        symbols_researched=1,
        unmapped_holdings=0,
        omitted_symbols=0,
        trading_decisions=(
            TradingDecisionResult(
                "SYNTH",
                "Synthetic trader plan",
                "Synthetic risk debate",
                "access_token: synthetic-secret; hold the position",
                "Buy",
            ),
        ),
    )
    report = build_portfolio_report(
        mode="live",
        generated_at=now,
        request=RequestScope(
            orders_from=now.date(),
            orders_to=now.date(),
            max_pages_per_status=3,
            max_symbols=10,
            selected_symbols=["SYNTH"],
            symbol_selection="explicit",
        ),
        analytics=analytics,
        holdings=holdings,
        scenarios=scenarios,
    )

    markdown = render_markdown(report)

    assert "## Trader · Risk · 최종 결정" in markdown
    assert "Synthetic trader plan" in markdown
    assert "Synthetic risk debate" in markdown
    assert "hold the position" in markdown
    assert "synthetic-secret" not in markdown
    assert "주문을 생성하거나 실행하지 않습니다" in markdown


def test_broker_date_defaults_follow_korea_local_calendar():
    utc_evening = datetime(2026, 11, 9, 17, 30, tzinfo=UTC)

    assert portfolio_cli._today_kst(utc_evening) == date(2026, 11, 10)
    assert portfolio_cli._default_order_dates(portfolio_cli._today_kst(utc_evening)) == (
        date(2026, 10, 12),
        date(2026, 11, 10),
    )


def test_historical_end_date_gets_a_relative_30_day_default_window(monkeypatch):
    monkeypatch.setattr(
        portfolio_cli,
        "_today_kst",
        lambda now=None: date(2026, 11, 10),
    )

    start, end, symbols = portfolio_cli._validate_request(
        None, date(2026, 10, 15), None, 10
    )

    assert start == date(2026, 9, 16)
    assert end == date(2026, 10, 15)
    assert symbols == []


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


def test_full_workflow_requires_scenarios_before_broker_setup(tmp_path, monkeypatch):
    monkeypatch.delenv("TOSS_BROKER_READ_ONLY_VERIFIED", raising=False)

    result = runner.invoke(
        app,
        [
            "portfolio",
            "live",
            "--full-workflow",
            "--no-scenarios",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "--full-workflow requires --scenarios" in result.output
    assert "TOSS_BROKER_READ_ONLY_VERIFIED" not in result.output


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

        def get_transactions(self, account_seq, *, from_date=None, to_date=None):
            calls.append(("transactions", account_seq, from_date, to_date))
            return Transactions((Transaction("BUY", "STOCK", True, False),), now)

        def get_prices(self, symbols):
            calls.append(("prices", tuple(symbols)))
            return ()

        def get_candles(self, symbol, **kwargs):
            from tradingagents.portfolio.models import CandlePage

            calls.append(("candles", symbol, kwargs["interval"], kwargs["count"]))
            return CandlePage(symbol, "1d", (), now)

        def get_exchange_rate(self, base_currency, quote_currency):
            calls.append(("exchange_rate", base_currency, quote_currency))
            return ExchangeRate(
                base_currency,
                quote_currency,
                Decimal("1380"),
                Decimal("1375"),
                now - timedelta(seconds=10),
                now + timedelta(seconds=50),
                now,
            )

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
    transaction_calls = [row for row in calls if row[0] == "transactions"]
    assert transaction_calls == [("transactions", 876543210, None, None)]
    assert ("exchange_rate", "USD", "KRW") in calls

    json_path = next(tmp_path.glob("*.json"))
    markdown_path = next(tmp_path.glob("*.md"))
    raw_json = json_path.read_text(encoding="utf-8")
    report = PortfolioReport.model_validate_json(raw_json)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert report.status == "partial"
    assert report.request.orders_from.isoformat() == "2026-10-01"
    assert report.request.orders_to.isoformat() == "2026-11-01"
    assert report.request.transactions_from is None
    assert report.request.transactions_to is None
    assert report.orders.count == 1
    assert report.transactions.count == 1
    assert report.transactions.by_asset_class[0].key == "STOCK"
    assert report.fx is not None and report.fx.applied
    assert report.converted_totals is not None
    assert report.converted_totals.market_value_total == Decimal("25")
    assert report.converted_totals.buying_power_total is None
    assert report.converted_totals.portfolio_value_total is None
    assert report.source_failures == [
        "buying-power retrieval failed for USD: 분류되지 않은 API 오류 (재시도 가능: 아니요)",
        "closed order-history retrieval failed: 분류되지 않은 API 오류 (재시도 가능: 아니요)",
    ]
    assert any(source.source == "Toss Securities holdings API" for source in report.sources)
    assert any(source.source == "Toss Securities order history API" for source in report.sources)
    assert any(source.source == "Toss Securities transactions API" for source in report.sources)
    assert any(source.source == "Toss Securities exchange-rate API" for source in report.sources)
    assert "synthetic private response" not in raw_json
    assert "synthetic raw broker response" not in raw_json
    assert "987654321" not in raw_json and "876543210" not in raw_json
    assert "synthetic-order-id-must-not-be-saved" not in raw_json
    assert "누락과 실패" in markdown
    assert "주문 기간: 2026-10-01 ~ 2026-11-01" in markdown
    assert "거래내역 기간: 전체 제공 이력 ~ 상한 없음 (미결제 포함)" in markdown


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


def test_symbol_api_failure_category_is_rendered_without_exception_text():
    now = datetime.now(UTC)
    holdings = Holdings((_holding(now),), now)
    analytics = analyze_portfolio(holdings, (), None, as_of=now)
    scenarios = PortfolioScenarioReport(
        status="partial",
        portfolio_analysis_status="unknown",
        summary=None,
        horizons=(),
        symbol_research=(
            SymbolResearchResult(
                "SYNTH",
                "failed",
                None,
                "US",
                (),
                failure_category="timeout",
                retryable=True,
            ),
        ),
        symbols_researched=1,
        unmapped_holdings=0,
        omitted_symbols=0,
    )
    report = build_portfolio_report(
        mode="live",
        generated_at=now,
        request=RequestScope(
            orders_from=now.date(),
            orders_to=now.date(),
            max_pages_per_status=3,
            max_symbols=10,
            selected_symbols=["SYNTH"],
            symbol_selection="explicit",
        ),
        analytics=analytics,
        holdings=holdings,
        scenarios=scenarios,
    )

    markdown = render_markdown(report)

    assert "시간 초과 (재시도 가능: 예)" in markdown
    assert "synthetic" not in markdown.lower()


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
