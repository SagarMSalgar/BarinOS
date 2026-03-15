"""Proactive Assistant: classifier, offer tracking, flows. One offer per thread, then silence."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider

CONFIDENCE_THRESHOLD = 0.85
PLANNING_SIGNALS_MIN = 3
FEATURE_PLANNER = "project_planner"
FEATURE_MEETING = "meeting_summary"
FEATURE_REQUIREMENTS = "requirements_analyser"
FEATURE_ONBOARDING = "onboarding_buddy"


def _load_proactive_prompts(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.core.config import load_config
    config = config or load_config()
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "proactive.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def classify_conversation(conversation_text: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lightweight LLM classifier. Returns planning_signals, meeting_signals, requirements_signals, confidence."""
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_proactive_prompts(config)
    spec = prompts.get("classify_conversation") or {}
    sys = spec.get("system", "Classify the conversation. Reply with JSON: planning_signals, meeting_signals, requirements_signals, confidence.")
    user_tpl = spec.get("user_template", "Conversation:\n{{ conversation }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ conversation }}", (conversation_text or "")[:4000])
    out: dict[str, Any] = {
        "planning_signals": 0,
        "meeting_signals": 0,
        "requirements_signals": 0,
        "confidence": 0.0,
    }
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=200,
        )
        if not raw:
            return out
        text = raw.strip()
        if "```" in text:
            text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
            text = re.sub(r"\s*```.*$", "", text).strip()
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            out["planning_signals"] = int(data.get("planning_signals", 0))
            out["meeting_signals"] = int(data.get("meeting_signals", 0))
            out["requirements_signals"] = int(data.get("requirements_signals", 0))
            out["confidence"] = float(data.get("confidence", 0))
    except Exception:
        pass
    return out


async def offer_already_made(pool, team_id: str, channel_id: str, thread_ts: str, feature: str) -> bool:
    if not pool:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT 1 FROM proactive_offer_made
               WHERE team_id = $1 AND channel_id = $2 AND thread_ts = $3 AND feature = $4""",
            team_id, channel_id, thread_ts, feature,
        )
    return row is not None


async def record_offer_made(pool, team_id: str, channel_id: str, thread_ts: str, feature: str) -> None:
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO proactive_offer_made (team_id, channel_id, thread_ts, feature)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (team_id, channel_id, thread_ts, feature) DO NOTHING""",
            team_id, channel_id, thread_ts, feature,
        )


async def user_opted_out(pool, team_id: str, user_id: str, feature: str) -> bool:
    if not pool:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT 1 FROM proactive_opt_out
               WHERE team_id = $1 AND user_id = $2 AND feature = $3""",
            team_id, user_id, feature,
        )
    return row is not None


async def record_opt_out(pool, team_id: str, user_id: str, feature: str) -> None:
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO proactive_opt_out (team_id, user_id, feature)
               VALUES ($1, $2, $3)
               ON CONFLICT (team_id, user_id, feature) DO NOTHING""",
            team_id, user_id, feature,
        )


async def is_quiet_channel(pool, team_id: str, channel_id: str) -> bool:
    if not pool:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM slack_quiet_channels WHERE team_id = $1 AND channel_id = $2",
            team_id, channel_id,
        )
    return row is not None


async def get_flow(pool, flow_id: str) -> dict[str, Any] | None:
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, team_id, channel_id, thread_ts, feature, state, payload FROM proactive_flows WHERE id = $1",
            flow_id,
        )
    if not row:
        return None
    return {
        "id": row["id"],
        "team_id": row["team_id"],
        "channel_id": row["channel_id"],
        "thread_ts": row["thread_ts"],
        "feature": row["feature"],
        "state": row["state"],
        "payload": dict(row["payload"]) if row.get("payload") else {},
    }


async def save_flow(pool, flow_id: str, team_id: str, channel_id: str, thread_ts: str, feature: str, state: str, payload: dict[str, Any]) -> None:
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO proactive_flows (id, team_id, channel_id, thread_ts, feature, state, payload, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
               ON CONFLICT (id) DO UPDATE SET state = $6, payload = $7::jsonb, updated_at = NOW()""",
            flow_id, team_id, channel_id, thread_ts, feature, state, json.dumps(payload or {}),
        )


async def generate_project_plan(raw_input: str, kb_context: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_proactive_prompts(config)
    spec = prompts.get("project_plan_prompt") or {}
    sys = spec.get("system", "Output a JSON project plan.")
    user_content = f"Raw input from team:\n{raw_input[:12000]}"
    if kb_context:
        user_content += f"\n\nRelevant context from knowledge base:\n{kb_context[:4000]}"
    user_content += "\n\nOutput only valid JSON."
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_content}],
            stream=False,
            max_tokens=3000,
        )
        if not raw:
            return {}
        text = raw.strip()
        if "```" in text:
            text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
            text = re.sub(r"\s*```.*$", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}


async def analyse_requirements(doc_text: str, kb_context: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_proactive_prompts(config)
    spec = prompts.get("requirements_analysis_prompt") or {}
    sys = spec.get("system", "Analyse requirements. Output JSON.")
    user_content = f"Document text:\n{doc_text[:12000]}"
    if kb_context:
        user_content += f"\n\nKnowledge base context:\n{kb_context[:3000]}"
    user_content += "\n\nOutput only valid JSON."
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_content}],
            stream=False,
            max_tokens=2500,
        )
        if not raw:
            return {}
        text = raw.strip()
        if "```" in text:
            text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
            text = re.sub(r"\s*```.*$", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}


async def extract_meeting_summary(meeting_text: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract decisions, action items, open questions from meeting notes/transcript."""
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_proactive_prompts(config)
    spec = prompts.get("meeting_summary_prompt") or {}
    sys = spec.get("system", "Extract decisions, action items, open questions. Output JSON.")
    user_tpl = spec.get("user_template", "Meeting notes:\n{{ meeting_text }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ meeting_text }}", (meeting_text or "")[:12000])
    out: dict[str, Any] = {"decisions": [], "action_items": [], "open_questions": []}
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=2000,
        )
        if not raw:
            return out
        text = raw.strip()
        if "```" in text:
            text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
            text = re.sub(r"\s*```.*$", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            data = json.loads(m.group(0))
            out["decisions"] = data.get("decisions") or []
            out["action_items"] = data.get("action_items") or []
            out["open_questions"] = data.get("open_questions") or []
    except Exception:
        pass
    return out


def plan_preview_text(plan: dict[str, Any], project_name: str) -> str:
    """Format plan for Slack preview block."""
    deadline = plan.get("deadline") or "TBD"
    phases = plan.get("phases") or []
    phase_names = " → ".join(p.get("name", "") for p in phases) or "—"
    total = sum(len(p.get("tasks") or []) for p in phases)
    risks = plan.get("risks") or []
    risk_line = "; ".join((r.get("description") or "")[:80] for r in risks[:2]) if risks else "None"
    return (
        f"*Project:* {project_name}\n"
        f"*Deadline:* {deadline}\n"
        f"*Phases:* {phase_names}\n"
        f"*Total tasks:* {total}\n"
        f"*Risk:* {risk_line}"
    )


async def detect_standup_blockers(standups_json: list[dict], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Identify blockers from standup entries and suggest helpers."""
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_proactive_prompts(config)
    spec = prompts.get("standup_blockers_prompt") or {}
    sys = spec.get("system", "Identify blockers. Output JSON: blockers list.")
    user_tpl = spec.get("user_template", "Standups:\n{{ standups_json }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ standups_json }}", json.dumps(standups_json)[:6000])
    out: dict[str, Any] = {"blockers": []}
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=500,
        )
        if not raw:
            return out
        text = raw.strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            data = json.loads(m.group(0))
            out["blockers"] = data.get("blockers") or []
    except Exception:
        pass
    return out


async def get_onboarding_top_questions(pool, tenant_id: str, namespace: str, config: dict[str, Any] | None = None) -> list[str]:
    """Return 5 questions most relevant for new employees (from unanswered_questions or LLM default)."""
    defaults = [
        "How does the reimbursement process work?",
        "Where do I find the company's style guide?",
        "Who do I contact for IT issues?",
        "What's the process for booking time off?",
        "Where are the engineering docs?",
    ]
    if not pool:
        return defaults
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT question FROM unanswered_questions WHERE tenant_id = $1 AND namespace = $2 ORDER BY count DESC, updated_at DESC LIMIT 30",
                tenant_id, namespace,
            )
        if not rows:
            return defaults
        questions = [r["question"] for r in rows]
        config = config or load_config()
        llm = get_llm_provider(config)
        prompts = _load_proactive_prompts(config)
        spec = prompts.get("onboarding_top_questions_prompt") or {}
        sys = spec.get("system", "Pick 5 questions most relevant for a new employee. Output JSON array of 5 strings.")
        user_tpl = spec.get("user_template", "Questions:\n{{ questions_list }}\n\nJSON array of 5 strings:")
        user_msg = user_tpl.replace("{{ questions_list }}", "\n".join(questions[:30]))
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=300,
        )
        if not raw:
            return defaults
        text = raw.strip()
        m = re.search(r"\[[\s\S]*?\]", text)
        if m:
            arr = json.loads(m.group(0))
            if isinstance(arr, list) and len(arr) >= 5:
                return [str(x).strip() for x in arr[:5] if str(x).strip()]
    except Exception:
        pass
    return defaults


def new_flow_id() -> str:
    return str(uuid.uuid4())[:12]
