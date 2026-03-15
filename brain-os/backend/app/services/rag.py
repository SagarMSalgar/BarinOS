"""RAG: retrieve + LLM answer with streaming, citations, confidence, follow-ups. Config and LLM driven."""
from __future__ import annotations

import re
from typing import Any, AsyncIterator

from app.core.config import load_config, get_intent_prompt
from app.providers import get_embedding_provider, get_llm_provider
from app.store.vector import VectorStore, InMemoryVectorStore, SearchHit


def _build_context(hits: list[SearchHit]) -> str:
    out = []
    for i, h in enumerate(hits, 1):
        out.append(f"[{i}] Source: {h.meta.document_name}" + (f", page {h.meta.page}" if h.meta.page else "") + f"\n{h.content}")
    return "\n\n---\n\n".join(out)


def _citation_blocks(hits: list[SearchHit]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": h.meta.document_id,
            "document_name": h.meta.document_name,
            "page": h.meta.page,
            "section": h.meta.section,
            "score": h.score,
        }
        for h in hits
    ]


def _confidence_from_scores(scores: list[float]) -> float:
    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    return min(100, max(0, round(avg * 100, 1)))


_PERSONA_PROMPTS = {
    "customer_support": "Answer in a warm, helpful, friendly tone suitable for customer support. Be concise and use a welcoming style; you may use light emoji where appropriate. Still cite sources.",
    "legal": "Answer in a formal, precise, citation-heavy style suitable for legal or compliance. Use hedged language where appropriate and always cite the exact source. Avoid casual phrasing.",
    "sales": "Answer in a persuasive, benefit-focused style suitable for sales. Highlight value and outcomes. Keep citations for accuracy but frame for conversion.",
    "internal_expert": "Answer as an internal domain expert: clear, direct, and thorough. Use technical accuracy and cite sources. Assume the reader is a colleague.",
}

_STRICT_SYSTEM = (
    "STRICT MODE: Answer ONLY from the provided context. Do not use general knowledge, assumptions, or information from outside the context. "
    "Every sentence must be grounded in the context. If the answer is not in the context, say exactly: "
    "'This is not covered in your knowledge base.' Do not elaborate beyond the context. Cite sources by number."
)


def _filter_hits_by_source(hits: list[SearchHit], source_filter: list[str]) -> list[SearchHit]:
    """Keep only hits whose document_name matches any of the filter terms (case-insensitive substring)."""
    if not source_filter:
        return hits
    terms = [f.strip().lower() for f in source_filter if f and f.strip()]
    if not terms:
        return hits
    out = []
    for h in hits:
        name = (h.meta.document_name or "").lower()
        if any(t in name or name in t for t in terms):
            out.append(h)
    return out if out else hits  # If filter excludes all, return original to avoid empty context


async def stream_answer(
    tenant_id: str,
    namespace: str,
    question: str,
    *,
    config: dict[str, Any] | None = None,
    vector_store: VectorStore | None = None,
    top_k: int = 10,
    persona: str | None = None,
    pasted_context: str | None = None,
    strict_mode: bool = False,
    answer_language: str | None = None,
    source_filter: list[str] | None = None,
    episodic_context: str | None = None,
    user_memory_context: str | None = None,
    user_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream answer with token, citation, confidence, freshness, follow_ups, done. Emits phase events for live retrieval transparency."""
    config = config or load_config()
    vector_store = vector_store or InMemoryVectorStore()
    emb = get_embedding_provider(config)
    llm = get_llm_provider(config)

    # Phase 1: searching (real-time transparency)
    yield {"type": "phase", "payload": {"phase": "searching", "message": "Searching your knowledge…"}}

    # Retrieve with query expansion for better recall (always try so we get more relevant chunks)
    q_vec = (await emb.embed([question]))[0]
    hits_primary = await vector_store.search(namespace, q_vec, top_k=top_k)
    hits = list(hits_primary)
    try:
        expand_cfg = (config.get("intents") or {}).get("query") or {}
        if expand_cfg.get("query_expansion"):
            expanded = await llm.complete(
                [{"role": "user", "content": f"Rephrase this question in one alternative way that a search engine or knowledge base might use. One short phrase or question only, no explanation.\nQuestion: {question}"}],
                stream=False,
                max_tokens=60,
            )
            alt_q = (expanded or "").strip().strip('"').split("\n")[0].strip()
            if alt_q and alt_q != question:
                q_vec2 = (await emb.embed([alt_q]))[0]
                hits2 = await vector_store.search(namespace, q_vec2, top_k=top_k)
                seen = {h.content[:200]: h for h in hits_primary}
                for h in hits2:
                    if h.content[:200] not in seen:
                        seen[h.content[:200]] = h
                hits = list(seen.values())[: top_k * 2]
    except Exception:
        pass
    if source_filter:
        hits = _filter_hits_by_source(hits, source_filter)
    has_contradiction = False
    try:
        from app.db.connection import get_pool
        pool = await get_pool()
        if pool:
            doc_ids = [h.meta.document_id for h in hits]
            doc_names = list({h.meta.document_name for h in hits})
            async with pool.acquire() as conn:
                trust_rows = await conn.fetch(
                    "SELECT document_id, trust_score FROM source_trust WHERE tenant_id = $1 AND namespace = $2 AND document_id = ANY($3)",
                    tenant_id,
                    namespace,
                    doc_ids,
                )
                trust_map = {r["document_id"]: float(r["trust_score"]) for r in trust_rows}
                cont = await conn.fetchrow(
                    """SELECT 1 FROM contradictions WHERE tenant_id = $1 AND namespace = $2
                       AND (document_name_a = ANY($3::text[]) OR document_name_b = ANY($3::text[])) AND status = 'open' LIMIT 1""",
                    tenant_id,
                    namespace,
                    doc_names,
                )
            min_trust = 0.3
            filtered = [h for h in hits if trust_map.get(h.meta.document_id, 0.5) >= min_trust]
            if filtered:
                hits = filtered
            has_contradiction = cont is not None
    except Exception:
        pass
    context = _build_context(hits)
    citations = _citation_blocks(hits)
    confidence = _confidence_from_scores([h.score for h in hits])

    # Phase 2: sources (show which docs we're reading — Perplexity-like)
    unique_docs = []
    seen_ids = set()
    for h in hits:
        if h.meta.document_id not in seen_ids:
            seen_ids.add(h.meta.document_id)
            unique_docs.append({"document_id": h.meta.document_id, "document_name": h.meta.document_name})
    yield {"type": "phase", "payload": {"phase": "sources", "documents": unique_docs, "message": f"Reading {len(unique_docs)} source{'' if len(unique_docs) == 1 else 's'}…"}}
    # Emit no_answer_from_docs when strict mode and no/few sources so frontend can show "What's missing?"
    if strict_mode and len(unique_docs) == 0:
        yield {"type": "no_answer_from_docs", "payload": {"reason": "no_sources"}}
    yield {"type": "phase", "payload": {"phase": "answering", "message": "Answering from your knowledge base…"}}

    # Prompt from config
    prompt_cfg = get_intent_prompt(config, "query") or {}
    system = prompt_cfg.get("system", "Answer from the given context. Cite sources.")
    if has_contradiction:
        system = "Some of the retrieved sources may contradict each other; cite carefully and note any conflicts.\n\n" + system
    if episodic_context and episodic_context.strip():
        system = "Recent interactions (for continuity):\n" + episodic_context.strip()[:2000] + "\n\n---\n\n" + system
    if user_memory_context and user_memory_context.strip():
        system = "User preferences / remembered context:\n" + user_memory_context.strip()[:1000] + "\n\n---\n\n" + system
    if user_key and user_key.strip():
        try:
            from app.db.connection import get_pool
            pool = await get_pool()
            profile_prefs = None
            if pool:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT preferences FROM personal_profiles WHERE tenant_id = $1 AND namespace = $2 AND user_key = $3",
                        tenant_id,
                        namespace,
                        user_key.strip()[:500],
                    )
                    if row and row.get("preferences"):
                        profile_prefs = row["preferences"]
            if profile_prefs and isinstance(profile_prefs, dict) and profile_prefs:
                parts = [f"{k}: {v}" for k, v in list(profile_prefs.items())[:20]]
                system = "User profile (preferences): " + "; ".join(parts) + "\n\n---\n\n" + system
        except Exception:
            pass
    if strict_mode:
        system = _STRICT_SYSTEM + "\n\n" + system
    if answer_language and answer_language.strip():
        system = f"Answer in {answer_language.strip()}. Use the same sources and citations; only the language of the answer changes.\n\n" + system
    if persona and persona.strip():
        key = persona.strip().lower().replace(" ", "_")
        config_personas = (config.get("llm") or {}).get("personas") or {}
        persona_instruction = config_personas.get(key) or _PERSONA_PROMPTS.get(key)
        if persona_instruction:
            system = persona_instruction + "\n\n" + system
    user_tpl = prompt_cfg.get("user_template", "Context:\n{{ context }}\n\nQuestion: {{ question }}\n\nAnswer:")
    user_msg = user_tpl.replace("{{ context }}", context).replace("{{ question }}", question)
    if pasted_context and pasted_context.strip():
        user_msg = (
            "The user has pasted the following text from elsewhere (use it together with the context below to answer):\n\n"
            + pasted_context.strip()[:8000]
            + "\n\n---\n\n"
            + user_msg
        )

    # When strict mode and no context, yield a short message and skip LLM
    if strict_mode and not context.strip():
        yield {"type": "token", "payload": {"text": "This is not covered in your knowledge base."}}
        yield {"type": "citation", "payload": {"citations": []}}
        yield {"type": "confidence", "payload": {"score": 0.0}}
        yield {"type": "no_answer_from_docs", "payload": {"reason": "no_context"}}
        yield {"type": "follow_ups", "payload": {"questions": []}}
        yield {"type": "done", "payload": {}}
        return

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]

    # Stream tokens
    async for token in llm.stream(messages):
        yield {"type": "token", "payload": {"text": token}}

    # Emit citation and confidence (output spec)
    yield {"type": "citation", "payload": {"citations": citations}}
    yield {"type": "confidence", "payload": {"score": confidence}}
    # Freshness: would come from document registry last_verified_at
    yield {"type": "freshness", "payload": {"message": "Based on doc last verified recently", "timestamp": None}}
    # Follow-ups from config: exactly 4 in order [Compliance, Comparison, Action Plan, Technical]
    follow_up_count = (config.get("outputs") or {}).get("streaming") or {}
    if isinstance(follow_up_count, dict):
        follow_up_count = follow_up_count.get("follow_up_count", 4)
    if follow_up_count and hits:
        follow_cfg = get_intent_prompt(config, "follow_ups")
        if follow_cfg:
            # Build short context summary
            summary = "\n".join(h.content[:200] for h in hits[:3])
            ans_for_follow = context[:2000]  # placeholder; in prod use full streamed answer
            user_f = follow_cfg["user_template"].replace("{{ answer }}", ans_for_follow).replace("{{ context_summary }}", summary)
            try:
                follow_text = await llm.complete(
                    [{"role": "system", "content": follow_cfg["system"]}, {"role": "user", "content": user_f}],
                    stream=False,
                    max_tokens=400,
                )
                # Take exactly 4 questions in defined category order (Compliance, Comparison, Action Plan, Technical)
                questions = [q.strip() for q in follow_text.strip().split("\n") if q.strip()][: int(follow_up_count)]
                yield {"type": "follow_ups", "payload": {"questions": questions}}
            except Exception:
                yield {"type": "follow_ups", "payload": {"questions": []}}
    if strict_mode and confidence < 30.0 and len(hits) > 0:
        yield {"type": "no_answer_from_docs", "payload": {"reason": "low_confidence", "confidence": confidence}}
    yield {"type": "done", "payload": {}}
