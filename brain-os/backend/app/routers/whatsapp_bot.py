"""WhatsApp bot: Twilio (or generic webhook) receives message, replies with BrainOS answer."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, Form
from fastapi.responses import Response, PlainTextResponse

router = APIRouter(prefix="/api/bots/whatsapp", tags=["whatsapp"])


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


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(None, alias="Body"),
    From: str = Form(None, alias="From"),
    To: str = Form(None, alias="To"),
):
    """Twilio WhatsApp webhook: form POST with Body=message. Returns TwiML or plain text."""
    # Also accept JSON for non-Twilio (e.g. WhatsApp Business API)
    body_text = Body
    if body_text is None:
        try:
            j = await request.json()
            body_text = j.get("text") or j.get("Body") or j.get("message", "")
        except Exception:
            body_text = ""
    body_text = (body_text or "").strip()
    tenant_id = os.environ.get("WHATSAPP_TENANT_ID", "default")
    namespace = os.environ.get("WHATSAPP_NAMESPACE", "main")
    answer = await _get_answer(tenant_id, namespace, body_text or "What can you help with?", request)
    # TwiML response for Twilio
    if "twilio" in (request.headers.get("user-agent") or "").lower() or os.environ.get("WHATSAPP_TWILIO"):
        return Response(
            content=f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{answer}</Message></Response>',
            media_type="application/xml",
        )
    return PlainTextResponse(answer)


@router.post("/message")
async def whatsapp_message(request: Request):
    """Generic JSON webhook: {"text": "user question"} -> {"reply": "answer"}."""
    body = await request.json()
    text = (body.get("text") or body.get("message") or "").strip()
    tenant_id = os.environ.get("WHATSAPP_TENANT_ID", "default")
    namespace = os.environ.get("WHATSAPP_NAMESPACE", "main")
    answer = await _get_answer(tenant_id, namespace, text or "What can you help with?", request)
    return {"reply": answer}
