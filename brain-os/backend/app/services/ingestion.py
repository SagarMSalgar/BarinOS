"""Universal ingestion: chunk, embed, index. Config-driven; LLM used for structure extraction when configured."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any

from app.core.config import load_config, get_intent_prompt
from app.providers import get_embedding_provider, get_llm_provider
from app.store import DocumentRegistry, VectorStore
from app.store.vector import InMemoryVectorStore


def _default_chunk(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Simple semantic-ish chunking by paragraphs then by size."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks = []
    current = []
    current_len = 0
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if current_len + len(p) > chunk_size and current:
            chunks.append("\n\n".join(current))
            overlap_text = "\n\n".join(current)[-overlap:] if overlap else ""
            current = [overlap_text, p] if overlap_text else [p]
            current_len = len(p) + len(overlap_text)
        else:
            current.append(p)
            current_len += len(p)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _progress_cb_noop(_phase: str, _cur: int, _tot: int, _msg: str) -> None:
    pass


async def ingest_document(
    tenant_id: str,
    namespace: str,
    document_id: str,
    document_name: str,
    raw_content: str,
    *,
    config: dict[str, Any] | None = None,
    registry: DocumentRegistry | None = None,
    vector_store: VectorStore | None = None,
    extract_with_llm: bool = True,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Chunk, optionally extract with LLM, embed, and index. Returns stats. Optional progress_callback(phase, current, total, message)."""
    config = config or load_config()
    registry = registry or DocumentRegistry()
    vector_store = vector_store or InMemoryVectorStore()
    report = progress_callback or _progress_cb_noop

    # Optional LLM extraction (from config intent)
    content_to_chunk = raw_content
    report("reading", 0, 1, "Reading your document...")
    if extract_with_llm:
        prompt_cfg = get_intent_prompt(config, "ingest")
        if prompt_cfg:
            llm = get_llm_provider(config)
            user_msg = prompt_cfg["user_template"].replace("{{ raw_content }}", raw_content[:50000])
            messages = [
                {"role": "system", "content": prompt_cfg["system"]},
                {"role": "user", "content": user_msg},
            ]
            try:
                extracted = await llm.complete(messages, stream=False, max_tokens=16000)
                if extracted and len(extracted.strip()) > 100:
                    content_to_chunk = extracted
            except Exception:
                pass

    chunks = _default_chunk(content_to_chunk)
    if not chunks:
        return {"document_id": document_id, "chunks_created": 0, "indexed": False}

    total = len(chunks)
    report("chunking", total, total, f"Creating {total} knowledge chunks...")

    emb = get_embedding_provider(config)
    dim_cfg = config.get("embedding", {}).get("dimensions", 1536)
    vectors = []
    for i in range(0, len(chunks), 10):
        batch = chunks[i : i + 10]
        vecs = await emb.embed(batch, dimensions=dim_cfg)
        vectors.extend(vecs)
        report("embedding", min(i + len(batch), total), total, f"Embedding chunk {min(i + len(batch), total)} of {total}...")

    ids = []
    contents = []
    metadatas = []
    for i, (c, vec) in enumerate(zip(chunks, vectors)):
        ch_id = f"{document_id}:chunk:{i}"
        ids.append(ch_id)
        contents.append(c)
        content_hash = hashlib.sha256(c.encode()).hexdigest()[:16]
        metadatas.append({
            "document_id": document_id,
            "document_name": document_name,
            "page": None,
            "section": None,
            "chunk_index": i,
            "content_hash": content_hash,
            "language": "en",
        })

    report("indexing", 0, 1, "Writing to knowledge base...")
    await vector_store.upsert(namespace, ids, vectors, contents, metadatas)
    await registry.update(document_id, status="ready", metadata={"chunk_count": len(chunks), "namespace": namespace})
    return {
        "document_id": document_id,
        "chunks_created": len(chunks),
        "indexed": True,
    }
