"""Mocked wire coverage for TradingAgents' NVIDIA Build smoke path."""

import json
import time

import httpx
import pytest

from scripts import smoke_structured_output
from scripts.smoke_structured_output import (
    _reserve_nvidia_smoke_request_slot,
    _run_nvidia_single_call,
    _run_single_structured_call,
)


@pytest.fixture(autouse=True)
def isolate_local_rate_limit_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        smoke_structured_output,
        "NVIDIA_SMOKE_RATE_LIMIT_FILE",
        tmp_path / "last-request",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    ["deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"],
)
def test_nvidia_smoke_sends_one_capped_synthetic_request(monkeypatch, model):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")
    requests = []
    client_options = {}
    create_llm_client = smoke_structured_output.create_llm_client

    def capture_client_options(**kwargs):
        client_options.update(kwargs)
        return create_llm_client(**kwargs)

    monkeypatch.setattr(
        smoke_structured_output, "create_llm_client", capture_client_options
    )

    def handle_request(request):
        payload = json.loads(request.content)
        requests.append((request, payload))
        tool_name = payload["tools"][0]["function"]["name"]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-synthetic",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_content": "synthetic-only reasoning",
                            "tool_calls": [
                                {
                                    "id": "call-synthetic",
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(
                                            {
                                                "recommendation": "Hold",
                                                "rationale": "Synthetic fixture rationale.",
                                                "strategic_actions": "No real action; fixture only.",
                                            }
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 37,
                    "completion_tokens": 18,
                    "total_tokens": 55,
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle_request)) as http_client:
        result, _elapsed = _run_single_structured_call(
            model, 96, provider="nvidia", http_client=http_client
        )

    assert len(requests) == 1
    request, payload = requests[0]
    assert str(request.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert payload["model"] == model
    assert payload.get("max_tokens") == 96, payload.keys()
    assert "max_completion_tokens" not in payload
    assert client_options["timeout"] == 300
    assert "tools" in payload
    assert "tool_choice" not in payload
    assert all("SYNTHETIC-ASSET-001" in message["content"] for message in payload["messages"])
    assert result["parsed"].recommendation.value == "Hold"
    assert result["raw"].response_metadata["token_usage"]["total_tokens"] == 55


@pytest.mark.unit
def test_structured_call_rejects_output_cap_over_256(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("invalid token cap must be rejected before client creation")

    monkeypatch.setattr(smoke_structured_output, "create_llm_client", fail_if_called)

    with pytest.raises(ValueError, match="between 1 and 256"):
        _run_single_structured_call(
            "deepseek-ai/deepseek-v4.1-flash", 257, provider="nvidia"
        )


@pytest.mark.unit
def test_local_rate_limit_reserves_one_slot_per_minute():
    reserved, wait_seconds = _reserve_nvidia_smoke_request_slot()
    assert reserved is True
    assert wait_seconds == 0

    reserved, wait_seconds = _reserve_nvidia_smoke_request_slot()
    assert reserved is False
    assert 1 <= wait_seconds <= 60


@pytest.mark.unit
def test_live_smoke_skips_when_nvidia_key_is_missing(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("missing-key smoke must not create or invoke a client")

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call", fail_if_called
    )

    assert _run_nvidia_single_call(
        "deepseek-ai/deepseek-v4.1-flash", 96, confirmed_no_charge=True
    ) == 2
    output = capsys.readouterr().out
    assert "NVIDIA_API_KEY is not set" in output
    assert "no API request was made" in output


@pytest.mark.unit
def test_live_smoke_requires_no_charge_confirmation(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("unconfirmed smoke must not create or invoke a client")

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call", fail_if_called
    )

    assert _run_nvidia_single_call("deepseek-ai/deepseek-v4.1-flash", 96) == 2
    output = capsys.readouterr().out
    assert "no-charge NVIDIA evaluation quota was not confirmed" in output
    assert "no API request was made" in output


@pytest.mark.unit
def test_live_smoke_enforces_one_request_per_minute(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")
    smoke_structured_output.NVIDIA_SMOKE_RATE_LIMIT_FILE.write_text(
        f"{time.time():.6f}", encoding="ascii"
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("cooldown must skip before the LLM call")

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call", fail_if_called
    )

    assert _run_nvidia_single_call(
        "deepseek-ai/deepseek-v4.1-flash", 96, confirmed_no_charge=True
    ) == 2
    output = capsys.readouterr().out
    assert "local safety limit is 1 request per 60 seconds" in output
    assert "no api request was made" in output.lower()


@pytest.mark.unit
def test_live_smoke_rejects_output_cap_over_256_before_request(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("invalid token cap must be rejected before the LLM call")

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call", fail_if_called
    )

    assert _run_nvidia_single_call(
        "deepseek-ai/deepseek-v4.1-flash", 257, confirmed_no_charge=True
    ) == 2
    output = capsys.readouterr().out
    assert "--max-tokens must be between 1 and 256" in output
    assert "no api request was made" in output.lower()


@pytest.mark.unit
def test_nvidia_provider_requires_bounded_single_call_mode(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["smoke_structured_output.py", "nvidia"])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("unbounded NVIDIA mode must be rejected before client creation")

    monkeypatch.setattr(smoke_structured_output, "create_llm_client", fail_if_called)

    with pytest.raises(SystemExit) as exc_info:
        smoke_structured_output.main()

    assert exc_info.value.code == 2
    assert "requires --single-call" in capsys.readouterr().err


@pytest.mark.unit
def test_cli_rejects_max_tokens_over_256_before_client_creation(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["smoke_structured_output.py", "nvidia", "--single-call", "--max-tokens", "257"],
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("invalid token cap must be rejected before client creation")

    monkeypatch.setattr(smoke_structured_output, "create_llm_client", fail_if_called)

    with pytest.raises(SystemExit) as exc_info:
        smoke_structured_output.main()

    assert exc_info.value.code == 2
    assert "--max-tokens must be between 1 and 256" in capsys.readouterr().err


@pytest.mark.unit
def test_live_smoke_reports_safe_transport_cause(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")

    def fail_with_transport_error(*_args, **_kwargs):
        try:
            raise OSError("private transport detail")
        except OSError as cause:
            raise RuntimeError("private request detail") from cause

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call",
        fail_with_transport_error,
    )

    assert _run_nvidia_single_call(
        "deepseek-ai/deepseek-v4.1-flash", 96, confirmed_no_charge=True
    ) == 1
    output = capsys.readouterr().out
    assert "RuntimeError; cause=OSError" in output
    assert "private transport detail" not in output
    assert "private request detail" not in output
    assert "synthetic-test-key" not in output


@pytest.mark.unit
def test_live_smoke_reports_http_status_without_error_body(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")

    class SyntheticHTTPError(Exception):
        status_code = 401

    def fail_with_http_error(*_args, **_kwargs):
        raise SyntheticHTTPError("private provider response body")

    monkeypatch.setattr(
        "scripts.smoke_structured_output._run_single_structured_call",
        fail_with_http_error,
    )

    assert _run_nvidia_single_call(
        "deepseek-ai/deepseek-v4.1-flash", 96, confirmed_no_charge=True
    ) == 1
    output = capsys.readouterr().out
    assert "SyntheticHTTPError; HTTP 401" in output
    assert "private provider response body" not in output
    assert "synthetic-test-key" not in output
