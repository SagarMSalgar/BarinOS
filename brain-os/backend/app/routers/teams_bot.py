"""Microsoft Teams bot: Bot Framework connector receives messages, replies with BrainOS answer."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/bots/teams", tags=["teams"])


async def _get_answer(tenant_id: str, namespace: str, question: str, app_request: Request) -> str:
    from app.services.rag import stream_answer
    config = getattr(app_request.app.state, "config", None)
    vs = getattr(app_request.app.state, "vector_store", None)
    if not config or not vs:
        return "BrainOS is not configured."
    text = ""
    async for event in stream_answer(tenant_id, namespace, question, config=config, vector_store=vs):
        if event.get("type") == "token":
            text += event.get("payload", {}).get("text", "")
    return text or "I couldn't find an answer in the knowledge base."


@router.post("/messages")
async def teams_messages(request: Request):
    """Bot Framework: Activity with type message -> reply with BrainOS answer."""
    body = await request.json()
    activity_type = body.get("type")
    if activity_type == "message":
        text = (body.get("text") or "").strip()
        tenant_id = os.environ.get("TEAMS_TENANT_ID", "default")
        namespace = os.environ.get("TEAMS_NAMESPACE", "main")
        answer = await _get_answer(tenant_id, namespace, text or "What can you help with?", request)
        service_url = body.get("serviceUrl", "")
        conversation = body.get("conversation", {})
        from_id = body.get("from", {})
        # Return reply; Bot Framework connector or Azure Bot can POST this to the conversation
        return {"status": "ok", "reply": answer, "type": "message"}
    return {"status": "ok"}
