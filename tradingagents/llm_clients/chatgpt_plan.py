"""LangChain chat model for ChatGPT plan usage via Sign in with ChatGPT."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

from .base_client import normalize_content

_NAMESPACE = "tradingagents"


def _get(value: Any, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in ("text", "output_text")
        )
    return str(content or "")


def _serialize_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    """Map LangChain messages to a complete, stateless Responses input array."""
    result: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": _content_text(message.content),
                }
            )
            continue

        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                result.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id") or call.get("call_id"),
                        "name": f"{_NAMESPACE}.{call['name']}",
                        "arguments": json.dumps(call.get("args", {}), ensure_ascii=False),
                    }
                )
            if message.content:
                result.append(
                    {"role": "assistant", "content": _content_text(message.content)}
                )
            continue

        role = "developer" if isinstance(message, SystemMessage) else (
            "assistant" if isinstance(message, AIMessage) else "user"
        )
        result.append({"role": role, "content": _content_text(message.content)})
    return result


def _responses_tools(tools: Sequence[Any]) -> tuple[list[dict[str, Any]], set[str]]:
    functions = []
    names = set()
    for tool in tools:
        converted = convert_to_openai_tool(tool)
        function = converted.get("function", converted)
        if function.get("type") not in (None, "function") or not function.get("name"):
            raise ValueError("ChatGPT plan usage supports only local function tools.")
        functions.append(
            {
                "type": "function",
                **{key: value for key, value in function.items() if key != "type"},
            }
        )
        names.add(str(function["name"]))
    if not functions:
        return [], names
    return [
        {
            "type": "namespace",
            "name": _NAMESPACE,
            "description": "Local stock research and analysis functions.",
            "tools": functions,
        }
    ], names


def _tool_choice(value: Any) -> Any:
    if value is None:
        return None
    if value in ("any", "required"):
        return "required"
    if value in ("auto", "none"):
        return value
    if isinstance(value, dict):
        function = value.get("function", value)
        name = function.get("name") if isinstance(function, dict) else None
        return {"type": "function", "name": f"{_NAMESPACE}.{name}"} if name else "required"
    if isinstance(value, str):
        return {"type": "function", "name": f"{_NAMESPACE}.{value}"}
    return "required"


def _response_events(response):
    """Decode Responses API server-sent events without logging their contents."""
    for line in response.iter_lines(decode_unicode=True):
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            event = json.loads(payload)
        except ValueError:
            raise RuntimeError("ChatGPT plan stream contained an invalid event.") from None
        if isinstance(event, dict):
            yield event


def _parse_response(response: Any, allowed_tools: set[str]) -> AIMessage:
    text_parts: list[str] = []
    tool_calls = []
    for item in _get(response, "output", []) or []:
        item_type = _get(item, "type")
        if item_type == "message":
            for part in _get(item, "content", []) or []:
                if _get(part, "type") in ("output_text", "text"):
                    text_parts.append(str(_get(part, "text", "")))
        elif item_type == "function_call":
            raw_name = str(_get(item, "name", ""))
            name = raw_name.removeprefix(f"{_NAMESPACE}.")
            if allowed_tools and name not in allowed_tools:
                raise RuntimeError("ChatGPT plan response named an unknown local tool.")
            try:
                arguments = json.loads(_get(item, "arguments", "{}"))
            except (TypeError, ValueError):
                raise RuntimeError("ChatGPT plan response contained invalid tool arguments.") from None
            if not isinstance(arguments, dict):
                raise RuntimeError("ChatGPT plan response contained invalid tool arguments.")
            tool_calls.append(
                {
                    "name": name,
                    "args": arguments,
                    "id": _get(item, "call_id") or _get(item, "id"),
                    "type": "tool_call",
                }
            )

    usage = _get(response, "usage")
    usage_metadata = None
    if usage is not None:
        input_tokens = int(_get(usage, "input_tokens", 0) or 0)
        output_tokens = int(_get(usage, "output_tokens", 0) or 0)
        usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return AIMessage(
        content="\n".join(text_parts),
        tool_calls=tool_calls,
        usage_metadata=usage_metadata,
        response_metadata={"model_name": _get(response, "model")},
    )


class ChatGPTPlanChatModel(BaseChatModel):
    """Responses API client with OAuth credentials from the local auth store.

    Requests always stream with ``store=False`` and do not retry. Unsupported
    sampling and output-token options are deliberately not sent.
    """

    model_name: str
    timeout: float | None = None
    _token_provider: Callable[[], str] = PrivateAttr()

    def __init__(
        self,
        *,
        model: str,
        token_provider: Callable[[], str],
        timeout: float | None = None,
        callbacks=None,
        tags=None,
        metadata=None,
    ):
        super().__init__(
            model_name=model,
            timeout=timeout,
            callbacks=callbacks,
            tags=tags,
            metadata=metadata,
            disable_streaming=True,
        )
        self._token_provider = token_provider

    @property
    def _llm_type(self) -> str:
        return "chatgpt-plan-responses"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name}

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,
    ):
        unsupported_kwargs = set(kwargs) - {"ls_structured_output_format"}
        if unsupported_kwargs:
            unsupported = ", ".join(sorted(unsupported_kwargs))
            raise ValueError(f"Unsupported ChatGPT plan tool options: {unsupported}")
        return self.bind(tools=list(tools), tool_choice=tool_choice, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if stop:
            raise ValueError("Stop sequences are not supported by ChatGPT plan usage.")
        tools, allowed_tools = _responses_tools(kwargs.pop("tools", []))
        choice = _tool_choice(kwargs.pop("tool_choice", None))
        # LangChain's structured-output wrapper adds this tracing hint. It is
        # local metadata, not a supported Responses API request field.
        kwargs.pop("ls_structured_output_format", None)
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise ValueError(f"Unsupported ChatGPT plan request options: {unsupported}")

        request: dict[str, Any] = {
            "model": self.model_name,
            "input": _serialize_messages(messages),
            "store": False,
            "stream": True,
        }
        if tools:
            request["tools"] = tools
        if choice is not None and tools:
            request["tool_choice"] = choice

        try:
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._token_provider()}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=request,
                stream=True,
                timeout=(10, self.timeout or 300),
            )
        except RuntimeError:
            raise
        except requests.RequestException:
            raise RuntimeError(
                "ChatGPT plan request failed. It was not retried and no API-key fallback was used."
            ) from None
        completed_response = None
        try:
            if not response.ok:
                code = None
                try:
                    body = response.json()
                    code = _get(_get(body, "error"), "code")
                except (ValueError, AttributeError):
                    pass
                if code == "subscription_sharing_usage_limit_exceeded":
                    raise RuntimeError(
                        "ChatGPT plan usage limit reached. Check ChatGPT Settings → Usage."
                    )
                if code == "subscription_sharing_user_not_eligible":
                    raise RuntimeError(
                        "This ChatGPT account or workspace is not eligible for plan usage."
                    )
                if code == "subscription_sharing_usage_unavailable":
                    raise RuntimeError(
                        "ChatGPT plan usage is temporarily unavailable. Check Settings → Usage."
                    )
                raise RuntimeError(
                    f"ChatGPT plan request failed (HTTP {response.status_code}). "
                    "It was not retried and no API-key fallback was used."
                )
            for event in _response_events(response):
                event_type = _get(event, "type")
                if event_type in ("response.failed", "error"):
                    error = _get(_get(event, "response"), "error") or _get(event, "error")
                    code = str(_get(error, "code", "request_failed"))
                    if code == "subscription_sharing_usage_limit_exceeded":
                        raise RuntimeError(
                            "ChatGPT plan usage limit reached. Check ChatGPT Settings → Usage."
                        )
                    if code == "subscription_sharing_user_not_eligible":
                        raise RuntimeError(
                            "This ChatGPT account or workspace is not eligible for plan usage."
                        )
                    if code == "subscription_sharing_usage_unavailable":
                        raise RuntimeError(
                            "ChatGPT plan usage is temporarily unavailable. Check Settings → Usage."
                        )
                    raise RuntimeError(f"ChatGPT plan request failed: {code}.")
                if event_type == "response.incomplete":
                    raise RuntimeError("ChatGPT plan response was incomplete.")
                if event_type == "response.completed":
                    completed_response = _get(event, "response")
        except RuntimeError:
            raise
        except requests.RequestException:
            raise RuntimeError(
                "ChatGPT plan stream failed. It was not retried and no API-key fallback was used."
            ) from None
        finally:
            response.close()
        if completed_response is None:
            raise RuntimeError(
                "ChatGPT plan stream ended without response.completed. "
                "It was not retried and no API-key fallback was used."
            )
        message = _parse_response(completed_response, allowed_tools)
        generation_info = {"finish_reason": "tool_calls" if message.tool_calls else "stop"}
        return ChatResult(generations=[ChatGeneration(message=message, generation_info=generation_info)])
