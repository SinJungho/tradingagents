import os

import pytest
from typer.testing import CliRunner

from cli import main
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.mark.parametrize(
    ("preset", "expected"),
    [("standard", ("gpt-6-luna", "medium")), ("deep", ("gpt-6.2-sol", "high"))],
)
def test_ticker_preset_applies_only_during_cli_run(monkeypatch, preset, expected):
    monkeypatch.setitem(DEFAULT_CONFIG, "llm_provider", "chatgpt")
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_provider", None)
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_provider", None)
    monkeypatch.setenv("TRADINGAGENTS_OPENAI_REASONING_EFFORT", "low")
    before = DEFAULT_CONFIG.copy()

    def check_config(**kwargs):
        assert DEFAULT_CONFIG["quick_think_llm"] == expected[0]
        assert DEFAULT_CONFIG["deep_think_llm"] == "gpt-6.1-sol"
        assert DEFAULT_CONFIG["openai_reasoning_effort"] == expected[1]
        assert os.environ["TRADINGAGENTS_QUICK_THINK_LLM"] == expected[0]

    monkeypatch.setattr(main, "run_analysis", check_config)
    result = CliRunner().invoke(main.app, ["--ticker", "TEST", "--model-preset", preset])
    assert result.exit_code == 0, result.exception
    assert before == DEFAULT_CONFIG
    assert os.environ["TRADINGAGENTS_OPENAI_REASONING_EFFORT"] == "low"
