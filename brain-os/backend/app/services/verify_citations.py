"""Verify cited sources: check freshness for URL-based docs, last_verified for others."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.store import DocumentRegistry
from app.services.fetch_url import fetch_url_content


async def verify_documents(
    document_ids: list[str],
    registry: DocumentRegistry,
) -> tuple[list[dict[str, Any]], str]:
    """
    For each document_id, check if the source is still current (URL: re-fetch and compare hash; else use last_verified).
    Returns (list of per-doc results, summary message).
    """
    results = []
    for doc_id in document_ids:
        doc = await registry.get(doc_id)
        if not doc:
            results.append({
                "document_id": doc_id,
                "document_name": "",
                "status": "not_found",
                "message": "Document not in registry",
            })
            continue
        name = doc.name or doc_id
        meta = doc.metadata or {}
        external_id = doc.external_id or ""
        content_hash = meta.get("content_hash")
        last_content = meta.get("last_content")  # may be truncated

        if external_id.startswith(("http://", "https://")):
            try:
                new_content = await fetch_url_content(external_id, timeout=15.0)
                new_hash = hashlib.sha256(new_content.encode()).hexdigest()[:16]
                if content_hash and new_hash == content_hash:
                    results.append({
                        "document_id": doc_id,
                        "document_name": name,
                        "status": "current",
                        "updated_at": doc.last_verified_at.isoformat() if doc.last_verified_at else None,
                    })
                else:
                    results.append({
                        "document_id": doc_id,
                        "document_name": name,
                        "status": "updated",
                        "message": "Source has changed since last ingestion",
                        "updated_at": datetime.utcnow().isoformat(),
                    })
            except Exception as e:
                results.append({
                    "document_id": doc_id,
                    "document_name": name,
                    "status": "error",
                    "message": str(e)[:200],
                })
        else:
            if doc.last_verified_at:
                results.append({
                    "document_id": doc_id,
                    "document_name": name,
                    "status": "current",
                    "updated_at": doc.last_verified_at.isoformat(),
                })
            else:
                results.append({
                    "document_id": doc_id,
                    "document_name": name,
                    "status": "not_verifiable",
                    "message": "Not a URL source; cannot re-verify automatically",
                })

    # Deduplicate by (document_name, status, message) so UI shows each unique outcome once with a count
    key_to_result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in results:
        name = (r.get("document_name") or "").strip()
        status = r.get("status") or ""
        msg = (r.get("message") or "").strip()
        key = (name, status, msg)
        if key not in key_to_result:
            key_to_result[key] = {**r, "count": 0}
        key_to_result[key]["count"] = key_to_result[key].get("count", 0) + 1
    deduplicated = list(key_to_result.values())

    # Summary (based on original counts)
    current = sum(1 for r in results if r["status"] == "current")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] in ("error", "not_found"))
    unverifiable = sum(1 for r in results if r["status"] == "not_verifiable")
    if updated > 0 or errors > 0:
        summary = f"{updated} source(s) updated since last sync."
        if errors > 0:
            summary += f" {errors} could not be verified."
    elif unverifiable == len(results):
        summary = "Sources are not URL-based; automatic verification unavailable."
    else:
        summary = "All sources current."
    return deduplicated, summary
