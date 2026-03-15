"""Browser extension APIs: compare text vs KB, fact-check, position, email, contract, research, form, meeting-prep, watch-page."""
from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/extension", tags=["extension"])


class TextVsKbBody(BaseModel):
    selected_text: str
    mode: str  # compare | factcheck | position
    tenant_id: str = "default"
    namespace: str = "main"


class VerifyClaimsBody(BaseModel):
    claims: list[str]
    tenant_id: str = "default"
    namespace: str = "main"


class EmailAnalyzeBody(BaseModel):
    subject: str = ""
    body: str = ""
    tenant_id: str = "default"
    namespace: str = "main"


class ContractReviewBody(BaseModel):
    contract_text: str
    tenant_id: str = "default"
    namespace: str = "main"


class ResearchSynthesizeBody(BaseModel):
    sources: list[str]
    tenant_id: str = "default"
    namespace: str = "main"


class FormSuggestBody(BaseModel):
    field_labels: list[str]
    tenant_id: str = "default"
    namespace: str = "main"


class MeetingPrepBody(BaseModel):
    meeting_title: str = ""
    attendee_names: list[str] = []
    tenant_id: str = "default"
    namespace: str = "main"


class WatchPageBody(BaseModel):
    url: str = ""
    action: str = "add"  # add | check
    content: str = ""  # for check: current page text
    tenant_id: str = "default"
    namespace: str = "main"
    user_key: str = "default"


@router.post("/text-vs-kb")
async def extension_text_vs_kb(body: TextVsKbBody, request: Request):
    """Compare selected text with knowledge base. mode: compare | factcheck | position."""
    from app.services.extension_service import text_vs_kb
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"error": "Vector store not configured", "consistent": [], "conflicts": []}
    result = await text_vs_kb(
        body.selected_text,
        body.mode,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )
    return result


@router.post("/verify-claims")
async def extension_verify_claims(body: VerifyClaimsBody, request: Request):
    """Verify list of claims against KB. For live document assistant."""
    from app.services.extension_service import verify_claims
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return []
    return await verify_claims(body.claims, body.tenant_id, body.namespace, vs, config)


@router.post("/email-analyze")
async def extension_email_analyze(body: EmailAnalyzeBody, request: Request):
    """Extract key info, actions, reply context from email + KB."""
    from app.services.extension_service import email_analyze
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"key_info": [], "suggested_actions": [], "reply_context": "", "related_doc_names": []}
    return await email_analyze(
        body.subject,
        body.body,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )


@router.post("/contract-review")
async def extension_contract_review(body: ContractReviewBody, request: Request):
    """Compare contract text to standard terms in KB."""
    from app.services.extension_service import contract_review
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"consistent": [], "deviations": [], "not_in_standard": []}
    return await contract_review(
        body.contract_text,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )


@router.post("/research-synthesize")
async def extension_research_synthesize(body: ResearchSynthesizeBody, request: Request):
    """Synthesize multiple research sources into findings and draft."""
    from app.services.extension_service import research_synthesize
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"key_findings": [], "agreements": [], "disagreements": [], "synthesis_draft": ""}
    return await research_synthesize(
        body.sources,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )


@router.post("/form-suggest")
async def extension_form_suggest(body: FormSuggestBody, request: Request):
    """Suggest form field values from KB."""
    from app.services.extension_service import form_field_suggest
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"suggestions": []}
    return await form_field_suggest(
        body.field_labels,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )


@router.post("/meeting-prep")
async def extension_meeting_prep(body: MeetingPrepBody, request: Request):
    """Generate meeting prep brief from KB."""
    from app.services.extension_service import meeting_prep
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"brief": "", "related_docs": [], "suggested_questions": []}
    return await meeting_prep(
        body.meeting_title,
        body.attendee_names or [],
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )


@router.get("/watched-pages")
async def extension_watched_pages(
    tenant_id: str = "default",
    namespace: str = "main",
    user_key: str = "default",
):
    """List watched pages for competitive intelligence."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"watched": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT url, last_checked_at, created_at
            FROM extension_watched_pages
            WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3
            ORDER BY last_checked_at DESC
            """,
            tenant_id,
            namespace,
            user_key,
        )
    return {
        "watched": [
            {"url": r["url"], "last_checked_at": str(r["last_checked_at"]), "created_at": str(r["created_at"])}
            for r in rows
        ]
    }


@router.post("/watch-page")
async def extension_watch_page(body: WatchPageBody, request: Request) -> dict[str, Any]:
    """Add a page to watch or check for changes (competitive intelligence)."""
    from app.db.connection import get_pool
    if not body.url or not body.url.strip():
        return {"ok": False, "error": "url required"}
    pool = await get_pool()
    if not pool:
        return {"ok": False, "error": "Database not configured"}
    content_hash = hashlib.sha256((body.content or "").encode()).hexdigest()[:32] if body.content else None
    async with pool.acquire() as conn:
        if body.action == "add":
            await conn.execute(
                """
                INSERT INTO extension_watched_pages (tenant_id, namespace, user_key, url, last_content, last_content_hash, last_checked_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (tenant_id, namespace, user_key, url)
                DO UPDATE SET last_checked_at = NOW()
                """,
                body.tenant_id,
                body.namespace,
                body.user_key,
                body.url.strip(),
                (body.content or "")[:50000] if body.content else None,
                content_hash,
            )
            return {"ok": True, "message": "Page added to watch list"}
        if body.action == "check":
            row = await conn.fetchrow(
                """
                SELECT last_content_hash, last_content FROM extension_watched_pages
                WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3 AND url = $4
                """,
                body.tenant_id,
                body.namespace,
                body.user_key,
                body.url.strip(),
            )
            if not row:
                await conn.execute(
                    """
                    INSERT INTO extension_watched_pages (tenant_id, namespace, user_key, url, last_content, last_content_hash, last_checked_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (tenant_id, namespace, user_key, url)
                    DO UPDATE SET last_content = EXCLUDED.last_content, last_content_hash = EXCLUDED.last_content_hash, last_checked_at = NOW()
                    """,
                    body.tenant_id,
                    body.namespace,
                    body.user_key,
                    body.url.strip(),
                    (body.content or "")[:50000],
                    content_hash,
                )
                return {"ok": True, "changed": False, "message": "First check; baseline saved"}
            prev_hash = row["last_content_hash"]
            prev_content = row["last_content"] or ""
            changed = prev_hash != content_hash
            new_content = (body.content or "")[:50000] if body.content else None
            summary = ""
            if changed and prev_content and new_content:
                from app.services.freshness import semantic_diff
                config = getattr(request.app.state, "config", None)
                try:
                    summary = await semantic_diff(
                        prev_content[:20000],
                        (new_content or "")[:20000],
                        config,
                    )
                except Exception:
                    summary = "Content changed; summary unavailable."
            await conn.execute(
                """
                UPDATE extension_watched_pages
                SET last_content = $1, last_content_hash = $2, last_checked_at = NOW()
                WHERE tenant_id = $3 AND namespace = $4 AND user_key = $5 AND url = $6
                """,
                new_content,
                content_hash,
                body.tenant_id,
                body.namespace,
                body.user_key,
                body.url.strip(),
            )
            return {
                "ok": True,
                "changed": changed,
                "message": "Content changed" if changed else "No changes",
                "summary": summary if summary else None,
            }
    return {"ok": False, "error": "Invalid action"}
