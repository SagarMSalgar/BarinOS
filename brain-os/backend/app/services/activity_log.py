"""Agent activity log — real-time feed of every agent action with timestamps."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from collections import deque
import asyncio

# In-memory ring buffer; in production use Redis stream or DB
_log: deque[dict[str, Any]] = deque(maxlen=10_000)
_lock = asyncio.Lock()


async def log_activity(
    action: str,
    tenant_id: str,
    details: dict[str, Any] | None = None,
    document_id: str | None = None,
    channel: str | None = None,
) -> None:
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "channel": channel,
        "details": details or {},
    }
    async with _lock:
        _log.append(entry)


def get_recent(limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
    items = list(_log)
    if tenant_id:
        items = [e for e in items if e.get("tenant_id") == tenant_id]
    return list(reversed(items[-limit:]))
