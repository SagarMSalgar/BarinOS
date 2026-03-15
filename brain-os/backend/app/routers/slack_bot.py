"""Slack bot: webhook receives events, replies with BrainOS chat answer. Proactive offers (one per thread, then silence)."""
from __future__ import annotations

import asyncio
import json
import hmac
import hashlib
import os
import re
import logging
import time
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Header, Query

from app.services.proactive_service import (
    classify_conversation,
    offer_already_made,
    record_offer_made,
    user_opted_out,
    is_quiet_channel,
    CONFIDENCE_THRESHOLD,
    PLANNING_SIGNALS_MIN,
    FEATURE_PLANNER,
    FEATURE_MEETING,
    FEATURE_REQUIREMENTS,
)
from app.services.slack_proactive_flows import (
    handle_block_action,
    handle_view_submission,
    _blocks_plan_offer,
    _blocks_meeting_offer,
    _blocks_requirements_offer,
)

router = APIRouter(prefix="/api/bots/slack", tags=["slack"])
log = logging.getLogger(__name__)

# Process each Slack event_id only once (Slack retries if we don't respond in ~3s; we respond immediately and process in background).
_seen_event_ids: dict[str, float] = {}
_EVENT_ID_TTL_SEC = 300
_MAX_SEEN = 5000


def _prune_seen_event_ids() -> None:
    now = time.monotonic()
    expired = [eid for eid, t in _seen_event_ids.items() if now - t > _EVENT_ID_TTL_SEC]
    for eid in expired:
        del _seen_event_ids[eid]
    while len(_seen_event_ids) > _MAX_SEEN:
        oldest = min(_seen_event_ids, key=lambda e: _seen_event_ids[e])
        del _seen_event_ids[oldest]


def _strip_mention(text: str) -> str:
    """Remove leading <@USERID> from Slack message text."""
    return re.sub(r"^\s*<@[A-Z0-9]+>\s*", "", text).strip()


def _verify_slack_signature(body: bytes, signature: str | None) -> bool:
    secret = (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
    if not secret or not signature:
        return False
    if not signature.startswith("v0="):
        return False
    computed = "v0=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


async def _get_answer(tenant_id: str, namespace: str, question: str, app_request: Request, user_key: str | None = None) -> tuple[str, list[dict], float]:
    """Same RAG flow as main chat: stream_answer with strict_mode and optional episodic/user memory."""
    from app.services.rag import stream_answer
    config = getattr(app_request.app.state, "config", None)
    vs = getattr(app_request.app.state, "vector_store", None)
    if not config or not vs:
        return "BrainOS is not configured.", [], 0.0
    episodic_context = ""
    user_memory_context = ""
    try:
        from app.db.connection import get_pool
        pool = await get_pool()
        if pool:
            from app.services.memory_service import get_recent_episodic, get_user_memory
            recent = await get_recent_episodic(pool, tenant_id, namespace, limit=5)
            if recent:
                episodic_context = "\n".join(f"- {m.get('summary', '')}" for m in recent)
            um = await get_user_memory(pool, tenant_id, namespace)
            if um:
                user_memory_context = json.dumps(um)[:1500]
    except Exception:
        pass
    text = ""
    citations: list[dict] = []
    confidence = 0.0
    async for event in stream_answer(
        tenant_id,
        namespace,
        question,
        config=config,
        vector_store=vs,
        strict_mode=False,
        episodic_context=episodic_context or None,
        user_memory_context=user_memory_context or None,
        user_key=user_key,
    ):
        if event.get("type") == "token":
            text += event.get("payload", {}).get("text", "")
        if event.get("type") == "citation":
            citations = event.get("payload", {}).get("citations") or citations
        if event.get("type") == "confidence":
            confidence = event.get("payload", {}).get("score", 0.0)
    return text or "I couldn't find an answer in the knowledge base.", citations, confidence


async def _process_slack_event_and_reply(
    app: Any, channel: str, text: str, tenant_id: str, namespace: str, bot_token: str, user_key: str | None = None
) -> None:
    """Background: typing indicator, same RAG as main chat, then one formatted reply (Block Kit: answer, sources, confidence)."""
    import httpx
    class _AppRequest:
        pass
    req = _AppRequest()
    req.app = app
    thinking_ts: str | None = None
    async with httpx.AsyncClient() as client:
        auth = {"Authorization": f"Bearer {bot_token}"}
        # Typing indicator so user sees immediate feedback
        r0 = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers=auth,
            json={"channel": channel, "text": "BrainOS is thinking…"},
        )
        if r0.is_success:
            body = r0.json()
            if body.get("ok") and body.get("ts"):
                thinking_ts = body["ts"]
        try:
            answer, citations, confidence = await _get_answer(tenant_id, namespace, text, req, user_key=user_key)
        except Exception:
            log.exception("Slack background: _get_answer failed")
            answer = "Sorry, I encountered an error. Please try again."
            citations = []
            confidence = 0.0
        blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": answer}}]
        if citations:
            source_lines = "\n".join(
                f"• {c.get('document_name', 'Source')}" + (f" (p.{c.get('page')})" if c.get("page") else "")
                for c in citations[:10]
            )
            blocks.append({"type": "divider"})
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Sources:*\n{source_lines}"}})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Confidence: {confidence:.0f}%  •  Ask a follow-up in thread or in Ask BrainOS"}]})
        r = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers=auth,
            json={"channel": channel, "text": answer, "blocks": blocks},
        )
        if not r.is_success:
            log.warning("Slack chat.postMessage failed: %s %s", r.status_code, r.text)
        # Remove typing indicator so only the final answer remains
        if thinking_ts:
            await client.post(
                "https://slack.com/api/chat.delete",
                headers=auth,
                json={"channel": channel, "ts": thinking_ts},
            )


async def _run_proactive_classifier(
    app: Any,
    team_id: str,
    channel_id: str,
    thread_ts: str,
    user_id: str,
    bot_token: str,
    tenant_id: str,
    namespace: str,
) -> None:
    try:
        from app.db.connection import get_pool
        import httpx
        pool = await get_pool()
        if not pool or not bot_token:
            return
        if await is_quiet_channel(pool, team_id, channel_id):
            return
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://slack.com/api/conversations.replies",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"channel": channel_id, "ts": thread_ts, "limit": 30},
            )
        if not r.is_success or len((r.json().get("messages") or [])) < 2:
            return
        messages = r.json().get("messages") or []
        conversation = "\n".join((m.get("text") or "").strip() for m in messages if not m.get("bot_id"))
        if len(conversation.strip()) < 50:
            return
        config = getattr(app.state, "config", None) or __import__("app.core.config", fromlist=["load_config"]).load_config()
        out = await classify_conversation(conversation[:4000], config)
        if (out.get("confidence") or 0) < CONFIDENCE_THRESHOLD:
            return
        planning, meeting, requirements = out.get("planning_signals") or 0, out.get("meeting_signals") or 0, out.get("requirements_signals") or 0
        if planning >= PLANNING_SIGNALS_MIN and not await offer_already_made(pool, team_id, channel_id, thread_ts, FEATURE_PLANNER) and not await user_opted_out(pool, team_id, user_id, FEATURE_PLANNER):
            await record_offer_made(pool, team_id, channel_id, thread_ts, FEATURE_PLANNER)
            async with httpx.AsyncClient() as client:
                await client.post("https://slack.com/api/chat.postEphemeral", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": channel_id, "user": user_id, "thread_ts": thread_ts, "text": "BrainOS noticed you're planning a project.", "blocks": _blocks_plan_offer()})
            return
        if meeting >= 1 and not await offer_already_made(pool, team_id, channel_id, thread_ts, FEATURE_MEETING) and not await user_opted_out(pool, team_id, user_id, FEATURE_MEETING):
            await record_offer_made(pool, team_id, channel_id, thread_ts, FEATURE_MEETING)
            async with httpx.AsyncClient() as client:
                await client.post("https://slack.com/api/chat.postEphemeral", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": channel_id, "user": user_id, "thread_ts": thread_ts, "text": "Looks like meeting notes.", "blocks": _blocks_meeting_offer()})
            return
        if requirements >= 1 and not await offer_already_made(pool, team_id, channel_id, thread_ts, FEATURE_REQUIREMENTS) and not await user_opted_out(pool, team_id, user_id, FEATURE_REQUIREMENTS):
            await record_offer_made(pool, team_id, channel_id, thread_ts, FEATURE_REQUIREMENTS)
            async with httpx.AsyncClient() as client:
                await client.post("https://slack.com/api/chat.postEphemeral", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": channel_id, "user": user_id, "thread_ts": thread_ts, "text": "I see a requirements document.", "blocks": _blocks_requirements_offer()})
    except Exception:
        log.exception("Proactive classifier failed")


async def _send_onboarding_dm(team_id: str, user_id: str, channel_id: str, bot_token: str, tenant_id: str, namespace: str, app: Any) -> None:
    try:
        from app.db.connection import get_pool
        from app.services.proactive_service import get_onboarding_top_questions
        import httpx
        pool = await get_pool()
        if not pool or not bot_token:
            return
        async with pool.acquire() as conn:
            if await conn.fetchrow("SELECT 1 FROM onboarding_dm_sent WHERE team_id = $1 AND user_id = $2", team_id, user_id):
                return
        questions = await get_onboarding_top_questions(pool, tenant_id, namespace, getattr(app.state, "config", None))
        text = "👋 Hi! I'm BrainOS — your company's AI knowledge assistant.\nI noticed you just joined. Here are 5 common questions for new folks:\n\n" + "\n".join(f"• {q}" for q in questions) + "\n\nYou can ask me anything by messaging me here or @mentioning me in any channel.\nI won't message you again unless you ask something!"
        async with httpx.AsyncClient() as client:
            r = await client.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": user_id, "text": text})
        if r.is_success and r.json().get("ok"):
            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO onboarding_dm_sent (team_id, user_id, channel_id) VALUES ($1, $2, $3) ON CONFLICT (team_id, user_id) DO NOTHING", team_id, user_id, channel_id)
    except Exception:
        log.exception("Onboarding DM failed")


@router.post("/interactions")
async def slack_interactions(request: Request, x_slack_signature: str | None = Header(None)):
    body = await request.body()
    if (os.environ.get("SLACK_SKIP_SIGNATURE_VERIFICATION") or "").strip().lower() not in ("1", "true", "yes") and not _verify_slack_signature(body, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    from urllib.parse import parse_qs
    parsed = parse_qs(body.decode() if isinstance(body, bytes) else body)
    payload_str = (parsed.get("payload") or [None])[0]
    if not payload_str:
        return {}
    payload = json.loads(payload_str)
    team_id = (payload.get("team") or {}).get("id", "")
    bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if team_id:
        try:
            from app.db.connection import get_pool
            pool = await get_pool()
            if pool:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT metadata FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>$3 = $4", "slack", "connected", "team_id", team_id)
                    if row and (row.get("metadata") or {}).get("access_token"):
                        bot_token = (row["metadata"].get("access_token") or "").strip()
        except Exception:
            pass
    if payload.get("type") == "block_actions":
        resp = await handle_block_action(payload, bot_token, request.app)
        if resp and resp.get("replace_original"):
            return {"replace_original": True, "text": resp.get("text", "Done.")}
    elif payload.get("type") == "view_submission":
        resp = await handle_view_submission(payload, bot_token, request.app)
        if resp:
            return resp
    return {}


@router.post("/events")
async def slack_events(request: Request, x_slack_signature: str | None = Header(None)):
    """Slack Events API: url_verification + app_mention/message handler."""
    body = await request.body()
    data = json.loads(body.decode()) if body else {}
    # Slack's URL verification must receive the challenge back; verify signature only for real events
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}
    skip_sig = (os.environ.get("SLACK_SKIP_SIGNATURE_VERIFICATION") or "").strip().lower() in ("1", "true", "yes")
    if not skip_sig:
        secret = (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
        if secret and not _verify_slack_signature(body, x_slack_signature):
            log.warning("Slack events: invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    event = data.get("event", {})
    # Onboarding: one DM when user joins a channel
    if event.get("type") == "member_joined_channel":
        user_id = event.get("user")
        channel_id = event.get("channel")
        team_id = data.get("team_id", "")
        tenant_id = os.environ.get("SLACK_TENANT_ID", "default")
        namespace = (os.environ.get("SLACK_NAMESPACE") or "my").strip() or "my"
        bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        if team_id:
            try:
                from app.db.connection import get_pool
                pool = await get_pool()
                if pool:
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT tenant_id, metadata FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>$3 = $4",
                            "slack", "connected", "team_id", team_id,
                        )
                        if row and row.get("metadata") and (row["metadata"] or {}).get("access_token"):
                            tenant_id = row["tenant_id"] or tenant_id
                            bot_token = (row["metadata"].get("access_token") or "").strip()
            except Exception:
                pass
        if user_id and channel_id and bot_token:
            asyncio.create_task(_send_onboarding_dm(team_id, user_id, channel_id, bot_token, tenant_id, namespace, request.app))
        return {"ok": True}

    if event.get("type") in ("app_mention", "message") and not event.get("bot_id"):
        text = _strip_mention(event.get("text", "").strip())
        if not text:
            return {"ok": True}
        event_id = event.get("event_id") or event.get("event_ts") or event.get("ts") or ""
        if event_id:
            _prune_seen_event_ids()
            if event_id in _seen_event_ids:
                return {"ok": True}
            _seen_event_ids[event_id] = time.monotonic()
        team_id = data.get("team_id", "")
        tenant_id = os.environ.get("SLACK_TENANT_ID", "default")
        namespace = (os.environ.get("SLACK_NAMESPACE") or "my").strip() or "my"
        bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        if team_id:
            try:
                from app.db.connection import get_pool
                pool = await get_pool()
                if pool:
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT tenant_id, metadata FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>$3 = $4",
                            "slack", "connected", "team_id", team_id,
                        )
                    if row and row.get("metadata") and (row["metadata"] or {}).get("access_token"):
                        tenant_id = row["tenant_id"] or tenant_id
                        bot_token = (row["metadata"].get("access_token") or "").strip()
            except Exception:
                pass
        if not bot_token:
            bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        channel = event.get("channel")
        if not channel or not bot_token:
            log.warning("Slack events: missing channel or SLACK_BOT_TOKEN, cannot post reply")
            return {"ok": True}
        # Respond to Slack immediately so it doesn't retry; process and post reply in background (one reply per event).
        user_key = event.get("user")  # Slack user ID for personal profile
        asyncio.create_task(
            _process_slack_event_and_reply(request.app, channel, text, tenant_id, namespace, bot_token, user_key)
        )
        # Proactive: in-thread messages get classifier run (one offer per thread, then silence)
        thread_ts = event.get("thread_ts")
        if thread_ts and team_id:
            asyncio.create_task(
                _run_proactive_classifier(request.app, team_id, channel, thread_ts, event.get("user", ""), bot_token, tenant_id, namespace)
            )
        return {"ok": True}
    return {"ok": True}


@router.post("/slash")
async def slack_slash(request: Request):
    """Slack Slash command: POST with text=..., response_url=... (optional)."""
    form = await request.form()
    text = form.get("text", "").strip()
    response_url = form.get("response_url")
    tenant_id = os.environ.get("SLACK_TENANT_ID", "default")
    namespace = os.environ.get("SLACK_NAMESPACE", "my")
    answer, citations, _ = await _get_answer(tenant_id, namespace, text or "What can you help with?", request)
    if response_url:
        import httpx
        blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": answer}}]
        if citations:
            source_lines = "\n".join(
                f"• {c.get('document_name', 'Source')}" + (f" (p.{c.get('page')})" if c.get("page") else "")
                for c in citations[:10]
            )
            blocks.append({"type": "divider"})
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Sources:*\n{source_lines}"}})
        async with httpx.AsyncClient() as client:
            await client.post(response_url, json={"text": answer, "blocks": blocks})
        return {"response_type": "in_channel", "text": "Answer sent."}
    return {"response_type": "in_channel", "text": answer}


@router.post("/standup-trigger")
async def slack_standup_trigger(team_id: str = Query(...), channel_id: str = Query(...)):
    from app.db.connection import get_pool
    import httpx
    pool = await get_pool()
    if not pool:
        return {"ok": False, "error": "No database"}
    async with pool.acquire() as conn:
        if not await conn.fetchrow("SELECT 1 FROM standup_config WHERE team_id = $1 AND channel_id = $2", team_id, channel_id):
            return {"ok": False, "error": "Standup not configured"}
    bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if team_id:
        try:
            async with pool.acquire() as conn:
                r = await conn.fetchrow("SELECT metadata FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>$3 = $4", "slack", "connected", "team_id", team_id)
                if r and (r.get("metadata") or {}).get("access_token"):
                    bot_token = (r["metadata"].get("access_token") or "").strip()
        except Exception:
            pass
    if not bot_token:
        return {"ok": False, "error": "No bot token"}
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Good morning! Quick standup (takes 30 seconds):"}},
        {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Submit standup"}, "action_id": "brainos_standup_open", "value": "open"}]},
    ]
    async with httpx.AsyncClient() as client:
        r = await client.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": channel_id, "text": "Good morning! Quick standup.", "blocks": blocks})
    return {"ok": r.is_success and r.json().get("ok")}


@router.post("/standup-publish")
async def slack_standup_publish(team_id: str = Query(...), channel_id: str = Query(...), submission_date: str | None = Query(None)):
    from datetime import date
    from app.db.connection import get_pool
    from app.services.proactive_service import detect_standup_blockers
    import httpx
    pool = await get_pool()
    if not pool:
        return {"ok": False}
    dt = submission_date or date.today().isoformat()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, yesterday_text, today_text, blockers_text FROM standup_submissions WHERE team_id = $1 AND channel_id = $2 AND submission_date = $3", team_id, channel_id, dt)
    if not rows:
        return {"ok": True, "published": 0}
    bot_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    try:
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT metadata FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>$3 = $4", "slack", "connected", "team_id", team_id)
            if r and (r.get("metadata") or {}).get("access_token"):
                bot_token = (r["metadata"].get("access_token") or "").strip()
    except Exception:
        pass
    standups = [{"user_id": r["user_id"], "yesterday": r["yesterday_text"], "today": r["today_text"], "blockers": r["blockers_text"]} for r in rows]
    blockers_out = await detect_standup_blockers(standups, None)
    lines = [f"<@{r['user_id']}>: Yesterday: {r['yesterday_text'] or '—'}. Today: {r['today_text'] or '—'}." + (f" Blockers: {r['blockers_text']}" if r["blockers_text"] else "") for r in rows]
    text = "Team Standup — " + dt + "\n\n" + "\n".join(lines)
    if blockers_out.get("blockers"):
        text += "\n\n🚧 " + "; ".join((b.get("blocker_text") or "")[:80] for b in blockers_out["blockers"][:5])
    async with httpx.AsyncClient() as client:
        await client.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {bot_token}"}, json={"channel": channel_id, "text": text})
    return {"ok": True, "published": len(rows)}


@router.post("/reminders-run")
async def slack_reminders_run(team_id: str = Query(...)):
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"ok": False}
    return {"ok": True, "sent": 0}


@router.get("/standup-config")
async def get_standup_config(team_id: str = Query(...)):
    """List standup-configured channels for this team."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"configs": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT channel_id, hour, minute, timezone FROM standup_config WHERE team_id = $1", team_id)
    return {"configs": [{"channel_id": r["channel_id"], "hour": r["hour"], "minute": r["minute"], "timezone": r["timezone"]} for r in rows]}


@router.post("/standup-config")
async def set_standup_config(
    team_id: str = Query(...),
    channel_id: str = Query(...),
    hour: int = Query(9, ge=0, le=23),
    minute: int = Query(30, ge=0, le=59),
    timezone: str = Query("UTC"),
):
    """Configure a channel as standup channel. Cron should call standup-trigger at this time."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"ok": False}
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO standup_config (team_id, channel_id, hour, minute, timezone) VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (team_id, channel_id) DO UPDATE SET hour = $3, minute = $4, timezone = $5""",
            team_id, channel_id, hour, minute, timezone,
        )
    return {"ok": True}


@router.get("/quiet-channels")
async def get_quiet_channels(team_id: str = Query(...)):
    """List channels where BrainOS never makes proactive offers."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"channel_ids": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT channel_id FROM slack_quiet_channels WHERE team_id = $1", team_id)
    return {"channel_ids": [r["channel_id"] for r in rows]}


@router.post("/quiet-channels")
async def set_quiet_channel(team_id: str = Query(...), channel_id: str = Query(...)):
    """Mark channel as quiet (no proactive offers)."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"ok": False}
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO slack_quiet_channels (team_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", team_id, channel_id)
    return {"ok": True}


@router.delete("/quiet-channels")
async def unset_quiet_channel(team_id: str = Query(...), channel_id: str = Query(...)):
    from app.db.connection import get_pool
    pool = await get_pool()
    if not pool:
        return {"ok": False}
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM slack_quiet_channels WHERE team_id = $1 AND channel_id = $2", team_id, channel_id)
    return {"ok": True}
