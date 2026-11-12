"""Synthetic-only tests for the deterministic report review gate."""

import pytest

from tradingagents.output_quality import QualityWarning, review_output
from tradingagents.reporting import write_report_tree


def _parts(*, trader="", manager="", analyst=""):
    parts = []
    if analyst:
        parts.append(("I. Analyst Team Reports", "1_analysts", [("Market Analyst", "market.md", analyst)]))
    if trader:
        parts.append(("III. Trading Team Plan", "3_trading", [("Trader", "trader.md", trader)]))
    if manager:
        parts.append(("V. Portfolio Manager Decision", "5_portfolio", [("Portfolio Manager", "decision.md", manager)]))
    return parts


@pytest.mark.unit
def test_numeric_claims_match_tool_values_without_editing_the_report():
    original = "Target price: 100.00 USD."
    warnings = review_output(
        {"tool_evidence_numbers": ["100"]}, "AAPL", _parts(manager=original)
    )

    assert warnings == ()
    assert original == _parts(manager=original)[0][2][0][2]


@pytest.mark.unit
def test_unsupported_numeric_claim_has_a_stable_location_and_reason():
    state = {"tool_evidence_numbers": ["100.00"]}
    parts = _parts(manager="Target price: 137.00 USD.")

    first = review_output(state, "AAPL", parts)
    second = review_output(state, "AAPL", parts)

    assert first == second == (
        QualityWarning(
            "Portfolio Manager · line 1",
            "Numeric claim candidate (137.00) has no matching supplied tool value or supported calculation.",
        ),
    )


@pytest.mark.unit
def test_supported_percent_calculation_uses_provided_inputs():
    warnings = review_output(
        {"tool_evidence_numbers": ["100.00", "110.00"]},
        "AAPL",
        _parts(trader="Return is (110 - 100) / 100 = 10%."),
    )

    assert warnings == ()


@pytest.mark.unit
@pytest.mark.parametrize("claim", [
    "Return is (110 - 100) / 100 = 9%.",
    "Return is 9% from 100 to 110.",
    "목표 수익률은 9%입니다.",
])
def test_unmatched_or_wrong_calculations_are_flagged_in_english_and_korean(claim):
    warnings = review_output(
        {"tool_evidence_numbers": ["100", "110"]}, "AAPL", _parts(trader=claim)
    )

    assert len(warnings) == 1
    assert warnings[0].location == "Trader · line 1"
    assert "Numeric claim candidate" in warnings[0].reason


@pytest.mark.unit
@pytest.mark.parametrize(("quantity", "text", "expected"), [
    (5, "Start a new position in AAPL.", "long"),
    (0, "Maintain your current position in AAPL.", "flat"),
    (-2, "You are long AAPL.", "short"),
    (-2, "AAPL 롱 보유 중입니다.", "short"),
    (5, "현재 AAPL 포지션이 없으므로 신규 진입한다.", "long"),
])
def test_direct_holdings_conflicts_follow_signed_positions(quantity, text, expected):
    state = {
        "portfolio_context_provided": True,
        "portfolio_positions": [{"ticker": "AAPL", "quantity": quantity}],
    }

    warnings = review_output(state, "AAPL", _parts(manager=text))

    assert len(warnings) == 1
    assert f"provided portfolio is {expected}" in warnings[0].reason


@pytest.mark.unit
def test_ticker_normalization_unknown_status_and_conditional_language():
    conflicting = review_output(
        {"portfolio_context_provided": True,
         "portfolio_positions": [{"ticker": "BTCUSDT", "quantity": -2}]},
        "BTC-USD",
        _parts(trader="You are long BTC."),
    )
    unknown = review_output(
        {}, "AAPL", _parts(manager="You currently hold AAPL.")
    )
    conditional = review_output(
        {}, "AAPL", _parts(trader="If you already hold AAPL, maintain your position.")
    )

    assert len(conflicting) == 1 and "portfolio is short" in conflicting[0].reason
    assert len(unknown) == 1 and "status was not provided" in unknown[0].reason
    assert conditional == ()


@pytest.mark.unit
def test_recommendation_ratings_alone_do_not_imply_holdings_conflicts():
    ratings_only = review_output(
        {"portfolio_context_provided": True, "portfolio_positions": []},
        "AAPL",
        _parts(manager="Rating: Hold. Buy after confirmation."),
    )
    explicit_flat = review_output(
        {"portfolio_context_provided": True, "portfolio_positions": []},
        "AAPL",
        _parts(manager="You have no current position in AAPL."),
    )

    assert ratings_only == explicit_flat == ()


@pytest.mark.unit
def test_same_location_and_reason_are_rendered_in_markdown_and_html(tmp_path):
    trader = "Start a new position in AAPL."
    manager = "Target price: 137.00 USD.\nYou currently have no position in AAPL."
    state = {
        "trader_investment_plan": trader,
        "final_trade_decision": manager,
        "portfolio_context_provided": True,
        "portfolio_positions": [{"ticker": "AAPL", "quantity": 5}],
        "tool_evidence_numbers": ["100"],
    }

    write_report_tree(state, "AAPL", tmp_path, html=True)

    markdown = (tmp_path / "complete_report.md").read_text(encoding="utf-8")
    html = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    trader_file = (tmp_path / "3_trading" / "trader.md").read_text(encoding="utf-8")
    warning = QualityWarning(
        "Portfolio Manager · line 1",
        "Numeric claim candidate (137.00) has no matching supplied tool value or supported calculation.",
    )

    assert f"**Location:** {warning.location}; **Reason:** {warning.reason}" in markdown
    assert warning.location in html and warning.reason in html
    assert trader_file == trader
    assert trader in markdown and manager in markdown
