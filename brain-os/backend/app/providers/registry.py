"""Resolve LLM and embedding providers from config. LLM-agnostic: add new providers here."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from .base import EmbeddingProvider, LLMProvider
from .openai_provider import OpenAIEmbedding, OpenAILLM

try:
    from .anthropic_provider import AnthropicLLM, register_anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from .gemini_provider import GeminiLLM, register_gemini
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

if TYPE_CHECKING:
    pass

_REGISTRY_LLM: dict[str, Any] = {
    "openai": lambda cfg: OpenAILLM(
        model=cfg.get("model", "gpt-4o"),
        api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
        **cfg.get("options", {}),
    ),
}
if _ANTHROPIC_AVAILABLE:
    register_anthropic(_REGISTRY_LLM)
if _GEMINI_AVAILABLE:
    register_gemini(_REGISTRY_LLM)

_REGISTRY_EMBED = {
    "openai": lambda cfg: OpenAIEmbedding(
        model=cfg.get("model", "text-embedding-3-small"),
        dimensions=cfg.get("dimensions", 1536),
        api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
    ),
}


def get_llm_provider(config: dict[str, Any]) -> LLMProvider:
    llm_cfg = config.get("llm", {})
    provider = (
        os.environ.get("BRAINOS_LLM_PROVIDER") or
        llm_cfg.get("provider", "openai")
    ).strip().lower()
    factory = _REGISTRY_LLM.get(provider)
    if not factory:
        raise ValueError(f"Unknown LLM provider: {provider}. Registered: {list(_REGISTRY_LLM)}")
    return factory(llm_cfg)


def get_embedding_provider(config: dict[str, Any]) -> EmbeddingProvider:
    emb_cfg = config.get("embedding", {})
    provider = emb_cfg.get("provider", "openai")
    factory = _REGISTRY_EMBED.get(provider)
    if not factory:
        raise ValueError(f"Unknown embedding provider: {provider}. Registered: {list(_REGISTRY_EMBED)}")
    return factory(emb_cfg)
