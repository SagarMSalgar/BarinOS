"""Freshness watchdog: re-fetch URL sources, semantic diff, re-embed and patch index."""
from __future__ import annotations

import hashlib
import os
from typing import Any

from app.core.config import load_config
from app.services.fetch_url import fetch_url_content
from app.services import semantic_diff, ingest_document, log_activity
from app.store import DocumentRegistry, VectorStore


async def check_document_freshness(
    document_id: str,
    document_name: str,
    tenant_id: str,
    namespace: str,
    external_id: str,
    last_content_hash: str | None,
    last_content: str | None,
    registry: DocumentRegistry,
    vector_store: VectorStore,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Fetch external_id (URL), compare hash; if changed run diff and re-ingest."""
    if not external_id.startswith(("http://", "https://")):
        return {"document_id": document_id, "changed": False, "reason": "not a URL"}
    try:
        new_content = await fetch_url_content(external_id, timeout=30.0)
    except Exception as e:
        return {"document_id": document_id, "changed": False, "error": str(e)}
    new_hash = hashlib.sha256(new_content.encode()).hexdigest()[:16]
    if last_content_hash and new_hash == last_content_hash:
        return {"document_id": document_id, "changed": False}
    summary = ""
    if last_content:
        summary = await semantic_diff(last_content[:50000], new_content[:50000], config)
    await log_activity("WATCHDOG", tenant_id, {"document": document_name, "summary": summary[:200]}, document_id=document_id)
    result = await ingest_document(
        tenant_id, namespace, document_id, document_name, new_content,
        config=config, registry=registry, vector_store=vector_store,
    )
    # Store content_hash and truncated excerpt; strip null bytes so PostgreSQL JSONB accepts it
    safe_excerpt = (new_content[:8000] or "").replace("\x00", "")
    meta = {"content_hash": new_hash, "last_content": safe_excerpt}
    await registry.update(document_id, last_verified_at=__import__("datetime").datetime.utcnow(), metadata=meta)
    # Log to change timeline for Freshness UI
    try:
        from app.db.connection import get_pool
        pool = await get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO document_changes_log (document_id, tenant_id, semantic_summary) VALUES ($1, $2, $3)",
                    document_id, tenant_id, (summary or "")[:2000],
                )
    except Exception:
        pass
    return {
        "document_id": document_id,
        "changed": True,
        "semantic_summary": summary,
        "re_ingested": result.get("chunks_created", 0),
    }


async def run_watchdog(
    registry: DocumentRegistry,
    vector_store: VectorStore,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run freshness check for all documents with external_id (URL)."""
    config = config or load_config()
    if not hasattr(registry, "list_with_external_id"):
        return []
    docs = await registry.list_with_external_id()
    results = []
    for doc in docs:
        if not doc.external_id:
            continue
        meta = doc.metadata or {}
        schedule = meta.get("watchdog_schedule", "off")
        if schedule == "off":
            continue
        namespace = meta.get("namespace", "main")
        res = await check_document_freshness(
            doc.id,
            doc.name,
            doc.tenant_id,
            namespace,
            doc.external_id,
            meta.get("content_hash"),
            meta.get("last_content"),
            registry,
            vector_store,
            config,
        )
        results.append(res)
    return results
