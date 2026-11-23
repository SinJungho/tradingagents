import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.chart_check import add_retry_state, compare_chart_csv
from tradingagents.dataflows.chart_zones import (
    _candidates,
    _pivots,
    _rank_directional_zones,
    compute_chart_zones,
    get_chart_zones_with_snapshot,
    resolve_as_of,
)


@pytest.fixture(autouse=True)
def isolate_local_validation_state(monkeypatch):
    unverified = {
        "status": "not_evaluated", "sample": None, "evaluated_at": None, "lift": None, "ci95": None,
        "latest_evaluation": None, "last_passed_evaluation": None,
        "effective_status": "not_evaluated", "latest_sample": None, "pending": False, "stale": False,
    }
    monkeypatch.setattr("tradingagents.zone_validation.current_validation", lambda as_of: {
        "support_resistance": unverified.copy(), "inside": unverified.copy(),
        "latest_sample": None, "pending": False, "stale": False,
        "chart_validation": {"status": "not_evaluated"},
    })


def _bars(count=720):
    dates = xcals.get_calendar("XNYS").sessions_in_range("2023-01-02", "2027-11-18")[:count]
    dates = dates.tz_localize(None)
    i = np.arange(count, dtype=np.float64)
    close = 100 + i * 0.025 + 8 * np.sin(i / 13) + 2 * np.sin(i / 3)
    return pd.DataFrame({
        "Open": close - 0.3,
        "High": close + 1.2 + 0.3 * np.sin(i),
        "Low": close - 1.1 - 0.2 * np.cos(i),
        "Close": close,
        "Volume": 1_000_000 + i,
    }, index=dates)


def test_chart_zones_are_reproducible_and_ignore_future_rows():
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    expected = compute_chart_zones(bars, "SYN", as_of)
    repeated = compute_chart_zones(bars.copy(), "SYN", as_of)
    extended = bars.copy()
    extended.loc[extended.index > pd.Timestamp(as_of), ["High", "Low", "Close"]] *= 5

    assert expected == repeated
    assert expected == compute_chart_zones(extended, "SYN", as_of)
    assert expected["snapshot_sha256"]
    assert expected["status"] == "ok"
    for zone in expected["zones"]:
        assert zone["touches"] == len(zone["touch_points"])
        assert all(point["confirmed_at"] <= as_of for point in zone["touch_points"])
    assert sum(zone["type"] == "inside" for zone in expected["zones"]) <= 1
    intervals = sorted((zone["lower"], zone["upper"]) for zone in expected["zones"])
    assert all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:], strict=False))


def test_chart_zones_hash_matches_saved_snapshot_bytes(monkeypatch):
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    monkeypatch.setattr("tradingagents.dataflows.chart_zones.route_to_vendor",
                        lambda method, *args, **kwargs: bars.copy() if method == "get_chart_history" else
                        [pd.Timestamp(bars.index[600]).tz_localize("America/New_York") + pd.Timedelta(hours=17)])

    result, snapshot = get_chart_zones_with_snapshot("SYN", as_of)
    assert result["anchored_vwap"]["earnings"]["anchor_date"] == bars.index[601].date().isoformat()
    actual_hash = hashlib.sha256(snapshot.to_csv(
        index_label="Date", float_format="%.6f", lineterminator="\n"
    ).encode()).hexdigest()

    assert actual_hash == result["snapshot_sha256"]
    assert snapshot.index[-1].date().isoformat() == result["as_of"]


def test_chart_zones_mark_short_history_insufficient():
    bars = _bars(300)
    as_of = "2024-02-23"
    result = compute_chart_zones(bars, "SYN", as_of)
    assert result["status"] == "insufficient"
    assert result["bars"] == int((bars.index <= pd.Timestamp(as_of)).sum())


def test_nonpositive_or_unavailable_asof_atr_is_not_used_as_zero():
    bars = _bars()
    bars["Open"] = bars["High"] = bars["Low"] = bars["Close"] = 100.0

    result = compute_chart_zones(bars, "FLAT", bars.index[-1].date().isoformat())

    assert result["status"] == "insufficient"
    assert result["reason"] == "atr_unavailable_or_nonpositive"
    assert any(item["kind"] == "atr_unavailable_or_nonpositive" for item in result["unknowns"])


def test_missing_xnys_session_is_reported_and_breaks_the_pivot_series():
    bars = _bars()
    missing = bars.index[350].date().isoformat()
    bars = bars.drop(bars.index[350])

    result = compute_chart_zones(bars, "SYN", bars.index[-1].date().isoformat())

    assert {missing} <= set(result["unknowns"][0]["dates"])


def test_current_date_uses_latest_completed_et_session():
    now = datetime.fromisoformat("2025-07-04T18:00:00-04:00").astimezone(ZoneInfo("America/New_York"))
    assert resolve_as_of("2025-07-04", now=now) == "2025-07-03"


def test_initial_zigzag_direction_skips_same_day_two_sided_confirmation():
    bars = pd.DataFrame({
        "High": [100, 101, 111, 112], "Low": [95, 90, 100, 104],
    })
    pivots = _pivots(bars, np.array([5.0, 5.0, 5.0, 5.0]))

    assert pivots == [{"index": 1, "kind": "low", "price": 90, "confirmed": 3}]


def test_zigzag_pivot_is_absent_until_the_confirmation_bar_is_in_as_of():
    bars = pd.DataFrame({"High": [100, 101, 108, 112], "Low": [95, 90, 98, 104]})
    atr = np.full(len(bars), 5.0)

    assert _pivots(bars.iloc[:3], atr[:3]) == []
    assert _pivots(bars, atr) == [{"index": 1, "kind": "low", "price": 90, "confirmed": 3}]


def test_kde_keeps_two_modes_with_stable_lower_price_tie_order():
    pivots = [
        {"index": 10, "price": 99.9}, {"index": 11, "price": 100.1},
        {"index": 10, "price": 109.9}, {"index": 11, "price": 110.1},
    ]
    atr = np.ones(20)

    zones = _candidates(pivots, atr, count=20, recency_halflife=189)

    assert len(zones) == 2
    assert [zone["peak"] for zone in zones] == sorted(zone["peak"] for zone in zones)
    assert all(zone["lower"] < zone["peak"] < zone["upper"] for zone in zones)
    assert zones[0]["upper"] < zones[1]["lower"]
    assert [len(zone["pivots"]) for zone in zones] == [2, 2]
    assert zones == _candidates(pivots, atr, count=20, recency_halflife=189)
    log_prices = np.log([pivot["price"] for pivot in pivots])
    widths = np.asarray([atr[pivot["index"]] / pivot["price"] * 0.5 for pivot in pivots])
    step = np.median([atr[pivot["index"]] / pivot["price"] for pivot in pivots]) * 0.05
    grid = np.arange(min(log_prices - 6 * widths), max(log_prices + 6 * widths) + step, step)
    assert all(zone["lower"] > np.exp(grid[0]) and zone["upper"] < np.exp(grid[-1]) for zone in zones)


def test_directional_score_ties_use_lower_price_and_preserve_exact_ties():
    first = {"distance_atr": 1.0, "score": 2.0, "lower": 99.0, "label": "first"}
    second = {"distance_atr": 1.0, "score": 2.0, "lower": 99.0, "label": "second"}
    lower_price = {"distance_atr": 1.0, "score": 2.0, "lower": 98.0, "label": "lower"}

    assert _rank_directional_zones([first, second, lower_price]) == [lower_price, first, second]


def test_reaction_window_stops_at_as_of_even_when_future_highs_change(monkeypatch):
    import tradingagents.dataflows.chart_zones as chart_zones

    bars = _bars()
    as_of_index = 620
    as_of = bars.index[as_of_index].date().isoformat()
    pivot_index = as_of_index - 5
    pivot = {"index": pivot_index, "kind": "low", "price": float(bars["Low"].iloc[pivot_index]),
             "confirmed": pivot_index + 1}
    monkeypatch.setattr(chart_zones, "_atr", lambda data, breaks=None: np.ones(len(data)))
    monkeypatch.setattr(chart_zones, "_pivots", lambda data, atr, breaks=None: [pivot])
    monkeypatch.setattr(chart_zones, "_candidates", lambda *args: [
        {"lower": pivot["price"] - 0.25, "upper": pivot["price"] + 0.25,
         "pivots": [pivot]},
    ])

    baseline = compute_chart_zones(bars, "SYN", as_of)
    changed_future = bars.copy()
    changed_future.loc[changed_future.index > pd.Timestamp(as_of), "High"] += 1000

    assert compute_chart_zones(changed_future, "SYN", as_of) == baseline
    assert baseline["zones"][0]["touch_points"][0]["reaction_bars"] == 5


def test_penetration_count_increases_after_close_reenters_zone(monkeypatch):
    import tradingagents.dataflows.chart_zones as chart_zones

    bars = _bars()
    as_of_index = 640
    as_of = bars.index[as_of_index].date().isoformat()
    pivot_index = 610
    pivot = {"index": pivot_index, "kind": "low", "price": 90.5, "confirmed": pivot_index + 1}
    for index, close in ((620, 89.0), (621, 90.5), (622, 89.0), (623, 90.5)):
        bars.iloc[index, bars.columns.get_loc("Open")] = close
        bars.iloc[index, bars.columns.get_loc("High")] = close + 0.5
        bars.iloc[index, bars.columns.get_loc("Low")] = close - 0.5
        bars.iloc[index, bars.columns.get_loc("Close")] = close
    monkeypatch.setattr(chart_zones, "_atr", lambda data, breaks=None: np.ones(len(data)))
    monkeypatch.setattr(chart_zones, "_pivots", lambda data, atr, breaks=None: [pivot])
    monkeypatch.setattr(chart_zones, "_candidates", lambda *args: [
        {"lower": 90.0, "upper": 91.0, "pivots": [pivot]},
    ])

    result = compute_chart_zones(bars, "SYN", as_of)
    zone = result["zones"][0]
    touch = zone["touch_points"][0]
    expected_score = 0.5 ** ((result["bars"] - pivot_index - 1) / 189) * touch["reaction_atr"] * 0.25

    assert zone["type"] == "support"
    assert zone["score"] == round(expected_score, 6)


def test_invalid_ohlc_is_reported_and_excluded_from_calculation():
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    invalid_day = bars.index[500]
    bars.loc[invalid_day, "Low"] = -1

    result = compute_chart_zones(bars, "SYN", as_of)

    assert result["status"] == "ok"
    assert any(item["kind"] == "invalid_ohlc" and invalid_day.date().isoformat() in item["dates"]
               for item in result["unknowns"])


def test_missing_final_requested_session_is_reported_before_as_of_fallback():
    bars = _bars()
    missing = bars.index[-1].date().isoformat()
    bars = bars.iloc[:-1]

    result = compute_chart_zones(bars, "SYN", missing)

    assert result["as_of"] == bars.index[-1].date().isoformat()
    assert any(item["kind"] == "missing_trailing_xnys_sessions" and missing in item["dates"]
               for item in result["unknowns"])


def test_chart_check_accepts_timezone_dates_and_ignores_bars_after_as_of(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    dates = ["2025-01-02", "2025-01-03"]
    snapshot = pd.DataFrame({"Date": dates, "Open": [10, 11], "High": [12, 13],
                            "Low": [9, 10], "Close": [11, 12], "Volume": [100, 101]})
    snapshot.to_csv(run / "snapshot.csv", index=False)
    zones = {"ticker": "SYN", "as_of": dates[-1], "snapshot_sha256": "abc",
             "latest_ex_dividend_date": None,
             "check_windows": {"recent_20": {"dates": dates, "count": 2}}}
    (run / "zones.json").write_text(json.dumps(zones))
    chart = tmp_path / "chart.csv"
    chart.write_text("date,o,h,l,c,v\n2025-01-02T00:00:00-05:00,10,12,9,11,7\n"
                     "2025-01-03T00:00:00-05:00,11,13,10,12,8\n"
                     "2025-01-04T00:00:00-05:00,12,14,11,13,9\n")

    result = compare_chart_csv(str(run), str(chart))

    assert result["status"] == "ok"
    assert result["rows"] == 2
    assert result["dates_after_as_of"] == ["2025-01-04"]


def test_chart_check_detects_price_mismatch(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    pd.DataFrame({"Date": ["2025-01-02"], "Open": [10], "High": [12],
                  "Low": [9], "Close": [11], "Volume": [100]}).to_csv(run / "snapshot.csv", index=False)
    (run / "zones.json").write_text(json.dumps({
        "ticker": "SYN", "as_of": "2025-01-02", "snapshot_sha256": "abc",
        "check_windows": {"recent_20": {"dates": ["2025-01-02"], "count": 1}},
    }))
    chart = tmp_path / "chart.csv"
    chart.write_text("date,o,h,l,c,v\n2025-01-02,20,24,18,22,0\n")

    assert compare_chart_csv(str(run), str(chart))["status"] == "mismatch"


def test_chart_check_tracks_range_and_data_retries_independently():
    first = add_retry_state({"status": "insufficient"})
    second = add_retry_state({"status": "mismatch"}, first)
    third = add_retry_state({"status": "mismatch"}, second)

    assert first["retry_action"] == "set_range"
    assert second["attempt"] == 2
    assert second["range_retry_count"] == 1
    assert second["retry_action"] == "get_chart_data"
    assert third["data_retry_count"] == 1
    assert third["retry_action"] is None
    assert third["status"] == "mismatch"
    assert [attempt["status"] for attempt in third["attempts"]] == ["insufficient", "mismatch", "mismatch"]


def test_chart_check_allows_only_one_retry_per_kind():
    first = add_retry_state({"status": "insufficient"})
    second = add_retry_state({"status": "insufficient"}, first)
    mismatch = add_retry_state({"status": "mismatch"}, second)
    final = add_retry_state({"status": "mismatch"}, mismatch)

    assert second["range_retry_count"] == 1
    assert second["retry_action"] is None
    assert mismatch["retry_action"] == "get_chart_data"
    assert final["data_retry_count"] == 1
    assert final["retry_action"] is None


def test_chart_check_accepts_raw_repeated_header_blocks_per_window(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    dates = ["2025-01-02", "2025-01-03"]
    pd.DataFrame({"Date": dates, "Open": [10, 11], "High": [12, 13],
                  "Low": [9, 10], "Close": [11, 12], "Volume": [100, 101]}).to_csv(
                      run / "snapshot.csv", index=False)
    windows = {
        "recent_20": {"dates": dates, "count": 2},
        "dividend": {"dates": [dates[1]], "count": 1},
        "oldest_first_touch": {"dates": [dates[0]], "count": 1},
    }
    (run / "zones.json").write_text(json.dumps({"ticker": "SYN", "as_of": dates[-1],
                                                  "snapshot_sha256": "abc",
                                                  "check_windows": windows}))
    chart = tmp_path / "chart.csv"
    chart.write_text(
        "date,o,h,l,c,v\n2025-01-02,10,12,9,11,7\n2025-01-03,11,13,10,12,8\n\n"
        "date,o,h,l,c,v\n2025-01-03,11,13,10,12,8\n\n"
        "date,o,h,l,c,v\n2025-01-02,10,12,9,11,7\n"
    )

    result = compare_chart_csv(str(run), str(chart))

    assert result["status"] == "ok"
    assert result["rows"] == 4
    assert {window["window"] for window in result["windows"]} == set(windows)


def test_chart_check_normalizes_timezone_crossing_into_et_date(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    pd.DataFrame({"Date": ["2025-01-02"], "Open": [10], "High": [12],
                  "Low": [9], "Close": [11], "Volume": [100]}).to_csv(run / "snapshot.csv", index=False)
    (run / "zones.json").write_text(json.dumps({
        "ticker": "SYN", "as_of": "2025-01-02", "snapshot_sha256": "abc",
        "check_windows": {"recent_20": {"dates": ["2025-01-02"], "count": 1}},
    }))
    chart = tmp_path / "chart.csv"
    chart.write_text("date,o,h,l,c,v\n2025-01-03T02:00:00+02:00,10,12,9,11,1\n")

    assert compare_chart_csv(str(run), str(chart))["status"] == "ok"


def test_chart_check_rejects_duplicate_dates_and_reports_missing_dates(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    dates = ["2025-01-02", "2025-01-03"]
    pd.DataFrame({"Date": dates, "Open": [10, 11], "High": [12, 13],
                  "Low": [9, 10], "Close": [11, 12], "Volume": [100, 101]}).to_csv(
                      run / "snapshot.csv", index=False)
    (run / "zones.json").write_text(json.dumps({
        "ticker": "SYN", "as_of": dates[-1], "snapshot_sha256": "abc",
        "check_windows": {"recent_20": {"dates": dates, "count": 2}},
    }))
    chart = tmp_path / "chart.csv"
    chart.write_text("date,o,h,l,c,v\n2025-01-02,10,12,9,11,1\n2025-01-02,10,12,9,11,1\n")
    duplicate = compare_chart_csv(str(run), str(chart))
    chart.write_text("date,o,h,l,c,v\n2025-01-02,10,12,9,11,1\n")
    missing = compare_chart_csv(str(run), str(chart))

    assert duplicate["reason"] == "duplicate_dates"
    assert missing["status"] == "insufficient"
    assert missing["missing_dates"] == ["2025-01-03"]


def test_chart_check_accepts_exact_price_tolerance_and_rejects_overage(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    pd.DataFrame({"Date": ["2025-01-02"], "Open": [10], "High": [12],
                  "Low": [9], "Close": [11], "Volume": [100]}).to_csv(run / "snapshot.csv", index=False)
    (run / "zones.json").write_text(json.dumps({
        "ticker": "SYN", "as_of": "2025-01-02", "snapshot_sha256": "abc",
        "check_windows": {"recent_20": {"dates": ["2025-01-02"], "count": 1}},
    }))
    chart = tmp_path / "chart.csv"
    chart.write_text("date,o,h,l,c,v\n2025-01-02,10.01,12,9,11,1\n")
    at_boundary = compare_chart_csv(str(run), str(chart))
    chart.write_text("date,o,h,l,c,v\n2025-01-02,10.0101,12,9,11,1\n")
    over_boundary = compare_chart_csv(str(run), str(chart))

    assert at_boundary["status"] == "ok"
    assert over_boundary["status"] == "mismatch"


def test_chart_check_cli_accepts_input_already_in_run_directory(tmp_path):
    from typer.testing import CliRunner

    from cli.main import app

    run = tmp_path / "run"
    run.mkdir()
    dates = ["2025-01-02"]
    pd.DataFrame({"Date": dates, "Open": [10], "High": [12], "Low": [9],
                  "Close": [11], "Volume": [100]}).to_csv(run / "snapshot.csv", index=False)
    (run / "zones.json").write_text(json.dumps({
        "ticker": "SYN", "as_of": dates[0], "snapshot_sha256": "abc",
        "check_windows": {"recent_20": {"dates": dates, "count": 1}},
    }))
    (run / "chart_check.csv").write_text("date,o,h,l,c,v\n2025-01-02,10,12,9,11,1\n")

    result = CliRunner().invoke(app, ["chart-check", "--run-dir", str(run),
                                      "--chart-csv", str(run / "chart_check.csv"), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "ok"


def test_fib_retracement_anchors_last_confirmed_swing_and_flags_breaks():
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    result = compute_chart_zones(bars, "SYN", as_of)
    fib = result["fib_retracement"]
    data = bars.loc[:as_of]

    assert fib["status"] in {"ok", "invalidated"}
    start, end = fib["start"], fib["end"]
    assert start["date"] < end["date"] and end["confirmed_at"] <= as_of
    assert {start["kind"], end["kind"]} == {"low", "high"}
    for anchor in (start, end):
        assert anchor["price"] == round(float(data.loc[anchor["date"], anchor["kind"].title()]), 6)
        window = result["check_windows"][f"fib_{'start' if anchor is start else 'end'}"]
        assert anchor["date"] in window["dates"] and window["count"] == len(window["dates"])
    span = end["price"] - start["price"]
    assert fib["levels"]["0.5"] == pytest.approx(end["price"] - 0.5 * span, abs=1e-6)
    later = data.loc[data.index > pd.Timestamp(end["date"])]
    beyond = (later["High"] > end["price"]).any() if fib["direction"] == "up" else (later["Low"] < end["price"]).any()
    assert (fib["reason"] == "new_extreme_after_end") == bool(beyond)


def test_fib_retracement_is_unavailable_without_two_pivots():
    bars = _bars()
    bars[["Open", "High", "Low", "Close"]] = bars[["Open", "High", "Low", "Close"]].iloc[0].to_numpy()
    bars["High"] += 0.01
    bars["Low"] -= 0.01
    result = compute_chart_zones(bars, "FLAT", bars.index[640].date().isoformat())

    assert result["fib_retracement"]["status"] == "unavailable"
    assert not any(name.startswith("fib_") for name in result["check_windows"])


def test_anchored_vwap_matches_manual_typical_price_average():
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    release = pd.Timestamp(bars.index[620]).tz_localize("America/New_York") + pd.Timedelta(hours=8)
    future = pd.Timestamp(bars.index[650]).tz_localize("America/New_York")
    result = compute_chart_zones(bars, "SYN", as_of, earnings_dates=[future, release])
    earnings = result["anchored_vwap"]["earnings"]
    part = bars.iloc[620:641]
    typical = (part["High"] + part["Low"] + part["Close"]) / 3
    expected = float((typical * part["Volume"]).sum() / part["Volume"].sum())

    assert earnings["status"] == "ok" and earnings["release_time_known"] is True
    assert earnings["anchor_date"] == bars.index[620].date().isoformat()
    assert earnings["value"] == pytest.approx(expected, abs=1e-6)
    assert earnings["values"][-1] == [as_of, earnings["value"]]
    assert result["check_windows"]["avwap_earnings"]["anchor_date"] == earnings["anchor_date"]
    swing = result["anchored_vwap"]["swing_start"]
    assert swing["anchor_date"] == result["fib_retracement"]["start"]["date"]
    assert swing["values"][0][0] == swing["anchor_date"]


def test_anchored_vwap_reports_missing_earnings_and_volume():
    bars = _bars()
    as_of = bars.index[640].date().isoformat()
    assert compute_chart_zones(bars, "SYN", as_of)["anchored_vwap"]["earnings"]["reason"] == \
        "earnings_dates_unavailable"
    bars.loc[bars.index[630], "Volume"] = np.nan
    release = pd.Timestamp(bars.index[620]).tz_localize("America/New_York")
    earnings = compute_chart_zones(bars, "SYN", as_of, earnings_dates=[release])["anchored_vwap"]["earnings"]

    assert earnings["status"] == "unavailable" and earnings["reason"] == "volume_missing_after_anchor"
    assert earnings["release_time_known"] is False
