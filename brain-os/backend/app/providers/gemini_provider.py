"""Google Gemini–backed LLM provider. Uses env GOOGLE_API_KEY or GEMINI_API_KEY."""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator

from .base import LLMProvider

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Convert BrainOS messages to a single prompt string for Gemini."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            parts.append(f"System:\n{content}")
        elif role == "user":
            parts.append(f"User:\n{content}")
        elif role in ("assistant", "model"):
            parts.append(f"Assistant:\n{content}")
    return "\n\n".join(parts) if parts else ""


class GeminiLLM(LLMProvider):
    """Gemini API via google-generativeai. Supports complete() and stream()."""

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key_env: str = "GOOGLE_API_KEY",
        **kwargs: Any,
    ):
        if not _GENAI_AVAILABLE:
            raise RuntimeError("Install google-generativeai: pip install google-generativeai")
        self.model_name = model
        self.api_key = os.environ.get(api_key_env) or os.environ.get("GEMINI_API_KEY")
        self._api_key_env = api_key_env
        self._options = kwargs

    def _get_model(self):
        genai.configure(api_key=self.api_key)
        return genai.GenerativeModel(self.model_name)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str | AsyncIterator[str]:
        model = self._get_model()
        prompt = _messages_to_prompt(messages)
        try:
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except AttributeError:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        if stream:
            return self._stream_gemini(model, prompt, generation_config)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(prompt, generation_config=generation_config),
        )
        if not response or not response.text:
            return ""
        return response.text

    async def _stream_gemini(self, model, prompt: str, generation_config) -> AsyncIterator[str]:
        """Run sync stream in executor and yield chunks."""
        loop = asyncio.get_event_loop()
        def _generate():
            return model.generate_content(prompt, generation_config=generation_config, stream=True)
        stream = await loop.run_in_executor(None, _generate)
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        result = await self.complete(
            messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if isinstance(result, str):
            return
        async for token in result:
            yield token


def register_gemini(registry: dict) -> None:
    registry["gemini"] = lambda cfg: GeminiLLM(
        model=cfg.get("model", "gemini-1.5-flash"),
        api_key_env=cfg.get("api_key_env", "GOOGLE_API_KEY"),
        **cfg.get("options", {}),
    )
