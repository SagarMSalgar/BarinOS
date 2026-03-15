"""Slack proactive flows: handle button clicks and modal submissions. One offer per thread, then silence."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.services import proactive_service as pro
from app.services.content_extraction import extract_from_slack_file, fetch_url_content
from app.services.google_sheets_service import (
    create_project_plan_spreadsheet,
    share_spreadsheet,
    create_action_items_sheet,
    create_clarification_sheet,
)

log = logging.getLogger(__name__)

FEATURE_PLANNER = pro.FEATURE_PLANNER
FEATURE_MEETING = pro.FEATURE_MEETING
FEATURE_REQUIREMENTS = pro.FEATURE_REQUIREMENTS


def _blocks_plan_offer() -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "🧠 BrainOS noticed you're planning a project.\nWant me to turn this into a structured plan with tasks, owners, and deadlines — and create a Google Sheet you can share with your team?"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Yes, create the plan"}, "action_id": "brainos_planner_yes", "value": "yes"},
            {"type": "button", "text": {"type": "plain_text", "text": "No thanks"}, "action_id": "brainos_planner_no", "value": "no"},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://your-brainos/settings|Turn off this feature>"}]},
    ]


def _blocks_meeting_offer() -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "🧠 Looks like meeting notes. Want me to extract action items, decisions made, and open questions — and create a task sheet from the action items?"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Yes, extract action items"}, "action_id": "brainos_meeting_yes", "value": "yes"},
            {"type": "button", "text": {"type": "plain_text", "text": "No thanks"}, "action_id": "brainos_meeting_no", "value": "no"},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://your-brainos/settings|Turn off this feature>"}]},
    ]


def _blocks_requirements_offer() -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "🧠 I see a requirements document. Want me to analyse it and tell you:\n• What's clear vs ambiguous\n• What seems to be missing\n• Estimated complexity and effort\n• Suggested questions to ask before starting"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Yes, analyse it"}, "action_id": "brainos_requirements_yes", "value": "yes"},
            {"type": "button", "text": {"type": "plain_text", "text": "No thanks"}, "action_id": "brainos_requirements_no", "value": "no"},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "<https://your-brainos/settings|Turn off this feature>"}]},
    ]


async def handle_block_action(payload: dict, bot_token: str, app: Any) -> dict | None:
    """Handle button clicks. Returns response payload for Slack (to update message or ack)."""
    pool = None
    try:
        from app.db.connection import get_pool
        pool = await get_pool()
    except Exception:
        pass

    action = payload.get("actions", [{}])[0] if payload.get("actions") else {}
    action_id = action.get("action_id", "")
    user_id = (payload.get("user", {}) or {}).get("id", "")
    channel = (payload.get("channel", {}) or {}).get("id", "")
    thread_ts = (payload.get("message", {}) or {}).get("thread_ts") or (payload.get("message") or {}).get("ts")
    team_id = payload.get("team", {}).get("id", "")
    response_url = payload.get("response_url")

    if not channel or not bot_token:
        return {}

    # Resolve tenant_id and namespace from team_id
    tenant_id = "default"
    try:
        if pool and team_id:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT tenant_id FROM connected_tools WHERE provider = $1 AND status = $2 AND metadata->>'team_id' = $3",
                    "slack", "connected", team_id,
                )
                if row:
                    tenant_id = row["tenant_id"] or tenant_id
    except Exception:
        pass
    namespace = "my"

    # No thanks / opt out
    if action_id == "brainos_planner_no":
        if pool:
            await pro.record_opt_out(pool, team_id, user_id, FEATURE_PLANNER)
        return {"replace_original": True, "text": "No problem. You won't see this again for this thread."}
    if action_id == "brainos_meeting_no":
        if pool:
            await pro.record_opt_out(pool, team_id, user_id, FEATURE_MEETING)
        return {"replace_original": True, "text": "No problem."}
    if action_id == "brainos_requirements_no":
        if pool:
            await pro.record_opt_out(pool, team_id, user_id, FEATURE_REQUIREMENTS)
        return {"replace_original": True, "text": "No problem."}

    # Standup: open modal
    if action_id == "brainos_standup_open":
        trigger_id = payload.get("trigger_id")
        if trigger_id and bot_token:
            channel_id = (payload.get("channel") or {}).get("id", "")
            modal = {
                "type": "modal",
                "callback_id": "brainos_standup_modal",
                "private_metadata": json.dumps({"channel_id": channel_id}),
                "title": {"type": "plain_text", "text": "Quick standup"},
                "submit": {"type": "plain_text", "text": "Submit standup"},
                "close": {"type": "plain_text", "text": "Skip today"},
                "blocks": [
                    {"type": "input", "block_id": "yesterday", "label": {"type": "plain_text", "text": "Yesterday"}, "element": {"type": "plain_text_input", "action_id": "yesterday", "multiline": True}},
                    {"type": "input", "block_id": "today", "label": {"type": "plain_text", "text": "Today"}, "element": {"type": "plain_text_input", "action_id": "today", "multiline": True}},
                    {"type": "input", "block_id": "blockers", "optional": True, "label": {"type": "plain_text", "text": "Blockers"}, "element": {"type": "plain_text_input", "action_id": "blockers", "multiline": True}},
                ],
            }
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/views.open",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"trigger_id": trigger_id, "view": modal},
                )
        return {"replace_original": True, "text": "Opening standup…"}

    # Yes — start flow
    if action_id == "brainos_planner_yes":
        flow_id = pro.new_flow_id()
        if pool:
            await pro.save_flow(pool, flow_id, team_id, channel, thread_ts or payload.get("message", {}).get("ts", ""), FEATURE_PLANNER, "collecting_input", {"user_id": user_id})
        msg = (
            "Perfect! Share everything you have — paste text, upload a PDF, DOCX, screenshot, or just describe it in your own words. "
            "The more detail the better. I'll handle the rest.\nWhen you're done sharing, click the button below."
        )
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": msg}},
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "I'm done, create the plan"}, "action_id": "brainos_plan_done", "value": flow_id}]},
        ]
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "thread_ts": thread_ts, "text": msg, "blocks": blocks},
            )
        return {"replace_original": True, "text": "Got it! Share your materials in the thread, then click “I'm done, create the plan” when ready."}

    if action_id == "brainos_plan_done":
        flow_id = (action.get("value") or "").strip()
        if not flow_id or not pool:
            return {}
        flow = await pro.get_flow(pool, flow_id)
        if not flow or flow.get("state") != "collecting_input":
            return {}
        # Collect thread messages and files, extract content, run KB + plan, post preview
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://slack.com/api/conversations.replies",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"channel": channel, "ts": flow["thread_ts"], "limit": 50},
            )
        replies = (r.json().get("messages") or []) if r.is_success else []
        config = getattr(app.state, "config", None)
        if not config:
            from app.core.config import load_config
            config = load_config()

        collected_text = []
        for msg in replies:
            if msg.get("bot_id"):
                continue
            text = (msg.get("text") or "").strip()
            if text:
                collected_text.append(text)
            for f in (msg.get("files") or []):
                url = f.get("url_private") or f.get("url_private_download")
                if url:
                    try:
                        ext = (f.get("filetype") or f.get("name") or "").lower()
                        t = await extract_from_slack_file(url, ext, bot_token, config)
                        if t:
                            collected_text.append(f"[From {f.get('name', 'file')}]\n{t}")
                    except Exception as e:
                        log.warning("File extract failed: %s", e)
        raw_input = "\n\n".join(collected_text)
        if not raw_input.strip():
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "thread_ts": flow["thread_ts"], "text": "I didn’t find any text or files in the thread. Paste a description or attach a document, then click “I'm done, create the plan” again."},
                )
            return {"replace_original": True, "text": "Please add some content first."}

        # KB context
        kb_context = ""
        try:
            vs = getattr(app.state, "vector_store", None)
            if vs and hasattr(vs, "search"):
                from app.providers import get_embedding_provider
                emb = get_embedding_provider(config)
                q = "project plan tasks phases milestones deliverables"
                q_vec = (await emb.embed([q]))[0]
                results = await vs.search(namespace, q_vec, top_k=5)
                if results:
                    kb_context = "\n".join((getattr(r, "content", None) or (r.get("content") if isinstance(r, dict) else "") or "")[:800] for r in results[:5])
        except Exception:
            pass

        plan = await pro.generate_project_plan(raw_input, kb_context or None, config)
        if not plan:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "thread_ts": flow["thread_ts"], "text": "I couldn’t generate a plan from that input. Try adding more detail (phases, tasks, or a deadline) and try again."},
                )
            return {"replace_original": True, "text": "Couldn’t generate plan."}

        project_name = (plan.get("project_name") or "Project").strip()
        preview = pro.plan_preview_text(plan, project_name)
        await pro.save_flow(pool, flow_id, team_id, channel, flow["thread_ts"], FEATURE_PLANNER, "preview", {**flow.get("payload", {}), "plan": plan, "project_name": project_name})

        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "Here's what I understood. Does this look right?\n\n" + preview}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Looks good, create the sheet"}, "action_id": "brainos_plan_approve", "value": flow_id},
                {"type": "button", "text": {"type": "plain_text", "text": "Let me adjust something"}, "action_id": "brainos_plan_adjust", "value": flow_id},
            ]},
        ]
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "thread_ts": flow["thread_ts"], "text": "Here's what I understood. Does this look right?\n\n" + preview, "blocks": blocks},
            )
        return {"replace_original": True, "text": "Plan ready for your review."}

    if action_id == "brainos_plan_approve":
        flow_id = (action.get("value") or "").strip()
        if not flow_id or not pool:
            return {}
        flow = await pro.get_flow(pool, flow_id)
        if not flow or flow.get("state") != "preview":
            return {}
        plan = flow.get("payload", {}).get("plan") or {}
        project_name = flow.get("payload", {}).get("project_name") or "Project"

        # Google token: from connected_tools for tenant (google_sheets or drive)
        google_token = None
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT metadata FROM connected_tools WHERE tenant_id = $1 AND provider IN ('google_sheets','drive','google') AND status = 'connected'",
                    tenant_id,
                )
                if row and row.get("metadata"):
                    google_token = (row["metadata"] or {}).get("access_token")
        except Exception:
            pass
        if not google_token:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel, "thread_ts": flow["thread_ts"],
                        "text": "Google Sheets isn’t connected yet. Connect Google in BrainOS Settings (Sources) to create the sheet.",
                    },
                )
            return {"replace_original": True, "text": "Connect Google first."}

        try:
            result = await create_project_plan_spreadsheet(
                google_token, plan, project_name, tenant_id=tenant_id, team_id=team_id,
            )
        except Exception as e:
            log.exception("Sheets create failed")
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "thread_ts": flow["thread_ts"], "text": f"Couldn’t create the sheet: {str(e)[:200]}"},
                )
            return {"replace_original": True, "text": "Error creating sheet."}

        sheet_id = result["sheet_id"]
        sheet_url = result["sheet_url"]
        total_tasks = result.get("total_tasks", 0)
        # Store for reminders
        import uuid
        rec_id = str(uuid.uuid4())[:12]
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO brainos_project_sheets (id, tenant_id, team_id, sheet_id, sheet_url, project_name, tasks_json, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())""",
                    rec_id, tenant_id, team_id, sheet_id, sheet_url, project_name, json.dumps(result.get("tasks_for_reminders", [])),
                )
        except Exception:
            pass

        risk_line = ""
        if (plan.get("risks") or []):
            risk_line = "\n⚠️ Risk flagged: " + (plan["risks"][0].get("description") or "")[:120]
        msg = (
            f"✅ Your project plan is ready!\n"
            f"📊 <{sheet_url}|{project_name} — Project Plan>\n"
            f"{total_tasks} tasks across phases. {risk_line}\n\n"
            f"Who should I share this with? Reply with email addresses or @mention teammates and I'll share it. Or say *Share with everyone in this thread* to share with all participants."
        )
        await pro.save_flow(pool, flow_id, team_id, channel, flow["thread_ts"], FEATURE_PLANNER, "sharing", {"sheet_id": sheet_id, "sheet_url": sheet_url, "project_name": project_name})
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "thread_ts": flow["thread_ts"], "text": msg, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": msg}}]},
            )
        return {"replace_original": True, "text": "Sheet created. Reply in thread to share."}

    # Meeting: Yes -> extract and post
    if action_id == "brainos_meeting_yes":
        thread_ts = thread_ts or (payload.get("message") or {}).get("ts")
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://slack.com/api/conversations.replies",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"channel": channel, "ts": thread_ts, "limit": 30},
            )
        replies = (r.json().get("messages") or []) if r.is_success else []
        meeting_text = "\n\n".join((m.get("text") or "").strip() for m in replies if not m.get("bot_id"))
        for msg in replies:
            for f in (msg.get("files") or []):
                url = f.get("url_private") or f.get("url_private_download")
                if url:
                    try:
                        t = await extract_from_slack_file(url, f.get("filetype") or "", bot_token, getattr(app.state, "config", None))
                        if t:
                            meeting_text += "\n\n[File]\n" + t
                    except Exception:
                        pass
        config = getattr(app.state, "config", None) or __import__("app.core.config", fromlist=["load_config"]).load_config()
        summary = await pro.extract_meeting_summary(meeting_text, config)
        decisions = summary.get("decisions") or []
        action_items = summary.get("action_items") or []
        open_q = summary.get("open_questions") or []
        text = "*Decisions made:*\n" + ("\n".join(f"• {d}" for d in decisions) if decisions else "None") + "\n\n*Action items:*\n"
        for a in action_items:
            text += f"• {(a.get('what') or '')[:200]}"
            if a.get("owner_mentioned"):
                text += f" — {a['owner_mentioned']}"
            if a.get("due"):
                text += f" (by {a['due']})"
            text += "\n"
        if not action_items:
            text += "None\n"
        text += "\n*Open questions:*\n" + ("\n".join(f"• {q}" for q in open_q) if open_q else "None")
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
        # One-click create task sheet if we have action items and Google connected
        google_token = None
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT metadata FROM connected_tools WHERE tenant_id = $1 AND provider IN ('google_sheets','drive','google') AND status = 'connected'", tenant_id)
                    if row and (row.get("metadata") or {}).get("access_token"):
                        google_token = row["metadata"]["access_token"]
            except Exception:
                pass
        if action_items and google_token:
            try:
                sheet_result = await create_action_items_sheet(google_token, action_items, "Meeting action items")
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"📋 <{sheet_result['sheet_url']}|Create task sheet> — action items as a Google Sheet."}})
            except Exception:
                pass
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "thread_ts": thread_ts, "text": text, "blocks": blocks},
            )
        return {"replace_original": True, "text": "Summary posted."}

    # Requirements: Yes -> analyse and post
    if action_id == "brainos_requirements_yes":
        thread_ts = thread_ts or (payload.get("message") or {}).get("ts")
        doc_text = ""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://slack.com/api/conversations.replies",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"channel": channel, "ts": thread_ts, "limit": 30},
            )
        replies = (r.json().get("messages") or []) if r.is_success else []
        for msg in replies:
            for f in (msg.get("files") or []):
                url = f.get("url_private") or f.get("url_private_download")
                if url:
                    try:
                        doc_text += "\n\n" + await extract_from_slack_file(url, f.get("filetype") or "", bot_token, getattr(app.state, "config", None))
                    except Exception:
                        pass
            if (msg.get("text") or "").strip() and not msg.get("bot_id"):
                doc_text += "\n\n" + (msg.get("text") or "").strip()
        if not doc_text.strip():
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "thread_ts": thread_ts, "text": "I couldn’t find a document in this thread. Upload a PDF/DOCX or paste the requirements, then try again."},
                )
            return {"replace_original": True, "text": "No document found."}
        config = getattr(app.state, "config", None) or __import__("app.core.config", fromlist=["load_config"]).load_config()
        vs = getattr(app.state, "vector_store", None)
        kb_context = ""
        if vs and hasattr(vs, "search"):
            try:
                from app.providers import get_embedding_provider
                emb = get_embedding_provider(config)
                q_vec = (await emb.embed(["requirements template best practices"]))[0]
                results = await vs.search(namespace, q_vec, top_k=3)
                kb_context = "\n".join((getattr(r, "content", None) or (r.get("content") if isinstance(r, dict) else "") or "")[:500] for r in (results or []))
            except Exception:
                pass
        analysis = await pro.analyse_requirements(doc_text, kb_context or None, config)
        clarity = analysis.get("clarity") or []
        missing = analysis.get("missing_sections") or []
        effort = analysis.get("effort_estimate") or "Not estimated"
        questions = analysis.get("questions_to_ask") or []
        text = "*Clarity:*\n" + "\n".join(f"• {c.get('requirement_or_section', '')[:100]} — {c.get('classification', '')}" for c in clarity[:15])
        text += "\n\n*Missing sections:*\n" + ("\n".join(f"• {m}" for m in missing) if missing else "None")
        text += f"\n\n*Rough effort:* {effort}"
        text += "\n\n*Questions to ask:*\n" + "\n".join(f"• {q}" for q in questions[:10])
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
        google_token = None
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT metadata FROM connected_tools WHERE tenant_id = $1 AND provider IN ('google_sheets','drive','google') AND status = 'connected'", tenant_id)
                    if row and (row.get("metadata") or {}).get("access_token"):
                        google_token = row["metadata"]["access_token"]
            except Exception:
                pass
        if google_token and clarity:
            try:
                sheet_result = await create_clarification_sheet(google_token, clarity, "Requirements clarification")
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"📋 <{sheet_result['sheet_url']}|Create clarification sheet>"}})
            except Exception:
                pass
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "thread_ts": thread_ts, "text": text, "blocks": blocks},
            )
        return {"replace_original": True, "text": "Analysis posted."}

    return {}


async def handle_view_submission(payload: dict, bot_token: str, app: Any) -> dict | None:
    """Handle modal submit (e.g. standup). Return response to Slack."""
    view = payload.get("view") or {}
    callback_id = view.get("callback_id", "")
    if callback_id == "brainos_standup_modal":
        user_id = (payload.get("user") or {}).get("id", "")
        team_id = (payload.get("team") or {}).get("id", "")
        values = view.get("state", {}).get("values", {})
        yesterday = (values.get("yesterday") or {}).get("yesterday") or {}
        today = (values.get("today") or {}).get("today") or {}
        blockers = (values.get("blockers") or {}).get("blockers") or {}
        yesterday_text = (yesterday.get("value") or "").strip()[:1000]
        today_text = (today.get("value") or "").strip()[:1000]
        blockers_text = (blockers.get("value") or "").strip()[:500]
        from datetime import date
        from app.db.connection import get_pool
        pool = await get_pool()
        if pool and team_id and user_id:
            private_meta = view.get("private_metadata") or "{}"
            try:
                meta = json.loads(private_meta)
                channel_id = meta.get("channel_id", "")
            except Exception:
                channel_id = ""
            if channel_id:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO standup_submissions (team_id, channel_id, user_id, submission_date, yesterday_text, today_text, blockers_text)
                           VALUES ($1, $2, $3, $4, $5, $6, $7)
                           ON CONFLICT (team_id, channel_id, user_id, submission_date) DO UPDATE
                           SET yesterday_text = $5, today_text = $6, blockers_text = $7, submitted_at = NOW()""",
                        team_id, channel_id, user_id, date.today(), yesterday_text, today_text, blockers_text,
                    )
        return {"response_action": "clear"}  # close modal
    return {}
