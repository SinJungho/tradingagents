from typer.testing import CliRunner

from cli.main import app
from tradingagents.api_diagnostics import APIFailure, EndpointProbe
from tradingagents.runtime_diagnostics import diagnose_runtime, worker_network_policy

runner = CliRunner()


def test_diagnostics_reports_current_worker_settings_without_values():
    config = {
        "llm_provider": "openai",
        "openai_auth": "api_key",
        "quick_think_provider": "openai",
        "deep_think_provider": "anthropic",
        "backend_url": "https://custom.example/v1?token=synthetic-endpoint-secret",
        "quick_think_backend_url": None,
        "deep_think_backend_url": None,
    }
    environ = {
        "ORCA_ENVIRONMENT": "local",
        "OPENAI_API_KEY": "synthetic-openai-key",
        "ANTHROPIC_API_KEY": "synthetic-anthropic-key",
        "TOSS_CLIENT_ID": "synthetic-client-id",
        "TOSS_CLIENT_SECRET": "synthetic-client-secret",
        "TOSS_BROKER_READ_ONLY_VERIFIED": "synthetic-acknowledgement",
        "FRED_API_KEY": "synthetic-fred-key",
    }
    seen = []

    def probe(url):
        seen.append(url)
        return EndpointProbe(False, APIFailure("timeout", True))

    report = diagnose_runtime(
        config=config,
        environ=environ,
        probe=probe,
        cwd="/synthetic/worker/project",
    )

    assert "Orca 실행 환경: local" in report
    assert "작업 디렉터리: /synthetic/worker/project" in report
    assert "quick: 제공자=openai" in report
    assert "deep: 제공자=anthropic" in report
    assert "OPENAI_API_KEY: 설정됨" in report
    assert "ANTHROPIC_API_KEY: 설정됨" in report
    assert "TOSS_CLIENT_SECRET: 설정됨" in report
    assert "FRED: 도달 실패: 시간 초과 (재시도 가능: 예)" in report
    assert all(
        secret not in report
        for name, secret in environ.items()
        if name != "ORCA_ENVIRONMENT"
    )
    assert "synthetic-endpoint-secret" not in report
    assert "custom.example" not in report
    assert "https://custom.example/v1?token=synthetic-endpoint-secret" in seen


def test_missing_worker_auth_and_hidden_orca_context_are_explicit():
    report = diagnose_runtime(
        config={
            "llm_provider": "openai",
            "openai_auth": "api_key",
            "quick_think_provider": None,
            "deep_think_provider": None,
        },
        environ={"ORCA_ENVIRONMENT": "local;synthetic-secret"},
        probe=lambda _url: EndpointProbe(True),
        cwd="/tmp/worker",
    )

    assert "Orca 실행 환경: 설정됨 (값 숨김)" in report
    assert "OPENAI_API_KEY: 누락" in report
    assert "인증=API 키 환경변수 (누락)" in report
    assert "synthetic-secret" not in report
    assert "프로세스에 노출되지 않음" not in report


def test_diagnostics_checks_public_data_hosts_without_printing_the_urls():
    seen = []

    def probe(url):
        seen.append(url)
        return EndpointProbe(True)

    report = diagnose_runtime(config={}, environ={}, probe=probe)

    for host in (
        "query1.finance.yahoo.com",
        "query2.finance.yahoo.com",
        "www.alphavantage.co",
        "api.stlouisfed.org",
        "www.sec.gov",
        "data.sec.gov",
        "openapi.tossinvest.com",
        "www.reddit.com",
        "api.stocktwits.com",
        "gamma-api.polymarket.com",
        "external-api.kalshi.com",
        "auth.openai.com",
    ):
        assert any(host in url for url in seen)
        assert host not in report

    assert "Yahoo Finance (quotes): 도달 가능" in report
    assert "SEC company facts: 도달 가능" in report


def test_worker_policy_contains_configured_data_vendors_only():
    policy = worker_network_policy(
        config={
            "llm_provider": "openai",
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "sec_edgar",
                "news_data": "yfinance",
                "macro_data": "fred",
                "prediction_markets": "kalshi",
            },
            "tool_vendors": {},
        },
        environ={},
    )
    hosts = {destination["hostname"] for destination in policy["destinations"]}

    assert {
        "query1.finance.yahoo.com",
        "query2.finance.yahoo.com",
        "www.sec.gov",
        "data.sec.gov",
        "api.stlouisfed.org",
        "external-api.kalshi.com",
        "www.reddit.com",
        "api.stocktwits.com",
    } <= hosts
    assert {
        "www.alphavantage.co",
        "gamma-api.polymarket.com",
        "openapi.tossinvest.com",
        "auth.openai.com",
    }.isdisjoint(hosts)


def test_worker_policy_honors_tool_vendor_override():
    policy = worker_network_policy(
        config={
            "llm_provider": "openai",
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "sec_edgar",
                "news_data": "yfinance",
                "macro_data": "fred",
                "prediction_markets": "kalshi",
            },
            "tool_vendors": {"get_stock_data": "alpha_vantage"},
        },
        environ={},
    )
    hosts = {destination["hostname"] for destination in policy["destinations"]}

    assert "www.alphavantage.co" in hosts


def test_worker_policy_includes_all_endpoints_for_unspecified_vendor_chain():
    policy = worker_network_policy(config={}, environ={})
    hosts = {destination["hostname"] for destination in policy["destinations"]}

    assert "www.alphavantage.co" in hosts
    assert "external-api.kalshi.com" in hosts
    assert "gamma-api.polymarket.com" in hosts


def test_worker_policy_uses_polymarket_default_without_kalshi():
    policy = worker_network_policy(
        config={
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "sec_edgar,yfinance",
                "news_data": "yfinance",
                "macro_data": "fred",
                "prediction_markets": "polymarket",
            },
            "tool_vendors": {},
        },
        environ={},
    )
    hosts = {destination["hostname"] for destination in policy["destinations"]}

    assert "gamma-api.polymarket.com" in hosts
    assert "external-api.kalshi.com" not in hosts


def test_worker_policy_includes_chatgpt_auth_only_when_selected():
    policy = worker_network_policy(
        config={"llm_provider": "openai", "openai_auth": "chatgpt_plan"},
        environ={},
    )
    hosts = {destination["hostname"] for destination in policy["destinations"]}

    assert "auth.openai.com" in hosts


def test_doctor_cli_uses_current_process_diagnostic(monkeypatch):
    monkeypatch.setattr("cli.main.diagnose_runtime", lambda: "synthetic diagnostic")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.output.strip() == "synthetic diagnostic"


def test_chatgpt_diagnoses_its_own_store_without_legacy_login(tmp_path, monkeypatch):
    from tradingagents.llm_clients import chatgpt_auth

    monkeypatch.setattr(chatgpt_auth, "AUTH_FILE", tmp_path / "chatgpt-auth.json")
    chatgpt_auth._write({"tokens": {"access_token": "synthetic-secret"}})
    monkeypatch.setattr(
        "tradingagents.chatgpt_plan_auth.connection_status",
        lambda: (_ for _ in ()).throw(AssertionError("wrong store")),
    )
    report = diagnose_runtime(
        config={"llm_provider": "chatgpt"}, environ={},
        probe=lambda _: EndpointProbe(False, APIFailure("dns", True)),
    )
    assert "저장됨; 유효성 미검증" in report
    assert "tradingagents login chatgpt" in report
    assert "auth connect" not in report
    assert "synthetic-secret" not in report
    assert "프로세스에 노출되지 않음" in report
    assert "도달 실패" in report


def test_legacy_plan_diagnosis_keeps_its_store_and_command(monkeypatch):
    monkeypatch.setattr("tradingagents.chatgpt_plan_auth.connection_status", lambda: None)
    report = diagnose_runtime(
        config={"llm_provider": "openai", "openai_auth": "chatgpt_plan"}, environ={},
        chatgpt_connected=lambda: True, probe=lambda _: EndpointProbe(True),
    )
    assert "연결 안 됨" in report
    assert "tradingagents auth connect" in report
    assert "login chatgpt" not in report
