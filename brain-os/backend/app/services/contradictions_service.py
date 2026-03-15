"""Detect contradictions between claims (batch job). LLM-driven; no hardcoded rules."""
from __future__ import annotations

import json
import re
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


async def detect_contradictions(
    pool,
    tenant_id: str,
    namespace: str,
    config: dict[str, Any] | None = None,
    max_pairs: int = 500,
) -> list[dict[str, Any]]:
    """Fetch claims, compare pairs from different docs, use LLM to decide contradiction. Store and return new ones."""
    if not pool:
        return []
    config = config or load_config()
    prompts = _load_claims_prompts(config)
    spec = prompts.get("contradict") or {}
    system = spec.get("system", "Reply JSON: {\"contradicts\": true|false, \"reason\": \"...\"}")
    user_tpl = spec.get("user_template", "Claim A: {{ claim_a }}\nClaim B: {{ claim_b }}\nJSON:")
    llm = get_llm_provider(config)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, document_id, document_name, claim_text FROM claims
               WHERE tenant_id = $1 AND namespace = $2 ORDER BY id LIMIT 200""",
            tenant_id,
            namespace,
        )
    claims = [dict(r) for r in rows]
    if len(claims) < 2:
        return []

    inserted = []
    seen = set()
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            if len(inserted) >= max_pairs:
                break
            a, b = claims[i], claims[j]
            if a["document_id"] == b["document_id"]:
                continue
            key = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
            if key in seen:
                continue
            user_msg = (
                user_tpl.replace("{{ claim_a }}", (a["claim_text"] or "")[:500])
                .replace("{{ claim_b }}", (b["claim_text"] or "")[:500])
                .replace("{{ doc_a }}", a["document_name"] or "")
                .replace("{{ doc_b }}", b["document_name"] or "")
            )
            try:
                raw = await llm.complete(
                    [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                    stream=False,
                    max_tokens=150,
                )
                raw = (raw or "").strip()
                m = re.search(r"\{[^{}]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                    if data.get("contradicts"):
                        reason = (data.get("reason") or "")[:500]
                        async with pool.acquire() as conn:
                            await conn.execute(
                                """INSERT INTO contradictions (tenant_id, namespace, claim_id_a, claim_id_b, document_name_a, document_name_b, claim_text_a, claim_text_b, summary, status)
                                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'open')""",
                                tenant_id,
                                namespace,
                                a["id"],
                                b["id"],
                                a["document_name"] or "",
                                b["document_name"] or "",
                                (a["claim_text"] or "")[:2000],
                                (b["claim_text"] or "")[:2000],
                                reason,
                            )
                        inserted.append({
                            "claim_id_a": a["id"],
                            "claim_id_b": b["id"],
                            "document_name_a": a["document_name"],
                            "document_name_b": b["document_name"],
                            "claim_text_a": (a["claim_text"] or "")[:200],
                            "claim_text_b": (b["claim_text"] or "")[:200],
                            "summary": reason,
                        })
                        seen.add(key)
            except Exception:
                continue
    return inserted


async def list_contradictions(
    pool,
    tenant_id: str,
    namespace: str,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List stored contradictions."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """SELECT id, claim_id_a, claim_id_b, document_name_a, document_name_b, claim_text_a, claim_text_b, summary, status, created_at
                   FROM contradictions WHERE tenant_id = $1 AND namespace = $2 AND status = $3 ORDER BY created_at DESC LIMIT $4""",
                tenant_id,
                namespace,
                status,
                limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, claim_id_a, claim_id_b, document_name_a, document_name_b, claim_text_a, claim_text_b, summary, status, created_at
                   FROM contradictions WHERE tenant_id = $1 AND namespace = $2 ORDER BY created_at DESC LIMIT $3""",
                tenant_id,
                namespace,
                limit,
            )
    return [
        {
            "id": r["id"],
            "claim_id_a": r["claim_id_a"],
            "claim_id_b": r["claim_id_b"],
            "document_name_a": r["document_name_a"],
            "document_name_b": r["document_name_b"],
            "claim_text_a": r["claim_text_a"],
            "claim_text_b": r["claim_text_b"],
            "summary": r["summary"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]
