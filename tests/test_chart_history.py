import pandas as pd

from tradingagents.dataflows.vendors.yahoo import chart_history


def test_chart_history_requests_unadjusted_daily_data_and_preserves_actions(monkeypatch):
    calls = {}
    index = pd.DatetimeIndex(["2025-01-02", "2025-01-03"], tz="America/New_York")
    expected = pd.DataFrame({
        "Open": [10.0, 11.0], "High": [12.0, 13.0], "Low": [9.0, 10.0],
        "Close": [11.0, 12.0], "Adj Close": [10.5, 11.5], "Volume": [100, 110],
        "Dividends": [0.0, 0.5], "Stock Splits": [0.0, 0.0],
    }, index=index)

    class FakeTicker:
        def __init__(self, symbol):
            calls["symbol"] = symbol

        def history(self, **kwargs):
            calls["kwargs"] = kwargs
            return expected

    monkeypatch.setattr(chart_history.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(chart_history, "yf_retry", lambda request: request())

    result = chart_history.get_chart_history("BRK-B", start="2024-01-01", end="2025-01-03")

    assert calls["symbol"] == "BRK-B"
    assert calls["kwargs"] == {
        "start": "2024-01-01", "end": "2025-01-04", "interval": "1d",
        "auto_adjust": False, "actions": True,
    }
    assert result.index.tz is None
    assert result["Dividends"].tolist() == [0.0, 0.5]
    assert result["Stock Splits"].tolist() == [0.0, 0.0]
