"""Document registry — PostgreSQL or in-memory. Tracks every file, version, last verified, status."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models.registry import DocumentRecord

# In-memory implementation; replace with SQLAlchemy/asyncpg for production
_store: dict[str, DocumentRecord] = {}
_by_tenant: dict[str, list[str]] = {}


class DocumentRegistry:
    async def create(self, tenant_id: str, name: str, source_type: str, external_id: str | None = None) -> DocumentRecord:
        doc_id = str(uuid4())
        rec = DocumentRecord(
            id=doc_id,
            tenant_id=tenant_id,
            name=name,
            source_type=source_type,
            external_id=external_id,
            status="pending",
        )
        _store[doc_id] = rec
        _by_tenant.setdefault(tenant_id, []).append(doc_id)
        return rec

    async def get(self, document_id: str) -> DocumentRecord | None:
        return _store.get(document_id)

    async def update(
        self,
        document_id: str,
        *,
        status: str | None = None,
        last_verified_at: datetime | None = None,
        freshness_score: float | None = None,
        version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentRecord | None:
        rec = _store.get(document_id)
        if not rec:
            return None
        if status is not None:
            rec.status = status
        if last_verified_at is not None:
            rec.last_verified_at = last_verified_at
        if freshness_score is not None:
            rec.freshness_score = freshness_score
        if version is not None:
            rec.version = version
        if metadata is not None:
            rec.metadata = {**rec.metadata, **metadata}
        rec.updated_at = datetime.utcnow()
        return rec

    async def list_by_tenant(self, tenant_id: str) -> list[DocumentRecord]:
        ids = _by_tenant.get(tenant_id, [])
        return [_store[d] for d in ids if d in _store]

    async def list_with_external_id(self) -> list[DocumentRecord]:
        """For freshness watchdog: documents that have external_id (e.g. URL)."""
        return [r for r in _store.values() if r.external_id]
