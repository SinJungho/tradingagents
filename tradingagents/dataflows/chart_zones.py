"""Deterministic daily support/resistance zones from Yahoo bars."""

from __future__ import annotations

import hashlib
from datetime import datetime, time
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from tradingagents.dataflows.router import route_to_vendor

ET = ZoneInfo("America/New_York")
PARAMS = {
    "version": "v1", "history_years": 5, "atr_period": 14, "zigzag_atr": 2.0,
    "kde_bandwidth_atr_pct": 0.5, "grid_atr_pct": 0.05, "hdr_mass": 0.5,
    "max_zone_width_atr_pct": 1.0, "min_pivots": 2, "reaction_bars": 20,
    "reaction_cap_atr": 5.0, "recency_halflife": 189, "breach_atr": 0.5,
    "trend_bars": 252, "trend_r2_sideways": 0.3, "zones_each_side": 3,
    "minimum_bars": 504, "annual_bars": 252,
}


def resolve_as_of(requested: str | None = None, *, now: datetime | None = None) -> str:
    """Return the last XNYS session available at the requested ET-20:00 cutoff."""
    current = (now or datetime.now(ET)).astimezone(ET)
    cutoff = pd.Timestamp(requested or current.date().isoformat())
    if cutoff.date() == current.date() and current.time() < time(20):
        cutoff -= pd.Timedelta(days=1)
    sessions = xcals.get_calendar("XNYS").sessions_in_range(cutoff - pd.Timedelta(days=14), cutoff)
    if sessions.empty:
        raise ValueError(f"No XNYS session on or before {cutoff.date()}.")
    return sessions[-1].date().isoformat()


def _clean(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    data = frame.copy()
    data.index = pd.DatetimeIndex(pd.to_datetime(data.index).date)
    data = data.loc[~data.index.duplicated(keep="first")].sort_index()
    data = data.loc[data.index <= pd.Timestamp(as_of)]
    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in data for c in required):
        raise ValueError("Yahoo chart history must contain Open, High, Low, Close, and Volume.")
    data[required] = data[required].apply(pd.to_numeric, errors="coerce")
    return data


def _atr(data: pd.DataFrame, breaks: set[int] | None = None) -> np.ndarray:
    high, low, close = (data[k].to_numpy(dtype=np.float64) for k in ("High", "Low", "Close"))
    out = np.full(len(data), np.nan)
    breaks = breaks or set()
    period = PARAMS["atr_period"]
    window: list[float] = []
    for i in range(len(data)):
        if i in breaks:
            window.clear()
        if not all(np.isfinite(v) for v in (high[i], low[i], close[i])):
            window.clear()
            continue
        tr = high[i] - low[i]
        if i and i not in breaks and np.isfinite(close[i - 1]):
            tr = max(tr, abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        window.append(float(tr))
        if len(window) == period:
            out[i] = np.mean(window, dtype=np.float64)
        elif len(window) > period:
            out[i] = (out[i - 1] * (period - 1) + tr) / period
    return out


def _pivots(data: pd.DataFrame, atr: np.ndarray, breaks: set[int] | None = None) -> list[dict]:
    """Confirm a candidate extreme after an opposite 2-ATR move."""
    high, low = data["High"].to_numpy(), data["Low"].to_numpy()
    pivots: list[dict] = []
    direction, low_i, high_i = 0, 0, 0
    breaks = breaks or set()
    for i in range(1, len(data)):
        if i in breaks:
            direction, low_i, high_i = 0, i, i
            continue
        if direction == 0:
            if low[i] < low[low_i]:
                low_i = i
            if high[i] > high[high_i]:
                high_i = i
            if not np.isfinite(atr[i]) or not np.isfinite(atr[low_i]) or not np.isfinite(atr[high_i]):
                continue
            up_confirmed = high[i] - low[low_i] >= PARAMS["zigzag_atr"] * atr[low_i]
            down_confirmed = high[high_i] - low[i] >= PARAMS["zigzag_atr"] * atr[high_i]
            if up_confirmed and down_confirmed:
                continue
            if up_confirmed and low_i < i:
                pivots.append({"index": low_i, "kind": "low", "price": low[low_i], "confirmed": i})
                direction, high_i = 1, i
            elif down_confirmed and high_i < i:
                pivots.append({"index": high_i, "kind": "high", "price": high[high_i], "confirmed": i})
                direction, low_i = -1, i
        elif direction > 0:
            if high[i] > high[high_i]:
                high_i = i
            if not np.isfinite(atr[i]) or not np.isfinite(atr[high_i]):
                continue
            if (low[i] <= high[high_i] - PARAMS["zigzag_atr"] * atr[high_i]
                    and high_i < i):
                pivots.append({"index": high_i, "kind": "high", "price": high[high_i], "confirmed": i})
                direction, low_i = -1, i
        else:
            if low[i] < low[low_i]:
                low_i = i
            if not np.isfinite(atr[i]) or not np.isfinite(atr[low_i]):
                continue
            if (high[i] >= low[low_i] + PARAMS["zigzag_atr"] * atr[low_i]
                    and low_i < i):
                pivots.append({"index": low_i, "kind": "low", "price": low[low_i], "confirmed": i})
                direction, high_i = 1, i
    return pivots


def _candidates(pivots: list[dict], atr: np.ndarray, count: int, recency_halflife: int) -> list[dict]:
    if len(pivots) < 2:
        return []
    price = np.asarray([p["price"] for p in pivots], dtype=np.float64)
    logp = np.log(price)
    atrp = np.asarray([atr[p["index"]] / p["price"] for p in pivots])
    step = max(float(np.median(atrp) * PARAMS["grid_atr_pct"]), 1e-6)
    width = np.maximum(atrp * PARAMS["kde_bandwidth_atr_pct"], step / 2)
    grid_start = float(np.min(logp - 6 * width))
    grid_end = float(np.max(logp + 6 * width))
    grid = np.arange(grid_start, grid_end + step, step, dtype=np.float64)
    weight = np.power(0.5, np.asarray([count - p["index"] - 1 for p in pivots]) /
                      recency_halflife)
    z = (grid[:, None] - logp[None, :]) / width[None, :]
    density = np.exp(-0.5 * z * z) @ (weight / (width * np.sqrt(2 * np.pi)))
    mass = density * step
    order = np.lexsort((grid, -density))
    cumulative = np.cumsum(mass[order], dtype=np.float64)
    stop = np.searchsorted(cumulative, PARAMS["hdr_mass"] * mass.sum(), side="left")
    threshold = density[order[min(stop, len(order) - 1)]]
    chosen = density >= threshold
    edges = np.diff(np.r_[False, chosen, False].astype(np.int8))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    result = []
    for start, end in zip(starts, ends, strict=True):
        peak = start + int(np.argmax(density[start:end]))
        members = [p for p in pivots if grid[start] <= np.log(p["price"]) <= grid[end - 1]]
        if len(members) < 2:
            continue
        local_atrp = np.asarray([atr[p["index"]] / p["price"] for p in members])
        cap = float(np.median(local_atrp) * PARAMS["max_zone_width_atr_pct"])
        lower = max(grid[start], grid[peak] - cap / 2)
        upper = min(grid[end - 1], grid[peak] + cap / 2)
        lower, upper = float(np.exp(lower)), float(np.exp(upper))
        result.append({"lower": lower, "upper": upper, "peak": float(np.exp(grid[peak])),
                       "_peak_index": peak, "pivots": members})
    result.sort(key=lambda z: (z["peak"], z["lower"], z["upper"]))
    for left, right in zip(result, result[1:], strict=False):
        if left["upper"] > right["lower"]:
            lo, hi = sorted((left["_peak_index"], right["_peak_index"]))
            valley = lo + int(np.argmin(density[lo:hi + 1]))
            boundary = float(np.exp(grid[valley]))
            left["upper"] = right["lower"] = boundary
    for candidate in result:
        candidate["pivots"] = []
    for pivot in pivots:
        matches = [candidate for candidate in result
                   if candidate["lower"] <= pivot["price"] <= candidate["upper"]]
        if matches:
            min(matches, key=lambda candidate: (candidate["lower"], candidate["upper"]))["pivots"].append(pivot)
    for candidate in result:
        candidate.pop("_peak_index")
    return [z for z in result if z["lower"] < z["upper"] and len(z["pivots"]) >= 2]


def _rank_directional_zones(zones: list[dict]) -> list[dict]:
    return sorted(zones, key=lambda zone: (zone["distance_atr"], -zone["score"], zone["lower"]))


FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)


def _fib_retracement(data: pd.DataFrame, pivots: list[dict], breaks: set[int]) -> dict:
    """Anchor retracement on the last confirmed ZigZag swing without a session gap."""
    if len(pivots) < 2:
        return {"status": "unavailable", "reason": "fewer_than_two_confirmed_pivots"}
    start, end = pivots[-2], pivots[-1]
    if start["kind"] == end["kind"] or any(start["index"] < b <= end["index"] for b in breaks):
        return {"status": "unavailable", "reason": "last_swing_crosses_session_gap"}
    up = end["kind"] == "high"
    later = data.iloc[end["index"] + 1:]
    reason = None
    if (later["High"] > end["price"]).any() if up else (later["Low"] < end["price"]).any():
        reason = "new_extreme_after_end"
    elif (later["Low"] < start["price"]).any() if up else (later["High"] > start["price"]).any():
        reason = "start_breached"
    span = end["price"] - start["price"]

    def anchor(p: dict) -> dict:
        return {"date": data.index[p["index"]].date().isoformat(), "price": round(float(p["price"]), 6),
                "kind": p["kind"], "confirmed_at": data.index[p["confirmed"]].date().isoformat(),
                "index": p["index"]}

    return {"status": "invalidated" if reason else "ok", "reason": reason, "direction": "up" if up else "down",
            "start": anchor(start), "end": anchor(end),
            "levels": {str(r): round(float(end["price"] - r * span), 6) for r in FIB_RATIOS}}


def _avwap(data: pd.DataFrame, start: int, breaks: set[int], atr_last: float, **anchor) -> dict:
    """Daily anchored VWAP of typical price from ``start`` through the last bar."""
    date = data.index[start].date().isoformat()
    base = {"anchor_date": date, **anchor}
    if any(b > start for b in breaks):
        return {"status": "unavailable", "reason": "session_gap_after_anchor", **base}
    part = data.iloc[start:]
    volume = part["Volume"].to_numpy(dtype=np.float64)
    if not np.isfinite(volume).all() or volume.sum() <= 0:
        return {"status": "unavailable", "reason": "volume_missing_after_anchor", **base}
    typical = part[["High", "Low", "Close"]].to_numpy(dtype=np.float64).mean(axis=1)
    values = np.cumsum(typical * volume) / np.where(np.cumsum(volume) > 0, np.cumsum(volume), np.nan)
    close = float(part["Close"].iloc[-1])
    return {"status": "ok", "reason": None, **base, "method": "daily_typical_price",
            "value": round(float(values[-1]), 6),
            "close_minus_vwap_atr": round((close - float(values[-1])) / float(atr_last), 6),
            "values": [[d.date().isoformat(), None if np.isnan(v) else round(float(v), 6)]
                       for d, v in zip(part.index, values, strict=True)]}


def _earnings_avwap(data: pd.DataFrame, earnings_dates, calendar, breaks: set[int], atr_last: float) -> dict:
    """Anchor on the first session that could trade on the latest earnings release."""
    if earnings_dates is None:
        return {"status": "unavailable", "reason": "earnings_dates_unavailable"}
    last = data.index[-1]
    for stamp in sorted((pd.Timestamp(s) for s in earnings_dates), reverse=True):
        local = stamp.tz_convert(ET) if stamp.tzinfo else stamp.tz_localize(ET)
        day = pd.Timestamp(local.date())
        time_known = local.time() != time(0, 0)
        if time_known and local.time() >= time(16, 0):
            day += pd.Timedelta(days=1)
        if day > last:
            continue
        session = calendar.date_to_session(day, direction="next")
        if session > last:
            continue
        if session not in data.index:
            return {"status": "unavailable", "reason": "anchor_session_missing",
                    "release_at": local.isoformat()}
        return _avwap(data, data.index.get_loc(session), breaks, atr_last,
                      release_at=local.isoformat(), release_time_known=time_known)
    return {"status": "unavailable", "reason": "no_earnings_before_as_of"}


def compute_chart_zones(
    frame: pd.DataFrame,
    symbol: str,
    as_of: str,
    *,
    include_validation: bool = True,
    recency_halflife: int = 189,
    earnings_dates: list | None = None,
) -> dict:
    """Compute deterministic zones from bars through ``as_of`` only."""
    if recency_halflife not in {189, 378, 756}:
        raise ValueError("Supported chart-zone recency half-lives are 189, 378, and 756 bars.")
    raw = _clean(frame, as_of)
    raw = raw.loc[raw.index >= pd.Timestamp(as_of) - pd.DateOffset(years=PARAMS["history_years"])]
    data = raw
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(data.index[0], data.index[-1]) if len(data) else []
    expected = [session.date() for session in sessions]
    positions = {day: i for i, day in enumerate(expected)}
    non_sessions = [day for day in data.index if day.date() not in positions]
    if non_sessions:
        data = data.loc[[day.date() in positions for day in data.index]]
    ohlc = data[["Open", "High", "Low", "Close"]].to_numpy(dtype=np.float64)
    finite_ohlc = np.isfinite(ohlc).all(axis=1)
    incomplete = pd.Series(~finite_ohlc, index=data.index)
    invalid_values = finite_ohlc & (ohlc <= 0).any(axis=1)
    invalid_geometry = finite_ohlc & (
        (data["High"].to_numpy() < data["Low"].to_numpy())
        | (data["High"].to_numpy() < data[["Open", "Close"]].max(axis=1).to_numpy())
        | (data["Low"].to_numpy() > data[["Open", "Close"]].min(axis=1).to_numpy())
    )
    invalid = pd.Series(invalid_values | invalid_geometry, index=data.index)
    unknowns = []
    if incomplete.any():
        unknowns.append({"kind": "incomplete_ohlc", "dates": [d.date().isoformat() for d in data.index[incomplete]]})
    if invalid.any():
        unknowns.append({"kind": "invalid_ohlc", "dates": [d.date().isoformat() for d in data.index[invalid]]})
    if non_sessions:
        unknowns.append({"kind": "non_xnys_rows", "dates": [day.date().isoformat() for day in non_sessions]})
    if data["Volume"].isna().any():
        unknowns.append({"kind": "missing_volume", "dates": [d.date().isoformat()
                                                                  for d in data.index[data["Volume"].isna()]]})
    excluded = incomplete | invalid
    valid_dates = data.index[~excluded]
    if len(valid_dates) == 0:
        validation = _validation_for_as_of(as_of) if include_validation else _empty_validation()
        return {"ticker": symbol.upper(), "as_of": as_of, "status": "insufficient", "bars": 0,
                "minimum_bars": PARAMS["minimum_bars"], "unknowns": unknowns,
                "validation": validation}
    if valid_dates[-1] < pd.Timestamp(as_of):
        missing_tail = calendar.sessions_in_range(valid_dates[-1] + pd.Timedelta(days=1), as_of)
        if len(missing_tail):
            unknowns.append({"kind": "missing_trailing_xnys_sessions",
                             "dates": [day.date().isoformat() for day in missing_tail]})
        unknowns.append({"kind": "unsettled_trailing_rows",
                         "dates": [d.date().isoformat() for d in data.index[data.index > valid_dates[-1]] ]})
        as_of = valid_dates[-1].date().isoformat()
        data = data.loc[data.index <= pd.Timestamp(as_of)]
        raw = raw.loc[raw.index <= pd.Timestamp(as_of)]
        excluded = excluded.loc[data.index]
        sessions = calendar.sessions_in_range(data.index[0], data.index[-1])
        expected = [session.date() for session in sessions]
        positions = {day: i for i, day in enumerate(expected)}
    data = data.loc[~excluded]
    raw.index.name = "Date"
    snapshot = raw.to_csv(float_format="%.6f", lineterminator="\n").encode()
    digest = hashlib.sha256(snapshot).hexdigest()
    if len(data) < PARAMS["minimum_bars"]:
        validation = _validation_for_as_of(as_of) if include_validation else _empty_validation()
        return {"ticker": symbol.upper(), "as_of": as_of, "status": "insufficient", "bars": len(data),
                "minimum_bars": PARAMS["minimum_bars"], "snapshot_sha256": digest, "unknowns": unknowns,
                "validation": validation}
    present = {day.date() for day in data.index}
    missing = [day for day in expected if day not in present]
    if missing:
        unknowns.append({"kind": "missing_xnys_session", "dates": [day.isoformat() for day in missing]})
    breaks = {i for i in range(1, len(data))
              if positions[data.index[i].date()] - positions[data.index[i - 1].date()] > 1}
    atr = _atr(data, breaks)
    if not np.isfinite(atr[-1]) or atr[-1] <= 0:
        unknowns.append({"kind": "atr_unavailable_or_nonpositive",
                         "date": data.index[-1].date().isoformat()})
        validation = _validation_for_as_of(as_of) if include_validation else _empty_validation()
        return {"ticker": symbol.upper(), "as_of": as_of, "status": "insufficient",
                "reason": "atr_unavailable_or_nonpositive", "bars": len(data),
                "minimum_bars": PARAMS["minimum_bars"], "snapshot_sha256": digest,
                "unknowns": unknowns, "validation": validation}
    pivots = _pivots(data, atr, breaks)
    close = float(data["Close"].iloc[-1])
    zones = []
    for candidate in _candidates(pivots, atr, len(data), recency_halflife):
        lower, upper = candidate["lower"], candidate["upper"]
        kind = "inside" if lower <= close <= upper else ("support" if upper < close else "resistance")
        touches, score = [], 0.0
        for pivot in candidate["pivots"]:
            i = pivot["index"]
            segment_end = min((point for point in breaks if point > i), default=len(data))
            future = data.iloc[i + 1:min(segment_end, i + 1 + PARAMS["reaction_bars"])]
            reaction = ((future["High"].max() - pivot["price"]) if pivot["kind"] == "low" else
                        (pivot["price"] - future["Low"].min())) if not future.empty else 0.0
            response = min(max(float(reaction / atr[i]), 0.0), PARAMS["reaction_cap_atr"])
            breaches, breached = 0, False
            for j in range(i + 1, segment_end):
                close_j = data["Close"].iloc[j]
                out = ((kind == "support" and close_j < lower - PARAMS["breach_atr"] * atr[j]) or
                       (kind == "resistance" and close_j > upper + PARAMS["breach_atr"] * atr[j]) or
                       (kind == "inside" and (close_j < lower - PARAMS["breach_atr"] * atr[j] or
                                               close_j > upper + PARAMS["breach_atr"] * atr[j])))
                if out and not breached:
                    breaches += 1
                    breached = True
                elif lower <= close_j <= upper:
                    breached = False
            recency = 0.5 ** ((len(data) - i - 1) / recency_halflife)
            score += recency * response * 0.5 ** breaches
            touches.append({"date": data.index[i].date().isoformat(), "price": round(float(pivot["price"]), 6),
                            "kind": pivot["kind"], "confirmed_at": data.index[pivot["confirmed"]].date().isoformat(),
                            "reaction_bars": len(future), "reaction_atr": round(response, 6)})
        distance = (0.0 if kind == "inside" else
                    abs(close - (upper if kind == "support" else lower)) / atr[-1])
        zones.append({"type": kind, "lower": round(lower, 6), "upper": round(upper, 6),
                      "touches": len(touches), "touch_points": touches, "score": round(score, 6),
                      "distance_atr": round(float(distance), 6),
                      "break_above": round(upper + 0.5 * atr[-1], 6) if kind == "inside" else None,
                      "break_below": round(lower - 0.5 * atr[-1], 6) if kind == "inside" else None})
    inside = sorted((z for z in zones if z["type"] == "inside"),
                    key=lambda z: (-z["score"], z["upper"] - z["lower"], z["lower"]))[:1]
    support = _rank_directional_zones([z for z in zones if z["type"] == "support"])[:3]
    resistance = _rank_directional_zones([z for z in zones if z["type"] == "resistance"])[:3]
    def fit(series: pd.Series) -> dict:
        y = np.log(series.to_numpy(dtype=np.float64))
        x = np.arange(len(y), dtype=np.float64)
        slope, intercept = np.polyfit(x, y, 1)
        total = np.sum((y - y.mean()) ** 2)
        r2 = 1 - np.sum((y - (intercept + slope * x)) ** 2) / total if total else 0.0
        return {"annual_slope": round(float(slope * 252), 6), "r2": round(float(r2), 6),
                "direction": "sideways" if r2 < 0.3 else ("up" if slope > 0 else "down")}
    dividends = frame.get("Dividends")
    ex_dates = [] if dividends is None else [
        pd.Timestamp(d).date().isoformat()
        for d, v in dividends.items()
        if pd.Timestamp(d).date().isoformat() <= as_of and pd.notna(v) and float(v) > 0
    ]
    dates = data.index
    def window(center: int, radius: int = 5) -> dict:
        selected = dates[max(0, center - radius):min(len(dates), center + radius + 1)]
        return {"dates": selected.date.astype(str).tolist(), "count": len(selected)}
    dividend_window = {"status": "unknown" if dividends is None else "not_applicable", "dates": [], "count": 0}
    if dividends is None:
        unknowns.append({"kind": "corporate_actions_unavailable", "fields": ["Dividends"]})
    if ex_dates:
        dividend_dt = pd.Timestamp(max(ex_dates))
        idx = int(np.searchsorted(dates.values, dividend_dt.to_datetime64()))
        dividend_window = {"status": "ok", **window(min(idx, len(dates) - 1))}
    displayed_touch_dates = [point["date"] for zone in inside +
                             sorted((z for z in zones if z["type"] != "inside"),
                                    key=lambda z: (z["distance_atr"], -z["score"]))[:6]
                             for point in zone["touch_points"]]
    first_touch = min(displayed_touch_dates) if displayed_touch_dates else None
    oldest_window = {"status": "not_applicable", "dates": [], "count": 0, "anchor_date": None}
    if first_touch:
        idx = int(np.searchsorted(dates.values, np.datetime64(first_touch)))
        oldest_window = {"status": "ok", "anchor_date": first_touch, **window(idx)}
    fib = _fib_retracement(data, pivots, breaks)
    fib_windows = {} if fib["status"] == "unavailable" else {
        f"fib_{end}": {"status": "ok", "anchor_date": fib[end]["date"], **window(fib[end].pop("index"))}
        for end in ("start", "end")}
    swing_avwap = ({"status": "unavailable", "reason": f"fib_{fib['reason']}"} if fib["status"] == "unavailable"
                   else _avwap(data, data.index.get_loc(pd.Timestamp(fib["start"]["date"])), breaks, atr[-1]))
    earnings_avwap = _earnings_avwap(data, earnings_dates, calendar, breaks, atr[-1])
    avwap_windows = {} if earnings_avwap["status"] == "unavailable" else {"avwap_earnings": {
        "status": "ok", "anchor_date": earnings_avwap["anchor_date"],
        **window(data.index.get_loc(pd.Timestamp(earnings_avwap["anchor_date"])))}}
    validation = _validation_for_as_of(as_of) if include_validation else _empty_validation()
    validation["pending"] = any(validation[name]["pending"] for name in ("support_resistance", "inside"))
    validation["stale"] = any(validation[name]["stale"] for name in ("support_resistance", "inside"))
    version = "v1" if recency_halflife == PARAMS["recency_halflife"] else f"v1-hl{recency_halflife}"
    return {"ticker": symbol.upper(), "as_of": as_of, "status": "ok", "params_version": version,
            "bars": len(data), "close": round(close, 6), "atr14": round(float(atr[-1]), 6),
            "price_basis": "Yahoo split-adjusted OHLC, dividend-unadjusted (auto_adjust=False)",
            "snapshot_sha256": digest, "latest_ex_dividend_date": max(ex_dates) if ex_dates else None,
            "unknowns": unknowns,
            "trend": {"all": fit(data["Close"]), "recent_252": fit(data["Close"].tail(252))},
            "zones": inside + support + resistance,
            "fib_retracement": fib,
            "anchored_vwap": {"swing_start": swing_avwap, "earnings": earnings_avwap},
            "check_windows": {"recent_20": {"dates": dates[-20:].date.astype(str).tolist(), "count": 20},
                              "dividend": dividend_window, "oldest_first_touch": oldest_window,
                              **fib_windows, **avwap_windows},
            "validation": validation}


def _empty_validation() -> dict:
    empty = {"status": "not_evaluated", "sample": None, "evaluated_at": None, "lift": None, "ci95": None,
             "latest_evaluation": None, "last_passed_evaluation": None,
             "effective_status": "not_evaluated", "latest_sample": None, "pending": False, "stale": False}
    return {"support_resistance": empty.copy(), "inside": empty.copy(), "latest_sample": None,
            "pending": False, "stale": False, "chart_validation": {"status": "not_evaluated"}}


def _validation_for_as_of(as_of: str) -> dict:
    from tradingagents.zone_validation import current_validation

    validation = current_validation(as_of)
    validation["pending"] = any(validation[name]["pending"] for name in ("support_resistance", "inside"))
    validation["stale"] = any(validation[name]["stale"] for name in ("support_resistance", "inside"))
    return validation


def get_chart_zones(symbol: str, curr_date: str | None = None) -> dict:
    result, _ = get_chart_zones_with_snapshot(symbol, curr_date)
    return result


def get_chart_zones_with_snapshot(
    symbol: str, curr_date: str | None = None
) -> tuple[dict, pd.DataFrame]:
    from tradingagents.dataflows.config import get_config

    configured = get_config().get("chart_zone_params", PARAMS["version"])
    if configured != PARAMS["version"]:
        raise ValueError(f"Unsupported chart-zone params version: {configured}")
    as_of = resolve_as_of(curr_date)
    end = as_of
    start = (pd.Timestamp(as_of) - pd.DateOffset(years=PARAMS["history_years"])).strftime("%Y-%m-%d")
    frame = route_to_vendor("get_chart_history", symbol, start=start, end=end)
    if isinstance(frame, str):
        raise ValueError(frame)
    try:
        earnings = route_to_vendor("get_earnings_dates", symbol)
    except Exception:
        earnings = None
    result = compute_chart_zones(frame, symbol, as_of,
                                 earnings_dates=earnings if isinstance(earnings, list) else None)
    snapshot = _clean(frame, result["as_of"])
    snapshot = snapshot.loc[snapshot.index >= pd.Timestamp(result["as_of"]) -
                            pd.DateOffset(years=PARAMS["history_years"])]
    snapshot.index.name = "Date"
    return result, snapshot
