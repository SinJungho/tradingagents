import json

import pandas as pd
from typer.testing import CliRunner

from cli.main import app


def test_chart_zones_cli_enforces_ten_ticker_limit_before_fetch(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("tradingagents.dataflows.chart_zones.get_chart_zones_with_snapshot",
                        lambda *args, **kwargs: calls.append(args))

    result = CliRunner().invoke(app, [
        "chart-zones", "--tickers", ",".join(f"T{i}" for i in range(11)),
        "--output-dir", str(tmp_path),
    ])

    assert result.exit_code == 2
    assert "At most 10 tickers are allowed" in result.output
    assert calls == []


def test_chart_zones_cli_continues_after_one_ticker_fails(monkeypatch, tmp_path):
    calls = []

    def fetch(symbol, as_of):
        calls.append(symbol)
        if symbol == "BAD":
            raise RuntimeError("synthetic Yahoo failure")
        frame = pd.DataFrame({"Open": [10.0], "High": [12.0], "Low": [9.0],
                              "Close": [11.0], "Volume": [100]},
                             index=pd.DatetimeIndex(["2025-01-02"], name="Date"))
        return ({"ticker": symbol, "as_of": "2025-01-02", "status": "ok",
                 "snapshot_sha256": "1234567890abcdef", "zones": [],
                 "validation": {"pending": True, "stale": False}, "trend": {}}, frame)

    monkeypatch.setattr("tradingagents.dataflows.chart_zones.get_chart_zones_with_snapshot", fetch)

    result = CliRunner().invoke(app, [
        "chart-zones", "--tickers", "BAD,GOOD", "--date", "2025-01-02", "--json",
        "--output-dir", str(tmp_path),
    ])

    rows = json.loads(result.output)
    assert result.exit_code == 1
    assert calls == ["BAD", "GOOD"]
    assert [row["status"] for row in rows] == ["failed", "ok"]
    assert rows[1]["run_dir"]


def test_chart_zones_cli_does_not_accept_weekly_mode(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("tradingagents.dataflows.chart_zones.get_chart_zones_with_snapshot",
                        lambda *args, **kwargs: calls.append(args))

    result = CliRunner().invoke(app, [
        "chart-zones", "--tickers", "SYN", "--periodicity", "weekly",
        "--output-dir", str(tmp_path),
    ])

    assert result.exit_code == 2
    assert "No such option" in result.output
    assert calls == []


def test_chart_check_cli_interprets_export_dates_in_explicit_timezone(tmp_path):
    (tmp_path / "snapshot.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n2026-11-18,10,12,9,11,100\n"
    )
    (tmp_path / "zones.json").write_text(json.dumps({
        "ticker": "QQQ", "as_of": "2026-11-18", "snapshot_sha256": "synthetic",
        "check_windows": {"recent": {"dates": ["2026-11-18"], "count": 1}},
    }))
    csv = tmp_path / "export.csv"
    raw = "date,o,h,l,c,v\n2026-11-17T15:00:00Z,10,12,9,11,100\n"
    csv.write_text(raw)

    args = ["chart-check", "--run-dir", str(tmp_path), "--chart-csv", str(csv), "--json"]
    default = CliRunner().invoke(app, args)
    local = CliRunner().invoke(app, [*args, "--chart-timezone", "Asia/Seoul"])
    assert json.loads(default.output)["status"] == "insufficient"
    assert local.exit_code == 0
    result = json.loads(local.output)
    assert result["status"] == "ok"
    assert result["chart_timezone"] == "Asia/Seoul"
    assert (tmp_path / "chart_check.csv").read_text() == raw
