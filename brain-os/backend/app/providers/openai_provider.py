"""OpenAI-backed LLM and embedding provider."""
from __future__ import annotations

import os
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from .base import EmbeddingProvider, LLMProvider


def _client(api_key: str | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))


class OpenAILLM(LLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key_env: str = "OPENAI_API_KEY", **kwargs: Any):
        self.model = model
        self.api_key = os.environ.get(api_key_env)
        self._options = kwargs

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str | AsyncIterator[str]:
        client = _client(self.api_key)
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **self._options,
        )
        if stream:
            return self._stream(client, kwargs)
        r = await client.chat.completions.create(**kwargs, stream=False)
        return (r.choices[0].message.content or "")

    async def _stream(self, client: AsyncOpenAI, kwargs: dict) -> AsyncIterator[str]:
        stream = await client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and getattr(delta, "content", None):
                yield delta.content

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = _client(self.api_key)
        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **self._options,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and getattr(delta, "content", None):
                yield delta.content


class OpenAIEmbedding(EmbeddingProvider):
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        api_key_env: str = "OPENAI_API_KEY",
    ):
        self.model = model
        self.dimensions = dimensions
        self.api_key = os.environ.get(api_key_env)

    async def embed(self, texts: list[str], dimensions: int | None = None) -> list[list[float]]:
        dim = dimensions or self.dimensions
        client = _client(self.api_key)
        r = await client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=dim,
        )
        return [e.embedding for e in r.data]
