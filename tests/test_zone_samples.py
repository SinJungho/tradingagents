import json
from datetime import UTC, datetime
from types import SimpleNamespace

from typer.testing import CliRunner

from cli import main as cli_main
from tradingagents.zone_samples import FIXED_SAMPLE, held_tickers, write_sample


def test_fixed_sample_has_48_tickers_and_holdings_are_prioritized_separately(tmp_path):
    result = write_sample(holdings=["AAPL", "NEW"], priority_tickers=["AAPL", "NEW"],
                          retrieved_at="2026-11-18T12:00:00+00:00", root=tmp_path)

    assert sum(map(len, FIXED_SAMPLE.values())) == 48
    assert len(result["tickers"]) == 49
    assert result["holdings_added"] == ["NEW"]
    assert result["priority_tickers"] == ["AAPL", "NEW"]
    assert result["ordered_tickers"][:2] == ["AAPL", "NEW"]
    assert len(result["batches"][0]) == 10
    stored = json.loads((tmp_path / result["path"].split("/")[-1]).read_text())
    assert "account_seq" not in stored
    assert "holdings" not in stored
    assert "NEW" in stored["tickers"]


def test_sold_holdings_remain_in_immutable_sample_history(tmp_path):
    first = write_sample(holdings=["NEW"], priority_tickers=["NEW"],
                         retrieved_at="2026-11-18T12:00:00+00:00", root=tmp_path)
    second = write_sample(holdings=[], priority_tickers=[],
                          retrieved_at="2026-11-19T12:00:00+00:00", root=tmp_path)

    assert "NEW" in first["tickers"] and "NEW" in second["tickers"]
    assert second["priority_tickers"] == []
    assert len(list(tmp_path.glob("v1-*.json"))) == 2


def test_same_holdings_refresh_keeps_immutable_sample_bytes_and_id(tmp_path):
    first = write_sample(holdings=["NEW"], priority_tickers=["NEW"],
                         retrieved_at="2026-11-18T12:00:00+00:00", root=tmp_path)
    original = (tmp_path / f"v1-{first['sha256'][:12]}.json").read_bytes()
    second = write_sample(holdings=["NEW"], priority_tickers=["NEW"],
                          retrieved_at="2026-11-25T12:00:00+00:00", root=tmp_path)

    assert second["sample_id"] == first["sample_id"]
    assert (tmp_path / f"v1-{first['sha256'][:12]}.json").read_bytes() == original
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["retrieved_at"] == "2026-11-25T12:00:00+00:00"


def test_holdings_sample_excludes_korean_listings():
    us = SimpleNamespace(symbol="BRK.B", market_country="US", exchange="NYSE")
    kr = SimpleNamespace(symbol="005930", market_country="KR", exchange="KRX")

    assert held_tickers([us, kr], country="US") == (["BRK-B"], [])


def test_zone_sample_refresh_uses_synthetic_read_only_holdings(monkeypatch, tmp_path):
    holdings = SimpleNamespace(
        holdings=[
            SimpleNamespace(symbol="BRK.B", market_country="US", exchange="NYSE"),
            SimpleNamespace(symbol="005930", market_country="KR", exchange="KRX"),
        ],
        retrieved_at=datetime(2026, 11, 18, 12, tzinfo=UTC),
    )

    class FakeAdapter:
        def __init__(self, *_args):
            pass

        def get_accounts(self):
            return object()

        def get_holdings(self, _account_seq):
            return holdings

    monkeypatch.setenv("TOSS_BROKER_READ_ONLY_VERIFIED", "I_ACKNOWLEDGE_READ_ONLY")
    monkeypatch.setenv("TOSS_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setattr("tradingagents.portfolio.toss.TossPortfolioAdapter", FakeAdapter)
    monkeypatch.setattr("cli.portfolio._select_account", lambda *_args: SimpleNamespace(account_seq=1))

    result = CliRunner().invoke(cli_main.app, ["zone-sample", "refresh", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "미국 외 제외 1개" in result.output
    sample = json.loads(next(tmp_path.glob("v1-*.json")).read_text())
    assert "BRK-B" in sample["tickers"]
    assert "BRK-B" in sample["priority_tickers"]
    assert "005930" not in sample["tickers"]
    assert "synthetic-secret" not in result.output


def test_zone_sample_refresh_without_retrieval_time_keeps_prior_pointer(monkeypatch, tmp_path):
    write_sample(holdings=["OLD"], priority_tickers=["OLD"],
                 retrieved_at="2026-11-18T12:00:00+00:00", root=tmp_path)
    pointer_before = (tmp_path / "latest.json").read_bytes()
    holdings = SimpleNamespace(holdings=[SimpleNamespace(symbol="NEW", market_country="US", exchange="NYSE")],
                               retrieved_at=None)

    class FakeAdapter:
        def __init__(self, *_args):
            pass

        def get_accounts(self):
            return object()

        def get_holdings(self, _account_seq):
            return holdings

    monkeypatch.setenv("TOSS_BROKER_READ_ONLY_VERIFIED", "I_ACKNOWLEDGE_READ_ONLY")
    monkeypatch.setenv("TOSS_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setattr("tradingagents.portfolio.toss.TossPortfolioAdapter", FakeAdapter)
    monkeypatch.setattr("cli.portfolio._select_account", lambda *_args: SimpleNamespace(account_seq=1))

    result = CliRunner().invoke(cli_main.app, ["zone-sample", "refresh", "--output-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "조회 시각이 없어" in result.output
    assert (tmp_path / "latest.json").read_bytes() == pointer_before
    assert "NEW" not in next(tmp_path.glob("v1-*.json")).read_text()
