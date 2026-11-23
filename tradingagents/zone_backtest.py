"""Event outcomes and deterministic baselines for daily chart-zone research."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from functools import lru_cache

import exchange_calendars as xcals
import numpy as np
import pandas as pd

BASELINE_VERSION = "matched-random-v1"
RANDOM_ZONE_COUNT = 200
MAX_REJECTION_DRAWS = 1_000
SUPPORT_SUCCESS_ATR = 1.0
SUPPORT_FAILURE_ATR = 0.5
EVALUATION_BARS = 60
MATCH_WIDTH_CALIPER_ATR = 0.05
MATCH_DISTANCE_CALIPER_ATR = 0.25

_OHLC = ("Open", "High", "Low", "Close")
_FINAL_STATUSES = {"hit", "failed", "not_touched", "touched_unresolved"}


def _frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.index = pd.DatetimeIndex(pd.to_datetime(data.index).date)
    data = data.loc[~data.index.duplicated(keep="first")].sort_index()
    if any(column not in data for column in _OHLC):
        raise ValueError("Backtest bars must contain Open, High, Low, and Close.")
    return data


@lru_cache(maxsize=512)
def _expected_evaluation_sessions(as_of: str, evaluation_bars: int) -> tuple:
    as_of_date = pd.Timestamp(as_of)
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(
        as_of_date, as_of_date + pd.Timedelta(days=max(120, evaluation_bars * 2))
    )
    return tuple(session.date() for session in sessions[1:evaluation_bars + 1])


def _valid_ohlc(row: pd.Series) -> bool:
    values = row.loc[list(_OHLC)].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values <= 0).any():
        return False
    open_, high, low, close = values
    return high >= max(open_, close) and low <= min(open_, close) and high >= low


def _inside_direction(data: pd.DataFrame, as_of_index: int, lower: float, upper: float) -> str | None:
    for close in data["Close"].iloc[:as_of_index].iloc[::-1]:
        if not np.isfinite(close) or close <= 0:
            continue
        if close > upper:
            return "support"
        if close < lower:
            return "resistance"
    return None


def evaluate_zone_event(
    frame: pd.DataFrame,
    as_of: str,
    zone: dict,
    atr: float,
    *,
    evaluation_bars: int = EVALUATION_BARS,
    _normalized: bool = False,
) -> dict:
    """Classify one zone using the first future touch and following daily bars.

    The touch bar is never used to decide success. With daily OHLC, the order
    within that bar cannot be recovered. If the next evaluation bar crosses
    both barriers, it is counted as failure.
    """
    data = frame if _normalized else _frame(frame)
    as_of_date = pd.Timestamp(as_of)
    exact = np.flatnonzero(data.index == as_of_date)
    if not len(exact):
        return {"status": "missing_as_of", "eligible": False, "touch_date": None,
                "outcome_date": None, "direction": None}
    origin = int(exact[0])
    lower, upper = float(zone["lower"]), float(zone["upper"])
    if not np.isfinite(atr) or atr <= 0 or lower <= 0 or lower > upper:
        return {"status": "invalid_zone_or_atr", "eligible": False, "touch_date": None,
                "outcome_date": None, "direction": None}
    kind = zone.get("type")
    direction = kind
    inside_activation = kind == "inside"
    if kind == "inside":
        direction = _inside_direction(data, origin, lower, upper)
        if direction is None:
            return {"status": "direction_unknown", "eligible": False, "touch_date": None,
                    "outcome_date": None, "direction": None}
    if direction not in {"support", "resistance"}:
        return {"status": "invalid_zone_type", "eligible": False, "touch_date": None,
                "outcome_date": None, "direction": direction}
    expected = pd.DatetimeIndex(_expected_evaluation_sessions(
        as_of_date.date().isoformat(), evaluation_bars
    ))
    if len(expected) < evaluation_bars or data.index[-1] < expected[-1]:
        return {"status": "insufficient_future", "eligible": False, "touch_date": None,
                "outcome_date": None, "direction": direction}
    missing = expected.difference(data.index)
    if len(missing):
        return {"status": "unresolved_data", "eligible": False, "touch_date": None,
                "outcome_date": None, "direction": direction,
                "unknown_date": missing[0].date().isoformat()}
    future = data.loc[expected]

    touch_date = as_of_date.date().isoformat() if inside_activation else None
    for day, row in future.iterrows():
        if not _valid_ohlc(row):
            return {"status": "unresolved_data", "eligible": False, "touch_date": touch_date,
                    "outcome_date": None, "direction": direction, "unknown_date": day.date().isoformat()}
        if not inside_activation and touch_date is None:
            touched = row["Low"] <= upper if direction == "support" else row["High"] >= lower
            if touched:
                touch_date = day.date().isoformat()
            continue

        success = (row["High"] >= upper + SUPPORT_SUCCESS_ATR * atr if direction == "support"
                   else row["Low"] <= lower - SUPPORT_SUCCESS_ATR * atr)
        failure = (row["Close"] <= lower - SUPPORT_FAILURE_ATR * atr if direction == "support"
                   else row["Close"] >= upper + SUPPORT_FAILURE_ATR * atr)
        if success and failure:
            return {"status": "failed", "eligible": True, "touch_date": touch_date,
                    "outcome_date": day.date().isoformat(), "direction": direction,
                    "same_bar_conflict": True}
        if failure:
            return {"status": "failed", "eligible": True, "touch_date": touch_date,
                    "outcome_date": day.date().isoformat(), "direction": direction,
                    "same_bar_conflict": False}
        if success:
            return {"status": "hit", "eligible": True, "touch_date": touch_date,
                    "outcome_date": day.date().isoformat(), "direction": direction,
                    "same_bar_conflict": False}
    if touch_date is None:
        return {"status": "not_touched", "eligible": True, "touch_date": None,
                "outcome_date": None, "direction": direction}
    return {"status": "touched_unresolved", "eligible": True, "touch_date": touch_date,
            "outcome_date": None, "direction": direction}


def _seed(ticker: str, as_of: str, zone_type: str, baseline_version: str) -> int:
    value = f"{ticker}|{as_of}|{zone_type}|{baseline_version}".encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def _control_zone(lower: float, upper: float, zone_type: str) -> dict:
    return {"type": zone_type, "lower": float(lower), "upper": float(upper)}


def _overlaps(a_lower: float, a_upper: float, b_lower: float, b_upper: float) -> bool:
    return a_lower <= b_upper and b_lower <= a_upper


def generate_baselines(
    ticker: str,
    as_of: str,
    zones: list[dict],
    close: float,
    atr: float,
    *,
    baseline_version: str = BASELINE_VERSION,
    count: int = RANDOM_ZONE_COUNT,
    max_draws: int = MAX_REJECTION_DRAWS,
) -> list[dict]:
    """Create unconditional and width/distance-matched controls in rank order."""
    if count < 1 or max_draws < 1 or close <= 0 or atr <= 0:
        raise ValueError("Baseline inputs must be positive and count must be nonzero.")
    output = []
    by_type: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for rank, zone in enumerate(zones, start=1):
        by_type[zone["type"]].append((rank, zone))

    for zone_type, ranked_zones in sorted(by_type.items()):
        random_rng = np.random.Generator(np.random.PCG64(
            _seed(ticker, as_of, zone_type, f"{baseline_version}:random-unconditional")
        ))
        matched_rng = np.random.Generator(np.random.PCG64(
            _seed(ticker, as_of, zone_type, f"{baseline_version}:matched")
        ))
        for rank, actual in ranked_zones:
            actual_lower, actual_upper = float(actual["lower"]), float(actual["upper"])
            if actual_lower <= 0 or actual_lower >= actual_upper:
                output.append({"rank": rank, "type": zone_type, "status": "invalid_actual_zone",
                               "random_unconditional": [], "matched": []})
                continue
            actual_log_width = math.log(actual_upper / actual_lower)
            actual_width_atr = (actual_upper - actual_lower) / atr
            actual_direction = ("support" if actual_upper < close else
                                "resistance" if actual_lower > close else "inside")
            if zone_type == "inside":
                actual_direction = "inside"
            elif actual_direction != zone_type:
                output.append({"rank": rank, "type": zone_type, "status": "zone_crosses_current_price",
                               "random_unconditional": [], "matched": []})
                continue
            distance = ((close - actual_upper) / atr if actual_direction == "support" else
                        (actual_lower - close) / atr if actual_direction == "resistance" else 0.0)
            random_zones: list[dict] = []
            matched_zones: list[dict] = []
            random_failed = matched_failed = matched_overlapping = 0

            for _ in range(max_draws):
                if len(random_zones) >= count:
                    break
                if actual_direction == "inside":
                    log_center = math.log(close) + float(random_rng.uniform(-actual_log_width / 2,
                                                                            actual_log_width / 2))
                    lower, upper = math.exp(log_center - actual_log_width / 2), math.exp(
                        log_center + actual_log_width / 2
                    )
                else:
                    log_center = (math.log(actual_lower) + math.log(actual_upper)) / 2 + float(
                        random_rng.uniform(-3 * atr / close, 3 * atr / close)
                    )
                    lower, upper = math.exp(log_center - actual_log_width / 2), math.exp(
                        log_center + actual_log_width / 2
                    )
                    if actual_direction == "support" and upper >= close:
                        random_failed += 1
                        continue
                    if actual_direction == "resistance" and lower <= close:
                        random_failed += 1
                        continue
                    if _overlaps(lower, upper, actual_lower, actual_upper):
                        random_failed += 1
                        continue
                random_zones.append(_control_zone(lower, upper, actual_direction))

            for _ in range(max_draws):
                if len(matched_zones) >= count:
                    break
                if actual_direction == "inside":
                    log_center = math.log(close) + float(matched_rng.uniform(-actual_log_width / 2,
                                                                             actual_log_width / 2))
                    lower, upper = math.exp(log_center - actual_log_width / 2), math.exp(
                        log_center + actual_log_width / 2
                    )
                else:
                    width_atr = actual_width_atr + float(
                        matched_rng.uniform(-MATCH_WIDTH_CALIPER_ATR, MATCH_WIDTH_CALIPER_ATR)
                    )
                    matched_distance = distance + float(
                        matched_rng.uniform(-MATCH_DISTANCE_CALIPER_ATR, MATCH_DISTANCE_CALIPER_ATR)
                    )
                    if width_atr <= 0 or matched_distance <= 0:
                        matched_failed += 1
                        continue
                    if actual_direction == "support":
                        upper = close - matched_distance * atr
                        lower = upper - width_atr * atr
                    else:
                        lower = close + matched_distance * atr
                        upper = lower + width_atr * atr
                    if lower <= 0:
                        matched_failed += 1
                        continue
                    if _overlaps(lower, upper, actual_lower, actual_upper):
                        matched_overlapping += 1
                matched_zone = _control_zone(lower, upper, actual_direction)
                matched_zone["distance_atr"] = round(
                    float((close - upper) / atr if actual_direction == "support"
                          else (lower - close) / atr if actual_direction == "resistance" else 0.0), 6
                )
                matched_zone["width_atr"] = round(float((upper - lower) / atr), 6)
                if actual_direction == "inside":
                    matched_zone["width_log"] = round(math.log(upper / lower), 6)
                matched_zones.append(matched_zone)

            complete = len(random_zones) == count and len(matched_zones) == count
            output.append({
                "rank": rank,
                "type": zone_type,
                "status": "ok" if complete else "unmatched",
                "random_unconditional": random_zones if len(random_zones) == count else [],
                "matched": matched_zones if len(matched_zones) == count else [],
                "random_rejections": random_failed,
                "matched_rejections": matched_failed,
                "matched_overlap_count": matched_overlapping,
            })
    return sorted(output, key=lambda result: result["rank"])


def summarize_event_results(events: list[dict]) -> dict:
    """Report conditional, eligible-zone, and touch metrics with separate counts."""
    counts = Counter(event.get("status", "unknown") for event in events)
    eligible = [event for event in events if event.get("eligible") and event.get("status") in _FINAL_STATUSES]
    hits = sum(event["status"] == "hit" for event in eligible)
    failures = sum(event["status"] == "failed" for event in eligible)
    touched = sum(event["status"] in {"hit", "failed", "touched_unresolved"} for event in eligible)
    resolved = hits + failures
    return {
        "eligible_zones": len(eligible),
        "hits": hits,
        "failures": failures,
        "not_touched": counts["not_touched"],
        "touched_unresolved": counts["touched_unresolved"],
        "unresolved_data": counts["unresolved_data"],
        "direction_unknown": counts["direction_unknown"],
        "insufficient_future": counts["insufficient_future"],
        "unmatched": counts["unmatched"],
        "touch_rate": touched / len(eligible) if eligible else None,
        "conditional_hit_rate": hits / resolved if resolved else None,
        "effective_hit_rate": hits / len(eligible) if eligible else None,
    }


def _paired_rates(events: list[dict], controls: list[dict]) -> list[dict]:
    controls_by_key: dict[tuple[str, str, str, int], list[dict]] = defaultdict(list)
    for control in controls:
        controls_by_key[(control["ticker"], control["as_of"], control["zone_type"], control["rank"])].append(control)
    pairs = []
    for event in events:
        if not event.get("eligible") or event.get("status") not in _FINAL_STATUSES:
            continue
        key = (event["ticker"], event["as_of"], event["zone_type"], event["rank"])
        matched = controls_by_key.get(key, [])
        eligible_controls = [row for row in matched if row.get("eligible") and row.get("status") in _FINAL_STATUSES]
        if not eligible_controls:
            continue
        pairs.append({
            "ticker": event["ticker"],
            "as_of": event["as_of"],
            "zone_type": event["zone_type"],
            "volatility_group": event.get("volatility_group", "unclassified"),
            "touch_date": event.get("touch_date"),
            "actual_hit": event["status"] == "hit",
            "baseline_rate": sum(row["status"] == "hit" for row in eligible_controls) / len(eligible_controls),
            "eligible": True,
            "control_count": len(eligible_controls),
        })
    return pairs


def _paired_lift(pairs: list[dict]) -> float | None:
    if not pairs:
        return None
    return round(float(np.mean([float(row["actual_hit"]) - row["baseline_rate"] for row in pairs])), 6)


def _sample_gate(pairs: list[dict]) -> tuple[bool, dict]:
    tickers = len({row["ticker"] for row in pairs})
    dates = len({row["as_of"] for row in pairs})
    episodes = len({(row["ticker"], row["zone_type"], row["touch_date"])
                    for row in pairs if row.get("touch_date")})
    enough = tickers >= 10 and dates >= 50 and episodes >= 100
    return enough, {"tickers": tickers, "as_of_dates": dates, "touch_episodes": episodes,
                    "minimums": {"tickers": 10, "as_of_dates": 50, "touch_episodes": 100}}


def build_as_of_grid(start: str, end: str, *, every_sessions: int = 20) -> list[str]:
    """Create stable XNYS as-of dates at a fixed valid-session interval."""
    if every_sessions < 1 or start > end:
        raise ValueError("Invalid as-of grid range or session interval.")
    sessions = xcals.get_calendar("XNYS").sessions_in_range(start, end)
    return [session.date().isoformat() for session in sessions[::every_sessions]]


def training_as_of_grid(
    start: str,
    end: str,
    validation_start: str,
    *,
    every_sessions: int = 20,
    embargo_sessions: int = EVALUATION_BARS,
) -> list[str]:
    """Exclude tuning dates whose full outcome window reaches validation."""
    candidates = build_as_of_grid(start, end, every_sessions=every_sessions)
    calendar = xcals.get_calendar("XNYS")
    validation = pd.Timestamp(validation_start)
    return [as_of for as_of in candidates
            if len(calendar.sessions_in_range(as_of, validation)) - 1 > embargo_sessions]


def validation_end_date(frames: dict[str, pd.DataFrame], *, future_bars: int = EVALUATION_BARS) -> str:
    """End validation before any ticker's final unobserved outcome window."""
    if not frames or future_bars < 1:
        raise ValueError("Validation needs daily frames and a positive future window.")
    last_dates = []
    for frame in frames.values():
        data = _frame(frame)
        valid = data[["Open", "High", "Low", "Close"]].apply(np.isfinite).all(axis=1)
        last_dates.append(data.index[valid][-1])
    common_end = min(last_dates)
    sessions = xcals.get_calendar("XNYS").sessions_in_range(common_end - pd.Timedelta(days=365), common_end)
    if len(sessions) <= future_bars:
        raise ValueError("Not enough completed XNYS sessions for the outcome window.")
    return sessions[-future_bars - 1].date().isoformat()


def prepare_sample_history(ticker: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply preregistered issuer-history bounds before hashing sample inputs."""
    data = _frame(frame)
    first_date = "2021-10-01" if ticker.upper() == "IONQ" else None
    if first_date is None:
        return data, {"eligibility_start": None, "excluded_pre_eligibility_rows": 0}
    excluded = int((data.index < pd.Timestamp(first_date)).sum())
    return data.loc[data.index >= pd.Timestamp(first_date)].copy(), {
        "eligibility_start": first_date, "excluded_pre_eligibility_rows": excluded,
    }


def validate_backtest_history(ticker: str, frame: pd.DataFrame) -> dict:
    """Apply the sample's missing-session and unexplained price-jump exclusions."""
    data = _frame(frame)
    if data.empty:
        return {"status": "excluded", "reason": "no_market_data"}
    ohlc = data[list(_OHLC)].to_numpy(dtype=np.float64)
    valid = np.isfinite(ohlc).all(axis=1)
    if valid.any():
        rows = ohlc[valid]
        valid_indexes = np.flatnonzero(valid)
        geometry = ((rows[:, 1] >= np.maximum(rows[:, 0], rows[:, 3]))
                    & (rows[:, 2] <= np.minimum(rows[:, 0], rows[:, 3]))
                    & (rows[:, 1] >= rows[:, 2]) & (rows > 0).all(axis=1))
        valid[valid_indexes] = geometry
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(data.index[0], data.index[-1])
    expected = pd.DatetimeIndex([session.date() for session in sessions])
    present = data.index[valid]
    missing_dates = expected.difference(present)
    missing_rate = len(missing_dates) / len(expected) if len(expected) else 1.0

    session_positions = {day: index for index, day in enumerate(expected)}
    close = data["Close"].to_numpy(dtype=np.float64)
    splits = data.get("Stock Splits", pd.Series(0.0, index=data.index))
    split_values = pd.to_numeric(splits, errors="coerce").fillna(0).to_numpy(dtype=np.float64)
    jumps = []
    valid_positions = np.flatnonzero(valid)
    for left, right in zip(valid_positions[:-1], valid_positions[1:], strict=True):
        previous_date, current_date = data.index[left], data.index[right]
        if session_positions.get(current_date, -10) - session_positions.get(previous_date, 10) != 1:
            continue
        if close[left] <= 0 or close[right] <= 0:
            continue
        ratio = close[right] / close[left]
        if abs(ratio - 1.0) < 0.5:
            continue
        split = split_values[right]
        split_explains = split > 0 and abs(np.log(ratio * split)) <= np.log(1.2)
        if not split_explains:
            jumps.append({"date": current_date.date().isoformat(),
                          "close_ratio": round(float(ratio), 6)})

    reasons = []
    if missing_rate > 0.01:
        reasons.append("missing_bar_rate_gt_1pct")
    if jumps:
        reasons.append("unexplained_daily_price_jump")
    return {
        "status": "excluded" if reasons else "ok",
        "reason": ",".join(reasons) if reasons else None,
        "ticker": ticker.upper(), "missing_bar_count": len(missing_dates),
        "expected_sessions": len(expected), "missing_bar_rate": round(float(missing_rate), 8),
        "missing_dates_sample": [day.date().isoformat() for day in missing_dates[:20]],
        "unexplained_jumps": jumps,
    }


def training_volatility_cutoffs(
    frames: dict[str, pd.DataFrame],
    as_of_dates: list[str],
    *,
    primary_tickers: set[str],
) -> dict:
    """Calculate and persist training-only tercile thresholds for ATR percent."""
    from tradingagents.dataflows.chart_zones import compute_chart_zones

    values = []
    for ticker in sorted(primary_tickers & set(frames)):
        frame = frames[ticker]
        for as_of in as_of_dates:
            result = compute_chart_zones(frame, ticker, as_of, include_validation=False)
            if result.get("status") == "ok" and result["close"] > 0:
                values.append(result["atr14"] / result["close"])
    if len(values) < 3:
        raise ValueError("Insufficient tuning ATR observations to define volatility terciles.")
    low, high = np.quantile(values, [1 / 3, 2 / 3], method="linear")
    return {"low_high_cutoffs": [round(float(low), 8), round(float(high), 8)],
            "observations": len(values), "method": "pooled primary-sample ATR14/close terciles",
            "training_dates": [as_of_dates[0], as_of_dates[-1]] if as_of_dates else []}


def evaluate_sample_frames(
    frames: dict[str, pd.DataFrame],
    as_of_dates: list[str],
    *,
    sample_id: str,
    ticker_cohorts: dict[str, str] | None = None,
    ticker_order: list[str] | None = None,
    eligibility_dates: dict[str, str] | None = None,
    baseline_version: str = BASELINE_VERSION,
    volatility_cutoffs: tuple[float, float] | None = None,
    recency_halflife: int = 189,
    control_count: int = RANDOM_ZONE_COUNT,
    bootstrap_repetitions: int = 10_000,
) -> dict:
    """Evaluate computed zones against paired random and matched controls.

    ``frames`` must already be immutable point-in-time snapshots. The caller
    owns provider acquisition and storage and supplies training-only volatility
    cutoffs for validation runs.
    """
    from tradingagents.dataflows.chart_zones import compute_chart_zones

    actual_events: list[dict] = []
    random_events: list[dict] = []
    matched_events: list[dict] = []
    failures: list[dict] = []
    baseline_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    params_version = "v1" if recency_halflife == 189 else f"v1-hl{recency_halflife}"
    order = [ticker for ticker in (ticker_order or sorted(frames)) if ticker in frames]
    order.extend(ticker for ticker in sorted(frames) if ticker not in order)
    for ticker in order:
        frame = _frame(frames[ticker])
        cohort = (ticker_cohorts or {}).get(ticker, "primary")
        for as_of in as_of_dates:
            if as_of < (eligibility_dates or {}).get(ticker, "0000-01-01"):
                continue
            try:
                zones_result = compute_chart_zones(frame, ticker, as_of, include_validation=False,
                                                   recency_halflife=recency_halflife)
            except (ValueError, KeyError, IndexError) as exc:
                failures.append({"ticker": ticker, "as_of": as_of, "reason": type(exc).__name__})
                continue
            if zones_result.get("status") != "ok":
                failures.append({"ticker": ticker, "as_of": as_of,
                                 "reason": zones_result.get("status", "unknown")})
                continue
            close, atr = float(zones_result["close"]), float(zones_result["atr14"])
            atr_pct = atr / close
            if volatility_cutoffs is None:
                volatility_group = "unclassified"
            elif atr_pct <= volatility_cutoffs[0]:
                volatility_group = "low"
            elif atr_pct >= volatility_cutoffs[1]:
                volatility_group = "high"
            else:
                volatility_group = "middle"
            zones = zones_result["zones"]
            controls = generate_baselines(ticker, as_of, zones, close, atr,
                                          baseline_version=baseline_version, count=control_count)
            controls_by_rank = {item["rank"]: item for item in controls}
            for rank, zone in enumerate(zones, start=1):
                diagnostic = baseline_counts[(cohort, zone["type"])]
                diagnostic["actual_zones"] += 1
                actual = evaluate_zone_event(frame, as_of, zone, atr, _normalized=True)
                actual_events.append({**actual, "ticker": ticker, "as_of": as_of,
                                      "zone_type": zone["type"], "rank": rank,
                                      "volatility_group": volatility_group, "cohort": cohort})
                generated = controls_by_rank[rank]
                diagnostic["random_rejections"] += generated.get("random_rejections", 0)
                diagnostic["matched_rejections"] += generated.get("matched_rejections", 0)
                diagnostic["matched_overlap_count"] += generated.get("matched_overlap_count", 0)
                diagnostic["matched_controls_generated"] += len(generated.get("matched", []))
                diagnostic["random_controls_generated"] += len(generated.get("random_unconditional", []))
                if generated["status"] != "ok":
                    diagnostic["unmatched_zones"] += 1
                    random_events.append({"ticker": ticker, "as_of": as_of, "zone_type": zone["type"],
                                          "rank": rank, "status": "unmatched", "eligible": False,
                                          "cohort": cohort})
                    matched_events.append({"ticker": ticker, "as_of": as_of, "zone_type": zone["type"],
                                           "rank": rank, "status": "unmatched", "eligible": False,
                                           "cohort": cohort})
                    continue
                for name, destination in (("random_unconditional", random_events), ("matched", matched_events)):
                    for control_zone in generated[name]:
                        outcome = evaluate_zone_event(frame, as_of, control_zone, atr, _normalized=True)
                        destination.append({**outcome, "ticker": ticker, "as_of": as_of,
                                            "zone_type": zone["type"], "rank": rank,
                                            "volatility_group": volatility_group, "cohort": cohort})

    cohort_names = sorted({event.get("cohort", "primary") for event in actual_events})
    cohort_reports = {}
    for cohort in cohort_names:
        cohort_reports[cohort] = {
            "actual": summarize_event_results([event for event in actual_events if event["cohort"] == cohort]),
            "random_unconditional": summarize_event_results(
                [event for event in random_events if event.get("cohort") == cohort]
            ),
            "matched": summarize_event_results([event for event in matched_events if event.get("cohort") == cohort]),
        }
    baseline_diagnostics = {
        f"{cohort}:{zone_type}": {
            **dict(counts),
            "matched_overlap_rate": round(
                counts["matched_overlap_count"] / counts["matched_controls_generated"], 6
            ) if counts["matched_controls_generated"] else None,
        }
        for (cohort, zone_type), counts in sorted(baseline_counts.items())
    }

    groups = {
        "support_resistance": {"support", "resistance"},
        "inside": {"inside"},
    }
    results = {}
    for output_type, kinds in groups.items():
        actual = [event for event in actual_events
                  if event["zone_type"] in kinds and event.get("cohort") == "primary"]
        random_controls = [event for event in random_events
                           if event["zone_type"] in kinds and event.get("cohort") == "primary"]
        matched_controls = [event for event in matched_events
                            if event["zone_type"] in kinds and event.get("cohort") == "primary"]
        pairs_random = _paired_rates(actual, random_controls)
        pairs_matched = _paired_rates(actual, matched_controls)
        random_pair_lifts, matched_pair_lifts = {}, {}
        for block in (3, 6, 12):
            random_pair_lifts[str(block)] = paired_block_bootstrap(
                pairs_random, sample_id=sample_id, baseline_version=f"{baseline_version}:random-unconditional",
                params_version=params_version, block_length=block, repetitions=bootstrap_repetitions,
            )
            matched_pair_lifts[str(block)] = paired_block_bootstrap(
                pairs_matched, sample_id=sample_id, baseline_version=f"{baseline_version}:matched",
                params_version=params_version, block_length=block, repetitions=bootstrap_repetitions,
            )
        enough, sample_size = _sample_gate(pairs_matched)
        volatility_lifts = {
            group: _paired_lift([row for row in pairs_matched if row["volatility_group"] == group])
            for group in ("low", "high")
        }
        primary = matched_pair_lifts["6"]
        if not enough:
            status, reason = "inconclusive", "minimum_effective_sample_not_met"
        elif output_type == "support_resistance" and volatility_cutoffs is None:
            status, reason = "inconclusive", "training_volatility_cutoffs_missing"
        elif primary["status"] != "ok":
            status, reason = "inconclusive", primary.get("reason", "bootstrap_unavailable")
        elif primary["ci95"][0] <= 0:
            status, reason = "failed", "matched_effective_hit_lift_ci_includes_zero"
        elif output_type == "support_resistance" and any(
            volatility_lifts[group] is None or volatility_lifts[group] <= 0 for group in ("low", "high")
        ):
            status, reason = "failed", "volatility_tercile_point_lift_not_positive"
        else:
            status, reason = "passed", None
        results[output_type] = {
            "status": status, "reason": reason,
            "actual": summarize_event_results(actual),
            "random_unconditional": summarize_event_results(random_controls),
            "matched": summarize_event_results(matched_controls),
            "random_unconditional_lift": _paired_lift(pairs_random),
            "matched_lift": _paired_lift(pairs_matched),
            "matched_lift_ci95": primary.get("ci95"),
            "bootstrap_random": random_pair_lifts,
            "bootstrap_matched": matched_pair_lifts,
            "volatility_tercile_lifts": volatility_lifts,
            "sample_size": sample_size,
            "matched_event_pairs": len(pairs_matched),
        }
    return {"sample": sample_id, "params_version": params_version, "baseline_version": baseline_version,
            "results": results, "cohorts": cohort_reports, "actual_events": actual_events,
            "unconditional_control_events": random_events, "matched_control_events": matched_events,
            "baseline_diagnostics": baseline_diagnostics,
            "matched_calipers": {"width_atr": MATCH_WIDTH_CALIPER_ATR,
                                 "distance_atr": MATCH_DISTANCE_CALIPER_ATR,
                                 "overlaps_actual_allowed": True},
            "data_failures": failures}


def paired_block_bootstrap(
    pairs: list[dict],
    *,
    sample_id: str,
    params_version: str = "v1",
    baseline_version: str = BASELINE_VERSION,
    block_length: int = 6,
    repetitions: int = 10_000,
) -> dict:
    """Paired ticker-cluster/circular-time-block bootstrap of effective hit lift."""
    if block_length not in {3, 6, 12}:
        raise ValueError("Block length must be 3, 6, or 12.")
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for pair in pairs:
        if pair.get("eligible") and pair.get("baseline_rate") is not None:
            grouped[pair["ticker"]][pair["as_of"]].append(pair)
    tickers = sorted(grouped)
    if not tickers:
        return {"status": "inconclusive", "reason": "no_matched_pairs", "ci95": None,
                "lift": None, "valid_replicates": 0, "block_length": block_length}

    all_dates = sorted({as_of for ticker_dates in grouped.values() for as_of in ticker_dates})
    by_ticker: dict[str, list[dict]] = {}
    for ticker in tickers:
        ticker_rows = []
        for as_of in all_dates:
            rows = grouped[ticker].get(as_of, [])
            ticker_rows.append({
                "as_of": as_of,
                "actual_hits": sum(bool(row["actual_hit"]) for row in rows),
                "baseline_hits": sum(float(row["baseline_rate"]) for row in rows),
                "events": len(rows),
            })
        by_ticker[ticker] = ticker_rows

    digest_text = f"zone-backtest|ci|{sample_id}|{params_version}|{baseline_version}"
    seed = int.from_bytes(hashlib.sha256(digest_text.encode()).digest()[:16], "big")
    if len(all_dates) // block_length < 6:
        return {"status": "inconclusive", "reason": "fewer_than_six_time_blocks", "ci95": None,
                "lift": None, "valid_replicates": 0, "block_length": block_length,
                "time_blocks": len(all_dates) // block_length, "seed": seed}
    rng = np.random.Generator(np.random.PCG64(seed))
    lifts = []
    zero_denominators = 0
    for _ in range(repetitions):
        picked = rng.choice(tickers, size=len(tickers), replace=True)
        actual_hits = baseline_hits = denominator = 0.0
        for ticker in picked:
            dates = by_ticker[ticker]
            starts_needed = max(1, math.ceil(len(dates) / block_length))
            indexes = []
            for _ in range(starts_needed):
                start = int(rng.integers(0, len(dates)))
                indexes.extend((start + offset) % len(dates) for offset in range(block_length))
            for index in indexes[:len(dates)]:
                date_row = dates[index]
                actual_hits += date_row["actual_hits"]
                baseline_hits += date_row["baseline_hits"]
                denominator += date_row["events"]
        if denominator == 0:
            zero_denominators += 1
            continue
        lifts.append((actual_hits - baseline_hits) / denominator)
    zero_share = zero_denominators / repetitions if repetitions else 1.0
    if zero_share > 0.01 or len(lifts) < max(1, int(repetitions * 0.99)):
        return {"status": "inconclusive", "reason": "too_many_zero_denominators", "ci95": None,
                "lift": None, "valid_replicates": len(lifts), "zero_denominator_replicates": zero_denominators,
                "block_length": block_length, "time_blocks": len(all_dates) // block_length, "seed": seed}
    ci_low, ci_high = np.quantile(lifts, [0.025, 0.975], method="linear")
    observed = sum(row["actual_hits"] - row["baseline_hits"] for dates in by_ticker.values()
                   for row in dates) / sum(row["events"] for dates in by_ticker.values() for row in dates)
    return {"status": "ok", "lift": round(float(observed), 6),
            "ci95": [round(float(ci_low), 6), round(float(ci_high), 6)],
            "valid_replicates": len(lifts), "zero_denominator_replicates": zero_denominators,
            "block_length": block_length, "time_blocks": len(all_dates) // block_length,
            "seed": seed, "method": "ticker_cluster_then_circular_time_blocks", "tickers": len(tickers),
            "dates": len({row["as_of"] for dates in by_ticker.values() for row in dates})}
