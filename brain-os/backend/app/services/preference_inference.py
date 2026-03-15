"""Infer personal profile preferences from answer feedback (thumbs up/down, what_wrong)."""
from __future__ import annotations

import json
from typing import Any


def infer_preference_deltas(helpful: bool, what_wrong: str | None) -> dict[str, Any]:
    """Map feedback to preference updates for personal_profiles.preferences.
    Returns a dict of key -> value to merge into preferences (only non-None values applied).
    """
    delta: dict[str, Any] = {}
    if helpful:
        # Positive feedback: optionally reinforce; we don't change preferences
        return delta
    # Not helpful: infer from what_wrong
    w = (what_wrong or "").strip().lower()
    # Explicit codes from UI
    if w == "missing_info":
        delta["answer_length_preference"] = "long"
        delta["detail_preference"] = "high"
    elif w == "wrong":
        delta["technical_depth"] = "lower"
        delta["format_preference"] = "concise"
    elif w == "outdated":
        # Content issue, not preference
        pass
    elif w == "other" or w:
        # Free-text or "other": check common phrases
        if "too long" in w or "too much" in w or "too much information" in w:
            delta["answer_length_preference"] = "short"
        elif "too short" in w or "show more" in w or "more detail" in w:
            delta["answer_length_preference"] = "long"
            delta["detail_preference"] = "high"
    return delta


async def apply_inferred_preferences(
    pool,
    tenant_id: str,
    namespace: str,
    user_key: str,
    delta: dict[str, Any],
) -> None:
    """Merge inferred preference deltas into personal_profiles for (tenant_id, namespace, user_key)."""
    if not pool or not delta:
        return
    user_key = (user_key or "default").strip()[:500]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT preferences FROM personal_profiles
               WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3""",
            tenant_id,
            namespace,
            user_key,
        )
        prefs: dict[str, Any] = {}
        if row and row.get("preferences") is not None:
            raw = row["preferences"]
            prefs = dict(raw) if isinstance(raw, dict) else {}
        for k, v in delta.items():
            if k and isinstance(k, str) and len(k) < 200:
                prefs[k] = v
        await conn.execute(
            """INSERT INTO personal_profiles (tenant_id, namespace, user_key, preferences, updated_at)
               VALUES ($1, $2, $3, $4::jsonb, NOW())
               ON CONFLICT (tenant_id, namespace, user_key) DO UPDATE SET preferences = $4::jsonb, updated_at = NOW()""",
            tenant_id,
            namespace,
            user_key,
            json.dumps(prefs),
        )
