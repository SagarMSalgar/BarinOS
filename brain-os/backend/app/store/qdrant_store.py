"""Qdrant vector store — production vector DB."""
from __future__ import annotations

import os
from typing import Any

from app.store.vector import ChunkMeta, SearchHit, VectorStore


class QdrantVectorStore(VectorStore):
    """Qdrant backend; uses collection per namespace (collection_name = prefix_namespace)."""

    def __init__(
        self,
        host: str | None = None,
        port: int = 6333,
        url: str | None = None,
        collection_prefix: str = "brainos",
        vector_size: int = 1536,
        prefer_grpc: bool = False,
    ) -> None:
        self._host = host or os.environ.get("QDRANT_HOST", "localhost")
        self._port = int(os.environ.get("QDRANT_PORT", port))
        self._url = url or os.environ.get("QDRANT_URL")  # e.g. http://qdrant:6333
        self._collection_prefix = collection_prefix
        self._vector_size = vector_size
        self._prefer_grpc = prefer_grpc
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                kwargs: dict[str, Any] = {"prefer_grpc": self._prefer_grpc}
                if self._url:
                    self._client = QdrantClient(url=self._url, **kwargs)
                else:
                    self._client = QdrantClient(host=self._host, port=self._port, **kwargs)
            except ImportError as e:
                raise RuntimeError("Install qdrant-client: pip install qdrant-client") from e
        return self._client

    def _collection_name(self, namespace: str) -> str:
        # Qdrant collection names: alphanumeric + underscore
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in namespace)
        return f"{self._collection_prefix}_{safe}" if safe else self._collection_prefix

    async def upsert(
        self,
        namespace: str,
        ids: list[str],
        vectors: list[list[float]],
        contents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        from qdrant_client.http import models as qmodels

        client = self._get_client()
        coll = self._collection_name(namespace)
        # Ensure collection exists
        try:
            client.get_collection(coll)
        except Exception:
            client.create_collection(
                collection_name=coll,
                vectors_config=qmodels.VectorParams(size=len(vectors[0]) if vectors else self._vector_size, distance=qmodels.Distance.COSINE),
            )
        import hashlib
        points = []
        for i, id_ in enumerate(ids):
            vec = vectors[i] if i < len(vectors) else []
            content = (contents[i] if i < len(contents) else "")[:40_000]
            meta = metadatas[i] if i < len(metadatas) else {}
            payload = {"content": content, **{k: (str(v) if v is not None else "") for k, v in meta.items()}}
            # Qdrant 1.7.x server expects integer point IDs in REST payload
            num_id = int(hashlib.sha256(id_.encode()).hexdigest()[:15], 16)
            points.append(qmodels.PointStruct(id=num_id, vector=vec, payload=payload))
        client.upsert(collection_name=coll, points=points)

    async def search(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        from qdrant_client.http import models as qmodels

        client = self._get_client()
        coll = self._collection_name(namespace)
        try:
            qfilter = None
            if filter_meta:
                qfilter = qmodels.Filter(
                    must=[qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)) for k, v in filter_meta.items()]
                )
            results = client.search(
                collection_name=coll,
                query_vector=vector,
                limit=top_k,
                query_filter=qfilter,
            )
        except Exception:
            return []
        out = []
        for r in results:
            payload = r.payload or {}
            content = payload.get("content", "")
            out.append(
                SearchHit(
                    id=str(r.id),
                    score=float(r.score or 0),
                    content=content,
                    meta=ChunkMeta(
                        document_id=payload.get("document_id", ""),
                        document_name=payload.get("document_name", ""),
                        page=int(payload["page"]) if payload.get("page") else None,
                        section=payload.get("section"),
                        chunk_index=int(payload.get("chunk_index", 0)),
                        content_hash=payload.get("content_hash"),
                        language=payload.get("language"),
                    ),
                )
            )
        return out

    async def delete_by_document(self, namespace: str, document_id: str) -> int:
        from qdrant_client.http import models as qmodels

        client = self._get_client()
        coll = self._collection_name(namespace)
        try:
            client.delete(
                collection_name=coll,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id))])
                ),
            )
        except Exception:
            pass
        return -1

    async def scroll(
        self,
        namespace: str,
        limit: int = 1000,
        offset: str | None = None,
        filter_meta: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from qdrant_client.http import models as qmodels

        client = self._get_client()
        coll = self._collection_name(namespace)
        scroll_filter = None
        if filter_meta:
            scroll_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)) for k, v in filter_meta.items()]
            )
        try:
            result, _ = client.scroll(
                collection_name=coll,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
                scroll_filter=scroll_filter,
            )
        except Exception:
            return []
        out = []
        for p in result:
            payload = p.payload or {}
            out.append({
                "id": str(p.id),
                "content": payload.get("content", ""),
                "document_id": payload.get("document_id", ""),
                "document_name": payload.get("document_name", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "content_hash": payload.get("content_hash"),
            })
        return out
