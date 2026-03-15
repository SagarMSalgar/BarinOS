"""Browser extension APIs: compare selected text vs KB, fact-check, position, email analyze, contract review, research synthesis, form suggest."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_config
from app.providers import get_embedding_provider, get_llm_provider


def _load_extension_prompts(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    config_dir = Path(config.get("_config_dir", Path(__file__).parent.parent.parent / "config"))
    path = config_dir / "prompts" / "extension.yaml"
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
        line += f"\n{content[:1500]}"
        out.append(line)
    return "\n\n---\n\n".join(out)


def _parse_json_from_llm(text: str) -> dict:
    text = (text or "").strip()
    if "```" in text:
        text = re.sub(r"^.*?```(?:json)?\s*", "", text).strip()
        text = re.sub(r"\s*```.*$", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    return {}


async def text_vs_kb(
    selected_text: str,
    mode: str,
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare selected text with knowledge base. mode: compare | factcheck | position."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    if not selected_text or not selected_text.strip():
        return {"error": "No text provided", "consistent": [], "conflicts": []}

    # Retrieve relevant chunks
    q_vec = (await emb.embed([selected_text[:4000]]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=12)
    if not hits:
        if mode == "factcheck":
            return {"verdict": "unverified", "explanation": "No matching documents in knowledge base.", "sources": [], "consistent": [], "conflicts": []}
        if mode == "position":
            return {"position": "No internal position found in knowledge base.", "sources": [], "confidence": 0.0}
        return {"consistent": [], "conflicts": [], "message": "No relevant documents found."}

    excerpts = _excerpts_from_hits(hits)

    if mode == "compare":
        spec = prompts.get("text_vs_kb_compare") or {}
        sys = spec.get("system", "Compare selected text with excerpts. Output JSON with consistent and conflicts arrays.")
        user_tpl = spec.get("user_template", "Selected text:\n{{ selected_text }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
        user_msg = user_tpl.replace("{{ selected_text }}", selected_text[:3000]).replace("{{ excerpts }}", excerpts[:8000])
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=2000,
        )
        out = _parse_json_from_llm(raw or "")
        return {
            "consistent": out.get("consistent", []),
            "conflicts": out.get("conflicts", []),
            "selected_text": selected_text[:500],
        }

    if mode == "factcheck":
        spec = prompts.get("text_vs_kb_factcheck") or {}
        sys = spec.get("system", "Fact-check claim against excerpts. Output JSON: verdict, explanation, sources.")
        user_tpl = spec.get("user_template", "Claim: {{ claim }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
        user_msg = user_tpl.replace("{{ claim }}", selected_text[:2000]).replace("{{ excerpts }}", excerpts[:8000])
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=1500,
        )
        out = _parse_json_from_llm(raw or "")
        return {
            "verdict": out.get("verdict", "unverified"),
            "explanation": out.get("explanation", ""),
            "sources": out.get("sources", []),
            "correct_info": out.get("correct_info", ""),
        }

    if mode == "position":
        spec = prompts.get("text_vs_kb_position") or {}
        sys = spec.get("system", "State our position based on excerpts. Output JSON: position, sources, confidence.")
        user_tpl = spec.get("user_template", "Topic/claim: {{ selected_text }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
        user_msg = user_tpl.replace("{{ selected_text }}", selected_text[:2000]).replace("{{ excerpts }}", excerpts[:8000])
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=1000,
        )
        out = _parse_json_from_llm(raw or "")
        return {
            "position": out.get("position", ""),
            "sources": out.get("sources", []),
            "confidence": float(out.get("confidence", 0)),
        }

    return {"error": "Invalid mode", "mode": mode}


async def verify_claims(
    claims: list[str],
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """For each claim, check if supported by KB. Returns list of {claim, supported, source, snippet}."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    spec = prompts.get("text_vs_kb_factcheck") or {}
    sys = spec.get("system", "Fact-check claim. Output JSON: verdict (correct/incorrect/unverified), explanation, sources.")
    results = []
    for claim in claims[:20]:
        claim = (claim or "").strip()
        if not claim:
            continue
        q_vec = (await emb.embed([claim[:2000]]))[0]
        hits = await vector_store.search(namespace, q_vec, top_k=5)
        excerpts = _excerpts_from_hits(hits) if hits else "No relevant documents."
        user_tpl = spec.get("user_template", "Claim: {{ claim }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
        user_msg = user_tpl.replace("{{ claim }}", claim).replace("{{ excerpts }}", excerpts[:6000])
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
            stream=False,
            max_tokens=500,
        )
        out = _parse_json_from_llm(raw or "")
        verdict = out.get("verdict", "unverified")
        results.append({
            "claim": claim,
            "supported": verdict == "correct",
            "verdict": verdict,
            "explanation": out.get("explanation", ""),
            "sources": out.get("sources", []),
            "correct_info": out.get("correct_info", ""),
        })
    return results


async def email_analyze(
    subject: str,
    body: str,
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract key info, related docs, actions, reply context from email + KB."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    combined = f"{subject or ''}\n\n{body or ''}"[:6000]
    if not combined.strip():
        return {"key_info": [], "suggested_actions": [], "reply_context": "", "related_doc_names": []}
    q_vec = (await emb.embed([combined]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=8)
    excerpts = _excerpts_from_hits(hits) if hits else ""
    spec = prompts.get("email_analyze") or {}
    sys = spec.get("system", "Analyze email. Output JSON: key_info, suggested_actions, reply_context, related_doc_names.")
    user_tpl = spec.get("user_template", "Subject: {{ subject }}\nBody: {{ body }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ subject }}", (subject or "")[:500]).replace("{{ body }}", (body or "")[:5000]).replace("{{ excerpts }}", excerpts[:6000])
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=1500,
    )
    out = _parse_json_from_llm(raw or {})
    return {
        "key_info": out.get("key_info", []),
        "suggested_actions": out.get("suggested_actions", []),
        "reply_context": out.get("reply_context", ""),
        "related_doc_names": out.get("related_doc_names", []),
    }


async def contract_review(
    contract_text: str,
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare contract excerpt to standard terms in KB."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    if not contract_text or not contract_text.strip():
        return {"consistent": [], "deviations": [], "not_in_standard": []}
    q_vec = (await emb.embed(["standard terms template contract clause"]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=10)
    standard_excerpts = _excerpts_from_hits(hits) if hits else "No standard terms in knowledge base."
    spec = prompts.get("contract_review") or {}
    sys = spec.get("system", "Compare contract to standard. Output JSON: consistent, deviations, not_in_standard.")
    user_tpl = spec.get("user_template", "Contract:\n{{ contract_text }}\n\nStandard:\n{{ standard_excerpts }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ contract_text }}", contract_text[:8000]).replace("{{ standard_excerpts }}", standard_excerpts[:8000])
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=2000,
    )
    out = _parse_json_from_llm(raw or {})
    return {
        "consistent": out.get("consistent", []),
        "deviations": out.get("deviations", []),
        "not_in_standard": out.get("not_in_standard", []),
    }


async def research_synthesize(
    sources: list[str],
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthesize multiple research sources into findings and draft."""
    config = config or load_config()
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    if not sources:
        return {"key_findings": [], "agreements": [], "disagreements": [], "synthesis_draft": ""}
    sources_text = "\n\n--- SOURCE ---\n\n".join((s[:4000] for s in sources[:25]))
    spec = prompts.get("research_synthesize") or {}
    sys = spec.get("system", "Synthesize sources. Output JSON: key_findings, agreements, disagreements, synthesis_draft.")
    user_tpl = spec.get("user_template", "Sources:\n{{ sources }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ sources }}", sources_text[:20000])
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=3000,
    )
    out = _parse_json_from_llm(raw or {})
    return {
        "key_findings": out.get("key_findings", []),
        "agreements": out.get("agreements", []),
        "disagreements": out.get("disagreements", []),
        "synthesis_draft": out.get("synthesis_draft", ""),
    }


async def form_field_suggest(
    field_labels: list[str],
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Suggest values for form fields from KB."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    prompts = _load_extension_prompts(config)
    if not field_labels:
        return {"suggestions": []}
    query = " ".join(field_labels[:30])[:500]
    q_vec = (await emb.embed([query]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=15)
    excerpts = _excerpts_from_hits(hits) if hits else ""
    spec = prompts.get("form_field_suggest") or {}
    sys = spec.get("system", "Suggest field values from excerpts. Output JSON: suggestions array.")
    user_tpl = spec.get("user_template", "Fields: {{ field_labels }}\n\nExcerpts:\n{{ excerpts }}\n\nJSON only:")
    user_msg = user_tpl.replace("{{ field_labels }}", json.dumps(field_labels)).replace("{{ excerpts }}", excerpts[:8000])
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=1500,
    )
    out = _parse_json_from_llm(raw or {})
    return {"suggestions": out.get("suggestions", [])}


async def meeting_prep(
    meeting_title: str,
    attendee_names: list[str],
    tenant_id: str,
    namespace: str,
    vector_store,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate meeting prep brief from KB: last notes, account context, relevant docs."""
    config = config or load_config()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)
    if not meeting_title or not meeting_title.strip():
        return {"brief": "", "related_docs": [], "suggested_questions": []}
    query = f"Meeting: {meeting_title}. Attendees: {', '.join(attendee_names[:10]) if attendee_names else 'N/A'}. Preparation, context, notes, action items."
    q_vec = (await emb.embed([query[:2000]]))[0]
    hits = await vector_store.search(namespace, q_vec, top_k=10)
    excerpts = _excerpts_from_hits(hits) if hits else "No relevant documents in knowledge base."
    sys = (
        "You are a meeting prep assistant. Given a meeting title and relevant knowledge base excerpts, "
        "produce a brief (2–4 short paragraphs): last meeting notes or context, key facts about the topic/account, "
        "and 3–5 suggested questions to ask. Output JSON only: "
        '{"brief": "string", "related_docs": ["doc name"], "suggested_questions": ["string"]}'
    )
    user_msg = f"Meeting: {meeting_title}\n\nKnowledge base excerpts:\n{excerpts[:6000]}"
    raw = await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        stream=False,
        max_tokens=1200,
    )
    out = _parse_json_from_llm(raw or {})
    return {
        "brief": out.get("brief", ""),
        "related_docs": out.get("related_docs", []),
        "suggested_questions": out.get("suggested_questions", []),
    }
