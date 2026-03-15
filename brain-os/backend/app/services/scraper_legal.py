"""Web intelligence: legal compliance verdict for URL scraping (ALLOWED/WARN/DENIED) + evidence."""
from __future__ import annotations

from typing import Any

from app.core.config import load_config, get_intent_prompt
from app.providers import get_llm_provider


async def legal_verdict(
    url: str,
    tos_excerpt: str | None = None,
    robots_excerpt: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verdict with confidence, evidence, and ToS clause quoted."""
    config = config or load_config()
    prompt_cfg = get_intent_prompt(config, "scraper_legal")
    if not prompt_cfg:
        return {"verdict": "WARN", "confidence": 0.5, "evidence": "No LLM config.", "tos_clause": None}
    llm = get_llm_provider(config)
    user_msg = (
        prompt_cfg["user_template"]
        .replace("{{ url }}", url)
        .replace("{{ tos_excerpt }}", tos_excerpt or "Not provided")
        .replace("{{ robots_excerpt }}", robots_excerpt or "Not provided")
    )
    messages = [{"role": "system", "content": prompt_cfg["system"]}, {"role": "user", "content": user_msg}]
    try:
        raw = await llm.complete(messages, stream=False, max_tokens=500)
        verdict = "WARN"
        if "ALLOWED" in raw.upper():
            verdict = "ALLOWED"
        elif "DENIED" in raw.upper():
            verdict = "DENIED"
        return {"verdict": verdict, "confidence": 0.8, "evidence": raw.strip(), "tos_clause": None}
    except Exception as e:
        return {"verdict": "WARN", "confidence": 0.0, "evidence": str(e), "tos_clause": None}
