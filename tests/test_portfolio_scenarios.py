"""Synthetic tests for portfolio scenario collection and synthesis."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from langsmith.run_helpers import get_tracing_context, tracing_context
from langsmith.run_trees import RunTree

from tradingagents.portfolio.analytics import analyze_portfolio
from tradingagents.portfolio.models import BuyingPower, Holding, Holdings, Order, Orders
from tradingagents.portfolio.scenarios import (
    DEFAULT_HORIZONS,
    HorizonSpec,
    PortfolioScenarioWorkflow,
    ScenarioConfig,
    SymbolResearchInput,
)

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def _holding(
    symbol,
    *,
    name="Synthetic Corp",
    country="US",
    exchange="NASDAQ",
    currency="USD",
    quantity="1",
    market_value="10",
    last_price=None,
    average_purchase_price=None,
    profit_loss_after_cost=None,
):
    return Holding(
        symbol=symbol,
        name=name,
        market_country=country,
        exchange=exchange,
        currency=currency,
        quantity=Decimal(quantity),
        last_price=Decimal(last_price) if last_price is not None else None,
        average_purchase_price=(
            Decimal(average_purchase_price) if average_purchase_price is not None else None
        ),
        purchase_amount=None,
        market_value=Decimal(market_value) if market_value is not None else None,
        market_value_after_cost=None,
        profit_loss=None,
        profit_loss_after_cost=(
            Decimal(profit_loss_after_cost) if profit_loss_after_cost is not None else None
        ),
        retrieved_at=NOW,
    )


def _order(order_id, status, side, quantity, filled_quantity):
    return Order(
        order_id=order_id,
        symbol="SYNTH",
        market_country="US",
        exchange="NASDAQ",
        currency="USD",
        side=side,
        order_type="LIMIT",
        status=status,
        price=None,
        quantity=Decimal(quantity),
        order_amount=None,
        filled_quantity=Decimal(filled_quantity),
        average_filled_price=None,
        filled_amount=None,
        ordered_at=None,
        canceled_at=None,
        filled_at=None,
        retrieved_at=NOW,
    )


def _case(evidence="synthetic source supports the thesis"):
    return {
        "investment_rationale": "The stated conditions support this case.",
        "evidence": [evidence],
        "catalysts": ["A cited company update"],
        "risks": ["A cited risk could weaken this thesis"],
        "watch_conditions": ["Track the cited operating metric"],
        "review_conditions": ["Review after the next reported update"],
        "invalidation": ["The cited thesis evidence reverses"],
        "portfolio_impact": "Exposure would move with the company-specific thesis.",
        # These unsupported fields must never appear on the public case object.
        "probability": 0.8,
        "forecast_return": "25%",
        "target_price": 150,
    }


def _response(config=None, evidence="synthetic source supports the thesis"):
    config = config or ScenarioConfig()
    return json.dumps(
        {
            "summary": "Scenarios are conditional on the supplied evidence.",
            "horizons": [
                {
                    "name": horizon.name,
                    "upside": _case(evidence),
                    "base": _case(evidence),
                    "downside": _case(evidence),
                }
                for horizon in config.horizons
            ],
            "probability": 0.99,
            "target_price": 999,
        }
    )


class MockScenarioLLM:
    def __init__(self, response):
        self.response = response
        self.messages = None
        self.tracing = None

    def invoke(self, messages):
        self.messages = messages
        self.tracing = get_tracing_context()
        return self.response

    def bind_tools(self, *_args, **_kwargs):
        raise AssertionError("scenario workflow must not bind tools")

    def with_structured_output(self, *_args, **_kwargs):
        raise AssertionError("scenario workflow must not bind structured output")


def test_default_and_configured_horizons_have_all_three_cases():
    assert [(h.name, h.minimum, h.maximum, h.unit) for h in DEFAULT_HORIZONS] == [
        ("short", 1, 20, "trading_days"),
        ("medium", 1, 6, "months"),
        ("long", 6, 24, "months"),
    ]
    config = ScenarioConfig(
        horizons=(
            HorizonSpec("short", 3, 15, "trading_days"),
            HorizonSpec("medium", 2, 8, "months"),
            HorizonSpec("long", 9, 30, "months"),
        )
    )
    llm = MockScenarioLLM(_response(config))
    workflow = PortfolioScenarioWorkflow(lambda item: f"Research for {item.symbol}", llm, config)

    report = workflow.invoke(Holdings((_holding("SYNTH"),), NOW))

    assert report.portfolio_analysis_status == "unknown"
    absent_analysis = json.loads(llm.messages[1].content)["portfolio_analysis"]
    assert absent_analysis["status"] == "unknown"
    assert absent_analysis["currencies_status"] == "unknown"
    assert absent_analysis["order_history"]["status"] == "unknown"
    assert [(item.name, item.window) for item in report.horizons] == [
        ("short", "3-15 trading days"),
        ("medium", "2-8 months"),
        ("long", "9-30 months"),
    ]
    for horizon in report.horizons:
        assert horizon.upside.investment_rationale
        assert horizon.base.investment_rationale
        assert horizon.downside.investment_rationale


def test_symbol_collection_is_mapped_deduplicated_and_redacted_before_synthesis():
    secret_values = ("acct-secret", "seq-secret", "order-secret", "token-secret", "raw-api-secret")
    holdings = Holdings(
        (
            _holding(
                "synth",
                name=(
                    "Synthetic Corp accountNo: acct-secret accountSeq=seq-secret "
                    "order_id: order-secret token: token-secret"
                ),
                quantity="2",
                market_value="20",
            ),
            _holding("SYNTH", name="Repeated position", quantity="3", market_value="35"),
            _holding("OTHER", name="Other Synthetic", quantity="7", market_value="70"),
        ),
        NOW,
    )
    seen = []

    def analyzer(item: SymbolResearchInput):
        seen.append(item)
        return "Supported evidence from market research. raw_api: raw-api-secret accountNo=acct-secret"

    llm = MockScenarioLLM(_response(evidence="Data evidence from SYNTH"))
    report = PortfolioScenarioWorkflow(analyzer, llm).invoke(holdings)

    assert len(seen) == 2
    assert seen[0].symbol == "SYNTH"
    assert seen[0].market_country == "US"
    assert seen[0].company_name is not None
    assert seen[0].exposures[0].quantity == Decimal("5")
    assert seen[0].exposures[0].market_value == Decimal("55")
    assert seen[1].symbol == "OTHER"
    assert seen[1].exposures[0].quantity == Decimal("7")
    assert seen[1].exposures[0].market_value == Decimal("70")
    assert report.symbols_researched == 2
    assert len(report.symbol_research) == 2
    assert all(secret not in str(item) for item in seen for secret in secret_values)
    prompt = "\n".join(message.content for message in llm.messages)
    assert "SYNTH" in prompt
    assert all(secret not in prompt for secret in secret_values)
    assert "raw_api:" not in prompt
    assert "[REDACTED]" in prompt
    prompt_data = json.loads(llm.messages[1].content)
    synth_exposure, other_exposure = [
        item["exposures"][0] for item in prompt_data["symbol_research"]
    ]
    assert synth_exposure == {
        "currency": "USD",
        "position_count": 2,
        "quantity": "5",
        "market_value": "55",
    }
    assert other_exposure == {
        "currency": "USD",
        "position_count": 1,
        "quantity": "7",
        "market_value": "70",
    }


def test_partial_symbol_failure_keeps_success_and_marks_coverage():
    def analyzer(item):
        if item.symbol == "FAIL":
            raise RuntimeError("private provider response must not escape")
        return "Evidence from the successful synthetic company report."

    llm = MockScenarioLLM(_response(evidence="Successful symbol evidence"))
    workflow = PortfolioScenarioWorkflow(analyzer, llm)
    report = workflow.invoke(Holdings((_holding("GOOD"), _holding("FAIL")), NOW))

    assert report.status == "partial"
    assert [(row.symbol, row.status) for row in report.symbol_research] == [
        ("GOOD", "analyzed"),
        ("FAIL", "failed"),
    ]
    assert report.symbol_research[0].analysis == "Evidence from the successful synthetic company report."
    assert report.symbol_research[1].analysis is None
    assert report.symbol_research[1].failure_category == "unknown"
    assert report.symbol_research[1].retryable is False
    assert "private provider response" not in "\n".join(message.content for message in llm.messages)


def test_holdings_and_analyzer_calls_are_capped_explicitly():
    config = ScenarioConfig(max_holdings=2, max_symbol_researches=1)
    calls = []
    llm = MockScenarioLLM(_response(config))
    workflow = PortfolioScenarioWorkflow(lambda item: calls.append(item.symbol) or "Research", llm, config)
    report = workflow.invoke(
        Holdings((_holding("ONE"), _holding("ONE"), _holding("TWO"), _holding("THREE")), NOW)
    )

    assert calls == ["ONE"]
    assert report.symbols_researched == 1
    assert [(item.symbol, item.status) for item in report.symbol_research] == [
        ("ONE", "analyzed"),
        ("TWO", "not_analyzed_limit"),
    ]
    assert report.omitted_symbols == 1
    assert report.status == "partial"


def test_scenario_llm_gets_no_tools_and_retains_evidence_without_unsupported_fields():
    evidence = "Synthetic source: reported volume expanded during the period."
    llm = MockScenarioLLM(_response(evidence=evidence))
    report = PortfolioScenarioWorkflow(lambda _item: "Volume evidence is in the source report.", llm).invoke(
        Holdings((_holding("SYNTH"),), NOW)
    )

    assert [message.type for message in llm.messages] == ["system", "human"]
    assert "untrusted data" in llm.messages[0].content
    assert evidence in report.horizons[0].upside.evidence
    case = report.horizons[0].upside
    assert not hasattr(case, "probability")
    assert not hasattr(case, "forecast_return")
    assert not hasattr(case, "target_price")


def test_invalid_horizon_config_is_rejected():
    with pytest.raises(ValueError, match="horizon bounds"):
        HorizonSpec("short", 20, 1, "trading_days")


def test_portfolio_analytics_prompt_uses_allowlisted_financial_and_coverage_facts():
    holdings = Holdings(
        (
            _holding(
                "SYNTH",
                quantity="2",
                market_value="24",
                last_price="12",
                average_purchase_price="10",
                profit_loss_after_cost="3",
            ),
            _holding(
                "005930",
                country="KR",
                exchange="KRX",
                currency="KRW",
                quantity="1",
                market_value="100",
                last_price="100",
                average_purchase_price="80",
                profit_loss_after_cost="19",
            ),
        ),
        NOW,
        as_of=NOW,
    )
    buying_power = (
        BuyingPower("USD", Decimal("5"), NOW),
        BuyingPower("KRW", Decimal("25"), NOW),
    )
    orders = Orders(
        (
            _order("order-secret-1", "FILLED", "BUY", "3", "2"),
            _order("order-secret-2", "OPEN", "SELL", "4", "0"),
        ),
        NOW,
        has_more=True,
        coverage_warnings=("accountNo: account-secret",),
    )
    analysis = analyze_portfolio(
        holdings,
        buying_power,
        orders,
        fx_rate=Decimal("0.001"),
        fx_timestamp=NOW,
        as_of=NOW,
    )
    llm = MockScenarioLLM(_response())
    report = PortfolioScenarioWorkflow(lambda _item: "Synthetic evidence.", llm).invoke(
        holdings, portfolio_analysis=analysis
    )

    facts = json.loads(llm.messages[1].content)["portfolio_analysis"]
    assert report.portfolio_analysis_status == "partial"
    assert report.status == "partial"
    usd = next(row for row in facts["currencies"] if row["currency"] == "USD")
    assert usd["market_value_total"] == "24"
    assert usd["profit_loss_total"] == "4"
    assert usd["profit_loss_status"] == "known_complete"
    assert usd["buying_power_total"] == "5"
    assert usd["buying_power_is_cash_balance"] is False
    assert usd["currency_weight"] is not None
    assert all(row["currency_weight"] is not None for row in facts["currencies"])
    assert {row["key"] for row in facts["concentrations"]["by_symbol"]} == {
        "SYNTH",
        "005930.KS",
    }
    assert facts["order_history"]["count"] == 2
    assert facts["order_history"]["status"] == "partial"
    assert facts["order_history"]["known_ordered_quantity_subtotal"] == "7"
    assert facts["order_history"]["known_filled_quantity_subtotal"] == "2"
    assert {row["status"] for row in facts["order_history"]["by_status"]} == {"FILLED", "OPEN"}
    assert any(source["source"] == "holdings" and source["as_of"] == NOW.isoformat() for source in facts["sources"])
    prompt = llm.messages[1].content
    assert "order-secret" not in prompt
    assert "account-secret" not in prompt
    assert "accountNo" not in prompt


def test_incomplete_portfolio_analysis_keeps_unknown_values_unknown():
    holdings = Holdings((_holding("SYNTH", market_value=None),), NOW)
    analysis = analyze_portfolio(holdings)
    llm = MockScenarioLLM(_response())
    report = PortfolioScenarioWorkflow(lambda _item: "Synthetic evidence.", llm).invoke(
        holdings, portfolio_analysis=analysis
    )

    facts = json.loads(llm.messages[1].content)["portfolio_analysis"]
    assert report.portfolio_analysis_status == "partial"
    assert report.status == "partial"
    assert facts["currencies_status"] == "partial"
    assert facts["currencies"][0]["market_value_total"] is None
    assert facts["currencies"][0]["profit_loss_status"] == "unknown"
    assert facts["buying_power"]["status"] == "unknown"
    assert facts["order_history"]["status"] == "unknown"


def test_watchlist_symbols_are_analyzed_without_inventing_holding_exposure():
    seen = []

    def analyzer(item):
        seen.append(item)
        return f"Synthetic research for {item.symbol}."

    llm = MockScenarioLLM(_response())
    report = PortfolioScenarioWorkflow(analyzer, llm).invoke(
        Holdings((), NOW),
        watchlist_symbols=(("MSFT", "US"), ("005930.KS", "KR")),
    )

    assert [item.symbol for item in seen] == ["MSFT", "005930.KS"]
    assert all(item.portfolio_relation == "watchlist" for item in seen)
    assert all(item.exposures == () for item in seen)
    assert all(row.portfolio_relation == "watchlist" for row in report.symbol_research)
    prompt_symbols = json.loads(llm.messages[1].content)["symbol_research"]
    assert all(row["portfolio_relation"] == "watchlist" for row in prompt_symbols)
    assert all(row["exposures"] == [] for row in prompt_symbols)


def test_watchlist_rejects_ambiguous_or_unsupported_korean_ticker():
    workflow = PortfolioScenarioWorkflow(lambda _item: "Synthetic.", MockScenarioLLM(_response()))
    with pytest.raises(ValueError, match=r"\.KS or \.KQ"):
        workflow.invoke(Holdings((), NOW), watchlist_symbols=(("005930", "KR"),))


def test_workflow_disables_langsmith_tracing_for_analyzer_and_model(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    observed = {}

    def analyzer(_item):
        observed["analyzer"] = get_tracing_context()
        return "Synthetic evidence."

    llm = MockScenarioLLM(_response())
    outer_parent = RunTree(name="outer", inputs={})
    with tracing_context(enabled=True, parent=outer_parent):
        assert get_tracing_context()["enabled"] is True
        report = PortfolioScenarioWorkflow(analyzer, llm).invoke(
            Holdings((_holding("SYNTH"),), NOW)
        )
        assert get_tracing_context()["enabled"] is True
        assert get_tracing_context()["parent"] is outer_parent

    assert report.status == "partial"
    assert observed["analyzer"]["enabled"] is False
    assert observed["analyzer"]["parent"] is None
    assert llm.tracing["enabled"] is False
    assert llm.tracing["parent"] is None


def _synthesis_with_names(names, key="name"):
    return json.dumps(
        {
            "summary": "Scenarios are conditional on the supplied evidence.",
            "horizons": [
                {key: name, "upside": _case(), "base": _case(), "downside": _case()}
                for name in names
            ],
        }
    )


@pytest.mark.parametrize(
    ("names", "key"),
    [
        (["Short-term", "medium (1-6 months)", "LONG"], "name"),
        (["long", "short", "medium"], "name"),
        (["short", "medium", "long"], "horizon"),
    ],
)
def test_synthesis_accepts_horizon_name_variants_in_configured_order(names, key):
    from tradingagents.portfolio.scenarios import _parse_synthesis

    _, horizons = _parse_synthesis(_synthesis_with_names(names, key), ScenarioConfig())

    assert [row.name for row in horizons] == ["short", "medium", "long"]


@pytest.mark.parametrize(
    "names",
    [["short", "medium"], ["short", "Short-term", "long"], ["short", "medium", "year"]],
)
def test_synthesis_rejects_missing_or_duplicate_horizons(names):
    from tradingagents.portfolio.scenarios import _parse_synthesis

    with pytest.raises(ValueError, match="horizons do not match"):
        _parse_synthesis(_synthesis_with_names(names), ScenarioConfig())
