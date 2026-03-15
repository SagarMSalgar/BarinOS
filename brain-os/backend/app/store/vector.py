"""Vector store abstraction — Qdrant, Pinecone, Chroma, or in-memory for dev."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ChunkMeta(BaseModel):
    document_id: str
    document_name: str
    page: int | None = None
    section: str | None = None
    chunk_index: int = 0
    content_hash: str | None = None
    language: str | None = None


class SearchHit(BaseModel):
    id: str
    score: float
    content: str
    meta: ChunkMeta


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        namespace: str,
        ids: list[str],
        vectors: list[list[float]],
        contents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert vectors with metadata."""
        ...

    @abstractmethod
    async def search(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        """Return top_k nearest neighbors with content and metadata."""
        ...

    @abstractmethod
    async def delete_by_document(self, namespace: str, document_id: str) -> int:
        """Delete all vectors for a document. Return count deleted."""
        ...

    async def scroll(
        self,
        namespace: str,
        limit: int = 1000,
        offset: str | None = None,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Scroll points for export. filter_meta e.g. {"document_id": "..."} to get chunks for one document."""
        raise NotImplementedError("scroll not implemented")


class InMemoryVectorStore(VectorStore):
    """Dev fallback when Pinecone/Chroma not configured."""

    def __init__(self) -> None:
        self._data: dict[str, list[tuple[str, list[float], str, dict]]] = {}

    async def upsert(
        self,
        namespace: str,
        ids: list[str],
        vectors: list[list[float]],
        contents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if namespace not in self._data:
            self._data[namespace] = []
        for i, id_ in enumerate(ids):
            vec = vectors[i] if i < len(vectors) else []
            content = contents[i] if i < len(contents) else ""
            meta = metadatas[i] if i < len(metadatas) else {}
            # Replace existing id
            self._data[namespace] = [(xid, v, c, m) for xid, v, c, m in self._data[namespace] if xid != id_]
            self._data[namespace].append((id_, vec, content, meta))

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na * nb == 0:
            return 0.0
        return dot / (na * nb)

    async def search(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        rows = self._data.get(namespace, [])
        scored = []
        for id_, vec, content, meta in rows:
            if filter_meta:
                if not all(meta.get(k) == v for k, v in filter_meta.items()):
                    continue
            score = self._cosine(vector, vec)
            scored.append((id_, score, content, meta))
        scored.sort(key=lambda x: -x[1])
        out = []
        for id_, score, content, meta in scored[:top_k]:
            out.append(
                SearchHit(
                    id=id_,
                    score=round(score, 4),
                    content=content,
                    meta=ChunkMeta(**{k: v for k, v in meta.items() if k in ChunkMeta.model_fields}),
                )
            )
        return out

    async def delete_by_document(self, namespace: str, document_id: str) -> int:
        if namespace not in self._data:
            return 0
        before = len(self._data[namespace])
        self._data[namespace] = [(xid, v, c, m) for xid, v, c, m in self._data[namespace] if m.get("document_id") != document_id]
        return before - len(self._data[namespace])

    async def scroll(
        self,
        namespace: str,
        limit: int = 1000,
        offset: str | None = None,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._data.get(namespace, [])
        if filter_meta:
            rows = [(id_, v, c, m) for id_, v, c, m in rows if all(m.get(k) == v for k, v in filter_meta.items())]
        rows = rows[:limit]
        return [{"id": id_, "content": c, **m} for id_, _v, c, m in rows]
