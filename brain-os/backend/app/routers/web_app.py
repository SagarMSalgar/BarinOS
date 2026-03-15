"""ZAYA Web Application Support API: intelligence and chat for embeddable widget (Zendesk, CRM, Jira, Notion, HR, etc.)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.web_app_service import web_app_intelligence, web_app_chat, APP_TYPES

router = APIRouter(prefix="/api/web-app", tags=["web-app"])


class IntelligenceBody(BaseModel):
    app_type: str  # zendesk | freshdesk | salesforce | hubspot | jira | linear | notion | confluence | hr | accounting | recruitment | custom
    context: dict[str, Any] = {}  # ticket_subject, ticket_body, deal_name, issue_title, page_content, etc.
    tenant_id: str = "default"
    namespace: str = "main"


class ChatBody(BaseModel):
    app_type: str = "custom"
    context: dict[str, Any] = {}
    question: str
    tenant_id: str = "default"
    namespace: str = "main"


@router.post("/intelligence")
async def post_intelligence(body: IntelligenceBody, request: Request) -> dict[str, Any]:
    """
    Return app-type-specific intelligence for the given context.
    Used by the embeddable ZAYA widget (Zendesk, Salesforce, Jira, Notion, HR, etc.).
    """
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {
            "error": "Vector store not configured",
            "app_type": body.app_type,
            "relevant_policy": None,
            "similar_past_tickets": [],
            "suggested_response": None,
        }
    result = await web_app_intelligence(
        body.app_type,
        body.context,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )
    return result


@router.post("/chat")
async def post_chat(body: ChatBody, request: Request) -> dict[str, Any]:
    """Answer a single question in the context of the current app view ("Ask ZAYA" in widget)."""
    vs = getattr(request.app.state, "vector_store", None)
    config = getattr(request.app.state, "config", None)
    if not vs:
        return {"answer": "Knowledge base is not configured.", "citations": []}
    result = await web_app_chat(
        body.app_type,
        body.context,
        body.question,
        body.tenant_id,
        body.namespace,
        vs,
        config,
    )
    return result


@router.get("/app-types")
async def get_app_types() -> dict[str, list[str]]:
    """Return list of supported app types for widget config."""
    return {"app_types": list(APP_TYPES)}
