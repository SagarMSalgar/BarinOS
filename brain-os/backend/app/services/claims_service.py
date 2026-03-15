"""Claims extraction from chunks, storage, timeline, 'when did this stop being true'. Config-driven prompts."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider


def _load_claims_prompts(config: dict[str, Any]) -> dict[str, Any]:
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "claims.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def extract_claims_from_chunk(
    chunk_id: str,
    document_id: str,
    document_name: str,
    content: str,
    tenant_id: str,
    namespace: str,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Use LLM to extract discrete claims from chunk text. Returns list of claim strings."""
    config = config or load_config()
    prompts = _load_claims_prompts(config)
    spec = prompts.get("extract_claims") or {}
    system = spec.get("system", "Extract factual claims from the text. Output JSON array of strings.")
    user_tpl = spec.get("user_template", "Text: {{ content }}\n\nJSON array of claims:")
    user_msg = user_tpl.replace("{{ content }}", content[:6000]).replace("{{ source }}", document_name)
    llm = get_llm_provider(config)
    try:
        raw = await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=1000,
        )
        raw = (raw or "").strip()
        m = re.search(r"\[[\s\S]*?\]", raw)
        if m:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    return []


async def store_claims(
    pool,
    tenant_id: str,
    namespace: str,
    chunk_id: str,
    document_id: str,
    document_name: str,
    claim_texts: list[str],
    valid_from: datetime | None = None,
    last_verified_at: datetime | None = None,
) -> list[str]:
    """Insert claims for a chunk. Returns list of claim ids."""
    if not pool or not claim_texts:
        return []
    valid_from = valid_from or datetime.now(timezone.utc)
    last_verified_at = last_verified_at or valid_from
    ids = []
    async with pool.acquire() as conn:
        for ct in claim_texts:
            if not (ct or "").strip():
                continue
            cid = str(uuid.uuid4())[:16]
            await conn.execute(
                """INSERT INTO claims (id, tenant_id, namespace, chunk_id, document_id, document_name, claim_text, valid_from, last_verified_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (id) DO NOTHING""",
                cid,
                tenant_id,
                namespace,
                chunk_id,
                document_id,
                document_name,
                ct.strip()[:8000],
                valid_from,
                last_verified_at,
            )
            ids.append(cid)
    return ids


async def get_claim_history(pool, claim_id: str) -> list[dict[str, Any]]:
    """Timeline of a claim: versions with valid_from/valid_until. Also current from claims table."""
    if not pool:
        return []
    out = []
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, claim_text, valid_from, valid_until, last_verified_at FROM claims WHERE id = $1", claim_id)
        if row:
            out.append({
                "claim_id": row["id"],
                "claim_text": row["claim_text"],
                "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
                "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
                "last_verified_at": row["last_verified_at"].isoformat() if row["last_verified_at"] else None,
            })
        rows = await conn.fetch(
            "SELECT claim_text, valid_from, valid_until, created_at FROM claim_versions WHERE claim_id = $1 ORDER BY created_at",
            claim_id,
        )
        for r in rows:
            out.append({
                "claim_text": r["claim_text"],
                "valid_from": r["valid_from"].isoformat() if r["valid_from"] else None,
                "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
    return out


async def when_did_stop_being_true(
    pool,
    tenant_id: str,
    namespace: str,
    claim_text_substring: str | None = None,
    claim_id: str | None = None,
) -> list[dict[str, Any]]:
    """Find claims that have valid_until set (stopped being true) or have newer version. Return timeline entries."""
    if not pool:
        return []
    out = []
    async with pool.acquire() as conn:
        if claim_id:
            rows = await conn.fetch(
                """SELECT c.id, c.claim_text, c.document_name, c.valid_from, c.valid_until, c.last_verified_at
                   FROM claims c WHERE c.id = $1""",
                claim_id,
            )
        elif claim_text_substring:
            rows = await conn.fetch(
                """SELECT id, claim_text, document_name, valid_from, valid_until, last_verified_at
                   FROM claims WHERE tenant_id = $1 AND namespace = $2 AND claim_text ILIKE $3
                   ORDER BY last_verified_at DESC LIMIT 20""",
                tenant_id,
                namespace,
                f"%{claim_text_substring}%",
            )
        else:
            rows = await conn.fetch(
                """SELECT id, claim_text, document_name, valid_from, valid_until, last_verified_at
                   FROM claims WHERE tenant_id = $1 AND namespace = $2 AND valid_until IS NOT NULL
                   ORDER BY valid_until DESC LIMIT 50""",
                tenant_id,
                namespace,
            )
        for r in rows:
            out.append({
                "claim_id": r["id"],
                "claim_text": r["claim_text"],
                "document_name": r["document_name"],
                "valid_from": r["valid_from"].isoformat() if r.get("valid_from") else None,
                "valid_until": r["valid_until"].isoformat() if r.get("valid_until") else None,
                "last_verified_at": r["last_verified_at"].isoformat() if r.get("last_verified_at") else None,
            })
    return out


async def list_claims(
    pool,
    tenant_id: str,
    namespace: str,
    document_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List claims for namespace, optionally filtered by document."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        if document_id:
            rows = await conn.fetch(
                """SELECT id, chunk_id, document_id, document_name, claim_text, valid_from, valid_until, last_verified_at, created_at
                   FROM claims WHERE tenant_id = $1 AND namespace = $2 AND document_id = $3 ORDER BY created_at DESC LIMIT $4""",
                tenant_id,
                namespace,
                document_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, chunk_id, document_id, document_name, claim_text, valid_from, valid_until, last_verified_at, created_at
                   FROM claims WHERE tenant_id = $1 AND namespace = $2 ORDER BY created_at DESC LIMIT $3""",
                tenant_id,
                namespace,
                limit,
            )
    return [
        {
            "id": r["id"],
            "chunk_id": r["chunk_id"],
            "document_id": r["document_id"],
            "document_name": r["document_name"],
            "claim_text": r["claim_text"],
            "valid_from": r["valid_from"].isoformat() if r.get("valid_from") else None,
            "valid_until": r["valid_until"].isoformat() if r.get("valid_until") else None,
            "last_verified_at": r["last_verified_at"].isoformat() if r.get("last_verified_at") else None,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]
