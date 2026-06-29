"""OpenAI-compatible Chat Completions provider implementation."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.settings import Settings
from app.core.errors import IntegrationNotConfiguredError
from app.core.logging import get_logger
from app.llm.provider import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall

logger = get_logger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    """LLM provider for OpenAI-compatible `/chat/completions` APIs."""

    def __init__(self, settings: Settings) -> None:
        """Create a provider from runtime settings."""
        if not settings.openai_api_key:
            raise IntegrationNotConfiguredError("OPENAI_API_KEY must be configured before using the LLM provider")
        self.base_url = settings.openai_base_url.rstrip("/")
        self.model = settings.openai_model
        self.api_key = settings.openai_api_key
        self.default_temperature = settings.llm_temperature
        self.default_max_tokens = settings.llm_max_tokens
        self.timeout = settings.llm_timeout_seconds

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call an OpenAI-compatible model and return the final message."""
        payload = self._payload(messages, tools, json_mode, False, temperature, max_tokens, system_prompt)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self._url, headers=self._headers, json=payload)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]["message"]
        tool_calls = [self._parse_tool_call(item) for item in choice.get("tool_calls", [])]
        usage = {key: int(value) for key, value in data.get("usage", {}).items() if isinstance(value, int)}
        logger.info("llm_complete", extra={"model": self.model, "tool_calls": len(tool_calls), "usage": usage})
        return LLMResponse(content=choice.get("content") or "", tool_calls=tool_calls, usage=usage)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream token deltas from an OpenAI-compatible model."""
        payload = self._payload(messages, tools, json_mode, True, temperature, max_tokens, system_prompt)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", self._url, headers=self._headers, json=payload, timeout=self.timeout
            ) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line.removeprefix("data: ").strip()
                    if raw == "[DONE]":
                        break
                    data = json.loads(raw)
                    delta = data["choices"][0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token

    @property
    def _url(self) -> str:
        """Return the provider chat completions URL."""
        return f"{self.base_url}/chat/completions"

    @property
    def _headers(self) -> dict[str, str]:
        """Return request headers for provider calls."""
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        """Build a Chat Completions request payload."""
        request_messages = list(messages)
        if system_prompt:
            request_messages = [LLMMessage(role="system", content=system_prompt), *request_messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message(message) for message in request_messages],
            "temperature": self.default_temperature if temperature is None else temperature,
            "max_tokens": self.default_max_tokens if max_tokens is None else max_tokens,
            "stream": stream,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def _message(self, message: LLMMessage) -> dict[str, Any]:
        """Convert a provider-neutral message to wire format."""
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            payload["name"] = message.name
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    def _parse_tool_call(self, item: dict[str, Any]) -> ToolCall:
        """Parse a model tool call into a typed value object."""
        function = item.get("function", {})
        raw_arguments = function.get("arguments") or "{}"
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        return ToolCall(id=item["id"], name=function["name"], arguments=arguments)
