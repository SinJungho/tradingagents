"""Diagnostics for the API configuration visible to the current worker process."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from tradingagents.api_diagnostics import (
    APIFailure,
    EndpointProbe,
    format_api_failure,
    probe_endpoint,
)
from tradingagents.default_config import build_default_config
from tradingagents.llm_clients.api_key_env import get_api_key_env

_PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "chatgpt": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "google": "https://generativelanguage.googleapis.com",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "qwen-cn": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://api.z.ai/api/paas/v4/",
    "glm-cn": "https://open.bigmodel.cn/api/paas/v4/",
    "minimax": "https://api.minimax.io/v1",
    "minimax-cn": "https://api.minimaxi.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "ollama": "http://localhost:11434/v1",
}
_DATA_ENDPOINTS = (
    ("Yahoo Finance", "https://query1.finance.yahoo.com"),
    ("SEC EDGAR", "https://www.sec.gov"),
    ("Toss Open API", "https://openapi.tossinvest.com"),
)
_TYPESAFE_ENDPOINT = "https://api.typesafe.ai"
_TOSS_ENV = (
    "TOSS_CLIENT_ID",
    "TOSS_CLIENT_SECRET",
    "TOSS_BROKER_READ_ONLY_VERIFIED",
)
_BEDROCK_ENV = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_PROFILE",
    "AWS_ACCESS_KEY_ID",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
)
_SAFE_CONTEXT_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _configured(environ: Mapping[str, str], name: str) -> bool:
    return bool(environ.get(name, "").strip())


def _provider(config: Mapping[str, object], tier: str) -> str:
    value = config.get(f"{tier}_think_provider") or config.get("llm_provider")
    if not isinstance(value, str):
        return "unknown"
    provider = value.strip().lower()
    return provider if re.fullmatch(r"[a-z0-9_-]{1,40}", provider) else "unknown"


def _tier_base_url(config: Mapping[str, object], provider: str, tier: str) -> str | None:
    tier_url = config.get(f"{tier}_think_backend_url")
    main_provider = str(config.get("llm_provider") or "").lower()
    configured_url = tier_url or (config.get("backend_url") if provider == main_provider else None)
    return configured_url.strip() if isinstance(configured_url, str) and configured_url.strip() else None


def _endpoint_url(
    provider: str, base_url: str | None, environ: Mapping[str, str]
) -> str | None:
    if base_url:
        return base_url
    if provider == "azure":
        return environ.get("AZURE_OPENAI_ENDPOINT") or None
    if provider == "ollama":
        return environ.get("OLLAMA_BASE_URL") or _PROVIDER_ENDPOINTS[provider]
    if provider == "openai_compatible":
        return None
    if provider == "bedrock":
        region = environ.get("AWS_REGION") or environ.get("AWS_DEFAULT_REGION") or "us-west-2"
        if not re.fullmatch(r"[a-z0-9-]{2,32}", region):
            return None
        return f"https://bedrock-runtime.{region}.amazonaws.com"
    return _PROVIDER_ENDPOINTS.get(provider)


def _auth_status(
    provider: str,
    config: Mapping[str, object],
    environ: Mapping[str, str],
    chatgpt_connected: Callable[[], bool],
    chatgpt_plan_connected: Callable[[], bool],
) -> tuple[str, tuple[str, ...], str]:
    if provider == "chatgpt" or (
        provider == "openai" and config.get("openai_auth") == "chatgpt_plan"
    ):
        try:
            connected = (chatgpt_connected if provider == "chatgpt" else chatgpt_plan_connected)()
        except Exception:
            connected = False
        command = "tradingagents login chatgpt" if provider == "chatgpt" else "tradingagents auth connect"
        state = "저장됨; 유효성 미검증" if connected else "연결 안 됨"
        return "ChatGPT plan 로컬 로그인", (), f"{state}; 로그인/복구: {command}"
    if provider == "bedrock":
        names = _BEDROCK_ENV
        configured = any(_configured(environ, name) for name in names)
        return "AWS 자격 증명 체인", names, "설정됨" if configured else "프로세스에서 확인 안 됨"
    if provider == "ollama":
        return "로컬 서버 인증 없음", (), "키 불필요"

    key_env = get_api_key_env(provider)
    if key_env is None:
        return "인증 방식 확인 불가", (), "제공자 또는 키 변수를 확인할 수 없음"
    configured = _configured(environ, key_env)
    if provider == "openai_compatible":
        return "선택 사항 API 키", (key_env,), "설정됨" if configured else "키 없이 사용"
    return "API 키 환경변수", (key_env,), "설정됨" if configured else "누락"


def _chatgpt_connected() -> bool:
    from tradingagents.llm_clients.chatgpt_auth import credential

    credential()  # Check local presence without refreshing or exposing account details.
    return True


def _chatgpt_plan_connected() -> bool:
    from tradingagents.chatgpt_plan_auth import connection_status

    return connection_status() is not None


def _safe_context(environ: Mapping[str, str]) -> str:
    value = environ.get("ORCA_ENVIRONMENT", "").strip()
    if not value:
        return "프로세스에 노출되지 않음"
    if _SAFE_CONTEXT_VALUE.fullmatch(value):
        return value
    return "설정됨 (값 숨김)"


def _probe_status(probe: EndpointProbe) -> str:
    if probe.reachable:
        return "도달 가능"
    return f"도달 실패: {format_api_failure(probe.failure or APIFailure('unknown', False))}"


def diagnose_runtime(
    *,
    config: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
    probe: Callable[[str], EndpointProbe] = probe_endpoint,
    chatgpt_connected: Callable[[], bool] = _chatgpt_connected,
    chatgpt_plan_connected: Callable[[], bool] = _chatgpt_plan_connected,
    cwd: str | None = None,
) -> str:
    """Build a safe diagnostic report using only the current process context."""
    active_env = os.environ if environ is None else environ
    active_config = build_default_config() if config is None else config
    working_directory = cwd if cwd is not None else os.getcwd()
    working_directory = _CONTROL.sub("?", working_directory)
    lines = [
        "실행 환경",
        f"- Orca 실행 환경: {_safe_context(active_env)}",
        f"- 작업 디렉터리: {working_directory}",
        "- 범위: 현재 프로세스에서 보이는 설정만 확인",
        "",
        "LLM 제공자",
    ]

    probe_cache: dict[str, EndpointProbe] = {}

    def check(url: str | None) -> str:
        if not url:
            return "endpoint 미설정 또는 확인 불가"
        try:
            parts = urlsplit(url)
            key = f"{parts.scheme}://{parts.hostname or ''}:{parts.port or ''}"
        except ValueError:
            return _probe_status(probe(url))
        if key not in probe_cache:
            probe_cache[key] = probe(url)
        return _probe_status(probe_cache[key])

    providers: set[str] = set()
    checked_vars: set[str] = set()
    endpoint_env_vars = (
        "TRADINGAGENTS_LLM_BACKEND_URL",
        "TRADINGAGENTS_QUICK_THINK_BACKEND_URL",
        "TRADINGAGENTS_DEEP_THINK_BACKEND_URL",
    )
    for tier in ("quick", "deep"):
        provider = _provider(active_config, tier)
        providers.add(provider)
        base_url = _tier_base_url(active_config, provider, tier)
        endpoint = _endpoint_url(provider, base_url, active_env)
        auth_method, auth_vars, auth_state = _auth_status(
            provider, active_config, active_env, chatgpt_connected, chatgpt_plan_connected
        )
        lines.append(
            f"- {tier}: 제공자={provider}, 인증={auth_method} ({auth_state}), "
            f"API 도달성={check(endpoint)}"
        )
        for name in auth_vars:
            if name in checked_vars:
                continue
            checked_vars.add(name)
            state = "설정됨" if _configured(active_env, name) else "누락"
            lines.append(f"  - {name}: {state}")
        for name in endpoint_env_vars:
            if name not in checked_vars:
                checked_vars.add(name)
                state = "설정됨" if _configured(active_env, name) else "미설정"
                lines.append(f"  - {name}: {state}")
        if provider == "azure":
            for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"):
                if name not in checked_vars:
                    checked_vars.add(name)
                    state = "설정됨" if _configured(active_env, name) else "미설정"
                    lines.append(f"  - {name}: {state}")
        elif provider == "bedrock":
            for name in ("AWS_REGION", "AWS_DEFAULT_REGION"):
                if name not in checked_vars:
                    checked_vars.add(name)
                    state = "설정됨" if _configured(active_env, name) else "미설정"
                    lines.append(f"  - {name}: {state}")
        elif provider == "ollama":
            name = "OLLAMA_BASE_URL"
            if name not in checked_vars:
                checked_vars.add(name)
                state = "설정됨" if _configured(active_env, name) else "기본 주소 사용"
                lines.append(f"  - {name}: {state}")
    lines.extend(["", "인증 환경변수 설정 여부"])
    for name in (
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_QUICK_THINK_PROVIDER",
        "TRADINGAGENTS_DEEP_THINK_PROVIDER",
        "TRADINGAGENTS_OPENAI_AUTH",
        "ALPHA_VANTAGE_API_KEY",
        "FRED_API_KEY",
        "TYPESAFE_API_KEY",
        "TYPESAFE_BASE_URL",
        "SEC_EDGAR_USER_AGENT",
        *_TOSS_ENV,
    ):
        if name in checked_vars:
            continue
        checked_vars.add(name)
        state = "설정됨" if _configured(active_env, name) else "미설정"
        lines.append(f"- {name}: {state}")

    lines.extend(["", "데이터 API 도달성"])
    data_endpoints = list(_DATA_ENDPOINTS)
    for name, url in (
        ("ALPHA_VANTAGE_API_KEY", "https://www.alphavantage.co"),
        ("FRED_API_KEY", "https://api.stlouisfed.org"),
    ):
        if _configured(active_env, name):
            data_endpoints.append((name.removesuffix("_API_KEY"), url))
    if _configured(active_env, "TYPESAFE_API_KEY"):
        data_endpoints.append(("TypeSafe", active_env.get("TYPESAFE_BASE_URL") or _TYPESAFE_ENDPOINT))
    for label, url in data_endpoints:
        lines.append(f"- {label}: {check(url)}")

    if providers == {"unknown"}:
        lines.append("\n진단: 선택된 LLM 제공자를 확인할 수 없습니다.")
    return "\n".join(lines)
