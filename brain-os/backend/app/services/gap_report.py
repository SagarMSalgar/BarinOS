"""Knowledge gap reports: cluster unanswered questions, priority, AI fix suggestions."""
from __future__ import annotations

from typing import Any

from app.core.config import load_config, get_intent_prompt
from app.providers import get_llm_provider


async def generate_gap_report(
    questions_with_freq: list[dict[str, Any]],  # [{"question": "...", "count": N}, ...]
    config: dict[str, Any] | None = None,
    answered_count: int = 0,
) -> dict[str, Any]:
    """Clustered gap list, priority, AI fix suggestions, completeness score (answered / (answered + unanswered) * 100)."""
    config = config or load_config()
    unanswered_count = len(questions_with_freq)
    total = answered_count + unanswered_count
    completeness_score = round((answered_count / total) * 100, 1) if total > 0 else 100.0

    prompt_cfg = get_intent_prompt(config, "gap_analysis")
    if not prompt_cfg:
        return {
            "clustered_gaps": questions_with_freq,
            "priority_ranking": _priority_from_freq(questions_with_freq),
            "ai_fix_suggestions": [],
            "completeness_score": completeness_score,
        }

    lines = [f"- {q.get('question', '')} (asked {q.get('count', 1)} times)" for q in questions_with_freq[:100]]
    user_msg = prompt_cfg["user_template"].replace("{{ questions_with_freq }}", "\n".join(lines))
    messages = [{"role": "system", "content": prompt_cfg["system"]}, {"role": "user", "content": user_msg}]
    llm = get_llm_provider(config)
    try:
        raw = await llm.complete(messages, stream=False, max_tokens=2000)
    except Exception:
        raw = ""

    return {
        "clustered_gaps": questions_with_freq,
        "priority_ranking": _priority_from_freq(questions_with_freq),
        "ai_fix_suggestions": [raw] if raw else [],
        "completeness_score": completeness_score,
    }


def _priority_from_freq(questions: list[dict]) -> list[dict]:
    sorted_q = sorted(questions, key=lambda x: -x.get("count", 0))
    out = []
    for i, q in enumerate(sorted_q[:20]):
        out.append({
            "question": q.get("question", ""),
            "frequency": q.get("count", 0),
            "priority": "High" if i < 5 else "Medium" if i < 10 else "Low",
        })
    return out
