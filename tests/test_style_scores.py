"""Style scores: arithmetic on what was public on the date, and a check of what followed."""

from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest

from tradingagents import style_scores
from tradingagents.style_scores import StyleSignal, evaluate_styles, score_styles


def _fact(end, val, filed):
    return {"end": end, "val": val, "filed": filed}


FACTS = {
    "Diluted EPS": [_fact("2024-12-31", 5.0, "2025-02-10")],
    "Revenue": [_fact("2023-12-31", 100.0, "2024-02-10"), _fact("2024-12-31", 120.0, "2025-02-10")],
    "Net Income": [_fact("2024-12-31", 20.0, "2025-02-10")],
    "Stockholders Equity": [_fact("2024-12-31", 100.0, "2025-02-10")],
}


def _closes(start="2024-01-01", periods=400, first=50.0, last=100.0):
    index = pd.bdate_range(start, periods=periods)
    return pd.Series([first + (last - first) * i / (periods - 1) for i in range(periods)], index=index)


@pytest.mark.unit
def test_every_style_scores_from_complete_inputs():
    closes = _closes()
    scores = score_styles("2025-06-02", closes, FACTS)

    price = float(closes[closes.index <= "2025-06-02"].iloc[-1])
    value = scores["value"]
    assert value.metrics[1].value == pytest.approx(price)
    expected_yield = 5.0 / price
    assert value.signal is (StyleSignal.BULLISH if expected_yield >= 0.06 else
                            StyleSignal.BEARISH if expected_yield <= 0.02 else StyleSignal.NEUTRAL)
    assert scores["growth"].signal is StyleSignal.BULLISH          # +20% revenue
    assert scores["quality"].signal is StyleSignal.BULLISH         # 20% return on equity
    assert scores["momentum"].signal is StyleSignal.BULLISH        # rising prices
    assert all(-1 <= s.score <= 1 for s in scores.values())
    assert scores["momentum"].horizon_days == 63 and scores["value"].horizon_days == 252


@pytest.mark.unit
def test_missing_inputs_abstain_instead_of_reading_neutral():
    scores = score_styles("2025-06-02", _closes(periods=100), None)

    assert {s.signal for s in scores.values()} == {StyleSignal.ABSTAIN}
    assert all(s.score is None and s.missing for s in scores.values())


@pytest.mark.unit
def test_a_stale_fiscal_year_is_not_the_current_state():
    scores = score_styles("2027-06-01", _closes(start="2026-01-01"), FACTS)

    assert scores["value"].signal is StyleSignal.ABSTAIN
    assert scores["growth"].signal is StyleSignal.ABSTAIN
    assert scores["quality"].signal is StyleSignal.ABSTAIN


@pytest.mark.unit
def test_prices_after_the_date_are_not_read():
    closes = _closes()
    late = closes.copy()
    late[late.index > "2025-03-03"] = 1_000_000.0

    assert score_styles("2025-03-03", closes, FACTS) == score_styles("2025-03-03", late, FACTS)


@pytest.mark.unit
def test_a_later_split_restates_the_price_in_the_filing_shares():
    # Adjusted closes state the price in post-split shares; EPS was filed before a
    # 10-for-1 split, so the price is multiplied back before the two are compared.
    closes = pd.Series([10.0], index=pd.DatetimeIndex(["2025-06-02"]))
    splits = pd.Series([10.0], index=pd.DatetimeIndex(["2025-04-01"]))

    with_split = score_styles("2025-06-02", closes, FACTS, splits)["value"]
    without = score_styles("2025-06-02", closes, FACTS)["value"]

    assert with_split.metrics[1].value == pytest.approx(100.0)
    assert with_split.signal is StyleSignal.NEUTRAL               # 5% earnings yield
    assert without.signal is StyleSignal.BULLISH                  # a 50% yield it never had


@pytest.mark.unit
def test_a_split_before_the_filing_is_already_in_the_filed_eps():
    closes = pd.Series([100.0], index=pd.DatetimeIndex(["2025-06-02"]))
    splits = pd.Series([10.0], index=pd.DatetimeIndex(["2024-06-01"]))

    assert score_styles("2025-06-02", closes, FACTS, splits)["value"].metrics[1].value == pytest.approx(100.0)


@pytest.mark.unit
def test_evaluation_scores_each_style_over_its_own_horizon():
    stock = _closes(start="2022-01-03", periods=900, first=50.0, last=150.0)
    bench = _closes(start="2022-01-03", periods=900, first=100.0, last=100.0)
    histories = {"AAA": stock, "SPY": bench}

    with mock.patch.object(style_scores, "_closes", side_effect=histories.__getitem__), \
         mock.patch.object(style_scores, "get_splits", return_value=pd.Series(dtype=float)), \
         mock.patch.object(style_scores, "_facts", return_value=None):
        result = evaluate_styles(["AAA"], ["2023-06-01", str(stock.index[-10].date())])

    momentum = result.cells["momentum"][StyleSignal.BULLISH]
    assert len(momentum.alphas) == 1 and momentum.alphas[0] > 0  # beat a flat benchmark
    assert momentum.pending == 1                                  # 63 sessions not yet traded
    assert result.abstained["value"] == 2                         # no filings, no value view
    assert "survivorship" in result.render()


@pytest.mark.unit
def test_one_unreachable_ticker_does_not_end_the_sweep():
    def closes(symbol):
        if symbol == "BAD":
            raise RuntimeError("vendor down")
        return _closes(start="2022-01-03", periods=900)

    with mock.patch.object(style_scores, "_closes", side_effect=closes), \
         mock.patch.object(style_scores, "get_splits", return_value=pd.Series(dtype=float)), \
         mock.patch.object(style_scores, "_facts", return_value=None):
        result = evaluate_styles(["BAD", "AAA"], ["2023-06-01"])

    assert result.failures == [("BAD", "vendor down")]
    assert result.cells["momentum"][StyleSignal.BULLISH].alphas or result.cells["momentum"][StyleSignal.NEUTRAL].alphas
