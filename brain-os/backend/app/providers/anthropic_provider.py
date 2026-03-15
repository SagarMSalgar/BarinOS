"""Anthropic-backed LLM provider (no embeddings)."""
from __future__ import annotations

import os
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .base import LLMProvider


class AnthropicLLM(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key_env: str = "ANTHROPIC_API_KEY", **kwargs: Any):
        self.model = model
        self.api_key = os.environ.get(api_key_env)
        self._options = kwargs

    def _to_anthropic_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        out = []
        for m in messages:
            role = m.get("role", "user")
            if role == "system":
                if out and out[-1].get("role") == "user":
                    out[-1]["content"] = out[-1]["content"] + "\n\n" + m.get("content", "")
                else:
                    out.append({"role": "user", "content": m.get("content", "")})
            else:
                out.append({"role": role, "content": m.get("content", "")})
        return out or [{"role": "user", "content": ""}]

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str | AsyncIterator[str]:
        client = AsyncAnthropic(api_key=self.api_key)
        msgs = self._to_anthropic_messages(messages)
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), None)
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=msgs,
            **self._options,
        )
        if system:
            kwargs["system"] = system
        if stream:
            return self._stream(client, kwargs)
        r = await client.messages.create(**kwargs)
        return (r.content[0].text if r.content else "")

    async def _stream(self, client: AsyncAnthropic, kwargs: dict) -> AsyncIterator[str]:
        with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = AsyncAnthropic(api_key=self.api_key)
        msgs = self._to_anthropic_messages(messages)
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), None)
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=msgs,
            system=system or "",
            **self._options,
        )
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text


def register_anthropic(registry: dict) -> None:
    registry["anthropic"] = lambda cfg: AnthropicLLM(
        model=cfg.get("model", "claude-sonnet-4-20250514"),
        api_key_env=cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
        **cfg.get("options", {}),
    )
