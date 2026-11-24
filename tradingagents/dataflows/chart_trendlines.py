"""Compare recent long-term rising support lines from a completed daily export."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from tradingagents.dataflows.chart_check import PRICE_COLUMNS, REQUIRED_COLUMNS, _date
from tradingagents.dataflows.chart_zones import _atr

PARAMS = {
    "pivot_radius": 5, "min_history": 756, "min_anchor_gap": 250, "min_second_anchor_age": 25,
    "reaction_window": 10, "reaction_gap": 25, "recent_reaction_age": 260, "min_reactions": 3,
    "touch_atr": 0.5, "rebound_atr": 1, "breach_atr": 0.5, "max_history_breach_ratio": 0.10,
    "max_distance_pct": 5,
}
QUANTUM = Decimal("0.000001")


def _reactions(i, line, pivots, lows, closes, atr):
    groups = []
    window = PARAMS["reaction_window"]
    for k in pivots:
        if k < i or k + window >= len(lows) - 1 or not np.isfinite(atr[k]) or atr[k] <= 0:
            continue
        distance = abs(lows[k] - line[k]) / atr[k]
        rebound = float(max(closes[k + 1:k + window + 1]) - lows[k]) / atr[k]
        if distance > PARAMS["touch_atr"] or rebound < PARAMS["rebound_atr"]:
            continue
        if not groups or k - groups[-1][-1][0] >= PARAMS["reaction_gap"]:
            groups.append([])
        groups[-1].append((k, float(distance), float(rebound)))
    return [min(group, key=lambda hit: hit[1]) for group in groups]


def _rank_candidates(days, prices, pivot_start):
    lows, closes = (prices[key].to_numpy() for key in ("Low", "Close"))
    log_lows = np.log(lows)
    atr = _atr(prices)
    span = np.arange(len(days))
    radius = PARAMS["pivot_radius"]
    pivots = [
        i for i in range(radius, len(days) - radius - 1)
        if days[i] >= pivot_start and lows[i] < min(lows[i-radius:i].min(), lows[i+1:i+radius+1].min())
    ]
    counts = dict.fromkeys(("pivots", "pairs", "geometry", "near_close", "historical", "eligible"), 0)
    counts["pivots"] = len(pivots)
    candidates = []
    for i, j in combinations(pivots, 2):
        counts["pairs"] += 1
        if (j - i < PARAMS["min_anchor_gap"] or len(days) - i < PARAMS["min_history"]
                or len(days) - j <= PARAMS["min_second_anchor_age"] or lows[j] <= lows[i]):
            continue
        counts["geometry"] += 1
        slope = (log_lows[j] - log_lows[i]) / (j - i)
        line = np.exp(log_lows[i] + slope * (span - i))
        distance = float(abs(line[-1] / closes[-1] - 1) * 100)
        if distance > PARAMS["max_distance_pct"]:
            continue
        counts["near_close"] += 1
        below = (closes - line) < -PARAMS["breach_atr"] * atr
        rate = float(np.mean(below[i:-1]))
        if rate > PARAMS["max_history_breach_ratio"]:
            continue
        counts["historical"] += 1
        hits = _reactions(i, line, pivots, lows, closes, atr)
        if (len(hits) < PARAMS["min_reactions"] or hits[-1][0] < len(days) - PARAMS["recent_reaction_age"]
                or hits[-1][0] < j + PARAMS["reaction_gap"]):
            continue
        candidates.append((i, j, hits, distance, rate))
    counts["eligible"] = len(candidates)
    candidates.sort(key=lambda row: (-len(row[2]), row[3], -row[2][-1][0], row[4], row[0], row[1]))
    return counts, candidates


def compare_trendlines(
    path: Path, *, ticker: str, start: date, as_of: date, pivot_start: date, chart_timezone: ZoneInfo,
    min_bars: int = 756, compare_anchor: date | None = None, extend_to: date | None = None,
) -> dict:
    """Rank observed rising lines; a projection is a drawing coordinate, not a price forecast."""
    extend_to = extend_to or as_of
    if not start <= pivot_start <= as_of <= extend_to:
        raise ValueError("Expected start <= pivot-start <= as-of <= extend-to.")
    if compare_anchor is not None and not start <= compare_anchor < as_of:
        raise ValueError("Comparison anchor must be in the completed analysis window.")
    cal = xcals.get_calendar("XNYS", start=start - pd.Timedelta(days=15), end=extend_to + pd.Timedelta(days=15))
    if not cal.is_session(start) or not cal.is_session(as_of) or not cal.is_session(extend_to):
        raise ValueError("Start, as-of and extension must be exchange sessions.")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(frame.columns) != REQUIRED_COLUMNS:
        raise ValueError("Expected a single date,o,h,l,c,v CSV.")
    frame.index = frame.pop("date").map(lambda value: _date(value, chart_timezone))
    start_day, last_day = start.isoformat(), as_of.isoformat()
    window = frame.loc[(frame.index >= start_day) & (frame.index <= last_day)].sort_index()
    days = window.index.tolist()
    expected = [stamp.date().isoformat() for stamp in cal.sessions_in_range(start, as_of)]
    missing, extra = sorted(set(expected) - set(days)), sorted(set(days) - set(expected))
    duplicates = sorted(set(window.index[window.index.duplicated()]))
    result = {
        "version": 1, "ticker": ticker, "as_of": last_day, "start": start_day,
        "pivot_start": pivot_start.isoformat(), "chart_timezone": chart_timezone.key,
        "bars": len(days), "expected_bars": len(expected), "minimum_bars": min_bars, "scale": "log",
        "missing_dates": missing, "extra_dates": extra, "duplicate_dates": duplicates,
        "sessions": "failed" if missing or extra or duplicates else "passed", "ohlcv": "unchecked",
        "params": PARAMS, "predictive_power": "not_evaluated", "counts": {}, "candidates": [], "selected": None,
    }
    if result["sessions"] == "failed":
        return {**result, "status": "invalid", "reason": "session_mismatch"}
    if len(days) < min_bars:
        return {**result, "status": "insufficient", "reason": "minimum_bars"}
    prices = window.apply(pd.to_numeric, errors="coerce").rename(columns={**PRICE_COLUMNS, "v": "Volume"})
    data = prices.to_numpy(dtype=float)
    opens, highs, lows, closes, volumes = data.T
    valid = np.isfinite(data).all() and np.all(
        (lows > 0) & (lows <= opens) & (lows <= closes) & (highs >= opens) & (highs >= closes)
        & (volumes > 0) & (volumes == np.floor(volumes))
    )
    if not valid:
        return {**result, "status": "invalid", "ohlcv": "failed", "reason": "invalid_ohlcv"}
    result["ohlcv"] = "passed"
    counts, ranked = _rank_candidates(days, prices, pivot_start.isoformat())
    result["counts"] = counts
    if not ranked:
        return {**result, "status": "unavailable", "reason": "no_eligible_candidate"}

    future_sessions = len(cal.sessions_in_range(as_of, extend_to)) - 1
    with localcontext() as context:
        context.prec = 30
        for i, j, hits, distance, rate in ranked:
            low_a, low_b = Decimal(window["l"].iloc[i]), Decimal(window["l"].iloc[j])
            start_log = low_a.ln()
            slope = (low_b.ln() - start_log) / (j - i)
            last = (start_log + slope * (len(days) - 1 - i)).exp()
            end = (start_log + slope * (len(days) - 1 - i + future_sessions)).exp()
            close = Decimal(window["c"].iloc[-1])
            result["candidates"].append({
                "anchors": [{"date": days[i], "low": str(low_a)}, {"date": days[j], "low": str(low_b)}],
                "sessions_between_anchors": j - i, "log_slope_per_session": str(slope),
                "reactions": [{"date": days[k], "distance_atr": round(d, 4), "rebound_atr": round(r, 4)}
                              for k, d, r in hits],
                "close": str(close), "as_of_line": str(last.quantize(QUANTUM)),
                "close_position": "above" if close > last else "below" if close < last else "at",
                "distance_pct": round(distance, 4), "historical_breach_ratio": round(rate, 6),
                "endpoint": {"date": extend_to.isoformat(), "price": str(end.quantize(QUANTUM)),
                             "future_sessions": future_sessions, "projected": future_sessions > 0},
            })

        selected = result["selected"] = result["candidates"][0]
        if compare_anchor is not None:
            day = compare_anchor.isoformat()
            if day not in days:
                raise ValueError("Comparison anchor is not a completed session in the CSV.")
            i = days.index(day)
            anchor = Decimal(window["l"].iloc[i])
            start_log = anchor.ln()
            chosen_slope = Decimal(selected["log_slope_per_session"])
            chosen_day = days.index(selected["anchors"][0]["date"])
            chosen_log = Decimal(selected["anchors"][0]["low"]).ln()
            last_log = chosen_log + chosen_slope * (len(days) - 1 - chosen_day)
            slope = (last_log - start_log) / (len(days) - 1 - i)
            breaches = [days[k] for k in range(i + 1, len(days))
                        if Decimal(window["c"].iloc[k]) < (start_log + slope * (k - i)).exp()]
            result["same_start_alternative"] = {
                "anchor": {"date": day, "low": str(anchor)}, "as_of_line": selected["as_of_line"],
                "log_slope_per_session": str(slope), "closes_below": len(breaches),
                "first_close_below": breaches[0] if breaches else None,
            }
    return {**result, "status": "ok"}
