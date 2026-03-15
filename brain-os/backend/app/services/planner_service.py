"""Agentic goal planner: convert user goal into structured task graph. LLM-driven."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_llm_provider


def _load_planner_prompts(config: dict[str, Any]) -> dict[str, Any]:
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "planner.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def plan_goal(goal: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Use LLM to convert goal into task graph. Returns { "tasks": [ { "action", "dependencies" }, ... ] }.
    """
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_planner_prompts(config)
    spec = prompts.get("plan_goal") or {}
    system = spec.get("system", "Output JSON with a 'tasks' array. Each task: action, dependencies (array of indices).")
    user_tpl = spec.get("user_template", "Goal: {{ goal }}\n\nJSON:")
    user_msg = user_tpl.replace("{{ goal }}", goal[:2000])
    raw = await llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=800,
    )
    tasks = []
    if raw:
        m = re.search(r"\{[\s\S]*\"tasks\"[\s\S]*\}", raw)
        if m:
            try:
                data = json.loads(m.group(0))
                tasks = data.get("tasks") or []
                for i, t in enumerate(tasks):
                    if not isinstance(t, dict):
                        tasks[i] = {"action": str(t), "dependencies": []}
                    else:
                        tasks[i] = {"action": t.get("action") or "unknown", "dependencies": t.get("dependencies") or []}
            except json.JSONDecodeError:
                tasks = [{"action": goal[:200], "dependencies": []}]
    if not tasks:
        tasks = [{"action": f"Achieve goal: {goal[:200]}", "dependencies": []}]
    return {"tasks": tasks, "goal": goal}
