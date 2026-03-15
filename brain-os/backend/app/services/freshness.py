"""Knowledge freshness: semantic diff, change notification, re-embed affected chunks."""
from __future__ import annotations

from typing import Any

from app.core.config import load_config, get_intent_prompt
from app.providers import get_llm_provider


async def semantic_diff(old_content: str, new_content: str, config: dict[str, Any] | None = None) -> str:
    """LLM-generated plain English summary of what changed."""
    config = config or load_config()
    prompt_cfg = get_intent_prompt(config, "freshness")
    if not prompt_cfg:
        return "Content changed (no summary available)."
    llm = get_llm_provider(config)
    user_msg = (
        prompt_cfg["user_template"]
        .replace("{{ old_content }}", old_content[:15000])
        .replace("{{ new_content }}", new_content[:15000])
    )
    messages = [{"role": "system", "content": prompt_cfg["system"]}, {"role": "user", "content": user_msg}]
    try:
        return (await llm.complete(messages, stream=False, max_tokens=1000)).strip()
    except Exception:
        return "Content changed."


async def build_change_notification(
    document_name: str,
    sections_updated: int,
    sections_removed: int,
    semantic_summary: str,
) -> dict[str, Any]:
    """Structured notification for dashboard/email."""
    return {
        "title": f"Knowledge updated: {document_name}",
        "message": semantic_summary,
        "sections_updated": sections_updated,
        "sections_removed": sections_removed,
        "action": "Auto-patched index — affected chunks re-embedded.",
    }
