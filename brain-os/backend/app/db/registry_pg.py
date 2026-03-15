"""PostgreSQL-backed document registry (same interface as in-memory)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models.registry import DocumentRecord

from .connection import get_pool

# PostgreSQL text/JSONB cannot store null byte (\u0000) and some control chars; strip them
_RE_UNSAFE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize_for_jsonb(obj: Any) -> Any:
    """Recursively remove null bytes and other chars PostgreSQL rejects in JSONB text."""
    if isinstance(obj, str):
        s = obj.replace("\x00", "")
        return _RE_UNSAFE.sub("", s)
    if isinstance(obj, dict):
        return {k: _sanitize_for_jsonb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_jsonb(x) for x in obj]
    return obj


class DocumentRegistryPostgres:
    """Document registry stored in PostgreSQL."""

    async def create(self, tenant_id: str, name: str, source_type: str, external_id: str | None = None) -> DocumentRecord:
        pool = await get_pool()
        if not pool:
            raise RuntimeError("DATABASE_URL not set")
        doc_id = str(uuid4())
        rec = DocumentRecord(
            id=doc_id,
            tenant_id=tenant_id,
            name=name,
            source_type=source_type,
            external_id=external_id,
            status="pending",
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO documents (id, tenant_id, name, source_type, external_id, status)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                doc_id, tenant_id, name, source_type, external_id or None, "pending",
            )
        return rec

    async def get(self, document_id: str) -> DocumentRecord | None:
        pool = await get_pool()
        if not pool:
            return None
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM documents WHERE id = $1", document_id)
        if not row:
            return None
        return _row_to_record(row)

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
        pool = await get_pool()
        if not pool:
            return None
        async with pool.acquire() as conn:
            updates = ["updated_at = NOW()"]
            args = []
            n = 1
            if status is not None:
                updates.append(f"status = ${n}")
                args.append(status)
                n += 1
            if last_verified_at is not None:
                updates.append(f"last_verified_at = ${n}")
                args.append(last_verified_at)
                n += 1
            if freshness_score is not None:
                updates.append(f"freshness_score = ${n}")
                args.append(freshness_score)
                n += 1
            if version is not None:
                updates.append(f"version = ${n}")
                args.append(version)
                n += 1
            if metadata is not None:
                updates.append(f"metadata = COALESCE(metadata, '{{}}'::jsonb) || ${n}::jsonb")
                args.append(json.dumps(_sanitize_for_jsonb(metadata)))
                n += 1
            if len(args) == 0:
                return await self.get(document_id)
            args.append(document_id)
            await conn.execute(
                f"UPDATE documents SET {', '.join(updates)} WHERE id = ${n}",
                *args,
            )
        return await self.get(document_id)

    async def list_by_tenant(self, tenant_id: str) -> list[DocumentRecord]:
        pool = await get_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM documents WHERE tenant_id = $1 ORDER BY updated_at DESC", tenant_id)
        return [_row_to_record(r) for r in rows]

    async def list_with_external_id(self) -> list[DocumentRecord]:
        """List documents that have external_id (e.g. URL) for freshness watchdog."""
        pool = await get_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM documents WHERE external_id IS NOT NULL AND external_id != ''")
        return [_row_to_record(r) for r in rows]


def _row_to_record(row) -> DocumentRecord:
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return DocumentRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        source_type=row["source_type"],
        external_id=row.get("external_id"),
        version=row.get("version", 1),
        status=row.get("status", "pending"),
        last_verified_at=row.get("last_verified_at"),
        freshness_score=row.get("freshness_score"),
        metadata=meta,
        created_at=row.get("created_at") or datetime.utcnow(),
        updated_at=row.get("updated_at") or datetime.utcnow(),
    )
