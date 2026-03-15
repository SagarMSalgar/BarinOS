"""Persistent cognitive memory: episodic, user, outcome. Memory write loop after interactions."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider


def _relative_time(created_at_iso: str | None) -> str:
    """Format timestamp as relative time for dashboard (e.g. '2 hours ago', 'Yesterday', '10m ago')."""
    if not created_at_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        if delta < timedelta(minutes=1):
            return "Just now"
        if delta < timedelta(hours=1):
            m = int(delta.total_seconds() / 60)
            return f"{m}m ago"
        if delta < timedelta(hours=24):
            h = int(delta.total_seconds() / 3600)
            return f"{h}h ago" if h == 1 else f"{h}h ago"
        if delta < timedelta(days=2):
            return "Yesterday"
        if delta < timedelta(days=7):
            d = delta.days
            return f"{d} days ago"
        return dt.strftime("%b %d")
    except Exception:
        return created_at_iso or "—"


def _event_id(mem_id: str) -> str:
    """Produce display id like EVENT_4920 from memory id."""
    n = hash(mem_id) % 10000
    if n < 0:
        n += 10000
    return f"EVENT_{n}"


def _load_memory_prompts(config: dict[str, Any]) -> dict[str, Any]:
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "memory.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def write_episodic_after_interaction(
    pool,
    tenant_id: str,
    namespace: str,
    question: str,
    answer: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Memory write loop: summarize interaction, extract durable facts, score importance, store in episodic_memory.
    """
    if not pool:
        return None
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_memory_prompts(config)

    summary = ""
    facts: list[str] = []
    importance = 0.5

    # Summarize
    spec = prompts.get("summarize_interaction") or {}
    sys = spec.get("system", "Summarize in one sentence.")
    user_tpl = spec.get("user_template", "Q: {{ question }}\nA: {{ answer }}\nSummary:")
    user_msg = user_tpl.replace("{{ question }}", question[:1000]).replace("{{ answer }}", (answer or "")[:2000])
    try:
        summary = (await llm.complete([{"role": "system", "content": sys}, {"role": "user", "content": user_msg}], stream=False, max_tokens=150)) or ""
        summary = summary.strip()[:500]
    except Exception:
        summary = f"Q: {question[:200]}"

    # Extract facts
    spec = prompts.get("extract_facts") or {}
    sys = spec.get("system", "Output JSON array of durable facts.")
    user_tpl = spec.get("user_template", "Q: {{ question }}\nA: {{ answer }}\nJSON:")
    user_msg = user_tpl.replace("{{ question }}", question[:800]).replace("{{ answer }}", (answer or "")[:1500])
    try:
        raw = await llm.complete([{"role": "system", "content": sys}, {"role": "user", "content": user_msg}], stream=False, max_tokens=300)
        m = re.search(r"\[[\s\S]*?\]", raw or "")
        if m:
            facts = json.loads(m.group(0))
            if isinstance(facts, list):
                facts = [str(x)[:500] for x in facts[:10]]
    except Exception:
        pass

    # Score importance
    spec = prompts.get("score_importance") or {}
    sys = spec.get("system", "Reply with one number 0.0 to 1.0.")
    user_tpl = spec.get("user_template", "Summary: {{ summary }}\nFacts: {{ facts }}\nScore:")
    user_msg = user_tpl.replace("{{ summary }}", summary[:500]).replace("{{ facts }}", json.dumps(facts)[:500])
    try:
        raw = await llm.complete([{"role": "system", "content": sys}, {"role": "user", "content": user_msg}], stream=False, max_tokens=20)
        for w in (raw or "").replace(",", " ").split():
            try:
                importance = max(0, min(1, float(w)))
                break
            except ValueError:
                continue
    except Exception:
        pass

    mem_id = str(uuid.uuid4())[:16]
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO episodic_memory (id, tenant_id, namespace, interaction_summary, question, answer_excerpt, facts_extracted, importance_score)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            mem_id,
            tenant_id,
            namespace,
            summary or "No summary",
            question[:2000],
            (answer or "")[:3000],
            json.dumps(facts),
            round(importance, 3),
        )
    return {"id": mem_id, "summary": summary, "facts": facts, "importance": importance}


async def get_recent_episodic(
    pool,
    tenant_id: str,
    namespace: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent episodic memory for context injection."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, interaction_summary, question, answer_excerpt, facts_extracted, importance_score, created_at
               FROM episodic_memory WHERE tenant_id = $1 AND namespace = $2 ORDER BY created_at DESC LIMIT $3""",
            tenant_id,
            namespace,
            limit,
        )
    return [
        {
            "id": r["id"],
            "summary": r["interaction_summary"],
            "question": r["question"],
            "answer_excerpt": (r["answer_excerpt"] or "")[:300],
            "facts": json.loads(r["facts_extracted"]) if isinstance(r["facts_extracted"], str) else (r["facts_extracted"] or []),
            "importance_score": float(r["importance_score"] or 0.5),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


async def get_user_memory(
    pool,
    tenant_id: str,
    namespace: str,
    user_key: str = "default",
) -> dict[str, Any]:
    """Get user/preference memory as key-value map."""
    if not pool:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, updated_at FROM user_memory WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3",
            tenant_id,
            namespace,
            user_key,
        )
    return {r["key"]: r["value"] for r in rows}


async def set_user_memory(
    pool,
    tenant_id: str,
    namespace: str,
    key: str,
    value: Any,
    user_key: str = "default",
) -> None:
    """Set one user memory key."""
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO user_memory (tenant_id, namespace, user_key, key, value, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (tenant_id, namespace, user_key, key) DO UPDATE SET value = $5, updated_at = $6""",
            tenant_id,
            namespace,
            user_key,
            key[:200],
            value if isinstance(value, (dict, list, str, int, float, bool)) else json.dumps(str(value)),
            datetime.now(timezone.utc),
        )


async def record_outcome(
    pool,
    tenant_id: str,
    namespace: str,
    run_type: str,
    success: bool,
    run_id: str | None = None,
    retrieval_success: bool | None = None,
    tool_success: bool | None = None,
    user_satisfaction: float | None = None,
    metadata: dict | None = None,
) -> None:
    """Store outcome for continuous learning (retrieval/tool/plan success, satisfaction)."""
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO outcome_memory (tenant_id, namespace, run_type, run_id, success, retrieval_success, tool_success, user_satisfaction, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            tenant_id,
            namespace,
            run_type[:50],
            run_id,
            success,
            retrieval_success,
            tool_success,
            user_satisfaction,
            json.dumps(metadata or {}),
        )


async def get_outcomes(
    pool,
    tenant_id: str,
    namespace: str,
    run_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List outcome memory for analytics / learning loop."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        if run_type:
            rows = await conn.fetch(
                """SELECT id, run_type, run_id, success, retrieval_success, tool_success, user_satisfaction, metadata, created_at
                   FROM outcome_memory WHERE tenant_id = $1 AND namespace = $2 AND run_type = $3 ORDER BY created_at DESC LIMIT $4""",
                tenant_id,
                namespace,
                run_type,
                limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, run_type, run_id, success, retrieval_success, tool_success, user_satisfaction, metadata, created_at
                   FROM outcome_memory WHERE tenant_id = $1 AND namespace = $2 ORDER BY created_at DESC LIMIT $3""",
                tenant_id,
                namespace,
                limit,
            )
    return [
        {
            "id": r["id"],
            "run_type": r["run_type"],
            "run_id": r["run_id"],
            "success": r["success"],
            "retrieval_success": r["retrieval_success"],
            "tool_success": r["tool_success"],
            "user_satisfaction": r["user_satisfaction"],
            "metadata": r["metadata"] if isinstance(r["metadata"], dict) else (json.loads(r["metadata"]) if isinstance(r["metadata"], str) else {}),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


# UI copy for dashboard (no hardcoded strings in frontend)
DASHBOARD_COPY = {
    "hero_title": "AI Cognitive Suite",
    "hero_subtitle": "A comprehensive view of your AI's evolving knowledge base, episodic records, and behavioral preferences.",
    "tab_episodic": "Episodic",
    "tab_user": "User",
    "tab_outcomes": "Outcomes",
    "section_recent_interactions": "Recent Interactions",
    "section_user_preferences": "User Preferences",
    "section_success_metrics": "Success Metrics & Retrieval",
    "search_placeholder": "Search memories...",
    "manual_memory_injection": "Manual Memory injection",
    "page_title": "Persistent Cognitive Memory",
    "engine_version": "Neural Engine v4.2.0",
}


async def get_dashboard(
    pool,
    tenant_id: str,
    namespace: str,
    user_key: str = "default",
    episodic_limit: int = 50,
    outcomes_limit: int = 80,
) -> dict[str, Any]:
    """Aggregate display-ready data for the cognitive memory dashboard. All labels and content from backend."""
    episodic_raw = await get_recent_episodic(pool, tenant_id, namespace, limit=episodic_limit)
    user_raw = await get_user_memory(pool, tenant_id, namespace, user_key=user_key)
    outcomes_raw = await get_outcomes(pool, tenant_id, namespace, run_type=None, limit=outcomes_limit)

    episodic = []
    for m in episodic_raw:
        score = float(m.get("importance_score") or 0.5)
        importance_label = "High Importance" if score >= 0.7 else "Neutral"
        facts = m.get("facts") or []
        if not isinstance(facts, list):
            facts = [str(facts)] if facts else []
        episodic.append({
            "id": m.get("id"),
            "event_id": _event_id(str(m.get("id", ""))),
            "title": (m.get("summary") or "")[:80] or "Interaction",
            "question": m.get("question") or "",
            "facts": [str(f)[:500] for f in facts[:10]],
            "importance_label": importance_label,
            "created_at_relative": _relative_time(m.get("created_at")),
        })

    user_preferences = []
    for k, v in user_raw.items():
        if isinstance(v, (dict, list)):
            desc = json.dumps(v, ensure_ascii=False)[:500]
        else:
            desc = str(v)[:500] if v is not None else ""
        label = k.replace("_", " ").title()
        user_preferences.append({"key": k, "label": label, "description": desc})

    outcomes = []
    for o in outcomes_raw:
        meta = o.get("metadata") or {}
        retrieval_method = meta.get("retrieval_method") if isinstance(meta.get("retrieval_method"), str) else ("Vector Search" if o.get("retrieval_success") else "Direct KV")
        tool_used = meta.get("tool_used") if isinstance(meta.get("tool_used"), str) else "redis_cached"
        sat = o.get("user_satisfaction")
        satisfaction_stars = max(1, min(5, round(sat * 5))) if sat is not None else None
        outcomes.append({
            "id": o.get("id"),
            "run_type": o.get("run_type") or "—",
            "success": bool(o.get("success")),
            "retrieval_method": retrieval_method,
            "tool_used": tool_used,
            "satisfaction_stars": satisfaction_stars,
            "when_relative": _relative_time(o.get("created_at")),
        })

    return {
        "copy": DASHBOARD_COPY,
        "episodic": episodic,
        "user_preferences": user_preferences,
        "outcomes": outcomes,
    }
