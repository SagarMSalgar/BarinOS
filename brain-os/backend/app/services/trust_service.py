"""Trust score per source: updated from citations, feedback (helpful/correction). Used in ranking."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def record_citation(pool, tenant_id: str, namespace: str, document_id: str) -> None:
    """Increment citation count for document (called when an answer cites this doc)."""
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO source_trust (document_id, tenant_id, namespace, trust_score, citation_count, helpful_count, correction_count, updated_at)
               VALUES ($1, $2, $3, 0.5, 1, 0, 0, $4)
               ON CONFLICT (document_id, tenant_id, namespace) DO UPDATE SET
                 citation_count = source_trust.citation_count + 1,
                 updated_at = $4""",
            document_id,
            tenant_id,
            namespace,
            datetime.now(timezone.utc),
        )


async def record_feedback(
    pool,
    tenant_id: str,
    namespace: str,
    helpful: bool,
    citation_document_ids: list[str],
) -> None:
    """Update trust: helpful -> increment helpful_count for cited docs; not helpful -> increment correction_count."""
    if not pool or not citation_document_ids:
        return
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        for doc_id in citation_document_ids:
            if helpful:
                await conn.execute(
                    """INSERT INTO source_trust (document_id, tenant_id, namespace, trust_score, citation_count, helpful_count, correction_count, updated_at)
                       VALUES ($1, $2, $3, 0.5, 0, 1, 0, $4)
                       ON CONFLICT (document_id, tenant_id, namespace) DO UPDATE SET
                         helpful_count = source_trust.helpful_count + 1, updated_at = $4""",
                    doc_id,
                    tenant_id,
                    namespace,
                    now,
                )
            else:
                await conn.execute(
                    """INSERT INTO source_trust (document_id, tenant_id, namespace, trust_score, citation_count, helpful_count, correction_count, updated_at)
                       VALUES ($1, $2, $3, 0.5, 0, 0, 1, $4)
                       ON CONFLICT (document_id, tenant_id, namespace) DO UPDATE SET
                         correction_count = source_trust.correction_count + 1, updated_at = $4""",
                    doc_id,
                    tenant_id,
                    namespace,
                    now,
                )


def _compute_trust(citation_count: int, helpful_count: int, correction_count: int) -> float:
    """Trust score 0..1 from counts. More citations + helpful -> higher; more corrections -> lower."""
    total = citation_count + helpful_count + correction_count
    if total == 0:
        return 0.5
    # positive signals: citations (mild), helpful (strong); negative: correction
    positive = citation_count * 0.1 + helpful_count * 0.5
    negative = correction_count * 0.6
    raw = 0.5 + (positive - negative) / max(total, 1)
    return max(0.0, min(1.0, round(raw, 3)))


async def refresh_trust_scores(pool, tenant_id: str, namespace: str) -> None:
    """Recompute trust_score for all rows from citation_count, helpful_count, correction_count."""
    if not pool:
        return
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT document_id, citation_count, helpful_count, correction_count FROM source_trust WHERE tenant_id = $1 AND namespace = $2",
            tenant_id,
            namespace,
        )
        for r in rows:
            score = _compute_trust(
                r["citation_count"] or 0,
                r["helpful_count"] or 0,
                r["correction_count"] or 0,
            )
            await conn.execute(
                "UPDATE source_trust SET trust_score = $1, updated_at = $2 WHERE document_id = $3 AND tenant_id = $4 AND namespace = $5",
                score,
                datetime.now(timezone.utc),
                r["document_id"],
                tenant_id,
                namespace,
            )


async def get_trust_scores(
    pool,
    tenant_id: str,
    namespace: str,
) -> dict[str, float]:
    """Return map document_id -> trust_score for use in ranking."""
    if not pool:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT document_id, trust_score FROM source_trust WHERE tenant_id = $1 AND namespace = $2",
            tenant_id,
            namespace,
        )
    return {r["document_id"]: float(r["trust_score"] or 0.5) for r in rows}


async def list_source_trust(
    pool,
    tenant_id: str,
    namespace: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List source trust for UI."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT st.document_id, st.trust_score, st.citation_count, st.helpful_count, st.correction_count, st.updated_at, d.name AS document_name
               FROM source_trust st
               LEFT JOIN documents d ON d.id = st.document_id AND d.tenant_id = st.tenant_id
               WHERE st.tenant_id = $1 AND st.namespace = $2 ORDER BY st.updated_at DESC LIMIT $3""",
            tenant_id,
            namespace,
            limit,
        )
    return [
        {
            "document_id": r["document_id"],
            "document_name": r.get("document_name") or r["document_id"],
            "trust_score": float(r["trust_score"] or 0.5),
            "citation_count": r["citation_count"] or 0,
            "helpful_count": r["helpful_count"] or 0,
            "correction_count": r["correction_count"] or 0,
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        }
        for r in rows
    ]
