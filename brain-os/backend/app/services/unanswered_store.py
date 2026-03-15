"""Store for unanswered questions (for scheduled gap reports). Uses PG if available else memory."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

# In-memory fallback
_memory: dict[str, list[dict[str, Any]]] = {}  # key: tenant_id:namespace


async def record_unanswered(tenant_id: str, namespace: str, question: str) -> None:
    """Record an unanswered question (call when confidence low or no answer)."""
    pool = await _get_pool()
    key = f"{tenant_id}:{namespace}"
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO unanswered_questions (tenant_id, namespace, question, count, updated_at)
                   VALUES ($1, $2, $3, 1, NOW())
                   ON CONFLICT (tenant_id, namespace, question)
                   DO UPDATE SET count = unanswered_questions.count + 1, updated_at = NOW()""",
                tenant_id, namespace, question,
            )
        return
    if key not in _memory:
        _memory[key] = []
    for e in _memory[key]:
        if e.get("question") == question:
            e["count"] = e.get("count", 1) + 1
            e["updated_at"] = datetime.utcnow().isoformat()
            return
    _memory[key].append({"question": question, "count": 1, "updated_at": datetime.utcnow().isoformat()})


async def get_unanswered_for_report(tenant_id: str | None = None, namespace: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch unanswered questions grouped for gap report. If tenant_id/namespace None, all."""
    pool = await _get_pool()
    if pool:
        async with pool.acquire() as conn:
            if tenant_id and namespace:
                rows = await conn.fetch(
                    """SELECT question, count FROM unanswered_questions
                       WHERE tenant_id = $1 AND namespace = $2 ORDER BY count DESC LIMIT $3""",
                    tenant_id, namespace, limit,
                )
            elif tenant_id:
                rows = await conn.fetch(
                    """SELECT question, count FROM unanswered_questions
                       WHERE tenant_id = $1 ORDER BY count DESC LIMIT $2""",
                    tenant_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT question, count FROM unanswered_questions ORDER BY count DESC LIMIT $1""",
                    limit,
                )
        return [{"question": r["question"], "count": r["count"]} for r in rows]
    # Memory
    out = []
    for k, entries in _memory.items():
        t, ns = k.split(":", 1)
        if tenant_id and t != tenant_id:
            continue
        if namespace and ns != namespace:
            continue
        for e in entries:
            out.append({"question": e["question"], "count": e.get("count", 1)})
    out.sort(key=lambda x: -x["count"])
    return out[:limit]


async def clear_unanswered(tenant_id: str, namespace: str | None = None) -> int:
    """Clear stored unanswered questions. Returns count cleared."""
    pool = await _get_pool()
    if pool:
        async with pool.acquire() as conn:
            if namespace:
                r = await conn.execute(
                    "DELETE FROM unanswered_questions WHERE tenant_id = $1 AND namespace = $2",
                    tenant_id, namespace,
                )
            else:
                r = await conn.execute("DELETE FROM unanswered_questions WHERE tenant_id = $1", tenant_id)
        return int(r.split()[-1]) if r else 0
    key = f"{tenant_id}:{namespace}" if namespace else None
    removed = 0
    for k in list(_memory.keys()):
        if key and k != key:
            continue
        if not key and not k.startswith(tenant_id + ":"):
            continue
        removed += len(_memory[k])
        del _memory[k]
    return removed


async def remove_unanswered(tenant_id: str, namespace: str, question: str) -> bool:
    """Remove a single question from unanswered (e.g. after new source answers it). Returns True if removed."""
    pool = await _get_pool()
    if pool:
        async with pool.acquire() as conn:
            r = await conn.execute(
                "DELETE FROM unanswered_questions WHERE tenant_id = $1 AND namespace = $2 AND question = $3",
                tenant_id, namespace, question,
            )
            return int(r.split()[-1]) if r else 0 > 0
    key = f"{tenant_id}:{namespace}"
    if key not in _memory:
        return False
    before = len(_memory[key])
    _memory[key] = [e for e in _memory[key] if e.get("question") != question]
    return len(_memory[key]) < before


async def _get_pool():
    if not os.environ.get("DATABASE_URL"):
        return None
    from app.db.connection import get_pool
    return await get_pool()
