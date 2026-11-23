import exchange_calendars as xcals
import numpy as np
import pandas as pd

from tradingagents.zone_backtest import (
    evaluate_sample_frames,
    evaluate_zone_event,
    generate_baselines,
    paired_block_bootstrap,
    prepare_sample_history,
    summarize_event_results,
    training_as_of_grid,
    validate_backtest_history,
)


def _future_frame(count=70):
    dates = xcals.get_calendar("XNYS").sessions_in_range("2025-01-02", "2025-06-30")[:count]
    dates = dates.tz_localize(None)
    return pd.DataFrame({
        "Open": np.full(len(dates), 102.0), "High": np.full(len(dates), 103.0),
        "Low": np.full(len(dates), 101.0), "Close": np.full(len(dates), 102.0),
        "Volume": np.ones(len(dates)),
    }, index=dates)


def test_touch_bar_is_excluded_and_success_is_checked_from_next_bar():
    frame = _future_frame()
    as_of = frame.index[0].date().isoformat()
    frame.iloc[1, frame.columns.get_loc("Low")] = 101.0
    frame.iloc[1, frame.columns.get_loc("High")] = 110.0
    frame.iloc[1, frame.columns.get_loc("Close")] = 102.0
    frame.iloc[2, frame.columns.get_loc("High")] = 104.0

    result = evaluate_zone_event(frame, as_of, {"type": "support", "lower": 100, "upper": 102}, 2)

    assert result["status"] == "hit"
    assert result["touch_date"] == frame.index[1].date().isoformat()
    assert result["outcome_date"] == frame.index[2].date().isoformat()


def test_same_bar_success_and_failure_after_touch_is_failure():
    frame = _future_frame()
    as_of = frame.index[0].date().isoformat()
    frame.iloc[1, frame.columns.get_loc("Low")] = 101.0
    frame.iloc[2, frame.columns.get_loc("High")] = 104.0
    frame.iloc[2, frame.columns.get_loc("Low")] = 98.0
    frame.iloc[2, frame.columns.get_loc("Close")] = 98.5

    result = evaluate_zone_event(frame, as_of, {"type": "support", "lower": 100, "upper": 102}, 2)

    assert result["status"] == "failed"
    assert result["same_bar_conflict"] is True
    assert result["outcome_date"] == frame.index[2].date().isoformat()


def test_no_touch_unresolved_missing_data_and_insufficient_future_are_distinct():
    frame = _future_frame()
    as_of = frame.index[0].date().isoformat()
    no_touch = evaluate_zone_event(frame, as_of, {"type": "support", "lower": 85, "upper": 90}, 2)

    touched = frame.copy()
    touched.iloc[1, touched.columns.get_loc("Low")] = 101.0
    unresolved = evaluate_zone_event(touched, as_of, {"type": "support", "lower": 100, "upper": 102}, 2)
    missing = frame.copy()
    missing.iloc[3, missing.columns.get_loc("Low")] = np.nan
    unknown = evaluate_zone_event(missing, as_of, {"type": "support", "lower": 100, "upper": 102}, 2)
    short = evaluate_zone_event(frame.iloc[:10], as_of,
                                {"type": "support", "lower": 100, "upper": 102}, 2)

    assert no_touch["status"] == "not_touched"
    assert unresolved["status"] == "touched_unresolved"
    assert unknown["status"] == "unresolved_data"
    assert short["status"] == "insufficient_future"


def test_missing_xnys_session_inside_future_window_is_unknown_not_skipped():
    frame = _future_frame()
    as_of = frame.index[0].date().isoformat()
    missing_day = frame.index[10].date().isoformat()
    frame = frame.drop(frame.index[10])

    result = evaluate_zone_event(frame, as_of, {"type": "support", "lower": 100, "upper": 102}, 2)

    assert result["status"] == "unresolved_data"
    assert result["unknown_date"] == missing_day


def test_sample_history_excludes_ionq_pre_first_trade_rows():
    sessions = xcals.get_calendar("XNYS").sessions_in_range("2021-09-20", "2021-10-12")
    frame = pd.DataFrame({"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0,
                          "Volume": 100}, index=sessions.tz_localize(None))

    result, bounds = prepare_sample_history("IONQ", frame)

    assert result.index[0].date().isoformat() == "2021-10-01"
    assert bounds == {"eligibility_start": "2021-10-01", "excluded_pre_eligibility_rows": 9}


def test_sample_history_excludes_missing_rate_over_one_percent():
    frame = _future_frame()
    frame = frame.drop(frame.index[[4, 9, 14]])

    result = validate_backtest_history("SYN", frame)

    assert result["status"] == "excluded"
    assert "missing_bar_rate_gt_1pct" in result["reason"]
    assert result["missing_bar_count"] == 3


def test_sample_history_rejects_unexplained_fifty_percent_jump_but_accepts_split():
    frame = _future_frame()
    frame["Stock Splits"] = 0.0
    frame.iloc[10:, frame.columns.get_loc("Open"):frame.columns.get_loc("Close") + 1] *= 0.5

    unexplained = validate_backtest_history("SYN", frame)
    frame.iloc[10, frame.columns.get_loc("Stock Splits")] = 2.0
    explained = validate_backtest_history("SYN", frame)

    assert unexplained["status"] == "excluded"
    assert "unexplained_daily_price_jump" in unexplained["reason"]
    assert explained["status"] == "ok"


def test_inside_zone_uses_last_close_outside_to_set_direction():
    frame = _future_frame()
    frame.iloc[0, frame.columns.get_loc("Close")] = 110.0
    frame.iloc[0, frame.columns.get_loc("Open")] = 109.0
    frame.iloc[0, frame.columns.get_loc("High")] = 111.0
    frame.iloc[1, frame.columns.get_loc("Close")] = 102.0
    frame.iloc[2, frame.columns.get_loc("Open")] = 105.0
    frame.iloc[2, frame.columns.get_loc("High")] = 106.0
    frame.iloc[2, frame.columns.get_loc("Low")] = 104.0
    frame.iloc[2, frame.columns.get_loc("Close")] = 105.0
    frame.iloc[3, frame.columns.get_loc("Open")] = 105.0
    frame.iloc[3, frame.columns.get_loc("High")] = 107.0
    frame.iloc[3, frame.columns.get_loc("Low")] = 104.0
    frame.iloc[3, frame.columns.get_loc("Close")] = 105.5

    result = evaluate_zone_event(frame, frame.index[1].date().isoformat(),
                                 {"type": "inside", "lower": 100, "upper": 105}, 2)

    assert result["direction"] == "support"
    assert result["status"] == "hit"
    assert result["touch_date"] == frame.index[1].date().isoformat()
    assert result["outcome_date"] == frame.index[3].date().isoformat()


def test_inside_zone_without_a_prior_outside_close_is_direction_unknown():
    frame = _future_frame()
    frame.iloc[0, frame.columns.get_loc("Close")] = 102.0
    frame.iloc[0, frame.columns.get_loc("Open")] = 102.0
    frame.iloc[0, frame.columns.get_loc("High")] = 103.0
    frame.iloc[0, frame.columns.get_loc("Low")] = 101.0

    result = evaluate_zone_event(frame, frame.index[0].date().isoformat(),
                                 {"type": "inside", "lower": 100, "upper": 105}, 2)

    assert result["status"] == "direction_unknown"
    assert result["eligible"] is False
    assert result["direction"] is None


def test_inside_same_bar_success_and_failure_is_conservatively_failed():
    frame = _future_frame()
    as_of = frame.index[1].date().isoformat()
    frame.iloc[0, frame.columns.get_loc("Close")] = 110.0
    frame.iloc[0, frame.columns.get_loc("Open")] = 109.0
    frame.iloc[0, frame.columns.get_loc("High")] = 111.0
    frame.iloc[0, frame.columns.get_loc("Low")] = 108.0
    frame.iloc[2, frame.columns.get_loc("Open")] = 102.0
    frame.iloc[2, frame.columns.get_loc("High")] = 108.0
    frame.iloc[2, frame.columns.get_loc("Low")] = 97.0
    frame.iloc[2, frame.columns.get_loc("Close")] = 98.0

    result = evaluate_zone_event(frame, as_of, {"type": "inside", "lower": 100, "upper": 105}, 2)

    assert result["status"] == "failed"
    assert result["same_bar_conflict"] is True
    assert result["touch_date"] == as_of
    assert result["outcome_date"] == frame.index[2].date().isoformat()


def test_baselines_are_deterministic_and_matched_on_width_and_distance():
    zones = [
        {"type": "support", "lower": 98.0, "upper": 99.0},
        {"type": "resistance", "lower": 111.0, "upper": 112.0},
        {"type": "inside", "lower": 100.0, "upper": 105.0},
    ]
    first = generate_baselines("SYN", "2025-01-02", zones, close=105.0, atr=1.0, count=5)
    second = generate_baselines("SYN", "2025-01-02", zones, close=105.0, atr=1.0, count=5)

    assert first == second
    assert all(row["status"] == "ok" for row in first)
    for row, actual in zip(first, zones, strict=True):
        assert len(row["random_unconditional"]) == 5
        assert len(row["matched"]) == 5
        for control in row["matched"]:
            assert control["type"] == actual["type"]
            if actual["type"] == "inside":
                assert control["lower"] <= 105.0 <= control["upper"]
                assert abs(control["width_log"] - np.log(actual["upper"] / actual["lower"])) < 1e-6
            else:
                assert abs(control["width_atr"] - 1.0) <= 0.05
                assert abs((control["upper"] - control["lower"]) - 1.0) <= 0.05
                distance = ((105.0 - control["upper"]) if actual["type"] == "support"
                            else control["lower"] - 105.0)
                assert abs(distance - 6.0) <= 0.25
                assert abs(control["distance_atr"] - 6.0) <= 0.25


def test_matched_baseline_keeps_actual_overlap_and_counts_it():
    result = generate_baselines(
        "SYN", "2025-01-02", [{"type": "support", "lower": 98.0, "upper": 99.0}],
        close=105.0, atr=1.0, count=100,
    )[0]

    assert result["status"] == "ok"
    assert len(result["matched"]) == 100
    assert result["matched_overlap_count"] > 0
    assert any(row["upper"] >= 98.0 and row["lower"] <= 99.0 for row in result["matched"])


def test_failed_random_resampling_is_marked_unmatched():
    result = generate_baselines("SYN", "2025-01-02",
                                [{"type": "support", "lower": 99.5, "upper": 100.0}],
                                close=100.1, atr=1.0, count=2, max_draws=1)

    assert result[0]["status"] == "unmatched"
    assert result[0]["random_unconditional"] == []
    assert result[0]["matched"] == []


def test_baseline_generation_stops_after_one_thousand_failed_draws():
    result = generate_baselines(
        "SYN", "2025-01-02", [{"type": "support", "lower": 90.0, "upper": 99.9}],
        close=100.0, atr=1.0, max_draws=1000,
    )[0]

    assert result["status"] == "unmatched"
    assert result["random_rejections"] == 1000
    assert result["random_unconditional"] == []
    assert len(result["matched"]) == 200


def test_paired_hierarchical_bootstrap_is_reproducible_and_keeps_pairs():
    dates = pd.date_range("2024-11-01", periods=50, freq="7D").strftime("%Y-%m-%d")
    pairs = [{"ticker": f"T{ticker:02d}", "as_of": as_of, "eligible": True,
              "actual_hit": index % 2 == 0, "baseline_rate": 0.2}
             for ticker in range(10) for index, as_of in enumerate(dates)]
    kwargs = {"sample_id": "v1@test", "block_length": 6, "repetitions": 300}

    first = paired_block_bootstrap(pairs, **kwargs)
    second = paired_block_bootstrap(pairs, **kwargs)
    three = paired_block_bootstrap(pairs, sample_id="v1@test", block_length=3, repetitions=300)
    three_again = paired_block_bootstrap(pairs, sample_id="v1@test", block_length=3, repetitions=300)
    twelve = paired_block_bootstrap(pairs, sample_id="v1@test", block_length=12, repetitions=300)

    assert first == second
    assert first["status"] == "ok"
    assert first["lift"] == 0.3
    assert first["ci95"][0] <= first["lift"] <= first["ci95"][1]
    assert first["seed"] == second["seed"]
    assert three["status"] == "ok"
    assert three == three_again
    assert three["method"] == "ticker_cluster_then_circular_time_blocks"
    assert three["tickers"] == 10
    assert three["dates"] == 50
    assert twelve["status"] == "inconclusive"
    assert twelve["reason"] == "fewer_than_six_time_blocks"


def test_bootstrap_zero_denominator_replicates_are_inconclusive(monkeypatch):
    import tradingagents.zone_backtest as zone_backtest

    class EmptyChoice:
        def __init__(self, _bit_generator):
            pass

        def choice(self, _values, size, replace):
            return []

    monkeypatch.setattr(zone_backtest.np.random, "Generator", EmptyChoice)
    pairs = [{"ticker": "SYN", "as_of": f"2025-01-{day:02d}", "eligible": True,
              "actual_hit": True, "baseline_rate": 0.2}
             for day in range(1, 19)]

    result = paired_block_bootstrap(pairs, sample_id="v1@zero", block_length=3, repetitions=10)

    assert result["status"] == "inconclusive"
    assert result["reason"] == "too_many_zero_denominators"
    assert result["zero_denominator_replicates"] == 10
    assert result["ci95"] is None


def test_bootstrap_without_matched_pairs_has_no_denominator():
    result = paired_block_bootstrap([], sample_id="v1@empty", block_length=3, repetitions=10)

    assert result["status"] == "inconclusive"
    assert result["reason"] == "no_matched_pairs"
    assert result["ci95"] is None


def test_event_metrics_separate_conditional_and_effective_success_rates():
    result = summarize_event_results([
        {"status": "hit", "eligible": True}, {"status": "failed", "eligible": True},
        {"status": "not_touched", "eligible": True}, {"status": "touched_unresolved", "eligible": True},
        {"status": "direction_unknown", "eligible": False},
    ])

    assert result["eligible_zones"] == 4
    assert result["conditional_hit_rate"] == 0.5
    assert result["effective_hit_rate"] == 0.25
    assert result["touch_rate"] == 0.75
    assert result["direction_unknown"] == 1


def test_tune_dates_respect_full_sixty_session_embargo_before_validation():
    dates = training_as_of_grid("2019-01-01", "2024-08-31", "2024-11-01")
    calendar = xcals.get_calendar("XNYS")

    assert dates
    assert all(len(calendar.sessions_in_range(day, "2024-11-01")) - 1 > 60 for day in dates)
    assert dates[-1] < "2024-08-31"


def test_evaluate_sample_frames_reuses_ticker_history_and_session_windows(monkeypatch):
    import tradingagents.zone_backtest as backtest

    normalize = backtest._frame
    session_cache = backtest._expected_evaluation_sessions
    session_cache.cache_clear()
    normalization_calls = 0

    def count_normalization(frame):
        nonlocal normalization_calls
        normalization_calls += 1
        return normalize(frame)

    monkeypatch.setattr(backtest, "_frame", count_normalization)
    dates = xcals.get_calendar("XNYS").sessions_in_range("2023-01-03", "2026-01-30")[:720]
    dates = dates.tz_localize(None)
    index = np.arange(len(dates), dtype=np.float64)
    close = 100 + index * 0.02 + 7 * np.sin(index / 11) + np.sin(index / 2)
    frame = pd.DataFrame({"Open": close - 0.2, "High": close + 1.1,
                          "Low": close - 1.0, "Close": close, "Volume": 1000}, index=dates)
    as_of = dates[600].date().isoformat()

    result = evaluate_sample_frames({"SYN": frame}, [as_of], sample_id="v1@test",
                                    control_count=2, bootstrap_repetitions=20)

    assert normalization_calls == 1
    assert session_cache.cache_info().misses == 1
    session_cache.cache_clear()
    assert result["sample"] == "v1@test"
    assert result["actual_events"]
    assert set(result["results"]) == {"support_resistance", "inside"}
    assert "conditional_hit_rate" in result["results"]["support_resistance"]["actual"]
    assert "effective_hit_rate" in result["results"]["support_resistance"]["matched"]
    assert all(value["status"] == "inconclusive" for value in result["results"].values())
    assert all(value["sample_size"]["minimums"]["as_of_dates"] == 50
               for value in result["results"].values())


def test_validation_record_locks_sample_from_later_tuning(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from cli.main import app
    from tradingagents.zone_samples import write_sample
    from tradingagents.zone_validation import append_evaluation

    sample_root = tmp_path / "samples"
    output_root = tmp_path / "backtest"
    sample = write_sample(holdings=[], priority_tickers=[],
                          retrieved_at="2026-11-18T12:00:00+00:00", root=sample_root)
    evaluation_root = output_root / "evaluations"
    append_evaluation({
        "sample": sample["sample_id"], "params_version": "v1", "baseline_version": "matched-v1",
        "evaluated_at": "2026-11-18T12:00:00+00:00", "quarter_index": 2026 * 4 + 3,
        "results": {"support_resistance": {"status": "inconclusive"},
                    "inside": {"status": "inconclusive"}},
    }, evaluation_root)
    calls = []
    monkeypatch.setattr("tradingagents.dataflows.router.route_to_vendor",
                        lambda *args, **kwargs: calls.append(args))

    result = CliRunner().invoke(app, [
        "zone-backtest", "run", "--period", "tune", "--sample-dir", str(sample_root),
        "--output-dir", str(output_root),
    ])

    assert result.exit_code == 2
    assert "validation holdout is locked" in result.output
    assert calls == []
    assert not (output_root / "inputs").exists()
