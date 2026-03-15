"""LLM-agnostic interfaces. All intelligence goes through these; no provider-specific code in core."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel


class LLMProvider(ABC):
    """Unified interface for any LLM (OpenAI, Anthropic, Azure, etc.)."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str | AsyncIterator[str]:
        """Non-streaming returns full text; streaming yields tokens."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream tokens one by one."""
        ...


class EmbeddingProvider(ABC):
    """Unified interface for embedding models."""

    @abstractmethod
    async def embed(self, texts: list[str], dimensions: int | None = None) -> list[list[float]]:
        """Return list of embedding vectors (same order as input texts)."""
        ...


class Citation(BaseModel):
    document_id: str
    document_name: str
    page: int | None = None
    section: str | None = None
    score: float = 0.0


class StreamedAnswer(BaseModel):
    """One piece of streamed output: either a token or a citation."""
    type: str  # "token" | "citation" | "confidence" | "freshness" | "follow_ups" | "done"
    payload: dict[str, Any] = {}
