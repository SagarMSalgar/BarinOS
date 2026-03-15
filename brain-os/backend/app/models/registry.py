"""Document and chunk registry models (align with PostgreSQL)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    id: str
    tenant_id: str
    name: str
    source_type: str  # upload | url | gdrive | slack | ...
    external_id: str | None = None  # URL or drive file id
    version: int = 1
    status: str = "pending"  # pending | processing | ready | failed
    last_verified_at: datetime | None = None
    freshness_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChunkRecord(BaseModel):
    id: str
    document_id: str
    tenant_id: str
    content: str
    content_hash: str | None = None
    page: int | None = None
    section: str | None = None
    chunk_index: int = 0
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IngestionAuditEntry(BaseModel):
    id: str
    document_id: str
    tenant_id: str
    action: str  # ingest | re_ingest | delete | patch
    prev_hash: str | None = None
    new_hash: str | None = None
    chain_prev_id: str | None = None  # for crypto chain
    created_at: datetime = Field(default_factory=datetime.utcnow)
