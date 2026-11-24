import csv
import json
import math
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pytest
from typer.testing import CliRunner

from cli.main import app
from tradingagents.dataflows.chart_trendlines import compare_trendlines

START = date(2016, 10, 3)
DAY = date(2026, 11, 20)
END = date(2026, 12, 7)
SEOUL = ZoneInfo("Asia/Seoul")


@pytest.fixture
def chart_export(tmp_path):
    path = tmp_path / "tratto.csv"
    schedule = xcals.get_calendar("XNYS", start=START, end=END)
    days = schedule.sessions_in_range(START, DAY)
    rows = []
    for i, stamp in enumerate(days):
        trade_date = stamp.date()
        date_string = datetime.combine(trade_date, time.min, SEOUL).astimezone(UTC).isoformat()
        base = 100 * math.exp(0.0005 * i)
        low = base * (1 + 0.025 * (1 - math.cos(2 * math.pi * (i % 125) / 125)))
        opened, high, close = low * 1.003, low * 1.018, low * 1.017
        if i == len(days) - 1:
            low, opened, close = base * 0.97, base, base * 0.98
        rows.append([date_string, opened, high, low, close, 1_000])
    save_chart(path, rows)
    return path, rows


def save_chart(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["date", "o", "h", "l", "c", "v"], *rows])


def compare(path, **overrides):
    return compare_trendlines(path, **{
        "ticker": "SYNTH", "start": START, "as_of": DAY, "pivot_start": date(2022, 10, 1),
        "chart_timezone": SEOUL, "min_bars": 2500, "compare_anchor": date(2020, 3, 23),
        "extend_to": END, **overrides,
    })


def test_candidate_counts_projection_and_future_bar_isolation(chart_export):
    path, rows = chart_export
    result = compare(path)
    assert result["status"] == "ok"
    counts = result["counts"]
    assert counts["pairs"] == math.comb(counts["pivots"], 2)
    assert counts["pairs"] > counts["geometry"] >= counts["near_close"] >= counts["historical"] >= counts["eligible"]
    assert counts["eligible"] == len(result["candidates"]) > 0
    assert len(result["selected"]["reactions"]) >= 3
    assert result["selected"]["close_position"] == "below"
    assert result["selected"]["endpoint"] == {
        "date": END.isoformat(), "price": result["selected"]["endpoint"]["price"],
        "future_sessions": 10, "projected": True,
    }
    assert float(result["selected"]["endpoint"]["price"]) > float(result["selected"]["as_of_line"])
    assert result["same_start_alternative"]["anchor"]["date"] == "2020-03-23"
    assert result["predictive_power"] == "not_evaluated"

    save_chart(path, [*rows, ["2026-11-22T15:00:00+00:00", 1, 2, 1, 2, 3]])
    assert result == compare(path)


@pytest.mark.parametrize(("case", "reason"), [
    ("missing", "session_mismatch"), ("duplicate", "session_mismatch"),
    ("bad_volume", "invalid_ohlcv"), ("minimum", "minimum_bars"),
])
def test_reject_invalid_input_without_drawing_coordinates(chart_export, case, reason):
    path, rows = chart_export
    options = {}
    if case == "missing":
        rows.pop(10)
    elif case == "duplicate":
        rows.append(rows[10])
    elif case == "bad_volume":
        rows[10][-1] = 0
    else:
        options["min_bars"] = 2600
    save_chart(path, rows)
    result = compare(path, **options)
    assert result["reason"] == reason
    assert result["selected"] is None and result["candidates"] == []


def test_cli_exposes_candidate_diagnostics(chart_export):
    path, _ = chart_export
    output = CliRunner().invoke(app, [
        "chart-trendlines", "--symbol", "SYNTH", "--chart-csv", str(path), "--start", START.isoformat(),
        "--as-of", DAY.isoformat(), "--pivot-start", "2022-10-01", "--min-bars", "2500",
        "--chart-timezone", "Asia/Seoul", "--json",
    ])
    assert output.exit_code == 0, output.output
    report = json.loads(output.output)
    assert report["ticker"] == "SYNTH" and report["bars"] >= 2500
    assert report["selected"]["endpoint"]["projected"] is False
