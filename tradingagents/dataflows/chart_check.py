"""Compare Tratto chart bars with the Yahoo snapshot used by chart-zones."""

from __future__ import annotations

import io
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PRICE_COLUMNS = {"o": "Open", "h": "High", "l": "Low", "c": "Close"}
REQUIRED_COLUMNS = ["date", "o", "h", "l", "c", "v"]
ET = ZoneInfo("America/New_York")


def _date(value, chart_timezone: ZoneInfo) -> str:
    text = str(value).strip()
    stamp = pd.Timestamp(text)
    if stamp.tzinfo is not None:
        return stamp.tz_convert(chart_timezone).date().isoformat()
    return text[:10]


def add_retry_state(result: dict, previous: dict | None = None) -> dict:
    """Track one range expansion and one chart-data refetch independently."""
    previous = previous or {}
    range_retries = int(previous.get("range_retry_count", 0))
    data_retries = int(previous.get("data_retry_count", 0))
    previous_action = previous.get("retry_action")
    if previous_action == "set_range":
        range_retries += 1
    elif previous_action == "get_chart_data":
        data_retries += 1
    action = None
    if result.get("status") == "insufficient" and range_retries < 1:
        action = "set_range"
    elif result.get("status") in {"mismatch", "date_mismatch"} and data_retries < 1:
        action = "get_chart_data"
    attempts = list(previous.get("attempts", []))
    attempts.append({"status": result.get("status"), "reason": result.get("reason"),
                     "retry_action": action, "rows": result.get("rows"),
                     "expected_rows": result.get("expected_rows")})
    return {
        **result,
        "attempt": int(previous.get("attempt", 0)) + 1,
        "attempts": attempts,
        "range_retry_count": range_retries,
        "data_retry_count": data_retries,
        "retry_action": action,
        "retry_recommended": action is not None,
    }


def compare_chart_csv(run_dir: str, chart_csv: str, *, chart_timezone: ZoneInfo = ET) -> dict:
    """Check exact requested windows; never use chart data to calculate zones."""
    from pathlib import Path

    root = Path(run_dir)
    zones = json.loads((root / "zones.json").read_text(encoding="utf-8"))
    snapshot = pd.read_csv(root / "snapshot.csv", parse_dates=[0])
    try:
        header = ",".join(REQUIRED_COLUMNS)
        blocks, current = [], []
        for line in Path(chart_csv).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                if current:
                    blocks.append("\n".join(current) + "\n")
                    current = []
            elif line.strip() == header:
                if current:
                    blocks.append("\n".join(current) + "\n")
                current = [header]
            elif current:
                current.append(line)
            else:
                return {"status": "unknown", "reason": "invalid_header",
                        "expected_header": REQUIRED_COLUMNS, "actual_header": line.split(",")}
        if current:
            blocks.append("\n".join(current) + "\n")
        if not blocks:
            return {"status": "unknown", "reason": "empty_chart_data"}
        chart_blocks = [pd.read_csv(io.StringIO(block), dtype={"date": "string"}) for block in blocks]
        if any(list(block.columns) != REQUIRED_COLUMNS for block in chart_blocks):
            return {"status": "unknown", "reason": "invalid_header", "expected_header": REQUIRED_COLUMNS}

        as_of = zones["as_of"]
        windows = {}
        for name, window in zones.get("check_windows", {}).items():
            if not isinstance(window, dict):
                continue
            dates = window.get("dates", [])
            if window.get("count") != len(dates) or len(dates) != len(set(dates)):
                return {"status": "unknown", "reason": "invalid_window_manifest", "window": name}
            if dates:
                windows[name] = list(dates)
        expected_union = sorted({day for dates in windows.values() for day in dates})
        if not windows:
            return {"status": "unknown", "reason": "no_comparison_windows"}

        normalized, after = [], {}
        for index, block in enumerate(chart_blocks):
            block["date"] = block["date"].map(lambda value: _date(value, chart_timezone))
            after[str(index)] = block[block["date"] > as_of]["date"].tolist()
            block = block[block["date"] <= as_of].copy()
            if block["date"].duplicated().any():
                return {"status": "date_mismatch", "reason": "duplicate_dates",
                        "block": index, "dates_after_as_of": after}
            normalized.append(block)

        # Accept raw blocks per requested window, or one raw block covering their union.
        if len(normalized) == 1 and set(normalized[0]["date"]) == set(expected_union):
            combined = normalized[0].set_index("date")
            chart_by_window = dict.fromkeys(windows, combined)
        elif len(normalized) == len(windows):
            chart_by_window = dict(zip(windows, (block.set_index("date") for block in normalized), strict=True))
        else:
            actual_union = {day for block in normalized for day in block["date"]}
            missing = sorted(set(expected_union) - actual_union)
            extra = sorted(actual_union - set(expected_union))
            status = "insufficient" if missing else "date_mismatch"
            return {"status": status, "reason": "window_blocks_differ", "missing_dates": missing,
                    "extra_dates": extra, "rows": sum(len(block) for block in normalized),
                    "expected_rows": sum(map(len, windows.values())), "dates_after_as_of": after,
                    "attempt": 1, "retry_recommended": bool(missing or extra)}

        yahoo = snapshot.copy()
        yahoo["Date"] = pd.to_datetime(yahoo.iloc[:, 0]).dt.date.astype(str)
        yahoo = yahoo.set_index("Date")
        summaries, all_ratios, mismatch = [], [], False
        missing, extra, total_rows = [], [], 0
        for window_name, dates in windows.items():
            chart = chart_by_window[window_name]
            absent = sorted(set(dates) - set(chart.index))
            additional = sorted(set(chart.index) - set(dates))
            missing.extend(absent)
            extra.extend(additional)
            if absent or additional:
                continue
            chart = chart.loc[dates]
            yahoo_window = yahoo.loc[dates]
            total_rows += len(dates)
            diffs = []
            for day in dates:
                for column, yahoo_column in PRICE_COLUMNS.items():
                    chart_value = float(chart.loc[day, column])
                    yahoo_value = float(yahoo_window.loc[day, yahoo_column])
                    if not np.isfinite(chart_value) or not np.isfinite(yahoo_value):
                        return {"status": "unknown", "reason": "non_finite_price", "date": day,
                                "column": column, "dates_after_as_of": after}
                    tolerance = max(abs(yahoo_value) * 0.001, 0.01)
                    difference = abs(chart_value - yahoo_value)
                    diffs.append({"date": day, "column": column, "absolute_difference": round(difference, 6),
                                  "chart_value": chart_value, "yahoo_value": yahoo_value})
                    if difference > tolerance:
                        mismatch = True
                    if yahoo_value != 0:
                        all_ratios.append(chart_value / yahoo_value)
            worst = max(diffs, key=lambda x: x["absolute_difference"], default=None)
            summaries.append({"window": window_name, "rows": len(dates), "max_difference": worst})
        if missing or extra:
            status = "insufficient" if missing else "date_mismatch"
            return {"status": status, "reason": "window_dates_differ",
                    "missing_dates": sorted(set(missing)), "extra_dates": sorted(set(extra)),
                    "rows": total_rows, "expected_rows": sum(map(len, windows.values())),
                    "dates_after_as_of": after, "attempt": 1, "retry_recommended": True}
        ratio = float(np.median(all_ratios)) if all_ratios else None
        after_summary = after["0"] if len(after) == 1 else after
        clues = []
        if ratio is not None and abs(ratio - 1) > 0.001:
            clues.append("price_basis_or_adjustment_difference")
        if mismatch and zones.get("latest_ex_dividend_date"):
            clues.append("dividend_adjustment_may_differ")
        return {"status": "mismatch" if mismatch else "ok", "ticker": zones["ticker"],
                "as_of": as_of, "snapshot_sha256": zones["snapshot_sha256"],
                "rows": total_rows, "expected_rows": sum(map(len, windows.values())),
                "dates_after_as_of": after_summary, "windows": summaries,
                "chart_to_yahoo_price_ratio_median": round(ratio, 6) if ratio is not None else None,
                "clues": clues, "attempt": 1,
                "retry_recommended": bool(mismatch)}
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return {"status": "unknown", "reason": f"invalid_chart_data:{type(exc).__name__}"}
