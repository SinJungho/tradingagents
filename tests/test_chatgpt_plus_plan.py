"""Mock-only coverage for the opt-in ChatGPT plan authentication path."""

import base64
import hashlib
import json

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from cli.prompts import ensure_api_key
from tradingagents import chatgpt_plan_auth as auth
from tradingagents.llm_clients.chatgpt_plan import ChatGPTPlanChatModel
from tradingagents.llm_clients.factory import build_llm_kwargs
from tradingagents.llm_clients.openai_client import OpenAIClient


class FakeResponse:
    def __init__(self, payload=None, status_code=200, events=None):
        self.payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.events = events or []
        self.closed = False

    def json(self):
        return self.payload

    def iter_lines(self, decode_unicode=False):
        return [f"data: {json.dumps(event)}".encode() for event in self.events]

    def close(self):
        self.closed = True


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setattr(auth.Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.mark.unit
def test_oauth_connect_validates_callback_and_saves_secure_credentials(
    isolated_home, monkeypatch
):
    state_data = {}
    token_request = {}

    def wait_callback(params, timeout):
        state_data.update({key: [value] for key, value in params.items()})
        return "http://127.0.0.1:1455/auth/callback", {
            "code": ["synthetic-code"],
            "state": [params["state"]],
            "client_id": ["oaiapp_synthetic"],
            "scope": [auth.SCOPES],
        }

    def post(url, data, timeout):
        token_request.update(data)
        return FakeResponse(
            {
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "id_token": "synthetic-id-token",
                "expires_in": 3600,
                "scope": auth.SCOPES,
            }
        )

    monkeypatch.setattr(auth, "_wait_for_callback", wait_callback)
    monkeypatch.setattr(auth.requests, "post", post)
    monkeypatch.setattr(
        auth,
        "_validate_id_token",
        lambda token, client_id, nonce: {
            "sub": "synthetic-subject",
            "email": "synthetic@example.test",
            "nonce": state_data["nonce"][0],
        },
    )

    account = auth.connect_chatgpt(timeout=5)

    assert account == {"email": "synthetic@example.test", "client_id": "oaiapp_synthetic"}
    assert state_data["client_id"] == ["dynamic_agent_client"]
    assert state_data["code_challenge_method"] == ["S256"]
    assert token_request["client_id"] == "oaiapp_synthetic"
    assert token_request["code"] == "synthetic-code"
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(token_request["code_verifier"].encode()).digest()
    ).decode().rstrip("=")
    assert state_data["code_challenge"] == [expected_challenge]
    assert auth.connection_status() == account
    assert auth.credentials_path().stat().st_mode & 0o777 == 0o600
    saved = json.loads(auth.credentials_path().read_text())
    assert saved["access_token"] == "synthetic-access"
    assert "chatgpt.tokens.use.direct" in saved["scopes"]


@pytest.mark.unit
def test_oauth_does_not_save_credentials_without_plan_scope(isolated_home, monkeypatch):
    def wait_callback(params, timeout):
        return "http://127.0.0.1:1455/auth/callback", {
            "code": ["synthetic-code"],
            "state": [params["state"]],
            "client_id": ["oaiapp_synthetic"],
            "scope": [auth.SCOPES],
        }

    monkeypatch.setattr(auth, "_wait_for_callback", wait_callback)
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "id_token": "synthetic-id-token",
                "scope": "openid profile email",
            }
        ),
    )
    monkeypatch.setattr(auth, "_validate_id_token", lambda *args: pytest.fail("must not validate"))

    with pytest.raises(auth.ChatGPTAuthError, match="not authorized"):
        auth.connect_chatgpt(timeout=5)
    assert not auth.credentials_path().exists()


@pytest.mark.unit
def test_refresh_rotates_tokens_and_checks_scope(isolated_home, monkeypatch):
    auth._save_credentials(
        {
            "client_id": "oaiapp_synthetic",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "id_token": "synthetic-id",
            "scopes": [auth.PLAN_SCOPE],
            "expires_at": 1,
        }
    )
    request = {}

    def post(url, data, timeout):
        request.update(data)
        return FakeResponse(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(auth.requests, "post", post)
    assert auth.get_access_token() == "new-access"
    assert request["grant_type"] == "refresh_token"
    assert request["client_id"] == "oaiapp_synthetic"
    renewed = json.loads(auth.credentials_path().read_text())
    assert renewed["refresh_token"] == "new-refresh"
    assert auth.PLAN_SCOPE in renewed["scopes"]


@pytest.mark.unit
def test_disconnect_revokes_refresh_token_and_clears_only_local_credentials(
    isolated_home, monkeypatch
):
    auth._save_credentials(
        {
            "client_id": "oaiapp_synthetic",
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "id_token": "synthetic-id",
            "scopes": [auth.PLAN_SCOPE],
        }
    )
    post_data = {}
    monkeypatch.setattr(
        auth.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {"revocation_endpoint": "https://auth.openai.com/revoke"}
        ),
    )

    def post(url, data, timeout):
        post_data.update(data)
        return FakeResponse({})

    monkeypatch.setattr(auth.requests, "post", post)
    assert auth.disconnect_chatgpt() is True
    assert post_data["token"] == "synthetic-refresh"
    assert not auth.credentials_path().exists()


@pytest.mark.unit
def test_plan_model_uses_required_streaming_payload_and_namespaced_tools(monkeypatch):
    from langchain_core.tools import tool

    @tool
    def lookup(symbol: str) -> str:
        """Read synthetic market data for one symbol."""
        return symbol

    request = {}
    events = [
        {
            "type": "response.completed",
            "response": {
                "model": "account-model",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-synthetic",
                        "name": "tradingagents.lookup",
                        "arguments": '{"symbol":"NVDA"}',
                    }
                ],
                "usage": {"input_tokens": 11, "output_tokens": 3},
            },
        }
    ]
    monkeypatch.setattr(
        "tradingagents.llm_clients.chatgpt_plan.requests.post",
        lambda url, **kwargs: (request.update(kwargs) or FakeResponse(events=events)),
    )
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    response = model.bind_tools([lookup], tool_choice="required").invoke(
        [SystemMessage(content="Research safely."), HumanMessage(content="Check NVDA.")]
    )

    payload = request["json"]
    assert request["headers"]["Authorization"] == "Bearer oauth-token"
    assert request["stream"] is True
    assert payload["store"] is False and payload["stream"] is True
    assert "temperature" not in payload and "max_output_tokens" not in payload
    assert payload["input"][0]["role"] == "developer"
    assert payload["tools"][0]["type"] == "namespace"
    assert payload["tools"][0]["tools"][0]["name"] == "lookup"
    assert payload["tool_choice"] == "required"
    assert response.tool_calls == [
        {"name": "lookup", "args": {"symbol": "NVDA"}, "id": "call-synthetic", "type": "tool_call"}
    ]
    assert response.usage_metadata["total_tokens"] == 14


@pytest.mark.unit
def test_plan_model_requires_completed_event_and_does_not_retry(monkeypatch):
    request_count = 0

    def post(url, **kwargs):
        nonlocal request_count
        request_count += 1
        return FakeResponse(events=[{"type": "response.output_text.delta", "delta": "partial"}])

    monkeypatch.setattr("tradingagents.llm_clients.chatgpt_plan.requests.post", post)
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    with pytest.raises(RuntimeError, match="without response.completed"):
        model.invoke("synthetic prompt")
    assert request_count == 1


@pytest.mark.unit
def test_plan_usage_limit_is_reported_without_a_second_request(monkeypatch):
    request_count = 0

    def post(url, **kwargs):
        nonlocal request_count
        request_count += 1
        return FakeResponse(
            {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
            status_code=429,
        )

    monkeypatch.setattr("tradingagents.llm_clients.chatgpt_plan.requests.post", post)
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    with pytest.raises(RuntimeError, match="usage limit reached"):
        model.invoke("Synthetic prompt")
    assert request_count == 1


@pytest.mark.unit
def test_temporary_plan_usage_unavailability_is_not_retried(monkeypatch):
    request_count = 0

    def post(url, **kwargs):
        nonlocal request_count
        request_count += 1
        return FakeResponse(
            {"error": {"code": "subscription_sharing_usage_unavailable"}},
            status_code=503,
        )

    monkeypatch.setattr("tradingagents.llm_clients.chatgpt_plan.requests.post", post)
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        model.invoke("Synthetic prompt")
    assert request_count == 1


@pytest.mark.unit
def test_plan_model_returns_text_only_after_completed_event(monkeypatch):
    request = {}
    events = [
        {
            "type": "response.completed",
            "response": {
                "model": "account-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Synthetic analysis."}],
                    }
                ],
            },
        }
    ]
    monkeypatch.setattr(
        "tradingagents.llm_clients.chatgpt_plan.requests.post",
        lambda url, **kwargs: (request.update(kwargs) or FakeResponse(events=events)),
    )
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    response = model.invoke(
        [SystemMessage(content="Be concise."), HumanMessage(content="Analyze synthetic data.")]
    )
    assert response.content == "Synthetic analysis."
    assert request["json"]["input"] == [
        {"role": "developer", "content": "Be concise."},
        {"role": "user", "content": "Analyze synthetic data."},
    ]


@pytest.mark.unit
def test_structured_output_uses_namespaced_function_tool(monkeypatch):
    class SyntheticDecision(BaseModel):
        action: str

    request = {}
    events = [
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "structured-synthetic",
                        "name": "tradingagents.SyntheticDecision",
                        "arguments": '{"action":"hold"}',
                    }
                ]
            },
        }
    ]
    monkeypatch.setattr(
        "tradingagents.llm_clients.chatgpt_plan.requests.post",
        lambda url, **kwargs: (request.update(kwargs) or FakeResponse(events=events)),
    )
    model = ChatGPTPlanChatModel(model="account-model", token_provider=lambda: "oauth-token")
    result = model.with_structured_output(SyntheticDecision).invoke("Synthetic prompt")

    assert result == SyntheticDecision(action="hold")
    assert request["json"]["tool_choice"] == "required"
    assert request["json"]["tools"][0]["tools"][0]["name"] == "SyntheticDecision"


@pytest.mark.unit
def test_openai_client_plan_mode_never_reads_api_key_or_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setattr("tradingagents.chatgpt_plan_auth.get_access_token", lambda: "oauth-token")
    request = {}
    monkeypatch.setattr(
        "tradingagents.llm_clients.chatgpt_plan.requests.post",
        lambda url, **kwargs: (request.update(kwargs) or FakeResponse(events=[
            {
                "type": "response.completed",
                "response": {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "Synthetic answer."}
                ]}]},
            }
        ])),
    )
    llm = OpenAIClient(
        "account-model", provider="openai", openai_auth="chatgpt_plan"
    ).get_llm()
    assert isinstance(llm, ChatGPTPlanChatModel)
    assert llm.invoke("Synthetic question").content == "Synthetic answer."
    assert request["headers"]["Authorization"] == "Bearer oauth-token"
    assert "must-not-be-used" not in request["headers"]["Authorization"]

    monkeypatch.setenv("TRADINGAGENTS_OPENAI_AUTH", "chatgpt_plan")
    assert ensure_api_key("openai") is None
    with pytest.raises(ValueError, match="requires provider 'openai'"):
        ensure_api_key("deepseek")


@pytest.mark.unit
def test_plan_mode_does_not_forward_unsupported_sampling_or_retry_options():
    config = {
        "llm_provider": "openai",
        "openai_auth": "chatgpt_plan",
        "openai_reasoning_effort": "high",
        "temperature": 0.2,
        "llm_max_retries": 4,
        "max_tokens": 1200,
    }
    assert build_llm_kwargs(config) == {"openai_auth": "chatgpt_plan"}
    config["llm_provider"] = "deepseek"
    with pytest.raises(ValueError, match="requires llm_provider='openai'"):
        build_llm_kwargs(config)


@pytest.mark.unit
def test_openai_api_key_mode_remains_default():
    client = OpenAIClient("gpt-5.5", provider="openai")
    assert client.kwargs.get("openai_auth", "api_key") == "api_key"
