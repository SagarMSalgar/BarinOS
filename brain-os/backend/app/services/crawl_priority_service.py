"""Crawl priority from query log and citation data: score docs/URLs by what users actually ask."""
from __future__ import annotations

from typing import Any


async def record_query_citations(
    pool,
    tenant_id: str,
    namespace: str,
    question: str,
    cited_document_ids: list[str],
) -> None:
    """Log a query and which docs were cited (for crawl priority)."""
    if not pool:
        return
    import json
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO query_citations (tenant_id, namespace, question, cited_document_ids) VALUES ($1, $2, $3, $4)""",
            tenant_id,
            namespace,
            question[:2000],
            json.dumps(list(cited_document_ids)),
        )


async def get_crawl_priority(
    pool,
    tenant_id: str,
    namespace: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Score documents by: how often they were cited in queries + how often they appeared in unanswered (what's missing).
    Higher score = more important to keep fresh / re-crawl.
    """
    if not pool:
        return []
    async with pool.acquire() as conn:
        # Citation frequency from query_citations
        rows = await conn.fetch(
            """SELECT cited_document_ids FROM query_citations WHERE tenant_id = $1 AND namespace = $2""",
            tenant_id,
            namespace,
        )
    from collections import Counter
    doc_counts = Counter()
    for r in rows:
        ids = r.get("cited_document_ids")
        if isinstance(ids, list):
            for doc_id in ids:
                doc_counts[doc_id] += 1
        elif isinstance(ids, str):
            try:
                import json
                arr = json.loads(ids)
                for doc_id in arr:
                    doc_counts[doc_id] += 1
            except Exception:
                pass

    # Unanswered questions might reference topics; we don't have doc ids there, so priority is citation-based.
    # Optional: join with documents that have external_id (URL) to return URL-level priority
    out = [{"document_id": doc_id, "citation_count": count, "priority_score": min(100, count * 10)} for doc_id, count in doc_counts.most_common(limit)]
    return out


async def get_crawl_priority_with_docs(
    pool,
    registry,
    tenant_id: str,
    namespace: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Crawl priority with document names and external_id (URL) when available."""
    priorities = await get_crawl_priority(pool, tenant_id, namespace, limit)
    if not registry:
        return priorities
    out = []
    for p in priorities:
        doc_id = p["document_id"]
        doc = await registry.get(doc_id) if hasattr(registry, "get") else None
        name = doc.name if doc and hasattr(doc, "name") else doc_id
        external_id = doc.external_id if doc and hasattr(doc, "external_id") else None
        out.append({
            **p,
            "document_name": name,
            "external_id": external_id,
        })
    return out
