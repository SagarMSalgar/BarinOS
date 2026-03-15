"""ZAYA Web Application Support: app-type-specific intelligence from knowledge base."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_embedding_provider, get_llm_provider

APP_TYPES = (
    "zendesk",
    "freshdesk",
    "salesforce",
    "hubspot",
    "jira",
    "linear",
    "notion",
    "confluence",
    "hr",
    "accounting",
    "recruitment",
    "custom",
)


def _load_web_app_prompts(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "web_app.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _excerpts_from_hits(hits: list) -> str:
    out = []
    for i, h in enumerate(hits, 1):
        name = getattr(h.meta, "document_name", None) or (h.meta if isinstance(h.meta, dict) else {}).get("document_name", "Source")
        page = getattr(h.meta, "page", None) or (h.meta if isinstance(h.meta, dict) else {}).get("page")
        content = getattr(h, "content", None) or (h if isinstance(h, dict) else {}).get("content", "")
        line = f"[{i}] {name}"
        if page is not None:
            line += f" (page {page})"
        line += f"\n{content[:2000]}"
        out.append(line)
    return "\n\n---\n\n".join(out)


def _parse_json_from_llm(text: str) -> dict:
    text = (text or "").strip()
    if "```" in text:
        text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
        text = re.sub(r"\s*```.*$", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _app_prompt_key(app_type: str) -> str:
    if app_type in ("zendesk", "freshdesk"):
        return "support_intelligence"
    if app_type in ("salesforce", "hubspot"):
        return "crm_intelligence"
    if app_type in ("jira", "linear"):
        return "jira_intelligence"
    if app_type in ("notion", "confluence"):
        return "notion_intelligence"
    if app_type == "hr":
        return "hr_intelligence"
    if app_type == "accounting":
        return "accounting_intelligence"
    if app_type == "recruitment":
        return "recruitment_intelligence"
    return "custom_intelligence"


def _build_context_text(context: dict[str, Any]) -> str:
    parts = []
    for k, v in (context or {}).items():
        if v is None or v == "":
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)[:2000]
        parts.append(f"{k}: {v}")
    return "\n".join(parts)[:15000]


async def web_app_intelligence(
    app_type: str,
    context: dict[str, Any],
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return app-type-specific intelligence (policies, similar items, suggestions)
    for the given context. Used by the embeddable ZAYA widget.
    """
    config = config or load_config()
    app_type = (app_type or "custom").lower().strip()
    if app_type not in APP_TYPES:
        app_type = "custom"

    context_text = _build_context_text(context)
    if not context_text.strip():
        context_text = "No context provided."

    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_web_app_prompts(config)
    key = _app_prompt_key(app_type)
    spec = prompts.get(key) or prompts.get("custom_intelligence") or {}
    system = spec.get("system", "Output JSON with relevant_docs, key_facts, suggested_actions.")
    user_tpl = spec.get("user_template", "CONTEXT:\n{{ context_text }}\n\nEXCERPTS:\n{{ excerpts }}\n\nJSON only.")

    query = f"{app_type} {context_text}"[:4000]
    q_vec = (await emb.embed([query]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=15)
    excerpts = _excerpts_from_hits(hits) if hits else "No relevant documents in knowledge base."

    replacements = {
        "context_text": context_text,
        "excerpts": excerpts[:12000],
        "ticket_subject": context.get("ticket_subject") or context.get("subject") or "",
        "ticket_body": context.get("ticket_body") or context.get("body") or context.get("description") or "",
        "customer_name": context.get("customer_name") or "",
        "customer_ref": context.get("customer_ref") or context.get("order_id") or "",
        "deal_name": context.get("deal_name") or context.get("account_name") or "",
        "deal_value": context.get("deal_value") or "",
        "deal_stage": context.get("deal_stage") or "",
        "issue_title": context.get("issue_title") or context.get("title") or "",
        "issue_description": context.get("issue_description") or context.get("description") or "",
        "issue_status": context.get("issue_status") or "",
        "issue_priority": context.get("issue_priority") or "",
        "page_content": context.get("page_content") or context_text[:5000],
        "form_type": context.get("form_type") or "",
        "candidate_name": context.get("candidate_name") or "",
        "role_name": context.get("role_name") or "",
        "app_type": app_type,
    }
    user_msg = user_tpl
    for k, v in replacements.items():
        user_msg = user_msg.replace("{{ " + k + " }}", str(v))

    raw = await llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=2500,
    )
    out = _parse_json_from_llm(raw or "")
    out["app_type"] = app_type
    out["raw_context_preview"] = context_text[:500]
    return out


async def web_app_chat(
    app_type: str,
    context: dict[str, Any],
    question: str,
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Answer a single question in the context of the current app view (for "Ask ZAYA" in widget)."""
    config = config or load_config()
    context_text = _build_context_text(context)
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    q_vec = (await emb.embed([(question + " " + context_text)[:4000]]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=8)
    excerpts = _excerpts_from_hits(hits) if hits else "No relevant documents."
    sys = "Answer the user's question using only the provided knowledge base excerpts. Be concise. Cite document names when relevant."
    user_msg = f"Context in app:\n{context_text[:1500]}\n\nKnowledge:\n{excerpts[:8000]}\n\nQuestion: {question}\n\nAnswer:"
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=1000,
    )
    return {"answer": (raw or "").strip(), "citations": []}
