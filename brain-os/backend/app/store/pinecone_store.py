"""Pinecone vector store (production)."""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from .vector import ChunkMeta, SearchHit, VectorStore


class PineconeVectorStore(VectorStore):
    def __init__(
        self,
        index_name: str | None = None,
        api_key: str | None = None,
        namespace_prefix: str = "brainos",
    ) -> None:
        self.index_name = index_name or os.environ.get("PINECONE_INDEX", "brainos")
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        self.namespace_prefix = namespace_prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from pinecone import Pinecone
                self._client = Pinecone(api_key=self.api_key).Index(self.index_name)
            except Exception as e:
                raise RuntimeError(f"Pinecone not available: {e}") from e
        return self._client

    def _meta_to_serializable(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {k: (str(v) if v is not None else "") for k, v in meta.items()}

    async def upsert(
        self,
        namespace: str,
        ids: list[str],
        vectors: list[list[float]],
        contents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        index = self._get_client()
        ns = f"{self.namespace_prefix}_{namespace}"
        # Pinecone accepts list of (id, vector, metadata). Store content in metadata.
        vectors_list = []
        for i, id_ in enumerate(ids):
            vec = vectors[i] if i < len(vectors) else []
            content = contents[i] if i < len(contents) else ""
            meta = metadatas[i] if i < len(metadatas) else {}
            meta["content"] = content[:40_000]  # limit size
            vectors_list.append({"id": id_, "values": vec, "metadata": self._meta_to_serializable(meta)})
        # Batch upsert (Pinecone sync API; in production use async client)
        index.upsert(vectors=vectors_list, namespace=ns)

    async def search(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        index = self._get_client()
        ns = f"{self.namespace_prefix}_{namespace}"
        query_kwargs = {"vector": vector, "top_k": top_k, "include_metadata": True}
        if filter_meta:
            query_kwargs["filter"] = filter_meta
        result = index.query(namespace=ns, **query_kwargs)
        out = []
        for match in (result.get("matches") or []):
            meta = match.get("metadata") or {}
            content = meta.get("content", "")
            out.append(
                SearchHit(
                    id=match["id"],
                    score=float(match.get("score", 0)),
                    content=content,
                    meta=ChunkMeta(
                        document_id=meta.get("document_id", ""),
                        document_name=meta.get("document_name", ""),
                        page=int(meta["page"]) if meta.get("page") else None,
                        section=meta.get("section"),
                        chunk_index=int(meta.get("chunk_index", 0)),
                        content_hash=meta.get("content_hash"),
                        language=meta.get("language"),
                    ),
                )
            )
        return out

    async def delete_by_document(self, namespace: str, document_id: str) -> int:
        index = self._get_client()
        ns = f"{self.namespace_prefix}_{namespace}"
        index.delete(filter={"document_id": document_id}, namespace=ns)
        return -1  # Pinecone doesn't return count
