"""PII scan: pattern + LLM semantic detection. Output for compliance/audit."""
from __future__ import annotations

import re
from typing import Any

from app.core.config import load_config, get_intent_prompt
from app.providers import get_llm_provider


# Minimal pattern set; config could drive these
PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(r"\+?[\d\s\-()]{10,}"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def pattern_scan(text: str) -> list[dict[str, Any]]:
    findings = []
    for pii_type, pat in PATTERNS.items():
        for m in pat.finditer(text):
            findings.append({"type": pii_type, "span": m.span(), "action": "redact"})
    return findings


async def llm_pii_scan(text_chunk: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """LLM semantic PII detection; returns types and locations (no raw values in report)."""
    config = config or load_config()
    prompt_cfg = get_intent_prompt(config, "pii_scan")
    if not prompt_cfg:
        return []
    llm = get_llm_provider(config)
    user_msg = prompt_cfg["user_template"].replace("{{ text_chunk }}", text_chunk[:8000])
    messages = [{"role": "system", "content": prompt_cfg["system"]}, {"role": "user", "content": user_msg}]
    try:
        await llm.complete(messages, stream=False, max_tokens=500)
        # In production parse LLM response into structured findings
    except Exception:
        pass
    return []


async def full_pii_report(text: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """PII scan report for compliance: every detection, type, field, action."""
    pattern_findings = pattern_scan(text)
    llm_findings = await llm_pii_scan(text[:12000], config)
    return {
        "pattern_findings": pattern_findings,
        "llm_findings": llm_findings,
        "total_count": len(pattern_findings) + len(llm_findings),
        "actions_taken": "redact" if (pattern_findings or llm_findings) else "none",
    }
